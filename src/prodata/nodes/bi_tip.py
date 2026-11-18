"""Colunas extras na dica dos gráficos (spec 041, RF-4141): agregadas como o valor (na contagem, somadas).

O espelho no HTML exportado fica em web/js/dash_compute.js; os dois precisam dar o mesmo número.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import polars as pl

Extras = dict[str, float | None]
Row = tuple[str, float, Extras]


def tip_columns(df: pl.DataFrame, wanted: Sequence[str], x_column: str) -> list[str]:
    """As colunas pedidas que existem, sem repetir e sem a categoria."""
    return [c for c in dict.fromkeys(wanted) if c in df.columns and c not in (x_column, "label", "value")]


def tip_aggregates(columns: list[str], agg: str) -> list[pl.Expr]:
    how = "sum" if agg == "count" else agg
    return [getattr(pl.col(c).cast(pl.Float64, strict=False), how)().alias(f"__tip_{c}") for c in columns]


def tip_extras(names: list[str], values: Sequence[Any]) -> Extras:
    return {c: (None if v is None else float(v)) for c, v in zip(names, values, strict=True)}


def series_item(label: str, value: float, extras: Extras) -> dict[str, Any]:
    s: dict[str, Any] = {"label": label, "value": round(value, 4)}
    if extras:
        s["tip"] = {c: (None if x is None else round(x, 4)) for c, x in extras.items()}
    return s


def others_extras(rest: list[Row]) -> Extras:
    """O "Outros" soma as colunas extras das categorias que ficaram de fora."""
    return {c: float(sum(r[2][c] or 0 for r in rest)) for c in rest[0][2]} if rest else {}
