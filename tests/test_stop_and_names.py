"""Spec 041: Parar qualquer execução e nome dinâmico no Output Data."""

import threading
import time
from itertools import pairwise
from typing import Any

import pytest

from prodata.domain.workflow import Workflow
from prodata.engine.runner import WorkflowRunner
from prodata.errors import InvalidInputError
from prodata.nodes.output_names import fill, name_columns, piece

ROWS = [["N", 10], ["N", 20], ["S", 5], ["L/2", 1], [None, 3]]


def flow(nodes: list[dict[str, Any]], chain: list[str]) -> Workflow:
    return Workflow.model_validate(
        {
            "id": "parar",
            "nodes": [
                {
                    "id": "src",
                    "type": "io.text_input",
                    "config": {"table": {"columns": ["regiao", "valor"], "rows": ROWS}},
                },
                *nodes,
            ],
            "edges": [{"id": f"e{i}", "source": a, "target": b} for i, (a, b) in enumerate(pairwise(chain))],
        }
    )


def test_stop_skips_what_is_left(runner: WorkflowRunner) -> None:
    slow = [
        {
            "id": "ini",
            "type": "flow.loop_start",
            "config": {"mode": "range", "start": "1", "end": "3000", "max_iterations": 5000},
        },
        {
            "id": "f",
            "type": "prep.formula",
            "config": {
                "formulas": [{"target": "new", "column": "x", "type": "Auto", "expression": "[#volta]"}]
            },
        },
        {"id": "fim", "type": "flow.loop_end", "config": {"start": "ini", "output": "last"}},
        {"id": "depois", "type": "prep.select", "config": {}},
    ]
    wf = flow(slow, ["src", "ini", "f", "fim", "depois"])
    box: dict[str, Any] = {}
    worker = threading.Thread(target=lambda: box.update(report=runner.run(wf)))
    worker.start()
    for _ in range(400):
        if str(runner.progress(wf.id).get("detail") or "").startswith("volta"):
            break
        time.sleep(0.01)
    assert runner.cancel(wf.id)
    worker.join(60)
    results = box["report"].node_results
    assert results["src"].status in ("executed", "cached")
    assert results["depois"].status == "skipped" and results["depois"].extra["stopped"]
    assert not runner.cancel(wf.id)  # nada rodando: nada a parar


def test_dynamic_name_writes_one_file_per_value(runner: WorkflowRunner) -> None:
    out = {
        "id": "grava",
        "type": "io.output_data",
        "config": {"filename": "vendas_{regiao}", "format": "csv", "if_exists": "replace"},
    }
    report = runner.run(flow([out], ["src", "grava"]))
    result = report.node_results["grava"]
    assert result.status == "executed", result.error
    names = sorted(p.name for p in runner.exports_dir.glob("vendas_*.csv"))
    assert names == ["vendas_L_2.csv", "vendas_N.csv", "vendas_S.csv", "vendas_vazio.csv"]
    assert len(result.extra["exported_files"]) == 4


def test_dynamic_name_never_overwrites_when_asking(runner: WorkflowRunner) -> None:
    out = {
        "id": "grava",
        "type": "io.output_data",
        "config": {"filename": "x_{regiao}", "format": "csv", "if_exists": "ask"},
    }
    wf = flow([out], ["src", "grava"])
    runner.run(wf)
    runner.run(wf)
    assert len(list(runner.exports_dir.glob("x_N*.csv"))) == 2  # a segunda vez cria outro, com data e hora


def test_dynamic_name_in_a_loop(runner: WorkflowRunner) -> None:
    nodes = [
        {"id": "ini", "type": "flow.loop_start", "config": {"mode": "each", "column": "regiao"}},
        {
            "id": "grava",
            "type": "io.output_data",
            "config": {"filename": "laco_{regiao}", "format": "csv", "if_exists": "replace"},
        },
        {"id": "fim", "type": "flow.loop_end", "config": {"start": "ini"}},
    ]
    report = runner.run(flow(nodes, ["src", "ini", "grava", "fim"]))
    assert report.node_results["fim"].status == "executed", report.node_results["fim"].error
    assert len(list(runner.exports_dir.glob("laco_*.csv"))) == 4
    assert not report.node_results["grava"].extra.get(
        "warnings"
    )  # a coluna no nome resolve: sem aviso de sobrescrever


def test_name_helpers() -> None:
    assert name_columns("vendas_{regiao}_{ano}", ["regiao", "ano"]) == ["regiao", "ano"]
    with pytest.raises(InvalidInputError, match="não existe"):
        name_columns("vendas_{nada}", ["regiao"])
    assert piece('a:b/c*"d') == "a_b_c_d" and piece(None) == "vazio" and piece("") == "vazio"
    assert fill("v_{regiao}", {"regiao": "SP"}) == "v_SP"
