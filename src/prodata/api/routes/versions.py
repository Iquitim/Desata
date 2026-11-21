"""Versões anteriores de um fluxo (spec 046, RF-4631..4634).

``arquivo`` (ou ``path``) é o caminho de um fluxo salvo numa pasta: cada arquivo tem o seu histórico. O caminho só
serve para achar o histórico (entra numa impressão SHA-256); nunca é aberto nem gravado.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query
from pydantic import BaseModel, Field

from prodata.api.deps import ServicesDep
from prodata.domain.workflow import ID_PATTERN, Workflow
from prodata.services.versions import Origin, VersionInfo

router = APIRouter(prefix="/api/workflows/{workflow_id}/versions", tags=["versões"])
WorkflowId = Annotated[str, Path(pattern=ID_PATTERN)]
VersionId = Annotated[str, Path(pattern=r"^\d{8}-\d{6}-\d{6}-(manual|auto|restore|columns)$")]
FilePath = Annotated[str | None, Query(max_length=1024)]


class CompareRequest(BaseModel):
    current: Workflow | None = None
    path: str | None = Field(None, max_length=1024)


class RecordRequest(BaseModel):
    workflow: Workflow
    origin: Origin
    path: str | None = Field(None, max_length=1024)


@router.get("")
def list_versions(
    workflow_id: WorkflowId, services: ServicesDep, arquivo: FilePath = None
) -> list[VersionInfo]:
    return services.versions.history(workflow_id, path=arquivo)


@router.post("/compare")
def compare_versions(
    workflow_id: WorkflowId, req: CompareRequest, services: ServicesDep
) -> list[VersionInfo]:
    """As versões com o resumo do que mudou até o fluxo de agora (o que está aberto na tela)."""
    return services.versions.history(workflow_id, req.current, path=req.path)


@router.get("/{version_id}")
def get_version(
    workflow_id: WorkflowId, version_id: VersionId, services: ServicesDep, arquivo: FilePath = None
) -> Workflow:
    return services.versions.get(workflow_id, version_id, path=arquivo)


@router.post("")
def record_version(workflow_id: WorkflowId, req: RecordRequest, services: ServicesDep) -> VersionInfo | None:
    """Guarda o fluxo como está, antes de restaurar outra versão ou de trocar colunas em todas as caixas."""
    workflow = req.workflow.model_copy(update={"id": workflow_id})
    if services.trust.is_blocked(workflow_id):
        return None
    return services.versions.record(workflow, req.origin, path=req.path)
