"""Fluxo em outro computador (spec 040): o que falta aqui e "Salvar com amostra dos dados"."""

from __future__ import annotations

from pathlib import Path as FsPath
from typing import Any, Literal

import polars as pl
from fastapi import APIRouter
from pydantic import BaseModel, Field

from prodata.api.deps import ServicesDep
from prodata.domain.samples import MAX_BYTES, SourceSample
from prodata.domain.samples import MAX_ROWS as SAMPLE_ROWS
from prodata.domain.workflow import Workflow
from prodata.engine import graph
from prodata.engine.serialize import json_rows
from prodata.errors import InvalidInputError
from prodata.nodes.textual import guess_personal, mask_frame
from prodata.services.audit import log_export
from prodata.services.portable import check_sources
from prodata.services.workflows import save_to_file
from prodata.team.runtime import SpaceView, runner_for

router = APIRouter(prefix="/api/portable", tags=["fluxo portátil"])


class CheckRequest(BaseModel):
    workflow: Workflow
    espaco: str | None = Field(None, pattern=r"^[a-f0-9]{16}$")  # fluxo do espaço: vale a equipe (spec 048)


@router.post("/sources")
def sources(req: CheckRequest, services: ServicesDep) -> dict[str, Any]:
    """Cada fonte do fluxo e se ela está neste computador, falta ou será lida da amostra (RF-4010)."""
    if req.espaco and (defs := services.team.space_definitions(req.espaco)) is not None:
        found = check_sources(req.workflow, SpaceView(services, runner_for(services, req.espaco)))
        team_keys = {f"query:sql:{k}" for k in defs.definitions.keys("consultas")}
        team_keys |= {f"api:api:{k}" for k in defs.definitions.keys("apis")}
        team_keys |= {f"connection:{k}" for k in defs.definitions.keys("conexoes")}
        for item in found:  # RF-4807: o que veio da equipe aparece como "Da equipe"
            item["equipe"] = item["state"] == "ok" and f"{item['kind']}:{item['key']}" in team_keys
    else:
        found = check_sources(req.workflow, services)
    return {"sources": found, "missing": sum(1 for s in found if s["state"] == "missing")}


ROW_CHOICES = (100, 500, 1000)
MaskMethod = Literal["", "cpf", "cnpj", "email", "keep_last", "keep_first", "fixed", "code"]


class SourceOptions(BaseModel):
    """O que levar de cada fonte (RF-4019): quantas linhas e o que mascarar, coluna a coluna."""

    rows: int = Field(1000, ge=1, le=1000)
    mask: dict[str, MaskMethod] = Field(default_factory=dict)


def _frame(workflow: Workflow, services: Any, node_id: str) -> pl.DataFrame | None:
    services.runner.run(workflow, node_id)
    entry = services.cache.get(workflow.id, node_id)
    return entry.tables["out"] if entry is not None and "out" in entry.tables else None


def _input_node(workflow: Workflow, item: dict[str, Any]) -> str | None:
    types = {x.id: x.type for x in workflow.nodes}
    return next((n for n in item["nodes"] if types[n] == "io.input_data"), None)


def _samples(
    workflow: Workflow, services: Any, options: dict[str, SourceOptions] | None
) -> tuple[dict[str, SourceSample], list[dict[str, Any]]]:
    """Lê as primeiras linhas de cada fonte que está aqui (executando só a caixa de entrada) e monta a amostra.

    ``options``: as fontes escolhidas, com linhas e máscara; None = prévia de todas, com a máscara sugerida.
    """
    made: dict[str, SourceSample] = {}
    report = []
    seen: set[str] = set()
    for item in check_sources(workflow, services):
        key = item["key"]
        if item["kind"] in ("subflow", "model", "connection") or key in seen:
            continue
        seen.add(key)
        node_id = _input_node(workflow, item)
        if node_id is None:  # usada só por um API Loop: a amostra é da leitura, não da chamada por linha
            continue
        if options is not None and key not in options:
            report.append({**_brief(item), "chosen": False})
            continue
        if item["state"] == "missing":
            report.append({**_brief(item), "chosen": False, "reason": "a fonte não está neste computador"})
            continue
        frame = (
            workflow.samples[key].frame()
            if item["state"] == "sample"
            else _frame(workflow, services, node_id)
        )
        if frame is None:
            report.append({**_brief(item), "chosen": False, "reason": "não foi possível ler a fonte"})
            continue
        suggested = guess_personal(frame.head(SAMPLE_ROWS))
        opt = options[key] if options is not None else SourceOptions(mask=suggested)
        masked = mask_frame(frame.head(opt.rows), dict(opt.mask), services.runner.secret_key)
        linked = bool(item.get("linked")) or (item["state"] == "sample" and workflow.samples[key].linked)
        made[key] = SourceSample.of(masked, _label(services, item), linked=linked)
        report.append(
            {
                **_brief(item),
                "chosen": True,
                "rows": made[key].rows,
                "available": min(frame.height, SAMPLE_ROWS),
                "size": made[key].size(),
                "columns": [{"name": c, "type": str(t)} for c, t in frame.schema.items()],
                "mask": suggested,
                "linked": linked,
            }
        )
    return made, report


