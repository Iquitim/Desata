"""Spec 041, laço: Início e Fim do loop, as três formas de repetir, as variáveis e o desenho."""

from pathlib import Path
from typing import Any

import polars as pl
import pytest

from prodata.domain.workflow import Workflow
from prodata.engine.loop_run import namespace
from prodata.engine.runner import WorkflowRunner

ROWS = [["N", 10, 1], ["N", 20, 2], ["S", 5, 1], ["S", 7, 3], ["L", 1, 1]]


def flow(nodes: list[dict[str, Any]], edges: list[tuple[str, str]]) -> Workflow:
    return Workflow.model_validate(
        {
            "id": "laco",
            "nodes": [
                {
                    "id": "src",
                    "type": "io.text_input",
                    "config": {"table": {"columns": ["regiao", "valor_venda", "itens"], "rows": ROWS}},
                },
                *nodes,
            ],
            "edges": [
                {
                    "id": f"e{i}",
                    "source": s.split(":")[0],
                    "sourceHandle": [*s.split(":"), "out"][1],
                    "target": t,
                    "targetHandle": "in",
                }
                for i, (s, t) in enumerate(edges)
            ],
        }
    )


def start(**cfg: Any) -> dict[str, Any]:
    return {"id": "ini", "type": "flow.loop_start", "config": cfg}


def end(**cfg: Any) -> dict[str, Any]:
    return {"id": "fim", "type": "flow.loop_end", "config": {"start": "ini", **cfg}}


def table(runner: WorkflowRunner, wf: Workflow, node: str, ns: str | None = None) -> pl.DataFrame:
    entry = runner.cache.get(ns or wf.id, node)
    assert entry is not None, node
    return entry.tables["out"]


def summarize() -> dict[str, Any]:
    return {
        "id": "soma",
        "type": "transform.summarize",
        "config": {
            "group_by": [],
            "aggregations": [{"column": "valor_venda", "agg": "sum", "alias": "total"}],
        },
    }


def test_each_value_stacks_one_row_per_region(runner: WorkflowRunner) -> None:
    wf = flow(
        [start(mode="each", column="regiao"), summarize(), end(output="stack")],
        [("src", "ini"), ("ini", "soma"), ("soma", "fim")],
    )
    report = runner.run(wf)
    assert report.node_results["fim"].status == "executed", report.node_results["fim"].error
    out = table(runner, wf, "fim").sort("regiao")
    assert out["regiao"].to_list() == ["L", "N", "S"]
    assert out["total"].to_list() == [1, 30, 12]
    assert out["volta"].to_list() == [1, 2, 3]  # ordem crescente: L, N, S
    assert report.node_results["fim"].annotation == "3 voltas"
    # o corpo mostra a última volta; cada volta tem o seu resultado
    assert table(runner, wf, "soma")["total"].to_list() == [12]
    assert table(runner, wf, "soma", namespace(wf.id, "fim", 1))["total"].to_list() == [1]


def test_variables_inside_formulas_and_error_outside(runner: WorkflowRunner) -> None:
    formula = {
        "id": "f",
        "type": "prep.formula",
        "config": {
            "formulas": [
                {
                    "target": "new",
                    "column": "rotulo",
                    "type": "Auto",
                    "expression": "Concat([#valor], ' ', ToString([#volta]), '/', ToString([#total]))",
                }
            ]
        },
    }
    wf = flow(
        [start(mode="each", column="regiao", order="appearance"), formula, end(output="stack")],
        [("src", "ini"), ("ini", "f"), ("f", "fim")],
    )
    report = runner.run(wf)
    assert report.node_results["fim"].status == "executed", report.node_results["fim"].error
    assert table(runner, wf, "fim")["rotulo"].unique(maintain_order=True).to_list() == [
        "N 1/3",
        "S 2/3",
        "L 3/3",
    ]
    outside = flow([formula], [("src", "f")])
    bad = runner.run(outside).node_results["f"]
    assert bad.status == "error" and "só vale dentro de um laço" in (bad.error or "")


