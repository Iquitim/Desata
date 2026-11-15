"""Peças do Regex (spec 039): o trecho descrito em linguagem simples vira a expressão regular.

A tabela ``PIECES`` é a única fonte: o motor e o SQL usam ``pattern_of`` aqui, e a tela recebe a mesma tabela pelo
catálogo e monta o padrão do mesmo jeito (``regex_builder.js``), para a prévia bater com a execução. Os trechos usam só
o que o Polars (Rust), o DuckDB (RE2) e o navegador entendem igual.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

PieceKind = Literal[
    "digits",
    "word",
    "alnum",
    "space",
    "literal",
    "any",
    "start",
    "end",
    "date",
    "cpf",
    "cnpj",
    "cep",
    "email",
    "phone",
    "decimal",
]

# base: o trecho de uma unidade; repeat: aceita quantidade (N exatos ou "quantos houver"); ready: peça pronta (cartão)
PIECES: dict[str, dict[str, Any]] = {
    "digits": {
        "label": "Número",
        "base": r"\d",
        "repeat": True,
        "unit": ("dígito", "dígitos"),
        "icon": "hash",
    },
    "word": {
        "label": "Palavra",
        "base": "[A-Za-zÀ-ÿ]",
        "repeat": True,
        "unit": ("letra", "letras"),
        "icon": "edit",
    },
    "alnum": {
        "label": "Letras e números",
        "base": "[A-Za-zÀ-ÿ0-9]",
        "repeat": True,
        "unit": ("letra ou número", "letras ou números"),
        "icon": "fingerprint",
    },
    "space": {
        "label": "Espaço",
        "base": r"\s",
        "repeat": True,
        "unit": ("espaço", "espaços"),
        "icon": "columns",
    },
    "literal": {"label": "Texto fixo", "base": "", "icon": "edit"},
    "any": {"label": "Qualquer coisa", "base": ".*?", "icon": "more", "say": "qualquer coisa"},
    "start": {"label": "Início do texto", "base": "^", "icon": "skip", "say": "no início do texto"},
    "end": {"label": "Fim do texto", "base": "$", "icon": "skip", "say": "no fim do texto"},
    "date": {
        "label": "Data",
        "base": r"\d{2}/\d{2}/\d{4}",
        "ready": True,
        "icon": "clock",
        "example": "31/10/2026",
        "say": "uma data",
    },
    "cpf": {
        "label": "CPF",
        "base": r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}",
        "ready": True,
        "icon": "user",
        "example": "123.456.789-09",
        "say": "um CPF",
    },
    "cnpj": {
        "label": "CNPJ",
        "base": r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}",
        "ready": True,
        "icon": "building",
        "example": "12.345.678/0001-90",
        "say": "um CNPJ",
    },
    "cep": {
        "label": "CEP",
        "base": r"\d{5}-?\d{3}",
        "ready": True,
        "icon": "globe",
        "example": "01310-100",
        "say": "um CEP",
    },
    "email": {
        "label": "E-mail",
        "base": r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+",
        "ready": True,
        "icon": "link",
        "example": "ana@empresa.com.br",
        "say": "um e-mail",
    },
    "phone": {
        "label": "Telefone",
        "base": r"\(?\d{2}\)?\s?\d{4,5}-?\d{4}",
        "ready": True,
        "icon": "server",
        "example": "(11) 98765-4321",
        "say": "um telefone",
    },
    "decimal": {
        "label": "Valor com vírgula",
        "base": r"\d{1,3}(?:\.\d{3})+,\d+|\d+,\d+",
        "ready": True,
        "icon": "sigma",
        "example": "1.234,56",
        "say": "um valor com vírgula",
    },
}

_SPECIAL = set("\\.^$|?*+()[]{}")


def escape(text: str) -> str:
    """Texto fixo como expressão regular. O mesmo conjunto na tela: só os caracteres que têm significado."""
    return "".join("\\" + c if c in _SPECIAL else c for c in text)


class RegexPiece(BaseModel):
    kind: PieceKind = "digits"
    text: str = Field("", max_length=200)  # texto fixo
    count: int | None = Field(None, ge=1, le=99)  # quantidade exata; vazio = quantos houver
    take: bool = False  # vira coluna (modo Pegar)
    name: str = Field("", max_length=60)


def piece_regex(piece: RegexPiece) -> str:
    spec = PIECES[piece.kind]
    if piece.kind == "literal":
        part = escape(piece.text)
    elif spec.get("repeat"):
        part = spec["base"] + (
            "+" if piece.count is None else "" if piece.count == 1 else f"{{{piece.count}}}"
        )
    elif spec.get("ready") and "|" in spec["base"]:
        part = f"(?:{spec['base']})"  # alternativa só vale dentro dela mesma
    else:
        part = spec["base"]
    return f"({part})" if piece.take else part


def pattern_of(pieces: list[RegexPiece]) -> str:
    return "".join(piece_regex(p) for p in pieces)


def names_of(pieces: list[RegexPiece]) -> list[str]:
    taken = [p for p in pieces if p.take]
    if not taken:  # sem peça marcada, o trecho inteiro vira uma coluna
        return ["trecho"] if pieces else []
    return [p.name.strip() or f"grupo_{i + 1}" for i, p in enumerate(taken)]


def catalog() -> dict[str, dict[str, Any]]:
    """O que a tela precisa para montar e descrever as peças: rótulo, trecho, ícone e exemplo."""
    keep = ("label", "base", "repeat", "ready", "unit", "icon", "example", "say")
    return {kind: {k: v for k, v in spec.items() if k in keep} for kind, spec in PIECES.items()}
