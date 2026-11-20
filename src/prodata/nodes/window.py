"""Rank (spec 044, RF-4401..4406): posição de cada linha pela ordem de colunas, por grupo, com três jeitos de empate.

Posição única = ROW_NUMBER; empate divide e pula = RANK; empate divide sem pular = DENSE_RANK.
"""

from __future__ import annotations

from typing import Literal

import polars as pl
from pydantic import Field

from prodata.engine.sql.fragment import ROW_POSITION, Fragment, SqlContext, numbered, q, sql_for
from prodata.forms import ui
from prodata.nodes.base import NodeContext, NodeOutput, ToolConfig, tool
from prodata.nodes.prep import SortItem

RankMethod = Literal["row", "rank", "dense"]
_SQL_FUNCTION = {"row": "row_number()", "rank": "rank()", "dense": "dense_rank()"}
_METHOD_NAME = {"row": "posição única", "rank": "empate divide e pula", "dense": "empate divide sem pular"}
MAX_TOP = 1_000_000


class RankConfig(ToolConfig):
    order_by: list[SortItem] = Field(
        default_factory=list,
        title="Classificar por",
        description="A coluna que decide quem fica na frente. Ex.: vendas, decrescente (a maior é a 1ª).",
    )
    method: RankMethod = Field("rank", title="Quando empatar", json_schema_extra=ui(widget="rank_method"))
    group_by: list[str] = Field(
        default_factory=list,
        title="Recomeçar a cada grupo",
        description="Opcional. Ex.: região: cada região tem o seu 1º lugar. Vazio = um ranking só.",
        json_schema_extra=ui(widget="columns"),
    )
    column: str = Field("posicao", title="Nome da coluna nova")
    keep_top: bool = Field(False, title="Manter só os primeiros")
    top: int = Field(
        3,
        ge=1,
        le=MAX_TOP,
        title="Quantas posições manter",
        description="De cada grupo. Com empate, podem vir mais linhas (dois 3º lugares contam como 3º).",
        json_schema_extra=ui(show_if={"keep_top": [True]}),
    )


def _name(cfg: RankConfig) -> str:
    return cfg.column.strip() or "posicao"


NOT_READY = "Escolha em Classificar por a coluna que decide a posição: até lá, os dados passam sem mudança."


def _check(columns: list[str], cfg: RankConfig) -> list[SortItem]:
    """As colunas de classificação. Vazio = ainda não configurado (os dados passam, como no Sort sem ordem)."""
    order = [i for i in cfg.order_by if i.column]
    if missing := [c for c in (*(i.column for i in order), *cfg.group_by) if c not in columns]:
        raise ValueError(f"Coluna(s) inexistente(s): {', '.join(missing)}")
    if _name(cfg) in columns:
        raise ValueError(f"Já existe uma coluna chamada '{_name(cfg)}': escolha outro nome para a posição.")
    return order


def _annotate(cfg: RankConfig) -> str:
    order = [i for i in cfg.order_by if i.column]
    if not order:
        return "Escolha a coluna"
    first = order[0]
    text = f"{first.column} {'↓' if first.descending else '↑'}"
    if cfg.group_by:
        text += f" por {', '.join(cfg.group_by)}"
    return text + (f" · top {cfg.top}" if cfg.keep_top else "")


@tool(
    type="prep.rank",
    name="Rank",
    category="prep",
    icon="trophy",
    description=(
        "Ranking: dá a posição de cada linha (1º, 2º, 3º…) pela ordem de uma coluna, por grupo, e fica com o top N. "
        "Equivale a ROW_NUMBER, RANK e DENSE_RANK."
    ),
    config=RankConfig,
    explainer="rank",
    annotate=_annotate,
)
def rank(ctx: NodeContext, cfg: RankConfig) -> NodeOutput:
    df = ctx.input()
    order = _check(df.columns, cfg)
    if not order:
        return NodeOutput(tables={"out": df}, extra={"warnings": [NOT_READY]})
    groups = list(cfg.group_by)
    cols = [i.column for i in order]
    # Ordem estável: grupo, depois a classificação; vazios por último nas duas direções, empate pela chegada.
    df = df.sort(
        [*groups, *cols],
        descending=[False] * len(groups) + [i.descending for i in order],
        nulls_last=True,
        maintain_order=True,
    )
    over = groups or None
    row = pl.int_range(1, pl.len() + 1, dtype=pl.Int64)
    row = row.over(over) if over else row
    name = _name(cfg)
    if cfg.method == "row":
        position = row
    else:
        # Linha nova no ranking quando alguma coluna de classificação muda em relação à anterior do grupo.
        changed = pl.any_horizontal(
            [
                pl.col(c).ne_missing(pl.col(c).shift(1).over(over) if over else pl.col(c).shift(1))
                for c in cols
            ]
        )
        first = row == 1
        step = (first | changed).cast(pl.Int64)
        dense = step.cum_sum().over(over) if over else step.cum_sum()
        if cfg.method == "dense":
            position = dense
        else:
            df = df.with_columns(row.alias("__pd_row"), dense.alias("__pd_tie"))
            position = pl.col("__pd_row").min().over([*groups, "__pd_tie"])
    out = df.with_columns(position.alias(name))
    out = out.drop([c for c in ("__pd_row", "__pd_tie") if c in out.columns])
    if cfg.keep_top:
        out = out.filter(pl.col(name) <= cfg.top)
    return NodeOutput(tables={"out": out})


@sql_for("prep.rank")
def rank_sql(ctx: SqlContext, cfg: RankConfig) -> dict[str, Fragment]:
    source = ctx.input()
    order = _check(source.columns, cfg)
    if not order:
        return {"out": Fragment(f"SELECT * FROM {q(source.block)}", "Rank ainda sem coluna de classificação")}
    groups = ", ".join(q(c) for c in cfg.group_by)
    partition = f"PARTITION BY {groups} " if groups else ""
    by = ", ".join(f"{q(i.column)} {'DESC' if i.descending else 'ASC'} NULLS LAST" for i in order)
    function = _SQL_FUNCTION[cfg.method]
    tie = f", {ROW_POSITION}" if cfg.method == "row" else ""
    name = q(_name(cfg))
    window = f"{function} OVER ({partition}ORDER BY {by}{tie})"
    top = f"\nQUALIFY {name} <= {int(cfg.top)}" if cfg.keep_top else ""
    final_order = ", ".join([*(f"{q(c)} ASC NULLS LAST" for c in cfg.group_by), f"{name} ASC", ROW_POSITION])
    sql = (
        f"SELECT * EXCLUDE ({ROW_POSITION}) FROM (\n"
        f"  SELECT *, {window} AS {name}\n  FROM {numbered(source.block)}{top.replace(chr(10), chr(10) + '  ')}\n"
        f") ORDER BY {final_order}"
    )
    what = f"Posição por {', '.join(i.column for i in order)} ({_METHOD_NAME[cfg.method]})"
    return {
        "out": Fragment(
            sql,
            what + (f", top {cfg.top}" if cfg.keep_top else ""),
            ordered_by=[*cfg.group_by, _name(cfg)],
        )
    }
