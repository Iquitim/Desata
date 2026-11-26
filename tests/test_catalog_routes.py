"""Rotas do catálogo de dados públicos (spec 049, T07): visão geral, busca, atualizar, favoritos e recentes."""

from __future__ import annotations

import time
from collections.abc import Callable

import httpx
from fastapi.testclient import TestClient

from conftest import catalog_fixture

Server = Callable[[Callable[[httpx.Request], httpx.Response]], list[httpx.Request]]


def _orgaos(request: httpx.Request) -> httpx.Response:
    host = request.url.host
    if host == "dadosabertos.bcb.gov.br":
        return httpx.Response(200, content=catalog_fixture("bcb_catalogo_pagina.json"))
    if host == "servicodados.ibge.gov.br":
        return httpx.Response(200, content=catalog_fixture("ibge_catalogo.json"))
    if host == "www.ipeadata.gov.br":
        return httpx.Response(200, content=catalog_fixture("ipea_catalogo.json"))
    if request.url.path.endswith("/api/3/action/package_search"):
        return httpx.Response(200, content=catalog_fixture("ckan_cvm_busca.json"))
    return httpx.Response(404)


def test_visao_geral_sem_rede(client: TestClient) -> None:
    data = client.get("/api/catalogo").json()
    ids = [c["id"] for c in data["categorias"]]
    assert ids[:3] == ["economia", "precos", "cambio"]
    assert all(c["icone"] for c in data["categorias"])
    assert next(c for c in data["categorias"] if c["id"] == "territorio")["quantidade"] == 3
    assert len(data["portais"]) == 25
    lugares = data["lugares"]
    assert (
        sum(pl["esfera"] == "estadual" for pl in lugares) == 27 and sum(pl["capital"] for pl in lugares) == 27
    )
    assert all(pl["motivo"] for pl in lugares if pl["situacao"] != "le_direto")
    assert data["desatualizado"] is True  # nunca foi lido
    assert data["lido_em"] is None
    assert data["destaques"] >= 20
    assert data["atualizacao"]["rodando"] is False


def test_busca_e_filtros(client: TestClient) -> None:
    rows = client.get("/api/catalogo/busca", params={"q": "selic"}).json()["resultados"]
    assert rows[0]["destaque"] is True
    rows = client.get("/api/catalogo/busca", params={"categoria": "territorio"}).json()["resultados"]
    assert {r["categoria"] for r in rows} == {"territorio"}
    rows = client.get("/api/catalogo/busca", params={"especial": "destaques"}).json()["resultados"]
    assert all(r["destaque"] for r in rows)
    assert client.get("/api/catalogo/busca", params={"limite": 0}).status_code == 422


def test_favoritos_e_recentes(client: TestClient) -> None:
    assert client.post("/api/catalogo/favoritos/bcb.sgs/432").json() == {"favorita": True}
    client.post("/api/catalogo/recentes/ibge.agregado/1737")
    client.post("/api/catalogo/recentes/bcb.sgs/11")
    favs = client.get("/api/catalogo/busca", params={"especial": "favoritos"}).json()["resultados"]
    assert [r["id"] for r in favs] == ["bcb.sgs/432"]
    recents = client.get("/api/catalogo/busca", params={"especial": "recentes"}).json()["resultados"]
    assert [r["id"] for r in recents] == ["bcb.sgs/11", "ibge.agregado/1737"]
    overview = client.get("/api/catalogo").json()
    assert (overview["favoritos"], overview["recentes"]) == (1, 2)
    assert client.post("/api/catalogo/favoritos/bcb.sgs/432").json() == {"favorita": False}


