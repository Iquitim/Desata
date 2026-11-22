"""Confiança por diferença (spec 047, RF-4741, RF-4742).

Um fluxo do espaço com assinatura válida abre liberado. Só pede conferência quando, desde a última versão que esta
pessoa abriu liberada ou confiou, ganhou ou mudou uma **parte sensível**: onde lê ou grava arquivos, consultas a banco,
APIs, caixa SQL, subfluxos. Filtros, fórmulas e layout não pedem nada.

O que fica guardado neste computador é só a "assinatura" de cada parte sensível (caixa → tipo e detalhe), nunca o
fluxo nem os dados.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from prodata.domain.workflow import Workflow
from prodata.services.trust import summary

SENSITIVE = frozenset({"file", "folder", "api", "query", "sql", "subflow", "output"})


def sensitive_parts(workflow: Workflow) -> dict[str, str]:
    """Caixa → "tipo|detalhe" de cada parte sensível. Sem nomes cadastrados: compara o que está no fluxo."""
    return {
        str(item["node_id"]): f"{item['kind']}|{item['detail']}"
        for item in summary(workflow, {}, set())
        if item["kind"] in SENSITIVE
    }


def changed_parts(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """As caixas com parte sensível nova ou alterada. Uma parte que saiu não pede conferência (o fluxo faz menos)."""
    return [node for node, key in after.items() if before.get(node) != key]


# ---------------------------------------------------------------- definições da equipe (spec 048, RF-4806)

DEF_MARK = "#def:"  # o que vem depois é a impressão da definição da equipe que a caixa usa


def _print(data: dict[str, Any]) -> str:
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def definition_prints(workflow: Workflow, defs: Any) -> dict[str, str]:
    """Caixa → impressão das partes sensíveis da definição da equipe que ela lê: servidor, banco e tipo da conexão;
    endereço, método, parâmetros e corpo da API; o SQL da consulta (com a conexão dela). Nome e descrição ficam de
    fora: mudar só isso não pede conferência."""
    if defs is None:
        return {}

    def connection(cid: str) -> dict[str, Any] | None:
        conn = defs.get("conexoes", cid)
        if conn is None:
            return None
        return {k: getattr(conn, k) for k in ("kind", "host", "port", "database", "user", "odbc_dsn")}

    out: dict[str, str] = {}
    for node in workflow.nodes:
        cfg = node.config
        found: dict[str, Any] | None = None
        dataset = str(cfg.get("dataset") or "") if node.type == "io.input_data" else ""
        if dataset.startswith("sql:"):
            query = defs.get("consultas", dataset[4:])
            if query is not None:
                found = {"sql": [query.connection, query.mode, query.table, query.query],
                         "conexao": connection(query.connection)}  # fmt: skip
        api_id = (
            dataset[4:]
            if dataset.startswith("api:")
            else (cfg.get("source") if node.type == "io.api_loop" else None)
        )
        if api_id:
            api = defs.get("apis", str(api_id))
            if api is not None:
                found = {"api": [api.url, api.method, api.body,
                                 [(p.name, p.value) for p in api.params if not p.secret],
                                 [(p.name, p.value) for p in api.headers if not p.secret]]}  # fmt: skip
        if node.type == "io.database_input" and cfg.get("connection"):
            found = {"conexao": connection(str(cfg["connection"]))}
        if found and any(v is not None for v in found.values()):
            out[node.id] = _print(found)
    return out


def with_definitions(parts: dict[str, str], prints: dict[str, str]) -> dict[str, str]:
    """As partes sensíveis do fluxo mais a impressão das definições da equipe que cada caixa lê."""
    out = {node: f"{key}{DEF_MARK}{prints[node]}" if node in prints else key for node, key in parts.items()}
    for node, value in prints.items():
        out.setdefault(node, f"definicao{DEF_MARK}{value}")
    return out


def flow_only(parts: dict[str, str]) -> dict[str, str]:
    return {node: key.split(DEF_MARK)[0] for node, key in parts.items()}
