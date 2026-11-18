"""Etapa do laço no exemplo (spec 041): para cada segmento, os 3 clientes de maior MRR."""

from __future__ import annotations

from typing import Any

from prodata.samples.workflows import _container, _edge, _node

LOOP_NODES = ("n_laco_ini", "n_laco_ordem", "n_laco_top", "n_laco_fim")


def loop_section(y: int = 1120) -> dict[str, list[dict[str, Any]]]:
    """Etapa do laço (spec 041): para cada segmento, os 3 clientes de maior MRR, empilhados."""
    top = y + 108  # abaixo da descrição da etapa e do título da moldura do laço
    return {
        "containers": [
            {
                **_container(
                    "c_laco", "7 · Laço: os 3 maiores clientes de cada segmento", "#0e7490", 20, y, 1220, 196
                ),
                "description": "Para cada segmento, ordena pelo MRR e fica com os 3 primeiros. Abra uma caixa de dentro e "
                "escolha a volta na aba Resultado.",
            }
        ],
        "nodes": [
            _node(
                "n_laco_ini",
                "flow.loop_start",
                "Para cada segmento",
                0,
                top,
                mode="each",
                column="segmento",
                rows="group",
            ),
            _node(
                "n_laco_ordem",
                "prep.sort",
                "Maior MRR primeiro",
                1,
                top,
                sorts=[{"column": "mrr_mensal", "descending": True}],
            ),
            _node("n_laco_top", "prep.sample", "Os 3 primeiros", 2, top, mode="first", n=3),
            _node("n_laco_fim", "flow.loop_end", "Fim do loop", 3, top, start="n_laco_ini", output="stack"),
        ],
        "edges": [
            _edge("e_laco0", "n_join", "J", "n_laco_ini"),
            _edge("e_laco1", "n_laco_ini", "out", "n_laco_ordem"),
            _edge("e_laco2", "n_laco_ordem", "out", "n_laco_top"),
            _edge("e_laco3", "n_laco_top", "out", "n_laco_fim"),
        ],
    }


def add_loop_section(workflow: dict[str, Any]) -> bool:
    """Leva a etapa do laço a uma demonstração salva, abaixo do que já existe. Devolve se mudou algo."""
    ids = {n["id"] for n in workflow["nodes"]}
    if "n_join" not in ids or "n_laco_ini" in ids:
        return False
    bottom = max(
        [n["y"] + 56 for n in workflow["nodes"]]
        + [c["y"] + c["height"] for c in workflow.get("containers", [])]
    )
    section = loop_section(bottom + 20)
    workflow.setdefault("containers", []).extend(section["containers"])
    workflow["nodes"].extend(section["nodes"])
    workflow.setdefault("edges", []).extend(section["edges"])
    return True
