"""Abertura protegida (spec 028, RF-2821..2826): a tela pergunta se o fluxo aberto está liberado e confirma."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from prodata.api.deps import Services, ServicesDep
from prodata.domain.workflow import Workflow
from prodata.services.portable import check_sources
from prodata.services.trust import summary

router = APIRouter(prefix="/api/trust", tags=["confiança"])


class TrustRequest(BaseModel):
    workflow: Workflow


def _names(services: Services) -> dict[str, str]:
    names = {f"sql:{q.id}": f"consulta {q.name}" for q in services.queries.list()}
    names |= {f"api:{a.id}": f"API {a.name}" for a in services.apis.list()}
    names |= {f"flow:{w.id}": f"fluxo {w.name}" for w in services.workflows.list()}
    names |= {f"folder:{s.id}": f"{s.pattern} em {s.folder}" for s in services.datasets.folders.list()}
    for p in services.datasets.pdfs.all_sources():
        where = p.path if p.mode == "arquivo" else f"{p.pattern} em {p.path}"
        names |= {
            f"pdf:{p.id}/{out}": f"PDF {p.name} ({where})" for out in services.datasets.pdfs.status(p).outputs
        }
    return names


def state(services: Services, workflow: Workflow) -> dict[str, Any]:
    protected = services.trust.is_blocked(workflow.id)
    if not protected:
        return {"protected": False, "summary": []}
    missing = {s["key"] for s in check_sources(workflow, services) if s["state"] != "ok"}
    return {
        "protected": True,
        "summary": summary(workflow, _names(services), missing),
        "reason": services.trust.reason(workflow.id),  # espaço da equipe: por que não confere (spec 047)
    }


@router.post("/state")
def trust_state(req: TrustRequest, services: ServicesDep) -> dict[str, Any]:
    """Se o fluxo está em modo protegido e, nesse caso, o que ele faz."""
    return state(services, req.workflow)


@router.post("/confirm")
def trust_confirm(req: TrustRequest, services: ServicesDep) -> dict[str, Any]:
    """A pessoa conferiu e confiou: o conteúdo de agora fica liberado neste computador."""
    services.trust.confirm(req.workflow)
    return state(services, req.workflow)
