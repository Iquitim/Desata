"""Leituras guardadas (spec 049, RF-4925, RF-4973): a última leitura bem-sucedida de cada consulta do catálogo.

Fica na pasta de dados deste computador (``<catálogo>/leituras/<impressão>.parquet`` e ``.json``), nunca no fluxo nem
na pasta de um espaço da equipe. A impressão é a da fonte com as escolhas: a mesma caixa, com as mesmas escolhas, acha
a sua leitura; mudou a escolha, é outra consulta.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl

FOLDER = "leituras"


def fingerprint(source_id: str, choices: dict[str, Any]) -> str:
    text = json.dumps(
        {"fonte": source_id, "escolhas": choices}, sort_keys=True, ensure_ascii=False, default=str
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


@dataclass
class Saved:
    frame: pl.DataFrame
    read_at: datetime
    warnings: list[str]


def save(root: Path, source_id: str, choices: dict[str, Any], frame: pl.DataFrame, read_at: datetime,
         warnings: list[str] | None = None) -> None:  # fmt: skip
    folder = root / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    key = fingerprint(source_id, choices)
    data_tmp = folder / f"{key}.{os.getpid()}.parquet.tmp"
    frame.write_parquet(data_tmp)
    os.replace(data_tmp, folder / f"{key}.parquet")
    meta = {"fonte": source_id, "escolhas": choices, "lido_em": read_at.isoformat(), "linhas": frame.height,
            "avisos": warnings or []}  # fmt: skip
    meta_tmp = folder / f"{key}.{os.getpid()}.json.tmp"
    meta_tmp.write_text(json.dumps(meta, ensure_ascii=False, default=str), encoding="utf-8")
    os.replace(meta_tmp, folder / f"{key}.json")


def load(root: Path, source_id: str, choices: dict[str, Any]) -> Saved | None:
    folder = root / FOLDER
    key = fingerprint(source_id, choices)
    try:
        meta = json.loads((folder / f"{key}.json").read_text(encoding="utf-8"))
        frame = pl.read_parquet(folder / f"{key}.parquet")
    except OSError, ValueError, pl.exceptions.PolarsError:
        return None
    return Saved(frame, datetime.fromisoformat(meta["lido_em"]), list(meta.get("avisos", [])))


def read_at(root: Path, source_id: str, choices: dict[str, Any]) -> datetime | None:
    try:
        meta = json.loads(
            (root / FOLDER / f"{fingerprint(source_id, choices)}.json").read_text(encoding="utf-8")
        )
        return datetime.fromisoformat(meta["lido_em"])
    except OSError, ValueError, KeyError:
        return None
