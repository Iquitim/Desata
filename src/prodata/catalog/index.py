"""Catálogo guardado e busca (spec 049, RF-4904, RF-4932..4934).

- Os catálogos completos dos órgãos (séries do SGS no portal do BCB, tabelas do IBGE, séries do Ipeadata) ficam na
  pasta de dados deste computador, um arquivo por órgão, com a data da leitura: ``catalogo/indice/<orgao>.json.gz``.
- **Atualizar** lê cada órgão direto da fonte; o que falha mantém o catálogo anterior desse órgão, com a data e o
  motivo, e os outros seguem (RF-4933). Sem internet, a busca usa o que está guardado (RF-4934).
- A busca não diferencia acento nem maiúsculas, procura no nome, órgão, resumo, palavras e código, e põe os
  destaques primeiro (RF-4931). Um número que não está em catálogo nenhum vira "ler direto" do SGS.
"""

from __future__ import annotations

import gzip
import json
import os
import re
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from prodata.catalog import curated, hosts, portals
from prodata.catalog.http import CatalogClient, CatalogError
from prodata.catalog.readers import bcb_sgs, ckan, ibge, ipea

STALE_AFTER = timedelta(days=7)
MAX_RESULTS = 100


@dataclass(frozen=True)
class Agency:
    id: str
    nome: str
    servico: str
    # Devolve as entradas, ou as entradas e avisos ("2 conjuntos não puderam ser lidos").
    read: Callable[[CatalogClient], list[dict[str, Any]] | tuple[list[dict[str, Any]], list[str]]]


def _bcb(client: CatalogClient) -> list[dict[str, Any]]:
    return [
        {
            "id": f"bcb.sgs/{e['codigo']}",
            "codigo": e["codigo"],
            "nome": e["nome"],
            "resumo": e["descricao"][:240],
            "periodicidade": e["periodicidade"].lower(),
            "unidade": e["unidade"],
            "inicio": e["inicio"],
            "fim": e["fim"],
            "atualizado": e["atualizado"],
            "grupo": e["area"],
        }
        for e in bcb_sgs.catalog(client)
    ]


def _ibge(client: CatalogClient) -> list[dict[str, Any]]:
    return [
        {
            "id": f"ibge.agregado/{e['codigo']}",
            "codigo": e["codigo"],
            "nome": e["nome"],
            "grupo": e["pesquisa"],
        }
        for e in ibge.catalog(client)
    ]


def _ipea(client: CatalogClient) -> list[dict[str, Any]]:
    return [
        {
            "id": f"ipea/{e['codigo']}",
            "codigo": e["codigo"],
            "nome": e["nome"],
            "resumo": e["descricao"][:240],
            "periodicidade": e["periodicidade"].lower(),
            "unidade": " ".join(p for p in (e["multiplicador"], e["unidade"]) if p),
            "atualizado": e["atualizado"],
            "grupo": e["fonte_sigla"] or e["base"],
            "ativa": e["ativa"],
        }
        for e in ipea.catalog(client)
        if e["numerica"]
    ]


def _portal_reader(portal_id: str) -> Callable[[CatalogClient], tuple[list[dict[str, Any]], list[str]]]:
    return lambda client: ckan.catalog_with_warnings(client, portal_id)


AGENCIES: tuple[Agency, ...] = (
    Agency("bcb", "Banco Central do Brasil", "bcb_dados", _bcb),
    Agency("ibge", "IBGE", "ibge", _ibge),
    Agency("ipea", "Ipeadata", "ipea", _ipea),
    # Portais de dados abertos (RF-4936): cada um é um "órgão" do catálogo guardado, com o próprio arquivo.
    *(Agency(p.id, p.nome, hosts.PORTAL_SERVICE[p.id], _portal_reader(p.id)) for p in portals.PORTALS),
)
AGENCY_BY_ID = {a.id: a for a in AGENCIES}
# Órgão de cada serviço, para o filtro "por órgão" da busca.
AGENCY_OF_SERVICE = {
    "bcb_sgs": "bcb", "bcb_dados": "bcb", "bcb_olinda": "bcb", "ibge": "ibge", "ipea": "ipea", "tesouro": "tesouro",
    "siconfi": "tesouro", "comex": "comex", "receita": "receita", "anbima": "calendario",
}  # fmt: skip


