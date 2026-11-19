"""Spec 041, RF-4170: o laço na aba SQL, desenrolado volta a volta e conferido com o resultado do motor."""

import time
from itertools import pairwise
from typing import Any

import pytest
from fastapi.testclient import TestClient

ROWS = [["N", 10, "a"], ["N", 20, "b"], ["S", 5, "c"], ["S", 7, "d"], ["L", 1, "e"]]


def flow(
    start: dict[str, Any], end: dict[str, Any], body: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    body = body or [
        {
            "id": "soma",
            "type": "transform.summarize",
            "config": {
                "group_by": [],
                "aggregations": [{"column": "valor_venda", "agg": "sum", "alias": "total"}],
            },
        }
    ]
    chain = ["src", "ini", *[b["id"] for b in body], "fim"]
    return {
        "id": "laco_sql",
        "nodes": [
            {
                "id": "src",
                "type": "io.text_input",
                "config": {"table": {"columns": ["regiao", "valor_venda", "cliente"], "rows": ROWS}},
            },
            {"id": "ini", "type": "flow.loop_start", "config": start},
            *body,
            {"id": "fim", "type": "flow.loop_end", "config": {"start": "ini", **end}},
        ],
        "edges": [
            {"id": f"e{i}", "source": a, "sourceHandle": "out", "target": b, "targetHandle": "in"}
            for i, (a, b) in enumerate(pairwise(chain))
        ],
    }


def verified(client: TestClient, wf: dict[str, Any]) -> dict[str, Any]:
    assert client.post("/api/execute", json={"workflow": wf}).status_code == 200
    client.post("/api/sql/verify", json={"workflow": wf})
    for _ in range(300):
        if client.get(f"/api/sql/verify/{wf['id']}").json()["done"]:
            break
        time.sleep(0.05)
    res = client.post("/api/sql/generate", json={"workflow": wf, "selection": ["fim:out"]})
    assert res.status_code == 200, res.text
    return res.json()


def output(data: dict[str, Any]) -> dict[str, Any]:
    return next(o for o in data["outputs"] if o["node_id"] == "fim")


def test_each_value_stacked_is_translated_and_matches(client: TestClient) -> None:
    data = verified(client, flow({"mode": "each", "column": "regiao"}, {"output": "stack"}))
    state = output(data)["state"]
    assert state["state"] in ("ready", "ready_notes"), state
    assert "UNION ALL BY NAME" in data["text"] and "WHERE regiao = 'N'" in data["text"]


def test_variables_go_into_each_turn(client: TestClient) -> None:
    body = [
        {
            "id": "f",
            "type": "prep.formula",
            "config": {
                "formulas": [
                    {
                        "target": "new",
                        "column": "rotulo",
                        "type": "Auto",
                        "expression": "Concat('volta ', ToString([#volta]), ' de ', [#valor])",
                    }
                ]
            },
        }
    ]
    data = verified(
        client, flow({"mode": "each", "column": "regiao", "order": "appearance"}, {"output": "stack"}, body)
    )
    assert output(data)["state"]["state"] in ("ready", "ready_notes"), output(data)["state"]
    assert "'N'" in data["text"] and "[#valor]" not in data["text"]


@pytest.mark.lento
def test_range_and_last_turn(client: TestClient) -> None:
    body = [
        {
            "id": "f",
            "type": "prep.formula",
            "config": {
                "formulas": [
                    {"target": "new", "column": "x", "type": "Auto", "expression": "[valor_venda] * [#valor]"}
                ]
            },
        }
    ]
    data = verified(client, flow({"mode": "range", "start": "1", "end": "3"}, {"output": "stack"}, body))
    assert output(data)["state"]["state"] in ("ready", "ready_notes"), output(data)["state"]
    data = verified(client, flow({"mode": "range", "start": "1", "end": "3"}, {"output": "last"}, body))
    assert output(data)["state"]["state"] in ("ready", "ready_notes"), output(data)["state"]


def test_while_and_accumulate_explain_why_not(client: TestClient) -> None:
    data = verified(
        client, flow({"mode": "while", "max_iterations": 3}, {"output": "last", "expression": "1 == 1"})
    )
    block = next(b for b in data["blocks"] if b["node_id"] == "ini")
    assert "Enquanto" in (block.get("reason") or ""), block
