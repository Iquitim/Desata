"""O que este computador lembra de cada espaço (spec 047): fica na pasta de dados, nunca na pasta do espaço.

- ``vistos``: o conteúdo (impressão) de cada fluxo da última vez que esta pessoa o abriu ou salvou, para a faixa
  "Atualizado por Bruno" (RF-4732);
- ``confianca``: as partes sensíveis da última versão liberada ou confiada (RF-4741);
- ``pendentes/``: versões que a sincronização não deixou gravar na hora, para enviar depois (RF-4763).
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any

from prodata.domain.workflow import ID_PATTERN
from prodata.errors import InvalidInputError
from prodata.team.repository import atomic_write

_ID = re.compile(ID_PATTERN)
MAX_FLOWS = 5000  # bem acima do uso real; evita que o arquivo cresça sem limite


class LocalState:
    def __init__(self, folder: Path, space_id: str) -> None:
        self.path = folder / f"{space_id}-local.json"
        self.pending_dir = folder / "pendentes" / space_id
        self._lock = threading.Lock()

    def _load(self) -> dict[str, dict[str, Any]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except OSError, ValueError:
            return {"vistos": {}, "confianca": {}}
        if not isinstance(data, dict):
            return {"vistos": {}, "confianca": {}}
        out: dict[str, dict[str, Any]] = {}
        for section in ("vistos", "confianca"):
            value = data.get(section)
            out[section] = value if isinstance(value, dict) else {}
        return out

    def _put(self, section: str, workflow_id: str, value: Any) -> None:
        with self._lock:
            data = self._load()
            part = data[section]
            part.pop(workflow_id, None)
            part[workflow_id] = value
            while len(part) > MAX_FLOWS:
                part.pop(next(iter(part)))
            self.path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(self.path, json.dumps(data, ensure_ascii=False, indent=1))

    def seen(self, workflow_id: str) -> str | None:
        value = self._load()["vistos"].get(workflow_id)
        return value if isinstance(value, str) else None

    def set_seen(self, workflow_id: str, sha256: str) -> None:
        self._put("vistos", workflow_id, sha256)

    def trusted(self, workflow_id: str) -> dict[str, str] | None:
        value = self._load()["confianca"].get(workflow_id)
        return {str(k): str(v) for k, v in value.items()} if isinstance(value, dict) else None

    def set_trusted(self, workflow_id: str, parts: dict[str, str]) -> None:
        self._put("confianca", workflow_id, parts)

    # ------------------------------------------------------------------ envio adiado (RF-4763)

    def _pending(self, workflow_id: str) -> Path:
        if not _ID.match(workflow_id):
            raise InvalidInputError("Identificador de fluxo inválido.")
        return self.pending_dir / f"{workflow_id}.json"

    def add_pending(self, workflow_id: str, item: dict[str, Any]) -> None:
        self.pending_dir.mkdir(parents=True, exist_ok=True)
        atomic_write(self._pending(workflow_id), json.dumps(item, ensure_ascii=False))

    def pending(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        if not self.pending_dir.is_dir():
            return out
        for path in self.pending_dir.glob("*.json"):
            if not _ID.match(path.stem):
                continue
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
            except OSError, ValueError:
                continue
            if isinstance(item, dict):
                out[path.stem] = item
        return out

    def drop_pending(self, workflow_id: str) -> None:
        self._pending(workflow_id).unlink(missing_ok=True)
