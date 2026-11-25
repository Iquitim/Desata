"""Sem rede fora de hora (spec 049, RF-4983, CA-08; constituição 1.8.1, princípio IV).

Abrir o programa, carregar tudo o que a tela pede ao abrir (inclusive a vista Dados) e executar um fluxo sem fonte
pública não pode tentar nenhuma conexão externa, nem criar o cliente do catálogo.
"""

from __future__ import annotations

import importlib.util
import socket
from pathlib import Path
from typing import Any

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.routing import Mount

from prodata.catalog import http as catalog_http

DOCS = Path(__file__).resolve().parent.parent / "docs"
_spec = importlib.util.spec_from_file_location("gerar_contexto_ia_rede", DOCS / "gerar_contexto_ia.py")
assert _spec and _spec.loader
generator = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(generator)

LOCAL = {"127.0.0.1", "::1", "localhost", "0.0.0.0"}


@pytest.fixture
def network_attempts(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Registra e recusa qualquer conexão ou consulta de nome que não seja deste computador."""
    attempts: list[Any] = []
    real_connect = socket.socket.connect
    real_getaddrinfo = socket.getaddrinfo

    def connect(self: socket.socket, address: Any) -> Any:
        host = address[0] if isinstance(address, tuple) else str(address)
        if host not in LOCAL:
            attempts.append(("connect", address))
            raise OSError("rede externa bloqueada no teste")
        return real_connect(self, address)

    def getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        if host not in LOCAL and host is not None:
            attempts.append(("dns", host))
            raise OSError("rede externa bloqueada no teste")
        return real_getaddrinfo(host, *args, **kwargs)

    created: list[Any] = []
    real_init = catalog_http.CatalogClient.__init__

    def init(self: Any, *args: Any, **kwargs: Any) -> None:
        created.append(self)
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(catalog_http.CatalogClient, "__init__", init)
    attempts.append(created)  # o primeiro item é a lista de clientes do catálogo criados
    return attempts


def _get_paths(routes: list[Any], prefix: str = "") -> set[str]:
    """Todas as rotas GET sem parâmetro no caminho, inclusive as das sub-aplicações montadas."""
    out: set[str] = set()
    for route in routes:
        included = getattr(route, "original_router", None)  # include_router nas versões novas do FastAPI
        if included is not None:
            out |= _get_paths(list(included.routes), prefix)
        elif isinstance(route, Mount):
            out |= _get_paths(list(route.routes), prefix + route.path)
        elif isinstance(route, APIRoute) and "GET" in (route.methods or set()) and "{" not in route.path:
            out.add(prefix + route.path)
    return out


# Rotas GET que acessam a internet por desenho: só a tela do catálogo, aberto, as chama (constituição 1.8.1).
# A lista é exata: uma rota nova que acesse a rede não passa sem ser declarada aqui, de propósito.
CATALOG_NETWORK_ROUTES = {"/api/catalogo/moedas", "/api/catalogo/cnpj"}


def test_abrir_o_programa_e_a_vista_dados_nao_acessa_a_rede(
    network_attempts: list[Any], client: TestClient
) -> None:
    created = network_attempts.pop(0)
    paths = sorted(_get_paths(client.app.routes))  # type: ignore[attr-defined]
    assert "/api/datasets" in paths
    assert len(paths) > 20
    assert set(paths) >= CATALOG_NETWORK_ROUTES  # a lista não guarda rota que não existe mais
    for path in ["/", *paths]:
        if path not in CATALOG_NETWORK_ROUTES:
            client.get(path)
    assert network_attempts == []
    assert created == []


def test_as_rotas_que_acessam_a_rede_sao_so_as_declaradas(
    network_attempts: list[Any], client: TestClient
) -> None:
    """Cada rota da lista, chamada sozinha, é a única coisa que cria o cliente do catálogo."""
    created = network_attempts.pop(0)
    for path in sorted(CATALOG_NETWORK_ROUTES):
        before = len(created)
        client.get(path)
        assert len(created) > before, f"{path} está na lista, mas não acessa a rede: tire da lista"


def test_fluxo_sem_fonte_publica_nao_acessa_a_rede(network_attempts: list[Any], client: TestClient) -> None:
    created = network_attempts.pop(0)
    res = client.post("/api/execute", json={"workflow": generator.EXAMPLE})
    assert res.status_code == 200, res.text
    assert {r["status"] for r in res.json()["node_results"].values()} == {"executed"}
    assert network_attempts == []
    assert created == []


def test_o_bloqueio_do_teste_funciona(network_attempts: list[Any]) -> None:
    network_attempts.pop(0)
    with pytest.raises(OSError):
        socket.getaddrinfo("servicodados.ibge.gov.br", 443)
    assert network_attempts == [("dns", "servicodados.ibge.gov.br")]
