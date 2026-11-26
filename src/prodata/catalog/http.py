"""Cliente HTTP do catálogo (spec 049, RF-4981, RF-4982).

- Só os endereços de ``hosts.ALLOWED_HOSTS``, só HTTPS, só métodos de leitura (GET, HEAD e PROPFIND para listar a
  pasta do CNPJ). Redirecionamento é seguido à mão e conferido a cada passo; para fora da lista, é recusado.
- A resposta tem tamanho máximo, lido aos pedaços: um órgão que manda demais não enche a memória.
- A consulta vai com espaço como ``%20`` (o OData do Banco Central recusa o ``+``) e mantém ``$ @ ' ( ) ,``.
- As mensagens dizem o órgão e o motivo em palavras ("o site do IBGE não respondeu em 5 segundos"), e o tipo da
  falha (``kind``) separa "sem conexão" de "órgão fora do ar" (RF-4923).
"""

from __future__ import annotations

import base64
import json
import logging
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote, urlencode, urljoin, urlsplit

import httpx

from prodata import __version__
from prodata.brand import marca
from prodata.catalog import hosts
from prodata.connectors.api import _system_tls

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

Method = Literal["GET", "HEAD", "PROPFIND", "POST"]
FailureKind = Literal["recusado", "conexao", "tempo", "http", "limite", "resposta", "bloqueio"]

# Página de bloqueio de leitura automática no lugar da resposta (Goiás, Vitória: "Acesso negado", "Request Rejected").
_BLOCK_MARKS = ("acesso negado", "request rejected", "access denied", "the requested url was rejected")

READ_METHODS: frozenset[str] = frozenset({"GET", "HEAD", "PROPFIND"})
MAX_REDIRECTS = 5
DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_BYTES = 64 * 1024 * 1024
RETRY_STATUS = frozenset({429, 502, 503, 504})
RETRY_WAIT = 1.0

# Trocado nos testes por um transporte simulado; o conftest põe um que recusa tudo (nenhum teste sai para a rede).
_transport: httpx.BaseTransport | None = None

_STATUS_TEXT = {
    400: "pedido recusado",
    403: "acesso negado",
    404: "endereço não encontrado",
    429: "pedidos demais em pouco tempo",
    500: "erro interno do site",
    502: "erro no servidor intermediário",
    503: "serviço indisponível",
    504: "o servidor intermediário não teve resposta",
}


