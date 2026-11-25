"""Downloads grandes do catálogo: o CNPJ da Receita (spec 049, RF-4951..4953, constituição 1.8.0).

- Só na pasta que a pessoa escolheu: caminho absoluto, já existente, fora da pasta de dados do programa e fora das
  pastas dos espaços da equipe. O programa cria ali só a subpasta ``CNPJ-AAAA-MM`` e grava nomes fixos.
- Endereços e tamanhos vêm sempre da listagem da Receita, nunca do pedido da tela.
- Um arquivo por vez, em segundo plano, gravando em ``<arquivo>.parte`` e retomando com ``Range`` do ponto em que
  parou (depois de Pausar, de uma queda ou de fechar o programa). Só renomeia quando o tamanho bate com o anunciado.
- Uma parte que falha tenta de novo sozinha três vezes antes de pedir ação; disco cheio pausa na hora, com o motivo.
- O estado de cada download fica em ``<catálogo>/downloads/<id>.json``: dá para continuar ao abrir o programa.
"""

from __future__ import annotations

import contextlib
import errno
import json
import logging
import os
import re
import shutil
import threading
import time
import uuid
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from prodata.catalog.http import CatalogClient, CatalogError
from prodata.catalog.readers import receita

log = logging.getLogger(__name__)

RETRIES = 3
RETRY_WAIT = 5.0
CHUNK = 1024 * 1024
SAVE_EVERY = 1.0  # segundos entre gravações do estado durante o download
EXPANSION = 4  # o CSV descompactado ocupa umas 4 vezes o ZIP (conferido nos meses de 2026)
FINAL = {"concluido", "cancelado"}
_ID = re.compile(r"^[0-9a-f]{12}$")


class DownloadError(ValueError):
    """Pedido que não dá para atender, com o motivo em palavras (pasta proibida, espaço, já em andamento...)."""


class _StoppedError(Exception):
    pass


def check_folder(raw: str, forbidden: Iterable[Path]) -> Path:
    """A pasta escolhida: absoluta, existente, gravável e fora das pastas proibidas (RF-4952)."""
    text = (raw or "").strip().strip('"')
    path = Path(text)
    if not text or not path.is_absolute():
        raise DownloadError("Escolha a pasta com Baixar…: o caminho precisa ser completo, como D:\\Dados.")
    if not path.is_dir():
        raise DownloadError(f"A pasta {path} não existe ou não está acessível agora.")
    resolved = path.resolve()
    for blocked in forbidden:
        try:
            base = blocked.resolve()
        except OSError:
            continue
        if resolved == base or base in resolved.parents:
            raise DownloadError(
                f"Essa pasta fica dentro de {base}, que é do programa ou de um espaço da equipe. Escolha outra pasta: "
                "o CNPJ é grande e é deste computador."
            )
    if not os.access(resolved, os.W_OK):
        raise DownloadError(f"Não há permissão para gravar em {resolved}.")
    return resolved


def free_space(folder: Path) -> int:
    return shutil.disk_usage(folder).free


def space_needed(sizes: Iterable[int], keep_zips: bool) -> int:
    """Estimativa do espaço: os ZIPs (se forem mantidos) mais o CSV descompactado de cada um."""
    sizes = list(sizes)
    unzipped = sum(sizes) * EXPANSION
    return unzipped + (sum(sizes) if keep_zips else max(sizes, default=0))


def _disk_full(exc: OSError) -> bool:
    return exc.errno == errno.ENOSPC or getattr(exc, "winerror", None) in (39, 112)


