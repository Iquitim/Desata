"""Tesouro Nacional (spec 049): preços e taxas do Tesouro Direto, pelo portal Tesouro Transparente (CKAN).

Conferido na T01: o conjunto tem um CSV único (~15 MB, todo o histórico), com ``;`` e vírgula decimal, datas
``dd/mm/aaaa``. O endereço do CSV é lido do próprio conjunto (``package_show``), não fixado: se o Tesouro trocar o
arquivo, o programa acompanha.
"""

from __future__ import annotations

import io
from datetime import date
from typing import Any

import polars as pl

from prodata.catalog.http import CatalogClient, CatalogError
from prodata.catalog.model import ReadResult

CKAN = "https://www.tesourotransparente.gov.br/ckan/api/3/action/package_show"
DIRETO_ID = "taxas-dos-titulos-ofertados-pelo-tesouro-direto"
COLUMNS = {
    "Tipo Titulo": "titulo",
    "Data Vencimento": "vencimento",
    "Data Base": "data",
    "Taxa Compra Manha": "taxa_compra",
    "Taxa Venda Manha": "taxa_venda",
    "PU Compra Manha": "pu_compra",
    "PU Venda Manha": "pu_venda",
    "PU Base Manha": "pu_base",
}


def package(client: CatalogClient, dataset: str = DIRETO_ID) -> dict[str, Any]:
    result: dict[str, Any] = client.get(CKAN, params={"id": dataset}).json().get("result", {})
    return result


def _csv_url(info: dict[str, Any]) -> str:
    for res in info.get("resources", []):
        url = str(res.get("url") or "")
        if url.lower().endswith(".csv"):
            return url
    raise CatalogError("O Tesouro não publicou o arquivo CSV do Tesouro Direto neste conjunto.", "resposta")


def meta(client: CatalogClient) -> dict[str, Any]:
    info = package(client)
    csv: dict[str, Any] = next(
        (r for r in info.get("resources", []) if str(r.get("url", "")).lower().endswith(".csv")), {}
    )
    return {
        "nome": info.get("title", ""),
        "descricao": info.get("notes", ""),
        "atualizado": csv.get("last_modified") or info.get("metadata_modified", ""),
        "licenca": info.get("license_title", ""),
        "tamanho": int(csv.get("size") or 0),
    }


def _decode(body: bytes) -> str:
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        return body.decode("latin-1")


def read_direto(client: CatalogClient, start: date | None = None, end: date | None = None) -> ReadResult:
    url = _csv_url(package(client))
    answer = client.get(url, timeout=120)
    raw = pl.read_csv(
        io.StringIO(_decode(answer.body)),
        separator=";",
        infer_schema=False,
    )
    missing = [c for c in COLUMNS if c not in raw.columns]
    if missing:
        raise CatalogError(
            f"O Tesouro mudou o arquivo do Tesouro Direto: faltam as colunas {', '.join(missing)}.",
            "resposta",
        )
    number = [c for src, c in COLUMNS.items() if src.startswith(("Taxa", "PU"))]
    frame = raw.select([pl.col(src).alias(dst) for src, dst in COLUMNS.items()]).with_columns(
        pl.col("data").str.strptime(pl.Date, "%d/%m/%Y", strict=False),
        pl.col("vencimento").str.strptime(pl.Date, "%d/%m/%Y", strict=False),
        *[
            pl.col(c).str.replace_all(r"\.", "").str.replace(",", ".").cast(pl.Float64, strict=False)
            for c in number
        ],
    )
    if start is not None:
        frame = frame.filter(pl.col("data") >= start)
    if end is not None:
        frame = frame.filter(pl.col("data") <= end)
    frame = frame.select("data", "titulo", "vencimento", *number).sort(["data", "titulo", "vencimento"])
    return ReadResult(frame, [answer.url])
