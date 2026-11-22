"""Espaço da equipe (spec 047): espaços, identidade e fluxos do espaço. Camada fina sobre ``prodata.team``."""

from __future__ import annotations

import secrets
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Path, Query, Response
from pydantic import BaseModel, Field

from prodata.api.deps import Services, ServicesDep
from prodata.domain.workflow import ID_PATTERN, Workflow
from prodata.team.repository import SpaceFlow
from prodata.team.signing import Role
from prodata.team.versions import SpaceVersionInfo
from prodata.team.workspaces import SPACE_ID

router = APIRouter(prefix="/api/equipe", tags=["equipe"])
SpaceId = Annotated[str, Path(pattern=SPACE_ID)]
WorkflowId = Annotated[str, Path(pattern=ID_PATTERN)]
VersionId = Annotated[str, Path(pattern=r"^\d{8}-\d{6}-\d{6}-[a-z]+-[A-Za-z0-9._-]{1,64}$")]


class NameRequest(BaseModel):
    nome: str = Field(min_length=1, max_length=80)


class SpaceRequest(BaseModel):
    acao: Literal["criar", "entrar"]
    caminho: str = Field(min_length=1, max_length=1024)
    nome: str = Field("", max_length=80)


class MoveRequest(BaseModel):
    workflow_id: str = Field(pattern=ID_PATTERN)


@router.get("")
def overview(services: ServicesDep) -> dict[str, Any]:
    return services.team.overview()


@router.post("/identidade")
def set_name(req: NameRequest, services: ServicesDep) -> dict[str, Any]:
    me = services.team.identity.set_name(req.nome)
    return {"usuario": me.usuario, "nome": me.nome, "tem_nome": True}


class MembersRequest(BaseModel):
    acao: Literal["aceitar", "recusar", "papel", "remover"]
    usuario: str = Field(pattern=r"^[A-Za-z0-9._-]{1,64}$")
    papel: Role = "leitor"


@router.post("/espacos")
def add_space(req: SpaceRequest, services: ServicesDep) -> dict[str, Any]:
    team = services.team
    return team.create(req.caminho, req.nome) if req.acao == "criar" else team.join(req.caminho)


@router.get("/espacos/{space_id}/membros")
def list_members(space_id: SpaceId, services: ServicesDep) -> dict[str, Any]:
    return services.team.members_view(space_id)


@router.post("/espacos/{space_id}/membros")
def change_members(space_id: SpaceId, req: MembersRequest, services: ServicesDep) -> dict[str, Any]:
    return services.team.change_members(space_id, req.acao, req.usuario, req.papel)


@router.delete("/espacos/{space_id}", status_code=204)
def leave_space(space_id: SpaceId, services: ServicesDep) -> Response:
    services.team.workspaces.leave(space_id)
    return Response(status_code=204)


@router.get("/espacos/{space_id}/fluxos")
def list_flows(space_id: SpaceId, services: ServicesDep) -> list[SpaceFlow]:
    return services.team.flows(space_id)


def _open(space_id: str, workflow_id: str, services: Services) -> dict[str, Any]:
    workflow, reason = services.team.get(space_id, workflow_id)
    info = services.team.opened(space_id, workflow, reason)
    # a assinatura decide (RF-4715); com assinatura válida, só pede conferência do que mudou de sensível (RF-4741)
    services.trust.space_flow(
        workflow, reason or info["motivo"], space=space_id, only=info["conferir"] or None
    )
    return {"fluxo": workflow, **info}


@router.get("/espacos/{space_id}/fluxos/{workflow_id}")
def get_flow(space_id: SpaceId, workflow_id: WorkflowId, services: ServicesDep) -> Workflow:
    flow: Workflow = _open(space_id, workflow_id, services)["fluxo"]
    return flow


@router.get("/espacos/{space_id}/fluxos/{workflow_id}/abrir")
def open_flow(space_id: SpaceId, workflow_id: WorkflowId, services: ServicesDep) -> dict[str, Any]:
    """O fluxo e o que a tela mostra ao abrir: a base para o Salvar, quem salvou por último e "Atualizado por"."""
    return _open(space_id, workflow_id, services)


