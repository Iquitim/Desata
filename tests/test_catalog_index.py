"""Destaques, catálogo guardado, Atualizar o catálogo e busca (spec 049, T05, CA-03, CA-04)."""

from __future__ import annotations

import gzip
import json
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest

from conftest import catalog_fixture
from prodata.catalog import curated, hosts
from prodata.catalog.http import CatalogClient
from prodata.catalog.index import CatalogStore, normalize

Server = Callable[[Callable[[httpx.Request], httpx.Response]], list[httpx.Request]]


def _orgaos(request: httpx.Request, *, fail: str | None = None) -> httpx.Response:
    host = request.url.host
    if fail and fail in host:
        return httpx.Response(503)
    if host == "dadosabertos.bcb.gov.br":
        return httpx.Response(200, content=catalog_fixture("bcb_catalogo_pagina.json"))
    if host == "servicodados.ibge.gov.br":
        return httpx.Response(200, content=catalog_fixture("ibge_catalogo.json"))
    if host == "www.ipeadata.gov.br":
        return httpx.Response(200, content=catalog_fixture("ipea_catalogo.json"))
    return httpx.Response(404)


@pytest.fixture
def store(tmp_path: Path) -> CatalogStore:
    return CatalogStore(tmp_path / "catalogo")


@pytest.fixture
def filled(store: CatalogStore, catalog_server: Server) -> CatalogStore:
    catalog_server(_orgaos)
    with CatalogClient() as client:
        store.refresh(client)
    return store


# ------------------------------------------------------------------ destaques


def test_destaques_completos_e_coerentes() -> None:
    ids = [s.id for s in curated.SOURCES]
    assert len(ids) == len(set(ids))
    for source in curated.SOURCES:
        assert source.categoria in curated.CATEGORY_IDS, source.id
        assert source.servico in hosts.SERVICES, source.id
        assert source.licenca and source.citacao, source.id
        if source.kind != "cnpj":
            assert source.colunas, source.id
            assert all(c.description for c in source.colunas), source.id
    used = {s.categoria for s in curated.SOURCES}
    assert used == curated.CATEGORY_IDS - {"series"}  # Ipeadata entra pela busca no catálogo completo


def test_cada_destaque_da_spec_existe() -> None:
    wanted = {"bcb.sgs/432", "bcb.sgs/11", "bcb.sgs/12", "bcb.focus/mensal", "ibge.agregado/1737",
              "ibge.agregado/1736", "bcb.sgs/189", "bcb.ptax/moeda", "ibge.localidades/municipios",
              "ibge.agregado/6579", "ibge.agregado/4099", "ibge.agregado/5938", "receita.cnpj/dados-abertos",
              "calendario/feriados", "calendario/dias-uteis", "tesouro.direto/precos-taxas", "siconfi/relatorios",
              "comex/exportacao", "comex/importacao"}  # fmt: skip
    assert wanted <= set(curated.BY_ID)


# ------------------------------------------------------------------ atualizar


def test_atualizar_guarda_cada_orgao(filled: CatalogStore) -> None:
    state = filled.state()
    assert all(s.lido_em and not s.erro for s in state.values())
    assert state["ipea"].quantidade > 5
    assert (filled.root / "indice" / "ibge.json.gz").exists()
    assert not filled.stale()


def test_orgao_que_falha_mantem_o_anterior(filled: CatalogStore, catalog_server: Server) -> None:
    """CA-04: o IBGE fora do ar mantém o catálogo anterior dele, com a data; os outros atualizam."""
    before = filled.state()
    catalog_server(lambda r: _orgaos(r, fail="ibge"))
    later = datetime.now() + timedelta(hours=1)
    with CatalogClient() as client:
        report = filled.refresh(client, now=lambda: later)
    assert report.falhas == ["ibge"]
    state = filled.state()
    assert state["ibge"].lido_em == before["ibge"].lido_em
    assert "503" in state["ibge"].erro
    assert state["ibge"].quantidade == before["ibge"].quantidade
    assert state["bcb"].lido_em == later
    assert filled.search("1737", agency="ibge")  # o catálogo anterior continua buscável


