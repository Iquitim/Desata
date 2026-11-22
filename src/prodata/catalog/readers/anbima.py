"""ANBIMA (spec 049, RF-4944): a planilha oficial de feriados nacionais do mercado financeiro (2001 a 2099).

Conferido na T01: ``.xls`` com as colunas Data, Dia da Semana e Feriado, e linhas vazias e notas no fim; lida pelo
``fastexcel``, que o programa já usa.
"""

from __future__ import annotations

import fastexcel
import polars as pl

from prodata.catalog.http import CatalogClient, CatalogError
from prodata.catalog.model import ReadResult

URL = "https://www.anbima.com.br/feriados/arqs/feriados_nacionais.xls"


def parse(body: bytes) -> pl.DataFrame:
    try:
        raw = fastexcel.read_excel(body).load_sheet(0).to_polars()
    except Exception as exc:
        raise CatalogError(
            f"A planilha de feriados da ANBIMA não pôde ser lida ({type(exc).__name__}).", "resposta"
        ) from None
    if raw.width < 3 or not raw.schema[raw.columns[0]].is_temporal():
        raise CatalogError(
            "A ANBIMA mudou a planilha de feriados: a primeira coluna não é de datas.", "resposta"
        )
    frame = raw.select(
        pl.col(raw.columns[0]).cast(pl.Date).alias("data"),
        pl.col(raw.columns[2]).cast(pl.String).str.strip_chars().alias("feriado"),
    ).drop_nulls("data")
    return frame.unique("data", keep="first").sort("data")


def read(client: CatalogClient) -> ReadResult:
    answer = client.get(URL, timeout=60, max_bytes=8 * 1024 * 1024)
    return ReadResult(parse(answer.body), [answer.url])
