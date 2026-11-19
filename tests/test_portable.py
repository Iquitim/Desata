"""Spec 040: o fluxo em outro computador. O que falta aparece, e a amostra que viaja com o fluxo roda no lugar."""

import json
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from fastapi.testclient import TestClient

from prodata.config import Settings
from prodata.domain.samples import MAX_ROWS, SourceSample
from prodata.domain.workflow import Workflow
from prodata.engine.runner import WorkflowRunner
from prodata.main import create_app


def _flow(**extra: Any) -> dict[str, Any]:
    return {
        "id": "de_fora",
        "name": "De fora",
        "nodes": [
            {"id": "a", "type": "io.input_data", "config": {"dataset": "clientes_enterprise.csv"}},
            {"id": "b", "type": "io.input_data", "config": {"dataset": "fantasma.csv"}},
            {"id": "c", "type": "io.input_data", "config": {"dataset": "api:nao_cadastrada"}},
            {"id": "d", "type": "flow.subflow", "config": {"workflow": "subfluxo_que_falta"}},
        ],
        "edges": [],
        **extra,
    }


def test_sources_that_are_missing_here(client: TestClient) -> None:
    """CA-05: cada fonte do fluxo, de todos os tipos, e o que falta neste computador."""
    out = client.post("/api/portable/sources", json={"workflow": _flow()}).json()
    by_key = {s["key"]: s for s in out["sources"]}
    assert by_key["clientes_enterprise.csv"]["state"] == "ok"
    assert (
        by_key["fantasma.csv"]["state"] == "missing"
        and by_key["fantasma.csv"]["action"] == "Escolher o arquivo"
    )
    assert (
        by_key["api:nao_cadastrada"]["state"] == "missing"
        and by_key["api:nao_cadastrada"]["label"] == "nao_cadastrada"
    )
    assert (
        by_key["subfluxo_que_falta"]["kind"] == "subflow"
        and by_key["subfluxo_que_falta"]["state"] == "missing"
    )
    assert out["missing"] == 3


def test_the_demo_has_everything_here(client: TestClient) -> None:
    demo = client.get("/api/workflows/demo_pipeline_360").json()
    out = client.post("/api/portable/sources", json={"workflow": demo}).json()
    assert out["missing"] == 0 and len(out["sources"]) >= 5


def test_sample_is_read_only_when_the_source_is_missing(runner: WorkflowRunner) -> None:
    """CA-06: sem a fonte, o Input Data lê a amostra e avisa; com a fonte de verdade presente, a amostra é ignorada."""
    fake = pl.DataFrame({"id": [1, 2], "nome": ["a", "b"]})
    samples = {
        "fantasma.csv": SourceSample.of(fake, "Clientes do outro computador").model_dump(mode="json"),
        "clientes_enterprise.csv": SourceSample.of(fake, "não deve ser usada").model_dump(mode="json"),
    }
    flow = Workflow.model_validate({**_flow(), "nodes": _flow()["nodes"][:2], "samples": samples})
    report = runner.run(flow)
    b = report.node_results["b"]
    assert b.status == "executed" and b.extra.get("sample") is True
    assert any("amostra" in w for w in b.extra["warnings"])
    assert runner.cache.get(flow.id, "b").tables["out"].equals(fake)
    real = runner.cache.get(flow.id, "a").tables["out"]
    assert real.height > 2 and "sample" not in report.node_results["a"].extra


def test_missing_source_without_sample_says_where_to_fix(runner: WorkflowRunner) -> None:
    flow = Workflow.model_validate({**_flow(), "nodes": [_flow()["nodes"][1]]})
    report = runner.run(flow)
    assert report.node_results["b"].status == "error"
    assert "Faltam neste computador" in (report.node_results["b"].error or "")


def test_sample_respects_the_limits() -> None:
    big = pl.DataFrame({"n": range(5000)})
    assert SourceSample.of(big, "x").rows == MAX_ROWS
    huge = SourceSample(label="x", rows=1, data="A" * (8 * 1024 * 1024))
    with pytest.raises(ValueError, match="5 MB"):
        Workflow.model_validate({**_flow(), "samples": {"a.csv": huge.model_dump(mode="json")}})


@pytest.mark.lento
def test_share_with_sample_and_open_on_another_computer(client: TestClient, tmp_path: Path) -> None:
    """CA-06/CA-07: grava com a amostra das fontes escolhidas, sem caminho nem segredo; noutro computador, roda."""
    demo = client.get("/api/workflows/demo_pipeline_360").json()
    preview = client.post("/api/portable/share/preview", json={"workflow": demo}).json()
    chosen = [s["key"] for s in preview["sources"] if s["chosen"]][:2]
    assert len(chosen) == 2 and preview["total"] <= preview["limit"]
    target = tmp_path / "compartilhar" / "pipeline.prodata.json"
    target.parent.mkdir()
    saved = client.post(
        "/api/portable/share/save",
        json={"workflow": demo, "path": str(target), "sources": {k: {"rows": 1000} for k in chosen}},
    ).json()
    raw = json.loads(target.read_text(encoding="utf-8"))
    assert sorted(raw["samples"]) == sorted(chosen) == sorted(saved["workflow"]["samples"])
    text = target.read_text(encoding="utf-8")
    assert str(tmp_path) not in text and "storage" not in text  # nenhum caminho local no arquivo

    # outro computador: pasta de dados nova, sem os arquivos de exemplo
    other = Settings(
        storage_dir=tmp_path / "outro",
        log_level="WARNING",
        secrets_backend="memory",
        allowed_hosts=["testserver"],
        seed_samples=False,
    )
    with TestClient(create_app(other)) as there:
        opened = there.post("/api/files/workflow/open", json={"path": str(target)}).json()["workflow"]
        check = {
            s["key"]: s["state"]
            for s in there.post("/api/portable/sources", json={"workflow": opened}).json()["sources"]
        }
        assert all(check[k] == "sample" for k in chosen)
        flow = {
            **opened,
            "nodes": [
                n
                for n in opened["nodes"]
                if n["type"] == "io.input_data" and n["config"].get("dataset") in chosen
            ],
        }
        flow["edges"] = []
        there.post("/api/trust/confirm", json={"workflow": flow})
        report = there.post("/api/execute", json={"workflow": flow}).json()
        assert all(
            r["status"] == "executed" and r["extra"].get("sample") for r in report["node_results"].values()
        )


