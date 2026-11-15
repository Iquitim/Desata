"""Amostra que viaja com o fluxo (spec 040, RF-4013..4016).

Opcional, criada só em "Salvar com amostra dos dados". Guarda as primeiras linhas de uma fonte em Parquet (os tipos voltam
exatos), em base64 dentro do arquivo do fluxo, com o nome legível da fonte e a data. Nunca guarda caminho, senha ou
conexão: só os dados e os nomes das colunas.
"""

from __future__ import annotations

import base64
import hashlib
import io
from datetime import UTC, datetime

import polars as pl
from pydantic import BaseModel, Field

MAX_ROWS = 1_000  # por fonte
MAX_BYTES = 5 * 1024 * 1024  # no total, já em Parquet


class SourceSample(BaseModel):
    label: str = Field(max_length=200)  # o nome que a pessoa vê, nunca o caminho
    rows: int = Field(ge=0, le=MAX_ROWS)
    columns: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    data: str  # Parquet em base64
    linked: bool = (
        False  # na origem, um arquivo vinculado (lido de uma pasta de quem enviou); o caminho nunca vai
    )

    @classmethod
    def of(cls, frame: pl.DataFrame, label: str, linked: bool = False) -> SourceSample:
        head = frame.head(MAX_ROWS)
        buf = io.BytesIO()
        head.write_parquet(buf, compression="zstd")
        return cls(
            label=label,
            rows=head.height,
            columns=head.columns,
            data=base64.b64encode(buf.getvalue()).decode(),
            linked=linked,
        )

    def frame(self) -> pl.DataFrame:
        return pl.read_parquet(io.BytesIO(base64.b64decode(self.data)))

    def size(self) -> int:
        return len(self.data) * 3 // 4

    def digest(self) -> str:
        return hashlib.sha256(self.data.encode()).hexdigest()[:16]
