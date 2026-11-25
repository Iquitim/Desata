"""Factory da aplicação FastAPI. Nada é criado em disco no import, só no ``create_app``."""

from __future__ import annotations

import importlib
import logging
import re
import threading
from collections.abc import Awaitable, Callable
from html import escape
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from prodata import __version__
from prodata.api.deps import Services
from prodata.api.errors import install_error_handlers
from prodata.api.routes import routers
from prodata.brand import css as brand_css
from prodata.brand import marca
from prodata.catalog.service import CatalogService
from prodata.config import Settings
from prodata.connectors import ConnectionStore, KeyringSecretStore, MemorySecretStore, SecretStore
from prodata.connectors.api_store import ApiStore
from prodata.connectors.jira_store import JiraStore
from prodata.connectors.queries import QueryStore
from prodata.connectors.secrets import installation_key
from prodata.domain.workflow import Workflow
from prodata.engine.cache import ResultCache
from prodata.engine.runner import WorkflowRunner
from prodata.ingestion import DatasetStore
from prodata.nodes import REGISTRY
from prodata.samples.apis import refresh_example_docs, seed_example_apis
from prodata.samples.datasets import ensure_sample_datasets
from prodata.samples.demo_logo import refresh_demo_logo
from prodata.samples.pdfs import refresh_example_pdfs, seed_example_pdfs
from prodata.samples.workflow_loop import add_loop_section
from prodata.samples.workflows import (
    DEMO_V3_NODES,
    DEMO_WORKFLOW_ID,
    add_api_section,
    add_pdf_section,
    add_replay_section,
    demo_workflow,
)
from prodata.scheduling.service import SchedulingService
from prodata.scheduling.store import ScheduleStore
from prodata.services.audit import setup_audit
from prodata.services.constants import ConstantStore
from prodata.services.organization import OrganizationStore
from prodata.services.trust import TrustRegistry
from prodata.services.usage import UsageIndex
from prodata.services.versions import VersionStore
from prodata.services.workflows import WorkflowRepository
from prodata.team.identity import IdentityStore
from prodata.team.service import TeamService
from prodata.team.workspaces import Workspaces

WEB_DIR = Path(__file__).parent / "web"
log = logging.getLogger("prodata")


def build_services(settings: Settings) -> Services:
    settings.ensure_dirs()
    setup_audit(settings.storage_dir)
    datasets = DatasetStore(settings.datasets_dir, settings.max_upload_mb * 1024 * 1024)
    cache = ResultCache(settings.cache_dir, settings.cache_memory_mb * 1024 * 1024)
    workflows = WorkflowRepository(settings.workflows_dir)
    secrets: SecretStore = (
        KeyringSecretStore() if settings.secrets_backend == "keyring" else MemorySecretStore()
    )
    connections = ConnectionStore(settings.connections_file, secrets)
    queries = QueryStore(settings.queries_file)
    apis = ApiStore(settings.apis_file, secrets)
    jira = JiraStore(settings.storage_dir / "jira", secrets)
    trust = TrustRegistry(settings.storage_dir / "confianca.json")
    constants = ConstantStore(settings.storage_dir / "constantes.json")
    # Na atualização para a 0.6, o que já estava na biblioteca começa confiável (RF-2825).
    trust.start([workflows.get(s.id) for s in workflows.list()])
    if settings.seed_samples:
        ensure_sample_datasets(settings.datasets_dir)
        if not workflows.exists(DEMO_WORKFLOW_ID) or _uses_removed_tools(workflows.get(DEMO_WORKFLOW_ID)):
            workflows.save(Workflow.model_validate(demo_workflow()))
            seed_example_apis(apis)
            seed_example_pdfs(datasets.pdfs)
        else:
            saved = workflows.get(DEMO_WORKFLOW_ID).model_dump(mode="json", by_alias=True)
            with_api = add_api_section(saved)
            if with_api or add_replay_section(saved):
                add_replay_section(saved)
                workflows.save(Workflow.model_validate(saved))
            if with_api:
                seed_example_apis(apis)
            with_pdf = add_pdf_section(saved)
            if with_pdf:
                seed_example_pdfs(datasets.pdfs)
            with_loop = add_loop_section(saved)  # etapa do laço (spec 041)
            # o logo do dashboard do exemplo segue a marca ativa (exemplo criado com outra marca)
            if with_pdf | with_loop | refresh_demo_logo(saved):
                workflows.save(Workflow.model_validate(saved))
        refresh_example_docs(apis)
        refresh_example_pdfs(datasets.pdfs)
        if workflows.exists(DEMO_WORKFLOW_ID):
            trust.created(workflows.get(DEMO_WORKFLOW_ID))
    team = TeamService(
        Workspaces(settings.storage_dir / "espacos.json", marca().id, marca().nome),
        IdentityStore(secrets, settings.storage_dir / "equipe.json"),
        workflows,
        settings.storage_dir / "equipe",
    )
    return Services(
        settings=settings,
        datasets=datasets,
        cache=cache,
        runner=WorkflowRunner(
            cache,
            datasets,
            settings.exports_dir,
            connections,
            queries,
            apis,
            constants,
            jira,
            state_dir=settings.storage_dir / "estado",
            workflows=workflows,
            secret_key=lambda: installation_key(secrets),
            guard=trust.check_runnable,
            catalog_root=settings.storage_dir / "catalogo",
        ),
        workflows=workflows,
        connections=connections,
        queries=queries,
        apis=apis,
        jira=jira,
        trust=trust,
        usage=UsageIndex(settings.workflows_dir),
        constants=constants,
        organization=OrganizationStore(settings.storage_dir / "organizacao.json"),
        schedules=SchedulingService(
            ScheduleStore(
                settings.storage_dir / "agendamentos.json",
                settings.storage_dir / "logs" / "agendamentos.jsonl",
            ),
            workflows,
            trust,
            team=team,  # fluxos do espaço da equipe: só a versão oficial (spec 047)
        ),
        versions=VersionStore(settings.storage_dir / "versoes"),
        team=team,
        catalog=CatalogService(settings.storage_dir / "catalogo"),
    )


