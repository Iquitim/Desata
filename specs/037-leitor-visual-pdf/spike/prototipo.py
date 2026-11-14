"""Protótipo de tela do spike 037 (fora do pacote): marcar no PDF, ver o dado nascer e rastrear a origem.

    uv run python specs/037-leitor-visual-pdf/spike/prototipo.py [porta]

Usa o motor de verdade (``prodata.documents``) e os tokens visuais do Desata. Os documentos são os PDFs sintéticos de
``tests/fixtures/pdf``. Nada aqui entra no pacote: a tela definitiva nasce na vista Dados (T03..T09).
"""

from __future__ import annotations

import sys
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import Body, FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from prodata import brand
from prodata.documents.cache import DocumentCache, failure_text
from prodata.documents.reader import PdfReadError
from prodata.documents.recipe import Recipe
from prodata.documents.suggest import suggest_field, suggest_table
from prodata.documents.types import TYPE_LABELS
from prodata.documents.worker import PdfWorker

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
FIX = ROOT / "tests" / "fixtures" / "pdf"
WEB = ROOT / "src" / "prodata" / "web"
DOCS = {
    "outubro": "Relatório de outubro (2 páginas)",
    "novembro": "Relatório de novembro (cabeçalho mais abaixo)",
    "dois_totais": "Relatório com dois totais",
    "invalido": "Relatório incompleto",
    "girado": "Relatório com a página girada",
    "rotacao_interna": "Relatório girado dentro do PDF",
    "escaneado": "Relatório escaneado",
    "protegido": "Relatório com senha",
    "quebrado": "Arquivo danificado",
}

app = FastAPI(title="Spike 037")
app.mount("/static", StaticFiles(directory=WEB), name="static")
worker = PdfWorker(timeout=30)
cache = DocumentCache(Path(tempfile.mkdtemp(prefix="spike037-")), worker)


def _path(doc: str) -> Path:
    if doc not in DOCS:
        raise HTTPException(404, "documento desconhecido")
    return FIX / f"relatorio_{doc}.pdf"


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(HERE / "prototipo.html")


@app.get("/prototipo.{ext}", include_in_schema=False)
def asset(ext: str) -> FileResponse:
    if ext not in ("js", "css"):
        raise HTTPException(404)
    return FileResponse(HERE / f"prototipo.{ext}", headers={"Cache-Control": "no-store"})


@app.get("/marca/cores.css", include_in_schema=False)
def colors() -> Response:
    return Response(brand.css(brand.marca()), media_type="text/css")


@app.get("/api/docs")
def docs() -> dict[str, Any]:
    return {"docs": [{"id": k, "nome": v} for k, v in DOCS.items()], "tipos": TYPE_LABELS}


@app.get("/api/docs/{doc}")
def words(doc: str) -> dict[str, Any]:
    try:
        return cache.words(_path(doc))
    except PdfReadError as exc:
        return {"erro": exc.code, "mensagem": failure_text(exc.code), "pages": [], "words": []}


@lru_cache(maxsize=64)
def _png(doc: str, page: int, scale: float) -> bytes:
    data: bytes = worker.call("render", path=str(_path(doc)), page_index=page, scale=scale)
    return data


@app.get("/api/docs/{doc}/pagina/{page}.png")
def page_image(doc: str, page: int, escala: float = 1.5) -> Response:
    scale = round(max(0.5, min(escala, 4.0)) * 4) / 4  # degraus de 0,25: o cache acerta mais
    try:
        return Response(_png(doc, page, scale), media_type="image/png", headers={"Cache-Control": "max-age=3600"})
    except PdfReadError as exc:
        raise HTTPException(422, failure_text(exc.code)) from None


@app.post("/api/campo")
def field(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    try:
        return suggest_field(cache.words(_path(payload["doc"])), payload["palavras"])
    except (PdfReadError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from None


@app.post("/api/tabela")
def table(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    try:
        info = cache.words(_path(payload["doc"]))
        return suggest_table(info, payload["pagina"], payload["area"], payload.get("nome", "tabela"))
    except (PdfReadError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from None


@app.post("/api/extrair")
def run(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    try:
        recipe = Recipe.model_validate(payload["receita"])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    targets = payload.get("docs") or list(DOCS)
    return {"digest": recipe.digest(), "resultados": {d: cache.extract(_path(d), recipe) for d in targets}}


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8737
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