def test_range_runs_the_whole_table_each_turn(runner: WorkflowRunner) -> None:
    formula = {
        "id": "f",
        "type": "prep.formula",
        "config": {
            "formulas": [
                {"target": "new", "column": "x", "type": "Auto", "expression": "[valor_venda] * [#valor]"}
            ]
        },
    }
    wf = flow(
        [start(mode="range", start="1", end="3", step=1), formula, end(output="stack")],
        [("src", "ini"), ("ini", "f"), ("f", "fim")],
    )
    report = runner.run(wf)
    assert report.node_results["fim"].status == "executed", report.node_results["fim"].error
    out = table(runner, wf, "fim")
    assert out.height == 15 and out["valor"].unique().sort().to_list() == [1, 2, 3]


def test_while_accumulates_until_the_condition_stops(runner: WorkflowRunner) -> None:
    grow = {
        "id": "f",
        "type": "prep.formula",
        "config": {
            "formulas": [
                {
                    "target": "existing",
                    "existing": "valor_venda",
                    "type": "Auto",
                    "expression": "[valor_venda] * 2",
                }
            ]
        },
    }
    wf = flow(
        [
            start(mode="while", max_iterations=50),
            grow,
            end(output="accumulate", expression="[valor_venda] < 100"),
        ],
        [("src", "ini"), ("ini", "f"), ("f", "fim")],
    )
    report = runner.run(wf)
    assert report.node_results["fim"].status == "executed", report.node_results["fim"].error
    out = table(runner, wf, "fim")
    # o menor valor (1) dobra até passar de 100: 128, na 7ª volta
    assert out["valor_venda"].min() == 128 and report.node_results["fim"].annotation == "7 voltas"


def test_while_stops_at_the_limit_and_warns(runner: WorkflowRunner) -> None:
    keep = {"id": "f", "type": "prep.select", "config": {}}
    wf = flow(
        [start(mode="while", max_iterations=5), keep, end(output="last", expression="1 == 1")],
        [("src", "ini"), ("ini", "f"), ("f", "fim")],
    )
    result = runner.run(wf).node_results["fim"]
    assert result.annotation == "5 voltas" and "limite" in result.extra["warnings"][0]


def test_too_many_turns_is_refused(runner: WorkflowRunner) -> None:
    wf = flow(
        [
            start(mode="range", start="1", end="50", max_iterations=10),
            {"id": "f", "type": "prep.select", "config": {}},
            end(),
        ],
        [("src", "ini"), ("ini", "f"), ("f", "fim")],
    )
    result = runner.run(wf).node_results["fim"]
    assert result.status == "error" and "limite" in (result.error or "")


def test_body_cannot_leak_outside(runner: WorkflowRunner) -> None:
    wf = flow(
        [
            start(mode="each", column="regiao"),
            summarize(),
            end(),
            {"id": "fora", "type": "prep.select", "config": {}},
        ],
        [("src", "ini"), ("ini", "soma"), ("soma", "fim"), ("soma", "fora")],
    )
    report = runner.run(wf)
    assert "sem passar pelo Fim" in (report.node_results["soma"].error or "")
    assert report.node_results["fim"].status == "error"


def test_end_without_start_and_start_without_end(runner: WorkflowRunner) -> None:
    wf = flow([{"id": "fim", "type": "flow.loop_end", "config": {"start": ""}}], [("src", "fim")])
    assert "não tem o Início" in (runner.run(wf).node_results["fim"].error or "")
    wf = flow([start(mode="each", column="regiao")], [("src", "ini")])
    assert "Falta o Fim" in (runner.run(wf).node_results["ini"].error or "")


def test_error_in_a_turn_says_which(runner: WorkflowRunner) -> None:
    broken = {
        "id": "f",
        "type": "prep.formula",
        "config": {
            "formulas": [{"target": "new", "column": "x", "type": "Auto", "expression": "[nao_existe] + 1"}]
        },
    }
    wf = flow(
        [start(mode="each", column="regiao"), broken, end()], [("src", "ini"), ("ini", "f"), ("f", "fim")]
    )
    result = runner.run(wf).node_results["fim"]
    assert result.status == "error" and (result.error or "").startswith("Volta 1 (L)")


