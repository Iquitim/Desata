"""Mudanças no formato das fontes (spec 046, RF-4601..4609)."""

from __future__ import annotations

import io
from pathlib import Path

import polars as pl
import pytest

from prodata.domain.schemas import ColumnSpec, RememberedSchema
from prodata.domain.workflow import Workflow
from prodata.engine import schema_drift as drift
from prodata.engine.runner import WorkflowRunner
from prodata.ingestion import DatasetStore


def cols(*pairs: str) -> list[ColumnSpec]:
    return [ColumnSpec(name=p.split(":")[0], type=p.split(":")[1]) for p in pairs]


# ---------------------------------------------------------------- diferença e renome


def test_diff_lists_new_missing_and_retyped() -> None:
    d = drift.diff(
        cols("id:Int64", "valor:Float64", "uf:String"), cols("id:Int64", "valor:String", "regiao:String")
    )
    assert d.added == ["regiao"] and d.removed == ["uf"]
    assert [(r.name, r.old, r.new) for r in d.retyped] == [("valor", "Float64", "String")]
    assert drift.diff(cols("a:Int64"), cols("a:Int64")).empty


def test_rename_hint_needs_the_same_type() -> None:
    old = cols("id:Int64", "valor:Float64")
    assert drift.diff(old, cols("id:Int64", "valor_total:Float64")).renames == [("valor", "valor_total")]
    # sumiu um número e apareceu um texto: nada de sugestão, mesmo com nome parecido
    assert drift.diff(old, cols("id:Int64", "valor_txt:String")).renames == []


def test_rename_hint_with_several_candidates_uses_the_position() -> None:
    old = cols("a:Float64", "b:Float64", "c:Float64")
    new = cols("a:Float64", "b2:Float64", "x:Float64", "c:Float64")
    assert drift.diff(old, new).renames == [("b", "b2")]


def test_type_examples_show_what_broke_the_old_type() -> None:
    s = pl.Series("valor", ["10,5", "N/D", "20", "—", "N/D"])
    assert drift.type_examples(s, "Float64") == ["N/D", "—"]


# ---------------------------------------------------------------- fórmulas


def test_expression_columns_ignore_text_and_constants() -> None:
    expr = "IF [valor] > [#limite] THEN '[valor] alto' ELSE [Row-1:valor] + [desconto] ENDIF"
    assert drift.expression_columns(expr) == {"valor", "desconto"}


def test_rename_in_expression_keeps_the_rest() -> None:
    expr = "IF [valor] > 0 THEN '[valor]' ELSE [Row-1:valor] ENDIF"
    assert drift.rename_in_expression(expr, "valor", "valor_total") == (
        "IF [valor_total] > 0 THEN '[valor]' ELSE [Row-1:valor_total] ENDIF"
    )


# ---------------------------------------------------------------- caixas atingidas e troca


def flow() -> Workflow:
    return Workflow.model_validate({
        "id": "drift",
        "nodes": [
            {"id": "src", "type": "io.input_data", "config": {"dataset": "vendas.csv"}},
            {"id": "sel", "type": "prep.select", "config": {"fields": [{"name": "valor", "rename": "Receita"}]}},
            {"id": "f", "type": "prep.formula", "config": {"formulas": [{"name": "dobro", "expression": "[valor] * 2"}]}},
            {"id": "s", "type": "transform.summarize",
             "config": {"group_by": ["uf"], "aggregations": [{"column": "valor", "agg": "sum"}]}},
            {"id": "after", "type": "prep.filter", "config": {"mode": "custom", "expression": "[valor] > 0"}},
            {"id": "sql", "type": "transform.sql_query", "config": {"sql": "SELECT uf, valor FROM entrada"}},
        ],
        "edges": [
            {"id": "e1", "source": "src", "target": "sel"},
            {"id": "e2", "source": "src", "target": "f"},
            {"id": "e3", "source": "f", "target": "s"},
            {"id": "e4", "source": "sel", "target": "after"},
            {"id": "e5", "source": "src", "target": "sql"},
        ],
    })  # fmt: skip


