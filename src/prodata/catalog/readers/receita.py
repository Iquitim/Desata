"""Dados abertos do CNPJ na pasta pública da Receita (spec 049, RF-4951, RF-4956).

A Receita publica uma pasta por mês (``AAAA-MM``) num Nextcloud oficial, com os ZIPs de cada parte: Empresas0..9,
Estabelecimentos0..9, Socios0..9, Simples e as tabelas auxiliares. A listagem é por WebDAV (PROPFIND), com o link
público de compartilhamento do próprio órgão (não é credencial, constituição 1.8.1). Nada aqui baixa os ZIPs: isso
é do ``catalog.download``, na pasta que a pessoa escolher.
"""

from __future__ import annotations

import contextlib
import re
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import unquote

from prodata.catalog import hosts
from prodata.catalog.http import CatalogClient, CatalogError
from prodata.catalog.model import SourceNotFoundError, safe_xml

_DAV = "{DAV:}"
_BODY = (
    b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/><d:getcontentlength/>'
    b"<d:getlastmodified/></d:prop></d:propfind>"
)
_MONTH = re.compile(r"^(\d{4})-(\d{2})$")
_PART = re.compile(r"^([A-Za-z]+?)(\d*)\.zip$")
LISTING_MAX = 4 * 1024 * 1024

# Os grupos de partes, na ordem da tela, com o nome em português e o padrão de marcação (RF-4951).
GROUPS: tuple[tuple[str, str, str, bool], ...] = (
    (
        "empresas",
        "Empresas",
        "Razão social, natureza jurídica, porte e capital social de cada CNPJ básico.",
        True,
    ),
    (
        "estabelecimentos",
        "Estabelecimentos",
        "Matriz e filiais: endereço, situação cadastral, CNAE, datas.",
        True,
    ),
    ("socios", "Sócios", "Quadro de sócios e administradores.", False),
    ("simples", "Simples e MEI", "Opção pelo Simples Nacional e pelo MEI, com as datas.", False),
    ("cnaes", "CNAE", "Tabela das atividades econômicas.", True),
    ("municipios", "Municípios", "Tabela dos municípios no código da Receita.", True),
    ("naturezas", "Naturezas jurídicas", "Tabela das naturezas jurídicas.", True),
    ("paises", "Países", "Tabela dos países.", True),
    ("qualificacoes", "Qualificações", "Tabela das qualificações dos sócios.", True),
    ("motivos", "Motivos", "Tabela dos motivos da situação cadastral.", True),
)
GROUP_NAMES = {g[0]: g[1] for g in GROUPS}
_GROUP_OF = {"empresas": "empresas", "estabelecimentos": "estabelecimentos", "socios": "socios", "simples": "simples",
             "cnaes": "cnaes", "municipios": "municipios", "naturezas": "naturezas", "paises": "paises",
             "qualificacoes": "qualificacoes", "motivos": "motivos"}  # fmt: skip


@dataclass(frozen=True)
class Part:
    arquivo: str  # Empresas0.zip
    grupo: str  # empresas
    indice: int | None  # 0..9; None nas tabelas de um arquivo só
    tamanho: int
    url: str

    def as_dict(self) -> dict[str, Any]:
        return {"arquivo": self.arquivo, "grupo": self.grupo, "indice": self.indice, "tamanho": self.tamanho,
                "url": self.url}  # fmt: skip


def _auth(link: str) -> tuple[str, str]:
    return (link, "")


def _base(link_index: int) -> str:
    return f"{hosts.CNPJ_DAV}{hosts.CNPJ_LINKS[link_index][1]}"


def auth_for(url: str) -> tuple[str, str]:
    """O link público certo para um endereço da pasta (o principal ou o alternativo)."""
    for link, root in hosts.CNPJ_LINKS:
        if root and url.startswith(f"{hosts.CNPJ_DAV}{root}/"):
            return _auth(link)
    return _auth(hosts.CNPJ_LINKS[-1][0])


