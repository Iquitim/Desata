"""Banco Central do Brasil: séries do SGS e o catálogo do portal de dados abertos (spec 049).

Regras do órgão que ficam por conta do programa (RF-4943), conferidas na T01:
- desde 2025 o SGS exige período e aceita no máximo 10 anos por consulta (sem período: erro 406);
- janela sem nenhum valor responde 404 ("Value(s) not found"): é vazio, não erro;
- série que não existe responde 200 com uma página HTML;
- datas vêm como ``dd/mm/aaaa`` e valores como texto com ponto decimal.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timedelta
from typing import Any

import polars as pl

from prodata.catalog.http import CatalogClient, CatalogError
from prodata.catalog.model import ReadResult, SourceNotFoundError, add_years, to_number

DATA_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados"
CKAN_SEARCH = "https://dadosabertos.bcb.gov.br/api/3/action/package_search"
WINDOW_YEARS = 10
CATALOG_PAGE = 1000


def windows(start: date, end: date, years: int = WINDOW_YEARS) -> list[tuple[date, date]]:
    """Janelas seguidas, sem sobreposição, de no máximo ``years`` anos cada."""
    out: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        stop = min(add_years(cursor, years) - timedelta(days=1), end)
        out.append((cursor, stop))
        cursor = stop + timedelta(days=1)
    return out


def _br(day: date) -> str:
    return day.strftime("%d/%m/%Y")


def read_series(client: CatalogClient, code: int, start: date, end: date) -> ReadResult:
    rows: dict[date, float | None] = {}
    urls: list[str] = []
    for first, last in windows(start, end):
        url = DATA_URL.format(code=code)
        params = {"formato": "json", "dataInicial": _br(first), "dataFinal": _br(last)}
        answer = client.get(url, params=params, ok=frozenset({404}))
        urls.append(answer.url)
        if answer.status == 404:
            continue
        if not answer.body.lstrip().startswith(b"["):
            raise SourceNotFoundError(f"A série {code} não existe no SGS do Banco Central.")
        for item in answer.json():
            day = datetime.strptime(item["data"], "%d/%m/%Y").date()
            rows[day] = to_number(item.get("valor"))
    days = sorted(rows)
    frame = pl.DataFrame(
        {"data": days, "valor": [rows[d] for d in days]}, schema={"data": pl.Date, "valor": pl.Float64}
    )
    return ReadResult(frame, urls)


# ------------------------------------------------------------------ catálogo e metadados


def _text(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text in ("None", "null") else text


def _description(notes: Any) -> str:
    """Tira o aviso técnico entre ``---`` do começo (a regra dos 10 anos, que o programa já cuida)."""
    text = _text(notes).replace("\r\n", "\n")
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            text = text[end + 3 :]
    return text.strip()


def _entry(p: dict[str, Any]) -> dict[str, Any]:
    org = p.get("organization") or {}
    return {
        "codigo": _text(p.get("codigo_sgs")),
        "nome": _text(p.get("title")),
        "descricao": _description(p.get("notes")),
        "periodicidade": _text(p.get("periodicidade")),
        "unidade": _text(p.get("unidade_medida")),
        "inicio": _text(p.get("inicio_periodo")),
        "fim": _text(p.get("fim_periodo")),
        "atualizado": p.get("metadata_modified") or "",
        "licenca": p.get("license_title") or "",
        "area": org.get("title") or "",
        "id": p.get("name") or "",
    }


def meta(client: CatalogClient, code: int) -> dict[str, Any]:
    answer = client.get(CKAN_SEARCH, params={"q": f"codigo_sgs:{code}", "rows": 5})
    for p in answer.json().get("result", {}).get("results", []):
        if str(p.get("codigo_sgs") or "").strip() == str(code):
            return _entry(p)
    raise SourceNotFoundError(f"A série {code} não está no catálogo do Banco Central.")


def catalog(client: CatalogClient) -> Iterator[dict[str, Any]]:
    """Todas as séries do SGS publicadas no portal de dados abertos, página a página."""
    start = 0
    while True:
        params = {"fq": "codigo_sgs:[* TO *]", "rows": CATALOG_PAGE, "start": start, "sort": "name asc"}
        result = client.get(CKAN_SEARCH, params=params, timeout=60).json().get("result", {})
        page = result.get("results", [])
        for p in page:
            entry = _entry(p)
            if entry["codigo"].isdigit():
                yield entry
        start += len(page)
        if not page or start >= int(result.get("count", 0)):
            return


__all__ = ["CatalogError", "catalog", "meta", "read_series", "windows"]
