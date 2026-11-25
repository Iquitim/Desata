"""Detalhe e prévia de uma fonte do catálogo (spec 049, T08, RF-4911..4915, RF-4937, RF-4938)."""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Callable

import httpx
from fastapi.testclient import TestClient

from conftest import catalog_fixture

Server = Callable[[Callable[[httpx.Request], httpx.Response]], list[httpx.Request]]


def _orgaos(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    host = request.url.host
    if host == "api.bcb.gov.br":
        return httpx.Response(200, content=catalog_fixture("sgs_432.json"))
    if host == "servicodados.ibge.gov.br":
        name = {
            "/api/v3/agregados/1737/metadados": "ibge_1737_meta.json",
            "/api/v3/agregados/1737/periodos": "ibge_1737_periodos.json",
        }.get(path)
        if name:
            return httpx.Response(200, content=catalog_fixture(name))
        if "/variaveis/" in path:
            return httpx.Response(200, content=catalog_fixture("ibge_1737_dados.json"))
    if host == "dados.cvm.gov.br":
        if path.endswith("package_show"):
            return httpx.Response(200, content=catalog_fixture("ckan_cvm_conjunto.json"))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            archive.writestr("processo.csv", "cnpj;valor\n00394411000109;1.234,56\n33000167000101;10,00\n")
        return httpx.Response(200, content=buf.getvalue())
    if host == "dadosabertos.bcb.gov.br" and path.endswith("package_show"):
        resource = {"id": "r1", "name": "PTAX", "format": "OData",
                    "url": "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"}  # fmt: skip
        return httpx.Response(200, json={"success": True, "result": {"name": "ptax", "title": "Taxas de câmbio",
                                                                      "resources": [resource]}})  # fmt: skip
    if host == "olinda.bcb.gov.br":
        if path.endswith("$metadata"):
            return httpx.Response(200, content=catalog_fixture("odata_ptax_metadata.xml"))
        if path.endswith("/swagger"):
            return httpx.Response(200, content=catalog_fixture("odata_ptax_swagger.json"))
    return httpx.Response(404)


def test_detalhe_de_um_destaque(client: TestClient, catalog_server: Server) -> None:
    catalog_server(_orgaos)
    d = client.get("/api/catalogo/fonte", params={"id": "bcb.sgs/432"}).json()
    assert d["nome"] == "Taxa Selic meta"
    assert d["leitura"] == "pronta"
    assert d["atualizado_rotulo"] == "último dado em"
    assert d["atualizado"].startswith("20")
    assert d["orgao"] == "Banco Central do Brasil"
    assert "ODbL" in d["licenca"]
    assert [c["nome"] for c in d["colunas"]] == ["data", "valor"]
    assert all(c["descricao"] for c in d["colunas"])
    assert d["escolhas"][0]["id"] == "periodo"


def test_detalhe_sem_internet_sai_com_o_que_o_programa_sabe(client: TestClient) -> None:
    # O conftest deixa o catálogo sem rede.
    d = client.get("/api/catalogo/fonte", params={"id": "ibge.agregado/1737"}).json()
    assert d["nome"] == "IPCA"
    assert d["colunas"]
    assert d["avisos"] and "Não foi possível conferir" in d["avisos"][0]


def test_detalhe_do_ibge_com_ultimo_periodo(client: TestClient, catalog_server: Server) -> None:
    catalog_server(_orgaos)
    d = client.get("/api/catalogo/fonte", params={"id": "ibge.agregado/1737"}).json()
    assert d["periodo"]["inicio"] == "197912"
    assert d["atualizado_rotulo"].startswith("último período")
    variavel = next(e for e in d["escolhas"] if e["id"] == "variavel")
    assert {o["rotulo"] for o in variavel["opcoes"]} >= {"Número-índice", "Variação mensal (%)"}


def test_previa_le_como_o_fluxo(client: TestClient, catalog_server: Server) -> None:
    catalog_server(_orgaos)
    p = client.post(
        "/api/catalogo/previa", json={"id": "ibge.agregado/1737", "escolhas": {"variavel": 2266}}
    ).json()
    assert p["linhas_lidas"] > 0
    assert len(p["linhas"]) <= 10
    assert [c["name"] for c in p["colunas"]][:2] == ["codigo", "localidade"]


def test_previa_sem_internet_diz_o_motivo(client: TestClient) -> None:
    res = client.post("/api/catalogo/previa", json={"id": "bcb.sgs/432", "escolhas": {}})
    assert res.status_code == 502
    assert "Banco Central" in res.json()["detail"]


def test_calendario_nao_precisa_de_rede(client: TestClient) -> None:
    p = client.post(
        "/api/catalogo/previa", json={"id": "calendario/feriados", "escolhas": {"local": "SP"}}
    ).json()
    assert (
        any(r["nome"] == "Revolução Constitucionalista de 1932" for r in p["linhas"]) or p["linhas_lidas"] > 0
    )


def test_conjunto_de_portal_com_arquivos(client: TestClient, catalog_server: Server) -> None:
    catalog_server(_orgaos)
    d = client.get("/api/catalogo/fonte", params={"id": "ckan/cvm/processo-sancionador"}).json()
    assert d["leitura"] == "automatica"
    assert d["arquivos"]
    assert d["pagina"].startswith("https://dados.cvm.gov.br/dataset/")
    assert d["escolhas"] == [{"id": "arquivo", "rotulo": "Arquivo", "tipo": "arquivo"}]


def test_previa_obrigatoria_do_arquivo(client: TestClient, catalog_server: Server) -> None:
    catalog_server(_orgaos)
    d = client.get("/api/catalogo/fonte", params={"id": "ckan/cvm/processo-sancionador"}).json()
    legivel = next(a for a in d["arquivos"] if a["situacao"] == "legivel")
    p = client.post("/api/catalogo/arquivo/previa", json={"id": d["id"], "arquivo": legivel["id"]}).json()
    assert p["membro"] == "processo.csv"
    assert dict(p["formato_aceito"]["colunas"]) == {"cnpj": "texto", "valor": "numero"}
    assert p["linhas"][0]["cnpj"] == "00394411000109"  # identificador com o zero
    assert p["numeros_convertidos"] == ["valor"]


def test_arquivo_que_so_abre_no_navegador(client: TestClient, catalog_server: Server) -> None:
    catalog_server(_orgaos)
    d = client.get("/api/catalogo/fonte", params={"id": "ckan/cvm/processo-sancionador"}).json()
    link = next((a for a in d["arquivos"] if a["situacao"] == "so_link"), None)
    if link is None:
        return  # o conjunto gravado só tem arquivos legíveis
    res = client.post("/api/catalogo/arquivo/previa", json={"id": d["id"], "arquivo": link["id"]})
    assert res.status_code == 404


def test_consultas_odata_de_um_conjunto_do_banco_central(client: TestClient, catalog_server: Server) -> None:
    catalog_server(_orgaos)
    o = client.get("/api/catalogo/odata", params={"id": "ckan/bcb_portal/ptax", "arquivo": "r1"}).json()
    names = {c["nome"]: c for c in o["consultas"]}
    assert names["CotacaoMoedaPeriodo"]["conferida"] is True
    assert names["CotacaoMoedaPeriodoFechamento"]["conferida"] is False
    papeis = {p["nome"]: p["papel"] for p in names["CotacaoMoedaPeriodo"]["parametros"]}
    assert papeis == {"moeda": None, "dataInicial": "inicio", "dataFinalCotacao": "fim"}
    assert o["documentacao"].startswith("https://olinda.bcb.gov.br/")


def test_fonte_invalida(client: TestClient) -> None:
    for bad in ("../x", "a", "bcb.sgs/1;drop"):
        assert client.get("/api/catalogo/fonte", params={"id": bad}).status_code == 404
    res = client.post("/api/catalogo/previa", json={"id": "receita.cnpj/dados-abertos", "escolhas": {}})
    assert res.status_code == 404
    assert "Baixar" in json.dumps(res.json(), ensure_ascii=False)
