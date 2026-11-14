"""Tipos dos campos e conversão do texto do PDF (spec 037, RF-3720).

Padrão brasileiro primeiro: ``1.234,56`` é mil duzentos e trinta e quatro e cinquenta e seis; ``1.234`` sem vírgula é
mil duzentos e trinta e quatro; ``12.5`` (um ponto, sem grupo de três) é doze e meio. Texto que não converte levanta
:class:`InvalidValueError` sem repetir o conteúdo: o valor nunca é inventado nem "aproximado".
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

FieldType = Literal["texto", "inteiro", "decimal", "moeda", "data", "mes_ano", "sim_nao"]
TYPES: tuple[FieldType, ...] = ("texto", "inteiro", "decimal", "moeda", "data", "mes_ano", "sim_nao")
TYPE_LABELS: dict[str, str] = {
    "texto": "Texto",
    "inteiro": "Número inteiro",
    "decimal": "Número decimal",
    "moeda": "Moeda (R$)",
    "data": "Data",
    "mes_ano": "Mês/ano",
    "sim_nao": "Sim/não",
}

_MONTHS = {
    "janeiro": 1, "jan": 1, "fevereiro": 2, "fev": 2, "marco": 3, "mar": 3, "abril": 4, "abr": 4, "maio": 5, "mai": 5,
    "junho": 6, "jun": 6, "julho": 7, "jul": 7, "agosto": 8, "ago": 8, "setembro": 9, "set": 9, "outubro": 10,
    "out": 10, "novembro": 11, "nov": 11, "dezembro": 12, "dez": 12,
}  # fmt: skip
_TRUE = {"sim", "s", "x", "yes", "y", "verdadeiro", "true", "v"}
_FALSE = {"nao", "n", "no", "falso", "false", "f"}
_THOUSANDS = re.compile(r"\d{1,3}(\.\d{3})+")


class InvalidValueError(ValueError):
    """O texto não converte para o tipo pedido. A mensagem diz o porquê, nunca o conteúdo."""


def normalize(text: str) -> str:
    """Sem acento, minúsculo, um espaço só: 'Competência ' e 'COMPETENCIA' ficam iguais."""
    decomposed = unicodedata.normalize("NFKD", text)
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(plain.casefold().split())


def parse_number(text: str) -> Decimal:
    s = normalize(text).replace("r$", "").replace(" ", "")
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative, s = True, s[1:-1]
    if s.startswith("-"):
        negative, s = True, s[1:]
    elif s.endswith("-"):
        negative, s = True, s[:-1]
    elif s.startswith("+"):
        s = s[1:]
    if not re.fullmatch(r"[\d.,]+", s) or not re.search(r"\d", s):
        raise InvalidValueError("não é um número")
    if "," in s:
        whole, _, frac = s.partition(",")
        if "," in frac or "." in frac or not frac.isdigit():
            raise InvalidValueError("número com vírgula fora do lugar")
        if "." in whole:
            if not _THOUSANDS.fullmatch(whole):
                raise InvalidValueError("separador de milhar fora do lugar")
            whole = whole.replace(".", "")
        s = f"{whole or '0'}.{frac}"
    elif "." in s:
        if _THOUSANDS.fullmatch(s):
            s = s.replace(".", "")
        elif s.count(".") > 1:
            raise InvalidValueError("separador de milhar fora do lugar")
    try:
        value = Decimal(s)
    except InvalidOperation:
        raise InvalidValueError("não é um número") from None
    return -value if negative else value


def _parse_date(text: str) -> date:
    s = normalize(text)
    try:
        if m := re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4}|\d{2})", s):
            day, month, year = int(m[1]), int(m[2]), int(m[3])
            return date(year + 2000 if year < 100 else year, month, day)
        if m := re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s):
            return date(int(m[1]), int(m[2]), int(m[3]))
        if (m := re.fullmatch(r"(\d{1,2}) de ([a-z]+) de (\d{4})", s)) and m[2] in _MONTHS:
            return date(int(m[3]), _MONTHS[m[2]], int(m[1]))
    except ValueError:
        raise InvalidValueError("data que não existe") from None
    raise InvalidValueError("não é uma data")


def _parse_month(text: str) -> date:
    s = normalize(text)
    m = re.fullmatch(r"(\d{1,2})[/.-](\d{4})", s) or re.fullmatch(r"(\d{4})-(\d{1,2})", s)
    if m:
        month, year = (int(m[1]), int(m[2])) if len(m[2]) == 4 else (int(m[2]), int(m[1]))
        if 1 <= month <= 12:
            return date(year, month, 1)
        raise InvalidValueError("mês que não existe")
    m = re.fullmatch(r"([a-z]+)(?:/| de | )(\d{4}|\d{2})", s)
    if m and m[1] in _MONTHS:
        year = int(m[2])
        return date(year + 2000 if year < 100 else year, _MONTHS[m[1]], 1)
    raise InvalidValueError("não é um mês/ano")


def convert(text: str, kind: str) -> Any:
    """Texto do PDF → valor do tipo. ``InvalidValueError`` quando não converte."""
    clean = " ".join(text.split())
    if not clean:
        raise InvalidValueError("vazio")
    if kind == "texto":
        return clean
    if kind in ("inteiro", "decimal", "moeda"):
        number = parse_number(clean)
        if kind == "inteiro":
            if number != number.to_integral_value():
                raise InvalidValueError("tem casas decimais")
            return int(number)
        if kind == "moeda":
            cents = number.quantize(Decimal("0.01"))
            if cents != number:
                raise InvalidValueError("mais de duas casas decimais")
            return cents
        return number
    if kind == "data":
        return _parse_date(clean)
    if kind == "mes_ano":
        return _parse_month(clean)
    if kind == "sim_nao":
        word = normalize(clean)
        if word in _TRUE:
            return True
        if word in _FALSE:
            return False
        raise InvalidValueError("não é sim nem não")
    raise InvalidValueError("tipo desconhecido")


def guess_type(text: str) -> FieldType:
    """Tipo mais provável para o texto marcado (a pessoa troca na hora se não for)."""
    clean = " ".join(text.split())
    attempts: list[FieldType] = ["data", "mes_ano"]
    if "R$" in clean.upper() or re.search(r"\d,\d{2}$", clean):
        attempts.insert(0, "moeda")
    attempts += ["inteiro", "decimal"]
    for kind in attempts:
        try:
            convert(clean, kind)
            return kind
        except InvalidValueError:
            continue
    if normalize(clean) in {"sim", "nao"}:
        return "sim_nao"
    return "texto"


def to_json(value: Any) -> Any:
    """Valor convertido → JSON da prévia (Decimal vira texto para não perder centavos; data vira ISO)."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    return value
