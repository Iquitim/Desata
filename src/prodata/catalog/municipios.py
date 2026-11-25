"""Juntar com municípios do IBGE (spec 049, RF-4962, CA-06).

Uma caixa SQL comum faz a junção, com a regra à vista: código de 7 dígitos, código de 6 (sem o dígito
verificador) ou nome com UF ("São Paulo/SP", "Sao Paulo - SP", "São Paulo (SP)" ou a UF numa coluna à parte), sem
diferenciar acento, maiúsculas, hífen e "d'"/"D'". Nome sem UF casa só quando existe num estado só. As linhas que
não casam ficam, com o código vazio. A conferência antes de inserir executa o mesmo SQL sobre os dados da caixa:
o que a pessoa vê é o que o fluxo vai dar.
"""

from __future__ import annotations

from typing import Any

import duckdb
import polars as pl

from prodata.engine import sandbox

UFS = ("AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI",
       "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO")  # fmt: skip
OUT = ("ibge_municipio_codigo", "ibge_municipio_nome", "ibge_uf")


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _key(expr: str) -> str:
    """Nome comparável: sem acento, minúsculas, sem apóstrofo (d'Oeste e D'Oeste ficam iguais), hífen vira espaço."""
    return ("trim(regexp_replace(regexp_replace(strip_accents(lower(" + expr + ")), '[''’`´]', '', 'g'), "
            "'[^a-z0-9]+', ' ', 'g'))")  # fmt: skip


def output_names(columns: list[str]) -> tuple[str, str, str]:
    """Os nomes das colunas novas, sem repetir uma que a tabela já tem."""
    taken = set(columns)
    names = []
    for base in OUT:
        name, n = base, 2
        while name in taken:
            name, n = f"{base}_{n}", n + 1
        taken.add(name)
        names.append(name)
    return names[0], names[1], names[2]


def match_sql(column: str, uf_column: str | None, columns: list[str]) -> str:
    """A consulta da caixa SQL: ``input_1`` é a tabela, ``input_2`` os municípios do IBGE."""
    code, name, uf = output_names(columns)
    ufs = ", ".join(f"'{u}'" for u in UFS)
    value = f"trim(CAST(t.{_q(column)} AS VARCHAR))"
    uf_col = f"upper(trim(CAST(t.{_q(uf_column)} AS VARCHAR)))" if uf_column else "NULL"
    return f"""-- Junta com os municípios do IBGE: código de 7 dígitos, de 6 (sem o verificador) ou nome com UF,
-- sem diferenciar acento, maiúsculas, hífen e "d'". As linhas que não casam ficam, com o código vazio.
WITH municipios AS (
  SELECT codigo, codigo6, nome, uf, {_key("nome")} AS chave,
         count(*) OVER (PARTITION BY {_key("nome")}) AS homonimos
  FROM input_2
),
tabela AS (
  SELECT t.*, row_number() OVER () AS __pd_linha, {value} AS __pd_valor, {uf_col} AS __pd_uf_coluna
  FROM input_1 AS t
),
partes AS (
  SELECT *,
    CASE WHEN regexp_full_match(__pd_valor, '[0-9]{{7}}') THEN __pd_valor END AS __pd_c7,
    CASE WHEN regexp_full_match(__pd_valor, '[0-9]{{6}}') THEN __pd_valor END AS __pd_c6,
    CASE WHEN upper(regexp_extract(__pd_valor, '[/,(-]\\s*([A-Za-z]{{2}})\\)?\\s*$', 1)) IN ({ufs})
         THEN upper(regexp_extract(__pd_valor, '[/,(-]\\s*([A-Za-z]{{2}})\\)?\\s*$', 1)) END AS __pd_uf_texto
  FROM tabela
),
chaves AS (
  SELECT *, coalesce(__pd_uf_coluna, __pd_uf_texto) AS __pd_uf,
    {_key("CASE WHEN __pd_uf_texto IS NOT NULL THEN regexp_replace(__pd_valor, '\\s*[/,(-]\\s*[A-Za-z]{2}\\)?\\s*$', '') ELSE __pd_valor END")} AS __pd_chave
  FROM partes
)
SELECT c.* EXCLUDE (__pd_linha, __pd_valor, __pd_uf_coluna, __pd_c7, __pd_c6, __pd_uf_texto, __pd_uf, __pd_chave),
       m.codigo AS {_q(code)}, m.nome AS {_q(name)}, m.uf AS {_q(uf)}
FROM chaves AS c
LEFT JOIN municipios AS m ON
     m.codigo = c.__pd_c7
  OR m.codigo6 = c.__pd_c6
  OR (c.__pd_c7 IS NULL AND c.__pd_c6 IS NULL AND m.chave = c.__pd_chave
      AND (m.uf = c.__pd_uf OR (c.__pd_uf IS NULL AND m.homonimos = 1)))
ORDER BY c.__pd_linha"""


def check(
    frame: pl.DataFrame, municipalities: pl.DataFrame, column: str, uf_column: str | None
) -> dict[str, Any]:
    """Executa a mesma consulta e conta: quantas linhas casam e quais valores não casam, com o motivo."""
    if column not in frame.columns or (uf_column and uf_column not in frame.columns):
        raise ValueError("A coluna escolhida não está mais nesta saída. Execute o fluxo de novo.")
    sql = match_sql(column, uf_column, frame.columns)
    code = output_names(frame.columns)[0]
    with sandbox.sandboxed_connection() as con:
        con.register("input_1", frame)
        con.register("input_2", municipalities)
        sandbox.lock(con)
        try:
            out = con.sql(sql).pl()
        except duckdb.Error as exc:
            raise ValueError(str(exc).split("\n\nLINE")[0]) from None
    matched = out.filter(pl.col(code).is_not_null()).height
    missing = out.filter(pl.col(code).is_null()).group_by(column).len().sort("len", descending=True).head(50)
    names = {_plain(n) for n in municipalities["nome"].to_list()}
    sample = []
    for value, count in missing.iter_rows():
        text = "" if value is None else str(value)
        if not text.strip():
            reason = "vazio"
        elif _plain(text) in names and not uf_column and not _has_uf(text):
            reason = (
                "o nome existe em mais de um estado: informe a UF (São Paulo/SP) ou escolha a coluna de UF"
            )
        else:
            reason = "não encontrado: confira a grafia, o código ou a UF"
        sample.append({"valor": text, "linhas": count, "motivo": reason})
    return {"linhas": frame.height, "casam": matched, "nao_casam": frame.height - matched, "exemplos": sample,
            "sql": sql}  # fmt: skip


def _plain(text: str) -> str:
    import re
    import unicodedata

    text = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", re.sub(r"['’`´]", "", text)).strip()


def _has_uf(text: str) -> bool:
    import re

    found = re.search(r"[/,(-]\s*([A-Za-z]{2})\)?\s*$", text)
    return bool(found and found.group(1).upper() in UFS)