def test_progresso_por_orgao(store: CatalogStore, catalog_server: Server) -> None:
    catalog_server(_orgaos)
    calls: list[tuple[str, str]] = []
    with CatalogClient() as client:
        store.refresh(client, ["ipea"], progress=lambda a, s: calls.append((a, s)))
    assert calls[0] == ("ipea", "lendo")
    assert calls[1][1].isdigit()


def test_velho_ou_nunca_lido_pede_atualizacao(filled: CatalogStore, store: CatalogStore) -> None:
    assert filled.stale(datetime.now() + timedelta(days=8))
    assert CatalogStore(filled.root.parent / "outro").stale()


def test_arquivo_estragado_nao_derruba(filled: CatalogStore) -> None:
    (filled.root / "indice" / "ipea.json.gz").write_bytes(b"lixo")
    fresh = CatalogStore(filled.root)
    assert fresh.entries("ipea") == []
    assert fresh.search("selic")  # os destaques continuam


def test_arquivo_guardado_e_comprimido(filled: CatalogStore) -> None:
    data = json.loads(gzip.decompress((filled.root / "indice" / "bcb.json.gz").read_bytes()))
    assert data["orgao"] == "bcb"
    assert all(e["id"].startswith("bcb.sgs/") for e in data["entradas"])


# ------------------------------------------------------------------ busca


def test_normalizar() -> None:
    assert normalize("  Municípios  do   BRASIL ") == "municipios do brasil"


def test_busca_sem_acento_e_sem_maiuscula(store: CatalogStore) -> None:
    ids = [e["id"] for e in store.search("MUNICIPIOS")]
    assert ids[0] == "ibge.localidades/municipios"
    assert next(e["id"] for e in store.search("dolar")) == "bcb.ptax/moeda"


def test_busca_sem_internet_encontra_ipca_e_1737(store: CatalogStore) -> None:
    """CA-03: sem rede e sem catálogo guardado, os destaques bastam para ipca e 1737."""
    assert store.search("ipca")[0]["id"] == "ibge.agregado/1737"
    assert store.search("1737")[0]["id"] == "ibge.agregado/1737"


def test_destaques_primeiro_depois_o_catalogo_completo(filled: CatalogStore) -> None:
    results = filled.search("selic")
    flags = [e["destaque"] for e in results]
    assert flags[0] is True
    assert flags == sorted(flags, reverse=True)
    assert any(e["id"].startswith("ipea/") for e in results)


def test_destaque_nao_repete_no_catalogo_completo(filled: CatalogStore) -> None:
    ids = [e["id"] for e in filled.search("432")]
    assert ids.count("bcb.sgs/432") == 1


def test_codigo_fora_dos_catalogos_vira_ler_direto(store: CatalogStore) -> None:
    results = store.search("433")
    assert results[-1]["id"] == "bcb.sgs/433"
    assert results[-1]["direto"] is True


def test_filtros(filled: CatalogStore) -> None:
    assert {e["orgao"] for e in filled.search("", agency="ibge")} == {"ibge"}
    assert {e["categoria"] for e in filled.search("", category="territorio")} == {"territorio"}
    assert all(e["id"].startswith("ipea/") for e in filled.search("", category="series"))
    mensais = filled.search("", periodicity="mensal")
    assert mensais
    assert all("mensal" in e.get("periodicidade", "") for e in mensais)


def test_focus_entra_no_filtro_do_banco_central(store: CatalogStore) -> None:
    assert "bcb.focus/mensal" in [e["id"] for e in store.search("focus", agency="bcb")]


def test_limite_de_resultados(filled: CatalogStore) -> None:
    assert len(filled.search("", limit=5)) == 5
