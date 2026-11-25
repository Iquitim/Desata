"""Situação dos órgãos: No ar, Lenta, Fora do ar desde, sem conexão e histórico (spec 049, T10, CA-02, CA-03)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from prodata.catalog import health
from prodata.catalog.health import HealthStore
from prodata.catalog.http import CatalogClient

Server = Callable[[Callable[[httpx.Request], httpx.Response]], list[httpx.Request]]
T0 = datetime(2026, 11, 25, 14, 20)


def _clock(*moments: datetime) -> Callable[[], datetime]:
    it = iter(moments)
    return lambda: next(it)


def _only_ibge_down(request: httpx.Request) -> httpx.Response:
    if request.url.host == "servicodados.ibge.gov.br":
        return httpx.Response(503)
    return httpx.Response(207 if request.method == "PROPFIND" else 200, content=b"{}")


def test_um_orgao_fora_os_outros_no_ar(tmp_path: Path, catalog_server: Server) -> None:
    """CA-02: o IBGE fora mostra desde quando e o motivo; os outros seguem no ar."""
    catalog_server(_only_ibge_down)
    store = HealthStore(tmp_path)
    data = store.check(CatalogClient, now=lambda: T0)
    ibge = health.summary(data, "ibge")
    assert ibge["situacao"] == "fora"
    assert ibge["desde"] == T0.isoformat()
    assert ibge["motivo"] == "O site do IBGE respondeu erro 503: serviço indisponível."
    assert health.summary(data, "bcb_sgs")["situacao"] == "no_ar"
    assert data["sem_conexao"] is False


def test_fora_desde_a_primeira_falha_e_volta(tmp_path: Path, catalog_server: Server) -> None:
    catalog_server(_only_ibge_down)
    store = HealthStore(tmp_path)
    later = T0 + timedelta(minutes=10)
    store.check(CatalogClient, ["ibge"], now=lambda: T0)
    data = store.check(CatalogClient, ["ibge"], now=lambda: later)
    assert health.summary(data, "ibge")["desde"] == T0.isoformat()  # continua a mesma queda
    catalog_server(lambda r: httpx.Response(200, content=b"[]"))
    data = store.check(CatalogClient, ["ibge"], force=True, now=lambda: later + timedelta(minutes=1))
    ibge = health.summary(data, "ibge")
    assert ibge["situacao"] == "no_ar" and ibge["desde"] is None


def test_lenta(tmp_path: Path, catalog_server: Server, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health, "SLOW", -1.0)  # qualquer resposta conta como lenta
    catalog_server(lambda r: httpx.Response(200, content=b"[]"))
    data = HealthStore(tmp_path).check(CatalogClient, ["ibge"], now=lambda: T0)
    row = health.summary(data, "ibge")
    assert row["situacao"] == "lenta"
    assert "levou" in row["motivo"]


def test_tempo_esgotado(tmp_path: Path, catalog_server: Server) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("devagar", request=request)

    catalog_server(handler)
    data = HealthStore(tmp_path).check(CatalogClient, ["ibge", "ipea"], now=lambda: T0)
    assert health.summary(data, "ibge")["motivo"] == "O site do IBGE não respondeu em 5 segundos."


def test_sem_internet_ninguem_e_acusado(tmp_path: Path) -> None:
    """CA-03: o conftest deixa o catálogo sem rede; todas as sondas falham por conexão."""
    data = HealthStore(tmp_path).check(CatalogClient, now=lambda: T0)
    assert data["sem_conexao"] is True
    assert {health.summary(data, s)["situacao"] for s in ("ibge", "bcb_sgs", "cvm")} == {"nao_conferido"}
    assert health.summary(data, "ibge")["historico"] == {}


def test_historico_guarda_o_pior_do_dia_e_30_dias(tmp_path: Path, catalog_server: Server) -> None:
    store = HealthStore(tmp_path)
    catalog_server(lambda r: httpx.Response(200, content=b"[]"))
    old = T0 - timedelta(days=40)
    store.check(CatalogClient, ["ibge"], now=lambda: old)
    store.check(CatalogClient, ["ibge"], force=True, now=lambda: T0)
    catalog_server(_only_ibge_down)
    store.check(CatalogClient, ["ibge"], force=True, now=lambda: T0 + timedelta(hours=1))
    catalog_server(lambda r: httpx.Response(200, content=b"[]"))
    data = store.check(CatalogClient, ["ibge"], force=True, now=lambda: T0 + timedelta(hours=2))
    history = health.summary(data, "ibge")["historico"]
    assert history == {T0.date().isoformat(): "fora"}  # o pior do dia; o de 40 dias atrás saiu


def test_uma_conferencia_a_cada_5_minutos(tmp_path: Path, catalog_server: Server) -> None:
    seen = catalog_server(lambda r: httpx.Response(200, content=b"[]"))
    store = HealthStore(tmp_path)
    store.check(CatalogClient, ["ibge"], now=lambda: T0)
    store.check(CatalogClient, ["ibge"], now=lambda: T0 + timedelta(minutes=2))
    assert len(seen) == 1
    store.check(
        CatalogClient, ["ibge"], force=True, now=lambda: T0 + timedelta(minutes=3)
    )  # Conferir de novo
    store.check(CatalogClient, ["ibge"], now=lambda: T0 + timedelta(minutes=9))
    assert len(seen) == 3


def test_sonda_da_receita_usa_propfind(tmp_path: Path, catalog_server: Server) -> None:
    seen = catalog_server(lambda r: httpx.Response(207, content=b"<d:multistatus/>"))
    HealthStore(tmp_path).check(CatalogClient, ["receita"], now=lambda: T0)
    assert seen[0].method == "PROPFIND"


def test_rotas_da_situacao(client: TestClient, catalog_server: Server) -> None:
    before = client.get("/api/catalogo/situacao").json()
    assert before["servicos"]["ibge"]["situacao"] == "nao_conferido"
    catalog_server(_only_ibge_down)
    after = client.post("/api/catalogo/situacao", json={"forcar": True, "servicos": ["ibge", "ipea"]}).json()
    assert after["servicos"]["ibge"]["situacao"] == "fora"
    assert after["servicos"]["ipea"]["situacao"] == "no_ar"
    overview = client.get("/api/catalogo").json()
    assert "ibge" in next(c for c in overview["categorias"] if c["id"] == "territorio")["servicos"]
    assert next(p for p in overview["portais"] if p["id"] == "cvm")["servico"] == "cvm"
