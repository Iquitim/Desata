"""Fluxo em outro computador (spec 040, RF-4010..4017): o que ele usa e o que falta aqui.

Uma conferência só, de todos os tipos de fonte, para a vista Dados, o Designer, a abertura protegida e o "Salvar para
compartilhar". Nada daqui lê os dados: só confere se cada fonte está cadastrada neste computador.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from prodata.connectors.api_model import source_api_id
from prodata.connectors.jira_model import source_jira_id
from prodata.connectors.queries import source_query_id
from prodata.documents.sources import source_pdf_ref
from prodata.domain.workflow import Workflow
from prodata.errors import NotFoundError
from prodata.ingestion.folders import source_folder_id
from prodata.nodes import ml_library

# o que cada tipo pede para resolver, na vista Dados
ACTIONS = {
    "file": "Escolher o arquivo",
    "folder": "Escolher a pasta",
    "pdf": "Escolher os PDFs",
    "query": "Cadastrar a consulta",
    "api": "Cadastrar a API",
    "jira": "Cadastrar a consulta do Jira",
    "connection": "Cadastrar a conexão",
    "subflow": "Abrir o subfluxo",
    "model": "Importar o modelo",
}
KIND_LABELS = {
    "file": "Arquivo",
    "folder": "Pasta de arquivos",
    "pdf": "Leitor de PDF",
    "query": "Consulta de banco",
    "api": "API",
    "jira": "Consulta do Jira",
    "connection": "Conexão de banco",
    "subflow": "Subfluxo",
    "model": "Modelo",
}


def kind_of(source: str) -> str:
    if source_folder_id(source) is not None:
        return "folder"
    if source_pdf_ref(source) is not None:
        return "pdf"
    if source_query_id(source) is not None:
        return "query"
    if source_api_id(source) is not None:
        return "api"
    if source_jira_id(source) is not None:
        return "jira"
    return "file"


def _found(lookup: Callable[[], Any]) -> Any | None:
    try:
        return lookup()
    except NotFoundError:
        return None


def _lookup(services: Any, kind: str, key: str) -> Any | None:
    """O cadastro da fonte neste computador, ou None quando falta."""
    ds = services.datasets
    if kind == "file":
        return _found(lambda: ds.resolve(key))
    if kind == "folder":
        return _found(lambda: ds.folders.get(source_folder_id(key)))
    if kind == "pdf":
        ref = source_pdf_ref(key)
        return _found(lambda: ds.pdfs.get(ref[0])) if ref else None
    if kind == "query":
        return _found(lambda: services.queries.get(source_query_id(key)))
    if kind == "api":
        return _found(lambda: services.apis.get(source_api_id(key)))
    if kind == "jira":
        return _found(lambda: services.jira.query(source_jira_id(key)))
    if kind == "connection":
        return _found(lambda: services.connections.get(key))
    if kind == "subflow":
        return key if services.workflows.exists(key) else None
    if kind == "model":
        folder = ml_library.folder_of(services.runner.state_dir)
        return _found(lambda: ml_library.card(folder, key))
    return None


def _uses(workflow: Workflow) -> dict[tuple[str, str], list[str]]:
    """(tipo, chave) de cada fonte usada → as caixas que a usam."""
    uses: dict[tuple[str, str], list[str]] = {}
    for node in workflow.nodes:
        cfg = node.config
        found: tuple[str, str] | None = None
        if node.type == "io.input_data" and cfg.get("dataset"):
            source = str(cfg["dataset"])
            found = (kind_of(source), source)
        elif node.type == "io.api_loop" and cfg.get("source"):
            found = ("api", f"api:{cfg['source']}")
        elif node.type == "io.database_input" and cfg.get("connection"):
            found = ("connection", str(cfg["connection"]))
        elif node.type == "flow.subflow" and cfg.get("workflow"):
            found = ("subflow", str(cfg["workflow"]))
        elif node.type == "ml.model_input" and cfg.get("model"):
            found = ("model", str(cfg["model"]))
        if found:
            uses.setdefault(found, []).append(node.id)
    return uses


def check_sources(workflow: Workflow, services: Any) -> list[dict[str, Any]]:
    """Cada fonte do fluxo: ``ok`` (está aqui), ``sample`` (falta, mas veio a amostra) ou ``missing`` (falta)."""
    out = []
    for (kind, key), nodes in _uses(workflow).items():
        here = _lookup(services, kind, key)
        sample = workflow.samples.get(key)
        state = "ok" if here is not None else "sample" if sample is not None else "missing"
        # arquivo: o nome que o fluxo procura (a amostra pode ter vindo de um arquivo com outro nome)
        label = (
            key
            if kind == "file"
            else getattr(here, "name", None) or (sample.label if sample is not None else _label(kind, key))
        )
        if kind == "pdf" and sample is None and "/" in key:  # cada saída do PDF é uma fonte: diz qual
            label = f"{label} · {key.split('/', 1)[1].removeprefix('itens_')}"
        item: dict[str, Any] = {
            "key": key,
            "kind": kind,
            "kind_label": KIND_LABELS[kind],
            "label": label,
            "nodes": nodes,
            "state": state,
            "action": ACTIONS[kind],
        }
        if kind == "file" and here is not None:  # arquivo vinculado: lido de uma pasta só deste computador
            item["linked"] = key in services.datasets._links()
        if sample is not None:
            item["sample"] = {
                "linked": sample.linked,
                "rows": sample.rows,
                "created_at": sample.created_at.isoformat(),
                "size": sample.size(),
            }
        out.append(item)
    return out


def _label(kind: str, key: str) -> str:
    """Um nome para mostrar quando a fonte não está aqui: o arquivo, ou o identificador sem o prefixo."""
    return key.split(":", 1)[1] if kind in ("folder", "pdf", "query", "api", "jira") and ":" in key else key