def test_impact_follows_the_wires_until_the_name_changes() -> None:
    found = drift.impact(flow(), "src", ["valor"])["valor"]
    # o Select renomeia valor para Receita: o Filter depois dele usa outra coluna, não esta
    assert set(found.nodes) == {"sel", "f", "s"}
    assert found.maybe == {"sql"}  # SQL livre: só "talvez"


def test_rename_column_in_every_kind_of_field() -> None:
    wf = flow()
    found = drift.impact(wf, "src", ["valor"])["valor"]
    for node_id, ports in found.nodes.items():
        node = wf.node(node_id)
        assert drift.rename_column(node.config, node.type, ports, "in", "valor", "valor_total")
    assert wf.node("sel").config["fields"] == [
        {"name": "valor_total", "rename": "Receita"}
    ]  # o renome continua
    assert wf.node("f").config["formulas"][0]["expression"] == "[valor_total] * 2"
    assert wf.node("s").config["aggregations"][0]["column"] == "valor_total"
    assert wf.node("sql").config["sql"] == "SELECT uf, valor FROM entrada"  # texto livre nunca é alterado


def test_join_keys_follow_the_port() -> None:
    wf = Workflow.model_validate({
        "id": "j",
        "nodes": [
            {"id": "a", "type": "io.input_data", "config": {"dataset": "a.csv"}},
            {"id": "b", "type": "io.input_data", "config": {"dataset": "b.csv"}},
            {"id": "j", "type": "transform.join", "config": {"keys": [{"left": "id", "right": "id"}]}},
        ],
        "edges": [
            {"id": "e1", "source": "a", "target": "j", "targetHandle": "L"},
            {"id": "e2", "source": "b", "target": "j", "targetHandle": "R"},
        ],
    })  # fmt: skip
    found = drift.impact(wf, "a", ["id"])["id"]
    assert found.nodes == {"j": {"L"}}
    node = wf.node("j")
    drift.rename_column(node.config, node.type, {"L"}, "L", "id", "codigo")
    assert node.config["keys"] == [{"left": "codigo", "right": "id"}]  # o lado direito não muda


# ---------------------------------------------------------------- execução


def save_csv(store: DatasetStore, text: str) -> str:
    return store.save("vendas_drift.csv", io.BytesIO(text.encode()), overwrite=True).name


def drift_flow(dataset: str, export_dir: Path, **output: object) -> Workflow:
    return Workflow.model_validate({
        "id": "drift_run",
        "nodes": [
            {"id": "src", "type": "io.input_data", "config": {"dataset": dataset}},
            {"id": "f", "type": "prep.formula", "config": {"formulas": [{"name": "dobro", "expression": "[valor] * 2"}]}},
            {"id": "out", "type": "io.output_data",
             "config": {"filename": "saida", "format": "csv", "folder": str(export_dir), "if_exists": "replace", **output}},
        ],
        "edges": [{"id": "e1", "source": "src", "target": "f"}, {"id": "e2", "source": "f", "target": "out"}],
    })  # fmt: skip


def remember(wf: Workflow, result_extra: dict, node_id: str) -> None:
    wf.schemas[node_id] = RememberedSchema(ports={
        p: [ColumnSpec(**c) for c in cs] for p, cs in result_extra["schema"].items()
    })  # fmt: skip


def test_first_read_only_remembers_then_reports_the_change(
    runner: WorkflowRunner, store: DatasetStore, tmp_path: Path
) -> None:
    name = save_csv(store, "uf;valor\nSP;10\nRJ;20\n")
    wf = drift_flow(name, tmp_path)
    first = runner.run(wf).node_results
    assert "schema_change" not in first["src"].extra
    assert [c["name"] for c in first["src"].extra["schema"]["out"]] == ["uf", "valor"]
    remember(wf, first["src"].extra, "src")
    save_csv(store, "uf;valor_total;desconto\nSP;10;1\nRJ;20;2\n")
    change = runner.run(wf).node_results["src"].extra["schema_change"]
    assert change["added"] == ["valor_total", "desconto"] and change["removed"] == ["valor"]
    assert change["renames"][0]["old"] == "valor" and change["renames"][0]["new"] == "valor_total"
    assert change["renames"][0]["values"] == ["10", "20"]
    assert change["affected"]["valor"] == {"f": ["in"]}


