"""Execução de workflows: validação, ordem topológica, cache incremental e propagação de falhas."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl
from pydantic import ValidationError

from prodata.connectors.api_model import source_api_id
from prodata.connectors.api_store import ApiStore
from prodata.connectors.queries import QueryStore, source_query_id
from prodata.connectors.store import ConnectionStore
from prodata.domain.execution import (
    AnchorSummary,
    ColumnSummary,
    EdgeTelemetry,
    ExecutionReport,
    LogEntry,
    NodeResult,
)
from prodata.domain.workflow import Node, Workflow
from prodata.engine import constants as constants_engine
from prodata.engine import errors_pt, graph, loops, subflow
from prodata.engine import schema_drift as drift
from prodata.engine.cache import FrozenEntry, NodeEntry, ResultCache
from prodata.engine.loop_run import LoopRun
from prodata.engine.profiling import simple_type
from prodata.errors import NotFoundError, ProdataError
from prodata.ingestion.datasets import DatasetStore
from prodata.nodes import REGISTRY, NodeContext, ToolSpec
from prodata.nodes.io import OutputDataConfig, export_path
from prodata.services.constants import ConstantStore

log = logging.getLogger(__name__)
# Today() numa fórmula: o resultado muda a cada dia, então a data entra na impressão digital da caixa.
_TODAY = re.compile(r"\btoday\s*\(", re.IGNORECASE)
# Parar (spec 041): o que ainda não executou fica assim.
STOPPED = NodeResult(
    status="skipped",
    annotation="Interrompido",
    error="Execução interrompida: clique em Executar para continuar.",
    extra={"stopped": True},
)


class SkippedError(Exception):
    """Falha de um nó com mensagem para o usuário e, opcionalmente, o campo afetado."""

    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field


@dataclass
class _Inputs:
    tables: dict[str, pl.DataFrame]
    models: dict[str, dict[str, Any]]
    fingerprints: dict[str, str]


def _summarize(entry: NodeEntry) -> dict[str, AnchorSummary]:
    if entry.summary is not None:
        cached: dict[str, AnchorSummary] = entry.summary
        return cached
    anchors: dict[str, AnchorSummary] = {}
    for port, df in entry.tables.items():
        nulls = df.null_count().row(0) if df.width else ()
        anchors[port] = AnchorSummary(
            kind="data",
            row_count=df.height,
            col_count=df.width,
            columns=[
                ColumnSummary(
                    name=name,
                    type=simple_type(dtype),
                    ok_pct=round(100 - (n / df.height * 100), 1) if df.height else 100.0,
                )
                for (name, dtype), n in zip(df.schema.items(), nulls, strict=True)
            ],
        )
    for port, bundle in entry.models.items():
        anchors[port] = AnchorSummary(
            kind="model", row_count=1, col_count=len(bundle["feature_columns"]), metrics=bundle["metrics"]
        )
    entry.summary = anchors
    return anchors


_validation_message = errors_pt.validation_message  # spec 046: tipos de erro do Pydantic em português


class WorkflowRunner:
    def __init__(
        self,
        cache: ResultCache,
        datasets: DatasetStore,
        exports_dir: Path,
        connections: ConnectionStore | None = None,
        queries: QueryStore | None = None,
        apis: ApiStore | None = None,
        constants: ConstantStore | None = None,
        jira: Any = None,
        *,
        state_dir: Path | None = None,
        workflows: Any = None,
        secret_key: Any = None,
        guard: Any = None,
    ) -> None:
        self.jira = jira
        # Spec 033: estado das caixas entre execuções, biblioteca (subfluxos) e chave do Mask.
        self.state_dir = state_dir
        self.workflows = workflows
        self.secret_key = secret_key
        self.guard = guard
        self.chain: tuple[str, ...] = ()
        self.injected: dict[str, tuple[pl.DataFrame, str]] | None = None
        self.constants = constants
        self.cache = cache
        self.datasets = datasets
        self.exports_dir = exports_dir
        self.connections = connections
        self.queries = queries
        self.apis = apis
        self._lock = threading.Lock()
        # Andamento das execuções em curso, por fluxo (spec 018): a interface consulta para iluminar a caixa da vez.
        self._progress: dict[str, dict[str, Any]] = {}
        # Assinatura de cada caixa na última execução: diz se o resultado guardado vale para o fluxo atual (spec 020).
        self._ran: dict[str, dict[str, str]] = {}

    def run(
        self,
        workflow: Workflow,
        target_node_id: str | None = None,
        *,
        hold_exports: bool = False,
        unattended: bool = False,
    ) -> ExecutionReport:
        """Executa o fluxo. ``hold_exports``: execução automática (ao abrir o fluxo, trocar de aba): exportações
        em "Perguntar" cujo arquivo já existe esperam o usuário clicar em Executar (spec 017).
        ``unattended``: ninguém olhando (agendada, linha de comando): as fontes leem primeiro e, se o formato de
        uma delas mudou de um jeito perigoso, nada mais executa nem grava (spec 046, RF-4607)."""
        started = time.perf_counter()
        order = graph.topological_order(workflow)
        found = loops.find(workflow, order)  # laços (spec 041)
        resolution = self.resolve(workflow, found.members)
        workflow = resolution.workflow
        if target_node_id:
            if target_node_id not in order:
                raise graph.GraphError(f"Caixa não encontrada no fluxo: {target_node_id}")
            # Executar até uma caixa de dentro do laço roda o laço inteiro (até o Fim de fora).
            for end, loop in found.loops.items():
                if loop.depth == 1 and target_node_id in {loop.start, *loop.body}:
                    target_node_id = end
            keep = graph.ancestors(workflow, target_node_id) | {target_node_id}
            order = [n for n in order if n in keep]
        if unattended:  # fontes não têm entradas: lê-las antes de tudo continua respeitando a ordem do grafo
            sources = [n for n in order if workflow.node(n).type in drift.SOURCE_TYPES]
            order = [*sources, *(n for n in order if n not in sources)]

        progress: dict[str, Any] = {"order": order, "running": None, "done": {}}
        self._progress[workflow.id] = progress
        try:
            return self._run_locked(
                workflow, order, progress, started, hold_exports, resolution, found, unattended=unattended
            )
        finally:
            self._progress.pop(workflow.id, None)

    def api_texts(self, node: Node) -> list[str]:
        """Textos da API que a caixa lê, onde uma constante pode aparecer: endereço e parâmetros fixos."""
        dataset = str(node.config.get("dataset") or "")
        api_id = source_api_id(dataset) if node.type == "io.input_data" else node.config.get("source")
        if self.apis is None or not api_id or node.type not in ("io.input_data", "io.api_loop"):
            return []
        try:
            api = self.apis.get(str(api_id))
        except NotFoundError, ProdataError:
            return []
        return [
            api.url,
            *(p.value for p in api.params if not p.secret),
            *(h.value for h in api.headers if not h.secret),
        ]

    def resolve(
        self, workflow: Workflow, loop_members: set[str] | None = None
    ) -> constants_engine.Resolution:
        """O fluxo com as constantes trocadas pelo valor (spec 028); no laço, as variáveis ficam para cada volta."""
        shared = self.constants.all() if self.constants else {}
        return constants_engine.resolve(workflow, shared, self.api_texts, loop_members=loop_members)

    def cancel(self, workflow_id: str) -> bool:
        """Pede para parar a execução em curso (spec 041): confere antes de cada caixa e a cada volta de um laço.

        A caixa que já está rodando termina; as seguintes ficam como "não executado".
        """
        current = self._progress.get(workflow_id)
        if current is None:
            return False
        current["cancel"] = True
        return True

    def snapshot(self, workflow: Workflow) -> Workflow:
        """Grava no fluxo o valor das constantes compartilhadas que ele usa (RF-2850)."""
        shared = self.constants.all() if self.constants else {}
        saved = constants_engine.snapshot(workflow, shared, self.api_texts)
        return workflow.model_copy(update={"shared_constants": saved})

    def _freshness(self, workflow: Workflow, node_id: str) -> str:
        return f"{graph.upstream_signature(workflow, node_id)}:{self._sources_signature(workflow, node_id)}"

    def is_fresh(self, workflow: Workflow, node_id: str) -> bool:
        """O resultado guardado da caixa ainda corresponde à configuração e aos arquivos atuais?"""
        ran = self._ran.get(workflow.id, {}).get(node_id)
        return ran is not None and ran == self._freshness(self.resolve(workflow).workflow, node_id)

    def progress(self, workflow_id: str) -> dict[str, Any]:
        """Caixa em execução e caixas já concluídas da execução em curso (vazio se nada roda)."""
        current = self._progress.get(workflow_id)
        if current is None:
            return {"running": None, "done": {}, "order": [], "active": False}
        return {
            "running": current["running"],
            "done": dict(current["done"]),
            "detail": current.get("detail"),
            "order": list(current["order"]),
            "active": True,
        }

    def _run_locked(
        self,
        workflow: Workflow,
        order: list[str],
        progress: dict[str, Any],
        started: float,
        hold_exports: bool,
        resolution: constants_engine.Resolution,
        found: loops.Found | None = None,
        *,
        unattended: bool = False,
    ) -> ExecutionReport:
        found = found or loops.Found()
        looper = LoopRun(self, workflow, found, hold_exports, progress, resolution)
        stop_reason: str | None = None  # spec 046: formato perigoso numa execução sem ninguém olhando
        # O corpo dos laços roda dentro do Fim de fora; aqui fica de fora.
        inside = found.members - {e for e, loop in found.loops.items() if loop.depth == 1}
        results: dict[str, NodeResult] = {}
        fingerprints: dict[str, str] = {}
        widgets: list[dict[str, Any]] = []
        logs: list[LogEntry] = []

        with self._lock:
            self.cache.prune(workflow.id, {n.id for n in workflow.nodes})
            frozen, signatures = self._valid_cache_points(workflow, order)
            needed = graph.needed_nodes(workflow, order, set(frozen)) if frozen else set(order)
            for node_id in order:
                if node_id in inside:
                    continue
                node = workflow.node(node_id)
                spec = REGISTRY.get(node.type)
                waiting = self._waiting_export(node) if hold_exports else None
                progress["running"] = node_id
                progress["detail"] = None
                if progress.get("cancel") or stop_reason:  # Parar (spec 041) ou formato perigoso (spec 046)
                    result = self._halted(stop_reason)
                elif node_id not in needed:
                    result = self._held_result(workflow, node, spec)
                elif waiting:
                    result = NodeResult(
                        status="skipped",
                        annotation="Arquivo já existe: clique em Executar",
                        error=f"{waiting} já existe. Clique em Executar para escolher entre substituir ou criar outro.",
                        extra={"export_waiting": waiting},
                    )
                elif node_id in frozen:
                    result = self._frozen_result(workflow, node, spec, frozen[node_id], fingerprints)
                elif node_id in found.loops:
                    result, body = looper.run(workflow, found.loops[node_id], results, fingerprints)
                    self._record_body(workflow, found, body, results, progress, logs)
                elif node_id in found.problems:
                    result = NodeResult(status="error", error=found.problems[node_id])
                else:
                    # "Parar se o formato da saída mudar" (spec 046, RF-4608): o Output nem executa
                    result = self._output_check(workflow, node, results) or self._run_node(
                        workflow, node, spec, results, fingerprints, hold_exports, progress, resolution
                    )
                    if node.type in drift.SOURCE_TYPES | drift.OUTPUT_TYPES:
                        stop_reason = self._schema_result(workflow, node, spec, result, results, unattended)
                    if node_id in signatures and result.status in ("executed", "cached"):
                        entry = self.cache.get(workflow.id, node_id)
                        if entry is not None:
                            saved = self.cache.freeze(workflow.id, node_id, entry, signatures[node_id])
                            result.extra = {
                                **result.extra,
                                "cache_point": "saved",
                                "frozen_at": saved.frozen_at,
                            }
                results[node_id] = result
                progress["done"][node_id] = result.status
                if result.status in ("executed", "cached"):
                    self._ran.setdefault(workflow.id, {})[node_id] = self._freshness(workflow, node_id)
                else:
                    self._ran.get(workflow.id, {}).pop(node_id, None)
                name = node.label or (spec.name if spec else node.type)
                if node_id in found.warnings:
                    result.extra = {
                        **result.extra,
                        "warnings": [*result.extra.get("warnings", []), *found.warnings[node_id]],
                    }
                logs.append(self._log_entry(workflow, node_id, result))
                if widget := result.extra.get("bi_widget"):
                    widgets.append({**widget, "node_id": node_id, "node_label": name})

        telemetry = {
            e.id: EdgeTelemetry(kind=anchor.kind, row_count=anchor.row_count)
            for e in workflow.edges
            if (src := results.get(e.source)) and (anchor := src.anchors.get(e.source_handle))
        }
        return ExecutionReport(
            workflow_id=workflow.id,
            total_elapsed_ms=round((time.perf_counter() - started) * 1000, 1),
            node_results=results,
            edge_telemetry=telemetry,
            bi_widgets=widgets,
            logs=logs,
        )

    # ------------------------------------------------------------------ formato das fontes e saídas (spec 046)

    def _error_result(
        self, exc: BaseException, inputs: _Inputs, annotation: str, started: float
    ) -> NodeResult:
        """Erro em português, com o texto técnico guardado e as colunas parecidas (spec 046, RF-4621..4623)."""
        columns = list(dict.fromkeys(c for df in inputs.tables.values() for c in df.columns))
        friendly = errors_pt.translate(exc, columns)
        extra: dict[str, Any] = {}
        if friendly.technical:
            extra["error_detail"] = friendly.technical
            log.info("Erro traduzido; texto original: %s", friendly.technical)
        if friendly.hint:
            extra["error_hint"] = friendly.hint
        return NodeResult(
            status="error",
            error=friendly.message,
            annotation=annotation,
            elapsed_ms=self._ms(started),
            extra=extra,
        )

    @staticmethod
    def _halted(stop_reason: str | None) -> NodeResult:
        if not stop_reason:
            return STOPPED.model_copy()
        return NodeResult(
            status="skipped", annotation="Não executado", error=f"Execução parada: {stop_reason}"
        )

    @staticmethod
    def _incoming_schema(
        workflow: Workflow, node: Node, results: dict[str, NodeResult]
    ) -> dict[str, list[drift.ColumnSpec]]:
        """O que chega em cada entrada da caixa, pelo resumo do resultado das caixas de antes."""
        out: dict[str, list[drift.ColumnSpec]] = {}
        for e in workflow.edges:
            src = results.get(e.source) if e.target == node.id else None
            anchor = src.anchors.get(e.source_handle) if src else None
            if anchor is not None and anchor.kind == "data":
                out[e.target_handle] = [drift.ColumnSpec(name=c.name, type=c.type) for c in anchor.columns]
        return out

    def _output_check(
        self, workflow: Workflow, node: Node, results: dict[str, NodeResult]
    ) -> NodeResult | None:
        """Output com "Parar se o formato da saída mudar" e formato diferente do gravado: não executa (RF-4608)."""
        if node.type not in drift.OUTPUT_TYPES or not node.config.get("stop_on_schema_change"):
            return None
        current = self._incoming_schema(workflow, node, results)
        change, sentence = drift.output_change(workflow.schemas.get(node.id), current)
        if change is None:
            return None
        return NodeResult(
            status="error",
            annotation="Formato mudou: nada gravado",
            error=f"{sentence} Nada foi gravado, porque a caixa está configurada para parar nesse caso.",
            extra={"schema": {p: [c.model_dump() for c in cols] for p, cols in current.items()},
                   "schema_change": change},
        )  # fmt: skip

    def _schema_result(
        self,
        workflow: Workflow,
        node: Node,
        spec: ToolSpec | None,
        result: NodeResult,
        results: dict[str, NodeResult],
        unattended: bool,
    ) -> str | None:
        """Junta ao resultado o formato atual e a diferença do lembrado. Sem ninguém olhando, devolve o motivo
        para parar tudo antes das saídas (RF-4607)."""
        if result.status not in ("executed", "cached"):
            return None
        if node.type in drift.OUTPUT_TYPES:
            current = self._incoming_schema(workflow, node, results)
            change, sentence = drift.output_change(workflow.schemas.get(node.id), current)
            extra: dict[str, Any] = {
                "schema": {p: [c.model_dump() for c in cols] for p, cols in current.items()}
            }
            if change:
                extra["schema_change"] = change
                extra["warnings"] = [*result.extra.get("warnings", []), sentence]
            result.extra = {**result.extra, **extra}
            return None
        entry = self.cache.get(workflow.id, node.id)
        frame = entry.tables.get("out") if entry is not None else None
        if frame is None:
            return None
        result.extra = {**result.extra, **drift.source_extra(workflow, node, frame)}
        change = result.extra.get("schema_change")
        if not unattended or not change:
            return None
        name = result.annotation or node.label or (spec.name if spec else node.type)
        reason = drift.unattended_stop(change, str(node.config.get("on_new_columns") or "seguir"), name)
        if reason:
            result.status = "error"
            result.error = reason
        return reason

    # ------------------------------------------------------------------ pontos de cache (spec 012)

    def _valid_cache_points(
        self, workflow: Workflow, order: list[str]
    ) -> tuple[dict[str, FrozenEntry], dict[str, str]]:
        """Pontos com instantâneo ainda válido e a assinatura atual de todos os pontos."""
        points = [n for n in workflow.nodes if n.cache_point and not n.disabled]
        self.cache.prune_frozen(workflow.id, {n.id for n in points})
        signatures = {
            n.id: f"{graph.upstream_signature(workflow, n.id)}:{self._sources_signature(workflow, n.id)}"
            for n in points
            if n.id in order
        }
        frozen: dict[str, FrozenEntry] = {}
        for node_id, signature in signatures.items():
            snapshot = self.cache.frozen(workflow.id, node_id)
            if (
                snapshot is not None
                and snapshot.signature == signature
                and not _expired(snapshot, workflow.node(node_id).cache_refresh)
            ):
                frozen[node_id] = snapshot
            elif snapshot is not None:
                self.cache.unfreeze(workflow.id, node_id)  # algo antes do ponto mudou, ou o prazo venceu
        return frozen, signatures

    def _waiting_export(self, node: Node) -> str | None:
        """Nome do arquivo, se for uma exportação em "Perguntar" que encontraria o arquivo já existente."""
        if node.type != "io.output_data" or node.disabled:
            return None
        try:
            cfg = OutputDataConfig.model_validate(node.config)
            path = export_path(self.exports_dir, cfg)
        except ValidationError, ProdataError:
            return None
        return path.name if cfg.if_exists == "ask" and path.exists() else None

    def _sources_signature(self, workflow: Workflow, node_id: str) -> str:
        """Data e tamanho dos arquivos de origem antes do ponto (spec 017): um arquivo atualizado
        invalida o cache. Fontes de banco não aparecem aqui; para elas existe a renovação por prazo."""
        parts = []
        for upstream in sorted(graph.ancestors(workflow, node_id)):
            node = workflow.node(upstream)
            dataset = str(node.config.get("dataset") or "")
            external = (
                source_query_id(dataset) is not None
                or source_api_id(dataset) is not None
                or dataset.startswith("jira:")
            )
            if node.type != "io.input_data" or not dataset or external:
                continue
            try:
                parts.append(f"{dataset}={self.datasets.signature(dataset)}")
            except NotFoundError:
                parts.append(f"{dataset}=sumiu")
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:12]

    def _frozen_result(
        self,
        workflow: Workflow,
        node: Node,
        spec: ToolSpec | None,
        snapshot: FrozenEntry,
        fingerprints: dict[str, str],
    ) -> NodeResult:
        self.cache.put(workflow.id, node.id, snapshot.entry, persist=False)
        fingerprints[node.id] = f"frozen:{snapshot.signature}"
        return NodeResult(
            status="cached",
            elapsed_ms=snapshot.entry.elapsed_ms,
            anchors=_summarize(snapshot.entry),
            annotation=self._annotation(node, spec),
            extra={**snapshot.entry.extra, "cache_point": "frozen", "frozen_at": snapshot.frozen_at},
        )

    def _held_result(self, workflow: Workflow, node: Node, spec: ToolSpec | None) -> NodeResult:
        """Caixa antes de um ponto de cache: não executa. Mostra o último resultado, se houver."""
        entry = self.cache.get(workflow.id, node.id)
        annotation = self._annotation(node, spec)
        if entry is not None:
            return NodeResult(
                status="cached", anchors=_summarize(entry), annotation=annotation, extra={"held": True}
            )
        return NodeResult(
            status="skipped",
            annotation=annotation,
            error="Em cache: o ponto de cache adiante já tem o resultado, esta caixa não precisou executar.",
            extra={"held": True},
        )

    @staticmethod
    def _annotation(node: Node, spec: ToolSpec | None) -> str:
        if spec is None:
            return ""
        try:
            return spec.annotation(spec.config.model_validate(node.config))
        except ValidationError:
            return ""

    # ------------------------------------------------------------------ nó a nó

    def _run_node(
        self,
        workflow: Workflow,
        node: Node,
        spec: ToolSpec | None,
        results: dict[str, NodeResult],
        fingerprints: dict[str, str],
        hold: bool = False,
        progress: dict[str, Any] | None = None,
        resolution: constants_engine.Resolution | None = None,
    ) -> NodeResult:
        if resolution is not None and node.id in resolution.problems and not node.disabled:
            return NodeResult(status="error", error=resolution.problems[node.id])
        result = self._run_node_inner(workflow, node, spec, results, fingerprints, hold, progress, resolution)
        if resolution is not None and (notes := resolution.warnings.get(node.id)):
            result.extra = {**result.extra, "warnings": [*result.extra.get("warnings", []), *notes]}
        return result

    def _run_node_inner(
        self,
        workflow: Workflow,
        node: Node,
        spec: ToolSpec | None,
        results: dict[str, NodeResult],
        fingerprints: dict[str, str],
        hold: bool,
        progress: dict[str, Any] | None,
        resolution: constants_engine.Resolution | None,
    ) -> NodeResult:
        if spec is None:
            return NodeResult(status="error", error=f"Ferramenta desconhecida: {node.type}")
        if node.disabled:
            self.cache.drop(workflow.id, node.id)
            return NodeResult(status="disabled")

        try:
            cfg = spec.config.model_validate(node.config)
        except ValidationError as exc:
            message, field = _validation_message(exc)
            return NodeResult(status="error", error=message, error_field=field)
        annotation = spec.annotation(cfg)

        try:
            inputs = self._gather_inputs(workflow, node, spec, results, fingerprints)
        except SkippedError as skip:
            return NodeResult(status="skipped", error=skip.message, annotation=annotation)

        ctx = NodeContext(
            inputs.tables,
            inputs.models,
            self.datasets,
            self.exports_dir,
            self.connections,
            self.queries,
            self.apis,
            constants=resolution.values.get(node.id, {}) if resolution else {},
            jira=self.jira,
            workflow_id=workflow.id,
            node_id=node.id,
            state_root=self.state_dir,
            hold=hold,
            input_fingerprints=inputs.fingerprints,
            injected=self.injected,
            secret_key=self.secret_key,
            samples=workflow.samples,  # spec 040: só valem quando a fonte não está neste computador
        )
        ctx.run_subflow = lambda child: subflow.run(self, workflow, node, child, ctx)
        ctx.subflow_signature = lambda child: subflow.signature(self, child)
        if progress is not None:
            ctx.report = lambda text: progress.__setitem__("detail", text)
        started = time.perf_counter()
        try:
            fp = self._fingerprint(node, spec, cfg, ctx, inputs)
            cached = self.cache.get(workflow.id, node.id)
            if cached and cached.fingerprint == fp and not spec.side_effect:
                fingerprints[node.id] = fp
                return NodeResult(
                    status="cached",
                    elapsed_ms=cached.elapsed_ms,
                    anchors=_summarize(cached),
                    annotation=annotation,
                    extra=cached.extra,
                )
            if hold and spec.only_on_request and (reason := spec.only_on_request(ctx, cfg)):
                return NodeResult(
                    status="skipped",
                    annotation="Clique em Executar",
                    error=reason,
                    extra={"api_waiting": True},
                )
            output = spec.run(ctx, cfg)
        except (ProdataError, ValueError, KeyError, pl.exceptions.PolarsError) as exc:
            self.cache.drop(workflow.id, node.id)
            return self._error_result(exc, inputs, annotation, started)
        except Exception as exc:  # isolamento: um nó com bug não derruba o fluxo inteiro
            self.cache.drop(workflow.id, node.id)
            friendly = errors_pt.translate(exc)
            if (
                friendly.technical is None
            ):  # nada conhecido (arquivo aberto, memória…): é bug, vai inteiro ao log
                log.exception("Falha inesperada na caixa %s (%s)", node.id, node.type)
                return NodeResult(
                    status="error",
                    error=f"Erro interno: {exc}",
                    annotation=annotation,
                    elapsed_ms=self._ms(started),
                )
            log.warning("Caixa %s (%s): %s", node.id, node.type, friendly.technical)
            return self._error_result(exc, inputs, annotation, started)

        elapsed = self._ms(started)
        entry = NodeEntry(
            fingerprint=fp, tables=output.tables, models=output.models, extra=output.extra, elapsed_ms=elapsed
        )
        self.cache.put(workflow.id, node.id, entry)
        fingerprints[node.id] = fp
        return NodeResult(
            status="executed",
            elapsed_ms=elapsed,
            anchors=_summarize(entry),
            annotation=annotation,
            extra=output.extra,
        )

    def _gather_inputs(
        self,
        workflow: Workflow,
        node: Node,
        spec: ToolSpec,
        results: dict[str, NodeResult],
        fingerprints: dict[str, str],
    ) -> _Inputs:
        ports = {p.id: p for p in spec.inputs}
        found = _Inputs({}, {}, {})
        for edge in (e for e in workflow.edges if e.target == node.id):
            port = ports.get(edge.target_handle)
            if port is None:
                raise SkippedError(f"Conexão em porta inexistente [{edge.target_handle}].")
            parent = results.get(edge.source)
            if parent is None or parent.status not in ("executed", "cached"):
                parent_name = workflow.node(edge.source).label or edge.source
                raise SkippedError(f"Entrada [{port.label}] indisponível: '{parent_name}' não foi executado.")
            entry = self.cache.get(workflow.id, edge.source)
            if entry is None:
                raise SkippedError(f"Entrada [{port.label}] indisponível.")
            if port.kind == "model":
                if edge.source_handle not in entry.models:
                    raise SkippedError(f"A entrada [{port.label}] espera um modelo treinado.")
                found.models[port.id] = entry.models[edge.source_handle]
            else:
                if edge.source_handle not in entry.tables:
                    raise SkippedError(f"A entrada [{port.label}] espera uma tabela.")
                try:
                    found.tables[port.id] = entry.tables[edge.source_handle]
                except ProdataError as exc:  # saiu da memória e o arquivo do cache sumiu
                    raise SkippedError(f"Entrada [{port.label}] indisponível. {exc.message}") from exc
            found.fingerprints[port.id] = f"{fingerprints[edge.source]}:{edge.source_handle}"

        missing = [p.label for p in spec.inputs if p.required and p.id not in found.fingerprints]
        if missing:
            raise SkippedError("Conecte a(s) entrada(s): " + ", ".join(f"[{m}]" for m in missing))
        return found

    @staticmethod
    def _fingerprint(node: Node, spec: ToolSpec, cfg: Any, ctx: NodeContext, inputs: _Inputs) -> str:
        config = cfg.model_dump(mode="json")
        payload = {
            "type": node.type,
            "config": config,
            "inputs": dict(sorted(inputs.fingerprints.items())),
            "extra": spec.fingerprint(ctx, cfg) if spec.fingerprint else "",
            # Constantes usadas e, com Today() na caixa, a data: o resultado muda quando o dia muda (spec 029).
            "constants": node.config.get(constants_engine.USED_KEY) or {},
            "day": date.today().isoformat() if _TODAY.search(json.dumps(config)) else "",
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:20]

    def _record_body(
        self,
        workflow: Workflow,
        found: loops.Found,
        body: dict[str, NodeResult],
        results: dict[str, NodeResult],
        progress: dict[str, Any],
        logs: list[LogEntry],
    ) -> None:
        """Resultado das caixas de dentro do laço (a última volta), com os avisos do desenho."""
        for body_id, body_result in body.items():
            if notes := found.warnings.get(body_id):
                body_result.extra = {
                    **body_result.extra,
                    "warnings": [*body_result.extra.get("warnings", []), *notes],
                }
            results[body_id] = body_result
            progress["done"][body_id] = body_result.status
            if body_result.status in ("executed", "cached"):  # a aba SQL confere o corpo também
                self._ran.setdefault(workflow.id, {})[body_id] = self._freshness(workflow, body_id)
            logs.append(self._log_entry(workflow, body_id, body_result))

    def _log_entry(self, workflow: Workflow, node_id: str, result: NodeResult) -> LogEntry:
        node = workflow.node(node_id)
        spec = REGISTRY.get(node.type)
        return LogEntry(
            node_id=node_id,
            node_name=node.label or (spec.name if spec else node.type),
            status=result.status,
            elapsed_ms=result.elapsed_ms,
            message=self._log_message(result),
        )

    @staticmethod
    def _ms(started: float) -> float:
        return round((time.perf_counter() - started) * 1000, 1)

    @staticmethod
    def _log_message(result: NodeResult) -> str:
        rows = sum(a.row_count for a in result.anchors.values() if a.kind == "data")
        match result.status:
            case "executed":
                # o tempo fica na coluna própria do Log, formatado na tela com o separador escolhido (spec 038)
                text = f"{rows:,} linha(s)".replace(",", ".")
                warnings = result.extra.get("warnings") or []
                return f"{text} · atenção: {' '.join(warnings)}" if warnings else text
            case "cached":
                return f"{rows:,} linha(s), reaproveitado do cache".replace(",", ".")
            case "disabled":
                return "Desabilitado"
            case _:
                return result.error or ""


def _expired(snapshot: FrozenEntry, refresh: str) -> bool:
    """Prazo do ponto de cache (spec 017): "daily" vale até o fim do dia (hora local); "hourly", por uma hora."""
    if refresh == "changes":
        return False
    frozen_at = datetime.fromisoformat(snapshot.frozen_at)
    now = datetime.now(UTC)
    if refresh == "hourly":
        return now - frozen_at >= timedelta(hours=1)
    return frozen_at.astimezone().date() != now.astimezone().date()
