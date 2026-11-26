"""Linha e área no tempo (0.9.6): a série inteira, na ordem do eixo, sem o corte de categorias.

O "Máximo de categorias" faz sentido em colunas e rosca (as maiores, e o resto em "Outros"). Numa linha de datas ou
de números, cortar nos primeiros pontos escondia a série sem aviso (a Selic de um ano virava duas semanas). Aqui, com
o eixo X de datas, números ou texto de data (2026-10, 2026-10-29), a linha e a área mostram todos os pontos na ordem
do eixo; acima de ``MAX_POINTS``, uma amostra espalhada pela série inteira (com o primeiro e o último), e o visual
avisa. O espelho em JavaScript fica em ``web/js/dash_compute.js``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import polars as pl

CONTINUOUS_CHARTS = ("line", "area", "area_stacked")
MAX_POINTS = 2000
DATE_TEXT = r"^\d{4}-\d{2}(-\d{2})?([ T]\d{2}:\d{2}(:\d{2}(\.\d+)?)?)?$"


def continuous(df: pl.DataFrame, x: str, chart_type: str) -> bool:
    """Linha ou área com o eixo X de datas, números ou texto de data: a série vai inteira, na ordem do eixo."""
    if chart_type not in CONTINUOUS_CHARTS or x not in df.columns:
        return False
    dtype = df.schema[x]
    if dtype == pl.Boolean:
        return False
    if dtype.is_numeric() or dtype == pl.Date or isinstance(dtype, pl.Datetime):
        return True
    if dtype == pl.String:
        values = df[x].drop_nulls()
        return values.len() > 0 and values.str.contains(DATE_TEXT).all()
    return False


def axis_order(df: pl.DataFrame, x: str, label: pl.Expr) -> list[str]:
    """Os rótulos do eixo na ordem dos valores (datas e números em ordem, não como texto); o vazio por último."""
    keys = df.select(pl.col(x).alias("__x"), label.alias("label")).unique(subset="label", keep="first")
    return [str(v) for v in keys.sort("__x", nulls_last=True)["label"].to_list()]


def spread[T](items: Sequence[T], limit: int = MAX_POINTS) -> list[T]:
    """No máximo ``limit`` itens espalhados pela sequência inteira, com o primeiro e o último."""
    n = len(items)
    if n <= limit:
        return list(items)
    # metade para cima, como o Math.floor(v + 0.5) do espelho em JavaScript (round do Python arredonda para o par)
    return [items[int(i * (n - 1) / (limit - 1) + 0.5)] for i in range(limit)]


def counts(
    widget: dict[str, Any], df: pl.DataFrame, x: str, chart_type: str, max_items: int, total: int
) -> None:
    """O que ficou de fora, para o visual avisar: pontos da série (linha e área no tempo) ou categorias cortadas."""
    if continuous(df, x, chart_type):
        widget.update(point_count=total, sampled=len(widget["series"]) < total)
    elif total > max_items:
        widget["category_count"] = total