def _brief(item: dict[str, Any]) -> dict[str, Any]:
    return {"key": item["key"], "label": item["label"], "kind_label": item["kind_label"]}


def _label(services: Any, item: dict[str, Any]) -> str:
    """O nome que a pessoa vê na vista Dados (nome de exibição da organização), nunca um caminho."""
    info = services.organization.get().sources.get(item["key"])
    return info.label if info is not None and info.label else str(item["label"])


class PreviewRequest(BaseModel):
    workflow: Workflow


@router.post("/share/preview")
def share_preview(req: PreviewRequest, services: ServicesDep) -> dict[str, Any]:
    """O que iria na amostra: fonte a fonte, linhas e tamanho (RF-4013)."""
    graph.topological_order(req.workflow)
    made, report = _samples(req.workflow, services, None)
    total = sum(s.size() for s in made.values())
    return {"sources": report, "total": total, "limit": MAX_BYTES, "max_rows": 1000}


class MaskPreview(BaseModel):
    workflow: Workflow
    key: str
    mask: dict[str, MaskMethod] = Field(default_factory=dict)


@router.post("/share/mask-preview")
def mask_preview(req: MaskPreview, services: ServicesDep) -> dict[str, Any]:
    """As primeiras linhas da fonte já mascaradas, para conferir antes de salvar (RF-4019)."""
    item = next((s for s in check_sources(req.workflow, services) if s["key"] == req.key), None)
    node_id = _input_node(req.workflow, item) if item else None
    if item is None or node_id is None or item["state"] == "missing":
        raise InvalidInputError("Esta fonte não está neste computador.")
    frame = (
        req.workflow.samples[req.key].frame()
        if item["state"] == "sample"
        else _frame(req.workflow, services, node_id)
    )
    if frame is None:
        raise InvalidInputError("Não foi possível ler a fonte.")
    shown = mask_frame(frame.head(5), dict(req.mask), services.runner.secret_key)
    return {"columns": shown.columns, "rows": json_rows(shown)}


class ShareRequest(BaseModel):
    workflow: Workflow
    path: str = Field(min_length=1, max_length=1000)
    sources: dict[str, SourceOptions] = Field(default_factory=dict, max_length=500)


@router.post("/share/save")
def share_save(req: ShareRequest, services: ServicesDep) -> dict[str, Any]:
    """Grava o fluxo com a amostra das fontes escolhidas, dentro dos limites, e registra a exportação (RF-4014)."""
    graph.topological_order(req.workflow)
    if not req.sources:
        raise InvalidInputError("Escolha pelo menos uma fonte para a amostra, ou use Salvar como.")
    made, _ = _samples(req.workflow, services, req.sources)
    total = sum(s.size() for s in made.values())
    if total > MAX_BYTES:
        raise InvalidInputError(
            f"A amostra teria {total // 1024} KB: o limite é {MAX_BYTES // 1024 // 1024} MB. Tire fontes da amostra."
        )
    workflow = services.runner.snapshot(req.workflow).model_copy(update={"samples": made})
    path = save_to_file(workflow, req.path)
    services.trust.saved(workflow)
    label = workflow.dashboard.confidentiality if workflow.dashboard else "interno"
    log_export(
        "Fluxo com amostra",
        FsPath(path).name,
        str(label),
        sum(s.rows for s in made.values()),
        None,
        fontes=len(made),
        mascaradas=sum(len([m for m in o.mask.values() if m]) for o in req.sources.values()),
    )
    return {"path": str(path), "workflow": workflow.model_dump(mode="json", by_alias=True)}