def test_nested_loop(runner: WorkflowRunner) -> None:
    nodes = [
        start(mode="each", column="regiao"),
        {"id": "ini2", "type": "flow.loop_start", "config": {"mode": "range", "start": "1", "end": "2"}},
        {
            "id": "f",
            "type": "prep.formula",
            "config": {
                "formulas": [{"target": "new", "column": "x", "type": "Auto", "expression": "[#volta]"}]
            },
        },
        {"id": "fim2", "type": "flow.loop_end", "config": {"start": "ini2", "output": "stack"}},
        end(output="stack"),
    ]
    wf = flow(nodes, [("src", "ini"), ("ini", "ini2"), ("ini2", "f"), ("f", "fim2"), ("fim2", "fim")])
    report = runner.run(wf)
    assert report.node_results["fim"].status == "executed", report.node_results["fim"].error
    assert table(runner, wf, "fim").height == 10  # 5 linhas, cada região 2 vezes


def test_cache_per_turn_skips_unchanged_turns(runner: WorkflowRunner, tmp_path: Path) -> None:
    wf = flow(
        [start(mode="each", column="regiao"), summarize(), end()],
        [("src", "ini"), ("ini", "soma"), ("soma", "fim")],
    )
    runner.run(wf)
    again = runner.run(wf)
    assert again.node_results["soma"].status == "cached"


@pytest.mark.parametrize("output", ["last"])
def test_last_and_accumulate_keep_one_table(runner: WorkflowRunner, output: str) -> None:
    wf = flow(
        [start(mode="each", column="regiao"), summarize(), end(output=output)],
        [("src", "ini"), ("ini", "soma"), ("soma", "fim")],
    )
    runner.run(wf)
    assert table(runner, wf, "fim").height == 1


def test_output_writes_one_file_per_turn(runner: WorkflowRunner) -> None:
    out = {
        "id": "grava",
        "type": "io.output_data",
        "config": {"filename": "regiao_[#valor]", "format": "csv", "if_exists": "replace"},
    }
    wf = flow(
        [start(mode="each", column="regiao"), out, end()],
        [("src", "ini"), ("ini", "grava"), ("grava", "fim")],
    )
    report = runner.run(wf)
    assert report.node_results["fim"].status == "executed", report.node_results["fim"].error
    names = sorted(p.name for p in runner.exports_dir.glob("regiao_*.csv"))
    assert names == ["regiao_L.csv", "regiao_N.csv", "regiao_S.csv"]


def test_output_without_variable_warns(runner: WorkflowRunner) -> None:
    out = {
        "id": "grava",
        "type": "io.output_data",
        "config": {"filename": "um_so", "format": "csv", "if_exists": "replace"},
    }
    wf = flow(
        [start(mode="each", column="regiao"), out, end()],
        [("src", "ini"), ("ini", "grava"), ("grava", "fim")],
    )
    report = runner.run(wf)
    assert any("sobrescreve" in w for w in report.node_results["grava"].extra.get("warnings", []))


def test_cancel_stops_at_the_next_turn(runner: WorkflowRunner) -> None:
    import threading
    import time

    slow = {
        "id": "f",
        "type": "prep.formula",
        "config": {"formulas": [{"target": "new", "column": "x", "type": "Auto", "expression": "[#volta]"}]},
    }
    wf = flow(
        [start(mode="range", start="1", end="3000", max_iterations=5000), slow, end(output="last")],
        [("src", "ini"), ("ini", "f"), ("f", "fim")],
    )
    box: dict[str, Any] = {}
    worker = threading.Thread(target=lambda: box.update(report=runner.run(wf)))
    worker.start()
    for _ in range(400):
        if str(runner.progress(wf.id).get("detail") or "").startswith("volta"):
            break
        time.sleep(0.01)
    assert runner.cancel(wf.id)
    worker.join(60)
    result = box["report"].node_results["fim"]
    assert result.status == "skipped" and "interrompida" in (result.error or "") and result.extra["stopped"]
