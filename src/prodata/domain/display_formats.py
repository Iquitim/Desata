"""Formato de exibição da coluna (spec 050): moeda, número, porcentagem, documento e data.

O formato muda só a aparência: o dado, o tipo e o CSV ficam como estão. Fica no fluxo por caixa e por coluna e vale
nas caixas seguintes enquanto a coluna mantém o nome (RF-5011). A mesma regra de herança existe em
``web/js/col_format.js``; os dois lados usam os casos de ``tests/fixtures/formatos_heranca.json``.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

FormatKind = Literal["none", "number", "currency", "percent", "document", "date"]
DOCUMENT_MASKS = {
    "cpf": "###.###.###-##",
    "cnpj": "##.###.###/####-##",
    "cep": "#####-###",
}
# Vão para a tela, o HTML exportado e o formato do Excel: nada que abra marcação ou feche aspas.
_UNSAFE = re.compile(r"[<>\"'\\\x00-\x1f]")


class DisplayFormat(BaseModel):
    """Uma escolha de formato. Só escolhas, nunca valores da coluna (RF-5052)."""

    model_config = ConfigDict(extra="ignore")

    kind: FormatKind = "none"
    decimals: int = Field(2, ge=0, le=6)
    thousands: bool = True
    symbol: str = Field("R$", max_length=6)
    base: Literal["fraction", "hundred"] = "fraction"
    mask: str = Field("cpf", max_length=40)
    pattern: Literal["dmy", "my", "dmy_hm", "long", "iso"] = "dmy"

    @field_validator("symbol")
    @classmethod
    def _symbol(cls, value: str) -> str:
        value = value.strip()
        if _UNSAFE.search(value):
            raise ValueError("Símbolo da moeda com caractere não permitido.")
        return value

    @field_validator("mask")
    @classmethod
    def _mask(cls, value: str) -> str:
        if value in DOCUMENT_MASKS or value == "phone":
            return value
        if _UNSAFE.search(value):
            raise ValueError("Máscara com caractere não permitido.")
        if "#" not in value:
            raise ValueError("A máscara precisa de pelo menos um # (um dígito).")
        return value

    def compact(self) -> dict[str, Any]:
        """Só os campos que valem para o tipo: o arquivo do fluxo não guarda escolhas que não se aplicam."""
        keep = {
            "number": ("decimals", "thousands"),
            "currency": ("decimals", "symbol"),
            "percent": ("decimals", "base"),
            "document": ("mask",),
            "date": ("pattern",),
        }.get(self.kind, ())
        return {"kind": self.kind, **{k: getattr(self, k) for k in keep}}


ColumnFormats = dict[str, dict[str, DisplayFormat]]


class _Edge(Protocol):
    source: str
    target: str
    target_handle: str


class _Node(Protocol):
    id: str
    type: str


def _port_rank(order: Sequence[str], handle: str) -> tuple[int, str]:
    return (order.index(handle), "") if handle in order else (len(order), handle)


def effective_formats(
    formats: ColumnFormats,
    nodes: Iterable[_Node],
    edges: Iterable[_Edge],
    node_id: str,
    ports: Callable[[str], Sequence[str]] = lambda _type: (),
) -> dict[str, DisplayFormat]:
    """Formatos que valem na caixa: os dela e, por coluna que ela não definiu, os das entradas, na ordem das portas
    da ferramenta (a primeira entrada ganha, RF-5012). ``none`` bloqueia o que viria de antes e não aparece."""
    types = {n.id: n.type for n in nodes}
    incoming: dict[str, list[_Edge]] = {}
    for e in edges:
        incoming.setdefault(e.target, []).append(e)
    memo: dict[str, dict[str, DisplayFormat]] = {}

    def walk(nid: str, seen: frozenset[str]) -> dict[str, DisplayFormat]:
        if nid in memo:
            return memo[nid]
        out: dict[str, DisplayFormat] = {}
        order = ports(types.get(nid, ""))
        for e in sorted(incoming.get(nid, []), key=lambda e: _port_rank(order, e.target_handle)):
            if e.source in seen:  # um fluxo com laço não chega aqui, mas a herança nunca entra em ciclo
                continue
            for col, spec in walk(e.source, seen | {nid}).items():
                out.setdefault(col, spec)
        own = formats.get(nid, {})
        out.update(own)
        memo[nid] = out
        return out

    found = walk(node_id, frozenset())
    return {col: spec for col, spec in found.items() if spec.kind != "none"}
