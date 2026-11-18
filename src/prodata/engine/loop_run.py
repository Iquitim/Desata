"""Execução de um laço (spec 041): as voltas do corpo, cada uma no seu espaço de cache, e o que sai no Fim."""

from __future__ import annotations

import hashlib
import json
import time
from typing import TYPE_CHECKING, Any

import polars as pl

from prodata.domain.execution import NodeResult
from prodata.domain.workflow import Node, Workflow
from prodata.engine import constants as constants_engine
from prodata.engine import formula, loops
from prodata.engine.cache import NodeEntry
from prodata.nodes import REGISTRY
from prodata.nodes.loop import LoopEndConfig, LoopStartConfig

if TYPE_CHECKING:
    from prodata.engine.runner import WorkflowRunner

OK = ("executed", "cached")


def namespace(workflow_id: str, end: str, turn: int) -> str:
    """Espaço de cache de uma volta: é por ele que a aba Resultado mostra uma volta escolhida."""
    return f"{workflow_id}~{end}~{turn}"


def _show(value: Any) -> str:
    text = "vazio" if value is None else str(value)
    return text if len(text) <= 40 else f"{text[:39]}…"


def _hash(*parts: Any) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:20]


class LoopRun:
    """Roda os laços de um fluxo para o executor. Um objeto por execução."""

    def __init__(
        self,
        runner: WorkflowRunner,
        workflow: Workflow,
        found: loops.Found,
        hold: bool,
        progress: dict[str, Any],
        resolution: constants_engine.Resolution,
    ) -> None:
        self.runner = runner
        self.workflow = workflow
        self.found = found
        self.hold = hold
        self.progress = progress
        self.resolution = resolution

    # ------------------------------------------------------------ o laço

    def run(
        self,
        workflow: Workflow,
        loop: loops.Loop,
        results: dict[str, NodeResult],
        fingerprints: dict[str, str],
    ) -> tuple[NodeResult, dict[str, NodeResult]]:
        """Resultado do Fim e das caixas do corpo (as da última volta)."""
        blocked = self._blocked(loop, results)
        if blocked is not None:
            return blocked
        start, end = workflow.node(loop.start), workflow.node(loop.end)
        s_cfg = LoopStartConfig.model_validate(start.config)
        e_cfg = LoopEndConfig.model_validate(end.config)
        base_entry = self.runner.cache.get(workflow.id, loop.start)
        if base_entry is None:
            return NodeResult(status="skipped", error="O Início do loop não foi executado."), {}
        base = base_entry.tables["out"]
        try:
            values = loops.plan(s_cfg, base)
        except ValueError as exc:
            return NodeResult(status="error", error=str(exc)), {}
        if values is None and not e_cfg.expression.strip():
            return NodeResult(
                status="error", error="No modo Enquanto, escreva no Fim do loop a condição para continuar."
            ), {}
        return self._turns(workflow, loop, s_cfg, e_cfg, base, values, results, fingerprints)

    def _blocked(
        self, loop: loops.Loop, results: dict[str, NodeResult]
    ) -> tuple[NodeResult, dict[str, NodeResult]] | None:
        problems = self.found.problems
        bad = [n for n in (loop.start, loop.end, *loop.body) if n in problems]
        if bad:
            body = {
                b: NodeResult(status="error", error=problems[b])
                if b in problems
                else NodeResult(
                    status="skipped", error="O laço tem um problema no desenho: veja a caixa marcada."
                )
                for b in loop.body
            }
            message = problems.get(loop.end) or "Corrija o laço: veja a caixa marcada em vermelho."
            return NodeResult(status="error", error=message), body
        start = results.get(loop.start)
        if start is None or start.status not in OK:
            skipped = NodeResult(status="skipped", error="O Início do loop não foi executado.")
            return skipped, dict.fromkeys(loop.body, skipped)
        return None

    def _turns(
        self,
        workflow: Workflow,
        loop: loops.Loop,
        s_cfg: LoopStartConfig,
        e_cfg: LoopEndConfig,
        base: pl.DataFrame,
        values: list[Any] | None,
        results: dict[str, NodeResult],
        fingerprints: dict[str, str],
    ) -> tuple[NodeResult, dict[str, NodeResult]]:
        started = time.perf_counter()
        total = len(values) if values is not None else None
        collected: list[tuple[int, Any, pl.DataFrame]] = []
        times: list[float] = []
        prints: list[str] = []
        body: dict[str, NodeResult] = {}
        current, seed, warning = base, fingerprints.get(loop.start, ""), None
        turn = 0
        while values is None or turn < len(values):
            turn += 1
            if values is None and turn > s_cfg.max_iterations:
                warning = f"Parou no limite de {s_cfg.max_iterations} voltas: a condição ainda valia."
                break
            if self.progress.get("cancel"):
                stop = NodeResult(
                    status="skipped",
                    annotation="Interrompido",
                    error=f"Execução interrompida na volta {turn}.",
                    extra={"stopped": True},
                )
                return stop, body
            value = values[turn - 1] if values is not None else turn
            self.progress["detail"] = f"volta {turn} de {total}" if total else f"volta {turn}"
            source = current if e_cfg.output == "accumulate" else base
            table = loops.iteration_table(s_cfg, source, value)
            t0 = time.perf_counter()
            out, local, error, seed = self._turn(
                workflow, loop, turn, value, total, table, seed, results, fingerprints
            )
            body = {
                b: local[b] for b in loop.body if b in local
            }  # só o corpo: o Início e os de fora têm o resultado deles
            times.append(round((time.perf_counter() - t0) * 1000, 1))
            if error or out is None:
                return NodeResult(status="error", error=f"Volta {turn} ({_show(value)}): {error}"), body
            prints.append(seed)
            collected = [*collected, (turn, value, out)] if e_cfg.output == "stack" else [(turn, value, out)]
            current = out
            if values is None and not self._keep_going(e_cfg, out, value, turn):
                break
        value_name = (
            s_cfg.column
            if s_cfg.mode == "each" and not s_cfg.values.strip()
            else ("valor" if s_cfg.mode == "range" else "")
        )
        final = loops.combine(e_cfg.output, collected, value_name)
        return self._finish(
            workflow,
            loop,
            final,
            turn - (1 if warning else 0),
            times,
            prints,
            warning,
            started,
            body,
            fingerprints,
        )

    @staticmethod
    def _keep_going(e_cfg: LoopEndConfig, out: pl.DataFrame, value: Any, turn: int) -> bool:
        expression = constants_engine.fill_expression(e_cfg.expression, loops.variables(value, turn, None))
        return bool(out.height) and bool(formula.evaluate_mask(out, expression).any())

    def _finish(
        self,
        workflow: Workflow,
        loop: loops.Loop,
        final: pl.DataFrame,
        turns: int,
        times: list[float],
        prints: list[str],
        warning: str | None,
        started: float,
        body: dict[str, NodeResult],
        fingerprints: dict[str, str],
    ) -> tuple[NodeResult, dict[str, NodeResult]]:
        from prodata.engine.runner import _summarize

        cache = self.runner.cache
        # As caixas do corpo mostram a última volta; as outras ficam no espaço de cada uma.
        last = namespace(workflow.id, loop.end, turns)
        for b in loop.body:
            entry = cache.get(last, b)
            if entry is not None:
                cache.put(workflow.id, b, entry, persist=False)
            if b in body:
                body[b] = body[b].model_copy(
                    update={"extra": {**body[b].extra, "loop": {"end": loop.end, "turns": turns}}}
                )
        extra: dict[str, Any] = {"loop": {"end": loop.end, "turns": turns, "times": times[: loops.MAX_TIMES]}}
        if warning:
            extra["warnings"] = [warning]
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        fp = _hash(prints, workflow.node(loop.end).config)
        before = cache.get(workflow.id, loop.end)
        status = (
            "cached" if before is not None and before.fingerprint == fp else "executed"
        )  # nada mudou nas voltas
        entry = NodeEntry(fingerprint=fp, tables={"out": final}, models={}, extra=extra, elapsed_ms=elapsed)
        cache.put(workflow.id, loop.end, entry)
        fingerprints[loop.end] = fp
        annotation = f"{turns} {'volta' if turns == 1 else 'voltas'}"
        return NodeResult(
            status=status,
            elapsed_ms=elapsed,
            anchors=_summarize(entry),
            annotation=annotation,
            extra=extra,
        ), body

    # ------------------------------------------------------------ uma volta

    def _turn(
        self,
        workflow: Workflow,
        loop: loops.Loop,
        turn: int,
        value: Any,
        total: int | None,
        table: pl.DataFrame,
        seed: str,
        results: dict[str, NodeResult],
        fingerprints: dict[str, str],
    ) -> tuple[pl.DataFrame | None, dict[str, NodeResult], str | None, str]:
        from prodata.engine.runner import _summarize

        ns = namespace(workflow.id, loop.end, turn)
        names = loops.variables(value, turn, total)
        inside = set(loop.body)  # só as caixas do corpo levam as variáveis; as de fora não mudam
        iteration = workflow.model_copy(
            update={
                "id": ns,
                "nodes": [self._fill(n, names) if n.id in inside else n for n in workflow.nodes],
            }
        )
        local, prints = self._outside_parents(workflow, ns, loop, results, fingerprints)
        start_fp = _hash(seed, turn, value)
        entry = NodeEntry(fingerprint=start_fp, tables={"out": table}, models={}, extra={}, elapsed_ms=0)
        self.runner.cache.put(ns, loop.start, entry, persist=False)
        local[loop.start] = NodeResult(status="executed", anchors=_summarize(entry))
        prints[loop.start] = start_fp
        inner_members = {
            m for e in loop.inner for m in self.found.loops[e].body
        }  # o Início de dentro roda normal
        for b in loop.body:
            if b in inner_members:
                continue
            node = iteration.node(b)
            if b in self.found.loops:  # laço de dentro
                res, sub = self.run(iteration, self.found.loops[b], local, prints)
                local.update(sub)
            else:
                res = self.runner._run_node(
                    iteration, node, REGISTRY.get(node.type), local, prints, self.hold, None, self.resolution
                )
            local[b] = res
            if res.status not in OK:
                name = node.label or (REGISTRY[node.type].name if node.type in REGISTRY else node.type)
                return None, local, f"{name}: {res.error or 'não executou'}", seed
        edge = next((e for e in workflow.edges if e.target == loop.end), None)
        if edge is None:
            return None, local, "Ligue a última caixa do laço no Fim do loop.", seed
        got = self.runner.cache.get(ns, edge.source)
        if got is None or edge.source_handle not in got.tables:
            return None, local, "O resultado da volta não chegou ao Fim do loop.", seed
        return got.tables[edge.source_handle], local, None, prints.get(edge.source, seed)

    def _outside_parents(
        self,
        workflow: Workflow,
        ns: str,
        loop: loops.Loop,
        results: dict[str, NodeResult],
        fingerprints: dict[str, str],
    ) -> tuple[dict[str, NodeResult], dict[str, str]]:
        """Caixas de fora que alimentam o corpo: o mesmo resultado em todas as voltas."""
        inside = set(loop.body) | {loop.start}
        local: dict[str, NodeResult] = {}
        prints: dict[str, str] = {}
        for edge in workflow.edges:
            if edge.target not in inside or edge.source in inside or edge.source in local:
                continue
            if edge.source in results:
                local[edge.source] = results[edge.source]
                prints[edge.source] = fingerprints.get(edge.source, "")
                entry = self.runner.cache.get(workflow.id, edge.source)
                if entry is not None:
                    self.runner.cache.put(ns, edge.source, entry, persist=False)
        return local, prints

    @staticmethod
    def _fill(node: Node, names: dict[str, Any]) -> Node:
        refs = constants_engine.node_refs(node.type, node.config) & set(loops.LOOP_NAMES)
        if not refs:
            return node
        values = {k: names[k] for k in refs}
        config = constants_engine.fill_config(node.type, node.config, values)
        used = dict(config.get(constants_engine.USED_KEY) or {})
        used.update({k: f"laço:{v.type}:{v.value}" for k, v in values.items()})
        config[constants_engine.USED_KEY] = used
        return node.model_copy(update={"config": config})
