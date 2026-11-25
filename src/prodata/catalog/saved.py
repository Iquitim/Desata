"""Fontes públicas guardadas na vista Dados e o aviso Dados novos (spec 049, RF-4915, RF-4935).

- Guardadas (``<catálogo>/fontes_publicas.json``): a fonte e as escolhas, como na caixa, para usar em vários fluxos.
- Novidades (``<catálogo>/novidades.json``): a última atualização que cada órgão informou, conferida só com o catálogo
  aberto (constituição 1.8.1). A vista Dados e o canvas comparam com a leitura guardada, sem acessar a rede.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from prodata.catalog import cache

NEWS_EVERY = timedelta(hours=6)


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    os.replace(tmp, path)


def _read(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return default


class SavedSources:
    def __init__(self, root: Path) -> None:
        self.path = root / "fontes_publicas.json"
        self._lock = threading.Lock()

    def list(self) -> list[dict[str, Any]]:
        data = _read(self.path, [])
        return [d for d in data if isinstance(d, dict) and d.get("key") and isinstance(d.get("fonte"), dict)]

    def add(self, fonte: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            rows = self.list()
            item = {
                "key": uuid.uuid4().hex[:12],
                "fonte": fonte,
                "criado_em": datetime.now().isoformat(timespec="seconds"),
            }
            rows.append(item)
            _write(self.path, rows)
            return item

    def update(self, key: str, fonte: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            rows = self.list()
            for row in rows:
                if row["key"] == key:
                    row["fonte"] = fonte
                    _write(self.path, rows)
                    return row
        raise KeyError(key)

    def delete(self, key: str) -> None:
        with self._lock:
            rows = [r for r in self.list() if r["key"] != key]
            _write(self.path, rows)


class News:
    """A última atualização informada por cada órgão, por fonte (sem as escolhas: é a da fonte)."""

    def __init__(self, root: Path) -> None:
        self.path = root / "novidades.json"
        self.root = root
        self._lock = threading.Lock()

    def load(self) -> dict[str, dict[str, Any]]:
        data = _read(self.path, {})
        return data if isinstance(data, dict) else {}

    def due(self, source_id: str, now: datetime) -> bool:
        last = self.load().get(source_id, {}).get("conferido_em")
        return not last or now - datetime.fromisoformat(last) >= NEWS_EVERY

    def record(self, source_id: str, updated: str | None, label: str, now: datetime) -> None:
        with self._lock:
            data = self.load()
            data[source_id] = {
                "atualizado": updated,
                "rotulo": label,
                "conferido_em": now.isoformat(timespec="seconds"),
            }
            _write(self.path, data)

    def state(self, source_id: str, choices: dict[str, Any]) -> dict[str, Any]:
        """Compara o que o órgão informou com a leitura guardada desta consulta (sem rede)."""
        info = self.load().get(source_id, {})
        saved = cache.load(self.root, source_id, choices)
        out: dict[str, Any] = {"id": source_id, "atualizado": info.get("atualizado"), "rotulo": info.get("rotulo", ""),
                               "lido_em": saved.read_at.isoformat(timespec="seconds") if saved else None,
                               "novo": False, "texto": ""}  # fmt: skip
        updated = _day(info.get("atualizado"))
        if saved is None or updated is None:
            return out
        if info.get("rotulo") == "último dado em" and "data" in saved.frame.columns and saved.frame.height:
            last = saved.frame["data"].max()
            last_day = last.date() if isinstance(last, datetime) else last
            if isinstance(last_day, date) and updated > last_day:
                out.update(
                    novo=True,
                    texto=f"O órgão já tem dados até {updated:%d/%m/%Y}; a última leitura vai até {last_day:%d/%m/%Y}.",
                )
        elif updated > saved.read_at.date():
            out.update(
                novo=True,
                texto=f"O órgão publicou dados novos em {updated:%d/%m/%Y}, depois da última leitura ({saved.read_at:%d/%m/%Y}).",
            )
        return out


def _day(text: Any) -> date | None:
    if not text:
        return None
    try:
        return datetime.fromisoformat(str(text)[:10]).date()
    except ValueError:
        return None