def test_personal_columns_are_suggested_for_masking() -> None:
    from prodata.nodes.textual import guess_personal, mask_frame

    df = pl.DataFrame(
        {
            "cpf_cliente": ["123.456.789-09", "987.654.321-00"],
            "contato": ["ana@empresa.com.br", "bruno@loja.com"],
            "coluna_x": ["11987654321", "(21) 3333-4444"],
            "valor": ["10", "20"],
        }
    )
    assert guess_personal(df) == {"cpf_cliente": "cpf", "contato": "keep_first", "coluna_x": "keep_last"}
    masked = mask_frame(df, {"cpf_cliente": "cpf", "contato": "email"})
    assert masked["cpf_cliente"].to_list() == ["***.456.789-**", "***.654.321-**"]
    assert masked["contato"].to_list()[0].startswith("a") and "ana@" not in masked["contato"].to_list()[0]
    assert masked["valor"].to_list() == ["10", "20"]


def test_share_with_row_limit_and_mask(client: TestClient, tmp_path: Path) -> None:
    """CA-09: 100 linhas, CPF mascarado; nenhum CPF legível no arquivo e a fonte de origem igual."""
    rows = "\n".join(f"{i};{100 + i:03d}.456.789-{i % 100:02d};{i * 10}" for i in range(300))
    up = client.post(
        "/api/datasets", files={"file": ("pessoas.csv", f"id;cpf;valor\n{rows}\n".encode(), "text/csv")}
    )
    assert up.status_code == 201
    flow = {
        "id": "pessoas",
        "name": "Pessoas",
        "nodes": [{"id": "a", "type": "io.input_data", "config": {"dataset": "pessoas.csv"}}],
        "edges": [],
    }
    preview = client.post("/api/portable/share/preview", json={"workflow": flow}).json()
    item = preview["sources"][0]
    assert item["mask"] == {"cpf": "cpf"} and item["available"] == 300
    shown = client.post(
        "/api/portable/share/mask-preview",
        json={"workflow": flow, "key": "pessoas.csv", "mask": {"cpf": "cpf"}},
    ).json()
    assert all(r["cpf"].startswith("***.") for r in shown["rows"])
    target = tmp_path / "pessoas.prodata.json"
    client.post(
        "/api/portable/share/save",
        json={
            "workflow": flow,
            "path": str(target),
            "sources": {"pessoas.csv": {"rows": 100, "mask": {"cpf": "cpf"}}},
        },
    )
    sample = SourceSample.model_validate(
        json.loads(target.read_text(encoding="utf-8"))["samples"]["pessoas.csv"]
    )
    frame = sample.frame()
    assert sample.rows == 100 and frame.height == 100
    assert all(v.startswith("***.") and v.endswith("-**") for v in frame["cpf"].to_list())
    original = client.post("/api/datasets/pessoas.csv/preview", json={}).json()
    assert ".456.789-" in json.dumps(original) and "***." not in json.dumps(original)
    empty = client.post(
        "/api/portable/share/save", json={"workflow": flow, "path": str(target), "sources": {}}
    )
    assert empty.status_code == 400


def test_linked_file_is_flagged_for_sharer_and_receiver(client: TestClient, tmp_path: Path) -> None:
    """CA-10: arquivo vinculado avisa nos dois lados; o arquivo leva o sinal, nunca o caminho."""
    folder = tmp_path / "pasta_minha"
    folder.mkdir()
    (folder / "metas.csv").write_text("uf;meta\nSP;10\nRJ;20\n", encoding="utf-8")
    linked = client.post("/api/datasets/link", json={"path": str(folder / "metas.csv")}).json()
    flow = {
        "id": "vinc",
        "name": "Vinculado",
        "nodes": [{"id": "a", "type": "io.input_data", "config": {"dataset": linked["name"]}}],
        "edges": [],
    }
    check = client.post("/api/portable/sources", json={"workflow": flow}).json()["sources"][0]
    assert check["linked"] is True
    preview = client.post("/api/portable/share/preview", json={"workflow": flow}).json()
    assert preview["sources"][0]["linked"] is True
    target = tmp_path / "vinc.prodata.json"
    client.post(
        "/api/portable/share/save",
        json={"workflow": flow, "path": str(target), "sources": {linked["name"]: {"rows": 100}}},
    )
    text = target.read_text(encoding="utf-8")
    assert "pasta_minha" not in text and str(folder) not in text
    assert json.loads(text)["samples"][linked["name"]]["linked"] is True
    other = Settings(
        storage_dir=tmp_path / "outro",
        log_level="WARNING",
        secrets_backend="memory",
        allowed_hosts=["testserver"],
        seed_samples=False,
    )
    with TestClient(create_app(other)) as there:
        opened = there.post("/api/files/workflow/open", json={"path": str(target)}).json()["workflow"]
        item = there.post("/api/portable/sources", json={"workflow": opened}).json()["sources"][0]
        assert item["state"] == "sample" and item["sample"]["linked"] is True