@router.put("/espacos/{space_id}/fluxos/{workflow_id}")
def save_flow(space_id: SpaceId, workflow_id: WorkflowId, workflow: Workflow, services: ServicesDep,
              base: Annotated[str | None, Query(pattern=r"^[0-9a-f]{64}$")] = None, forcar: bool = False,
              origem: Literal["manual", "auto", "restore"] = "manual") -> dict[str, Any]:  # fmt: skip
    """Grava no espaço. ``base``: a versão que estava aberta; se outra pessoa salvou depois dela, responde 409 e as duas
    versões ficam guardadas (RF-4761). ``adiado``: a sincronização segurou o arquivo e o envio ficou para depois."""
    workflow = workflow.model_copy(update={"id": workflow_id})
    res = services.team.save(
        space_id, services.runner.snapshot(workflow), base=base, force=forcar, origin=origem
    )
    services.trust.saved(res["fluxo"])
    return res


class SpaceVersionRequest(BaseModel):
    current: Workflow | None = None


class RecordRequest(BaseModel):
    workflow: Workflow
    origin: Literal["restore"] = "restore"


@router.post("/espacos/{space_id}/fluxos/{workflow_id}/versoes/comparar")
def list_versions(space_id: SpaceId, workflow_id: WorkflowId, req: SpaceVersionRequest,
                  services: ServicesDep) -> list[SpaceVersionInfo]:  # fmt: skip
    """Versões anteriores do fluxo do espaço, com o autor (RF-4731), comparadas com o que está aberto."""
    return services.team.history(space_id, workflow_id, req.current)


@router.get("/espacos/{space_id}/fluxos/{workflow_id}/versoes/{version_id}")
def get_version(
    space_id: SpaceId, workflow_id: WorkflowId, version_id: VersionId, services: ServicesDep
) -> Workflow:
    return services.team.version(space_id, workflow_id, version_id)


@router.post("/espacos/{space_id}/fluxos/{workflow_id}/versoes", status_code=204)
def record_version(
    space_id: SpaceId, workflow_id: WorkflowId, req: RecordRequest, services: ServicesDep
) -> Response:
    services.team.record_version(space_id, req.workflow.model_copy(update={"id": workflow_id}), req.origin)
    return Response(status_code=204)


@router.post("/espacos/{space_id}/mover")
def move_to_space(space_id: SpaceId, req: MoveRequest, services: ServicesDep) -> Workflow:
    saved = services.team.move_from_library(space_id, req.workflow_id)
    services.trust.saved(saved)
    return saved


@router.post("/espacos/{space_id}/fluxos/{workflow_id}/copia")
def copy_to_library(space_id: SpaceId, workflow_id: WorkflowId, services: ServicesDep) -> Workflow:
    copy = services.team.copy_to_library(space_id, workflow_id, f"wf_{secrets.token_hex(4)}")
    services.trust.saved(copy)
    return copy


class EditingRequest(BaseModel):
    acao: Literal["abrir", "renovar", "soltar", "estado"]
    forcar: bool = False


@router.post("/espacos/{space_id}/fluxos/{workflow_id}/edicao")
def editing(
    space_id: SpaceId, workflow_id: WorkflowId, req: EditingRequest, services: ServicesDep
) -> dict[str, Any]:
    """Quem está editando (spec 047, RF-4721..4723): abrir, renovar, soltar ou consultar a marca de edição."""
    return services.team.editing(space_id, workflow_id, req.acao, force=req.forcar)


@router.post("/espacos/{space_id}/fluxos/{workflow_id}/oficial")
def publish_official(
    space_id: SpaceId, workflow_id: WorkflowId, services: ServicesDep
) -> dict[str, Any] | None:
    """Publicar como oficial (RF-4751): a versão de trabalho, assinada por um Publicador. É o que os agendamentos rodam."""
    return services.team.publish(space_id, workflow_id)


@router.get("/espacos/{space_id}/agendamentos")
def team_schedules(space_id: SpaceId, services: ServicesDep) -> dict[str, Any]:
    """Os agendamentos dos fluxos do espaço, de todos os computadores (RF-4753)."""
    return services.team.team_schedules(space_id)
