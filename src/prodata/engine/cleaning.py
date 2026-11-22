"""Recomendações de limpeza a partir do que a caixa entrega (spec 048, RF-4831..4835).

O perfil já encontra os problemas comuns; aqui cada um vira uma recomendação com a contagem, exemplos "antes → depois"
e a correção pronta: a ferramenta que já existe (Data Cleansing, Select com troca de tipo, Unique), configurada. Nada é
corrigido sozinho: a tela mostra e a pessoa escolhe. Número e data guardados como texto usam a mesma conversão
tolerante do Select e do aviso de "tipo mudou" (spec 046), então o que a recomendação promete é o que a caixa faz.
"""

from __future__ import annotations

from typing import Any

import polars as pl

from prodata.engine.convert import convert

MAX_ROWS = 200_000  # amostra para calcular (as contagens dizem "na amostra" acima disso)
MIN_SHARE = 0.8  # número/data como texto: pelo menos 80% dos valores preenchidos convertem
MAX_EXAMPLES = 5


def _cleanse(column: str, **flags: Any) -> dict[str, Any]:
    base = {"columns": [column], "trim_whitespace": False, "collapse_whitespace": False, "empty_as_null": False,
            "case_mode": "none"}  # fmt: skip
    return {"tool": "prep.data_cleansing", "port": "out", "config": {**base, **flags}}


def _quoted(value: Any) -> str:
    return f'"{value}"' if isinstance(value, str) else str(value)


def _padded(name: str, text: pl.Series) -> dict[str, Any] | None:
    values = text.drop_nulls()
    stripped = values.str.strip_chars()
    hit = (values != stripped) & (stripped != "")
    count = int(hit.sum())
    if not count:
        return None
    examples = values.filter(hit).unique(maintain_order=True).head(MAX_EXAMPLES).to_list()
    return {"tipo": "espacos", "coluna": name, "linhas": count,
            "titulo": f"{count} {'valor' if count == 1 else 'valores'} com espaço no começo ou no fim",
            "detalhe": f'Em {name}: "SP " não casa com "SP" num Join ou num filtro.',
            "exemplos": [{"antes": _quoted(v), "depois": _quoted(v.strip())} for v in examples],
            "correcao": _cleanse(name, trim_whitespace=True)}  # fmt: skip


def _as_type(name: str, text: pl.Series) -> dict[str, Any] | None:
    """Número ou data guardados como texto (com os valores que impedem, como "N/D")."""
    filled = text.drop_nulls().str.strip_chars()
    filled = filled.filter(filled != "")
    if filled.len() < 3:
        return None
    for target, kind, word in ((pl.Float64, "numero_texto", "número"), (pl.Date, "data_texto", "data")):
        result = convert(filled, target)
        ok = filled.len() - result.failed
        if ok / filled.len() < MIN_SHARE or ok == 0:
            continue
        cast = "Date" if target == pl.Date else "Float64"
        if target == pl.Float64:
            numbers = result.series.drop_nulls()
            if numbers.len() and bool((numbers == numbers.round(0)).all()):
                cast = "Int64"
        blockers = result.examples
        suffix = (
            f" ({result.failed} {'linha' if result.failed == 1 else 'linhas'} com {', '.join(_quoted(b) for b in blockers)})"
            if result.failed
            else ""
        )
        sample = filled.unique(maintain_order=True).head(MAX_EXAMPLES - len(blockers)).to_list()
        converted = convert(pl.Series(name, sample, dtype=pl.String), target).series.to_list()
        examples = [
            {"antes": _quoted(v), "depois": _shown(c, cast)} for v, c in zip(sample, converted, strict=True)
        ]
        examples += [{"antes": _quoted(b), "depois": "vazio"} for b in blockers]
        return {"tipo": kind, "coluna": name, "linhas": int(filled.len()),
                "titulo": f"{name} parece {word}, mas está como texto{suffix}",
                "detalhe": f"Como texto, {name} não soma, não compara como {word} e ordena errado.",
                "exemplos": examples,
                "correcao": {"tool": "prep.select", "port": "out",
                             "config": {"fields": [{"name": name, "keep": True, "rename": "", "cast": cast}], "order": []}}}  # fmt: skip
    return None


