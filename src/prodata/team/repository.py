"""Fluxos de um espaço da equipe (spec 047, RF-4703, RF-4705, RF-4763).

Os fluxos ficam na raiz da pasta do espaço como arquivos ``<id>.prodata.json`` comuns: quem abre a pasta no Explorer
reconhece, e o Abrir arquivo de sempre continua funcionando. Só arquivos do espaço são gravados ali, nunca dados das
fontes, resultados ou amostras (constituição, princípio IV).
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ValidationError

from prodata.domain.workflow import ID_PATTERN, Workflow
from prodata.errors import InvalidInputError, NotFoundError

SUFFIX = ".prodata.json"
SIG = ".sig"  # assinatura ao lado do fluxo (spec 047)
RETRIES = (
    8  # a sincronização (OneDrive, SharePoint) pode segurar o arquivo por alguns segundos enquanto envia
)
RETRY_WAIT = 0.4
_ID = re.compile(ID_PATTERN)


class HeldFileError(InvalidInputError):
    """A sincronização segurou o arquivo além das novas tentativas (RF-4763): quem chama pode adiar o envio."""


class SpaceFlow(BaseModel):
    id: str
    name: str
    node_count: int
    modified_at: datetime
    editando: str | None = None  # quem está editando agora (spec 047, RF-4724)
    editando_desde: datetime | None = None


def atomic_write(path: Path, text: str, *, retries: int = RETRIES, wait: float = RETRY_WAIT,
                 sleep: Callable[[float], None] = time.sleep) -> None:  # fmt: skip
    """Grava por inteiro ou nada: temporário ao lado e troca atômica. Arquivo preso pela sincronização: tenta de
    novo algumas vezes antes de desistir (RF-4763); quem chama decide o que fazer se não der."""
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    for attempt in range(retries):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == retries - 1:
                tmp.unlink(missing_ok=True)
                raise
            sleep(wait)


def _content(workflow: Workflow) -> str:
    """O que vai para a pasta do espaço: o fluxo sem a amostra dos dados (RF-4705)."""
    data = workflow.model_dump(mode="json", by_alias=True, exclude={"samples"})
    return json.dumps(data, indent=2, ensure_ascii=False)


class SpaceRepository:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, workflow_id: str) -> Path:
        if not _ID.match(workflow_id):
            raise InvalidInputError("Identificador de fluxo inválido.")
        return self.root / f"{workflow_id}{SUFFIX}"

    def flows(self) -> list[SpaceFlow]:
        """Os fluxos do espaço. Só vale o arquivo cujo nome é o id do fluxo: cópias de conflito da sincronização
        (``fluxo-NOTEANA.prodata.json``) não viram fluxos soltos na biblioteca (RF-4762)."""
        out: list[SpaceFlow] = []
        for path in sorted(self.root.glob(f"*{SUFFIX}")):
            stem = path.name.removesuffix(SUFFIX)
            try:
                wf = Workflow.model_validate_json(path.read_text(encoding="utf-8"))
                modified = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
            except OSError, ValidationError, ValueError:
                continue
            if wf.id != stem:
                continue
            out.append(SpaceFlow(id=wf.id, name=wf.name, node_count=len(wf.nodes), modified_at=modified))
        out.sort(key=lambda f: f.modified_at, reverse=True)
        return out

    def exists(self, workflow_id: str) -> bool:
        return self._path(workflow_id).is_file()

    def get(self, workflow_id: str) -> Workflow:
        path = self._path(workflow_id)
        if not path.is_file():
            raise NotFoundError(
                "Esse fluxo não está mais no espaço (foi apagado ou a sincronização ainda não trouxe)."
            )
        try:
            return Workflow.model_validate_json(path.read_text(encoding="utf-8"))
        except (ValidationError, ValueError) as exc:
            raise InvalidInputError(
                f"O arquivo do fluxo no espaço está ilegível ({exc.__class__.__name__})."
            ) from exc

    def save(self, workflow: Workflow, signature: str | None = None) -> Workflow:
        """Grava o fluxo e, ao lado, a assinatura de quem salvou (``<id>.prodata.json.sig``, spec 047, RF-4714)."""
        path = self._path(workflow.id)
        try:
            atomic_write(path, _content(workflow))
            if signature is not None:
                atomic_write(path.with_name(f"{path.name}{SIG}"), signature)
        except PermissionError as exc:
            raise HeldFileError(
                "A pasta do espaço segurou o arquivo por tempo demais (a sincronização ainda está enviando?) ou não "
                "permite gravar. Tente de novo em instantes; nada foi perdido."
            ) from exc
        return workflow.model_copy(update={"samples": {}})

    def conflict_copies(self) -> list[tuple[Path, Workflow]]:
        """Cópias de conflito criadas pela sincronização (RF-4762): ``fluxo-NOTEANA.prodata.json`` (OneDrive,
        SharePoint), ``fluxo (1).prodata.json``, ``fluxo.prodata.sync-conflict-….json`` (Syncthing). Valem só as de
        um fluxo que existe no espaço; o resto da pasta não é da conta do programa."""
        out: list[tuple[Path, Workflow]] = []
        for path in sorted(self.root.glob("*.json")):
            if ".prodata" not in path.name or path.name.endswith(".tmp"):
                continue
            try:
                wf = Workflow.model_validate_json(path.read_text(encoding="utf-8"))
            except OSError, ValidationError, ValueError:
                continue
            if path.name != f"{wf.id}{SUFFIX}" and _ID.match(wf.id) and self.exists(wf.id):
                out.append((path, wf))
        return out

    def copy_signature(self, path: Path) -> str | None:
        try:
            return path.with_name(f"{path.name}{SIG}").read_text(encoding="utf-8")
        except OSError:
            return None

    def remove_copy(self, path: Path) -> None:
        """Tira da pasta uma cópia de conflito que já virou versão (o conteúdo está guardado em Versões)."""
        if path.parent != self.root or not any(path == p for p, _ in self.conflict_copies()):
            raise InvalidInputError("Esse arquivo não é uma cópia de conflito do espaço.")
        path.unlink(missing_ok=True)
        path.with_name(f"{path.name}{SIG}").unlink(missing_ok=True)

    def signature(self, workflow_id: str) -> str | None:
        """O texto da assinatura da versão de trabalho, ou None se não houver (alterado ou criado fora do programa)."""
        path = self._path(workflow_id)
        try:
            return path.with_name(f"{path.name}{SIG}").read_text(encoding="utf-8")
        except OSError:
            return None

    def delete(self, workflow_id: str) -> None:
        path = self._path(workflow_id)
        if not path.is_file():
            raise NotFoundError("Esse fluxo não está mais no espaço.")
        path.unlink()
        path.with_name(f"{path.name}{SIG}").unlink(missing_ok=True)
