"""Receitas prontas: Corrigir pelo IPCA e Converter pela PTAX (spec 049, T18, RF-4961, CA-06)."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from conftest import catalog_fixture

Server = Callable[[Callable[[httpx.Request], httpx.Response]], list[httpx.Request]]


def _ibge(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("/1737/metadados"):
        return httpx.Response(200, content=catalog_fixture("ibge_1737_meta.json"))
    if "/1737/periodos/" in path and path.endswith("/variaveis/2266"):
        return httpx.Response(200, content=catalog_fixture("ibge_1737_dados.json"))
    return httpx.Response(404)


IPCA = {
    k: float(v)
    for k, v in json.loads(catalog_fixture("ibge_1737_dados.json"))[0]["resultados"][0]["series"][0][
        "serie"
    ].items()
}


def _flow(recipe: dict[str, Any], rows: list[list[Any]]) -> dict[str, Any]:
    source = {"id": "vendas", "type": "io.text_input", "label": "Vendas", "x": 0, "y": 0,
              "config": {"table": {"columns": ["data", "valor"], "rows": rows}}}  # fmt: skip
    entry = recipe["entrada"]
    edges = [*recipe["edges"], {"id": "e_in", "source": "vendas", "sourceHandle": "out", "target": entry["node"],
                                "targetHandle": entry["port"]}]  # fmt: skip
    return {"id": "wf-receita", "name": "Receita", "nodes": [source, *recipe["nodes"]], "edges": edges,
            "containers": [recipe["container"]]}  # fmt: skip


def _run(client: TestClient, flow: dict[str, Any], node: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    report = client.post("/api/execute", json={"workflow": flow}).json()["node_results"]
    bad = {k: v.get("error") for k, v in report.items() if v["status"] == "error"}
    assert not bad, bad
    return report, client.get(f"/api/results/{flow['id']}/{node}/out").json()["rows"]


def test_corrigir_pelo_ipca_bate_com_a_conta_a_mao(client: TestClient, catalog_server: Server) -> None:
    """CA-06: cada venda vai para o valor do mês mais recente publicado: valor × índice de referência ÷ índice do mês."""
    catalog_server(_ibge)
    recipe = client.post(
        "/api/catalogo/receita",
        json={"receita": "ipca", "valor": "valor", "data": "data", "desde": "2026-01-15"},
    ).json()
    assert recipe["container"]["title"] == "Corrigir valor pelo IPCA"
    assert {n["type"] for n in recipe["nodes"]} >= {
        "io.public_data",
        "transform.join",
        "prep.formula",
        "transform.summarize",
    }
    flow = _flow(recipe, [["2026-01-15", "100"], ["2026-06-30", "250.5"], ["2026-12-10", "80"]])
    _report, rows = _run(client, flow, recipe["saida"]["node"])
    reference = IPCA["202610"]
    got = {str(r["data"])[:10]: r["valor_corrigido"] for r in rows}
    assert got["2026-01-15"] == pytest.approx(100 * reference / IPCA["202601"])
    assert got["2026-06-30"] == pytest.approx(250.5 * reference / IPCA["202606"])
    assert got["2026-12-10"] is None  # dezembro ainda sem IPCA publicado: fica vazio, não some
    assert len(rows) == 3


def test_ipca_com_mes_de_referencia_escolhido(client: TestClient, catalog_server: Server) -> None:
    catalog_server(_ibge)
    body = {
        "receita": "ipca",
        "valor": "valor",
        "data": "data",
        "referencia": "2026-03",
        "desde": "2026-01-01",
    }
    recipe = client.post("/api/catalogo/receita", json=body).json()
    _report, rows = _run(client, _flow(recipe, [["2026-01-15", "100"]]), recipe["saida"]["node"])
    assert rows[0]["valor_corrigido"] == pytest.approx(100 * IPCA["202603"] / IPCA["202601"])
    assert "2026-03" in recipe["container"]["description"]


def _ptax_days() -> dict[date, float]:
    rows = json.loads(catalog_fixture("ptax_usd.json"))["value"]
    return {datetime.fromisoformat(r["dataHoraCotacao"][:19]).date(): r["cotacaoVenda"]
            for r in rows if r["tipoBoletim"] == "Fechamento"}  # fmt: skip


def test_converter_pela_ptax_usa_o_dia_util_anterior(client: TestClient, catalog_server: Server) -> None:
    catalog_server(lambda r: httpx.Response(200, content=catalog_fixture("ptax_usd.json")))
    days = _ptax_days()
    first, last = min(days), max(days)
    weekend = next(d for d in (last + timedelta(n) for n in range(1, 8)) if d.weekday() >= 5)
    recipe = client.post("/api/catalogo/receita", json={"receita": "ptax", "valor": "valor", "data": "data",
                                                        "desde": first.isoformat()}).json()  # fmt: skip
    rows_in = [[first.isoformat(), "1000"], [weekend.isoformat(), "550"]]
    report, rows = _run(client, _flow(recipe, rows_in), recipe["saida"]["node"])
    got = {str(r["data"])[:10]: r for r in rows}
    assert got[first.isoformat()]["valor_usd"] == pytest.approx(1000 / days[first])
    assert got[weekend.isoformat()]["valor_usd"] == pytest.approx(
        550 / days[last]
    )  # sexta (ou o último dia útil)
    assert str(got[weekend.isoformat()]["ptax_data"])[:10] == last.isoformat()
    join = next(n["id"] for n in recipe["nodes"] if n["type"] == "transform.join")
    assert (
        "1 linha(s) sem valor na própria data usaram a data anterior" in report[join]["extra"]["warnings"][0]
    )


def test_receita_nao_acessa_a_rede_e_recusa_coluna_estranha(client: TestClient) -> None:
    assert (
        client.post(
            "/api/catalogo/receita", json={"receita": "ptax", "valor": "a]b", "data": "d"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/catalogo/receita", json={"receita": "ptax", "valor": "v", "data": "d", "moeda": "us"}
        ).status_code
        == 422
    )
