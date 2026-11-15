"""Data digitada pela pessoa (spec 040): o mesmo leitor no motor e no SQL do Filter básico.

Aceita ``AAAA-MM-DD`` (o que o calendário grava) e ``DD/MM/AAAA`` ou ``DD-MM-AAAA`` (como no Brasil), com ou sem aspas.
"""

from __future__ import annotations

import re
from datetime import date, datetime

_ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
_BR = re.compile(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4}|\d{2})$")  # ano com 2 dígitos = 20xx
_TIME = re.compile(r"^(.*?)[ T](\d{1,2}):(\d{2})(?::(\d{2}))?$")


def parse_user_date(text: str) -> date | None:
    """A data escrita, ou None quando não é uma data que existe."""
    raw = text.strip().strip("'\"").strip()
    if m := _ISO.match(raw):
        y, mo, d = int(m[1]), int(m[2]), int(m[3])
    elif m := _BR.match(raw):
        d, mo, y = int(m[1]), int(m[2]), int(m[3])
        y += 2000 if len(m[3]) == 2 else 0
    else:
        return None
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def parse_user_moment(text: str) -> date | datetime | None:
    """Data com hora (``2026-01-05 10:30:00``) vira o instante; sem hora, a data."""
    raw = text.strip().strip("'\"").strip()
    if ":" not in raw:
        return parse_user_date(raw)
    try:  # o formato padrão, inclusive com fração de segundo ("2026-01-05 10:30:00.000000")
        return datetime.fromisoformat(raw)
    except ValueError:
        pass
    m = _TIME.match(raw)
    day = parse_user_date(m[1]) if m else None
    if m is None or day is None:
        return None
    try:  # "08/07/2026 14:30", "2026-07-08T14:30:00"…
        return datetime(day.year, day.month, day.day, int(m[2]), int(m[3]), int(m[4] or 0))
    except ValueError:
        return None


def moment_or_error(text: str, column: str) -> date | datetime:
    found = parse_user_moment(text)
    if found is None:
        raise ValueError(
            f"'{text}' não é uma data para comparar com a coluna '{column}': escolha no calendário ou escreva 31/12/2026."
        )
    return found


def date_or_error(text: str, column: str) -> date:
    found = parse_user_date(text)
    if found is None:
        raise ValueError(
            f"'{text}' não é uma data para comparar com a coluna '{column}': escolha no calendário ou escreva 31/12/2026."
        )
    return found
