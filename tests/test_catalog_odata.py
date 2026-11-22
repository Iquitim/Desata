"""Leitor de OData do Banco Central pelo $metadata e pelo swagger (spec 049, T04b, RF-4937, CA-11)."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

import httpx
import polars as pl
import pytest

from conftest import catalog_fixture
from prodata.catalog.http import CatalogClient, CatalogError
from prodata.catalog.model import SourceNotFoundError
from prodata.catalog.readers import odata

Server = Callable[[Callable[[httpx.Request], httpx.Response]], list[httpx.Request]]


def _query(request: httpx.Request) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(unquote(str(request.url))).query).items()}


def _olinda(
    rows: Callable[[httpx.Request], list[dict[str, Any]]] | None = None,
) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        service = "ptax" if "/PTAX/" in path else "saldos"
        if path.endswith("$metadata"):
            return httpx.Response(200, content=catalog_fixture(f"odata_{service}_metadata.xml"))
        if path.endswith("/swagger"):
            return httpx.Response(200, content=catalog_fixture(f"odata_{service}_swagger.json"))
        return httpx.Response(200, json={"value": rows(request) if rows else []})

    return handler


def _ptax(client: CatalogClient) -> odata.Service:
    return odata.describe(client, "PTAX", "v1")


# ------------------------------------------------------------------ descrição


def test_descricao_do_servico(catalog_server: Server) -> None:
    catalog_server(_olinda())
    with CatalogClient() as client:
        service = _ptax(client)
    names = [e.nome for e in service.entradas]
    assert "Moedas" in names
    assert "CotacaoMoedaPeriodo" in names
    assert not any(n.startswith("_") for n in names)  # suporte das funções fica de fora
    assert service.titulo.startswith("Dólar comercial")
    periodo = service.entry("CotacaoMoedaPeriodo")
    assert periodo.titulo.startswith("Boletim")
    assert [p.nome for p in periodo.parametros] == ["moeda", "dataInicial", "dataFinalCotacao"]
    assert dict(periodo.colunas)["cotacaoVenda"] == "Edm.Decimal"


def test_parametros_conferidos_e_nao_conferidos(catalog_server: Server) -> None:
    catalog_server(_olinda())
    with CatalogClient() as client:
        service = _ptax(client)
    periodo = service.entry("CotacaoMoedaPeriodo")
    assert periodo.conferida
    moeda, inicio, fim = periodo.parametros
    assert (moeda.tipo, moeda.opcoes, moeda.exemplo) == ("texto", "Moedas.simbolo", "USD")
    assert (inicio.tipo, inicio.formato, inicio.papel) == ("data", "MM-DD-AAAA", "inicio")
    assert fim.papel == "fim"
    assert service.entry("Moedas").conferida  # sem parâmetro
    assert not service.entry("CotacaoMoedaPeriodoFechamento").conferida


def test_valores_pelo_papel_e_formato(catalog_server: Server) -> None:
    catalog_server(_olinda())
    with CatalogClient() as client:
        ptax = _ptax(client)
        saldos = odata.describe(client, "Saldos_BCB", "v1")
    values = odata.param_values(
        ptax.entry("CotacaoMoedaPeriodo"), date(2026, 11, 1), date(2026, 11, 20), {"moeda": "EUR"}
    )
    assert values == {"moeda": "EUR", "dataInicial": "11-01-2026", "dataFinalCotacao": "11-20-2026"}
    # Saldos: fim de mês nas duas pontas.
    values = odata.param_values(saldos.entry("Saldos_Mensais_BCB"), date(2025, 1, 15), date(2024, 2, 10))
    assert values == {"Data_base": "2025-01-31", "Data_fim": "2024-02-29"}
    # Sem o que digitar, usa o exemplo conferido.
    assert (
        odata.param_values(ptax.entry("CotacaoMoedaDia"), date(2026, 1, 2), date(2026, 1, 2))["moeda"]
        == "USD"
    )


def test_tabela_de_parametros_coerente() -> None:
    for key, params in odata.verified_params().items():
        assert "/" in key
        for name, spec in params.items():
            if "formato" in spec:
                assert spec["formato"] in odata.DATE_FORMATS, (key, name)
                assert spec["papel"] in ("inicio", "fim", "dia", "mes", "a_partir_do_mes", "a_partir_de"), (
                    key,
                    name,
                )


# ------------------------------------------------------------------ leitura


def test_leitura_com_parametros_e_tipos(catalog_server: Server) -> None:
    sample = [{"paridadeCompra": 1.11, "paridadeVenda": 1.12, "cotacaoCompra": 6.1, "cotacaoVenda": 6.2,
               "dataHoraCotacao": "2026-11-03 13:04:14.7", "tipoBoletim": "Fechamento"}]  # fmt: skip
    seen = catalog_server(_olinda(lambda r: sample))
    with CatalogClient() as client:
        service = _ptax(client)
        entry = service.entry("CotacaoMoedaPeriodo")
        values = odata.param_values(entry, date(2026, 11, 1), date(2026, 11, 20), {"moeda": "EUR"})
        result = odata.read(client, service, "CotacaoMoedaPeriodo", values)
    data_request = next(r for r in seen if "Cotacao" in r.url.path)
    raw = data_request.url.raw_path.decode()
    assert (
        "CotacaoMoedaPeriodo(moeda=@moeda,dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)"
        in unquote(raw)
    )
    q = _query(data_request)
    assert q["@moeda"] == "'EUR'"
    assert q["@dataInicial"] == "'11-01-2026'"
    assert "$skip" not in q  # a primeira página vai sem $skip (Saldos recusa até $skip=0)
    assert result.frame.schema["cotacaoVenda"] == pl.Float64
    assert result.info["servico"] == "PTAX"


def test_paginacao_a_partir_da_segunda_pagina(
    catalog_server: Server, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(odata, "PAGE", 2)
    pages = {
        None: [{"simbolo": "A"}, {"simbolo": "B"}],
        "2": [{"simbolo": "C"}, {"simbolo": "D"}],
        "4": [{"simbolo": "E"}],
    }
    seen = catalog_server(_olinda(lambda r: pages[_query(r).get("$skip")]))
    with CatalogClient() as client:
        frame = odata.read(client, _ptax(client), "Moedas").frame
    assert frame["simbolo"].to_list() == ["A", "B", "C", "D", "E"]
    assert [_query(r).get("$skip") for r in seen if r.url.path.endswith("/Moedas")] == [None, "2", "4"]


def test_servico_que_nao_pagina_diz_isso(catalog_server: Server, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(odata, "PAGE", 2)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/Moedas") and "$skip" in _query(request):
            return httpx.Response(500, text="/*{ codigo: 500 }*/")
        return _olinda(lambda r: [{"simbolo": "A"}, {"simbolo": "B"}])(request)

    catalog_server(handler)
    with CatalogClient() as client, pytest.raises(CatalogError, match="período menor") as err:
        odata.read(client, _ptax(client), "Moedas")
    assert err.value.kind == "limite"


def test_filtro_pronto_do_portal(catalog_server: Server) -> None:
    url = ("https://olinda.bcb.gov.br/olinda/servico/DASFN/versao/v1/odata/Recursos?$filter=CnpjInstituicao%20eq%20"
           "'80271455000180'%20and%20Api%20eq%20'canais_atendimento'&$format=json&$top=5")  # fmt: skip
    parsed = odata.parse_resource_url(url)
    assert parsed == (
        "DASFN",
        "v1",
        "Recursos",
        {"$filter": "CnpjInstituicao eq '80271455000180' and Api eq 'canais_atendimento'"},
    )
    assert odata.parse_resource_url("https://exemplo.com/olinda/servico/X/versao/v1/odata/Y") is None


@pytest.mark.parametrize(
    ("values", "match"),
    [
        ({"moeda": "USD"}, "Faltam"),
        ({"moeda": "", "dataInicial": "x", "dataFinalCotacao": "y"}, "Faltam"),
    ],
)
def test_parametros_faltando(values: dict[str, str], match: str, catalog_server: Server) -> None:
    catalog_server(_olinda())
    with CatalogClient() as client, pytest.raises(SourceNotFoundError, match=match):
        odata.read(client, _ptax(client), "CotacaoMoedaPeriodo", values)


def test_aspas_escapadas_no_parametro(catalog_server: Server) -> None:
    seen = catalog_server(_olinda())
    with CatalogClient() as client:
        odata.read(client, _ptax(client), "CotacaoMoedaDia", {"moeda": "U'SD", "dataCotacao": "01-02-2026"})
    assert _query(seen[-1])["@moeda"] == "'U''SD'"


def test_inteiro_validado() -> None:
    param = odata.Param("DataBase", "inteiro", inteiro=True)
    entry = odata.Entry("Metricas", "Métricas", parametros=(param,))
    service = odata.Service("PANORAMA_DE_CONSORCIOS", "v1", entradas=[entry])
    with pytest.raises(SourceNotFoundError, match="inteiro"):
        odata._url_and_params(service, entry, {"DataBase": "2025 or 1"})
    url, query = odata._url_and_params(service, entry, {"DataBase": "202509"})
    assert query == {"@DataBase": "202509"}
    assert url.endswith("Metricas(DataBase=@DataBase)")


@pytest.mark.parametrize(("servico", "versao"), [("PTAX/../x", "v1"), ("PTAX", "1"), ("a b", "v1")])
def test_nome_de_servico_invalido_nao_sai(servico: str, versao: str, catalog_server: Server) -> None:
    seen = catalog_server(_olinda())
    with CatalogClient() as client, pytest.raises(SourceNotFoundError):
        odata.describe(client, servico, versao)
    assert seen == []


def test_tipos_das_colunas() -> None:
    entry = odata.Entry("X", "X", colunas=(("d", "Edm.Date"), ("t", "Edm.DateTimeOffset"), ("n", "Edm.Int32"),
                                           ("v", "Edm.Decimal"), ("s", "Edm.String")))  # fmt: skip
    rows = [{"d": "2026-01-31", "t": "2026-01-31T10:20:30Z", "n": "7", "v": 1, "s": "a"},
            {"d": "2026-02-28", "t": "2026-02-28T00:00:00Z", "n": 8, "v": 2.5, "s": "b"}]  # fmt: skip
    frame = odata._frame(rows, entry)
    assert frame.schema["d"] == pl.Date
    assert frame.schema["t"].is_temporal() and frame.schema["t"] != pl.Date
    assert (frame.schema["n"], frame.schema["v"], frame.schema["s"]) == (pl.Int64, pl.Float64, pl.String)
    assert frame["n"].to_list() == [7, 8]
    assert frame["d"][1] == date(2026, 2, 28)


def test_sem_linhas_mantem_as_colunas() -> None:
    entry = odata.Entry("X", "X", colunas=(("a", "Edm.String"), ("b", "Edm.Decimal")))
    frame = odata._frame([], entry)
    assert frame.columns == ["a", "b"]
    assert frame.is_empty()


def test_swagger_ausente_nao_impede(catalog_server: Server) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/swagger"):
            return httpx.Response(403)
        return _olinda()(request)

    catalog_server(handler)
    with CatalogClient() as client:
        service = _ptax(client)
    assert service.entry("CotacaoMoedaPeriodo").titulo == "CotacaoMoedaPeriodo"


def test_xml_com_entidades_e_recusado(catalog_server: Server) -> None:
    bomb = (b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;">]>'
            b"<edmx:Edmx>&b;</edmx:Edmx>")  # fmt: skip

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("$metadata"):
            return httpx.Response(200, content=bomb)
        return _olinda()(request)

    catalog_server(handler)
    with CatalogClient() as client, pytest.raises(CatalogError, match="descrição inválida"):
        _ptax(client)


def test_fixture_do_swagger_e_real() -> None:
    doc = json.loads(catalog_fixture("odata_ptax_swagger.json"))
    assert doc["swagger"] == "2.0"
