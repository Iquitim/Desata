"""Versões anteriores dos fluxos de um espaço da equipe, com o autor (spec 047, RF-4731, RF-4761, RF-4762).

Ficam na própria pasta do espaço, para todos verem: ``_equipe/versoes/<fluxo>/<AAAAMMDD-HHMMSS-ffffff>-<origem>-<usuário>
.json``, com a assinatura de quem salvou ao lado (``.sig``). Como as versões da biblioteca (spec 046), guardam o fluxo
inteiro, sem a amostra dos dados. A data do nome só ordena e é mostrada; quem decide se uma versão vale é a assinatura.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

from prodata.domain.workflow import ID_PATTERN, Workflow
from prodata.errors import InvalidInputError, NotFoundError
from prodata.services.versions import AUTO_GAP, Changes, changes_between
from prodata.team.repository import SIG, atomic_write
from prodata.team.signing import Members, Signature, check_flow, flow_content
from prodata.team.workspaces import CONTROL

log = logging.getLogger(__name__)

SpaceOrigin = Literal["manual", "auto", "restore", "conflito", "copia"]
MAX_VERSIONS = 50  # o espaço guarda mais que a biblioteca: várias pessoas salvam o mesmo fluxo
VERSIONS_DIR = "versoes"
_NAME = re.compile(r"^(\d{8}-\d{6}-\d{6})-(manual|auto|restore|conflito|copia)-([A-Za-z0-9._-]{1,64})\.json$")
_ID = re.compile(ID_PATTERN)
UNKNOWN = "desconhecido"  # cópia de conflito sem assinatura: ninguém para creditar


class SpaceVersionInfo(BaseModel):
    id: str
    created_at: datetime
    origin: SpaceOrigin
    name: str
    node_count: int
    autor: str
    autor_nome: str
    confere: bool = False  # assinatura válida de um membro que podia editar
    sha256: str = ""
    changes: Changes | None = None


def content_sha(workflow: Workflow) -> str:
    """A impressão do conteúdo, a mesma da assinatura: serve de base para descobrir conflitos (RF-4761)."""
    return hashlib.sha256(flow_content(workflow)).hexdigest()


def _text(workflow: Workflow) -> str:
    return json.dumps(
        workflow.model_dump(mode="json", by_alias=True, exclude={"samples"}), ensure_ascii=False
    )


class SpaceVersions:
    def __init__(self, space_root: Path, space_id: str,
                 clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:  # fmt: skip
        self.folder = space_root / CONTROL / VERSIONS_DIR
        self.space_id = space_id
        self._clock = clock
        self._lock = threading.Lock()

    def _dir(self, workflow_id: str) -> Path:
        if not _ID.match(workflow_id):
            raise InvalidInputError("Identificador de fluxo inválido.")
        return self.folder / workflow_id

    def _files(self, workflow_id: str) -> list[tuple[Path, datetime, SpaceOrigin, str]]:
        folder = self._dir(workflow_id)
        if not folder.is_dir():
            return []
        out: list[tuple[Path, datetime, SpaceOrigin, str]] = []
        for file in folder.iterdir():
            m = _NAME.match(file.name)
            if not m:
                continue
            when = datetime.strptime(m.group(1), "%Y%m%d-%H%M%S-%f").replace(tzinfo=UTC)
            out.append((file, when, m.group(2), m.group(3)))  # type: ignore[arg-type]
        out.sort(key=lambda item: item[1], reverse=True)
        return out

    @staticmethod
    def _read(path: Path) -> Workflow:
        return Workflow.model_validate_json(path.read_text(encoding="utf-8"))

    @staticmethod
    def _signature(path: Path) -> Signature | None:
        try:
            return Signature.model_validate_json(
                path.with_name(f"{path.name}{SIG}").read_text(encoding="utf-8")
            )
        except OSError, ValidationError, ValueError:
            return None

    def record(self, workflow: Workflow, origin: SpaceOrigin, signature: Signature | None,
               author: str | None = None) -> SpaceVersionInfo | None:  # fmt: skip
        """Guarda uma versão. Devolve None quando não guardou: igual à última, ou automático cedo demais. Uma versão
        de conflito ou de cópia sempre entra (é justamente o que não pode se perder)."""
        user = author or (signature.autor if signature else UNKNOWN)
        with self._lock:
            files = self._files(workflow.id)
            now = self._clock()
            if files and origin not in ("conflito", "copia"):
                last, last_when, _, last_user = files[0]
                if origin == "auto" and last_user == user and now - last_when < AUTO_GAP:
                    return None
                try:
                    if content_sha(self._read(last)) == content_sha(workflow):
                        return None
                except (OSError, ValidationError, ValueError) as exc:
                    log.warning("Versão ilegível ignorada: %s (%s)", last.name, exc)
            if (
                files and now <= files[0][1]
            ):  # relógio atrasado em relação a quem salvou antes: mantém a ordem
                now = files[0][1] + timedelta(microseconds=1)
            folder = self._dir(workflow.id)
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / f"{now.strftime('%Y%m%d-%H%M%S-%f')}-{origin}-{user}.json"
            atomic_write(target, _text(workflow))
            if signature is not None:
                atomic_write(target.with_name(f"{target.name}{SIG}"), signature.model_dump_json(indent=1))
            for old, _, _, _ in self._files(workflow.id)[MAX_VERSIONS:]:
                old.unlink(missing_ok=True)
                old.with_name(f"{old.name}{SIG}").unlink(missing_ok=True)
            return self._info(target, now, origin, user, workflow, signature, None)

    def _info(self, path: Path, when: datetime, origin: SpaceOrigin, user: str, workflow: Workflow,
              signature: Signature | None, members: Members | None) -> SpaceVersionInfo:  # fmt: skip
        name = signature.nome if signature and signature.autor == user and signature.nome else user
        if user == UNKNOWN:
            name = "outro computador (cópia da sincronização)"
        ok = members is not None and check_flow(signature, self.space_id, workflow, members) is None
        if ok and members is not None and signature is not None:
            member = members.member(signature.autor, signature.chave_publica)
            name = member.nome if member else name
        return SpaceVersionInfo(id=path.name.removesuffix(".json"), created_at=when, origin=origin,
                                name=workflow.name, node_count=len(workflow.nodes), autor=user, autor_nome=name,
                                confere=ok, sha256=content_sha(workflow))  # fmt: skip

    def history(self, workflow_id: str, members: Members | None,
                current: Workflow | None = None) -> list[SpaceVersionInfo]:  # fmt: skip
        out: list[SpaceVersionInfo] = []
        for file, when, origin, user in self._files(workflow_id):
            try:
                wf = self._read(file)
            except (OSError, ValidationError, ValueError) as exc:
                log.warning("Versão ilegível ignorada: %s (%s)", file.name, exc)
                continue
            info = self._info(file, when, origin, user, wf, self._signature(file), members)
            if current is not None:
                info.changes = changes_between(wf, current)
            out.append(info)
        return out

    def get(self, workflow_id: str, version_id: str) -> Workflow:
        if not _NAME.match(f"{version_id}.json"):
            raise InvalidInputError("Versão inválida.")
        file = self._dir(workflow_id) / f"{version_id}.json"
        if not file.is_file():
            raise NotFoundError(
                f"Essa versão não existe mais (o espaço guarda as {MAX_VERSIONS} mais recentes)."
            )
        return self._read(file)

    def find(self, workflow_id: str, sha256: str) -> str | None:
        """O id da versão mais recente com esse conteúdo (para "Ver o que mudou" desde a que você viu)."""
        for file, _, _, _ in self._files(workflow_id):
            try:
                if content_sha(self._read(file)) == sha256:
                    return file.name.removesuffix(".json")
            except OSError, ValidationError, ValueError:
                continue
        return None
