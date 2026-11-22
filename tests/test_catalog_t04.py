"""Leitores do Ipeadata, Tesouro Direto, Siconfi e Comex Stat, com respostas de verdade gravadas (spec 049, T04)."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from urllib.parse import parse_qs, unquote, urlsplit

import httpx
import polars as pl
import pytest

from conftest import catalog_fixture
from prodata.catalog import hosts
from prodata.catalog.http import CatalogClient, CatalogError
from prodata.catalog.model import SourceNotFoundError
from prodata.catalog.readers import comex, ipea, siconfi, tesouro

Server = Callable[[Callable[[httpx.Request], httpx.Response]], list[httpx.Request]]


def _query(request: httpx.Request) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(unquote(str(request.url))).query).items()}


# ------------------------------------------------------------------ POST só no Comex Stat


def test_post_so_na_consulta_do_comex() -> None:
    assert hosts.post_allowed("https://api-comexstat.mdic.gov.br/general?language=pt")
    assert not hosts.post_allowed("https://api-comexstat.mdic.gov.br/general/dates/updated")
    assert not hosts.post_allowed("https://api-comexstat.mdic.gov.br/cities")
    assert not hosts.post_allowed("http://api-comexstat.mdic.gov.br/general")
    others = [s for s in hosts.SERVICES.values() if s.id != "comex"]
    assert all(not s.post_paths for s in others)


@pytest.mark.parametrize(
    "url",
    [
        "https://servicodados.ibge.gov.br/api/v3/agregados",
        "https://api-comexstat.mdic.gov.br/cities",
        "https://api-comexstat.mdic.gov.br/general/x",
    ],
)
def test_post_recusado_em_outro_endereco(url: str, catalog_server: Server) -> None:
    seen = catalog_server(lambda r: httpx.Response(200, json={}))
    with CatalogClient() as client, pytest.raises(CatalogError) as err:
        client.post_query(url, {"a": 1})
    assert err.value.kind == "recusado"
    assert seen == []


def test_post_nao_segue_redirecionamento(catalog_server: Server) -> None:
    seen = catalog_server(
        lambda r: httpx.Response(307, headers={"location": "https://api-comexstat.mdic.gov.br/general/outro"})
    )
    with CatalogClient() as client, pytest.raises(CatalogError) as err:
        client.post_query("https://api-comexstat.mdic.gov.br/general", {"flow": "export"})
    assert err.value.kind == "recusado"
    assert len(seen) == 1


# ------------------------------------------------------------------ Ipeadata


def test_ipea_catalogo_e_metadados(catalog_server: Server) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "Metadados(" in unquote(str(request.url)):
            return httpx.Response(200, content=catalog_fixture("ipea_meta.json"))
        return httpx.Response(200, content=catalog_fixture("ipea_catalogo.json"))

    catalog_server(handler)
    with CatalogClient() as client:
        rows = ipea.catalog(client)
        info = ipea.meta(client, "BM12_TJOVER12")
    assert "BM12_TJOVER12" in {r["codigo"] for r in rows}
    assert info["nome"].startswith("Taxa de juros")
    assert info["atualizado"].startswith("20")
    assert info["fonte"]


def test_ipea_serie(catalog_server: Server) -> None:
    catalog_server(lambda r: httpx.Response(200, content=catalog_fixture("ipea_valores.json")))
    with CatalogClient() as client:
        frame = ipea.read_series(client, "BM12_TJOVER12", date(1974, 6, 1)).frame
    assert frame.columns == ["data", "valor"]
    assert frame.filter(pl.col("data") < date(1974, 6, 1)).is_empty()
    assert frame["data"].is_sorted()


def test_ipea_codigo_inexistente_e_lista_vazia(catalog_server: Server) -> None:
    catalog_server(lambda r: httpx.Response(200, json={"value": []}))
    with CatalogClient() as client, pytest.raises(SourceNotFoundError, match="NAOEXISTE"):
        ipea.read_series(client, "NAOEXISTE")


@pytest.mark.parametrize("code", ["X')", "a b", "", "x" * 41])
def test_ipea_codigo_invalido_nao_sai(code: str, catalog_server: Server) -> None:
    seen = catalog_server(lambda r: httpx.Response(200, json={"value": []}))
    with CatalogClient() as client, pytest.raises(SourceNotFoundError):
        ipea.read_series(client, code)
    assert seen == []


# ------------------------------------------------------------------ Tesouro Direto


def _tesouro(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("package_show"):
        return httpx.Response(200, content=catalog_fixture("tesouro_direto.json"))
    return httpx.Response(200, content=catalog_fixture("tesouro_direto_csv.csv"))


def test_tesouro_direto_com_virgula_decimal(catalog_server: Server) -> None:
    seen = catalog_server(_tesouro)
    with CatalogClient() as client:
        frame = tesouro.read_direto(client).frame
    # O endereço do CSV vem do próprio conjunto.
    assert seen[1].url.path.endswith(".csv")
    assert frame.columns == [
        "data",
        "titulo",
        "vencimento",
        "taxa_compra",
        "taxa_venda",
        "pu_compra",
        "pu_venda",
        "pu_base",
    ]
    assert frame.schema["data"] == frame.schema["vencimento"]
    assert frame.filter(pl.col("pu_compra") <= 100).is_empty()
    assert frame["taxa_compra"].null_count() == 0


def test_tesouro_mudou_o_arquivo(catalog_server: Server) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("package_show"):
            return _tesouro(request)
        return httpx.Response(200, text="Titulo;Data\nX;01/01/2026\n")

    catalog_server(handler)
    with CatalogClient() as client, pytest.raises(CatalogError, match="faltam as colunas"):
        tesouro.read_direto(client)


def test_tesouro_metadados(catalog_server: Server) -> None:
    catalog_server(_tesouro)
    with CatalogClient() as client:
        info = tesouro.meta(client)
    assert "ODbL" in info["licenca"]
    assert info["tamanho"] > 1_000_000


# ------------------------------------------------------------------ Siconfi


def test_siconfi_dca(catalog_server: Server) -> None:
    seen = catalog_server(lambda r: httpx.Response(200, content=catalog_fixture("siconfi_dca.json")))
    with CatalogClient() as client:
        result = siconfi.read_report(client, "dca", 2024, "3550308", anexo="DCA-Anexo I-C")
    q = _query(seen[0])
    assert q["an_exercicio"] == "2024"
    assert q["no_anexo"] == "DCA-Anexo I-C"
    assert "co_tipo_demonstrativo" not in q
    frame = result.frame
    assert frame["codigo"].unique().to_list() == ["3550308"]
    assert frame.schema["valor"].is_float()


def test_siconfi_rreo_padroes(catalog_server: Server) -> None:
    seen = catalog_server(lambda r: httpx.Response(200, content=catalog_fixture("siconfi_rreo.json")))
    with CatalogClient() as client:
        siconfi.read_report(client, "rreo", 2025, "3550308")
    q = _query(seen[0])
    assert q["co_tipo_demonstrativo"] == "RREO"
    assert q["nr_periodo"] == "6"


def test_siconfi_pagina_ate_o_fim(catalog_server: Server) -> None:
    item = json.loads(catalog_fixture("siconfi_dca.json"))["items"][0]

    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(_query(request)["offset"])
        more = offset < 4
        return httpx.Response(
            200, json={"items": [item, item], "hasMore": more, "limit": 2, "offset": offset}
        )

    seen = catalog_server(handler)
    with CatalogClient() as client:
        frame = siconfi.read_report(client, "dca", 2024, "3550308").frame
    assert [_query(r)["offset"] for r in seen] == ["0", "2", "4"]
    assert frame.height == 6


def test_siconfi_sem_relatorio(catalog_server: Server) -> None:
    catalog_server(lambda r: httpx.Response(200, json={"items": [], "hasMore": False}))
    with CatalogClient() as client:
        result = siconfi.read_report(client, "dca", 2030, "3550308")
    assert result.frame.is_empty()
    assert "não tem esse relatório" in result.warnings[0]


@pytest.mark.parametrize(("report", "ente"), [("xyz", "3550308"), ("dca", "35503"), ("dca", "35a")])
def test_siconfi_parametros_invalidos(report: str, ente: str, catalog_server: Server) -> None:
    seen = catalog_server(lambda r: httpx.Response(200, json={"items": []}))
    with CatalogClient() as client, pytest.raises(SourceNotFoundError):
        siconfi.read_report(client, report, 2024, ente)  # type: ignore[arg-type]
    assert seen == []


def test_siconfi_entes(catalog_server: Server) -> None:
    catalog_server(lambda r: httpx.Response(200, content=catalog_fixture("siconfi_entes.json")))
    with CatalogClient() as client:
        frame = siconfi.entities(client).frame
    assert frame.schema["codigo"] == frame.schema["ente"]
    assert frame["capital"].dtype == pl.Boolean


# ------------------------------------------------------------------ Comex Stat


def _comex(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/tables/uf":
        return httpx.Response(200, content=catalog_fixture("comex_uf.json"))
    if request.url.path == "/general":
        return httpx.Response(200, content=catalog_fixture("comex_geral.json"))
    return httpx.Response(200, content=catalog_fixture("comex_atualizado.json"))


def test_comex_consulta_com_uf_do_proprio_comex(catalog_server: Server) -> None:
    seen = catalog_server(_comex)
    with CatalogClient() as client:
        result = comex.read_general(
            client, "export", "2026-01", "2026-03", details=["country"], states=["sp"]
        )
    post = next(r for r in seen if r.method == "POST")
    body = json.loads(post.content)
    assert body["filters"] == [{"filter": "state", "values": [41]}]
    assert body["period"] == {"from": "2026-01", "to": "2026-03"}
    assert set(body) == {"flow", "monthDetail", "period", "details", "metrics", "filters"}
    frame = result.frame
    assert frame.columns == ["ano", "mes", "data", "pais", "valor_fob_usd", "peso_kg"]
    assert frame["data"].min() == date(2026, 1, 1)
    assert frame.schema["valor_fob_usd"].is_float()


def test_comex_codigo_junto_do_nome() -> None:
    rows = [{"coNcm": "09011110", "year": "2025", "ncm": "Café não torrado", "metricFOB": "10"}]
    frame = comex._frame(rows, ["ncm"], ["metricFOB"], month_detail=False)
    assert frame.to_dicts() == [
        {"ano": 2025, "ncm_codigo": "09011110", "ncm": "Café não torrado", "valor_fob_usd": 10.0}
    ]


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"flow": "outro"}, "exportação"),
        ({"start": "2026-13"}, "período"),
        ({"start": "2026-05", "end": "2026-01"}, "período"),
        ({"details": ["cpf"]}, "não tem"),
        ({"metrics": ["metricCIF"]}, "importação"),
        ({"states": ["XX"]}, "UF desconhecida"),
    ],
)
def test_comex_parametros_invalidos(kwargs: dict[str, object], match: str, catalog_server: Server) -> None:
    seen = catalog_server(_comex)
    args: dict[str, object] = {"flow": "export", "start": "2026-01", "end": "2026-03"} | kwargs
    with CatalogClient() as client, pytest.raises(SourceNotFoundError, match=match):
        comex.read_general(client, **args)  # type: ignore[arg-type]
    assert not any(r.method == "POST" for r in seen)


def test_comex_atualizado(catalog_server: Server) -> None:
    catalog_server(_comex)
    with CatalogClient() as client:
        assert comex.updated(client) == {"atualizado": "2026-11-06", "ultimo_mes": "2026-10"}
