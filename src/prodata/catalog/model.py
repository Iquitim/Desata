"""Peças comuns do catálogo (spec 049): período escolhido, colunas com dicionário e o resultado de uma leitura."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal

import polars as pl
from pydantic import BaseModel, Field

ColumnType = Literal["data", "numero", "inteiro", "texto"]


@dataclass(frozen=True)
class Column:
    name: str
    type: ColumnType
    # Uma frase do que significa, em português (dicionário de colunas, RF-4912).
    description: str


class PeriodChoice(BaseModel):
    """O período escolhido na caixa (RF-4914). Relativo é resolvido na execução, para o agendamento trazer o recente."""

    kind: Literal["ultimos_anos", "desde", "intervalo", "tudo"] = "ultimos_anos"
    anos: int = Field(default=5, ge=1, le=100)
    inicio: date | None = None
    fim: date | None = None

    def resolve(self, today: date, first: date | None = None) -> tuple[date, date]:
        floor = first or date(1900, 1, 1)
        match self.kind:
            case "ultimos_anos":
                start = _years_before(today, self.anos)
                return max(start, floor), today
            case "desde":
                return max(self.inicio or floor, floor), today
            case "intervalo":
                # O fim pode passar de hoje: a Selic meta e o Focus têm datas futuras.
                return max(self.inicio or floor, floor), self.fim or today
            case _:
                return floor, today


def _years_before(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:  # 29 de fevereiro
        return day.replace(year=day.year - years, day=28)


def add_years(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year + years)
    except ValueError:
        return day.replace(year=day.year + years, day=28)


@dataclass
class ReadResult:
    frame: pl.DataFrame
    # Os endereços chamados, para o Avançado e o Perfil (sem nada sigiloso: o catálogo não tem segredo).
    urls: list[str] = field(default_factory=list)
    # Avisos em palavras para a caixa ("12 valores marcados pelo IBGE como sem dado viraram vazio").
    warnings: list[str] = field(default_factory=list)
    # O que o órgão disse sobre o que veio (unidade, nome da variável), para o Perfil e a citação.
    info: dict[str, str] = field(default_factory=dict)
    read_at: datetime = field(default_factory=datetime.now)


class SourceNotFoundError(Exception):
    """O código pedido não existe no órgão (série, tabela ou variável)."""


# Marcas que o IBGE e outros órgãos usam para "sem dado" (RF-4943).
MISSING_MARKS = frozenset({"", "-", "..", "...", "X", "x", "null", "None"})


def to_number(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    text = str(value).strip()
    if text in MISSING_MARKS:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def count_missing(values: list[object]) -> int:
    return sum(1 for v in values if v is not None and str(v).strip() in MISSING_MARKS)
