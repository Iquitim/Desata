"""Lugares do catálogo: estados, capitais e todos os municípios do IBGE (spec 049, RF-4958, RF-4965, RF-4966).

A busca e o painel de um lugar funcionam sem internet: a lista de municípios vai no programa
(``municipios_ibge.json``, gerada por ``scripts/gerar_mapa_brasil.py``). O painel diz o que há no lugar — o portal
do estado e o da capital, com a situação conferida, as prefeituras com portal próprio e as fontes federais já
filtradas pelo lugar — e nada é lido até a pessoa escolher uma fonte.
"""

from __future__ import annotations

import json
import unicodedata
from functools import cache
from pathlib import Path
from typing import Any

from prodata.catalog import holidays, portals

DATA = Path(__file__).with_name("municipios_ibge.json")


def _norm(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(plain.lower().replace("'", "").replace("-", " ").split())


@cache
def municipalities() -> tuple[tuple[str, str, str], ...]:
    """(código do IBGE, nome, UF) de cada município."""
    rows = json.loads(DATA.read_text(encoding="utf-8"))["municipios"]
    return tuple((str(c), str(n), str(uf)) for c, n, uf in rows)


@cache
def _index() -> tuple[tuple[str, str, str, str], ...]:
    return tuple((_norm(n), c, n, uf) for c, n, uf in municipalities())


def _by_ibge() -> dict[str, portals.Place]:
    return {pl.ibge: pl for pl in (*portals.PLACES, *portals.MAP_CITIES)}


STATES: dict[str, portals.Place] = {pl.uf: pl for pl in portals.PLACES if pl.esfera == "estadual"}


def _row(place_id: str, nome: str, uf: str, esfera: str) -> dict[str, Any]:
    known = _by_ibge().get(place_id.split(":")[1])
    row: dict[str, Any] = {"id": place_id, "nome": nome, "uf": uf, "esfera": esfera, "capital": False,
                           "situacao": "", "portal": "", "motivo": ""}  # fmt: skip
    if known is not None:
        row.update(capital=known.capital, situacao=known.situacao, portal=known.portal, motivo=known.motivo)
    if esfera == "estadual":
        row["resumo"] = "portal do estado e dados federais"
    elif known is not None and known.situacao == "le_direto":
        row["resumo"] = "portal da prefeitura e dados federais"
    else:
        row["resumo"] = "dados do município"
    return row


def search(query: str, limit: int = 12) -> list[dict[str, Any]]:
    """Estados e municípios cujo nome tem o que foi digitado (sem acento nem maiúsculas); o nome exato primeiro."""
    q = _norm(query)
    if len(q) < 3:
        return []
    found: list[tuple[int, dict[str, Any]]] = []
    for uf, pl in STATES.items():
        name = _norm(pl.nome)
        if q in name or q == uf.lower():
            found.append(
                (0 if name == q or q == uf.lower() else 2, _row(f"est:{pl.ibge}", pl.nome, uf, "estadual"))
            )
    for name, code, nome, uf in _index():
        if q in name:
            rank = 0 if name == q else 1 if name.startswith(q) else 3
            found.append((rank, _row(f"mun:{code}", nome, uf, "municipal")))
    found.sort(key=lambda r: (r[0], r[1]["nome"], r[1]["uf"]))
    return [row for _, row in found[:limit]]


def _sources(code: str, uf: str, level: str) -> list[dict[str, Any]]:
    """As fontes federais já filtradas pelo lugar: o mesmo detalhe e as mesmas escolhas da caixa."""
    local = uf if level == "N3" else code
    # A base traz os feriados municipais só das capitais (RF-4967): avisa antes de adicionar.
    local_note = ("A base do programa traz os feriados municipais só das capitais: inclua os desta cidade em "
                  "Editar feriados.") if holidays.outside_base(local) else ""  # fmt: skip
    rows = [
        {
            "id": "ibge.agregado/6579",
            "nome": "População estimada",
            "escolhas": {"nivel": level, "localidades": code},
        },
        {"id": "ibge.agregado/5938", "nome": "PIB", "escolhas": {"nivel": level, "localidades": code}},
    ]
    if level == "N3":
        rows.append({"id": "ibge.agregado/4099", "nome": "Taxa de desocupação",
                     "escolhas": {"nivel": "N3", "localidades": code}})  # fmt: skip
    rows += [
        {"id": "siconfi/relatorios", "nome": "Receitas e despesas (Siconfi)", "escolhas": {"ente": code}},
        {"id": "calendario/feriados", "nome": "Feriados", "escolhas": {"local": local}, "nota": local_note},
        {"id": "calendario/dias-uteis", "nome": "Dias úteis", "escolhas": {"local": local}, "nota": local_note},
        {"id": "receita.cnpj/dados-abertos", "nome": "Empresas (CNPJ)", "escolhas": {},
         "nota": "Baixe o CNPJ e filtre pela " + ("UF" if level == "N3" else "cidade") + " na leitura."},
    ]  # fmt: skip
    return rows


def _portal_row(pl: portals.Place) -> dict[str, Any]:
    return {"id": pl.id, "nome": pl.nome, "situacao": pl.situacao, "portal": pl.portal, "pagina": pl.pagina,
            "motivo": pl.motivo, "conferido": portals.CHECKED}  # fmt: skip


def detail(place_id: str) -> dict[str, Any]:
    """O painel de um estado ("est:31") ou município ("mun:3136702")."""
    kind, _, code = place_id.partition(":")
    if kind == "est":
        state = next((pl for pl in STATES.values() if pl.ibge == code), None)
        if state is None:
            raise KeyError(place_id)
        capital = next(pl for pl in portals.PLACES if pl.capital and pl.uf == state.uf)
        others = [_portal_row(pl) for pl in portals.MAP_CITIES if pl.uf == state.uf]
        return {"id": place_id, "nome": state.nome, "uf": state.uf, "esfera": "estadual",
                "portal_estado": _portal_row(state), "capital": _portal_row(capital), "prefeituras": others,
                "fontes": _sources(code, state.uf, "N3")}  # fmt: skip
    if kind == "mun":
        city = next((c for c in municipalities() if c[0] == code), None)
        if city is None:
            raise KeyError(place_id)
        known = _by_ibge().get(code)
        return {"id": place_id, "nome": city[1], "uf": city[2], "esfera": "municipal",
                "estado": STATES[city[2]].nome, "portal": _portal_row(known) if known else None,
                "fontes": _sources(code, city[2], "N6")}  # fmt: skip
    raise KeyError(place_id)


def municipalities_of(uf: str) -> list[dict[str, Any]]:
    """Demais municípios de uma UF (sem a capital): os que têm portal próprio primeiro, depois em ordem alfabética."""
    with_portal = {pl.ibge for pl in portals.MAP_CITIES}
    capital = next(pl.ibge for pl in portals.PLACES if pl.capital and pl.uf == uf)
    rows = [(c in with_portal, _norm(n), {"id": f"mun:{c}", "nome": n, "portal": c in with_portal})
            for c, n, u in municipalities() if u == uf and c != capital]  # fmt: skip
    rows.sort(key=lambda r: (not r[0], r[1]))
    return [r[2] for r in rows]