def _listing(client: CatalogClient, path: str) -> tuple[list[dict[str, Any]], int]:
    """Lista uma pasta, no link principal e, se ele falhar, no alternativo (devolve também qual funcionou)."""
    error: CatalogError | None = None
    for index, (link, _root) in enumerate(hosts.CNPJ_LINKS):
        url = f"{_base(index)}{path}"
        try:
            answer = client.propfind(url, _BODY, auth=_auth(link), max_bytes=LISTING_MAX)
        except CatalogError as exc:
            if exc.kind == "recusado":
                raise
            error = exc
            continue
        return _entries(answer.body), index
    assert error is not None
    raise error


def _entries(body: bytes) -> list[dict[str, Any]]:
    try:
        root = safe_xml(body)
    except (ValueError, SyntaxError) as exc:
        raise CatalogError(
            f"A listagem da Receita veio num formato inesperado ({exc}).", "resposta"
        ) from None
    out = []
    for response in root.iter(f"{_DAV}response"):
        href = unquote(response.findtext(f"{_DAV}href") or "")
        props: dict[str, Any] = {"nome": href.rstrip("/").rsplit("/", 1)[-1], "pasta": href.endswith("/")}
        for prop in response.iter(f"{_DAV}prop"):
            size = prop.findtext(f"{_DAV}getcontentlength")
            if size and size.isdigit():
                props["tamanho"] = int(size)
            modified = prop.findtext(f"{_DAV}getlastmodified")
            if modified:
                with contextlib.suppress(TypeError, ValueError):
                    props["modificado"] = parsedate_to_datetime(modified).isoformat()
            if prop.find(f"{_DAV}resourcetype/{_DAV}collection") is not None:
                props["pasta"] = True
        out.append(props)
    return out


def months(client: CatalogClient) -> list[str]:
    """Os meses publicados, do mais antigo ao mais novo."""
    entries, _index = _listing(client, "/")
    found = sorted({e["nome"] for e in entries if e["pasta"] and _MONTH.match(e["nome"])})
    if not found:
        raise SourceNotFoundError("A pasta da Receita não tem nenhum mês publicado agora.")
    return found


def parts(client: CatalogClient, month: str) -> list[Part]:
    """As partes de um mês, com o tamanho de cada uma (da própria listagem, sem baixar nada)."""
    if not _MONTH.match(month):
        raise SourceNotFoundError(f"Mês inválido: {month!r} (esperado AAAA-MM).")
    entries, index = _listing(client, f"/{month}/")
    out: list[Part] = []
    for e in entries:
        match = _PART.match(e["nome"]) if not e["pasta"] else None
        if not match:
            continue
        group = _GROUP_OF.get(match.group(1).lower())
        if group is None or "tamanho" not in e:
            continue  # arquivo que o programa não conhece: fica de fora, sem adivinhar
        out.append(Part(arquivo=e["nome"], grupo=group, indice=int(match.group(2)) if match.group(2) else None,
                        tamanho=e["tamanho"], url=f"{_base(index)}/{month}/{e['nome']}"))  # fmt: skip
    if not out:
        raise SourceNotFoundError(f"A pasta {month} da Receita ainda não tem os arquivos.")
    order = {g[0]: i for i, g in enumerate(GROUPS)}
    return sorted(out, key=lambda p: (order[p.grupo], p.indice or 0))


def summary(client: CatalogClient) -> dict[str, Any]:
    """O mês mais recente, as partes por grupo, com o tamanho de cada uma e o total (RF-4951)."""
    month = months(client)[-1]
    found = parts(client, month)
    groups = []
    for gid, name, description, default in GROUPS:
        items = [p for p in found if p.grupo == gid]
        if items:
            groups.append({"id": gid, "nome": name, "descricao": description, "padrao": default,
                           "arquivos": [p.as_dict() for p in items], "tamanho": sum(p.tamanho for p in items)})  # fmt: skip
    return {"mes": month, "grupos": groups, "tamanho": sum(p.tamanho for p in found)}
