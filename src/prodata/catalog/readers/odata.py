"""OData do Banco Central (Olinda), lido pela descrição do próprio serviço (spec 049, RF-4937).

Conferido na T04b (52 serviços, 682 conjuntos do portal):
- ``$metadata`` (XML, OData 4) dá as tabelas (EntitySet), as funções com parâmetros (FunctionImport/Function) e as
  colunas com tipo (EntityType); os conjuntos com "_" na frente são só o suporte das funções;
- ``/swagger`` dá o título de cada consulta, a descrição dos parâmetros e quais são inteiros;
- quase todo parâmetro é declarado como texto, e o formato da data muda de um serviço para outro (PTAX:
  ``'MM-DD-AAAA'``; Pix: ``AAAAMM`` "a partir do mês"; Saldos: fim de mês). Testar formatos até um trazer dados
  **não** é confiável (o Pix aceita ``'09/2026'`` e devolve 2023): os parâmetros vêm de ``odata_params.json``,
  conferidos um a um; consulta com parâmetro fora dela fica como "parâmetros não conferidos", com a prévia
  obrigatória;
- o OData recusa o espaço como "+": o cliente do catálogo manda ``%20``.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qsl, unquote, urlsplit

import polars as pl

from prodata.catalog.http import CatalogClient, CatalogError
from prodata.catalog.model import ReadResult, SourceNotFoundError, safe_xml

BASE = "https://olinda.bcb.gov.br/olinda/servico"
_NS = "{http://docs.oasis-open.org/odata/ns/edm}"
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,80}$")
_VERSION = re.compile(r"^v\d{1,2}$")
_RESOURCE_URL = re.compile(
    r"^https://olinda\.bcb\.gov\.br/olinda/servico/([^/]+)/versao/(v\d+)/odata/?([^/?(]*)"
)
# Página grande: vários serviços não aceitam $skip, então a primeira página precisa trazer o máximo possível.
PAGE = 50_000
MAX_PAGES = 60

ParamKind = Literal["texto", "inteiro", "data"]
Role = Literal["inicio", "fim", "dia", "mes", "a_partir_do_mes", "a_partir_de"]
# Formatos de data encontrados nos serviços do Banco Central.
DATE_FORMATS: dict[str, str] = {
    "MM-DD-AAAA": "%m-%d-%Y",
    "AAAA-MM-DD": "%Y-%m-%d",
    "AAAAMM": "%Y%m",
    "AAAA-MM": "%Y-%m",
    "DD/MM/AAAA": "%d/%m/%Y",
    "AAAAMMDD": "%Y%m%d",
}
PARAMS_FILE = Path(__file__).with_name("odata_params.json")
_EDM = {
    "Edm.String": pl.String,
    "Edm.Decimal": pl.Float64,
    "Edm.Double": pl.Float64,
    "Edm.Single": pl.Float64,
    "Edm.Int16": pl.Int64,
    "Edm.Int32": pl.Int64,
    "Edm.Int64": pl.Int64,
    "Edm.Byte": pl.Int64,
    "Edm.Boolean": pl.Boolean,
    "Edm.Date": pl.Date,
    "Edm.DateTimeOffset": pl.Datetime,
}


@dataclass(frozen=True)
class Param:
    nome: str
    tipo: ParamKind
    descricao: str = ""
    # Inteiro vai sem aspas na consulta; texto e data vão entre aspas simples.
    inteiro: bool = False
    # Só nos conferidos (odata_params.json):
    conferido: bool = False
    formato: str | None = None
    papel: Role | None = None
    ajuste: str | None = None
    opcoes: str | None = None  # "Consulta.coluna" do mesmo serviço com os valores possíveis
    exemplo: str = ""


@dataclass(frozen=True)
class Entry:
    """Uma consulta do serviço: tabela sem parâmetro ou função com parâmetros."""

    nome: str
    titulo: str
    descricao: str = ""
    parametros: tuple[Param, ...] = ()
    colunas: tuple[tuple[str, str], ...] = ()  # (nome, tipo Edm)

    @property
    def conferida(self) -> bool:
        """Sem parâmetro, ou com todos os parâmetros conferidos: entra sem a pessoa digitar formato nenhum."""
        return all(p.conferido for p in self.parametros)


@dataclass
class Service:
    servico: str
    versao: str
    titulo: str = ""
    descricao: str = ""
    entradas: list[Entry] = field(default_factory=list)

    @property
    def url(self) -> str:
        return f"{BASE}/{self.servico}/versao/{self.versao}"

    def entry(self, name: str) -> Entry:
        for e in self.entradas:
            if e.nome == name:
                return e
        raise SourceNotFoundError(
            f"A consulta {name!r} não existe no serviço {self.servico} do Banco Central."
        )


def _check_names(servico: str, versao: str) -> None:
    if not _NAME.match(servico) or not _VERSION.match(versao):
        raise SourceNotFoundError(f"{servico}/{versao} não é um serviço OData do Banco Central.")


def parse_resource_url(url: str) -> tuple[str, str, str, dict[str, str]] | None:
    """Endereço de um recurso do portal → (serviço, versão, consulta, $filter/$select já prontos)."""
    match = _RESOURCE_URL.match(url)
    if not match:
        return None
    query = {k: v for k, v in parse_qsl(urlsplit(url).query) if k in ("$filter", "$select", "$orderby")}
    return match.group(1), match.group(2), unquote(match.group(3)), query


def _kind(name: str, description: str, swagger_type: str) -> ParamKind:
    if swagger_type == "integer":
        return "inteiro"
    text = f"{name} {description}".lower()
    return "data" if "data" in text or "date" in text else "texto"


def describe(client: CatalogClient, servico: str, versao: str) -> Service:
    """Tabelas, funções, parâmetros e colunas do serviço, pelo ``$metadata`` e pelo ``/swagger``."""
    _check_names(servico, versao)
    service = Service(servico, versao)
    meta = client.get(f"{service.url}/odata/$metadata", max_bytes=4 * 1024 * 1024)
    try:
        root = safe_xml(meta.body)
    except ET.ParseError, ValueError:
        raise CatalogError(
            f"O serviço {servico} do Banco Central devolveu uma descrição inválida.", "resposta"
        ) from None

    types: dict[str, tuple[tuple[str, str], ...]] = {}
    for et in root.iter(f"{_NS}EntityType"):
        types[et.get("Name", "")] = tuple(
            (p.get("Name", ""), p.get("Type", "")) for p in et.findall(f"{_NS}Property")
        )
    functions: dict[str, tuple[list[tuple[str, str]], str]] = {}
    for fn in root.iter(f"{_NS}Function"):
        ret = fn.find(f"{_NS}ReturnType")
        rtype = (ret.get("Type", "") if ret is not None else "").removeprefix("Collection(").removesuffix(")")
        params = [(p.get("Name", ""), p.get("Type", "")) for p in fn.findall(f"{_NS}Parameter")]
        functions[fn.get("Name", "")] = (params, rtype.rsplit(".", 1)[-1])

    swagger = _swagger(client, service)
    service.titulo = swagger.get("titulo", "")
    service.descricao = swagger.get("descricao", "")
    ops: dict[str, dict[str, Any]] = swagger.get("ops", {})

    for es in root.iter(f"{_NS}EntitySet"):
        name = es.get("Name", "")
        if name.startswith("_"):
            continue  # suporte de função
        op = ops.get(name, {})
        etype = es.get("EntityType", "").rsplit(".", 1)[-1]
        service.entradas.append(
            Entry(name, op.get("titulo") or name, op.get("descricao", ""), (), types.get(etype, ()))
        )
    for fi in root.iter(f"{_NS}FunctionImport"):
        name = fi.get("Name", "")
        params, rtype = functions.get(fi.get("Function", "").rsplit(".", 1)[-1] or name, ([], ""))
        op = ops.get(name, {})
        described = op.get("parametros", {})
        checked = verified_params().get(f"{servico}/{name}", {})
        built = tuple(
            _param(p_name, p_type, described.get(p_name, {}), checked.get(p_name))
            for p_name, p_type in params
        )
        service.entradas.append(
            Entry(name, op.get("titulo") or name, op.get("descricao", ""), built, types.get(rtype, ()))
        )
    if not service.entradas:
        raise SourceNotFoundError(f"O serviço {servico} do Banco Central não tem consultas publicadas.")
    return service


@cache
def verified_params() -> dict[str, dict[str, dict[str, Any]]]:
    data: dict[str, Any] = json.loads(PARAMS_FILE.read_text(encoding="utf-8"))
    return data["consultas"]


def _param(name: str, edm: str, described: dict[str, Any], checked: dict[str, Any] | None) -> Param:
    swagger_type = described.get("tipo", "")
    description = described.get("descricao", "")
    inteiro = edm.startswith("Edm.Int") or swagger_type == "integer"
    if checked is None:
        return Param(name, _kind(name, description, swagger_type), description, inteiro)
    kind: ParamKind = "data" if checked.get("formato") else ("inteiro" if inteiro else "texto")
    return Param(
        name, kind, description, inteiro, conferido=True, formato=checked.get("formato"), papel=checked.get("papel"),
        ajuste=checked.get("ajuste"), opcoes=checked.get("opcoes"), exemplo=checked.get("exemplo", ""),
    )  # fmt: skip


def _swagger(client: CatalogClient, service: Service) -> dict[str, Any]:
    """Títulos e descrições do ``/swagger``; se o serviço não tiver, a descrição fica só com o ``$metadata``."""
    try:
        doc = client.get(f"{service.url}/swagger", max_bytes=4 * 1024 * 1024, retries=0).json()
    except CatalogError:
        return {}
    info = doc.get("info", {}) if isinstance(doc, dict) else {}
    ops: dict[str, dict[str, Any]] = {}
    for path, methods in (doc.get("paths") or {}).items():
        op = (methods or {}).get("get") or {}
        name = path.lstrip("/").split("(", 1)[0]
        params = {
            str(p.get("name", "")).lstrip("@"): {
                "descricao": p.get("description") or "",
                "tipo": p.get("type") or "",
            }
            for p in op.get("parameters", [])
            if str(p.get("name", "")).startswith("@")
        }
        ops[name] = {
            "titulo": op.get("summary") or "",
            "descricao": op.get("description") or "",
            "parametros": params,
        }
    return {"titulo": info.get("title", ""), "descricao": info.get("description", ""), "ops": ops}


# ------------------------------------------------------------------ leitura


def format_date(day: date, fmt: str) -> str:
    if fmt not in DATE_FORMATS:
        raise SourceNotFoundError(f"Formato de data {fmt!r} desconhecido.")
    return day.strftime(DATE_FORMATS[fmt])


def _month_end(day: date) -> date:
    following = date(day.year + (day.month == 12), day.month % 12 + 1, 1)
    return following - timedelta(days=1)


def param_values(entry: Entry, start: date, end: date, typed: dict[str, str] | None = None) -> dict[str, str]:
    """Os valores dos parâmetros: as datas conferidas saem do período escolhido, pelo papel de cada uma; o resto
    vem do que a pessoa digitou ou escolheu (``typed``). Parâmetro não conferido vai como a pessoa digitou."""
    typed = typed or {}
    out: dict[str, str] = {}
    for p in entry.parametros:
        if p.conferido and p.formato:
            day = start if p.papel in ("inicio", "a_partir_do_mes", "a_partir_de") else end
            if p.ajuste == "fim_do_mes":
                day = _month_end(day)
            out[p.nome] = format_date(day, p.formato)
        else:
            out[p.nome] = str(typed.get(p.nome, p.exemplo)).strip()
    return out


def _literal(param: Param, value: str) -> str:
    if param.inteiro:
        if not re.fullmatch(r"-?\d{1,12}", value.strip()):
            raise SourceNotFoundError(f"O parâmetro {param.nome} é um número inteiro; {value!r} não é.")
        return value.strip()
    return "'" + value.replace("'", "''") + "'"


def _url_and_params(service: Service, entry: Entry, values: dict[str, str]) -> tuple[str, dict[str, str]]:
    query: dict[str, str] = {}
    if not entry.parametros:
        return f"{service.url}/odata/{entry.nome}", query
    missing = [p.nome for p in entry.parametros if not str(values.get(p.nome, "")).strip()]
    if missing:
        raise SourceNotFoundError(f"Faltam os parâmetros: {', '.join(missing)}.")
    signature = ",".join(f"{p.nome}=@{p.nome}" for p in entry.parametros)
    for p in entry.parametros:
        query[f"@{p.nome}"] = _literal(p, str(values[p.nome]))
    return f"{service.url}/odata/{entry.nome}({signature})", query


def read(
    client: CatalogClient,
    service: Service,
    entry_name: str,
    values: dict[str, str] | None = None,
    *,
    extra: dict[str, str] | None = None,
    limit: int | None = None,
) -> ReadResult:
    """Lê a consulta inteira, página a página (``$top``/``$skip``), com os tipos das colunas do ``$metadata``."""
    entry = service.entry(entry_name)
    url, query = _url_and_params(service, entry, values or {})
    allowed_extra = {k: v for k, v in (extra or {}).items() if k in ("$filter", "$select", "$orderby")}
    rows: list[dict[str, Any]] = []
    urls: list[str] = []
    page = min(PAGE, limit) if limit else PAGE
    for n in range(MAX_PAGES):
        params: dict[str, Any] = {**query, **allowed_extra, "$format": "json", "$top": page}
        if n:
            # Só a partir da segunda página: alguns serviços (Saldos do BCB) recusam $skip, até com zero.
            params["$skip"] = n * page
        try:
            answer = client.get(url, params=params, timeout=120)
        except CatalogError as exc:
            if n and exc.kind == "http":
                raise CatalogError(
                    f"Esta consulta do Banco Central não divide o resultado em partes e passou de {n * page:,} linhas. "
                    "Escolha um período menor.".replace(",", "."),
                    "limite",
                ) from None
            raise
        urls.append(answer.url)
        chunk = answer.json().get("value", [])
        rows.extend(chunk)
        if len(chunk) < page or (limit and len(rows) >= limit):
            break
    else:
        raise CatalogError(
            f"A consulta passou de {MAX_PAGES * PAGE:,} linhas. Use parâmetros ou um filtro para trazer menos.".replace(
                ",", "."
            ),
            "limite",
        )
    if limit:
        rows = rows[:limit]
    return ReadResult(_frame(rows, entry), urls, info={"servico": service.servico, "consulta": entry.titulo})


def _frame(rows: list[dict[str, Any]], entry: Entry) -> pl.DataFrame:
    declared = dict(entry.colunas)
    names = list(declared) or (list(rows[0]) if rows else [])
    for row in rows[:1]:
        names += [k for k in row if k not in names and not k.startswith("@")]
    cols: dict[str, list[Any]] = {n: [r.get(n) for r in rows] for n in names}
    frame = pl.DataFrame(cols, schema=dict.fromkeys(names, pl.String) if not rows else None, strict=False)
    casts = []
    for name in names:
        target = _EDM.get(declared.get(name, ""))
        if target is None or name not in frame.columns:
            continue
        col = pl.col(name)
        if target == pl.Date:
            casts.append(col.cast(pl.String).str.slice(0, 10).str.strptime(pl.Date, "%Y-%m-%d", strict=False))
        elif target == pl.Datetime:
            casts.append(col.cast(pl.String).str.slice(0, 19).str.replace("T", " ")
                         .str.strptime(pl.Datetime, "%Y-%m-%d %H:%M:%S", strict=False))  # fmt: skip
        else:
            casts.append(col.cast(target, strict=False))
    return frame.with_columns(casts) if casts else frame
