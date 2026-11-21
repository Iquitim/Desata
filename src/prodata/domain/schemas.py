"""Formato lembrado das fontes e das saídas (spec 046, RF-4601, RF-4608).

Viaja dentro do fluxo e guarda só nomes e tipos de coluna: nunca valores, caminhos ou credenciais.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class ColumnSpec(BaseModel):
    name: str = Field(max_length=500)
    type: str = Field(max_length=20)


class RememberedSchema(BaseModel):
    """Colunas e tipos por porta da caixa (``out`` numa fonte; ``in``, ``in2``… num Output)."""

    ports: dict[str, list[ColumnSpec]] = Field(default_factory=dict)
    seen_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
