"""Conversão de tipos tolerante, com relatório do que não converteu (spec 018, RF-1804).

O ``cast`` do Polars é estrito demais para dados de planilha brasileira: "1.234,56", " 12 " ou "12.0"
viram vazio sem aviso, e texto → data/booleano nem existe. Aqui cada conversão entende os formatos
comuns e devolve quantos valores (e quais) não puderam ser convertidos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import polars as pl

TRUE_WORDS = ["true", "1", "sim", "s", "yes", "y", "verdadeiro", "v", "x"]
FALSE_WORDS = ["false", "0", "não", "nao", "n", "no", "falso", "f"]
DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d"]
DATETIME_FORMATS = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"]
# O Excel guarda datas como dias desde 30/12/1899.
EXCEL_EPOCH = pl.date(1899, 12, 30)


@dataclass
class Conversion:
    series: pl.Series
    failed: int = 0
    examples: list[str] = field(default_factory=list)
    number_format: str = ""  # número em texto: "br" ou "us", o formato usado (spec 048)


def _text(series: pl.Series) -> pl.Series:
    return series.cast(pl.String).str.strip_chars()


NumberFormat = Literal["auto", "br", "us"]
# Valores que só existem num dos padrões (spec 048, RF-4836). Os mesmos padrões estão nas macros do SQL.
US_ONLY = (
    r"^-?\d{1,3}(,\d{3})+\.\d+$"  # 1,234.56
    r"|^-?\d{1,3}(,\d{3}){2,}$"  # 1,234,567
    r"|^-?0\.\d+$"  # 0.5
    r"|^-?\d*\.(\d{1,2}|\d{4,})$"  # 3.75, 12.5, 2.12345 (nunca 3 casas: "1.200" é ambíguo)
)
BR_ONLY = (
    r"^-?\d{1,3}(\.\d{3})+,\d+$"  # 1.234,56
    r"|^-?\d{1,3}(\.\d{3}){2,}$"  # 1.234.567
    r"|^-?0,\d+$"  # 0,5
    r"|^-?\d*,(\d{1,2}|\d{4,})$"  # 12,5, 1234,56
)


def _number_text(text: pl.Series) -> pl.Series:
    return text.str.replace_all(r"(?i)r\$|\s", "")


def number_format_of(text: pl.Series) -> Literal["br", "us"]:
    """O formato da coluna: o que tiver mais valores que só existem nele. Empate ou ambíguo: brasileiro."""
    s = _number_text(text.drop_nulls())
    us = int(s.str.contains(US_ONLY).sum())
    br = int(s.str.contains(BR_ONLY).sum())
    return "us" if us > br else "br"


def parse_number(text: pl.Series, number_format: NumberFormat = "auto") -> pl.Series:
    """Número a partir de texto, com "R$" e espaços. Padrão brasileiro: ponto separa o milhar e vírgula o decimal
    ("1.200" é mil e duzentos). Padrão americano: vírgula separa o milhar e ponto o decimal. ``auto`` decide pela
    coluna inteira (spec 048, RF-4836): dados de fora do Brasil são reconhecidos, e o ambíguo fica brasileiro."""
    s = _number_text(text)
    fmt = number_format_of(text) if number_format == "auto" else number_format
    if fmt == "us":
        normalized = s.str.replace_all(",", "", literal=True)
    else:
        normalized = s.str.replace_all(r"\.", "").str.replace(",", ".", literal=True)
    return pl.select(normalized.alias(text.name)).to_series().cast(pl.Float64, strict=False)


def parse_date(text: pl.Series) -> pl.Series:
    attempts = [text.str.to_date(fmt, strict=False) for fmt in DATE_FORMATS]
    attempts += [text.str.to_datetime(fmt, strict=False).dt.date() for fmt in DATETIME_FORMATS]
    attempts.append((text + "-01").str.to_date("%Y-%m-%d", strict=False))  # 2026-10
    return pl.select(pl.coalesce(attempts).alias(text.name)).to_series()


def _convert(
    series: pl.Series, target: pl.DataType | type[pl.DataType], number_format: NumberFormat = "auto"
) -> pl.Series:
    source = series.dtype
    if target == pl.String:
        return series.cast(pl.String)
    if source == pl.String:
        text = _text(series)
        if target in (pl.Float64, pl.Int64):
            number = parse_number(text, number_format)
            return number if target == pl.Float64 else number.cast(pl.Int64, strict=False)
        if target == pl.Boolean:
            lower = text.str.to_lowercase()
            out = pl.when(lower.is_in(TRUE_WORDS)).then(True).when(lower.is_in(FALSE_WORDS)).then(False)
            return pl.select(out.alias(series.name)).to_series()
        if target == pl.Date:
            return parse_date(text)
    if target == pl.Date and source.is_numeric():
        days = series.cast(pl.Int64, strict=False)
        return pl.select((EXCEL_EPOCH + pl.duration(days=pl.lit(days))).alias(series.name)).to_series()
    if target == pl.Date and isinstance(source, pl.Datetime):
        return series.dt.date()
    return series.cast(target, strict=False)


def convert(
    series: pl.Series, target: pl.DataType | type[pl.DataType], number_format: NumberFormat = "auto"
) -> Conversion:
    """Converte e conta o que se perdeu: valores preenchidos que viraram vazio."""
    out = _convert(series, target, number_format).alias(series.name)
    filled = series.is_not_null()
    if series.dtype == pl.String:
        filled = filled & (series.str.strip_chars() != "")
    lost = filled & out.is_null()
    failed = int(lost.sum())
    examples = (
        [str(v) for v in series.filter(lost).unique(maintain_order=True).head(3).to_list()] if failed else []
    )
    decided = ""
    if series.dtype == pl.String and target in (pl.Float64, pl.Int64):
        decided = number_format_of(_text(series)) if number_format == "auto" else number_format
    return Conversion(out, failed, examples, decided)
