"""Recomendações de limpeza (spec 048, RF-4831..4835): o que a caixa entrega e como corrigir com uma caixa pronta."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from prodata.api.deps import ServicesDep
from prodata.domain.workflow import Node, Workflow
from prodata.engine.cleaning import recommend
from prodata.nodes import REGISTRY

router = APIRouter(prefix="/api/cleaning", tags=["limpeza"])


class RecommendRequest(BaseModel):
    workflow: Workflow
    node_id: str = Field(min_length=1, max_length=64)
    anchor: str = Field("out", max_length=16)


def _config(node: Node) -> dict[str, Any]:
    spec = REGISTRY.get(node.type)
    try:
        defaults = spec.config().model_dump(mode="json") if spec is not None else {}
    except ValueError:
        defaults = {}
    return {**defaults, **node.config}


def _fixes(rec: dict[str, Any], child: Node) -> bool:
    """A caixa logo depois já faz esta correção? (RF-4835: não sugere de novo.)"""
    fix = rec["correcao"]
    if child.type != fix["tool"] or child.disabled:
        return False
    cfg = _config(child)
    column = rec["coluna"]
    if child.type == "prep.unique":
        return not cfg.get("keys")
    if child.type == "prep.select":
        return any(f.get("name") == column and f.get("cast") for f in cfg.get("fields", []))
    covers = not cfg.get("columns") or column in cfg.get("columns", [])
    flag = {"espacos": cfg.get("trim_whitespace"), "caixa": cfg.get("case_mode", "none") != "none",
            "texto_vazio": cfg.get("empty_as_null")}.get(rec["tipo"], False)  # fmt: skip
    return bool(covers and flag)


@router.post("/recommend")
def recommendations(req: RecommendRequest, services: ServicesDep) -> dict[str, Any]:
    """As recomendações para a saída da caixa (do último resultado guardado). Sem resultado, ``disponivel: false``."""
    table = services.cache.table(req.workflow.id, req.node_id, req.anchor)
    if table is None:
        return {"disponivel": False, "recomendacoes": []}
    ignored = set(req.workflow.ignored_cleaning.get(req.node_id, []))
    children = [req.workflow.node(e.target) for e in req.workflow.edges
                if e.source == req.node_id and e.source_handle == req.anchor]  # fmt: skip
    found = [r for r in recommend(table, ignored) if not any(_fixes(r, c) for c in children)]
    return {"disponivel": True, "recomendacoes": found}
