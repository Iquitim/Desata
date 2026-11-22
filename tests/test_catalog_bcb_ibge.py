"""Leitores do Banco Central (SGS e Olinda) e do IBGE, com respostas de verdade gravadas (spec 049, T03)."""

from __future__ import annotations

import itertools
import json
from collections.abc import Callable
from datetime import date
from urllib.parse import parse_qs, unquote, urlsplit

import httpx
import pytest

from conftest import catalog_fixture
from prodata.catalog.http import CatalogClient, CatalogError
from prodata.catalog.model import PeriodChoice, SourceNotFoundError
from prodata.catalog.readers import bcb_olinda, bcb_sgs, ibge

Server = Callable[[Callable[[httpx.Request], httpx.Response]], list[httpx.Request]]


def _query(request: httpx.Request) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(unquote(str(request.url))).query).items()}


# ------------------------------------------------------------------ período


def test_periodo_relativo_e_resolvido_na_hora() -> None:
    hoje = date(2026, 11, 22)
    assert PeriodChoice().resolve(hoje) == (date(2021, 11, 22), hoje)
    assert PeriodChoice(kind="ultimos_anos", anos=1).resolve(date(2028, 2, 29)) == (
        date(2027, 2, 28),
        date(2028, 2, 29),
    )
    assert PeriodChoice(kind="desde", inicio=date(2000, 1, 1)).resolve(hoje) == (date(2000, 1, 1), hoje)
    assert PeriodChoice(kind="tudo").resolve(hoje, first=date(1986, 6, 4)) == (date(1986, 6, 4), hoje)
    # O fim pode passar de hoje (Selic meta, Focus).
    choice = PeriodChoice(kind="intervalo", inicio=date(2026, 1, 1), fim=date(2027, 1, 1))
    assert choice.resolve(hoje) == (date(2026, 1, 1), date(2027, 1, 1))


# ------------------------------------------------------------------ SGS


def test_janelas_de_dez_anos_sem_sobrepor() -> None:
    ws = bcb_sgs.windows(date(2011, 11, 22), date(2026, 11, 22))
    assert ws == [(date(2011, 11, 22), date(2021, 11, 21)), (date(2021, 11, 22), date(2026, 11, 22))]
    ws = bcb_sgs.windows(date(1995, 1, 1), date(2026, 11, 22))
    assert len(ws) == 4
    assert all(b > a for (a, _), (b, _) in itertools.pairwise(ws))
    assert all((e.year - s.year) <= 10 for s, e in ws)
    assert bcb_sgs.windows(date(2026, 1, 2), date(2026, 1, 1)) == []


def test_selic_de_quinze_anos_vem_em_janelas_e_sem_repetir(catalog_server: Server) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        q = _query(request)
        assert q["formato"] == "json"
        # Repete de propósito a data de fronteira nas duas janelas: o resultado não pode duplicar.
        return httpx.Response(
            200,
            json=[{"data": q["dataInicial"], "valor": "0.04"}, {"data": "22/11/2021", "valor": "0.05"}],
        )

    seen = catalog_server(handler)
    with CatalogClient() as client:
        result = bcb_sgs.read_series(client, 11, date(2011, 11, 22), date(2026, 11, 22))
    assert len(seen) == 2
    assert _query(seen[0])["dataFinal"] == "21/11/2021"
    assert _query(seen[1])["dataInicial"] == "22/11/2021"
    assert result.frame["data"].to_list() == [date(2011, 11, 22), date(2021, 11, 22)]
    assert result.frame.schema["valor"].is_float()
    assert len(result.urls) == 2


def test_sgs_resposta_real(catalog_server: Server) -> None:
    catalog_server(lambda r: httpx.Response(200, content=catalog_fixture("sgs_433.json")))
    with CatalogClient() as client:
        frame = bcb_sgs.read_series(client, 433, date(2025, 1, 1), date(2026, 11, 22)).frame
    assert frame.height == 22
    assert frame["data"][0] == date(2025, 1, 1)
    assert frame["valor"].null_count() == 0


def test_janela_sem_valor_e_vazia(catalog_server: Server) -> None:
    body = {"erro": {"statusCode": 404, "detail": "SGSNegocioException: Value(s) not found"}}
    catalog_server(lambda r: httpx.Response(404, json=body))
    with CatalogClient() as client:
        frame = bcb_sgs.read_series(client, 11, date(1950, 1, 1), date(1959, 12, 31)).frame
    assert frame.is_empty()
    assert frame.columns == ["data", "valor"]


