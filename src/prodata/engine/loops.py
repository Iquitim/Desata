"""Laço no executor (spec 041, RF-4160..4171).

O corpo do laço são as caixas nos caminhos entre o Início e o Fim do loop. No passo normal o executor pula o corpo;
ao chegar no Fim, roda o corpo uma vez por volta, cada volta num espaço de cache próprio (``<fluxo>~<fim>~<volta>``),
com as variáveis ``[#valor]``, ``[#volta]`` e ``[#total]`` trocadas como constantes. O que sai no Fim é empilhado,
acumulado ou só a última volta.
"""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import polars as pl

from prodata.domain.constants import ConstantValue
from prodata.domain.workflow import Workflow
from prodata.engine import graph
from prodata.engine.dates import parse_user_date
from prodata.nodes.loop import LOOP_END, LOOP_START, LoopStartConfig

LOOP_NAMES = ("valor", "volta", "total")
MAX_DEPTH = 3
MAX_TIMES = 1000  # tempos por volta guardados no resultado do Fim
_VAR = re.compile(r"\[#(valor|volta)\]")


@dataclass
class Loop:
    start: str
    end: str
    body: list[str]  # em ordem de execução, sem o Início e o Fim
    depth: int = 1
    inner: list[str] = field(default_factory=list)  # Fins dos laços de dentro


@dataclass
class Found:
    loops: dict[str, Loop] = field(default_factory=dict)  # por id do Fim
    problems: dict[str, str] = field(default_factory=dict)
    warnings: dict[str, list[str]] = field(default_factory=dict)

    @property
    def members(self) -> set[str]:
        """Caixas dentro de algum laço (podem usar as variáveis do laço)."""
        return {b for loop in self.loops.values() for b in loop.body} | {
            loop.end for loop in self.loops.values()
        }


def _descendants(workflow: Workflow, node_id: str) -> set[str]:
    children: dict[str, list[str]] = {}
    for e in workflow.edges:
        children.setdefault(e.source, []).append(e.target)
    seen: set[str] = set()
    queue = deque(children.get(node_id, []))
    while queue:
        n = queue.popleft()
        if n not in seen:
            seen.add(n)
            queue.extend(children.get(n, []))
    return seen


def find(workflow: Workflow, order: list[str]) -> Found:
    """Os laços do fluxo e o que está errado no desenho deles (RF-4167)."""
    out = Found()
    _pairs(workflow, order, out)
    _leaks(workflow, out)
    _nesting(out)
    _warnings(workflow, out)
    return out


def _pairs(workflow: Workflow, order: list[str], out: Found) -> None:
    """Cada Fim com o seu Início, e o corpo entre eles."""
    types = {n.id: n.type for n in workflow.nodes}
    position = {n: i for i, n in enumerate(order)}
    paired: set[str] = set()
    for end in (n for n in workflow.nodes if n.type == LOOP_END):
        sid = str(end.config.get("start") or "")
        if types.get(sid) != LOOP_START:
            out.problems[end.id] = (
                "Este Fim do loop não tem o Início: crie o laço pela paleta (Loop) ou apague esta caixa."
            )
        elif sid not in graph.ancestors(workflow, end.id):
            out.problems[end.id] = (
                "Ligue o Início do loop até este Fim, passando pelas caixas que vão repetir."
            )
        elif sid in paired:
            out.problems[end.id] = "Este Início do loop já tem um Fim: cada laço tem um Início e um Fim."
        else:
            paired.add(sid)
            body = (_descendants(workflow, sid) & graph.ancestors(workflow, end.id)) - {sid, end.id}
            out.loops[end.id] = Loop(sid, end.id, sorted(body, key=lambda n: position.get(n, 0)))
    for start in (n for n in workflow.nodes if n.type == LOOP_START):
        if start.id not in paired:
            out.problems[start.id] = (
                "Falta o Fim do loop: ligue as caixas que vão repetir até um Fim do loop."
            )


def _leaks(workflow: Workflow, out: Found) -> None:
    """Nada sai do corpo sem passar pelo Fim; o Início só alimenta o corpo."""
    for lp in out.loops.values():
        inside = set(lp.body)
        for edge in workflow.edges:
            escapes = edge.target not in inside and edge.target != lp.end
            if edge.source in inside and escapes:
                out.problems[edge.source] = (
                    "Esta caixa está dentro do laço e manda dados para fora sem passar pelo Fim do loop."
                )
            if edge.source == lp.start and escapes:
                out.problems[lp.start] = "O Início do loop só pode ligar nas caixas do laço."


def _nesting(out: Found) -> None:
    """Laços de dentro ficam inteiros no corpo do de fora; cruzados são erro; até três níveis."""
    items = list(out.loops.values())
    for a in items:
        for other in items:
            if a is other:
                continue
            a_set = {a.start, a.end, *a.body}
            if a_set <= set(other.body):
                other.inner.append(a.end)
            elif a_set & set(other.body) and not {other.start, other.end, *other.body} <= set(a.body):
                out.problems.setdefault(
                    a.end,
                    "Dois laços se cruzam: um laço de dentro precisa ficar inteiro entre o Início e o Fim do outro.",
                )
    for a in items:
        a.depth = 1 + sum(1 for other in items if a.end in other.inner)
        if a.depth > MAX_DEPTH:
            out.problems[a.end] = f"Laço dentro de laço vai até {MAX_DEPTH} níveis."


