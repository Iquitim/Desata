"""Ipeadata (Ipea), API OData 4 (spec 049): catálogo de séries e valores.

Conferido na T01: por HTTPS, ``Metadados`` traz ~4.100 séries com fonte, periodicidade, unidade e última atualização;
código inexistente responde 200 com lista vazia (não é erro HTTP); datas vêm com fuso (``1974-01-01T00:00:00-02:00``).
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

import polars as pl

from prodata.catalog.http import CatalogClient
from prodata.catalog.model import ReadResult, SourceNotFoundError

BASE = "https://www.ipeadata.gov.br/api/odata4"
_CODE = re.compile(r"^[A-Za-z0-9_]{1,40}$")


def _check(code: str) -> str:
    if not _CODE.match(code):
        raise SourceNotFoundError(f"{code!r} não é um código de série do Ipeadata.")
    return code


def _entry(m: dict[str, Any]) -> dict[str, Any]:
    return {
        "codigo": m.get("SERCODIGO", ""),
        "nome": (m.get("SERNOME") or "").strip(),
        "descricao": (m.get("SERCOMENTARIO") or "").strip(),
        "atualizado": m.get("SERATUALIZACAO") or "",
        "base": m.get("BASNOME") or "",
        "fonte": m.get("FNTNOME") or "",
        "fonte_sigla": m.get("FNTSIGLA") or "",
        "fonte_url": m.get("FNTURL") or "",
        "periodicidade": m.get("PERNOME") or "",
        "unidade": m.get("UNINOME") or "",
        "multiplicador": m.get("MULNOME") or "",
        "ativa": m.get("SERSTATUS") == "A",
        "numerica": bool(m.get("SERNUMERICA", True)),
        "tema": m.get("TEMCODIGO"),
        "pais": m.get("PAICODIGO") or "",
    }


def catalog(client: CatalogClient) -> list[dict[str, Any]]:
    rows = client.get(f"{BASE}/Metadados", timeout=90).json().get("value", [])
    return [_entry(m) for m in rows if m.get("SERCODIGO")]


def meta(client: CatalogClient, code: str) -> dict[str, Any]:
    rows = client.get(f"{BASE}/Metadados('{_check(code)}')").json().get("value", [])
    if not rows:
        raise SourceNotFoundError(f"A série {code} não existe no Ipeadata.")
    return _entry(rows[0])


def read_series(
    client: CatalogClient, code: str, start: date | None = None, end: date | None = None
) -> ReadResult:
    answer = client.get(f"{BASE}/ValoresSerie(SERCODIGO='{_check(code)}')", timeout=90)
    rows: list[dict[str, Any]] = answer.json().get("value", [])
    if not rows:
        raise SourceNotFoundError(f"A série {code} não existe no Ipeadata ou não tem valores.")
    frame = pl.DataFrame(
        {
            "data": [date.fromisoformat(r["VALDATA"][:10]) for r in rows],
            "valor": [r.get("VALVALOR") for r in rows],
            "nivel": [r.get("NIVNOME") or "" for r in rows],
            "territorio": [r.get("TERCODIGO") or "" for r in rows],
        },
        schema={"data": pl.Date, "valor": pl.Float64, "nivel": pl.String, "territorio": pl.String},
    )
    if start is not None:
        frame = frame.filter(pl.col("data") >= start)
    if end is not None:
        frame = frame.filter(pl.col("data") <= end)
    if frame["nivel"].eq("").all():
        frame = frame.drop("nivel", "territorio")
    return ReadResult(frame.sort("data"), [answer.url])