def _case(name: str, text: pl.Series) -> dict[str, Any] | None:
    values = text.drop_nulls().str.strip_chars()
    values = values.filter(values != "")
    if values.is_empty():
        return None
    frame = pl.DataFrame({"v": values}).with_columns(pl.col("v").str.to_lowercase().alias("k"))
    groups = frame.group_by("k").agg(
        pl.col("v").n_unique().alias("formas"), pl.col("v").unique().alias("lista"), pl.len().alias("n")
    )
    mixed = groups.filter(pl.col("formas") > 1)
    if mixed.is_empty():
        return None
    rows = int(mixed["n"].sum())
    upper = int((frame["v"] == frame["v"].str.to_uppercase()).sum())
    mode = "upper" if upper >= values.len() / 2 else "title"
    sample = [sorted(lst)[:3] for lst in mixed.sort("n", descending=True)["lista"].head(3).to_list()]
    shown = ", ".join("/".join(_quoted(v) for v in forms) for forms in sample)
    fix = (lambda v: v.upper()) if mode == "upper" else (lambda v: v.title())
    return {"tipo": "caixa", "coluna": name, "linhas": rows,
            "titulo": f"O mesmo valor escrito com maiúsculas diferentes ({shown})",
            "detalhe": f"Em {name}, cada forma vira um grupo diferente no Summarize e no Join.",
            "exemplos": [{"antes": _quoted(v), "depois": _quoted(fix(v))} for forms in sample for v in forms][:MAX_EXAMPLES],
            "correcao": _cleanse(name, case_mode=mode)}  # fmt: skip


def _empty_text(name: str, text: pl.Series) -> dict[str, Any] | None:
    empties = int((text.drop_nulls().str.strip_chars() == "").sum())
    nulls = int(text.null_count())
    if not empties or not nulls:
        return None
    return {"tipo": "texto_vazio", "coluna": name, "linhas": empties,
            "titulo": f"{empties} textos vazios misturados com {nulls} vazios de verdade",
            "detalhe": f'Em {name}, "" e vazio contam diferente num filtro "está vazio".',
            "exemplos": [{"antes": '""', "depois": "vazio"}],
            "correcao": _cleanse(name, empty_as_null=True)}  # fmt: skip


def _duplicates(df: pl.DataFrame) -> dict[str, Any] | None:
    if df.width == 0 or df.height < 2:
        return None
    try:
        repeated = int(df.is_duplicated().sum())  # todas as cópias, inclusive a primeira
        extra = df.height - df.unique().height  # as que sobram (o Unique tira)
    except pl.exceptions.InvalidOperationError:  # colunas que não comparam (listas aninhadas)
        return None
    if extra <= 0:
        return None
    return {"tipo": "linhas_repetidas", "coluna": "", "linhas": extra,
            "titulo": f"{extra} {'linha repetida' if extra == 1 else 'linhas repetidas'} por inteiro",
            "detalhe": f"{repeated} linhas aparecem mais de uma vez com todos os valores iguais.",
            "exemplos": [], "correcao": {"tool": "prep.unique", "port": "U", "config": {"keys": []}}}  # fmt: skip


def recommend(df: pl.DataFrame, ignored: set[str] | None = None) -> list[dict[str, Any]]:
    """As recomendações da tabela, as que atingem mais linhas primeiro. ``ignored``: chaves "tipo:coluna"."""
    ignored = ignored or set()
    sample = df.head(MAX_ROWS)
    found: list[dict[str, Any]] = []
    for name in sample.columns:
        series = sample[name]
        if series.dtype != pl.String:
            continue
        for check in (_padded, _as_type, _case, _empty_text):
            rec = check(name, series)
            if rec:
                found.append(rec)
    if (dup := _duplicates(sample)) is not None:
        found.append(dup)
    for rec in found:
        rec["id"] = f"{rec['tipo']}:{rec['coluna']}"
        rec["amostra"] = df.height > MAX_ROWS
    out = [r for r in found if r["id"] not in ignored]
    out.sort(key=lambda r: r["linhas"], reverse=True)
    return out


def _shown(value: Any, cast: str) -> str:
    """O valor convertido como a pessoa vai ver: inteiro sem ",0", decimal com vírgula, data dd /mm/aaaa."""
    if value is None:
        return "vazio"
    if cast == "Int64" and isinstance(value, float):
        return str(int(value))
    if isinstance(value, float):
        return f"{value:g}".replace(".", ",")
    if hasattr(value, "strftime"):
        return str(value.strftime("%d/%m/%Y"))
    return str(value)
