"""Leitores de PDF da aba Dados (spec 037): cadastro, documentos, páginas, sugestões, avaliação e correções.

Todo PDF é lido no processo isolado (``documents/worker.py``). As respostas trazem texto do documento só para a
tela da própria pessoa; nada disso vai para log (RF-3782): os erros levam o código da falha, não o conteúdo.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Body, File, Form, Query, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from prodata.api.deps import ServicesDep
from prodata.documents.cache import failure_text
from prodata.documents.extract import APROVADO, FALHOU, REVISAR
from prodata.documents.outputs import build_outputs
from prodata.documents.reader import PdfReadError
from prodata.documents.recipe import Recipe
from prodata.documents.sources import MAIN_OUTPUT, Correction, PdfEntry, PdfSource, outputs_of
from prodata.documents.store import PdfStore
from prodata.documents.suggest import suggest_field, suggest_table
from prodata.documents.types import TYPE_LABELS
from prodata.engine.profiling import schema_of
from prodata.engine.serialize import json_rows
from prodata.errors import InvalidInputError, NotFoundError

router = APIRouter(prefix="/api/pdfs", tags=["dados"])
# Relatórios de demonstração que vão no pacote (RF-3790): para experimentar sem um PDF próprio.
EXAMPLES = Path(__file__).resolve().parents[2] / "samples" / "pdf"
EXAMPLE_NAME = "Relatórios de exemplo (PDF)"

# A prévia de impacto avalia uma amostra (RF-3740): o bastante para ver o efeito da regra, sem esperar a pasta toda.
SAMPLE = 12
MATRIX_MAX = 200
EVAL_BUDGET_S = 20.0


def _store(services: Any) -> PdfStore:
    store: PdfStore = services.datasets.pdfs
    return store


def _entry(store: PdfStore, source: PdfSource) -> PdfEntry:
    return PdfEntry(**source.model_dump(), status=store.status(source))


@router.get("")
def list_pdfs(services: ServicesDep) -> list[PdfEntry]:
    store = _store(services)
    return [_entry(store, s) for s in store.all_sources()]


@router.post("", status_code=201)
def create_pdf(source: PdfSource, services: ServicesDep) -> PdfEntry:
    store = _store(services)
    # a extração pode vir pronta (uma das extrações salvas, RF-3705); save confere se ela existe
    return _entry(store, store.save(source.model_copy(update={"id": "", "stored": False})))


@router.post("/upload", status_code=201)
async def upload_pdf(
    services: ServicesDep, file: UploadFile = File(...), name: str = Form(""), recipe: str = Form("")
) -> PdfEntry:
    """Cópia enviada (RF-3701): o programa guarda o PDF e a fonte aponta para a cópia."""
    store = _store(services)
    data = await file.read()
    path = store.store_upload(file.filename or "documento.pdf", data)
    label = name.strip() or (file.filename or "PDF").rsplit(".", 1)[0]
    try:
        saved = store.save(PdfSource(name=label[:80], mode="arquivo", path=str(path), recipe=recipe.strip()))
    except Exception:
        path.unlink(missing_ok=True)
        raise
    sources = store._sources()
    sources[saved.id] = saved.model_copy(update={"stored": True})
    store._save_sources(sources)
    return _entry(store, sources[saved.id])


# ------------------------------------------------------------------ extrações salvas (RF-3705)


@router.get("/recipes")
def recipe_library(services: ServicesDep) -> list[dict[str, Any]]:
    return _store(services).recipe_library()


@router.get("/recipes/{recipe_id}/export")
def export_recipe(recipe_id: str, services: ServicesDep) -> Response:
    """Arquivo da extração: sem caminho, sem segredo, sem marca (RF-3783)."""
    store = _store(services)
    body = store.export_recipe(recipe_id)
    name = re.sub(r"[^\w.-]+", "_", body["extracao"]["nome"]).strip("._") or "extracao"
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode() or "extracao"
    disposition = (
        f"attachment; filename=\"{plain}.extracao.json\"; filename*=UTF-8''{quote(name)}.extracao.json"
    )
    return Response(
        json.dumps(body, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": disposition},
    )


@router.post("/recipes/import", status_code=201)
async def import_recipe(
    services: ServicesDep, file: UploadFile = File(...), source: str = Form("")
) -> dict[str, Any]:
    raw = await file.read()
    if len(raw) > 2 * 2**20:
        raise InvalidInputError("Arquivo de extração grande demais.")
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except UnicodeDecodeError, ValueError:
        raise InvalidInputError("Este arquivo não é uma extração de PDF válida.") from None
    recipe = _store(services).import_recipe(payload, source.strip() or None)
    return {"recipe": recipe.model_dump(mode="json"), "outputs": outputs_of(recipe)}


@router.delete("/recipes/{recipe_id}")
def delete_recipe(recipe_id: str, services: ServicesDep, force: bool = Query(False)) -> dict[str, Any]:
    """Sem ``force``, recusa se alguma fonte usa (409, com os nomes); com ``force``, elas voltam a rascunho."""
    return {"detached": _store(services).delete_recipe(recipe_id, force)}


class UseRecipe(BaseModel):
    recipe: str = Field(min_length=1, max_length=64)


@router.post("/{source_id}/recipe/use")
def use_recipe(source_id: str, req: UseRecipe, services: ServicesDep) -> PdfEntry:
    store = _store(services)
    return _entry(store, store.use_recipe(source_id, req.recipe))


class ForkRecipe(BaseModel):
    name: str = Field("", max_length=120)


@router.post("/{source_id}/recipe/fork", status_code=201)
def fork_recipe(source_id: str, req: ForkRecipe, services: ServicesDep) -> dict[str, Any]:
    recipe = _store(services).fork_recipe(source_id, req.name or None)
    return {"recipe": recipe.model_dump(mode="json"), "outputs": outputs_of(recipe)}


@router.post("/example", status_code=201)
def create_example(services: ServicesDep) -> PdfEntry:
    """Fonte com os relatórios de demonstração, sem extração: é para a pessoa praticar marcando."""
    store = _store(services)
    found = next((s for s in store.all_sources() if Path(s.path) == EXAMPLES), None)
    if found is None:
        found = store.save(
            PdfSource(name=EXAMPLE_NAME, mode="pasta", path=str(EXAMPLES), pattern="relatorio_*.pdf")
        )
    return _entry(store, found)


@router.put("/{source_id}")
def update_pdf(source_id: str, source: PdfSource, services: ServicesDep) -> PdfEntry:
    store = _store(services)
    current = store.get(source_id)
    # a extração muda só pela rota dela; aqui vale o resto do cadastro
    return _entry(store, store.save(source.model_copy(update={"recipe": current.recipe}), previous=source_id))


@router.delete("/{source_id}", status_code=204)
def delete_pdf(source_id: str, services: ServicesDep) -> Response:
    _store(services).delete(source_id)
    return Response(status_code=204)


class DuplicateRequest(BaseModel):
    name: str = Field("", max_length=80)


@router.post("/{source_id}/duplicate", status_code=201)
def duplicate_pdf(source_id: str, req: DuplicateRequest, services: ServicesDep) -> PdfEntry:
    store = _store(services)
    return _entry(store, store.duplicate(source_id, req.name or None))


# ------------------------------------------------------------------ documentos e páginas


@router.get("/{source_id}/docs")
def documents(source_id: str, services: ServicesDep) -> dict[str, Any]:
    store = _store(services)
    source = store.get(source_id)
    try:
        docs = store.documents(source)
    except (NotFoundError, InvalidInputError) as exc:
        return {"docs": [], "error": str(exc)}
    out = []
    for d in docs:
        path = d["path"]
        exists = path.is_file()
        out.append(
            {
                "key": d["key"],
                "name": d["name"],
                "example": d["example"],
                "added": d.get("added", False),
                "missing": not exists,
                "size_bytes": path.stat().st_size if exists else 0,
                "modified_at": datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()
                if exists
                else None,
            }
        )
    left_out = [{"name": p.name, "added": str(p) in source.added} for p in store.left_out_files(source)]
    return {"docs": out, "left_out": left_out, "error": ""}


# ------------------------------------------------------------------ documentos um a um (RF-3706)

MAX_ADD = 50  # por envio


class DocName(BaseModel):
    name: str = Field(min_length=1, max_length=260)


@router.post("/{source_id}/docs/add", status_code=201)
async def add_documents(
    services: ServicesDep, source_id: str, files: list[UploadFile] = File(...)
) -> dict[str, Any]:
    """Soma PDFs à fonte: o programa guarda uma cópia de cada; a pasta da pessoa não é tocada."""
    if len(files) > MAX_ADD:
        raise InvalidInputError(f"Envie até {MAX_ADD} PDFs por vez.")
    store = _store(services)
    payload = [(f.filename or "documento.pdf", await f.read()) for f in files]
    added = store.add_files(source_id, payload)
    return {"added": added, "source": _entry(store, store.get(source_id))}


@router.post("/{source_id}/docs/leave")
def leave_out(source_id: str, req: DocName, services: ServicesDep) -> dict[str, Any]:
    """Tira um documento: arquivo da pessoa fica no disco (Fora da fonte); cópia do programa é apagada."""
    store = _store(services)
    deleted = store.leave_out(source_id, req.name)
    return {"deleted": deleted, "source": _entry(store, store.get(source_id))}


@router.post("/{source_id}/docs/back")
def bring_back(source_id: str, req: DocName, services: ServicesDep) -> PdfEntry:
    store = _store(services)
    store.bring_back(source_id, req.name)
    return _entry(store, store.get(source_id))


@router.get("/{source_id}/docs/words")
def words(source_id: str, services: ServicesDep, doc: str = Query(...)) -> dict[str, Any]:
    store = _store(services)
    path = store.document_path(store.get(source_id), doc)
    try:
        info = store.cache.words(path)
    except PdfReadError as exc:
        return {"erro": exc.code, "mensagem": failure_text(exc.code), "pages": [], "words": []}
    return {**info, "assinatura": store.cache.fingerprint(path)}


@router.get("/{source_id}/docs/page.png")
def page_image(
    source_id: str,
    services: ServicesDep,
    doc: str = Query(...),
    page: int = Query(0, ge=0),
    escala: float = Query(1.5, gt=0, le=4),
) -> Response:
    store = _store(services)
    path = store.document_path(store.get(source_id), doc)
    scale = round(max(0.5, min(escala, 4.0)) * 4) / 4  # degraus de 0,25: o navegador reaproveita a imagem
    try:
        png = store.cache.worker.call("render", path=str(path), page_index=page, scale=scale)
    except PdfReadError as exc:
        raise InvalidInputError(failure_text(exc.code)) from None
    etag = f'"{store.cache.fingerprint(path)}-{page}-{scale}"'
    return Response(
        png, media_type="image/png", headers={"Cache-Control": "private, max-age=3600", "ETag": etag}
    )


# ------------------------------------------------------------------ extração


def _recipe_or_new(store: PdfStore, source: PdfSource) -> Recipe:
    return store.recipe_of(source) or Recipe(id="nova", nome=source.name)


@router.get("/{source_id}/recipe")
def get_recipe(source_id: str, services: ServicesDep) -> dict[str, Any]:
    store = _store(services)
    source = store.get(source_id)
    recipe = _recipe_or_new(store, source)
    return {
        "recipe": recipe.model_dump(mode="json"),
        "saved": bool(source.recipe),
        "tipos": TYPE_LABELS,
        "outputs": outputs_of(recipe),
        "shared": sum(1 for s in store.all_sources() if source.recipe and s.recipe == source.recipe),
    }


@router.put("/{source_id}/recipe")
def put_recipe(source_id: str, recipe: Recipe, services: ServicesDep) -> dict[str, Any]:
    saved = _store(services).save_recipe(source_id, recipe)
    return {"recipe": saved.model_dump(mode="json"), "outputs": outputs_of(saved), "digest": saved.digest()}


class FieldSuggestion(BaseModel):
    doc: str
    words: list[dict[str, Any]] = Field(min_length=1, max_length=2000)


@router.post("/{source_id}/suggest/field")
def suggest_field_route(source_id: str, req: FieldSuggestion, services: ServicesDep) -> dict[str, Any]:
    store = _store(services)
    path = store.document_path(store.get(source_id), req.doc)
    try:
        return suggest_field(store.cache.words(path), req.words)
    except PdfReadError as exc:
        raise InvalidInputError(failure_text(exc.code)) from None
    except ValueError as exc:
        raise InvalidInputError(str(exc)) from None


class TableSuggestion(BaseModel):
    doc: str
    page: int = Field(ge=0)
    area: tuple[float, float, float, float]
    name: str = "tabela"


@router.post("/{source_id}/suggest/table")
def suggest_table_route(source_id: str, req: TableSuggestion, services: ServicesDep) -> dict[str, Any]:
    store = _store(services)
    path = store.document_path(store.get(source_id), req.doc)
    try:
        return suggest_table(store.cache.words(path), req.page, req.area, req.name)
    except PdfReadError as exc:
        raise InvalidInputError(failure_text(exc.code)) from None
    except ValueError as exc:
        raise InvalidInputError(str(exc)) from None


class EvaluateRequest(BaseModel):
    recipe: Recipe
    docs: list[str] = Field(default_factory=list, max_length=MATRIX_MAX)  # chaves; vazio = amostra
    limit: int = Field(SAMPLE, ge=1, le=MATRIX_MAX)


def _evaluate(store: PdfStore, source: PdfSource, req: EvaluateRequest) -> dict[str, Any]:
    docs = store.documents(source)
    wanted = req.docs or [d["key"] for d in docs[: req.limit]]
    by_key = {d["key"]: d for d in docs}
    results: dict[str, Any] = {}
    started = time.monotonic()
    for key in wanted:
        if key not in by_key:
            continue
        if time.monotonic() - started > EVAL_BUDGET_S:  # nunca trava: devolve o que já avaliou e diz quantos
            break
        d = by_key[key]
        if not d["path"].is_file():
            results[key] = {
                "estado": FALHOU,
                "motivo": "arquivo não encontrado",
                "erro": "sumiu",
                "campos": [],
                "tabelas": [],
            }
            continue
        run = store.evaluate(source, req.recipe, d["path"], d["name"])
        results[key] = {**run.result, "corrigidos": run.corrected, "exemplo": d["example"]}
    counts = {s: sum(1 for r in results.values() if r["estado"] == s) for s in (APROVADO, REVISAR, FALHOU)}
    fields: dict[str, dict[str, int]] = {}
    for r in results.values():
        for f in r.get("campos", []):
            per = fields.setdefault(f["nome"], {})
            per[f["estado"]] = per.get(f["estado"], 0) + 1
    real = [d for d in docs if not d["example"]]
    return {
        "digest": req.recipe.digest(),
        "results": results,
        "evaluated": len(results),
        "total": len(docs),
        "total_source": len(real),
        "counts": counts,
        "fields": fields,
    }


@router.post("/{source_id}/evaluate")
async def evaluate(source_id: str, req: EvaluateRequest, services: ServicesDep) -> dict[str, Any]:
    """Aplica uma extração (ainda não salva) a uma amostra ou a documentos escolhidos: execução real, não estimativa."""
    store = _store(services)
    source = store.get(source_id)
    out = await run_in_threadpool(_evaluate, store, source, req)
    if not req.docs and out["evaluated"] == out["total"] and out["total"]:
        real = [r for r in out["results"].values() if not r.get("exemplo")]
        if (
            len(real) == out["total_source"]
            and req.recipe.digest() == (store.recipe_of(source) or req.recipe).digest()
        ):
            store.summaries[source_id] = (
                {s: sum(1 for r in real if r["estado"] == s) for s in (APROVADO, REVISAR, FALHOU)},
                datetime.now(UTC),
            )
    return out


@router.get("/{source_id}/outputs/{output}")
async def output_preview(
    source_id: str, output: str, services: ServicesDep, rows: int = Query(100, ge=1, le=500)
) -> dict[str, Any]:
    """Prévia de uma saída como o Input Data vai ler, mas sem parar pela política (para conferir)."""
    store = _store(services)

    def work() -> dict[str, Any]:
        source, recipe, docs = store.run(source_id)
        tables = build_outputs(source, recipe, docs)
        if output not in tables:
            raise NotFoundError(f"A saída '{output}' não existe nesta fonte.")
        table = tables[output]
        failed = sum(1 for d in docs if d.result["estado"] == FALHOU)
        return {
            "columns": schema_of(table),
            "rows": json_rows(table.head(rows)),
            "row_count": table.height,
            "documents": len(docs),
            "failed": failed,
            "stops": failed > 0 and source.policy == "parar" and output != "falhas",
        }

    return await run_in_threadpool(work)


# ------------------------------------------------------------------ correções


@router.get("/{source_id}/corrections")
def list_corrections(source_id: str, services: ServicesDep) -> list[Correction]:
    return _store(services).corrections(source_id)


class CorrectionRequest(BaseModel):
    doc: str
    field: str
    value: str = Field(min_length=1, max_length=400)


@router.post("/{source_id}/corrections", status_code=201)
def add_correction(source_id: str, req: CorrectionRequest, services: ServicesDep) -> Correction:
    return _store(services).add_correction(source_id, req.doc, req.field, req.value)


@router.delete("/{source_id}/corrections/{correction_id}", status_code=204)
def remove_correction(source_id: str, correction_id: str, services: ServicesDep) -> Response:
    _store(services).remove_correction(source_id, correction_id)
    return Response(status_code=204)


@router.get("/{source_id}/main")
def main_output(source_id: str) -> dict[str, str]:
    return {"value": f"pdf:{source_id}/{MAIN_OUTPUT}"}


__all__ = ["Body", "router"]
