"""Confiança por diferença (spec 047, RF-4741, RF-4742).

Um fluxo do espaço com assinatura válida abre liberado. Só pede conferência quando, desde a última versão que esta
pessoa abriu liberada ou confiou, ganhou ou mudou uma **parte sensível**: onde lê ou grava arquivos, consultas a banco,
APIs, caixa SQL, subfluxos. Filtros, fórmulas e layout não pedem nada.

O que fica guardado neste computador é só a "assinatura" de cada parte sensível (caixa → tipo e detalhe), nunca o
fluxo nem os dados.
"""

from __future__ import annotations

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
