"""Zeros à esquerda preservados na leitura de CSV da vista Dados (spec 049, RF-4995, CA-13)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl
from fastapi.testclient import TestClient

from prodata.ingestion.folders import read_folder
from prodata.ingestion.options import ReadOptions
from prodata.ingestion.readers import identifier_example, read_table, read_table_noted


def _csv(tmp_path: Path, text: str, name: str = "a.csv", encoding: str = "utf-8") -> Path:
    path = tmp_path / name
    path.write_bytes(text.encode(encoding))
    return path


def test_codigo_com_zero_fica_texto(tmp_path: Path) -> None:
    df, notes = read_table_noted(_csv(tmp_path, "codigo;qtd\n0012;5\n0340;7\n"), ReadOptions())
    assert df.schema["codigo"] == pl.String
    assert df["codigo"].to_list() == ["0012", "0340"]
    assert df.schema["qtd"] == pl.Int64
    assert notes == [
        "Lida(s) como texto para manter os zeros à esquerda e os códigos longos: codigo (ex.: 0012)."
    ]


def test_inteiro_comum_continua_inteiro_e_sem_nota(tmp_path: Path) -> None:
    df, notes = read_table_noted(_csv(tmp_path, "a,b\n1,-2\n30,4\n"), ReadOptions())
    assert df.schema == pl.Schema({"a": pl.Int64, "b": pl.Int64})
    assert df["b"].to_list() == [-2, 4]
    assert notes == []


def test_zero_depois_da_amostra_tambem_fica(tmp_path: Path) -> None:
    """O leitor decide pelas primeiras linhas; a conferência é no arquivo inteiro."""
    rows = "".join(f"{i};{i}\n" for i in range(100, 400))
    df = read_table(_csv(tmp_path, "cod;v\n" + rows + "0007;1\n"), ReadOptions(infer_schema_rows=50))
    assert df.schema["cod"] == pl.String
    assert df["cod"][-1] == "0007"
    assert df.schema["v"] == pl.Int64


def test_cnpj_cep_e_codigo_longo(tmp_path: Path) -> None:
    text = "cnpj;cep;ibge\n33000167000101;01310100;3550308\n60746948000112;20040002;3304557\n"
    df = read_table(_csv(tmp_path, text), ReadOptions())
    assert df.schema["cnpj"] == pl.String  # 14 dígitos
    assert df["cep"].to_list() == ["01310100", "20040002"]  # zero à esquerda
    assert df.schema["ibge"] == pl.Int64  # 7 dígitos sem zero: continua número, como antes


def test_latin1_e_previa(tmp_path: Path) -> None:
    path = _csv(tmp_path, "município;código\nSão Paulo;0012\nCampinas;0034\n", encoding="latin-1")
    df = read_table(path, ReadOptions(), n_rows=1)
    assert df["código"].to_list() == ["0012"]


def test_exemplo_de_identificador() -> None:
    assert identifier_example(pl.Series(["12", "0012"])) == "0012"
    assert identifier_example(pl.Series(["12", "34"])) is None
    assert identifier_example(pl.Series(["123456789012"])) == "123456789012"
    assert identifier_example(pl.Series(["12", "x"])) is None
    assert identifier_example(pl.Series([None, ""], dtype=pl.String)) is None


def test_pasta_junta_arquivo_com_zero_e_sem_zero(tmp_path: Path) -> None:
    a = _csv(tmp_path, "cod;v\n0012;1\n", "a.csv")
    b = _csv(tmp_path, "cod;v\n12;2\n", "b.csv")
    table, _odd = read_folder([a, b], ReadOptions(), "")
    assert table.schema["cod"] == pl.String
    assert table["cod"].to_list() == ["0012", "12"]


def test_caixa_mostra_o_aviso(client: TestClient) -> None:
    content = b"codigo;valor\n0012;10\n0340;20\n"
    assert (
        client.post("/api/datasets", files={"file": ("codigos.csv", content, "text/csv")}).status_code == 201
    )
    flow: dict[str, Any] = {
        "id": "wf-zeros",
        "name": "zeros",
        "nodes": [{"id": "f", "type": "io.input_data", "label": "F", "config": {"dataset": "codigos.csv"}}],
        "edges": [],
    }
    report = client.post("/api/execute", json={"workflow": flow}).json()["node_results"]["f"]
    assert report["status"] == "executed"
    assert "manter os zeros à esquerda" in str(report), report
    rows = client.get("/api/results/wf-zeros/f/out").json()["rows"]
    assert [r["codigo"] for r in rows] == ["0012", "0340"]
