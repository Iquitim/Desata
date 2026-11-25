"""Catálogo de dados públicos do Brasil (spec 049): visão geral, busca, atualização e favoritos."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from prodata.api.deps import ServicesDep
from prodata.catalog.download import DownloadError
from prodata.catalog.http import CatalogError
from prodata.catalog.model import SourceNotFoundError
from prodata.catalog.readers.files import FormatChangedError
from prodata.errors import InvalidInputError, NotFoundError
from prodata.nodes.public_data import PublicSelection

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


# ---------------------------------------------------------------- situação dos órgãos (RF-4921..4924)


@router.get("/situacao")
def health_state(services: ServicesDep) -> dict[str, Any]:
    """A última conferência de cada serviço, sem conferir de novo."""
    return services.catalog.health_state()


class HealthRequest(BaseModel):
    forcar: bool = False
    servicos: list[str] | None = Field(None, max_length=60)


@router.post("/situacao")
def check_health(req: HealthRequest, services: ServicesDep) -> dict[str, Any]:
    """Confere os órgãos em paralelo (até 5 s): ao abrir o catálogo e em Conferir de novo (``forcar``)."""
    return services.catalog.check_health(req.forcar, req.servicos)


# ---------------------------------------------------------------- feriados editáveis (RF-4945..4947)

Place = Query("BR", max_length=7, pattern=r"^(BR|[A-Z]{2}|\d{7})$")


@router.get("/feriados/editar")
def holidays_view(
    services: ServicesDep, local: str = Place, ano: int = Query(..., ge=1900, le=2100)
) -> dict[str, Any]:
    return _guard(lambda: services.catalog.holidays_view(local, ano))


class HolidayIn(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    abrangencia: str = Field(pattern=r"^(BR|[A-Z]{2}|\d{7})$")
    tipo: Literal["municipal", "estadual", "nacional", "ponto_facultativo", "meu"] = "meu"
    fixo: str | None = Field(None, pattern=r"^\d{2}-\d{2}$")
    pascoa: int | None = Field(None, ge=-100, le=100)
    unico: str | None = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    ajuste: Literal["domingo_seguinte"] | None = None
    desde: int | None = Field(None, ge=1900, le=2100)
    lei: str = Field("", max_length=200)
    nota: str = Field("", max_length=500)


class HolidayChange(BaseModel):
    id: str = Field(min_length=3, max_length=120)
    campos: dict[str, Any] = Field(default_factory=dict)
    desde: int | None = Field(None, ge=1900, le=2100)


def _holiday_action(
    services: ServicesDep, action: Callable[[], None], local: str, ano: int
) -> dict[str, Any]:
    try:
        _guard(action)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    return services.catalog.holidays_view(local, ano)


@router.post("/feriados/incluir")
def holiday_include(
    req: HolidayIn, services: ServicesDep, local: str = Place, ano: int = Query(2026)
) -> dict[str, Any]:
    return _holiday_action(
        services, lambda: services.catalog.holiday_include(req.model_dump(exclude_none=True)), local, ano
    )


@router.post("/feriados/corrigir")
def holiday_correct(
    req: HolidayChange, services: ServicesDep, local: str = Place, ano: int = Query(2026)
) -> dict[str, Any]:
    return _holiday_action(services, lambda: services.catalog.holiday_correct(req.id, req.campos), local, ano)


@router.post("/feriados/nao-vale-mais")
def holiday_stop(
    req: HolidayChange, services: ServicesDep, local: str = Place, ano: int = Query(2026)
) -> dict[str, Any]:
    return _holiday_action(
        services, lambda: services.catalog.holiday_stop(req.id, req.desde or ano), local, ano
    )


@router.post("/feriados/restaurar")
def holiday_restore(
    req: HolidayChange, services: ServicesDep, local: str = Place, ano: int = Query(2026)
) -> dict[str, Any]:
    return _holiday_action(services, lambda: services.catalog.holiday_restore(req.id), local, ano)


@router.post("/feriados/manter-o-meu")
def holiday_keep(
    req: HolidayChange, services: ServicesDep, local: str = Place, ano: int = Query(2026)
) -> dict[str, Any]:
    return _holiday_action(services, lambda: services.catalog.holiday_keep_mine(req.id), local, ano)


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


# ---------------------------------------------------------------- vista Dados e Dados novos (RF-4915, RF-4935)


@router.get("/salvas")
def saved_list(services: ServicesDep) -> dict[str, Any]:
    """As fontes guardadas na vista Dados, com a última leitura e o aviso Dados novos (sem acessar a rede)."""
    return {"fontes": services.catalog.saved_list()}


class SavedIn(BaseModel):
    fonte: PublicSelection


@router.post("/salvas")
def saved_add(req: SavedIn, services: ServicesDep) -> dict[str, Any]:
    return _guard(lambda: services.catalog.saved_add(req.fonte.model_dump()))


@router.put("/salvas/{key}")
def saved_update(key: str, req: SavedIn, services: ServicesDep) -> dict[str, Any]:
    _check_key(key)
    return _guard(lambda: services.catalog.saved_update(key, req.fonte.model_dump()))


@router.delete("/salvas/{key}")
def saved_delete(key: str, services: ServicesDep) -> dict[str, Any]:
    _check_key(key)
    services.catalog.saved_delete(key)
    return {"ok": True}


def _check_key(key: str) -> None:
    if not (1 <= len(key) <= 40 and key.isalnum()):
        raise HTTPException(400, "Fonte guardada inválida.")


class NewsItem(BaseModel):
    id: str = Field(min_length=3, max_length=300)
    escolhas: dict[str, Any] = Field(default_factory=dict)


class NewsRequest(BaseModel):
    fontes: list[NewsItem] = Field(default_factory=list, max_length=200)


@router.post("/novidades")
def news_state(req: NewsRequest, services: ServicesDep) -> dict[str, Any]:
    """Dados novos das caixas e das fontes guardadas: compara o que o órgão informou com a leitura guardada (sem rede)."""
    return {"novidades": services.catalog.news_state([i.model_dump() for i in req.fontes])}


class NewsCheckRequest(BaseModel):
    ids: list[str] = Field(default_factory=list, max_length=60)


@router.post("/novidades/conferir")
def news_check(req: NewsCheckRequest, services: ServicesDep) -> dict[str, Any]:
    """Pergunta aos órgãos a última atualização junto com a situação, ao abrir o catálogo (RF-4921; a cada 6 horas por fonte)."""
    _guard(lambda: services.catalog.news_check(req.ids))
    return {"ok": True}


# ---------------------------------------------------------------- CNPJ: downloads grandes (RF-4951..4953)


def _download(action: Callable[[], Any]) -> Any:
    try:
        return _guard(action)
    except DownloadError as exc:
        raise HTTPException(422, str(exc)) from None


@router.get("/cnpj")
def cnpj(services: ServicesDep, mes: str | None = Query(None, pattern=r"^\d{4}-\d{2}$")) -> dict[str, Any]:
    """O mês publicado pela Receita (o mais recente, ou o pedido), as partes com o tamanho e os downloads daqui."""
    return _download(lambda: services.catalog.cnpj(mes))


class CnpjListRequest(BaseModel):
    texto: str = Field("", max_length=200_000)


@router.post("/cnpj/ler")
def cnpj_list(req: CnpjListRequest) -> dict[str, Any]:
    """A lista de CNPJs colada, convertida para o formato da Receita, com como cada linha foi entendida (RF-4957)."""
    from prodata.catalog import cnpj as cnpj_layout

    return cnpj_layout.read_cnpj_list(req.texto)


@router.get("/cnpj/valores")
def cnpj_values(
    services: ServicesDep,
    fonte: str = Query(..., pattern=r"^[a-z0-9_-]{1,60}$"),
    tabela: Literal["municipios", "cnaes"] = "municipios",
    q: str = Query("", max_length=60),
) -> dict[str, Any]:
    """Municípios e CNAEs da tabela baixada junto (mesma pasta), para escolher no filtro sem decorar o código."""
    from prodata.catalog import cnpj as cnpj_layout

    try:
        source = services.datasets.folders.get(fonte)
    except NotFoundError as exc:
        raise HTTPException(404, str(exc)) from None
    return cnpj_layout.lookup_values(Path(source.folder), tabela, q)


class DownloadRequest(BaseModel):
    mes: str = Field(pattern=r"^\d{4}-\d{2}$")
    arquivos: list[str] = Field(min_length=1, max_length=60)
    pasta: str = Field(min_length=3, max_length=500)
    manter_zips: bool = False


@router.post("/downloads/plano")
def download_plan(req: DownloadRequest, services: ServicesDep) -> dict[str, Any]:
    """Antes de baixar: o tamanho das partes, o espaço livre na pasta escolhida e se basta."""
    return _download(
        lambda: services.catalog.downloads.plan(req.mes, req.arquivos, req.pasta, req.manter_zips)
    )


@router.post("/downloads")
def download_start(req: DownloadRequest, services: ServicesDep) -> dict[str, Any]:
    return _download(
        lambda: services.catalog.downloads.start(req.mes, req.arquivos, req.pasta, req.manter_zips)
    )


@router.get("/downloads")
def download_list(services: ServicesDep) -> dict[str, Any]:
    return services.catalog.downloads_state()


def _job_id(job_id: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{12}", job_id):
        raise HTTPException(400, "Download inválido.")
    return job_id


@router.get("/downloads/{job_id}")
def download_state(job_id: str, services: ServicesDep) -> dict[str, Any]:
    return _download(lambda: services.catalog.downloads.get(_job_id(job_id)))


@router.post("/downloads/{job_id}/{action}")
def download_action(
    job_id: str, action: Literal["pausar", "continuar", "cancelar"], services: ServicesDep
) -> dict[str, Any]:
    downloads = services.catalog.downloads
    run = {"pausar": downloads.pause, "continuar": downloads.resume, "cancelar": downloads.cancel}[action]
    return _download(lambda: run(_job_id(job_id)))
