"""Agendamentos (``agendamentos.json``) e histórico das execuções agendadas (``logs/agendamentos.jsonl``)."""

from __future__ import annotations

import builtins
import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, TypeAdapter, ValidationError

from prodata.errors import InvalidInputError, NotFoundError
from prodata.scheduling.model import Schedule

_LIST = TypeAdapter(list[Schedule])
MAX_HISTORY_BYTES = 2_000_000  # o histórico é cortado pela metade quando passa disso


class RunRecord(BaseModel):
    """Uma execução agendada: gravada pelo ``run --agendamento``, mesmo quando recusada."""

    schedule_id: str
    workflow: str = ""
    started_at: datetime
    finished_at: datetime
    status: Literal["ok", "failed", "refused"]
    errors: int = 0
    files: int = 0
    message: str = ""


class ScheduleStore:
    def __init__(self, path: Path, history: Path) -> None:
        self.path = path
        self.history = history
        self._lock = threading.Lock()

    def _read(self) -> list[Schedule]:
        if not self.path.is_file():
            return []
        try:
            return _LIST.validate_json(self.path.read_text(encoding="utf-8"))
        except (OSError, ValidationError) as exc:
            raise InvalidInputError(f"Lista de agendamentos corrompida em {self.path.name}: {exc}") from exc

    def _write(self, items: list[Schedule]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps([s.model_dump(mode="json") for s in items], indent=2, ensure_ascii=False), "utf-8"
        )
        os.replace(tmp, self.path)

    def list(self) -> list[Schedule]:
        with self._lock:
            return self._read()

    def get(self, schedule_id: str) -> Schedule:
        for s in self.list():
            if s.id == schedule_id:
                return s
        raise NotFoundError("Agendamento não encontrado.")

    def save(self, schedule: Schedule) -> Schedule:
        with self._lock:
            items = [s for s in self._read() if s.id != schedule.id]
            items.append(schedule)
            self._write(sorted(items, key=lambda s: (s.name.lower(), s.created_at)))
        return schedule

    def delete(self, schedule_id: str) -> None:
        with self._lock:
            self._write([s for s in self._read() if s.id != schedule_id])

    # ------------------------------------------------------------------ histórico

    def record(self, entry: RunRecord) -> None:
        self.history.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            if self.history.is_file() and self.history.stat().st_size > MAX_HISTORY_BYTES:
                lines = self.history.read_text(encoding="utf-8").splitlines()
                self.history.write_text("\n".join(lines[len(lines) // 2 :]) + "\n", encoding="utf-8")
            with self.history.open("a", encoding="utf-8") as fh:
                fh.write(entry.model_dump_json() + "\n")

    def records(self) -> builtins.list[RunRecord]:
        if not self.history.is_file():
            return []
        out: builtins.list[RunRecord] = []
        for line in self.history.read_text(encoding="utf-8").splitlines():
            try:
                out.append(RunRecord.model_validate_json(line))
            except ValidationError:
                continue  # linha cortada no meio de uma gravação: as outras continuam valendo
        return out

    def last_runs(self) -> dict[str, RunRecord]:
        last: dict[str, RunRecord] = {}
        for r in self.records():
            last[r.schedule_id] = r
        return last


def seen_file(store: ScheduleStore) -> Path:
    return store.path.with_name("agendamentos_vistos.json")


def read_seen(store: ScheduleStore) -> str:
    path = seen_file(store)
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except OSError, ValueError:
        data = {}
    return str(data.get("until", ""))
