"""Junta o cadastro, o Agendador do Windows e o histórico (spec 044, RF-4431..4438)."""

from __future__ import annotations

import json
import re
import secrets
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from prodata.brand import marca
from prodata.errors import InvalidInputError, NotFoundError
from prodata.scheduling.model import Schedule, ScheduleIn, next_run, sentence, when_text
from prodata.scheduling.store import ScheduleStore, read_seen, seen_file
from prodata.scheduling.task_xml import task_xml
from prodata.scheduling.windows import SchedulerError, TaskScheduler, supported
from prodata.services.trust import TrustRegistry
from prodata.services.workflows import SUFFIX, WorkflowRepository, load_from_file

TASK_EXE = "prodata-tarefa.exe"  # sem console e sem tela de abertura (RF-4436)
CLI_EXE = "prodata-cli.exe"


def task_command(schedule_id: str, target: str) -> tuple[str, str, str]:
    """Executável, argumentos e pasta da tarefa. Montado só aqui: nada vem da tela além do id conferido."""
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
        exe = base / TASK_EXE
        if not exe.is_file():
            exe = base / CLI_EXE
        args = ["run", target, "--agendamento", schedule_id]
        return str(exe), subprocess.list2cmdline(args), str(base)
    python = Path(sys.executable)
    windowless = python.with_name("pythonw.exe")
    exe = windowless if windowless.is_file() else python
    args = ["-m", "prodata", "run", target, "--agendamento", schedule_id]
    return str(exe), subprocess.list2cmdline(args), str(Path.cwd())


def task_name(s: Schedule) -> str:
    safe = re.sub(r'[\\/:*?"<>|]+', " ", s.name).strip()[:60] or "fluxo"
    return f"{marca().nome} - {safe} ({s.id})"


class SchedulingService:
    def __init__(
        self,
        store: ScheduleStore,
        workflows: WorkflowRepository,
        trust: TrustRegistry,
        scheduler: TaskScheduler | None = None,
        clock: Callable[[], datetime] = datetime.now,
        windows: Callable[[], bool] = supported,
    ) -> None:
        self.store = store
        self.workflows = workflows
        self.trust = trust
        self.scheduler = scheduler or TaskScheduler()
        self.clock = clock
        self.windows = windows

    # ------------------------------------------------------------------ conferências

    def _check(self, data: ScheduleIn) -> str:
        """Confere o fluxo e devolve o alvo do ``run`` (id ou caminho do arquivo)."""
        if not self.windows():
            raise InvalidInputError(
                "O agendamento visual existe só no Windows. Use a linha de comando, em Avançado."
            )
        if data.workflow_id:
            if not self.workflows.exists(data.workflow_id):
                raise NotFoundError("Salve o fluxo na biblioteca antes de agendar.")
            workflow = self.workflows.get(data.workflow_id)
            target = data.workflow_id
        else:
            path = Path(data.file_path)
            if not path.is_absolute() or not path.is_file() or not path.name.lower().endswith(SUFFIX):
                raise InvalidInputError(f"O arquivo do fluxo precisa existir e terminar em {SUFFIX}.")
            workflow, _ = load_from_file(str(path.resolve()))
            target = str(path.resolve())
        if not self.trust.opened(workflow):
            raise InvalidInputError(
                "Este fluxo veio de fora e ainda não foi confiado: abra, confira e escolha Confiar e executar antes de agendar."
            )
        return target

    def _install(self, s: Schedule, target: str) -> None:
        command, arguments, workdir = task_command(s.id, target)
        xml = task_xml(
            s,
            command=command,
            arguments=arguments,
            workdir=workdir,
            author=marca().nome,
            description=f'Criado pelo {marca().nome} para executar o fluxo "{s.name}". '
            f"Edite em {marca().nome} › Arquivo › Agendamentos.",
            start=self.clock(),
        )
        self.scheduler.create(task_name(s), xml)
        if s.paused:
            self.scheduler.set_enabled(task_name(s), False)

    # ------------------------------------------------------------------ ações

    def preview(self, data: ScheduleIn) -> dict[str, Any]:
        now = self.clock()
        moment = next_run(data, now)
        return {
            "sentence": sentence(data),
            "next_run": moment.isoformat(),
            "next_text": when_text(moment, now),
        }

    def create(self, data: ScheduleIn) -> dict[str, Any]:
        target = self._check(data)
        s = Schedule(**data.model_dump(), id=secrets.token_hex(4), created_at=self.clock())
        self._install(s, target)
        self.store.save(s)
        return self.item(s)

    def update(self, schedule_id: str, data: ScheduleIn) -> dict[str, Any]:
        old = self.store.get(schedule_id)
        target = self._check(data)
        s = Schedule(**data.model_dump(), id=old.id, created_at=old.created_at, paused=old.paused)
        if task_name(old) != task_name(s):
            self._forget(old)
        self._install(s, target)
        self.store.save(s)
        return self.item(s)

    def recreate(self, schedule_id: str) -> dict[str, Any]:
        s = self.store.get(schedule_id)
        self._install(s, self._check(s))
        return self.item(s)

    def set_paused(self, schedule_id: str, paused: bool) -> dict[str, Any]:
        s = self.store.get(schedule_id)
        self.scheduler.set_enabled(task_name(s), not paused)
        s = s.model_copy(update={"paused": paused})
        self.store.save(s)
        return self.item(s)

    def run_now(self, schedule_id: str) -> None:
        self.scheduler.run_now(task_name(self.store.get(schedule_id)))

    def _forget(self, s: Schedule) -> None:
        try:
            self.scheduler.delete(task_name(s))
        except SchedulerError:
            if self.scheduler.state(task_name(s)) != "missing":
                raise

    def delete(self, schedule_id: str) -> None:
        s = self.store.get(schedule_id)
        self._forget(s)
        self.store.delete(s.id)

    # ------------------------------------------------------------------ leitura

    def item(self, s: Schedule, last: dict[str, Any] | None = None) -> dict[str, Any]:
        now = self.clock()
        state = self.scheduler.state(task_name(s)) if self.windows() else "unsupported"
        paused = state == "paused" or (state != "active" and s.paused)
        moment = None if paused or state == "missing" else next_run(s, now)
        return {
            **s.model_dump(mode="json"),
            "paused": paused,
            "sentence": sentence(s),
            "task": state,
            "task_name": task_name(s),
            "next_run": moment.isoformat() if moment else None,
            "next_text": when_text(moment, now) if moment else None,
            "last": last,
        }

    def items(self) -> list[dict[str, Any]]:
        last = self.store.last_runs()
        return [
            self.item(s, last[s.id].model_dump(mode="json") if s.id in last else None)
            for s in self.store.list()
        ]

    def failures(self) -> list[dict[str, Any]]:
        """Execuções agendadas que falharam desde a última vez que a pessoa viu (RF-4435)."""
        until = read_seen(self.store)
        names = {s.id: s.name for s in self.store.list()}
        return [
            {**r.model_dump(mode="json"), "name": names.get(r.schedule_id, r.workflow)}
            for r in self.store.records()
            if r.status != "ok" and r.finished_at.isoformat() > until and r.schedule_id in names
        ]

    def mark_seen(self) -> None:
        seen_file(self.store).write_text(json.dumps({"until": self.clock().isoformat()}), encoding="utf-8")
