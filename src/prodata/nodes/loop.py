"""Laço (spec 041, RF-4160..4171): as caixas Início do loop e Fim do loop.

As duas caixas só repassam a tabela; quem repete o corpo (as caixas entre elas) é o executor (engine/loops.py), que
reconhece o par pelo campo ``start`` do Fim.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from prodata.engine.sql.fragment import Fragment, NoTranslationError, SqlContext, q, sql_for
from prodata.forms import ui
from prodata.nodes.base import NodeContext, NodeOutput, Port, ToolConfig, tool

LOOP_START = "flow.loop_start"
LOOP_END = "flow.loop_end"

LoopMode = Literal["each", "range", "while"]
_MODES = {
    "each": "Para cada valor de uma coluna",
    "range": "Para cada número ou data de uma faixa",
    "while": "Enquanto uma condição valer",
}


class LoopStartConfig(ToolConfig):
    mode: LoopMode = Field("each", title="Repetir", json_schema_extra=ui(labels=_MODES))
    column: str = Field("", title="Coluna", json_schema_extra=ui(widget="column", show_if={"mode": ["each"]}))
    values: str = Field(
        "",
        title="Ou só estes valores",
        description="Um por linha. Vazio: todos os valores da coluna.",
        json_schema_extra=ui(widget="textarea", show_if={"mode": ["each"]}),
    )
    order: Literal["asc", "appearance"] = Field(
        "asc",
        title="Ordem das voltas",
        json_schema_extra=ui(
            labels={"asc": "Crescente", "appearance": "Na ordem em que aparecem"}, show_if={"mode": ["each"]}
        ),
    )
    rows: Literal["group", "all"] = Field(
        "group",
        title="Em cada volta, a saída traz",
        json_schema_extra=ui(
            labels={"group": "Só as linhas do valor da volta", "all": "A tabela inteira"},
            show_if={"mode": ["each"]},
        ),
    )
    start: str = Field(
        "1",
        title="De",
        description="Um número (1) ou uma data (01/01/2026).",
        json_schema_extra=ui(show_if={"mode": ["range"]}),
    )
    end: str = Field("10", title="Até", json_schema_extra=ui(show_if={"mode": ["range"]}))
    step: float = Field(1, gt=0, title="Passo", json_schema_extra=ui(show_if={"mode": ["range"]}))
    unit: Literal["number", "day", "week", "month", "year"] = Field(
        "number",
        title="Passo em",
        json_schema_extra=ui(
            labels={"number": "Números", "day": "Dias", "week": "Semanas", "month": "Meses", "year": "Anos"},
            show_if={"mode": ["range"]},
        ),
    )
    max_iterations: int = Field(1000, ge=1, le=100_000, title="Limite de voltas")
    # Aba SQL (spec 041): preenchido pelo programa ao desenrolar o laço; nunca vai no arquivo do fluxo.
    sql_turn: dict[str, Any] = Field(default_factory=dict, json_schema_extra=ui(widget="hidden"))


def _start_note(cfg: LoopStartConfig) -> str:
    if cfg.mode == "each":
        return (
            f"Para cada {cfg.column}"
            if cfg.column
            else "Para cada valor da lista"
            if cfg.values.strip()
            else "Escolha a coluna"
        )
    if cfg.mode == "range":
        return f"De {cfg.start} até {cfg.end}"
    return f"Enquanto · até {cfg.max_iterations} voltas"


@tool(
    type=LOOP_START,
    name="Loop",
    category="control",
    icon="repeat",
    description="Repete as caixas entre o Início e o Fim do loop: para cada valor de uma coluna, para cada número ou data, ou enquanto uma condição valer. Use [#valor], [#volta] e [#total] nas fórmulas de dentro.",
    config=LoopStartConfig,
    annotate=_start_note,
)
def loop_start(ctx: NodeContext, cfg: LoopStartConfig) -> NodeOutput:
    return NodeOutput(tables={"out": ctx.input()})


class LoopEndConfig(ToolConfig):
    start: str = Field("", title="Início do loop", json_schema_extra=ui(widget="hidden"))
    output: Literal["stack", "accumulate", "last"] = Field(
        "stack",
        title="O que sai",
        json_schema_extra=ui(
            labels={
                "stack": "Empilhar: todas as voltas numa tabela",
                "accumulate": "Acumular: o resultado de uma volta entra na próxima",
                "last": "Só a última volta",
            }
        ),
    )
    expression: str = Field(
        "",
        title="Continuar enquanto (modo Enquanto)",
        description="Avaliada no resultado de cada volta: o laço continua enquanto alguma linha atender. Só vale com o Início em 'Enquanto'.",
        json_schema_extra=ui(widget="expression"),
    )
    # Aba SQL (spec 041): as voltas desenroladas, preenchidas pelo programa; nunca vão no arquivo do fluxo.
    sql_turns: dict[str, Any] = Field(default_factory=dict, json_schema_extra=ui(widget="hidden"))


@tool(
    type=LOOP_END,
    name="Fim do loop",
    category="control",
    icon="repeat",
    description="Onde o laço termina: junta o resultado das voltas.",
    config=LoopEndConfig,
    inputs=[Port("in", "I", "Resultado da volta")],
    annotate=lambda c: {"stack": "Empilha as voltas", "accumulate": "Acumula", "last": "Última volta"}[
        c.output
    ],
    hidden=True,
)
def loop_end(ctx: NodeContext, cfg: LoopEndConfig) -> NodeOutput:
    return NodeOutput(tables={"out": ctx.input()})


# Aba SQL (RF-4170): o laço chega aqui já desenrolado (engine/sql/loop_expand.py): cada volta é uma cópia do corpo,
# com o Início trocado por um filtro do valor, e o Fim empilha as cópias. Sem desenrolar, fica sem tradução, com o motivo.
_NO_SQL = "O laço não tem tradução para SQL neste formato."


@sql_for(LOOP_START)
def loop_start_sql(ctx: SqlContext, cfg: LoopStartConfig) -> dict[str, Fragment]:
    turn = cfg.sql_turn
    if not turn.get("active"):
        raise NoTranslationError(str(turn.get("reason") or _NO_SQL))
    source = ctx.input()
    where = turn.get("where") or ""
    sql = f"SELECT *\nFROM {q(source.block)}" + (f"\nWHERE {where}" if where else "")
    explain = (
        f"Volta {turn.get('turn')}: {turn.get('label')}"
        if where
        else f"Volta {turn.get('turn')}: a tabela inteira"
    )
    return {"out": Fragment(sql, explain)}


@sql_for(LOOP_END)
def loop_end_sql(ctx: SqlContext, cfg: LoopEndConfig) -> dict[str, Fragment]:
    plan = cfg.sql_turns
    turns = plan.get("turns") or []
    if not turns:
        raise NoTranslationError(str(plan.get("reason") or _NO_SQL))
    if plan.get("output") == "last":
        last = ctx.input(turns[-1]["port"])
        return {
            "out": Fragment(f"SELECT *\nFROM {q(last.block)}", f"Só a última volta ({len(turns)} voltas)")
        }
    value = str(plan.get("value_column") or "")
    selects = []
    for t in turns:
        src = ctx.input(t["port"])
        extra = f", {int(t['turn'])} AS {q('volta')}"
        if value and value not in src.columns:
            extra += f", {t['literal']} AS {q(value)}"
        selects.append(f"SELECT *{extra} FROM {q(src.block)}")
    glue = "\nUNION ALL BY NAME\n"
    return {
        "out": Fragment(glue.join(selects), f"Empilha as {len(turns)} voltas do laço, com a coluna volta")
    }
