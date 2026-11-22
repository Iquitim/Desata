"""Cliente do catálogo de dados públicos: lista fixa, só leitura, limites e mensagens (spec 049, T02)."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from prodata.catalog import hosts
from prodata.catalog import http as chttp
from prodata.catalog.http import CatalogClient, CatalogError

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture
def serve(monkeypatch: pytest.MonkeyPatch) -> Callable[[Handler], list[httpx.Request]]:
    def install(handler: Handler) -> list[httpx.Request]:
        seen: list[httpx.Request] = []

        def record(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return handler(request)

        monkeypatch.setattr(chttp, "_transport", httpx.MockTransport(record))
        monkeypatch.setattr(chttp, "RETRY_WAIT", 0.0)
        return seen

    return install


IBGE = "https://servicodados.ibge.gov.br/api/v1/localidades/regioes"


def test_lista_fixa_cobre_os_servicos_verificados() -> None:
    assert "api.bcb.gov.br" in hosts.ALLOWED_HOSTS
    assert "arquivos.receitafederal.gov.br" in hosts.ALLOWED_HOSTS
    for service in hosts.SERVICES.values():
        assert hosts.allowed(service.probe), service.id
        assert hosts.service_of(service.probe) is service, service.id
        assert service.probe_method in ("GET", "HEAD", "PROPFIND")


@pytest.mark.parametrize(
    "url",
    [
        "http://servicodados.ibge.gov.br/api/v1/localidades/regioes",  # sem criptografia
        "https://exemplo.com/dados",  # fora da lista
        "https://servicodados.ibge.gov.br.exemplo.com/x",  # parecido, mas outro host
        "https://user:senha@servicodados.ibge.gov.br/x",  # credencial no endereço
        "https://servicodados.ibge.gov.br:8443/x",  # outra porta
        "https://169.254.169.254/latest/meta-data",
    ],
)
def test_recusa_endereco_fora_da_lista(url: str, serve: Callable[[Handler], list[httpx.Request]]) -> None:
    seen = serve(lambda r: httpx.Response(200, json=[]))
    with CatalogClient() as client, pytest.raises(CatalogError) as err:
        client.get(url)
    assert err.value.kind == "recusado"
    assert seen == []


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH"])
def test_so_metodos_de_leitura(method: str, serve: Callable[[Handler], list[httpx.Request]]) -> None:
    seen = serve(lambda r: httpx.Response(200))
    with CatalogClient() as client, pytest.raises(CatalogError) as err:
        client.request(method, IBGE)  # type: ignore[arg-type]
    assert err.value.kind == "recusado"
    assert seen == []


def test_consulta_com_espaco_como_por_cento_20(serve: Callable[[Handler], list[httpx.Request]]) -> None:
    seen = serve(lambda r: httpx.Response(200, json={"value": []}))
    url = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/ExpectativaMercadoMensais"
    with CatalogClient() as client:
        client.get(url, params={"$top": 10, "$orderby": "Data desc", "@moeda": "'USD'"})
    raw = seen[0].url.raw_path.decode()
    assert "$orderby=Data%20desc" in raw
    assert "+" not in raw
    assert "@moeda='USD'" in raw
    assert "$top=10" in raw


def test_redirecionamento_dentro_da_lista_e_seguido(serve: Callable[[Handler], list[httpx.Request]]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/antigo"):
            return httpx.Response(302, headers={"location": "/api/v1/localidades/regioes"})
        return httpx.Response(200, json=[{"id": 1}])

    serve(handler)
    with CatalogClient() as client:
        answer = client.get("https://servicodados.ibge.gov.br/antigo")
    assert answer.json() == [{"id": 1}]
    assert answer.url == IBGE


@pytest.mark.parametrize("target", ["https://exemplo.com/x", "http://servicodados.ibge.gov.br/x"])
def test_redirecionamento_para_fora_e_recusado(
    target: str, serve: Callable[[Handler], list[httpx.Request]]
) -> None:
    seen = serve(lambda r: httpx.Response(302, headers={"location": target}))
    with CatalogClient() as client, pytest.raises(CatalogError) as err:
        client.get(IBGE)
    assert err.value.kind == "recusado"
    assert "IBGE" in err.value.message
    assert len(seen) == 1


def test_link_publico_nao_vai_para_outro_host(serve: Callable[[Handler], list[httpx.Request]]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "arquivos.receitafederal.gov.br":
            return httpx.Response(302, headers={"location": "https://www.anbima.com.br/x"})
        return httpx.Response(207, text="<d:multistatus/>")

    seen = serve(handler)
    with CatalogClient() as client:
        client.propfind(f"{hosts.CNPJ_DAV}/", b"<x/>", auth=("link", ""))
    assert seen[0].method == "PROPFIND"
    assert seen[0].headers["authorization"].startswith("Basic ")
    assert "authorization" not in seen[1].headers


def test_resposta_grande_demais(serve: Callable[[Handler], list[httpx.Request]]) -> None:
    serve(lambda r: httpx.Response(200, content=b"x" * 5000))
    with CatalogClient(max_bytes=1000) as client, pytest.raises(CatalogError) as err:
        client.get(IBGE)
    assert err.value.kind == "limite"


def test_erro_http_em_palavras_com_o_orgao(serve: Callable[[Handler], list[httpx.Request]]) -> None:
    serve(lambda r: httpx.Response(503))
    with CatalogClient() as client, pytest.raises(CatalogError) as err:
        client.get(IBGE, retries=0)
    assert err.value.kind == "http"
    assert err.value.message == "O site do IBGE respondeu erro 503: serviço indisponível."


def test_tenta_de_novo_em_503(serve: Callable[[Handler], list[httpx.Request]]) -> None:
    answers = iter([httpx.Response(503), httpx.Response(200, json=[])])
    seen = serve(lambda r: next(answers))
    with CatalogClient() as client:
        assert client.get(IBGE).json() == []
    assert len(seen) == 2


def test_codigo_esperado_nao_vira_erro(serve: Callable[[Handler], list[httpx.Request]]) -> None:
    serve(lambda r: httpx.Response(406, json={"error": "10 anos"}))
    with CatalogClient() as client:
        assert client.get(IBGE, ok=frozenset({406})).status == 406


def test_tempo_esgotado_diz_o_orgao(serve: Callable[[Handler], list[httpx.Request]]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("devagar", request=request)

    serve(handler)
    with CatalogClient(timeout=5) as client, pytest.raises(CatalogError) as err:
        client.get(IBGE, retries=0)
    assert err.value.kind == "tempo"
    assert err.value.message == "O site do IBGE não respondeu em 5 segundos."


def test_sem_conexao_e_outro_tipo() -> None:
    # O conftest deixa o catálogo sem rede.
    with CatalogClient() as client, pytest.raises(CatalogError) as err:
        client.get(IBGE, retries=0)
    assert err.value.kind == "conexao"


def test_download_em_partes_com_range(serve: Callable[[Handler], list[httpx.Request]]) -> None:
    seen = serve(lambda r: httpx.Response(206, content=b"abc", headers={"content-range": "bytes 10-12/100"}))
    url = f"{hosts.CNPJ_DAV}/2026-11/Cnaes.zip"
    with (
        CatalogClient() as client,
        client.stream(url, headers={"Range": "bytes=10-"}, auth=("link", "")) as res,
    ):
        assert res.status_code == 206
        assert b"".join(res.iter_bytes()) == b"abc"
    assert seen[0].headers["range"] == "bytes=10-"
    assert seen[0].headers["accept-encoding"] == "identity"


def test_download_fora_da_lista(serve: Callable[[Handler], list[httpx.Request]]) -> None:
    seen = serve(lambda r: httpx.Response(200))
    with CatalogClient() as client, pytest.raises(CatalogError), client.stream("https://exemplo.com/a.zip"):
        pass
    assert seen == []
