"""Nome dinâmico no Output Data (spec 041): ``vendas_{regiao}`` grava um arquivo por valor da coluna.

Dentro de um laço por região, cada volta tem um valor só e vira um arquivo; fora dele, a caixa separa sozinha.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import polars as pl

from prodata.errors import InvalidInputError

FIELD = re.compile(r"\{([^{}]{1,80})\}")
MAX_FILES = 500
_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def name_columns(filename: str, columns: list[str]) -> list[str]:
    """As colunas citadas entre chaves no nome; coluna que não existe é erro claro."""
    wanted = list(dict.fromkeys(m.strip() for m in FIELD.findall(filename or "")))
    missing = [c for c in wanted if c not in columns]
    if missing:
        raise InvalidInputError(
            f"O nome do arquivo cita {', '.join('{' + c + '}' for c in missing)}, que não existe na tabela."
        )
    return wanted


def piece(value: Any) -> str:
    """O valor como pedaço de nome de arquivo: sem caracteres proibidos no Windows, curto e nunca vazio."""
    if value is None:
        return "vazio"
    text = value.isoformat()[:10] if isinstance(value, date) else str(value)
    text = _BAD.sub("_", text).strip().strip(".")
    return text[:60] or "vazio"


def fill(filename: str, row: dict[str, Any]) -> str:
    return FIELD.sub(lambda m: piece(row.get(m.group(1).strip())), filename)


def split(df: pl.DataFrame, filename: str, columns: list[str]) -> list[tuple[str, pl.DataFrame]]:
    """Um (nome, tabela) por combinação de valores das colunas do nome, na ordem em que aparecem."""
    parts = df.partition_by(columns, maintain_order=True, as_dict=True) if df.height else {}
    if len(parts) > MAX_FILES:
        raise InvalidInputError(
            f"O nome dinâmico geraria {len(parts)} arquivos; o limite é {MAX_FILES}. Escolha uma coluna com menos valores."
        )
    out = []
    for key, part in parts.items():
        values = key if isinstance(key, tuple) else (key,)
        out.append((fill(filename, dict(zip(columns, values, strict=True))), part))
    return out


def new_file_path(path: Path) -> Path:
    """Mesmo nome com data e hora (e um número, se ainda assim existir): o arquivo antigo fica intacto."""
    stamp = datetime.now().strftime("%Y-%m-%d %Hh%M")
    candidate = path.with_name(f"{path.stem} {stamp}{path.suffix}")
    n = 2
    while candidate.exists():
        candidate = path.with_name(f"{path.stem} {stamp} ({n}){path.suffix}")
        n += 1
    return candidate