class CatalogError(Exception):
    def __init__(self, message: str, kind: FailureKind, status: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.kind = kind
        self.status = status


@dataclass
class Answer:
    status: int
    headers: httpx.Headers
    body: bytes
    url: str
    seconds: float

    def json(self) -> Any:
        try:
            return json.loads(self.body)
        except ValueError:
            if blocked(self.body):
                raise block_error(self.url) from None
            raise CatalogError(
                f"{_cap(_site(self.url))} devolveu uma resposta que não é JSON.", "resposta"
            ) from None

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", "replace")


def blocked(body: bytes) -> bool:
    """A resposta é uma página de bloqueio de programas (e não o dado pedido)."""
    head = body[:4000].decode("utf-8", "replace").lower()
    return "<html" in head and any(mark in head for mark in _BLOCK_MARKS)


def block_error(url: str) -> CatalogError:
    # O programa se identifica com o próprio nome e não se passa por navegador: o motivo vai em palavras.
    return CatalogError(
        f"{_cap(_site(url))} recusou o programa: o portal bloqueia a leitura automática. Abra no navegador.",
        "bloqueio",
        403,
    )


def basic_header(auth: tuple[str, str]) -> str:
    return "Basic " + base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()


def _site(url: str) -> str:
    service = hosts.service_of(url)
    if service is None:
        return hosts.host_of(url)
    return service.site or f"o site do {service.short}"


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def encode_query(params: Mapping[str, Any] | None) -> str:
    if not params:
        return ""
    pairs = [(k, "" if v is None else str(v)) for k, v in params.items()]
    return urlencode(pairs, quote_via=quote, safe="$@'(),:")


def with_query(url: str, params: Mapping[str, Any] | None) -> str:
    query = encode_query(params)
    if not query:
        return url
    return f"{url}{'&' if urlsplit(url).query else '?'}{query}"


def user_agent() -> str:
    return f"{marca().nome_curto}/{__version__} (catalogo de dados publicos)"


class CatalogClient:
    """Um cliente por tarefa (conferência, leitura, download); fechar depois de usar."""

    def __init__(self, *, timeout: float = DEFAULT_TIMEOUT, max_bytes: int = DEFAULT_MAX_BYTES) -> None:
        self.timeout = timeout
        self.max_bytes = max_bytes
        options: dict[str, Any] = {
            "timeout": timeout,
            "follow_redirects": False,
            "headers": {"User-Agent": user_agent(), "Accept-Encoding": "gzip"},
        }
        if _transport is not None:
            options["transport"] = _transport
        else:
            options["verify"] = _system_tls()
        self.client = httpx.Client(**options)

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> CatalogClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # ---------------------------------------------------------------- conferências

    @staticmethod
    def check(url: str, method: str = "GET") -> None:
        if method == "POST":
            # A consulta do Comex Stat só existe por POST; em nenhum outro endereço o catálogo usa POST.
            if not hosts.post_allowed(url):
                raise CatalogError(f"O catálogo só lê dados: o método {method} não é usado aqui.", "recusado")
            return
        if method not in READ_METHODS:
            raise CatalogError(f"O catálogo só lê dados: o método {method} não é usado.", "recusado")
        if not hosts.allowed(url):
            shown = hosts.host_of(url) or url[:80]
            raise CatalogError(
                f"{shown} não está na lista de endereços oficiais do catálogo. O {marca().nome} não acessa esse endereço.",
                "recusado",
            )

    def _message(self, exc: Exception, url: str, timeout: float) -> CatalogError:
        site = _site(url)
        if isinstance(exc, httpx.TimeoutException):
            return CatalogError(f"{_cap(site)} não respondeu em {timeout:g} segundos.", "tempo")
        text = str(exc)
        if "CERTIFICATE_VERIFY_FAILED" in text or "certificate" in text.lower():
            return CatalogError(
                f"O certificado de {hosts.host_of(url)} não pôde ser conferido neste computador: o site pode estar "
                "enviando o certificado incompleto, ou a rede da empresa troca o certificado. O programa não lê sem "
                "conferir; se persistir, fale com a TI.",
                "conexao",
            )
        if isinstance(exc, httpx.ConnectError | httpx.NetworkError):
            return CatalogError(f"Não foi possível conectar com {site}. Confira a internet.", "conexao")
        return CatalogError(f"Falha de rede ao acessar {site}.", "conexao")

    # ---------------------------------------------------------------- pedido

    def _send(
        self,
        method: Method,
        url: str,
        headers: Mapping[str, str],
        content: bytes | None,
        auth: tuple[str, str] | None,
        timeout: float,
        max_bytes: int,
    ) -> Answer:
        start = time.perf_counter()
        first_host = hosts.host_of(url)
        for _ in range(MAX_REDIRECTS + 1):
            self.check(url, method)
            # O link público da Receita só vai para o host de onde veio.
            send_auth = auth if hosts.host_of(url) == first_host else None
            request = self.client.build_request(
                method, url, headers=dict(headers), content=content, timeout=timeout
            )
            if send_auth:
                request.headers["Authorization"] = basic_header(send_auth)
            try:
                response = self.client.send(request, stream=True)
            except httpx.HTTPError as exc:
                raise self._message(exc, url, timeout) from None
            try:
                location = response.headers.get("location")
                if response.status_code in (301, 302, 303, 307, 308) and location:
                    if method == "POST":
                        raise CatalogError(
                            f"{_cap(_site(url))} redirecionou a consulta; o catálogo não seguiu.", "recusado"
                        )
                    target = urljoin(url, location)
                    if not hosts.allowed(target):
                        raise CatalogError(
                            f"{_cap(_site(url))} redirecionou para um endereço fora da lista oficial "
                            f"({hosts.host_of(target) or 'sem endereço'}). O {marca().nome} não seguiu.",
                            "recusado",
                        )
                    url = target
                    continue
                body = self._read_body(response, url, max_bytes, method)
            except httpx.HTTPError as exc:
                raise self._message(exc, url, timeout) from None
            finally:
                response.close()
            return Answer(response.status_code, response.headers, body, url, time.perf_counter() - start)
        raise CatalogError(f"{_cap(_site(url))} redirecionou vezes demais.", "resposta")

    def _read_body(self, response: httpx.Response, url: str, max_bytes: int, method: str) -> bytes:
        if method == "HEAD":
            return b""
        declared = response.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > max_bytes:
            raise self._too_big(url, max_bytes)
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > max_bytes:
                raise self._too_big(url, max_bytes)
            chunks.append(chunk)
        return b"".join(chunks)

    @staticmethod
    def _too_big(url: str, max_bytes: int) -> CatalogError:
        return CatalogError(
            f"A resposta de {_site(url)} passou do limite de {max_bytes // (1024 * 1024)} MB do catálogo.",
            "limite",
        )

    def request(
        self,
        method: Method,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        content: bytes | None = None,
        auth: tuple[str, str] | None = None,
        timeout: float | None = None,
        max_bytes: int | None = None,
        retries: int = 2,
        ok: frozenset[int] = frozenset(),
    ) -> Answer:
        """Faz o pedido; erro HTTP vira ``CatalogError`` com o motivo, salvo os códigos em ``ok``."""
        full = with_query(url, params)
        limit = timeout or self.timeout
        for attempt in range(retries + 1):
            try:
                answer = self._send(
                    method, full, headers or {}, content, auth, limit, max_bytes or self.max_bytes
                )
            except CatalogError as exc:
                if exc.kind == "tempo" and attempt < retries:
                    time.sleep(RETRY_WAIT * 2**attempt)
                    continue
                raise
            if answer.status in RETRY_STATUS and attempt < retries:
                time.sleep(RETRY_WAIT * 2**attempt)
                continue
            # 304 sem o programa ter pedido (cache do lado do órgão, visto no Banco Central): pede de novo sem cache.
            if answer.status == 304 and attempt < retries and "Cache-Control" not in (headers or {}):
                headers = {**(headers or {}), "Cache-Control": "no-cache", "Pragma": "no-cache"}
                continue
            if answer.status >= 400 and answer.status not in ok:
                raise http_error(answer)
            return answer
        raise CatalogError(
            f"{_cap(_site(full))} não respondeu.", "tempo"
        )  # pragma: no cover (o laço sempre volta)

    def get(self, url: str, **kwargs: Any) -> Answer:
        return self.request("GET", url, **kwargs)

    def head(self, url: str, **kwargs: Any) -> Answer:
        return self.request("HEAD", url, **kwargs)

    def post_query(self, url: str, query: Any, **kwargs: Any) -> Answer:
        """A consulta de um órgão que só a aceita por POST (corpo JSON montado pelo programa, só com a consulta)."""
        body = json.dumps(query, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        return self.request("POST", url, headers=headers, content=body, **kwargs)

    def propfind(self, url: str, body: bytes, *, auth: tuple[str, str], **kwargs: Any) -> Answer:
        headers = {"Depth": "1", "Content-Type": "application/xml"}
        return self.request("PROPFIND", url, headers=headers, content=body, auth=auth, **kwargs)

    def download_to(
        self, url: str, dest: Path, *, max_bytes: int, timeout: float | None = None
    ) -> tuple[str, int, httpx.Headers]:
        """Baixa ``url`` para ``dest`` (arquivos dos portais, RF-4938/4940).

        Segue redirecionamento só dentro da lista oficial; grava em ``<dest>.parte`` e só renomeia no fim, então um
        arquivo pela metade nunca fica com o nome final. Passou de ``max_bytes``: para, apaga e diz que é grande.
        Devolve o endereço final, o tamanho e os cabeçalhos.
        """
        limit = timeout or self.timeout
        partial = dest.with_name(dest.name + ".parte")
        dest.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(MAX_REDIRECTS + 1):
            self.check(url, "GET")
            request = self.client.build_request(
                "GET", url, headers={"Accept-Encoding": "identity"}, timeout=limit
            )
            try:
                response = self.client.send(request, stream=True)
            except httpx.HTTPError as exc:
                raise self._message(exc, url, limit) from None
            try:
                location = response.headers.get("location")
                if response.status_code in (301, 302, 303, 307, 308) and location:
                    target = urljoin(url, location)
                    if not hosts.allowed(target):
                        raise CatalogError(
                            f"{_cap(_site(url))} redirecionou o arquivo para um endereço fora da lista oficial "
                            f"({hosts.host_of(target) or 'sem endereço'}). O {marca().nome} não seguiu.",
                            "recusado",
                        )
                    url = target
                    continue
                if response.status_code >= 400:
                    raise http_error(Answer(response.status_code, response.headers, b"", url, 0.0))
                declared = response.headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > max_bytes:
                    raise self._too_big(url, max_bytes)
                size = 0
                try:
                    with partial.open("wb") as fh:
                        for chunk in response.iter_bytes():
                            size += len(chunk)
                            if size > max_bytes:
                                raise self._too_big(url, max_bytes)
                            fh.write(chunk)
                except BaseException:
                    partial.unlink(missing_ok=True)
                    raise
                partial.replace(dest)
                return url, size, response.headers
            except httpx.HTTPError as exc:
                partial.unlink(missing_ok=True)
                raise self._message(exc, url, limit) from None
            finally:
                response.close()
        raise CatalogError(f"{_cap(_site(url))} redirecionou vezes demais.", "resposta")

    @contextmanager
    def stream(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        auth: tuple[str, str] | None = None,
        timeout: float | None = None,
    ) -> Iterator[httpx.Response]:
        """GET em partes para os downloads grandes (RF-4953). Não segue redirecionamento: o download é direto."""
        self.check(url, "GET")
        request = self.client.build_request(
            "GET",
            url,
            headers={**(headers or {}), "Accept-Encoding": "identity"},
            timeout=timeout or self.timeout,
        )
        if auth:
            request.headers["Authorization"] = basic_header(auth)
        try:
            response = self.client.send(request, stream=True)
        except httpx.HTTPError as exc:
            raise self._message(exc, url, timeout or self.timeout) from None
        try:
            if response.status_code >= 400:
                raise http_error(Answer(response.status_code, response.headers, b"", url, 0.0))
            if response.status_code in (301, 302, 303, 307, 308):
                raise CatalogError(
                    f"{_cap(_site(url))} redirecionou o download; tente de novo mais tarde.", "resposta"
                )
            yield response
        finally:
            response.close()


def http_error(answer: Answer) -> CatalogError:
    status = answer.status
    if status == 403 and blocked(answer.body):
        return block_error(answer.url)
    try:
        phrase = _STATUS_TEXT.get(status) or HTTPStatus(status).phrase
    except ValueError:
        phrase = "erro"
    return CatalogError(f"{_cap(_site(answer.url))} respondeu erro {status}: {phrase}.", "http", status)
