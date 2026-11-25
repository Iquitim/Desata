"""Catálogo de dados públicos do Brasil (spec 049): visão geral, busca, atualização e favoritos."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from prodata.api.deps import ServicesDep
from prodata.catalog.http import CatalogError
from prodata.catalog.model import SourceNotFoundError
from prodata.catalog.readers.files import FormatChangedError
from prodata.errors import InvalidInputError

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


def _guard(action: Callable[[], Any]) -> Any:
    """Erros do órgão e da fonte chegam à tela com o motivo em palavras (princípio V)."""
    try:
        return action()
    except SourceNotFoundError as exc:
        raise HTTPException(404, str(exc)) from None
    except FormatChangedError as exc:
        raise HTTPException(409, str(exc)) from None
    except CatalogError as exc:
        status = 403 if exc.kind == "recusado" else 413 if exc.kind == "limite" else 502
        raise HTTPException(status, exc.message) from None
    except InvalidInputError as exc:
        raise HTTPException(422, str(exc)) from None


@router.get("/fonte")
def describe(services: ServicesDep, id: str = Query(..., max_length=300)) -> dict[str, Any]:
    """O detalhe da fonte (RF-4911): o que o programa sabe e o que o órgão informa na hora."""
    return _guard(lambda: services.catalog.describe(id))


class PreviewRequest(BaseModel):
    id: str = Field(min_length=3, max_length=300)
    escolhas: dict[str, Any] = Field(default_factory=dict)


@router.post("/previa")
def preview(req: PreviewRequest, services: ServicesDep) -> dict[str, Any]:
    """As últimas linhas lidas na hora, com as escolhas (RF-4913): a mesma leitura do fluxo."""
    return _guard(lambda: services.catalog.preview(req.id, req.escolhas))


class FilePreviewRequest(BaseModel):
    id: str = Field(min_length=3, max_length=300)
    arquivo: str = Field(min_length=1, max_length=100)
    opcoes: dict[str, Any] = Field(default_factory=dict)
    membro: str = Field("", max_length=500)


@router.post("/arquivo/previa")
def file_preview(req: FilePreviewRequest, services: ServicesDep) -> dict[str, Any]:
    """A prévia obrigatória do arquivo de um portal (RF-4938)."""
    return _guard(lambda: services.catalog.file_preview(req.id, req.arquivo, req.opcoes, req.membro))


@router.get("/odata")
def odata_entries(services: ServicesDep, id: str = Query(..., max_length=300),
                  arquivo: str = Query(..., max_length=100)) -> dict[str, Any]:  # fmt: skip
    """As consultas e os parâmetros (conferidos ou não) do serviço OData de um conjunto do Banco Central (RF-4937)."""
    return _guard(lambda: services.catalog.odata(id, arquivo))


@router.get("/moedas")
def currencies(services: ServicesDep) -> dict[str, Any]:
    return {"moedas": _guard(services.catalog.currencies)}


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
