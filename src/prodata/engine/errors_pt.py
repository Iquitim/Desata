"""Erros do motor em português, com o que fazer (spec 046, RF-4621..4623).

Só traduz o que reconhece: um erro que não se encaixa em nenhum caso conhecido continua como veio, sem tradução
inventada. O texto original fica em ``technical`` (vai inteiro para o log e para "Detalhes técnicos").
"""

from __future__ import annotations

import difflib
import errno
import re
from dataclasses import dataclass, field
from pathlib import PurePath
from typing import Any

from pydantic import ValidationError


@dataclass
class Friendly:
    message: str
    technical: str | None = None  # o texto original, quando a mensagem foi traduzida
    hint: dict[str, Any] = field(default_factory=dict)  # ex.: {"kind": "column_missing", "columns": [...]}


# ---------------------------------------------------------------- colunas que não existem (RF-4622)

_MISSING = [
    re.compile(r"Coluna\(s\)(?:-chave| de agregação)? inexistente\(s\): (?P<cols>.+?)(?:\.|$)"),
    re.compile(r"Coluna inexistente na referência: (?P<cols>\[[^\]]+\])"),
    re.compile(r"Coluna '(?P<col>[^']+)' não existe"),
    re.compile(r'unable to find column "(?P<col>[^"]+)"'),
    re.compile(r'[Rr]eferenced column "(?P<col>[^"]+)" not found'),
]


def missing_columns(message: str) -> list[str]:
    for pattern in _MISSING:
        m = pattern.search(message)
        if not m:
            continue
        if "col" in pattern.groupindex:
            return [m.group("col")]
        return [c.strip().strip("[]") for c in m.group("cols").split(",") if c.strip()]
    return []


def similar(name: str, columns: list[str], n: int = 3) -> list[str]:
    """Colunas parecidas: pelo texto e, de quebra, sem diferenciar maiúsculas e acentos."""
    lowered = {c.lower(): c for c in columns}
    exact = [lowered[name.lower()]] if name.lower() in lowered and lowered[name.lower()] != name else []
    close = [lowered[c] for c in difflib.get_close_matches(name.lower(), list(lowered), n=n, cutoff=0.6)]
    return list(dict.fromkeys([*exact, *close]))[:n]


def column_hint(message: str, columns: list[str]) -> dict[str, Any]:
    cols = [c for c in missing_columns(message) if c not in columns]
    if not cols:
        return {}
    return {"kind": "column_missing", "columns": cols, "similar": {c: similar(c, columns) for c in cols}}


# ---------------------------------------------------------------- textos em inglês que ainda escapam (RF-4621)


def _function_names() -> list[str]:
    from prodata.engine.formula import function_catalog

    return [f["name"] for f in function_catalog()]


def _rewrite(text: str) -> str | None:
    """Reescreve os trechos conhecidos em inglês (DuckDB, Polars) mantendo o começo da mensagem
    ("Fórmula de [x]: …"). Devolve None se nada foi reconhecido."""
    head, sep, tail = text.partition(": ") if text.startswith("Fórmula de ") else ("", "", text)
    prefix = f"{head}{sep}"
    if m := re.search(r"Scalar Function with name (\w+) does not exist", tail):
        name = m.group(1)
        near = difflib.get_close_matches(
            name.lower(), [f.lower() for f in _function_names()], n=3, cutoff=0.5
        )
        by_lower = {f.lower(): f for f in _function_names()}
        tip = f" Parecidas: {', '.join(by_lower[x] for x in near)}." if near else ""
        return f"{prefix}A função {name} não existe nas fórmulas.{tip} A lista completa fica no botão de funções do editor."
    if m := re.search(r"Table with name (\w+) does not exist", tail):
        return (f"{prefix}A tabela '{m.group(1)}' não existe nesta consulta. Use input_1 para a entrada 1 "
                "e input_2 para a entrada 2.")  # fmt: skip
    if m := re.search(r'Parser Error: syntax error at or near "([^"]*)"', tail):
        return f'{prefix}Erro de sintaxe perto de "{m.group(1)}". Confira vírgulas, aspas e palavras-chave.'
    if m := re.search(r'[Rr]eferenced column "([^"]+)" not found', tail):
        return f"{prefix}A coluna '{m.group(1)}' não existe na entrada."
    if m := re.search(r'unable to find column "([^"]+)"', tail):
        return f"{prefix}A coluna '{m.group(1)}' não existe na entrada."
    if re.search(r"duplicate|already exists", tail, re.IGNORECASE) and "column" in tail.lower():
        name = re.search(r'"([^"]+)"|\'([^\']+)\'', tail)
        which = f" '{next(g for g in name.groups() if g)}'" if name else ""
        return (
            f"{prefix}A coluna{which} aparece mais de uma vez. Renomeie uma delas (no Select, por exemplo)."
        )
    if re.search(r"out of memory|memory allocation|cannot allocate", tail, re.IGNORECASE):
        return prefix + _MEMORY
    return None


