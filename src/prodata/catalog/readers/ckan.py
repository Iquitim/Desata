"""Portais de dados abertos (CKAN): catálogo, detalhe do conjunto e classificação dos arquivos (spec 049).

RF-4936 (navegar por portal), RF-4939 (Pronto ou Leitura automática) e RF-4940 (tamanho, formato e endereço).
Cada arquivo de um conjunto é classificado antes de qualquer leitura:
- ``legivel``: formato que o programa lê, em endereço da lista, até 200 MB → leitura direta com prévia;
- ``grande``: legível, mas acima de 200 MB → download com pasta escolhida;
- ``odata``: serviço OData do Banco Central → leitor de OData;
- ``so_link``: PDF, página, formato que o programa não lê ou endereço fora da lista → Abrir no navegador, com o motivo.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Literal
from urllib.parse import urlsplit

from prodata.catalog import hosts
from prodata.catalog.http import CatalogClient, CatalogError
from prodata.catalog.model import SourceNotFoundError
from prodata.catalog.portals import BY_ID, Portal
from prodata.catalog.readers import odata

MAX_DIRECT_BYTES = 200 * 1024 * 1024
PAGE = 500
_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,200}$")
Situation = Literal["legivel", "grande", "odata", "so_link"]

READABLE = {"csv", "txt", "tsv", "xlsx", "xls", "xlsb", "xlsm", "parquet", "json", "ndjson", "zip"}
LINK_REASONS = {
    "pdf": "arquivo PDF: o programa não lê tabelas de PDF de portais",
    "html": "página da web, não um arquivo de dados",
    "ods": "planilha ODS: o programa ainda não lê esse formato",
    "xml": "arquivo XML: o programa não lê XML de portais",
    "geo": "mapa (dado geográfico): o programa não lê esse formato",
    "7z": "arquivo 7z: o programa só abre ZIP",
    "rar": "arquivo RAR: o programa só abre ZIP",
    "doc": "documento de texto, não uma tabela",
    "imagem": "imagem, não uma tabela",
    "api": "serviço sem formato de arquivo conhecido",
    "hash": "arquivo de conferência de integridade (hash), não uma tabela",
}
_ALIASES = {
    "csv/zip": "zip", "zip/csv": "zip", "zip": "zip", "application/zip": "zip", "application/x-zip-compressed": "zip",
    "application/x-7z-compressed": "7z", "7z": "7z", "rar": "rar", "text/csv": "csv", "csv": "csv", "txt": "txt",
    "tsv": "tsv", "xlsx": "xlsx", "xls": "xls", "xlsb": "xlsb", "xlsm": "xlsm", "parquet": "parquet", "json": "json",
    "ndjson": "ndjson", "jsonl": "ndjson", "pdf": "pdf", "html": "html", "htm": "html", "ods": "ods", "xml": "xml",
    "shp": "geo", "shp-zip": "geo", "geojson": "geo", "kml": "geo", "kmz": "geo", "wms": "geo", "doc": "doc",
    "docx": "doc", "odt": "doc", "jpeg": "imagem", "jpg": "imagem", "png": "imagem", "api": "api", "odata": "api",
    "sha512": "hash", "sha256": "hash", "sha1": "hash", "md5": "hash",
}  # fmt: skip


def portal(portal_id: str) -> Portal:
    found = BY_ID.get(portal_id)
    if found is None:
        raise SourceNotFoundError(f"O portal {portal_id!r} não está entre os portais verificados.")
    return found


def _format(declared: str, url: str) -> str:
    text = (declared or "").strip().lower().lstrip(".")
    if text in _ALIASES:
        return _ALIASES[text]
    path = urlsplit(url).path.lower()
    if path.endswith(".csv.zip"):
        return "zip"
    ext = path.rsplit(".", 1)[-1] if "." in path.rsplit("/", 1)[-1] else ""
    return _ALIASES.get(ext, text or ext or "desconhecido")


@dataclass(frozen=True)
class Resource:
    id: str
    nome: str
    formato: str
    url: str
    tamanho: int | None
    atualizado: str
    situacao: Situation
    motivo: str = ""
    descricao: str = ""

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def classify(raw: dict[str, Any]) -> Resource:
    url = str(raw.get("url") or "").strip()
    fmt = _format(str(raw.get("format") or ""), url)
    size = raw.get("size")
    size_int = (
        int(size) if isinstance(size, int | float) or (isinstance(size, str) and size.isdigit()) else None
    )
    base: dict[str, Any] = {
        "id": str(raw.get("id") or ""),
        "nome": str(raw.get("name") or raw.get("description") or "Arquivo").strip()[:200],
        "formato": fmt,
        "url": url,
        "tamanho": size_int,
        "atualizado": str(
            raw.get("last_modified") or raw.get("metadata_modified") or raw.get("created") or ""
        ),
        "descricao": str(raw.get("description") or "").strip()[:500],
    }
    if odata.parse_resource_url(url) is not None:
        return Resource(**base, situacao="odata")
    if not url.startswith(("https://", "http://")) or not urlsplit(url).hostname:
        return Resource(
            **base, situacao="so_link", motivo="o portal publicou um endereço inválido para este arquivo"
        )
    if not hosts.allowed(url):
        why = (
            "arquivo sem criptografia (http)"
            if url.startswith("http://")
            else "arquivo em outro site, fora da lista oficial"
        )
        return Resource(**base, situacao="so_link", motivo=why)
    if fmt not in READABLE:
        return Resource(
            **base,
            situacao="so_link",
            motivo=LINK_REASONS.get(fmt, f"formato {fmt.upper()}: o programa não lê"),
        )
    if size_int is not None and size_int > MAX_DIRECT_BYTES:
        return Resource(
            **base, situacao="grande", motivo="acima de 200 MB: vai pelo download com pasta escolhida"
        )
    return Resource(**base, situacao="legivel")


def _summary(p: dict[str, Any], portal_id: str) -> dict[str, Any]:
    resources = p.get("resources") or []
    formats = sorted({_format(str(r.get("format") or ""), str(r.get("url") or "")) for r in resources})
    readable = sum(1 for r in resources if classify(r).situacao in ("legivel", "grande", "odata"))
    org = p.get("organization") or {}
    return {
        "id": f"ckan/{portal_id}/{p.get('name')}",
        "codigo": p.get("name"),
        "nome": (p.get("title") or p.get("name") or "").strip(),
        "resumo": re.sub(r"\s+", " ", re.sub(r"[#*_`>\[\]]", "", p.get("notes") or "")).strip()[:240],
        "grupo": org.get("title") or "",
        "grupos": [g.get("title") or g.get("name") for g in p.get("groups") or []],
        "temas": [t.get("display_name") or t.get("name") for t in (p.get("tags") or [])[:12]],
        "atualizado": p.get("metadata_modified") or "",
        "licenca": p.get("license_title") or "",
        "formatos": formats,
        "recursos": len(resources),
        "legiveis": readable,
        "leitura_automatica": True,
    }


def catalog(client: CatalogClient, portal_id: str) -> list[dict[str, Any]]:
    """Todos os conjuntos do portal, resumidos (os arquivos de cada um vêm no detalhe, na hora)."""
    return catalog_with_warnings(client, portal_id)[0]


def catalog_with_warnings(client: CatalogClient, portal_id: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Como ``catalog``, e os avisos: uma página que o portal corta é lida de novo um conjunto por vez; o que mesmo
    assim não vem é contado e dito, nunca perdido em silêncio."""
    site = portal(portal_id)
    size = min(PAGE, site.lote)
    params: dict[str, Any] = {"sort": "name asc"}
    if portal_id == "bcb_portal":
        params["fq"] = "-codigo_sgs:[* TO *]"  # as séries do SGS já estão no catálogo do SGS
    out: list[dict[str, Any]] = []
    lost = 0
    start = 0
    total: int | None = None

    def page(first: int, rows: int) -> dict[str, Any]:
        result = client.get(
            f"{site.api}/package_search", params={**params, "rows": rows, "start": first}, timeout=120
        )
        body: dict[str, Any] = result.json().get("result") or {}
        return body

    while total is None or start < total:
        try:
            body = page(start, size)
        except CatalogError as exc:
            if total is None or exc.kind not in ("conexao", "resposta"):
                raise
            for one in range(start, min(start + size, total)):
                try:
                    out.extend(
                        _summary(p, portal_id) for p in page(one, 1).get("results") or [] if p.get("name")
                    )
                except CatalogError:
                    lost += 1
            start += size
            continue
        total = int(body.get("count") or 0)
        found = body.get("results") or []
        out.extend(_summary(p, portal_id) for p in found if p.get("name"))
        if not found:
            break
        start += len(found)
    warnings = (
        [f"{lost} conjunto(s) não puderam ser lidos: {site.site} corta respostas grandes."] if lost else []
    )
    return out, warnings


def dataset(client: CatalogClient, portal_id: str, name: str) -> dict[str, Any]:
    """O conjunto com todos os arquivos classificados (RF-4940)."""
    site = portal(portal_id)
    if not _NAME.match(name):
        raise SourceNotFoundError(f"{name!r} não é o nome de um conjunto de portal.")
    answer = client.get(f"{site.api}/package_show", params={"id": name}, ok=frozenset({404}), timeout=60)
    body = answer.json() if answer.status != 404 else {}
    p = body.get("result") if isinstance(body, dict) and body.get("success") else None
    if not p:
        raise SourceNotFoundError(f"O conjunto {name} não existe em {site.site}.")
    summary = _summary(p, portal_id)
    summary["descricao"] = (p.get("notes") or "").strip()
    summary["autor"] = p.get("author") or p.get("maintainer") or ""
    summary["pagina"] = f"{site.ckan}/dataset/{p.get('name')}"
    summary["arquivos"] = [classify(r).to_json() for r in p.get("resources") or []]
    return summary
