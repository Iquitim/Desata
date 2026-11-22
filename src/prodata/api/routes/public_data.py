"""Catálogo de dados públicos do Brasil (spec 049): visão geral, busca, atualização e favoritos."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from prodata.api.deps import ServicesDep

router = APIRouter(prefix="/api/catalogo", tags=["dados públicos"])

Special = Literal["favoritos", "recentes", "destaques"]


@router.get("")
def overview(services: ServicesDep) -> dict[str, Any]:
    """Categorias, portais e órgãos com as contagens e a data da última leitura (sem acessar a rede)."""
    return services.catalog.overview()


@router.get("/busca")
def search(
    services: ServicesDep,
    q: str = Query("", max_length=200),
    orgao: str | None = Query(None, max_length=40),
    categoria: str | None = Query(None, max_length=40),
    periodicidade: str | None = Query(None, max_length=40),
    especial: Special | None = None,
    limite: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    rows = services.catalog.search(
        q, agency=orgao, category=categoria, periodicity=periodicidade, special=especial, limit=limite
    )
    return {"resultados": rows}


class RefreshRequest(BaseModel):
    orgaos: list[str] | None = Field(None, max_length=50)


@router.post("/atualizar")
def refresh(req: RefreshRequest, services: ServicesDep) -> dict[str, Any]:
    """Atualizar o catálogo (RF-4933): lê os catálogos dos órgãos, direto da fonte, em segundo plano."""
    return services.catalog.start_refresh(req.orgaos)


@router.get("/atualizar")
def refresh_status(services: ServicesDep) -> dict[str, Any]:
    return services.catalog.refresh_status()


@router.post("/favoritos/{source_id:path}")
def toggle_favorite(source_id: str, services: ServicesDep) -> dict[str, Any]:
    if not source_id or len(source_id) > 300:
        raise HTTPException(400, "Fonte inválida.")
    return {"favorita": services.catalog.prefs.toggle_favorite(source_id)}


@router.post("/recentes/{source_id:path}")
def add_recent(source_id: str, services: ServicesDep) -> dict[str, Any]:
    if not source_id or len(source_id) > 300:
        raise HTTPException(400, "Fonte inválida.")
    services.catalog.prefs.add_recent(source_id)
    return {"ok": True}
