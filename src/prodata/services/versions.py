"""Versões anteriores de cada fluxo (spec 046, RF-4631..4634).

Uma versão é o fluxo inteiro, sem a amostra dos dados, num arquivo da pasta de dados deste computador:

- fluxo da biblioteca: ``<raiz>/biblioteca/<id do fluxo>/<AAAAMMDD-HHMMSS-ffffff>-<origem>.json``;
- fluxo salvo numa pasta: ``<raiz>/arquivos/<impressão do caminho>/…``. Cada arquivo tem o seu histórico, mesmo que
  duas cópias do fluxo (Salvar como) tenham o mesmo id. O caminho só entra no cálculo da impressão (SHA-256): nunca é
  aberto, nem gravado em texto.

O id do fluxo é validado (``ID_PATTERN``) e nenhum caminho de arquivo é montado com texto do cliente.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

from prodata.domain.workflow import ID_PATTERN, Workflow
from prodata.errors import InvalidInputError, NotFoundError

log = logging.getLogger(__name__)

Origin = Literal["manual", "auto", "restore", "columns"]
ORIGINS: tuple[Origin, ...] = ("manual", "auto", "restore", "columns")
MAX_VERSIONS = 30
AUTO_GAP = timedelta(minutes=10)  # o salvar automático guarda no máximo uma versão a cada 10 minutos
_NAME = re.compile(r"^(\d{8}-\d{6}-\d{6})-(manual|auto|restore|columns)\.json$")
_ID = re.compile(ID_PATTERN)
_SKIP_IDS = ("demo_pipeline_360",)  # o exemplo (e as lições, pelo prefixo) não guarda versões


class Changes(BaseModel):
    """O que mudou de uma versão para outra, em contagens (a tela escreve a frase)."""

    added: int = 0
    removed: int = 0
    changed: int = 0
    moved: int = 0
    wires_added: int = 0
    wires_removed: int = 0
    renamed: bool = False

    @property
    def empty(self) -> bool:
        return not any(
            (
                self.added,
                self.removed,
                self.changed,
                self.moved,
                self.wires_added,
                self.wires_removed,
                self.renamed,
            )
        )


class VersionInfo(BaseModel):
    id: str
    created_at: datetime
    origin: Origin
    name: str
    node_count: int
    changes: Changes | None = None  # em relação ao fluxo de agora, quando pedido


def keeps_versions(workflow_id: str) -> bool:
    """Exemplo e lições não guardam versões (RF-4634). O modo protegido é conferido por quem chama."""
    return workflow_id not in _SKIP_IDS and not workflow_id.startswith("licao_")


def _content(workflow: Workflow) -> dict[str, object]:
    return workflow.model_dump(mode="json", by_alias=True, exclude={"samples"})


def _digest(workflow: Workflow) -> str:
    raw = json.dumps(_content(workflow), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def changes_between(old: Workflow, new: Workflow) -> Changes:
    """Resumo do que mudou de ``old`` para ``new``: caixas por id; posição conta à parte; fios por ligação."""
    before = {n.id: n for n in old.nodes}
    after = {n.id: n for n in new.nodes}
    changed = moved = 0
    for node_id in before.keys() & after.keys():
        a, b = before[node_id], after[node_id]
        if (a.type, a.label, a.config, a.disabled) != (b.type, b.label, b.config, b.disabled):
            changed += 1
        elif (round(a.x), round(a.y)) != (round(b.x), round(b.y)):
            moved += 1

    def wires(wf: Workflow) -> set[tuple[str, str, str, str]]:
        return {(e.source, e.source_handle, e.target, e.target_handle) for e in wf.edges}

    w_old, w_new = wires(old), wires(new)
    return Changes(
        added=len(after.keys() - before.keys()),
        removed=len(before.keys() - after.keys()),
        changed=changed,
        moved=moved,
        wires_added=len(w_new - w_old),
        wires_removed=len(w_old - w_new),
        renamed=old.name != new.name,
    )


class VersionStore:
    def __init__(self, root: Path, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self.root = root
        self._clock = clock
        self._lock = threading.Lock()

    def _dir(self, workflow_id: str, path: str | None = None) -> Path:
        if not _ID.match(workflow_id):
            raise InvalidInputError("Identificador de fluxo inválido.")
        if path:
            normalized = os.path.normcase(os.path.normpath(path.strip()))
            return self.root / "arquivos" / hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]
        return self.root / "biblioteca" / workflow_id

    def _files(self, workflow_id: str, path: str | None = None) -> list[tuple[Path, datetime, Origin]]:
        """Arquivos de versão do fluxo, do mais novo para o mais antigo."""
        folder = self._dir(workflow_id, path)
        if not folder.is_dir():
            return []
        out: list[tuple[Path, datetime, Origin]] = []
        for file in folder.iterdir():
            m = _NAME.match(file.name)
            if not m:
                continue
            when = datetime.strptime(m.group(1), "%Y%m%d-%H%M%S-%f").replace(tzinfo=UTC)
            out.append((file, when, m.group(2)))  # type: ignore[arg-type]
        out.sort(key=lambda item: item[1], reverse=True)
        return out

    def _read(self, path: Path) -> Workflow:
        return Workflow.model_validate_json(path.read_text(encoding="utf-8"))

    def record(self, workflow: Workflow, origin: Origin, path: str | None = None) -> VersionInfo | None:
        """Guarda uma versão (``path``: o arquivo do fluxo salvo numa pasta; sem ele, a biblioteca).
        Devolve None quando não guardou (igual à última, ou automático cedo demais)."""
        if not keeps_versions(workflow.id):
            return None
        with self._lock:
            files = self._files(workflow.id, path)
            now = self._clock()
            if files:
                last_path, last_when, _ = files[0]
                if origin == "auto" and now - last_when < AUTO_GAP:
                    return None
                try:
                    if _digest(self._read(last_path)) == _digest(workflow):
                        return None
                except (OSError, ValidationError) as exc:
                    log.warning("Versão ilegível ignorada: %s (%s)", last_path.name, exc)
            folder = self._dir(workflow.id, path)
            folder.mkdir(parents=True, exist_ok=True)
            if files and now <= files[0][1]:  # relógio parado ou para trás: mantém a ordem dos arquivos
                now = files[0][1] + timedelta(microseconds=1)
            target = folder / f"{now.strftime('%Y%m%d-%H%M%S-%f')}-{origin}.json"
            tmp = target.with_suffix(".tmp")
            tmp.write_text(json.dumps(_content(workflow), ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, target)
            for old, _, _ in self._files(workflow.id, path)[MAX_VERSIONS:]:
                old.unlink(missing_ok=True)
            return self._info(target, now, origin, workflow)

    @staticmethod
    def _info(path: Path, when: datetime, origin: Origin, workflow: Workflow) -> VersionInfo:
        return VersionInfo(
            id=path.name.removesuffix(".json"),
            created_at=when,
            origin=origin,
            name=workflow.name,
            node_count=len(workflow.nodes),
        )

    def history(
        self, workflow_id: str, current: Workflow | None = None, path: str | None = None
    ) -> list[VersionInfo]:
        out: list[VersionInfo] = []
        for file, when, origin in self._files(workflow_id, path):
            try:
                wf = self._read(file)
            except (OSError, ValidationError) as exc:
                log.warning("Versão ilegível ignorada: %s (%s)", file.name, exc)
                continue
            info = self._info(file, when, origin, wf)
            if current is not None:
                info.changes = changes_between(wf, current)
            out.append(info)
        return out

    def get(self, workflow_id: str, version_id: str, path: str | None = None) -> Workflow:
        if not _NAME.match(f"{version_id}.json"):
            raise InvalidInputError("Versão inválida.")
        file = self._dir(workflow_id, path) / f"{version_id}.json"
        if not file.is_file():
            raise NotFoundError("Essa versão não existe mais (o fluxo guarda as 30 mais recentes).")
        return self._read(file)

    def delete_all(self, workflow_id: str) -> None:
        """Fluxo da biblioteca excluído: as versões vão junto. Arquivo numa pasta não é excluído pelo programa."""
        for file, _, _ in self._files(workflow_id):
            file.unlink(missing_ok=True)
