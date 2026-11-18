"""Laço na aba SQL (spec 041, RF-4170): desenrola o laço antes de traduzir.

Cada volta vira uma cópia do corpo, com o Início trocado por um filtro do valor da volta e as variáveis
``[#valor]``, ``[#volta]`` e ``[#total]`` já trocadas; o Fim empilha as cópias (``UNION ALL``) com a coluna da volta,
como o motor. O que não dá para desenrolar fica sem tradução, com o motivo: Enquanto, Acumular, laço dentro de laço,
mais de 50 voltas, ou "para cada valor" antes de executar (os valores vêm dos dados).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

import polars as pl

from prodata.domain.workflow import Edge, Node, Workflow
from prodata.engine import constants as constants_engine
from prodata.engine import graph, loops
from prodata.engine.cache import ResultCache
from prodata.engine.sql.fragment import lit, q
from prodata.nodes.loop import LoopEndConfig, LoopStartConfig

MAX_TURNS = 50


def sql_literal(value: Any) -> str:
    if isinstance(value, date):
        return f"DATE '{value.isoformat()[:10]}'"
    return lit(value)


def _show(value: Any) -> str:
    text = "vazio" if value is None else str(value)
    return text if len(text) <= 24 else f"{text[:23]}…"


def _with(node: Node, key: str, value: dict[str, Any], **changes: Any) -> Node:
    return node.model_copy(update={"config": {**node.config, key: value}, **changes})


def _why_not(lp: loops.Loop, found: loops.Found, s_cfg: LoopStartConfig, e_cfg: LoopEndConfig) -> str | None:
    if any(n in found.problems for n in (lp.start, lp.end, *lp.body)):
        return "Corrija o desenho do laço para ver o SQL."
    if lp.inner or lp.depth > 1:
        return "Laço dentro de laço ainda não tem tradução para SQL."
    if s_cfg.mode == "while":
        return "O laço Enquanto depende do resultado de cada volta: não tem tradução para SQL."
    if e_cfg.output == "accumulate":
        return "Acumular passa o resultado de uma volta para a próxima: não tem tradução para SQL."
    return None


def _values(
    workflow: Workflow,
    lp: loops.Loop,
    s_cfg: LoopStartConfig,
    cache: ResultCache,
    fresh: Callable[[str], bool],
) -> tuple[list[Any] | None, str | None]:
    if s_cfg.mode == "each" and not s_cfg.values.strip():
        table = cache.table(workflow.id, lp.start, "out") if fresh(lp.start) else None
        if table is None:
            return (
                None,
                f"Execute o fluxo até o Fim do loop: a tradução usa os valores de {s_cfg.column or 'da coluna'}.",
            )
    else:
        table = pl.DataFrame()
    try:
        values = loops.plan(s_cfg, table)
    except ValueError as exc:
        return None, str(exc)
    if values is None:
        return None, "Este laço não tem tradução para SQL."
    if len(values) > MAX_TURNS:
        return None, f"O laço tem {len(values)} voltas; a tradução para SQL vai até {MAX_TURNS}."
    return values, None


def _where(s_cfg: LoopStartConfig, value: Any) -> str:
    if s_cfg.mode != "each" or s_cfg.rows == "all" or not s_cfg.column:
        return ""
    col = q(s_cfg.column)
    if value is None:
        return f"{col} IS NULL"
    if s_cfg.values.strip():
        return f"CAST({col} AS VARCHAR) = {lit(str(value))}"
    return f"{col} = {sql_literal(value)}"


class LoopCache:
    """O cache visto pela aba SQL: a cópia de uma caixa na volta k lê o resultado daquela volta."""

    def __init__(self, cache: ResultCache, places: dict[str, tuple[str, str]]) -> None:
        self.cache = cache
        self.places = places  # id da cópia -> (espaço de cache da volta, id original)

    def table(self, workflow_id: str, node_id: str, port: str) -> pl.DataFrame | None:
        where, original = self.places.get(node_id, (workflow_id, node_id))
        return self.cache.table(where, original, port)

    def get(self, workflow_id: str, node_id: str) -> Any:
        where, original = self.places.get(node_id, (workflow_id, node_id))
        return self.cache.get(where, original)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.cache, name)


def original_id(node_id: str) -> str:
    """A caixa de verdade por trás de uma cópia de volta (``soma__v3`` -> ``soma``)."""
    base, sep, turn = node_id.rpartition("__v")
    return base if sep and turn.isdigit() else node_id


def places(workflow_id: str, expanded: Workflow, original: Workflow) -> dict[str, tuple[str, str]]:
    """Onde está o resultado de cada cópia: no espaço de cache da volta, com o id original."""
    from prodata.engine.loop_run import namespace

    known = {n.id for n in original.nodes}
    found = loops.find(original, graph.topological_order(original))
    end_of = {b: lp.end for lp in found.loops.values() for b in (lp.start, *lp.body)}
    out = {}
    for n in expanded.nodes:
        base = original_id(n.id)
        if n.id not in known and base in end_of:
            out[n.id] = (namespace(workflow_id, end_of[base], int(n.id.rpartition("__v")[2])), base)
    return out


def expand(workflow: Workflow, cache: ResultCache, fresh: Callable[[str], bool]) -> Workflow:
    """O fluxo com cada laço desenrolado, ou marcado com o motivo de não ter tradução."""
    found = loops.find(workflow, graph.topological_order(workflow))
    if not found.loops:
        return workflow
    nodes = {n.id: n for n in workflow.nodes}
    edges = list(workflow.edges)
    for lp in found.loops.values():
        start, end = nodes[lp.start], nodes[lp.end]
        s_cfg = LoopStartConfig.model_validate(start.config)
        e_cfg = LoopEndConfig.model_validate(end.config)
        reason = _why_not(lp, found, s_cfg, e_cfg)
        values: list[Any] | None = None
        if reason is None:
            values, reason = _values(workflow, lp, s_cfg, cache, fresh)
        if reason is not None or values is None:
            nodes[lp.start] = _with(start, "sql_turn", {"reason": reason})
            nodes[lp.end] = _with(end, "sql_turns", {"reason": reason})
            continue
        edges = _unroll(lp, nodes, edges, s_cfg, e_cfg, values)
    return workflow.model_copy(update={"nodes": list(nodes.values()), "edges": edges})


def _unroll(
    lp: loops.Loop,
    nodes: dict[str, Node],
    edges: list[Edge],
    s_cfg: LoopStartConfig,
    e_cfg: LoopEndConfig,
    values: list[Any],
) -> list[Edge]:
    inside = {lp.start, *lp.body}
    start = nodes.pop(lp.start)
    body = [nodes.pop(b) for b in lp.body]
    total = len(values)
    kept = [e for e in edges if e.source not in inside and e.target not in inside and e.target != lp.end]
    turns = []
    for k, value in enumerate(values, start=1):

        def rid(node_id: str, k: int = k) -> str:
            return f"{node_id}__v{k}" if node_id in inside else node_id

        names = loops.variables(value, k, total)
        label = f"{s_cfg.column} = {_show(value)}" if s_cfg.mode == "each" else f"valor = {_show(value)}"
        turn = {"active": True, "turn": k, "where": _where(s_cfg, value), "label": label}
        nodes[rid(lp.start)] = _with(
            start, "sql_turn", turn, id=rid(lp.start), label=f"{start.label or 'Início do loop'} · volta {k}"
        )
        for b in body:
            config = constants_engine.fill_config(b.type, b.config, names)
            nodes[rid(b.id)] = b.model_copy(
                update={"id": rid(b.id), "label": f"{b.label or b.type} · {_show(value)}", "config": config}
            )
        for e in edges:
            if e.target in inside or (e.target == lp.end and e.source in inside):
                handle = f"t{k}" if e.target == lp.end else e.target_handle
                kept.append(
                    e.model_copy(
                        update={
                            "id": f"{e.id}__v{k}",
                            "source": rid(e.source),
                            "target": rid(e.target),
                            "target_handle": handle,
                        }
                    )
                )
        turns.append({"port": f"t{k}", "turn": k, "literal": sql_literal(value)})
    value_column = (
        s_cfg.column
        if s_cfg.mode == "each" and not s_cfg.values.strip()
        else ("valor" if s_cfg.mode == "range" else "")
    )
    end = nodes[lp.end]
    nodes[lp.end] = _with(
        end, "sql_turns", {"output": e_cfg.output, "value_column": value_column, "turns": turns}
    )
    return kept
