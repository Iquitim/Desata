"""Trocar uma coluna que sumiu da fonte em todas as caixas que a usam (spec 046, RF-4603, RF-4604).

A tela manda o fluxo aberto e recebe o fluxo com a troca feita: a regra fica no motor (``schema_drift``).
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from prodata.domain.workflow import Workflow
from prodata.engine import schema_drift as drift
from prodata.errors import InvalidInputError
from prodata.nodes import REGISTRY

router = APIRouter(prefix="/api/schema", tags=["formato das fontes"])


class RenameRequest(BaseModel):
    workflow: Workflow
    source: str = Field(
        min_length=1, max_length=64
    )  # a entrada de onde a coluna sumiu; ou a caixa, com only_node
    old: str = Field(min_length=1, max_length=500)
    new: str = Field(min_length=1, max_length=500)
    only_node: bool = False  # erro de coluna numa caixa (RF-4622): troca só nela, em todas as entradas


class RenameResponse(BaseModel):
    workflow: Workflow
    changed: list[str]  # caixas que mudaram
    maybe: list[str]  # caixas SQL que citam a coluna no texto livre: a pessoa confere


class ImpactRequest(BaseModel):
    workflow: Workflow
    source: str = Field(min_length=1, max_length=64)
    columns: list[str] = Field(max_length=500)


@router.post("/impact")
def impact(req: ImpactRequest) -> dict[str, dict[str, list[str]]]:
    """Por coluna: as caixas que a usam e as SQL que talvez usem (para acender no canvas)."""
    found = drift.impact(req.workflow, req.source, req.columns)
    return {c: {"nodes": sorted(i.nodes), "maybe": sorted(i.maybe)} for c, i in found.items()}


@router.post("/rename")
def rename(req: RenameRequest) -> RenameResponse:
    if req.old == req.new:
        raise InvalidInputError("Escolha uma coluna diferente da que sumiu.")
    workflow = req.workflow.model_copy(deep=True)
    if not any(n.id == req.source for n in workflow.nodes):
        raise InvalidInputError("A entrada não está mais no fluxo.")
    if req.only_node:
        spec = REGISTRY.get(workflow.node(req.source).type)
        ports = {p.id for p in spec.inputs} if spec else set()
        found = drift.Impact(nodes={req.source: ports or {"in"}})
    else:
        found = drift.impact(workflow, req.source, [req.old])[req.old]
    changed: list[str] = []
    for node_id, ports in found.nodes.items():
        node = workflow.node(node_id)
        spec = REGISTRY.get(node.type)
        first = spec.inputs[0].id if spec and spec.inputs else None
        if drift.rename_column(node.config, node.type, ports, first, req.old, req.new):
            changed.append(node_id)
    return RenameResponse(workflow=workflow, changed=sorted(changed), maybe=sorted(found.maybe))