_MEMORY = ("Faltou memória para processar estes dados. Filtre ou selecione só as colunas necessárias antes desta "
           "caixa, ou use o limite de linhas da entrada para testar.")  # fmt: skip


def _os_message(exc: OSError) -> str | None:
    name = PurePath(str(exc.filename)).name if exc.filename else "o arquivo"
    win = getattr(exc, "winerror", None)
    if isinstance(exc, PermissionError) or exc.errno in (errno.EACCES, errno.EPERM) or win in (5, 32, 33):
        return (f"Não foi possível usar {name}: ele está aberto em outro programa (provavelmente o Excel) "
                "ou a pasta não permite gravar. Feche o arquivo e execute de novo.")  # fmt: skip
    if isinstance(exc, FileNotFoundError) or exc.errno == errno.ENOENT:
        return f"Não encontrei {name}. Confira se o arquivo ou a pasta ainda existe nesse lugar."
    if exc.errno == errno.ENOSPC:
        return "Acabou o espaço no disco. Libere espaço e execute de novo."
    return None


def translate(exc: BaseException, columns: list[str] | None = None) -> Friendly:
    """A mensagem para a pessoa, o texto técnico e, se for o caso, a dica de coluna parecida."""
    columns = columns or []
    original = getattr(exc, "message", None) or str(exc)
    if isinstance(exc, MemoryError):
        return Friendly(_MEMORY, technical=original or "MemoryError")
    if isinstance(exc, OSError) and (message := _os_message(exc)):
        return Friendly(message, technical=original)
    rewritten = _rewrite(original)
    message = rewritten or original
    return Friendly(message, technical=original if rewritten else None, hint=column_hint(original, columns))


# ---------------------------------------------------------------- configuração inválida


def _validation_text(err: Any) -> str:
    kind = err.get("type", "")
    ctx = err.get("ctx") or {}
    if kind == "literal_error":
        return f"valor não aceito (use {str(ctx.get('expected', 'uma das opções da lista')).replace(' or ', ' ou ')})"
    if kind == "missing":
        return "preenchimento obrigatório"
    if kind in ("int_parsing", "int_type", "int_from_float"):
        return "use um número inteiro"
    if kind in ("float_parsing", "float_type"):
        return "use um número"
    if kind in ("bool_parsing", "bool_type"):
        return "use ligado ou desligado"
    if kind in ("greater_than_equal", "greater_than"):
        return f"use um valor a partir de {ctx.get('ge', ctx.get('gt'))}"
    if kind in ("less_than_equal", "less_than"):
        return f"use um valor até {ctx.get('le', ctx.get('lt'))}"
    if kind == "string_too_long":
        return f"texto longo demais (até {ctx.get('max_length')} caracteres)"
    if kind == "string_pattern_mismatch":
        return "formato não aceito"
    if kind in ("list_type", "string_type", "dict_type"):
        return "tipo de valor não aceito"
    return str(err.get("msg", "valor inválido"))


def validation_message(exc: ValidationError) -> tuple[str, str | None]:
    first = exc.errors()[0]
    field_name = ".".join(str(p) for p in first["loc"]) or None
    return f"Configuração inválida em '{field_name}': {_validation_text(first)}.", field_name
