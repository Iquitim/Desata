"""Tesouro Nacional, Siconfi (spec 049): relatórios fiscais de estados e municípios (DCA, RREO, RGF).

Conferido na T04 com São Paulo (3550308): parâmetros ``an_exercicio``, ``id_ente``, ``nr_periodo``,
``co_tipo_demonstrativo``, ``no_anexo``, ``in_periodicidade``, ``co_poder``; paginação Oracle ORDS (``items``,
``hasMore``, ``limit`` de 5.000, ``offset``). Os valores já vêm como número.
"""

from __future__ import annotations

from typing import Any, Literal

import polars as pl

from prodata.catalog.http import CatalogClient
from prodata.catalog.model import ReadResult, SourceNotFoundError

BASE = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt"
Report = Literal["dca", "rreo", "rgf"]
MAX_PAGES = 200
_TEXT = ("instituicao", "uf", "anexo", "rotulo", "coluna", "cod_conta", "conta", "demonstrativo", "periodicidade",
         "esfera", "co_poder")  # fmt: skip


def entities(client: CatalogClient) -> ReadResult:
    """Estados, municípios e a União, com código do IBGE, UF, esfera, população e CNPJ."""
    rows, urls = _pages(client, f"{BASE}/entes", {})
    frame = pl.DataFrame(
        {
            "codigo": [str(r["cod_ibge"]) for r in rows],
            "ente": [r.get("ente") for r in rows],
            "uf": [r.get("uf") for r in rows],
            "regiao": [r.get("regiao") for r in rows],
            "esfera": [r.get("esfera") for r in rows],
            "capital": [str(r.get("capital") or "").strip() == "1" for r in rows],
            "populacao": [r.get("populacao") for r in rows],
            "cnpj": [r.get("cnpj") for r in rows],
            "exercicio": [r.get("exercicio") for r in rows],
        },
        schema_overrides={"populacao": pl.Int64, "exercicio": pl.Int64},
    ).sort("codigo")
    return ReadResult(frame, urls)


def _pages(client: CatalogClient, url: str, params: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    urls: list[str] = []
    offset = 0
    for _ in range(MAX_PAGES):
        answer = client.get(url, params={**params, "offset": offset}, timeout=120)
        urls.append(answer.url)
        data = answer.json()
        items = data.get("items", [])
        rows.extend(items)
        if not data.get("hasMore") or not items:
            return rows, urls
        offset += len(items)
    return rows, urls


def read_report(
    client: CatalogClient,
    report: Report,
    exercicio: int,
    ente: str,
    *,
    periodo: int | None = None,
    anexo: str | None = None,
    poder: str | None = None,
    periodicidade: str | None = None,
) -> ReadResult:
    if report not in ("dca", "rreo", "rgf"):
        raise SourceNotFoundError(f"Relatório {report!r} não existe no Siconfi.")
    if not ente.isdigit() or len(ente) not in (1, 2, 7):
        raise SourceNotFoundError(
            f"{ente!r} não é um código de ente do IBGE (UF com 2 dígitos ou município com 7)."
        )
    params: dict[str, Any] = {"an_exercicio": exercicio, "id_ente": ente}
    if report in ("rreo", "rgf"):
        params["co_tipo_demonstrativo"] = report.upper()
        params["nr_periodo"] = periodo or (6 if report == "rreo" else 3)
    if report == "rgf":
        params["in_periodicidade"] = periodicidade or "Q"
        params["co_poder"] = poder or "E"
    if anexo:
        params["no_anexo"] = anexo
    rows, urls = _pages(client, f"{BASE}/{report}", params)
    if not rows:
        frame = pl.DataFrame(schema={"exercicio": pl.Int64, "conta": pl.String, "valor": pl.Float64})
        return ReadResult(
            frame, urls, ["O Siconfi não tem esse relatório para o ente e o período escolhidos."]
        )
    columns = list(rows[0].keys())
    frame = pl.DataFrame(
        {c: [r.get(c) for r in rows] for c in columns},
        schema_overrides={
            "valor": pl.Float64,
            "cod_ibge": pl.String,
            **{c: pl.String for c in _TEXT if c in columns},
        },
        strict=False,
    )
    if "cod_ibge" in frame.columns:
        frame = frame.rename({"cod_ibge": "codigo"})
    return ReadResult(frame, urls)