_SIMPLE = {"prep.filter", "prep.formula", "transform.summarize", "prep.select", "prep.sort"}


def _warnings(workflow: Workflow, out: Found) -> None:
    """Gravar sem a variável no nome; laço que um Summarize resolveria (RF-4169, RF-4171)."""
    nodes = {n.id: n for n in workflow.nodes}
    for lp in out.loops.values():
        for bid in lp.body:
            n = nodes[bid]
            name = str(n.config.get("filename") or "")
            if n.type == "io.output_data" and not _VAR.search(name) and "{" not in name:
                out.warnings.setdefault(bid, []).append(
                    "Dentro do laço, cada volta grava de novo: sem [#valor], [#volta] ou uma {coluna} no nome, uma volta sobrescreve a outra."
                )
        cfg = nodes[lp.start].config
        kinds = {nodes[bid].type for bid in lp.body}
        if (
            (cfg.get("mode") or "each") == "each"
            and lp.body
            and kinds <= _SIMPLE
            and "transform.summarize" in kinds
        ):
            out.warnings.setdefault(lp.start, []).append(
                f"Dica: um Summarize agrupado por {cfg.get('column') or 'essa coluna'} faz o mesmo sem laço, e mais rápido."
            )


# ---------------------------------------------------------------- as voltas


def _constant(value: Any) -> ConstantValue:
    if isinstance(value, bool):
        return ConstantValue(type="text", value=str(value).lower())
    if isinstance(value, int | float):
        return ConstantValue(type="number", value=repr(value) if isinstance(value, float) else str(value))
    if isinstance(value, date):
        return ConstantValue(type="date", value=value.isoformat()[:10])
    return ConstantValue(type="text", value="" if value is None else str(value))


def _range(cfg: LoopStartConfig) -> list[Any]:
    limit = cfg.max_iterations + 1
    if cfg.unit == "number":
        try:
            a, b = float(cfg.start.replace(",", ".")), float(cfg.end.replace(",", "."))
        except ValueError as exc:
            raise ValueError(
                "No laço por faixa, 'De' e 'Até' precisam ser números (ou escolha passo em dias, meses…)."
            ) from exc
        values: list[Any] = []
        k = 0
        while a + k * cfg.step <= b + 1e-9 and len(values) < limit:
            v = a + k * cfg.step
            values.append(int(v) if float(v).is_integer() else round(v, 10))
            k += 1
        return values
    d1, d2 = parse_user_date(cfg.start), parse_user_date(cfg.end)
    if d1 is None or d2 is None:
        raise ValueError("No laço por datas, escreva 'De' e 'Até' como datas (01/01/2026).")
    step = int(cfg.step)
    every = {"day": f"{step}d", "week": f"{step}w", "month": f"{step}mo", "year": f"{step}y"}[cfg.unit]
    return pl.date_range(d1, d2, interval=every, eager=True).head(limit).to_list()


def plan(cfg: LoopStartConfig, table: pl.DataFrame) -> list[Any] | None:
    """Os valores de cada volta; None no modo Enquanto (para pela condição ou pelo limite)."""
    if cfg.mode == "while":
        return None
    if cfg.mode == "range":
        values = _range(cfg)
    elif cfg.values.strip():
        values = [v.strip() for v in re.split(r"[\n;]", cfg.values) if v.strip()]
    else:
        if cfg.column not in table.columns:
            raise ValueError("Escolha a coluna do laço (Para cada valor de…).")
        col = table.get_column(cfg.column)
        values = col.unique(maintain_order=True).to_list()
        if cfg.order == "asc":
            values = sorted(values, key=lambda v: (v is None, v))
    if len(values) > cfg.max_iterations:
        raise ValueError(
            f"O laço teria {len(values)} voltas, mais que o limite ({cfg.max_iterations}): aumente o limite no Início do loop."
        )
    return values


def iteration_table(cfg: LoopStartConfig, table: pl.DataFrame, value: Any) -> pl.DataFrame:
    """O que sai do Início em cada volta: só as linhas do valor, ou a tabela inteira."""
    if cfg.mode != "each" or cfg.rows == "all" or cfg.column not in table.columns:
        return table
    col = pl.col(cfg.column)
    if value is None:
        return table.filter(col.is_null())
    if cfg.values.strip():  # valores digitados: compara como texto
        return table.filter(col.cast(pl.String) == str(value))
    return table.filter(col == value)


def variables(value: Any, turn: int, total: int | None) -> dict[str, ConstantValue]:
    out = {"valor": _constant(value if value is not None or turn else None), "volta": _constant(turn)}
    out["total"] = _constant(total if total is not None else 0)
    return out


def combine(output: str, tables: list[tuple[int, Any, pl.DataFrame]], value_name: str) -> pl.DataFrame:
    """Empilha as voltas (com a coluna da volta e a do valor) ou fica com a última."""
    if not tables:
        return pl.DataFrame()
    if output != "stack":
        return tables[-1][2]
    parts = []
    for turn, value, df in tables:
        extra = [pl.lit(turn, dtype=pl.Int64).alias("volta")]
        if value_name and value_name not in df.columns:
            extra.append(pl.lit(value).alias(value_name))
        parts.append(df.with_columns(extra))
    return pl.concat(parts, how="diagonal_relaxed")
