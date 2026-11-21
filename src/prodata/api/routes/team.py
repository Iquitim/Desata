"""Espaço da equipe (spec 047): espaços, identidade e fluxos do espaço. Camada fina sobre ``prodata.team``."""

from __future__ import annotations

import secrets
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Path, Response
from pydantic import BaseModel, Field

from prodata.api.deps import ServicesDep
from prodata.domain.workflow import ID_PATTERN, Workflow
from prodata.team.repository import SpaceFlow
from prodata.team.workspaces import SPACE_ID, Space

router = APIRouter(prefix="/api/equipe", tags=["equipe"])
SpaceId = Annotated[str, Path(pattern=SPACE_ID)]
WorkflowId = Annotated[str, Path(pattern=ID_PATTERN)]


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


@router.post("/espacos")
def add_space(req: SpaceRequest, services: ServicesDep) -> Space:
    workspaces = services.team.workspaces
    return workspaces.create(req.caminho, req.nome) if req.acao == "criar" else workspaces.join(req.caminho)


@router.delete("/espacos/{space_id}", status_code=204)
def leave_space(space_id: SpaceId, services: ServicesDep) -> Response:
    services.team.workspaces.leave(space_id)
    return Response(status_code=204)


@router.get("/espacos/{space_id}/fluxos")
def list_flows(space_id: SpaceId, services: ServicesDep) -> list[SpaceFlow]:
    return services.team.flows(space_id)


@router.get("/espacos/{space_id}/fluxos/{workflow_id}")
def get_flow(space_id: SpaceId, workflow_id: WorkflowId, services: ServicesDep) -> Workflow:
    workflow = services.team.get(space_id, workflow_id)
    services.trust.opened(workflow)  # mudado fora do programa: abre protegido, como os da biblioteca
    return workflow


@router.put("/espacos/{space_id}/fluxos/{workflow_id}")
def save_flow(
    space_id: SpaceId, workflow_id: WorkflowId, workflow: Workflow, services: ServicesDep
) -> Workflow:
    workflow = workflow.model_copy(update={"id": workflow_id})
    saved = services.team.save(space_id, services.runner.snapshot(workflow))
    services.trust.saved(saved)
    return saved


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
