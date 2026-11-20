"""Chamadas ao ``schtasks.exe`` (spec 044, RF-4437): sem shell, só códigos de saída e XML (o texto é traduzido).

O executor é injetável: os testes não mexem no Agendador de verdade.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from prodata.errors import ProdataError
from prodata.scheduling.task_xml import enabled_from_xml

Runner = Callable[[list[str]], subprocess.CompletedProcess[str]]


class SchedulerError(ProdataError):
    code = "scheduler"


def schtasks() -> str:
    return str(Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32" / "schtasks.exe")


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # nada de console piscando
    return subprocess.run(  # noqa: S603  (executável fixo do sistema, argumentos em lista)
        [schtasks(), *args], capture_output=True, text=True, timeout=30, creationflags=flags, check=False
    )


def supported() -> bool:
    return sys.platform == "win32"


class TaskScheduler:
    def __init__(self, runner: Runner | None = None) -> None:
        self.runner = runner or _run

    def _call(self, args: list[str], what: str) -> subprocess.CompletedProcess[str]:
        try:
            done = self.runner(args)
        except (OSError, subprocess.SubprocessError) as exc:
            raise SchedulerError(
                f"Não foi possível falar com o Agendador do Windows ({what}): {exc}"
            ) from exc
        if done.returncode != 0:
            detail = (done.stderr or done.stdout or "").strip()
            hint = ""
            if "acesso" in detail.lower() or "access" in detail.lower():
                hint = " Pode ser uma regra da empresa que bloqueia tarefas agendadas: use a linha de comando, em Avançado."
            raise SchedulerError(f"O Agendador do Windows recusou ({what}): {detail}.{hint}")
        return done

    def create(self, name: str, xml: str) -> None:
        # O schtasks lê o XML de um arquivo; UTF-16 com BOM, como o próprio Agendador grava.
        fd, tmp = tempfile.mkstemp(suffix=".xml", prefix="tarefa_")
        os.close(fd)
        try:
            Path(tmp).write_text(xml, encoding="utf-16")
            self._call(["/Create", "/TN", name, "/XML", tmp, "/F"], "criar a tarefa")
        finally:
            Path(tmp).unlink(missing_ok=True)

    def state(self, name: str) -> str:
        """``active``, ``paused`` ou ``missing`` (apagada no Agendador do Windows)."""
        try:
            done = self.runner(["/Query", "/TN", name, "/XML"])
        except OSError, subprocess.SubprocessError:
            return "unknown"
        if done.returncode != 0:
            return "missing"
        return "active" if enabled_from_xml(done.stdout) else "paused"

    def set_enabled(self, name: str, enabled: bool) -> None:
        self._call(["/Change", "/TN", name, "/ENABLE" if enabled else "/DISABLE"], "pausar ou retomar")

    def run_now(self, name: str) -> None:
        self._call(["/Run", "/TN", name], "executar agora")

    def delete(self, name: str) -> None:
        self._call(["/Delete", "/TN", name, "/F"], "excluir a tarefa")