def normalize(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", plain.lower()).strip()


@dataclass
class AgencyState:
    lido_em: datetime | None = None
    quantidade: int = 0
    erro: str = ""
    erro_em: datetime | None = None
    aviso: str = ""


@dataclass
class RefreshReport:
    por_orgao: dict[str, AgencyState] = field(default_factory=dict)

    @property
    def falhas(self) -> list[str]:
        return [k for k, v in self.por_orgao.items() if v.erro]


class CatalogStore:
    """O catálogo guardado num diretório (``<pasta de dados>/catalogo``)."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._cache: dict[str, list[dict[str, Any]]] = {}

    def _file(self, agency: str) -> Path:
        return self.root / "indice" / f"{agency}.json.gz"

    def _state_file(self) -> Path:
        return self.root / "indice" / "estado.json"

    # ---------------------------------------------------------------- leitura

    def entries(self, agency: str) -> list[dict[str, Any]]:
        if agency not in self._cache:
            path = self._file(agency)
            if not path.exists():
                return []
            try:
                data = json.loads(gzip.decompress(path.read_bytes()))
            except OSError, ValueError:
                return []  # arquivo estragado: como se não houvesse; a próxima atualização refaz
            self._cache[agency] = list(data.get("entradas", []))
        return self._cache[agency]

    def state(self) -> dict[str, AgencyState]:
        try:
            raw = json.loads(self._state_file().read_text(encoding="utf-8"))
        except OSError, ValueError:
            raw = {}
        out: dict[str, AgencyState] = {}
        for agency in AGENCY_BY_ID:
            item = raw.get(agency, {})
            out[agency] = AgencyState(
                lido_em=_when(item.get("lido_em")),
                quantidade=int(item.get("quantidade", 0)),
                erro=str(item.get("erro", "")),
                erro_em=_when(item.get("erro_em")),
                aviso=str(item.get("aviso", "")),
            )
        return out

    def stale(self, now: datetime | None = None) -> bool:
        """Atualiza sozinho quando algum órgão nunca foi lido ou a leitura tem mais de 7 dias (RF-4933)."""
        moment = now or datetime.now()
        return any(s.lido_em is None or moment - s.lido_em > STALE_AFTER for s in self.state().values())

    # ---------------------------------------------------------------- atualização

    def _write_atomic(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)

    def _save_state(self, states: dict[str, AgencyState]) -> None:
        raw = {
            k: {
                "lido_em": v.lido_em.isoformat() if v.lido_em else None,
                "quantidade": v.quantidade,
                "erro": v.erro,
                "erro_em": v.erro_em.isoformat() if v.erro_em else None,
                "aviso": v.aviso,
            }
            for k, v in states.items()
        }
        self._write_atomic(self._state_file(), json.dumps(raw, ensure_ascii=False, indent=1).encode("utf-8"))

    def refresh(
        self,
        client: CatalogClient,
        agencies: Iterable[str] | None = None,
        *,
        progress: Callable[[str, str], None] | None = None,
        now: Callable[[], datetime] = datetime.now,
    ) -> RefreshReport:
        """Lê de novo o catálogo de cada órgão. Um que falha mantém o anterior (com o motivo); os outros seguem."""
        states = self.state()
        report = RefreshReport()
        for agency_id in agencies or AGENCY_BY_ID:
            agency = AGENCY_BY_ID[agency_id]
            if progress:
                progress(agency_id, "lendo")
            try:
                got = agency.read(client)
                rows, notes = got if isinstance(got, tuple) else (got, [])
                if not rows:
                    raise CatalogError(f"O catálogo do {agency.nome} veio vazio.", "resposta")
            except CatalogError as exc:
                states[agency_id].erro, states[agency_id].erro_em = exc.message, now()
            else:
                payload = {"orgao": agency_id, "lido_em": now().isoformat(), "entradas": rows}
                self._write_atomic(
                    self._file(agency_id), gzip.compress(json.dumps(payload, ensure_ascii=False).encode())
                )
                self._cache[agency_id] = rows
                states[agency_id] = AgencyState(lido_em=now(), quantidade=len(rows), aviso=" ".join(notes))
            report.por_orgao[agency_id] = states[agency_id]
            if progress:
                progress(agency_id, "erro" if states[agency_id].erro else f"{states[agency_id].quantidade}")
        self._save_state(states)
        return report

    # ---------------------------------------------------------------- busca

    def search(
        self,
        query: str,
        *,
        agency: str | None = None,
        periodicity: str | None = None,
        category: str | None = None,
        limit: int = MAX_RESULTS,
    ) -> list[dict[str, Any]]:
        terms = normalize(query).split()
        results: list[tuple[tuple[int, int, str], dict[str, Any]]] = []
        seen: set[str] = set()

        for source in curated.SOURCES:
            seen.add(source.id)
            entry = _curated_entry(source)
            if category and source.categoria != category:
                continue
            if not _filters(entry, agency, periodicity):
                continue
            rank = _rank(entry, terms, " ".join(source.palavras))
            if rank is not None:
                results.append(((0, rank, normalize(source.nome)), entry))

        if not category or category == "series":
            for agency_id in [agency] if agency else AGENCY_BY_ID:
                if category == "series" and agency_id != "ipea":
                    continue
                for raw in self.entries(agency_id):
                    if raw["id"] in seen:
                        continue
                    entry = {**raw, "orgao": agency_id, "destaque": False}
                    if not _filters(entry, None, periodicity):
                        continue
                    extra = " ".join(
                        [entry.get("grupo", ""), *entry.get("grupos", []), *entry.get("temas", [])]
                    )
                    rank = _rank(entry, terms, extra)
                    if rank is not None:
                        results.append(((1, rank, normalize(entry["nome"])), entry))
                        seen.add(raw["id"])

        code = query.strip()
        if code.isdigit() and len(code) <= 6 and f"bcb.sgs/{code}" not in seen and agency in (None, "bcb"):
            results.append(((2, 0, code), _direct_sgs(code)))

        results.sort(key=lambda item: item[0])
        return [entry for _, entry in results[:limit]]


def _when(text: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(text) if text else None
    except ValueError:
        return None


def _curated_entry(source: curated.Source) -> dict[str, Any]:
    agency = AGENCY_OF_SERVICE.get(source.servico, source.servico)
    return {
        "id": source.id,
        "codigo": source.codigo,
        "nome": source.nome,
        "resumo": source.resumo,
        "categoria": source.categoria,
        "periodicidade": source.periodicidade,
        "unidade": source.unidade,
        "servico": source.servico,
        "orgao": agency,
        "destaque": True,
    }


def _direct_sgs(code: str) -> dict[str, Any]:
    return {
        "id": f"bcb.sgs/{code}",
        "codigo": code,
        "nome": f"Série {code} do SGS do Banco Central",
        "resumo": "Não está no catálogo do portal do Banco Central: o programa lê direto pelo código e confere ao abrir.",
        "orgao": "bcb",
        "servico": "bcb_sgs",
        "destaque": False,
        "direto": True,
    }


def _filters(entry: dict[str, Any], agency: str | None, periodicity: str | None) -> bool:
    if agency and entry.get("orgao") != agency:
        return False
    return not (periodicity and normalize(periodicity) not in normalize(str(entry.get("periodicidade", ""))))


def _rank(entry: dict[str, Any], terms: list[str], extra: str) -> int | None:
    """None quando não casa; senão, menor é melhor: código exato, nome que começa pelo termo, nome, o resto."""
    if not terms:
        return 3
    name = normalize(entry.get("nome", ""))
    code = normalize(str(entry.get("codigo", "")))
    haystack = " ".join(
        [
            name,
            code,
            normalize(entry.get("resumo", "")),
            normalize(extra),
            normalize(str(entry.get("orgao", ""))),
        ]
    )
    if not all(term in haystack for term in terms):
        return None
    joined = " ".join(terms)
    if code == joined:
        return 0
    if name.startswith(joined):
        return 1
    if all(term in name for term in terms):
        return 2
    return 3