def test_serie_inexistente_responde_html(catalog_server: Server) -> None:
    catalog_server(lambda r: httpx.Response(200, text='<?xml version="1.0"?><!DOCTYPE html><html></html>'))
    with CatalogClient() as client, pytest.raises(SourceNotFoundError, match="999999"):
        bcb_sgs.read_series(client, 999999, date(2020, 1, 1), date(2020, 12, 31))


def test_sem_periodo_o_sgs_recusa(catalog_server: Server) -> None:
    # Resposta de verdade, para lembrar a regra; o leitor sempre manda período.
    assert "10 anos" in json.loads(catalog_fixture("sgs_sem_periodo.json"))["error"]


def test_metadados_e_catalogo_do_bcb(catalog_server: Server) -> None:
    catalog_server(lambda r: httpx.Response(200, content=catalog_fixture("bcb_catalogo.json")))
    with CatalogClient() as client:
        info = bcb_sgs.meta(client, 432)
    assert info["codigo"] == "432"
    assert info["unidade"] == "Percentual ao ano"
    assert "ODbL" in info["licenca"]
    assert not info["descricao"].startswith("---")
    assert info["fim"] != "None"


def test_catalogo_do_bcb_pagina_ate_o_fim(catalog_server: Server) -> None:
    page = json.loads(catalog_fixture("bcb_catalogo_pagina.json"))
    results = page["result"]["results"]

    def handler(request: httpx.Request) -> httpx.Response:
        start = int(_query(request)["start"])
        chunk = results[start : start + 2]
        return httpx.Response(
            200, json={"success": True, "result": {"count": len(results), "results": chunk}}
        )

    seen = catalog_server(handler)
    with CatalogClient() as client:
        rows = list(bcb_sgs.catalog(client))
    assert [r["codigo"] for r in rows] == [r["codigo_sgs"] for r in results]
    assert len(seen) == 3


# ------------------------------------------------------------------ Olinda


def test_ptax_fechamento_um_por_dia(catalog_server: Server) -> None:
    seen = catalog_server(lambda r: httpx.Response(200, content=catalog_fixture("ptax_usd.json")))
    with CatalogClient() as client:
        result = bcb_olinda.read_ptax(client, "usd", date(2026, 11, 1), date(2026, 11, 21))
    raw = seen[0].url.raw_path.decode()
    assert "@moeda='USD'" in raw
    assert "@dataInicial='11-01-2026'" in raw
    frame = result.frame
    assert set(frame["boletim"]) == {"Fechamento"}
    assert frame["data"].n_unique() == frame.height
    assert (frame["cotacao_venda"] >= frame["cotacao_compra"]).all()


def test_ptax_boletim_republicado_vale_o_ultimo(catalog_server: Server) -> None:
    rows = [
        {"paridadeCompra": 1, "paridadeVenda": 1, "cotacaoCompra": 5.0, "cotacaoVenda": 5.1,
         "dataHoraCotacao": "2026-11-03 13:04:00.1", "tipoBoletim": "Fechamento"},
        {"paridadeCompra": 1, "paridadeVenda": 1, "cotacaoCompra": 5.2, "cotacaoVenda": 5.3,
         "dataHoraCotacao": "2026-11-03 15:30:00.1", "tipoBoletim": "Fechamento"},
    ]  # fmt: skip
    catalog_server(lambda r: httpx.Response(200, json={"value": rows}))
    with CatalogClient() as client:
        frame = bcb_olinda.read_ptax(client, "USD", date(2026, 11, 3), date(2026, 11, 3)).frame
    assert frame.height == 1
    assert frame["cotacao_venda"][0] == 5.3


@pytest.mark.parametrize("moeda", ["US", "USD1", "U'D", ""])
def test_ptax_moeda_invalida(moeda: str, catalog_server: Server) -> None:
    seen = catalog_server(lambda r: httpx.Response(200, json={"value": []}))
    with CatalogClient() as client, pytest.raises(SourceNotFoundError):
        bcb_olinda.read_ptax(client, moeda, date(2026, 1, 1), date(2026, 1, 2))
    assert seen == []