def test_atualizar_em_segundo_plano(client: TestClient, catalog_server: Server) -> None:
    catalog_server(_orgaos)
    started = client.post("/api/catalogo/atualizar", json={"orgaos": ["ipea", "cvm"]}).json()
    assert started["rodando"] is True
    assert set(started["orgaos"]) == {"ipea", "cvm"}
    for _ in range(100):
        status = client.get("/api/catalogo/atualizar").json()
        if not status["rodando"]:
            break
        time.sleep(0.05)
    assert status["rodando"] is False
    assert status["orgaos"]["ipea"].isdigit()
    overview = client.get("/api/catalogo").json()
    assert overview["orgaos"]["ipea"]["quantidade"] > 0
    assert next(p for p in overview["portais"] if p["id"] == "cvm")["quantidade"] > 0
    # Agora a busca acha o catálogo completo guardado.
    rows = client.get("/api/catalogo/busca", params={"q": "selic", "orgao": "ipea"}).json()["resultados"]
    assert rows and all(r["orgao"] == "ipea" for r in rows)


def test_orgao_desconhecido_e_ignorado(client: TestClient, catalog_server: Server) -> None:
    catalog_server(_orgaos)
    started = client.post("/api/catalogo/atualizar", json={"orgaos": ["nao-existe"]}).json()
    assert started["orgaos"] == {}


# ------------------------------------------------------------------ lugares (revisão de 2026-11-26)


def test_busca_acha_estados_e_municipios_sem_rede(client: TestClient, catalog_server: Server) -> None:
    calls = catalog_server(lambda r: httpx.Response(500))
    found = client.get("/api/catalogo/busca", params={"q": "juiz de fora"}).json()["lugares"]
    assert found[0] == {**found[0], "id": "mun:3136702", "nome": "Juiz de Fora", "uf": "MG"}
    names = [
        (p["nome"], p["uf"])
        for p in client.get("/api/catalogo/busca", params={"q": "campinas"}).json()["lugares"]
    ]
    assert names[0] == ("Campinas", "SP")
    jesus = [
        p["uf"]
        for p in client.get("/api/catalogo/busca", params={"q": "Bom Jesus"}).json()["lugares"]
        if p["nome"] == "Bom Jesus"
    ]
    assert len(jesus) == len(set(jesus)) >= 4  # um por estado
    assert (
        client.get("/api/catalogo/busca", params={"q": "bahia"}).json()["lugares"][0]["esfera"] == "estadual"
    )
    assert client.get("/api/catalogo/busca", params={"q": "ju"}).json()["lugares"] == []
    assert not calls  # a lista de municípios vai no programa


def test_painel_do_estado_e_do_municipio(client: TestClient, catalog_server: Server) -> None:
    calls = catalog_server(lambda r: httpx.Response(500))
    mg = client.get("/api/catalogo/lugar", params={"id": "est:31"}).json()
    assert mg["portal_estado"]["situacao"] == "le_direto" and mg["capital"]["nome"] == "Belo Horizonte"
    pop = next(f for f in mg["fontes"] if f["id"] == "ibge.agregado/6579")
    assert pop["escolhas"] == {"nivel": "N3", "localidades": "31"}
    jf = client.get("/api/catalogo/lugar", params={"id": "mun:3136702"}).json()
    assert jf["nome"] == "Juiz de Fora" and jf["estado"] == "Minas Gerais" and jf["portal"] is None
    assert (
        next(f for f in jf["fontes"] if f["id"] == "ibge.agregado/6579")["escolhas"]["localidades"]
        == "3136702"
    )
    assert client.get("/api/catalogo/lugar", params={"id": "mun:9999999"}).status_code == 404
    assert client.get("/api/catalogo/lugar", params={"id": "x:1"}).status_code == 422
    assert not calls


def test_demais_municipios_com_portal_no_topo(client: TestClient) -> None:
    sp = client.get("/api/catalogo/municipios", params={"uf": "SP"}).json()
    assert sp["municipios"][0]["nome"] == "Mogi das Cruzes" and sp["municipios"][0]["portal"]
    assert all(m["nome"] != "São Paulo" for m in sp["municipios"])  # a capital fica em Municipais
    assert client.get("/api/catalogo/municipios", params={"uf": "XX"}).status_code == 404