def test_unattended_run_stops_before_any_output(
    runner: WorkflowRunner, store: DatasetStore, tmp_path: Path
) -> None:
    name = save_csv(store, "uf;valor\nSP;10\n")
    wf = drift_flow(name, tmp_path)
    remember(wf, runner.run(wf).node_results["src"].extra, "src")
    (tmp_path / "saida.csv").unlink()
    save_csv(store, "uf;valor_total\nSP;10\n")
    results = runner.run(wf, unattended=True).node_results
    assert results["src"].status == "error"
    assert "A coluna 'valor' sumiu" in (results["src"].error or "") and "1 caixa" in (
        results["src"].error or ""
    )
    assert results["out"].status == "skipped" and not (tmp_path / "saida.csv").exists()


def test_new_column_stops_only_when_asked(
    runner: WorkflowRunner, store: DatasetStore, tmp_path: Path
) -> None:
    name = save_csv(store, "uf;valor\nSP;10\n")
    wf = drift_flow(name, tmp_path)
    remember(wf, runner.run(wf).node_results["src"].extra, "src")
    save_csv(store, "uf;valor;extra\nSP;10;x\n")
    assert runner.run(wf, unattended=True).node_results["out"].status == "executed"  # padrão: seguir
    wf.node("src").config["on_new_columns"] = "parar"
    results = runner.run(wf, unattended=True).node_results
    assert results["src"].status == "error" and "coluna nova" in (results["src"].error or "")
    # com alguém olhando, o fluxo executa e só avisa
    assert runner.run(wf).node_results["out"].status == "executed"


def test_output_warns_and_can_stop_when_its_format_changes(
    runner: WorkflowRunner, store: DatasetStore, tmp_path: Path
) -> None:
    name = save_csv(store, "uf;valor\nSP;10\n")
    wf = drift_flow(name, tmp_path)
    remember(wf, runner.run(wf).node_results["out"].extra, "out")
    save_csv(store, "uf;valor;extra\nSP;10;x\n")
    out = runner.run(wf).node_results["out"]
    assert out.status == "executed" and any("formato diferente" in w for w in out.extra["warnings"])
    assert out.extra["schema_change"]["in"]["added"] == ["extra"]
    (tmp_path / "saida.csv").unlink()
    wf.node("out").config["stop_on_schema_change"] = True
    out = runner.run(wf).node_results["out"]
    assert out.status == "error" and "Nada foi gravado" in (out.error or "")
    assert not (tmp_path / "saida.csv").exists()


@pytest.mark.parametrize("policy", ["seguir", "parar"])
def test_policy_field_is_declarative(policy: str) -> None:
    from prodata.nodes import REGISTRY

    for tool in ("io.input_data", "io.input_folder", "io.database_input"):
        cfg = REGISTRY[tool].config.model_validate({"on_new_columns": policy})
        assert cfg.on_new_columns == policy  # type: ignore[attr-defined]


def test_folder_says_which_files_miss_a_column(tmp_path: Path) -> None:
    from prodata.ingestion.folders import missing_columns, read_folder
    from prodata.ingestion.options import ReadOptions

    folder = tmp_path / "pasta"
    folder.mkdir()
    (folder / "jan.csv").write_text("uf;valor;desconto\nSP;1;0\n", encoding="utf-8")
    (folder / "fev.csv").write_text("uf;valor\nSP;2\n", encoding="utf-8")
    (folder / "mar.csv").write_text("uf;valor\nRJ;3\n", encoding="utf-8")
    seen: dict[str, list[str]] = {}
    table, _odd = read_folder(sorted(folder.glob("*.csv")), ReadOptions(), "", seen=seen)
    assert table.columns == ["uf", "valor", "desconto"]  # o formato é o conjunto da pasta
    missing, phrases = missing_columns(seen)
    assert missing == {"desconto": ["fev.csv", "mar.csv"]}
    assert phrases == [
        "2 arquivos sem a coluna 'desconto' (fev.csv, mar.csv): nesses arquivos ela fica vazia."
    ]
