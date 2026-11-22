"""Ministério do Desenvolvimento, Indústria, Comércio e Serviços, Comex Stat (spec 049).

A consulta geral só existe por POST (decisão de 2026-11-22, RF-4981): o corpo é só a consulta (fluxo, período,
filtros, detalhes, métricas), montado aqui a partir de listas fechadas; nada da pessoa vai junto.
Conferido na T04: a UF tem código próprio do Comex Stat (SP = 41), lido de ``/tables/uf``; valores vêm como texto.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Literal

import polars as pl

from prodata.catalog.http import CatalogClient
from prodata.catalog.model import ReadResult, SourceNotFoundError, to_number

BASE = "https://api-comexstat.mdic.gov.br"
Flow = Literal["export", "import"]
DETAILS = {
    "country": "pais",
    "economicBlock": "bloco",
    "state": "uf",
    "via": "via",
    "urf": "urf",
    "ncm": "ncm",
    "subHeading": "sh6",
    "heading": "sh4",
    "chapter": "capitulo",
    "section": "secao",
}
METRICS = {
    "metricFOB": "valor_fob_usd",
    "metricKG": "peso_kg",
    "metricStatistic": "quantidade_estatistica",
    "metricFreight": "frete_usd",
    "metricInsurance": "seguro_usd",
    "metricCIF": "valor_cif_usd",
}
IMPORT_ONLY = {"metricFreight", "metricInsurance", "metricCIF"}
_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
# Códigos que acompanham o nome ("coNcm" junto de "ncm", "chapterCode" junto de "chapter").
_CODES = {"coNcm": "ncm_codigo", "chapterCode": "capitulo_codigo", "headingCode": "sh4_codigo",
          "subHeadingCode": "sh6_codigo", "sectionCode": "secao_codigo"}  # fmt: skip


def updated(client: CatalogClient) -> dict[str, str]:
    data = client.get(f"{BASE}/general/dates/updated").json().get("data", {})
    return {
        "atualizado": data.get("updated", ""),
        "ultimo_mes": f"{data.get('year', '')}-{data.get('monthNumber', '')}",
    }


def state_codes(client: CatalogClient) -> dict[str, int]:
    """Sigla da UF → código do Comex Stat (diferente do IBGE)."""
    rows = client.get(f"{BASE}/tables/uf", params={"language": "pt"}).json().get("data", [])
    return {r["uf"]: int(r["id"]) for r in rows if str(r.get("id", "")).isdigit()}


def read_general(
    client: CatalogClient,
    flow: Flow,
    start: str,
    end: str,
    *,
    details: list[str] | None = None,
    metrics: list[str] | None = None,
    states: list[str] | None = None,
    month_detail: bool = True,
) -> ReadResult:
    if flow not in ("export", "import"):
        raise SourceNotFoundError("O fluxo é exportação (export) ou importação (import).")
    if not (_MONTH.match(start) and _MONTH.match(end)) or start > end:
        raise SourceNotFoundError("O período do Comex Stat vai de um mês a outro, como 2025-01 a 2025-12.")
    chosen_details = details or []
    chosen_metrics = metrics or ["metricFOB", "metricKG"]
    bad = [d for d in chosen_details if d not in DETAILS] + [m for m in chosen_metrics if m not in METRICS]
    if bad:
        raise SourceNotFoundError(f"O Comex Stat não tem {', '.join(bad)}.")
    if flow == "export" and IMPORT_ONLY & set(chosen_metrics):
        raise SourceNotFoundError("Frete, seguro e valor CIF só existem na importação.")
    query: dict[str, Any] = {
        "flow": flow,
        "monthDetail": month_detail,
        "period": {"from": start, "to": end},
        "details": chosen_details,
        "metrics": chosen_metrics,
    }
    if states:
        codes = state_codes(client)
        unknown = [s for s in states if s.upper() not in codes]
        if unknown:
            raise SourceNotFoundError(f"UF desconhecida no Comex Stat: {', '.join(unknown)}.")
        query["filters"] = [{"filter": "state", "values": [codes[s.upper()] for s in states]}]
    answer = client.post_query(f"{BASE}/general?language=pt", query, timeout=120)
    rows: list[dict[str, Any]] = answer.json().get("data", {}).get("list", [])
    return ReadResult(
        _frame(rows, chosen_details, chosen_metrics, month_detail), [answer.url], info={"fluxo": flow}
    )


def _frame(
    rows: list[dict[str, Any]], details: list[str], metrics: list[str], month_detail: bool
) -> pl.DataFrame:
    cols: dict[str, list[Any]] = {"ano": [int(r["year"]) for r in rows]}
    schema: dict[str, Any] = {"ano": pl.Int64}
    if month_detail:
        cols["mes"] = [int(r.get("monthNumber") or 1) for r in rows]
        cols["data"] = [date(int(r["year"]), int(r.get("monthNumber") or 1), 1) for r in rows]
        schema |= {"mes": pl.Int64, "data": pl.Date}
    code_keys = [k for k in _CODES if rows and k in rows[0]]
    for key in code_keys:
        cols[_CODES[key]] = [str(r.get(key) or "") for r in rows]
        schema[_CODES[key]] = pl.String
    for d in details:
        cols[DETAILS[d]] = [r.get(d) for r in rows]
        schema[DETAILS[d]] = pl.String
    for m in metrics:
        cols[METRICS[m]] = [to_number(r.get(m)) for r in rows]
        schema[METRICS[m]] = pl.Float64
    frame = pl.DataFrame(cols, schema=schema)
    order = ["ano", "mes"] if month_detail else ["ano"]
    return frame.sort(order)