def test_focus_filtro_com_por_cento_20(catalog_server: Server) -> None:
    seen = catalog_server(lambda r: httpx.Response(200, content=catalog_fixture("focus_mensal.json")))
    with CatalogClient() as client:
        frame = bcb_olinda.read_focus(client, "IPCA", date(2026, 11, 1)).frame
    raw = seen[0].url.raw_path.decode()
    assert "$filter=Indicador%20eq%20'IPCA'%20and%20Data%20ge%20'2026-11-01'" in raw
    assert "+" not in raw
    assert frame.height == 10
    assert frame.schema["mediana"].is_float()


def test_focus_aspas_no_indicador_sao_escapadas(catalog_server: Server) -> None:
    seen = catalog_server(lambda r: httpx.Response(200, json={"value": []}))
    with CatalogClient() as client:
        bcb_olinda.read_focus(client, "X' or 1 eq 1 or 'a", date(2026, 1, 1))
    assert "Indicador%20eq%20'X''%20or" in seen[0].url.raw_path.decode()


def test_moedas(catalog_server: Server) -> None:
    catalog_server(lambda r: httpx.Response(200, content=catalog_fixture("ptax_moedas.json")))
    with CatalogClient() as client:
        rows = bcb_olinda.currencies(client)
    assert {"simbolo": "CAD", "nome": "Dólar canadense", "tipo": "A"} in rows


# ------------------------------------------------------------------ IBGE


def test_periodo_do_ibge_vira_data() -> None:
    assert ibge.period_date("202610", "mensal") == date(2026, 10, 1)
    assert ibge.period_date("202603", "trimestral") == date(2026, 7, 1)
    assert ibge.period_date("202601", "trimestral") == date(2026, 1, 1)
    assert ibge.period_date("2026", "anual") == date(2026, 1, 1)
    assert ibge.period_date("202612", "trimestral móvel") == date(2026, 12, 1)
    assert ibge.period_date("abc", "mensal") is None


def _ibge(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    name = {
        "/api/v3/agregados/1737/metadados": "ibge_1737_meta.json",
        "/api/v3/agregados/6579/metadados": "ibge_6579_meta.json",
        "/api/v3/agregados/1737/periodos/-12/variaveis/2266": "ibge_1737_dados.json",
        "/api/v3/agregados": "ibge_catalogo.json",
        "/api/v1/localidades/municipios": "ibge_municipios.json",
        "/api/v1/localidades/estados": "ibge_estados.json",
        "/api/v1/localidades/regioes": "ibge_regioes.json",
    }.get(path)
    if name:
        return httpx.Response(200, content=catalog_fixture(name))
    if path == "/api/v3/agregados/6579/periodos/-1/variaveis/9324":
        return httpx.Response(200, content=catalog_fixture("ibge_6579_uf.json"))
    return httpx.Response(404, json={"message": "não encontrado"})


def test_ipca_numero_indice(catalog_server: Server) -> None:
    catalog_server(_ibge)
    with CatalogClient() as client:
        result = ibge.read_table(client, 1737, 2266, period="-12")
    frame = result.frame
    assert frame.height == 12
    assert frame["nivel"].unique().to_list() == ["N1"]
    assert frame["data"].is_sorted()
    assert result.info["unidade"] == "Número-índice"


def test_municipios_sao_lidos_por_uf(catalog_server: Server) -> None:
    body = json.loads(catalog_fixture("ibge_6579_uf.json"))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/metadados"):
            return _ibge(request)
        loc = _query(request)["localidades"]
        uf = loc.removeprefix("N6[N3[").removesuffix("]]")
        one = json.loads(json.dumps(body))
        series = one[0]["resultados"][0]["series"]
        one[0]["resultados"][0]["series"] = [
            {"localidade": {"id": f"{uf}00001", "nivel": {"id": "N6"}, "nome": f"Cidade - {series[0]['localidade']['nome'][:2].upper()}"},
             "serie": {"2026": "100"}}
        ]  # fmt: skip
        return httpx.Response(200, json=one)

    seen = catalog_server(handler)
    with CatalogClient() as client:
        frame = ibge.read_table(client, 6579, 9324, period="-1", level="N6").frame
    asked = [_query(r)["localidades"] for r in seen if "variaveis" in r.url.path]
    assert len(asked) == 27
    assert "N6[N3[35]]" in asked
    assert frame.height == 27
    assert frame["localidade"].str.contains(" - ").sum() == 0


def test_valores_sem_dado_viram_vazio_com_aviso(catalog_server: Server) -> None:
    body = [{"id": "1", "variavel": "V", "unidade": "%", "resultados": [{"classificacoes": [], "series": [
        {"localidade": {"id": "1", "nivel": {"id": "N1"}, "nome": "Brasil"},
         "serie": {"2023": "1.5", "2024": "..", "2025": "-", "2026": "X"}}]}]}]  # fmt: skip
    catalog_server(lambda r: httpx.Response(200, json=body))
    with CatalogClient() as client:
        result = ibge.read_table(client, 1, 1, period="all", frequency="anual")
    assert result.frame["valor"].to_list() == [1.5, None, None, None]
    assert result.warnings == ["3 valores marcados pelo IBGE como sem dado viraram vazio."]


def test_consulta_grande_demais(catalog_server: Server) -> None:
    catalog_server(
        lambda r: httpx.Response(500, json={"statusCode": 500, "message": "Internal server error"})
    )
    with CatalogClient() as client, pytest.raises(CatalogError, match="grande demais"):
        ibge.read_table(client, 6579, 9324, period="2001-2026", level="N3", frequency="anual")


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"period": "-1;drop"}, "Período"),
        ({"level": "N9"}, "Nível"),
        ({"places": "35]&x=1"}, "Localidades"),
        ({"classification": "2[4]&a=b"}, "Classificação"),
    ],
)
def test_parametros_invalidos_nao_saem(kwargs: dict[str, str], match: str, catalog_server: Server) -> None:
    seen = catalog_server(lambda r: httpx.Response(200, json=[]))
    with CatalogClient() as client, pytest.raises(SourceNotFoundError, match=match):
        ibge.read_table(client, 1737, 2266, frequency="mensal", **kwargs)
    assert seen == []


