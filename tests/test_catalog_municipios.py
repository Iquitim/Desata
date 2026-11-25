"""Juntar com municípios do IBGE (spec 049, T19, RF-4962, CA-06)."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import polars as pl
import pytest
from fastapi.testclient import TestClient

from conftest import catalog_fixture
from prodata.catalog import municipios

Server = Callable[[Callable[[httpx.Request], httpx.Response]], list[httpx.Request]]

MUNICIPIOS = pl.DataFrame({
    "codigo": ["3550308", "3509502", "3545803", "1100015", "2201988", "4302709", "3304557"],
    "codigo6": ["355030", "350950", "354580", "110001", "220198", "430270", "330455"],
    "nome": ["São Paulo", "Campinas", "Santa Bárbara d'Oeste", "Alta Floresta D'Oeste", "Bom Jesus", "Bom Jesus", "Rio de Janeiro"],
    "uf": ["SP", "SP", "SP", "RO", "PI", "RS", "RJ"],
})  # fmt: skip


def _codes(frame: pl.DataFrame, column: str, uf: str | None = None) -> list[str | None]:
    sql = municipios.match_sql(column, uf, frame.columns)
    import duckdb

    con = duckdb.connect()
    con.register("input_1", frame)
    con.register("input_2", MUNICIPIOS)
    return con.sql(sql).pl()["ibge_municipio_codigo"].to_list()


def test_os_formatos_casam_com_o_mesmo_municipio() -> None:
    """CA-06: "Sao Paulo/SP", "355030" e "3550308" são o mesmo município."""
    table = pl.DataFrame(
        {"cidade": ["Sao Paulo/SP", "355030", "3550308", "SÃO PAULO - sp", "São Paulo (SP)", "são paulo, SP"]}
    )
    assert _codes(table, "cidade") == ["3550308"] * 6


def test_acento_maiusculas_hifen_e_d_apostrofo() -> None:
    table = pl.DataFrame(
        {
            "cidade": [
                "SANTA BARBARA D'OESTE",
                "santa bárbara d´oeste/SP",
                "Alta Floresta d'Oeste - RO",
                "campinas",
            ]
        }
    )
    assert _codes(table, "cidade") == ["3545803", "3545803", "1100015", "3509502"]


def test_homonimo_sem_uf_nao_casa_com_uf_casa() -> None:
    table = pl.DataFrame({"cidade": ["Bom Jesus", "Bom Jesus/RS", "Bom Jesus"], "estado": [None, None, "PI"]})
    assert _codes(table, "cidade") == [None, "4302709", None]
    assert _codes(table, "cidade", "estado") == [None, "4302709", "2201988"]


def test_codigo_como_numero_e_linhas_que_nao_casam_ficam() -> None:
    table = pl.DataFrame({"cod": [3550308, 3304557, 1234567, None], "valor": [1, 2, 3, 4]})
    assert _codes(table, "cod") == ["3550308", "3304557", None, None]


def test_nome_de_coluna_que_ja_existe_nao_repete() -> None:
    table = pl.DataFrame({"cidade": ["Campinas/SP"], "ibge_municipio_codigo": ["x"]})
    sql = municipios.match_sql("cidade", None, table.columns)
    assert '"ibge_municipio_codigo_2"' in sql


def test_conferencia_conta_e_explica() -> None:
    table = pl.DataFrame(
        {"cidade": ["Campinas", "Bom Jesus", "Bom Jesus", "Xique-Xiqui", None, "São Paulo/SP"]}
    )
    result = municipios.check(table, MUNICIPIOS, "cidade", None)
    assert result["casam"] == 2 and result["nao_casam"] == 4
    reasons = {e["valor"]: e for e in result["exemplos"]}
    assert reasons["Bom Jesus"]["linhas"] == 2 and "mais de um estado" in reasons["Bom Jesus"]["motivo"]
    assert "não encontrado" in reasons["Xique-Xiqui"]["motivo"]
    assert reasons[""]["motivo"] == "vazio"


def _ibge(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/localidades/municipios"):
        return httpx.Response(200, content=catalog_fixture("ibge_municipios.json"))
    return httpx.Response(404)


def test_do_menu_ao_fluxo(client: TestClient, catalog_server: Server) -> None:
    """A conferência usa o resultado da caixa e o mesmo SQL que entra no fluxo; o fluxo dá o mesmo número."""
    catalog_server(_ibge)
    source = {"id": "t", "type": "io.text_input", "label": "Cidades", "x": 0, "y": 0,
              "config": {"table": {"columns": ["cidade", "valor"],
                                   "rows": [["Campinas/SP", "1"], ["355030", "2"], ["Brasilia - DF", "3"], ["Lugar Nenhum", "4"]]}}}  # fmt: skip
    flow = {"id": "wf-mun", "name": "Municípios", "nodes": [source], "edges": []}
    client.post("/api/execute", json={"workflow": flow})
    check = client.post(
        "/api/catalogo/municipios/conferir", json={"fluxo": "wf-mun", "caixa": "t", "coluna": "cidade"}
    ).json()
    assert check["casam"] == 3 and check["exemplos"][0]["valor"] == "Lugar Nenhum"
    recipe = client.post(
        "/api/catalogo/receita/municipios", json={"coluna": "cidade", "colunas": ["cidade", "valor"]}
    ).json()
    assert recipe["container"]["title"] == "Juntar cidade com os municípios do IBGE"
    entry = recipe["entrada"]
    flow["nodes"] += recipe["nodes"]
    flow["edges"] = [
        *recipe["edges"],
        {
            "id": "e1",
            "source": "t",
            "sourceHandle": "out",
            "target": entry["node"],
            "targetHandle": entry["port"],
        },
    ]
    report = client.post("/api/execute", json={"workflow": flow}).json()["node_results"]
    assert all(r["status"] != "error" for r in report.values()), report
    rows = client.get(f"/api/results/wf-mun/{recipe['saida']['node']}/out").json()["rows"]
    assert [r["ibge_municipio_codigo"] for r in rows] == ["3509502", "3550308", "5300108", None]
    assert sum(1 for r in rows if r["ibge_municipio_codigo"]) == check["casam"]


def test_conferir_sem_executar_pede_para_executar(client: TestClient) -> None:
    answer = client.post(
        "/api/catalogo/municipios/conferir", json={"fluxo": "nada", "caixa": "x", "coluna": "c"}
    )
    assert answer.status_code == 409


@pytest.mark.parametrize("bad", ["a]b", "x\ny"])
def test_coluna_estranha_recusada(client: TestClient, bad: str) -> None:
    assert client.post("/api/catalogo/receita/municipios", json={"coluna": bad}).status_code == 422