def _uses_removed_tools(workflow: Workflow) -> bool:
    """Demonstração antiga: usa ferramentas removidas (spec 013) ou é anterior ao Pareto e ao Venn (spec 014)."""
    ids = {n.id for n in workflow.nodes}
    return any(n.type not in REGISTRY for n in workflow.nodes) or not ids.intersection(DEMO_V3_NODES)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    app = FastAPI(
        title=marca().nome,
        version=__version__,
        description="API do motor de pipelines visuais (Polars + DuckDB + Arrow).",
    )
    app.state.services = build_services(settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type"],
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=_accepted_hosts(settings))
    install_error_handlers(app)
    for router in routers:
        app.include_router(router)

    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
    install_brand_routes(app)

    @app.middleware("http")
    async def refuse_other_sites(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # O CORS só esconde a resposta: um envio de arquivo vindo de outro site ainda seria executado.
        origin = request.headers.get("origin")
        if (
            origin
            and request.method not in ("GET", "HEAD", "OPTIONS")
            and not _same_origin(origin, request.headers.get("host", ""), settings.cors_origins)
        ):
            return JSONResponse({"detail": "Pedido de outro site recusado."}, status_code=403)
        return await call_next(request)

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.middleware("http")
    async def revalidate_static(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Módulos ES não passam por bundler com hash no nome: força revalidação (ETag) a cada carga.
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/", include_in_schema=False)
    def index() -> HTMLResponse:
        return HTMLResponse(
            index_html(), headers={"Cache-Control": "no-cache", "Content-Security-Policy": APP_CSP}
        )

    log.info("%s %s pronto (storage: %s)", marca().nome, __version__, settings.storage_dir)
    threading.Thread(target=_warm_up, name="prodata-warmup", daemon=True).start()
    return app


def _accepted_hosts(settings: Settings) -> list[str]:
    """Só o próprio computador: com outro nome de host, uma página externa leria a API (DNS rebinding)."""
    if settings.host in ("0.0.0.0", "::"):  # noqa: S104  (só compara o que foi configurado)
        return ["*"]
    return sorted({"127.0.0.1", "localhost", settings.host, *settings.allowed_hosts})


def _same_origin(origin: str, host: str, allowed: list[str]) -> bool:
    return origin in allowed or urlsplit(origin).netloc == host


def _warm_up() -> None:
    """Carrega em segundo plano o que é pesado e só é usado depois (ML, motor de fórmulas).

    O servidor já atende enquanto isso; o primeiro treino não paga ~0,7 s de importação.
    """
    try:
        for module in (
            "sklearn.ensemble",
            "sklearn.linear_model",
            "sklearn.metrics",
            "sklearn.model_selection",
        ):
            importlib.import_module(module)
        from prodata.engine import formula

        formula.connect().close()
    except Exception:  # aquecimento é otimização: falhar aqui não pode derrubar o servidor
        log.debug("Aquecimento em segundo plano falhou", exc_info=True)


# Só roda script do próprio programa e nada sai para outro endereço, mesmo que algo consiga entrar na página.
# Estilo em linha é usado nos desenhos; imagens em data:/blob: são as do dashboard e as geradas para exportar.
APP_CSP = "; ".join(
    (
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob:",
        "font-src 'self' data:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'none'",
        "frame-ancestors 'none'",
    )
)

PRELOAD_MARKER = "<!-- modulepreload: o servidor insere aqui a pré-carga de todos os módulos JS -->"


def index_html() -> str:
    """index.html com <link rel="modulepreload"> para cada módulo: o navegador baixa todos em
    paralelo em vez de descobri-los em cascata. Lido a cada pedido (barato) para refletir edições."""
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    modules = sorted(p.name for p in (WEB_DIR / "js").glob("*.js") if p.name != "main.js")
    links = "\n".join(f'  <link rel="modulepreload" href="/static/js/{m}" />' for m in modules)
    return brand_page(html.replace(PRELOAD_MARKER, links))


# ------------------------------------------------------------------ marca (spec 036)

BRAND_FILES = {
    "logo-claro.svg": "image/svg+xml",
    "logo-escuro.svg": "image/svg+xml",
    "icone.png": "image/png",
    "icone-escuro.png": "image/png",
}
FONT_FILES = {"Open Sans": "open-sans-latin-wght-normal.woff2", "Inter": "inter-latin-wght-normal.woff2"}
_FONT_NAME = re.compile(r"^[A-Za-z0-9._-]+\.woff2$")


def brand_page(html: str) -> str:
    """Troca as marcações do index.html pelos dados da marca ativa (texto sempre escapado)."""
    b = marca()
    attrs = " ".join(
        f'data-marca-{k.replace("_", "-")}="{escape(v, quote=True)}"' for k, v in b.public().items()
    )
    font = FONT_FILES.get(b.fonte_texto)
    preload = (
        f'<link rel="preload" href="/static/fonts/{font}" as="font" type="font/woff2" crossorigin />'
        if font
        else ""
    )
    return (
        html.replace("{{marca.atributos}}", attrs)
        .replace("{{marca.titulo}}", escape(b.title))
        .replace("{{marca.nome}}", escape(b.nome, quote=True))
        .replace("{{marca.apoio}}", escape(b.tagline))
        .replace("{{marca.preload}}", preload)
    )


def _logo_fallback(name: str) -> str:
    """Logo que falta: o nome do produto escrito, em vez de imagem quebrada (RF-3603)."""
    color = "#ffffff" if "escuro" in name else "#1b1b19"
    text = escape(marca().nome)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 60">'
        f'<text x="0" y="42" font-family="Segoe UI, sans-serif" font-size="34" font-weight="700" fill="{color}">{text}</text></svg>'
    )


def install_brand_routes(app: FastAPI) -> None:
    @app.get("/marca/cores.css", include_in_schema=False)
    def brand_colors() -> Response:
        return Response(brand_css(marca()), media_type="text/css", headers={"Cache-Control": "no-cache"})

    @app.get("/marca/fontes/{name}", include_in_schema=False)
    def brand_font(name: str) -> Response:
        path = marca().dir / "fontes" / name
        if not _FONT_NAME.match(name) or not path.is_file():
            return Response(status_code=404)
        return FileResponse(path, media_type="font/woff2")

    @app.get("/api/marca")
    def brand_info() -> dict[str, str]:
        return {**marca().public(), "versao": __version__}

    @app.get("/marca/{name}", include_in_schema=False)
    def brand_file(name: str) -> Response:
        media = BRAND_FILES.get(name)
        if media is None:
            return Response(status_code=404)
        path = marca().dir / name
        if path.is_file():
            return FileResponse(path, media_type=media, headers={"Cache-Control": "no-cache"})
        if media == "image/svg+xml":
            return Response(_logo_fallback(name), media_type=media)
        return Response(status_code=404)
