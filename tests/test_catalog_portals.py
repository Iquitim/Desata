"""Portais de dados abertos (CKAN): lista verificada, catálogo, detalhe e classificação dos arquivos (spec 049, T04c)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from conftest import catalog_fixture
from prodata.catalog import hosts, portals
from prodata.catalog.http import CatalogClient, CatalogError
from prodata.catalog.index import CatalogStore
from prodata.catalog.model import SourceNotFoundError
from prodata.catalog.readers import ckan

Server = Callable[[Callable[[httpx.Request], httpx.Response]], list[httpx.Request]]


def _q(request: httpx.Request) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(str(request.url)).query).items()}


# ------------------------------------------------------------------ lista fixa


def test_cada_portal_tem_servico_e_hosts_na_lista() -> None:
    assert len(portals.PORTALS) == 16
    for p in portals.PORTALS:
        service = hosts.SERVICES[hosts.PORTAL_SERVICE[p.id]]
        assert p.host in service.hosts or p.id in ("bcb_portal", "tesouro_portal"), p.id
        assert p.host in hosts.ALLOWED_HOSTS
        assert all(h in hosts.ALLOWED_HOSTS for h in p.arquivos)
        assert p.ckan.startswith("https://")
        assert p.site.startswith("o portal")


def test_armazenamento_do_ibama_entra_exato() -> None:
    assert hosts.allowed("https://stibamadadosabertosprd.blob.core.windows.net/x/a.csv")
    assert not hosts.allowed("https://outraconta.blob.core.windows.net/a.csv")
    assert not hosts.allowed("https://blob.core.windows.net/a.csv")


def test_indisponiveis_nao_estao_na_lista() -> None:
    for base in portals.UNAVAILABLE:
        assert not hosts.allowed(f"{base}/api/3/action/package_search")


def test_mensagem_com_o_nome_do_portal(catalog_server: Server) -> None:
    catalog_server(lambda r: httpx.Response(503))
    with CatalogClient() as client, pytest.raises(CatalogError) as err:
        client.get("https://dadosabertos.aneel.gov.br/api/3/action/package_search", retries=0)
    assert err.value.message == "O portal da ANEEL respondeu erro 503: serviço indisponível."


# ------------------------------------------------------------------ classificação


@pytest.mark.parametrize(
    ("raw", "situacao", "motivo"),
    [
        ({"format": "CSV", "url": "https://dados.cvm.gov.br/a.csv", "size": 1000}, "legivel", ""),
        ({"format": ".CSV", "url": "https://dados.pe.gov.br/a.csv"}, "legivel", ""),
        ({"format": "CSV/ZIP", "url": "https://dados.rs.gov.br/a.zip"}, "legivel", ""),
        ({"format": "", "url": "https://dados.cvm.gov.br/dados/x.csv.zip"}, "legivel", ""),
        ({"format": "PARQUET", "url": "https://dadosabertos.aneel.gov.br/a.parquet"}, "legivel", ""),
        ({"format": "XLSX", "url": "https://dados.es.gov.br/a.xlsx", "size": 300 * 1024 * 1024}, "grande", "200 MB"),
        ({"format": "PDF", "url": "https://dados.cvm.gov.br/a.pdf"}, "so_link", "PDF"),
        ({"format": "ODS", "url": "https://dados.prefeitura.sp.gov.br/a.ods"}, "so_link", "ODS"),
        ({"format": "SHA512", "url": "https://cdn.tse.jus.br/a.sha512"}, "so_link", "integridade"),
        ({"format": "APPLICATION/X-7Z-COMPRESSED", "url": "https://dados.rs.gov.br/a.7z"}, "so_link", "7z"),
        ({"format": "CSV", "url": "https://www.gov.br/a.csv"}, "so_link", "fora da lista"),
        ({"format": "CSV", "url": "http://dados.cvm.gov.br/a.csv"}, "so_link", "http"),
        ({"format": "CSV", "url": "x"}, "so_link", "inválido"),
        ({"format": "JSON", "url": "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/Moedas?$format=json"},
         "odata", ""),
    ],
)  # fmt: skip
def test_classificacao(raw: dict[str, Any], situacao: str, motivo: str) -> None:
    resource = ckan.classify(raw)
    assert resource.situacao == situacao
    assert motivo in resource.motivo


def test_tamanho_em_texto() -> None:
    assert (
        ckan.classify({"format": "CSV", "url": "https://dados.mg.gov.br/a.csv", "size": "999"}).tamanho == 999
    )
    assert (
        ckan.classify({"format": "CSV", "url": "https://dados.mg.gov.br/a.csv", "size": "?"}).tamanho is None
    )


# ------------------------------------------------------------------ catálogo e detalhe


def _cvm(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("package_show"):
        return httpx.Response(200, content=catalog_fixture("ckan_cvm_conjunto.json"))
    return httpx.Response(200, content=catalog_fixture("ckan_cvm_busca.json"))


def test_catalogo_do_portal(catalog_server: Server) -> None:
    catalog_server(_cvm)
    with CatalogClient() as client:
        rows = ckan.catalog(client, "cvm")
    first = rows[0]
    assert first["id"].startswith("ckan/cvm/")
    assert first["leitura_automatica"] is True
    assert first["recursos"] >= first["legiveis"]
    assert "formatos" in first and "temas" in first


def test_catalogo_pagina_pelo_lote(catalog_server: Server, monkeypatch: pytest.MonkeyPatch) -> None:
    results = json.loads(catalog_fixture("ckan_cvm_busca.json"))["result"]["results"]
    site = portals.Portal(id="cvm", nome="CVM", orgao="CVM", esfera="federal", ckan="https://dados.cvm.gov.br",
                          site="o portal da CVM", lote=1)  # fmt: skip
    monkeypatch.setitem(portals.BY_ID, "cvm", site)

    def handler(request: httpx.Request) -> httpx.Response:
        q = _q(request)
        start, rows = int(q["start"]), int(q["rows"])
        return httpx.Response(
            200,
            json={
                "success": True,
                "result": {"count": len(results), "results": results[start : start + rows]},
            },
        )

    seen = catalog_server(handler)
    with CatalogClient() as client:
        rows = ckan.catalog(client, "cvm")
    assert len(rows) == len(results)
    assert {_q(r)["rows"] for r in seen} == {"1"}


def test_pagina_cortada_le_um_por_vez_e_avisa(
    catalog_server: Server, monkeypatch: pytest.MonkeyPatch
) -> None:
    results = json.loads(catalog_fixture("ckan_cvm_busca.json"))["result"]["results"]
    site = portals.Portal(id="sc", nome="SC", orgao="SC", esfera="estadual", ckan="https://dados.sc.gov.br",
                          site="o portal de Santa Catarina", lote=2)  # fmt: skip
    monkeypatch.setitem(portals.BY_ID, "sc", site)

    def handler(request: httpx.Request) -> httpx.Response:
        q = _q(request)
        start, rows = int(q["start"]), int(q["rows"])
        if rows == 2 and start == 0:
            return httpx.Response(
                200, json={"success": True, "result": {"count": 3, "results": results[0:2]}}
            )
        if rows == 2:
            raise httpx.RemoteProtocolError(
                "cortado", request=request
            )  # página do índice 2 em diante cortada
        if start == 2:
            return httpx.Response(
                200, json={"success": True, "result": {"count": 3, "results": results[2:3]}}
            )
        raise httpx.RemoteProtocolError("cortado", request=request)

    catalog_server(handler)
    with CatalogClient() as client:
        rows, warnings = ckan.catalog_with_warnings(client, "sc")
    assert len(rows) == 3
    assert warnings == []


def test_conjunto_que_nao_abre_e_contado(catalog_server: Server, monkeypatch: pytest.MonkeyPatch) -> None:
    results = json.loads(catalog_fixture("ckan_cvm_busca.json"))["result"]["results"]
    site = portals.Portal(id="sc", nome="SC", orgao="SC", esfera="estadual", ckan="https://dados.sc.gov.br",
                          site="o portal de Santa Catarina", lote=2)  # fmt: skip
    monkeypatch.setitem(portals.BY_ID, "sc", site)

    def handler(request: httpx.Request) -> httpx.Response:
        q = _q(request)
        if q["start"] == "0":
            return httpx.Response(
                200, json={"success": True, "result": {"count": 3, "results": results[0:2]}}
            )
        raise httpx.RemoteProtocolError("cortado", request=request)

    catalog_server(handler)
    with CatalogClient() as client:
        rows, warnings = ckan.catalog_with_warnings(client, "sc")
    assert len(rows) == 2
    assert warnings == [
        "1 conjunto(s) não puderam ser lidos: o portal de Santa Catarina corta respostas grandes."
    ]


def test_portal_do_banco_central_sem_as_series_sgs(catalog_server: Server) -> None:
    seen = catalog_server(
        lambda r: httpx.Response(200, json={"success": True, "result": {"count": 0, "results": []}})
    )
    with CatalogClient() as client:
        ckan.catalog(client, "bcb_portal")
    assert _q(seen[0])["fq"] == "-codigo_sgs:[* TO *]"


def test_detalhe_com_arquivos_classificados(catalog_server: Server) -> None:
    catalog_server(_cvm)
    with CatalogClient() as client:
        detail = ckan.dataset(client, "cvm", "processo-sancionador")
    assert detail["pagina"] == "https://dados.cvm.gov.br/dataset/processo-sancionador"
    assert detail["arquivos"]
    assert all(a["situacao"] in ("legivel", "grande", "odata", "so_link") for a in detail["arquivos"])
    assert all(a["motivo"] for a in detail["arquivos"] if a["situacao"] == "so_link")


def test_conjunto_inexistente(catalog_server: Server) -> None:
    catalog_server(lambda r: httpx.Response(404, json={"success": False}))
    with CatalogClient() as client, pytest.raises(SourceNotFoundError, match="não existe"):
        ckan.dataset(client, "cvm", "nao-existe")


@pytest.mark.parametrize(("portal_id", "name"), [("nao-existe", "x"), ("cvm", "../x"), ("cvm", "a b")])
def test_parametros_invalidos_nao_saem(portal_id: str, name: str, catalog_server: Server) -> None:
    seen = catalog_server(lambda r: httpx.Response(200, json={}))
    with CatalogClient() as client, pytest.raises(SourceNotFoundError):
        ckan.dataset(client, portal_id, name)
    assert seen == []


# ------------------------------------------------------------------ catálogo guardado


def test_portal_no_catalogo_guardado_e_na_busca(tmp_path: Path, catalog_server: Server) -> None:
    catalog_server(_cvm)
    store = CatalogStore(tmp_path / "catalogo")
    with CatalogClient() as client:
        report = store.refresh(client, ["cvm"])
    assert report.por_orgao["cvm"].quantidade > 0
    first = store.entries("cvm")[0]
    found = store.search(first["nome"].split()[0], agency="cvm")
    assert found
    assert found[0]["orgao"] == "cvm"
    assert found[0]["destaque"] is False


def test_aviso_do_portal_fica_guardado(
    tmp_path: Path, catalog_server: Server, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog_server(_cvm)
    monkeypatch.setattr(
        ckan,
        "catalog_with_warnings",
        lambda client, pid: ([{"id": "ckan/cvm/a", "nome": "A"}], ["1 conjunto(s) não puderam ser lidos"]),
    )
    store = CatalogStore(tmp_path / "catalogo")
    with CatalogClient() as client:
        store.refresh(client, ["cvm"])
    assert store.state()["cvm"].aviso == "1 conjunto(s) não puderam ser lidos"
