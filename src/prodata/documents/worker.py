"""Leitura de PDF num processo separado (spec 037, RF-3780).

Um PDF quebrado ou hostil não pode derrubar o programa: toda leitura (abrir, palavras, imagem) roda num processo filho,
com tempo limite por pedido e limite de memória. No Windows, o filho entra num Job Object com teto de memória e morre
junto se o programa fechar; fora dele, ``RLIMIT_AS``. Estourou o tempo ou o filho caiu: ele é encerrado, a falha volta
com código, e o próximo pedido sobe um filho novo.
"""

from __future__ import annotations

import ctypes
import multiprocessing as mp
import sys
import threading
import time
from multiprocessing.connection import Connection
from typing import Any

from prodata.documents.reader import PdfReadError

DEFAULT_TIMEOUT = 60.0
DEFAULT_MEMORY_MB = 1536
_OPS = ("inspect", "render")


def _limit_memory_posix(memory_mb: int) -> None:
    import resource  # só existe fora do Windows

    limit = memory_mb * 2**20
    getattr(resource, "setrlimit")(getattr(resource, "RLIMIT_AS"), (limit, limit))  # noqa: B009


def _serve(conn: Connection, memory_mb: int, test_ops: bool) -> None:
    """Laço do processo filho: recebe (operação, argumentos), devolve ("ok", resultado) ou ("erro", código, detalhe)."""
    if sys.platform != "win32":
        _limit_memory_posix(memory_mb)
    from prodata.documents import reader

    while True:
        try:
            op, kwargs = conn.recv()
        except EOFError:
            return
        try:
            if op == "inspect":
                conn.send(("ok", reader.inspect(**kwargs)))
            elif op == "render":
                conn.send(("ok", reader.render(**kwargs)))
            elif test_ops and op == "_dormir":
                time.sleep(kwargs["segundos"])
                conn.send(("ok", None))
            elif test_ops and op == "_consumir":
                blob = bytearray(kwargs["mb"] * 2**20)
                conn.send(("ok", len(blob)))
            else:
                conn.send(("erro", "operacao_invalida", ""))
        except PdfReadError as exc:
            conn.send(("erro", exc.code, exc.detail))
        except MemoryError:
            conn.send(("erro", "memoria", ""))
        except Exception as exc:  # o tipo ajuda a investigar; a mensagem pode trazer conteúdo, então não vai
            conn.send(("erro", "falha_leitura", type(exc).__name__))


# ------------------------------------------------------------------ Job Object (Windows)


class _IoCounters(ctypes.Structure):
    _fields_ = [(n, ctypes.c_ulonglong) for n in ("r_ops", "w_ops", "o_ops", "r_bytes", "w_bytes", "o_bytes")]


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimits),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


_LIMIT_PROCESS_MEMORY = 0x0100
_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
_EXTENDED_LIMIT_INFORMATION = 9
_PROCESS_SET_QUOTA_AND_TERMINATE = 0x0100 | 0x0001


def _job_with_memory_limit(pid: int, memory_mb: int) -> int:
    """Coloca o processo num Job Object com teto de memória. Devolve o handle do job (fechar encerra o processo)."""
    kernel32 = getattr(ctypes, "WinDLL")("kernel32", use_last_error=True)  # noqa: B009
    kernel32.CreateJobObjectW.restype = ctypes.c_void_p
    kernel32.OpenProcess.restype = ctypes.c_void_p
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise OSError("CreateJobObject falhou")
    info = _ExtendedLimits()
    info.BasicLimitInformation.LimitFlags = _LIMIT_PROCESS_MEMORY | _LIMIT_KILL_ON_JOB_CLOSE
    info.ProcessMemoryLimit = memory_mb * 2**20
    ok = kernel32.SetInformationJobObject(
        ctypes.c_void_p(job), _EXTENDED_LIMIT_INFORMATION, ctypes.byref(info), ctypes.sizeof(info)
    )
    process = kernel32.OpenProcess(_PROCESS_SET_QUOTA_AND_TERMINATE, False, pid)
    if (
        not ok
        or not process
        or not kernel32.AssignProcessToJobObject(ctypes.c_void_p(job), ctypes.c_void_p(process))
    ):
        kernel32.CloseHandle(ctypes.c_void_p(job))
        raise OSError("não foi possível limitar a memória do leitor de PDF")
    kernel32.CloseHandle(ctypes.c_void_p(process))
    return int(job)


def _close_job(job: int) -> None:
    getattr(ctypes, "WinDLL")("kernel32").CloseHandle(ctypes.c_void_p(job))  # noqa: B009


# ------------------------------------------------------------------ cliente


class PdfWorker:
    """Fila de leitura num processo filho. Seguro entre threads: um pedido por vez."""

    def __init__(
        self, timeout: float = DEFAULT_TIMEOUT, memory_mb: int = DEFAULT_MEMORY_MB, *, test_ops: bool = False
    ) -> None:
        self.timeout = timeout
        self.memory_mb = memory_mb
        self.test_ops = test_ops
        self._lock = threading.Lock()
        self._proc: Any = None
        self._conn: Any = None
        self._job: int | None = None

    def _start(self) -> None:
        ctx = mp.get_context("spawn")
        parent, child = ctx.Pipe()
        proc = ctx.Process(
            target=_serve, args=(child, self.memory_mb, self.test_ops), daemon=True, name="leitor-pdf"
        )
        proc.start()
        child.close()
        self._proc, self._conn = proc, parent
        if sys.platform == "win32":
            try:
                self._job = _job_with_memory_limit(int(proc.pid or 0), self.memory_mb)
            except OSError:
                self._stop()
                raise PdfReadError("sem_isolamento", "não foi possível limitar a memória") from None

    def _stop(self) -> None:
        if self._conn is not None:
            self._conn.close()
        if self._proc is not None and self._proc.is_alive():
            self._proc.terminate()
            self._proc.join(timeout=5)
        if self._job is not None:
            _close_job(self._job)
        self._proc, self._conn, self._job = None, None, None

    def call(self, op: str, timeout: float | None = None, **kwargs: Any) -> Any:
        if op not in _OPS and not (self.test_ops and op.startswith("_")):
            raise PdfReadError("operacao_invalida")
        with self._lock:
            if self._proc is None or not self._proc.is_alive():
                self._stop()
                self._start()
            assert self._conn is not None
            try:
                self._conn.send((op, kwargs))
                if not self._conn.poll(timeout or self.timeout):
                    self._stop()
                    raise PdfReadError("tempo_esgotado", f"mais de {int(timeout or self.timeout)} s")
                answer = self._conn.recv()
            except EOFError, BrokenPipeError, ConnectionResetError, OSError:
                code = self._proc.exitcode if self._proc is not None else None
                self._stop()
                raise PdfReadError("leitor_caiu", f"código {code}") from None
        if answer[0] == "ok":
            return answer[1]
        raise PdfReadError(answer[1], answer[2])

    def close(self) -> None:
        with self._lock:
            self._stop()

    def __enter__(self) -> PdfWorker:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