def test_tabela_inexistente(catalog_server: Server) -> None:
    catalog_server(lambda r: httpx.Response(500, json={"message": "erro"}))
    with CatalogClient() as client, pytest.raises(SourceNotFoundError, match="99999"):
        ibge.meta(client, 99999)


def test_catalogo_do_ibge(catalog_server: Server) -> None:
    catalog_server(_ibge)
    with CatalogClient() as client:
        rows = ibge.catalog(client)
    assert {"1737", "6579"} <= {r["codigo"] for r in rows}
    assert all(r["pesquisa"] for r in rows)


def test_municipios_com_codigos_em_texto(catalog_server: Server) -> None:
    catalog_server(_ibge)
    with CatalogClient() as client:
        frame = ibge.municipalities(client).frame
    campinas = frame.filter(frame["nome"] == "Campinas").to_dicts()[0]
    assert campinas["codigo"] == "3509502"
    assert campinas["codigo6"] == "350950"
    assert campinas["uf"] == "SP"
    assert campinas["regiao"] == "Sudeste"
    assert set(frame.schema.values()) == {frame.schema["codigo"]}


def test_municipio_sem_microrregiao(catalog_server: Server) -> None:
    sem = {"id": 5101837, "nome": "Boa Esperança do Norte", "microrregiao": None, "regiao-imediata": {
        "id": 510008, "nome": "Sorriso", "regiao-intermediaria": {"id": 5103, "nome": "Sinop", "UF": {
            "id": 51, "sigla": "MT", "nome": "Mato Grosso", "regiao": {"id": 5, "sigla": "CO", "nome": "Centro-Oeste"}}}}}  # fmt: skip
    catalog_server(lambda r: httpx.Response(200, json=[sem]))
    with CatalogClient() as client:
        row = ibge.municipalities(client).frame.to_dicts()[0]
    assert row["uf"] == "MT"
    assert row["uf_codigo"] == "51"
    assert row["microrregiao"] is None


def test_estados_e_regioes(catalog_server: Server) -> None:
    catalog_server(_ibge)
    with CatalogClient() as client:
        states = ibge.states(client).frame
        regions = ibge.regions(client).frame
    assert states.height == 27
    assert states["codigo"][0] == "11"
    assert regions["sigla"].to_list() == ["N", "NE", "SE", "S", "CO"]
