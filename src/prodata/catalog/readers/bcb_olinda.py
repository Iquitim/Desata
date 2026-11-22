"""Banco Central do Brasil, serviços Olinda (OData): PTAX e expectativas do mercado (Focus) (spec 049).

O OData do Olinda recusa o espaço escrito como "+" (verificado na T01): o cliente do catálogo manda ``%20``.
As datas dos parâmetros da PTAX vão como ``'MM-DD-AAAA'``, entre aspas simples.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import polars as pl

from prodata.catalog.http import CatalogClient
from prodata.catalog.model import ReadResult, SourceNotFoundError

BASE = "https://olinda.bcb.gov.br/olinda/servico"
PTAX = (
    f"{BASE}/PTAX/versao/v1/odata/CotacaoMoedaPeriodo(moeda=@moeda,dataInicial=@dataInicial,"
    "dataFinalCotacao=@dataFinalCotacao)"
)
MOEDAS = f"{BASE}/PTAX/versao/v1/odata/Moedas"
FOCUS = f"{BASE}/Expectativas/versao/v1/odata/{{recurso}}"
FOCUS_RESOURCES = {
    "mensal": "ExpectativaMercadoMensais",
    "anual": "ExpectativasMercadoAnuais",
    "trimestral": "ExpectativasMercadoTrimestrais",
}
BOLETINS = ("Abertura", "Intermediário", "Fechamento")


def _us(day: date) -> str:
    return f"'{day:%m-%d-%Y}'"


def currencies(client: CatalogClient) -> list[dict[str, str]]:
    rows = client.get(MOEDAS, params={"$format": "json"}).json().get("value", [])
    return [
        {"simbolo": r["simbolo"], "nome": r["nomeFormatado"], "tipo": r.get("tipoMoeda", "")} for r in rows
    ]


def read_ptax(
    client: CatalogClient, moeda: str, start: date, end: date, *, boletim: str = "Fechamento"
) -> ReadResult:
    """Cotação de compra e venda por dia. Padrão: o boletim de fechamento, que é a PTAX do dia."""
    symbol = moeda.strip().upper()
    if not symbol.isalpha() or len(symbol) != 3:
        raise SourceNotFoundError(f"{moeda!r} não é um código de moeda (exemplos: USD, EUR).")
    params = {
        "@moeda": f"'{symbol}'",
        "@dataInicial": _us(start),
        "@dataFinalCotacao": _us(end),
        "$format": "json",
    }
    answer = client.get(PTAX, params=params, timeout=60)
    rows: list[dict[str, Any]] = answer.json().get("value", [])
    if boletim != "todos":
        rows = [r for r in rows if r.get("tipoBoletim") == boletim]
    stamps = [datetime.fromisoformat(r["dataHoraCotacao"][:19]) for r in rows]
    frame = pl.DataFrame(
        {
            "data": [s.date() for s in stamps],
            "moeda": [symbol] * len(rows),
            "cotacao_compra": [float(r["cotacaoCompra"]) for r in rows],
            "cotacao_venda": [float(r["cotacaoVenda"]) for r in rows],
            "paridade_compra": [float(r["paridadeCompra"]) for r in rows],
            "paridade_venda": [float(r["paridadeVenda"]) for r in rows],
            "boletim": [r.get("tipoBoletim", "") for r in rows],
            "data_hora": stamps,
        },
        schema={
            "data": pl.Date,
            "moeda": pl.String,
            "cotacao_compra": pl.Float64,
            "cotacao_venda": pl.Float64,
            "paridade_compra": pl.Float64,
            "paridade_venda": pl.Float64,
            "boletim": pl.String,
            "data_hora": pl.Datetime,
        },
    )
    frame = frame.sort("data_hora")
    if boletim != "todos":
        # O Banco Central às vezes republica o boletim do dia (corrigido): vale o último.
        frame = frame.unique(subset=["data"], keep="last", maintain_order=True)
    return ReadResult(frame, [answer.url])


def read_focus(
    client: CatalogClient, indicador: str, start: date, *, periodicidade: str = "mensal"
) -> ReadResult:
    """Expectativas do mercado (Focus) para um indicador, desde ``start`` (data da pesquisa)."""
    resource = FOCUS_RESOURCES.get(periodicidade)
    if resource is None:
        raise SourceNotFoundError(f"Periodicidade {periodicidade!r} não existe no Focus.")
    safe = indicador.replace("'", "''")
    params = {
        "$format": "json",
        "$filter": f"Indicador eq '{safe}' and Data ge '{start:%Y-%m-%d}'",
        "$orderby": "Data asc",
    }
    answer = client.get(FOCUS.format(recurso=resource), params=params, timeout=90)
    rows: list[dict[str, Any]] = answer.json().get("value", [])
    frame = pl.DataFrame(
        {
            "data": [date.fromisoformat(r["Data"]) for r in rows],
            "indicador": [r.get("Indicador", "") for r in rows],
            "referencia": [str(r.get("DataReferencia", "")) for r in rows],
            "media": [r.get("Media") for r in rows],
            "mediana": [r.get("Mediana") for r in rows],
            "desvio_padrao": [r.get("DesvioPadrao") for r in rows],
            "minimo": [r.get("Minimo") for r in rows],
            "maximo": [r.get("Maximo") for r in rows],
            "respondentes": [r.get("numeroRespondentes") for r in rows],
            "base_calculo": [r.get("baseCalculo") for r in rows],
        },
        schema={
            "data": pl.Date,
            "indicador": pl.String,
            "referencia": pl.String,
            "media": pl.Float64,
            "mediana": pl.Float64,
            "desvio_padrao": pl.Float64,
            "minimo": pl.Float64,
            "maximo": pl.Float64,
            "respondentes": pl.Int64,
            "base_calculo": pl.Int64,
        },
    )
    return ReadResult(frame, [answer.url])