class DownloadManager:
    """Os downloads deste computador: começar, acompanhar, pausar, continuar e cancelar."""

    def __init__(
        self,
        root: Path,
        forbidden: Callable[[], list[Path]],
        *,
        client_factory: Callable[[], CatalogClient] = lambda: CatalogClient(timeout=60),
        retries: int = RETRIES,
        retry_wait: float = RETRY_WAIT,
        after_download: Callable[[DownloadManager, dict[str, Any]], None] | None = None,
    ) -> None:
        self.folder = root / "downloads"
        self.forbidden = forbidden
        self.client_factory = client_factory
        self.retries = retries
        self.retry_wait = retry_wait
        self.after_download = after_download
        self._lock = threading.RLock()
        self._threads: dict[str, threading.Thread] = {}
        self._stop: dict[str, threading.Event] = {}
        self._jobs: dict[str, dict[str, Any]] = {}
        self._load()

    # ------------------------------------------------------------------ estado

    def _path(self, job_id: str) -> Path:
        return self.folder / f"{job_id}.json"

    def _load(self) -> None:
        if not self.folder.is_dir():
            return
        for file in self.folder.glob("*.json"):
            try:
                job = json.loads(file.read_text(encoding="utf-8"))
            except OSError, ValueError:
                continue
            if not isinstance(job, dict) or not _ID.match(str(job.get("id", ""))):
                continue
            if (
                job.get("estado") == "baixando"
            ):  # o programa fechou (ou caiu) no meio: fica pausado para continuar
                job.update(
                    estado="pausado", motivo="O programa foi fechado durante o download.", velocidade=0
                )
            self._jobs[job["id"]] = job

    def _save(self, job: dict[str, Any]) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self._path(job["id"])
        tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(job, ensure_ascii=False, indent=1), encoding="utf-8")
        for attempt in range(5):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:  # o Windows prende o arquivo enquanto alguém o lê: tenta de novo
                if attempt == 4:
                    tmp.unlink(missing_ok=True)
                    raise
                time.sleep(0.05)

    def _view(self, job: dict[str, Any]) -> dict[str, Any]:
        done = sum(p["baixado"] for p in job["partes"])
        total = sum(p["tamanho"] for p in job["partes"])
        speed = job.get("velocidade") or 0
        current = next((p["arquivo"] for p in job["partes"] if p["estado"] == "baixando"), None)
        return {**job, "baixado": done, "total": total, "parte_atual": current,
                "restante_s": round((total - done) / speed) if speed and job["estado"] == "baixando" else None}  # fmt: skip

    def get(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise DownloadError("Esse download não existe mais.")
            return self._view(job)

    def jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                self._view(j) for j in sorted(self._jobs.values(), key=lambda j: j["criado_em"], reverse=True)
            ]

    def pending(self) -> list[dict[str, Any]]:
        """Downloads parados no meio: a vista Dados oferece Continuar o download do CNPJ."""
        return [j for j in self.jobs() if j["estado"] in ("pausado", "erro")]

    # ------------------------------------------------------------------ planejar e começar

    def plan(self, month: str, files: list[str], folder: str, keep_zips: bool = False) -> dict[str, Any]:
        """Antes de baixar: o tamanho das partes escolhidas, o espaço livre e se basta (RF-4951, RF-4952)."""
        chosen = check_folder(folder, self.forbidden())
        with self.client_factory() as client:
            parts = self._chosen(client, month, files)
        need = space_needed([p.tamanho for p in parts], keep_zips)
        free = free_space(chosen)
        return {"mes": month, "pasta": str(chosen), "destino": str(chosen / f"CNPJ-{month}"),
                "tamanho": sum(p.tamanho for p in parts), "necessario": need, "livre": free, "cabe": free >= need}  # fmt: skip

    @staticmethod
    def _chosen(client: CatalogClient, month: str, files: list[str]) -> list[receita.Part]:
        listed = {p.arquivo: p for p in receita.parts(client, month)}
        unknown = [f for f in files if f not in listed]
        if unknown:
            raise DownloadError(
                f"Estes arquivos não estão na pasta {month} da Receita: {', '.join(unknown[:5])}."
            )
        if not files:
            raise DownloadError("Marque pelo menos uma parte para baixar.")
        return [listed[f] for f in dict.fromkeys(files)]

    def start(self, month: str, files: list[str], folder: str, keep_zips: bool = False) -> dict[str, Any]:
        chosen = check_folder(folder, self.forbidden())
        with self._lock:
            if any(t.is_alive() for t in self._threads.values()):
                raise DownloadError(
                    "Já há um download em andamento. Espere terminar ou pause antes de começar outro."
                )
        with self.client_factory() as client:
            parts = self._chosen(client, month, files)
        need = space_needed([p.tamanho for p in parts], keep_zips)
        free = free_space(chosen)
        if free < need:
            raise DownloadError(
                f"Falta espaço em {chosen}: são precisos uns {_gb(need)} (ZIPs e arquivos descompactados) e há "
                f"{_gb(free)} livres. Escolha outra pasta ou menos partes."
            )
        dest = chosen / f"CNPJ-{month}"
        dest.mkdir(exist_ok=True)
        job: dict[str, Any] = {
            "id": uuid.uuid4().hex[:12], "fonte": "receita.cnpj/dados-abertos", "mes": month, "pasta": str(chosen),
            "destino": str(dest), "manter_zips": keep_zips, "estado": "baixando", "motivo": "", "velocidade": 0,
            "criado_em": datetime.now().isoformat(timespec="seconds"),
            "partes": [{**p.as_dict(), "baixado": 0, "estado": "esperando", "tentativas": 0} for p in parts],
        }  # fmt: skip
        with self._lock:
            self._jobs[job["id"]] = job
            self._save(job)
            self._launch(job)
        return self._view(job)

    def _launch(self, job: dict[str, Any]) -> None:
        stop = threading.Event()
        self._stop[job["id"]] = stop
        thread = threading.Thread(
            target=self._run, args=(job, stop), name=f"download-{job['id']}", daemon=True
        )
        self._threads[job["id"]] = thread
        thread.start()

    # ------------------------------------------------------------------ pausar, continuar, cancelar

    def pause(self, job_id: str) -> dict[str, Any]:
        self._halt(job_id)
        with self._lock:
            job = self._jobs[job_id]
            if job["estado"] == "baixando":
                job.update(estado="pausado", motivo="Pausado por você.", velocidade=0)
                self._save(job)
            return self._view(job)

    def resume(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise DownloadError("Esse download não existe mais.")
            if job["estado"] not in ("pausado", "erro"):
                return self._view(job)
            if any(t.is_alive() for i, t in self._threads.items() if i != job_id):
                raise DownloadError(
                    "Já há outro download em andamento. Pause aquele antes de continuar este."
                )
        dest = Path(job["destino"])
        if not dest.is_dir():
            raise DownloadError(f"A pasta {dest} não está mais acessível. Conecte o disco e tente de novo.")
        with self._lock:
            for part in job["partes"]:
                if part["estado"] == "erro":
                    part.update(estado="esperando", tentativas=0)
            job.update(estado="baixando", motivo="")
            self._save(job)
            self._launch(job)
            return self._view(job)

    def cancel(self, job_id: str) -> dict[str, Any]:
        """Para e apaga só o que este download gravou (os ZIPs e as partes); a pasta some se ficar vazia."""
        self._halt(job_id)
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise DownloadError("Esse download não existe mais.")
            dest = Path(job["destino"])
            for part in job["partes"]:
                for name in (part["arquivo"], f"{part['arquivo']}.parte"):
                    with contextlib.suppress(OSError):
                        (dest / name).unlink(missing_ok=True)
            with contextlib.suppress(OSError):
                dest.rmdir()  # só se ficou vazia: nada que a pessoa pôs ali é apagado
            job.update(estado="cancelado", motivo="Cancelado por você.", velocidade=0)
            self._save(job)
            return self._view(job)

    def _halt(self, job_id: str) -> None:
        with self._lock:
            if job_id not in self._jobs:
                raise DownloadError("Esse download não existe mais.")
            stop, thread = self._stop.get(job_id), self._threads.get(job_id)
        if stop is not None:
            stop.set()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=30)

    def shutdown(self) -> None:
        """Ao fechar o programa: pausa o que estiver baixando, para continuar ao abrir (RF-4953)."""
        with self._lock:
            running = [i for i, t in self._threads.items() if t.is_alive()]
        for job_id in running:
            self._halt(job_id)
            with self._lock:
                job = self._jobs[job_id]
                if job["estado"] == "baixando":
                    job.update(
                        estado="pausado", motivo="O programa foi fechado durante o download.", velocidade=0
                    )
                    self._save(job)

    # ------------------------------------------------------------------ o download

    def _run(self, job: dict[str, Any], stop: threading.Event) -> None:
        try:
            with self.client_factory() as client:
                for part in job["partes"]:
                    if part["estado"] == "baixado":
                        continue
                    if not self._part_with_retries(client, job, part, stop):
                        return
        except Exception as exc:
            log.exception("download %s", job["id"])
            self._fail(job, f"O download parou por um erro inesperado: {exc}")
            return
        with self._lock:
            job.update(estado="baixado", motivo="", velocidade=0)
            self._save(job)
        if self.after_download is not None:
            self.after_download(self, job)
        else:
            with self._lock:
                job["estado"] = "concluido"
                self._save(job)

    def _part_with_retries(
        self, client: CatalogClient, job: dict[str, Any], part: dict[str, Any], stop: threading.Event
    ) -> bool:
        while True:
            try:
                self._fetch(client, job, part, stop)
                return True
            except _StoppedError:
                return False
            except OSError as exc:
                if _disk_full(exc):
                    self._fail(
                        job,
                        f"O disco de {job['pasta']} ficou cheio. Libere espaço e use Continuar.",
                        "pausado",
                    )
                    return False
                reason = f"não foi possível gravar em {job['destino']} ({exc.strerror or exc})"
            except CatalogError as exc:
                reason = exc.message
            except httpx.HTTPError as exc:  # a conexão caiu no meio do arquivo: continua do ponto, com Range
                reason = f"a conexão com a Receita caiu ({type(exc).__name__})."
            with self._lock:
                part["tentativas"] += 1
                tries = part["tentativas"]
                self._save(job)
            if tries >= self.retries:
                with self._lock:
                    part["estado"] = "erro"
                self._fail(
                    job,
                    f"{part['arquivo']}: {reason} Tentou {tries} vezes; use Continuar para tentar de novo.",
                )
                return False
            if stop.wait(self.retry_wait * tries):
                return False

    def _fail(self, job: dict[str, Any], reason: str, state: str = "erro") -> None:
        with self._lock:
            job.update(estado=state, motivo=reason, velocidade=0)
            for part in job["partes"]:
                if part["estado"] == "baixando":
                    part["estado"] = "esperando"
            self._save(job)

    def _fetch(
        self, client: CatalogClient, job: dict[str, Any], part: dict[str, Any], stop: threading.Event
    ) -> None:
        dest = Path(job["destino"])
        final = dest / part["arquivo"]
        partial = dest / f"{part['arquivo']}.parte"
        size = part["tamanho"]
        have = partial.stat().st_size if partial.exists() else 0
        if have > size:  # maior que o anunciado: não dá para confiar no que está ali
            partial.unlink()
            have = 0
        with self._lock:
            part.update(estado="baixando", baixado=have)
            self._save(job)
        if have < size:
            headers = {"Range": f"bytes={have}-"} if have else {}
            with client.stream(part["url"], headers=headers, auth=receita.auth_for(part["url"])) as response:
                if have and response.status_code == 206:
                    start = re.match(r"bytes (\d+)-", response.headers.get("content-range", ""))
                    if not start or int(start.group(1)) != have:
                        raise CatalogError("A Receita respondeu um trecho diferente do pedido.", "resposta")
                    mode = "ab"
                else:  # 200: o servidor mandou o arquivo inteiro (sem retomar)
                    have, mode = 0, "wb"
                with partial.open(mode) as fh:
                    last_save = tick = time.monotonic()
                    tick_bytes = 0
                    for chunk in response.iter_bytes(CHUNK):
                        if stop.is_set():
                            raise _StoppedError
                        fh.write(chunk)
                        have += len(chunk)
                        tick_bytes += len(chunk)
                        if have > size:
                            raise CatalogError(
                                "O arquivo veio maior que o anunciado pela Receita.", "resposta"
                            )
                        now = time.monotonic()
                        if now - tick >= 0.5:
                            speed = tick_bytes / (now - tick)
                            with self._lock:
                                job["velocidade"] = round(
                                    speed if not job["velocidade"] else 0.7 * job["velocidade"] + 0.3 * speed
                                )
                            tick, tick_bytes = now, 0
                        with self._lock:
                            part["baixado"] = have
                            if now - last_save >= SAVE_EVERY:
                                self._save(job)
                                last_save = now
            if stop.is_set():
                raise _StoppedError
            if have != size:
                with self._lock:
                    part["baixado"] = have
                raise CatalogError(f"veio incompleto ({_gb(have)} de {_gb(size)}).", "conexao")
        os.replace(partial, final)
        with self._lock:
            part.update(estado="baixado", baixado=size, tentativas=0)
            self._save(job)


def _gb(n: int) -> str:
    if n >= 1024**3:
        return f"{n / 1024**3:.1f} GB".replace(".", ",")
    return f"{n / 1024**2:.0f} MB"
