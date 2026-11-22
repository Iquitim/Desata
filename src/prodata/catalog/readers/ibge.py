"""IBGE: tabelas da API de agregados v3 e localidades v1 (spec 049).

Regras do órgão que ficam por conta do programa (RF-4943), conferidas na T01:
- consulta grande demais (todos os municípios de muitos anos) responde 500: municípios são lidos por UF
  (``N6[N3[33]]``) e juntados;
- valores vêm como texto; "-", "..", "...", "X" são "sem dado" e viram vazio, com a contagem no aviso;
- o código do período depende da periodicidade: mensal ``AAAAMM``, trimestral ``AAAA0T`` (trimestre), anual ``AAAA``;
- o nome do município vem com a UF ("Campinas (SP)", "Acrelândia - AC"): o código de 7 dígitos é a chave.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

import polars as pl

from prodata.catalog.http import CatalogClient, CatalogError
from prodata.catalog.model import ReadResult, SourceNotFoundError, count_missing, to_number

API = "https://servicodados.ibge.gov.br/api"
AGREGADOS = f"{API}/v3/agregados"
LEVELS = {"N1": "Brasil", "N2": "Grande Região", "N3": "Unidade da Federação", "N6": "Município"}
UF_CODES = (
    11,
    12,
    13,
    14,
    15,
    16,
    17,
    21,
    22,
    23,
    24,
    25,
    26,
    27,
    28,
    29,
    31,
    32,
    33,
    35,
    41,
    42,
    43,
    50,
    51,
    52,
    53,
)
_PERIOD = re.compile(r"^(?:-\d{1,3}|\d{4,6}(?:-\d{4,6})?(?:,\d{4,6})*|all)$")


def catalog(client: CatalogClient) -> list[dict[str, Any]]:
    """Todas as tabelas, com a pesquisa a que pertencem."""
    out: list[dict[str, Any]] = []
    for survey in client.get(AGREGADOS, timeout=60).json():
        for table in survey.get("agregados", []):
            out.append(
                {"codigo": str(table["id"]), "nome": table["nome"], "pesquisa": survey.get("nome", "")}
            )
    return out


def meta(client: CatalogClient, table: int) -> dict[str, Any]:
    answer = client.get(f"{AGREGADOS}/{table}/metadados", ok=frozenset({404, 500}))
    data = answer.json() if answer.status == 200 else None
    if not isinstance(data, dict) or "id" not in data:
        raise SourceNotFoundError(f"A tabela {table} não existe na API de agregados do IBGE.")
    return data


def periods(client: CatalogClient, table: int) -> list[dict[str, Any]]:
    return list(client.get(f"{AGREGADOS}/{table}/periodos").json())


def period_date(code: str, frequency: str) -> date | None:
    """O primeiro dia do período: mensal 202610 → 01/10/2026; trimestral 202603 → 01/07/2026; anual 2026 → 01/01."""
    text = code.strip()
    if not text.isdigit():
        return None
    year = int(text[:4])
    if len(text) == 4:
        return date(year, 1, 1)
    part = int(text[4:])
    if frequency.startswith("trimestral") and "móvel" not in frequency and 1 <= part <= 4:
        return date(year, 3 * (part - 1) + 1, 1)
    if 1 <= part <= 12:
        return date(year, part, 1)
    return None


def _localities(level: str, places: str) -> list[str]:
    """Os pedidos de localidade: municípios de todo o Brasil viram um pedido por UF."""
    if level not in LEVELS:
        raise SourceNotFoundError(f"Nível territorial {level!r} não é usado pelo catálogo.")
    if places == "all" and level == "N6":
        return [f"N6[N3[{uf}]]" for uf in UF_CODES]
    if places != "all" and not re.fullmatch(r"\d{1,7}(,\d{1,7})*", places):
        raise SourceNotFoundError(f"Localidades {places!r} inválidas.")
    return [f"{level}[{places}]"]


def read_table(
    client: CatalogClient,
    table: int,
    variable: int,
    *,
    period: str = "-60",
    level: str = "N1",
    places: str = "all",
    classification: str | None = None,
    frequency: str | None = None,
) -> ReadResult:
    """Uma variável de uma tabela, em formato longo: uma linha por localidade e período."""
    if not _PERIOD.match(period):
        raise SourceNotFoundError(f"Período {period!r} inválido.")
    if classification is not None and not re.fullmatch(
        r"\d+\[[\d,all]+\](\|\d+\[[\d,all]+\])*", classification
    ):
        raise SourceNotFoundError(f"Classificação {classification!r} inválida.")
    freq = frequency or meta(client, table).get("periodicidade", {}).get("frequencia", "")
    url = f"{AGREGADOS}/{table}/periodos/{period}/variaveis/{variable}"
    cols: dict[str, list[Any]] = {
        k: [] for k in ("codigo", "localidade", "nivel", "periodo", "data", "valor")
    }
    raw_values: list[object] = []
    urls: list[str] = []
    unit = name = ""
    for loc in _localities(level, places):
        params: dict[str, str] = {"localidades": loc}
        if classification:
            params["classificacao"] = classification
        answer = client.get(url, params=params, timeout=90, ok=frozenset({500}))
        urls.append(answer.url)
        if answer.status == 500:
            raise CatalogError(
                "O IBGE recusou a consulta por ser grande demais. Escolha um período menor ou menos localidades.",
                "http",
                500,
            )
        body = answer.json()
        if not isinstance(body, list):
            raise SourceNotFoundError(f"A variável {variable} não existe na tabela {table} do IBGE.")
        for var in body:
            unit, name = var.get("unidade", ""), var.get("variavel", "")
            for result in var.get("resultados", []):
                for serie in result.get("series", []):
                    place = serie["localidade"]
                    for code, value in serie.get("serie", {}).items():
                        cols["codigo"].append(str(place["id"]))
                        cols["localidade"].append(_clean_name(place.get("nome", "")))
                        cols["nivel"].append(place.get("nivel", {}).get("id", level))
                        cols["periodo"].append(code)
                        cols["data"].append(period_date(code, freq))
                        cols["valor"].append(to_number(value))
                        raw_values.append(value)
    frame = pl.DataFrame(
        cols,
        schema={
            "codigo": pl.String,
            "localidade": pl.String,
            "nivel": pl.String,
            "periodo": pl.String,
            "data": pl.Date,
            "valor": pl.Float64,
        },
    ).sort(["codigo", "periodo"])
    warnings = []
    missing = count_missing(raw_values)
    if missing:
        warnings.append(f"{missing} valores marcados pelo IBGE como sem dado viraram vazio.")
    return ReadResult(frame, urls, warnings, info={"unidade": unit, "variavel": name})


def _clean_name(name: str) -> str:
    """'Campinas (SP)' e 'Acrelândia - AC' viram só o nome do lugar."""
    return re.sub(r"\s*(\([A-Z]{2}\)|-\s[A-Z]{2})$", "", name).strip()


# ------------------------------------------------------------------ localidades


def regions(client: CatalogClient) -> ReadResult:
    url = f"{API}/v1/localidades/regioes"
    rows = client.get(url).json()
    frame = pl.DataFrame(
        {
            "codigo": [str(r["id"]) for r in rows],
            "sigla": [r["sigla"] for r in rows],
            "nome": [r["nome"] for r in rows],
        }
    )
    return ReadResult(frame, [url])


def states(client: CatalogClient) -> ReadResult:
    url = f"{API}/v1/localidades/estados"
    rows = sorted(client.get(url).json(), key=lambda r: r["id"])
    frame = pl.DataFrame(
        {
            "codigo": [f"{r['id']:02d}" for r in rows],
            "sigla": [r["sigla"] for r in rows],
            "nome": [r["nome"] for r in rows],
            "regiao": [r["regiao"]["nome"] for r in rows],
            "regiao_sigla": [r["regiao"]["sigla"] for r in rows],
        }
    )
    return ReadResult(frame, [url])


def _dig(node: Any, *path: str) -> Any:
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def municipalities(client: CatalogClient) -> ReadResult:
    """Os 5.571 municípios, com os códigos como texto (7 e 6 dígitos), UF e região."""
    url = f"{API}/v1/localidades/municipios"
    rows = sorted(client.get(url, timeout=60).json(), key=lambda r: r["id"])
    cols: dict[str, list[Any]] = {
        k: []
        for k in (
            "codigo",
            "codigo6",
            "nome",
            "uf",
            "uf_codigo",
            "uf_nome",
            "regiao",
            "microrregiao",
            "mesorregiao",
            "regiao_imediata",
            "regiao_intermediaria",
        )
    }
    for r in rows:
        # Alguns municípios novos vêm sem microrregião: a UF sai da região imediata.
        uf = _dig(r, "microrregiao", "mesorregiao", "UF") or _dig(
            r, "regiao-imediata", "regiao-intermediaria", "UF"
        )
        code = f"{r['id']:07d}"
        cols["codigo"].append(code)
        cols["codigo6"].append(code[:6])
        cols["nome"].append(r["nome"])
        cols["uf"].append(_dig(uf, "sigla"))
        cols["uf_codigo"].append(f"{uf['id']:02d}" if uf else None)
        cols["uf_nome"].append(_dig(uf, "nome"))
        cols["regiao"].append(_dig(uf, "regiao", "nome"))
        cols["microrregiao"].append(_dig(r, "microrregiao", "nome"))
        cols["mesorregiao"].append(_dig(r, "microrregiao", "mesorregiao", "nome"))
        cols["regiao_imediata"].append(_dig(r, "regiao-imediata", "nome"))
        cols["regiao_intermediaria"].append(_dig(r, "regiao-imediata", "regiao-intermediaria", "nome"))
    frame = pl.DataFrame(cols, schema=dict.fromkeys(cols, pl.String))
    return ReadResult(frame, [url])
