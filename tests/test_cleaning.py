"""Recomendações de limpeza (spec 048, RF-4831..4835, CA-06)."""

from __future__ import annotations

from typing import Any

import polars as pl
from fastapi.testclient import TestClient

from prodata.engine.cleaning import recommend

DIRTY = pl.DataFrame({
    "uf": ["SP ", "SP", "sp", "RJ", "RJ", "MG"],
    "valor": ["10", "N/D", "30,5", "40", "50", "60"],
    "data": ["2026-01-05", "05/02/2026", "2026-03-01", "2026-04-01", "2026-05-01", "2026-06-01"],
    "obs": ["", None, "ok", "", None, "ok"],
})  # fmt: skip


def by_type(recs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {r["id"]: r for r in recs}


def test_each_common_problem_becomes_a_recommendation() -> None:
    recs = by_type(recommend(DIRTY))
    padded = recs["espacos:uf"]
    assert padded["linhas"] == 1 and padded["exemplos"][0] == {"antes": '"SP "', "depois": '"SP"'}
    assert (
        padded["correcao"]["tool"] == "prep.data_cleansing"
        and padded["correcao"]["config"]["trim_whitespace"]
    )
    number = recs["numero_texto:valor"]
    assert '"N/D"' in number["titulo"] and number["correcao"]["config"]["fields"][0]["cast"] == "Float64"
    date = recs["data_texto:data"]
    assert date["correcao"]["config"]["fields"][0]["cast"] == "Date"
    case = recs["caixa:uf"]
    assert case["correcao"]["config"]["case_mode"] == "upper"
    empty = recs["texto_vazio:obs"]
    assert empty["linhas"] == 2 and empty["correcao"]["config"]["empty_as_null"]


def test_repeated_rows_and_ignored() -> None:
    df = pl.DataFrame({"a": ["x", "x", "y"], "b": ["1", "1", "2"]})
    recs = by_type(recommend(df))
    assert recs["linhas_repetidas:"]["linhas"] == 1 and recs["linhas_repetidas:"]["correcao"]["port"] == "U"
    assert "linhas_repetidas:" not in by_type(recommend(df, {"linhas_repetidas:"}))


def test_clean_table_has_nothing_to_say() -> None:
    clean = pl.DataFrame({"uf": ["SP", "RJ"], "valor": [10, 20]})
    assert recommend(clean) == []


def test_most_affected_first() -> None:
    recs = recommend(DIRTY)
    assert [r["linhas"] for r in recs] == sorted((r["linhas"] for r in recs), reverse=True)


def flow(
    extra_nodes: list[dict[str, Any]] | None = None,
    edges: list[dict[str, Any]] | None = None,
    ignored: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    nodes = [
        {
            "id": "t",
            "type": "io.text_input",
            "config": {"table": {"columns": ["uf"], "rows": [["SP"], ["sp"], ["RJ"]]}},
        }
    ]
    body: dict[str, Any] = {
        "id": "limpa",
        "name": "Limpeza",
        "nodes": nodes + (extra_nodes or []),
        "edges": edges or [],
    }
    if ignored:
        body["ignored_cleaning"] = ignored
    return body


def test_route_suggests_and_skips_what_is_already_fixed_or_ignored(client: TestClient) -> None:
    wf = flow()
    client.post("/api/execute", json={"workflow": wf})
    res = client.post("/api/cleaning/recommend", json={"workflow": wf, "node_id": "t"}).json()
    assert res["disponivel"] and [r["id"] for r in res["recomendacoes"]] == ["caixa:uf"]
    fixed = flow([{"id": "c", "type": "prep.data_cleansing", "config": {"columns": ["uf"], "case_mode": "upper"}}],
                 [{"id": "e", "source": "t", "target": "c"}])  # fmt: skip
    assert (
        client.post("/api/cleaning/recommend", json={"workflow": fixed, "node_id": "t"}).json()[
            "recomendacoes"
        ]
        == []
    )
    ignored = flow(ignored={"t": ["caixa:uf"]})
    assert (
        client.post("/api/cleaning/recommend", json={"workflow": ignored, "node_id": "t"}).json()[
            "recomendacoes"
        ]
        == []
    )
    assert (
        client.post("/api/cleaning/recommend", json={"workflow": wf, "node_id": "sumiu"}).json()["disponivel"]
        is False
    )
