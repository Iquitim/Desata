"""Pasta de arquivos como fonte da aba Dados (spec 035): vários arquivos de um padrão viram uma tabela só.

A pasta é só lida, onde está: o PRO.DATA nunca grava, move ou apaga nada nela (constituição IV). O cadastro fica num
arquivo ao lado da lista de arquivos vinculados; os fluxos guardam só ``folder:<id>``.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import threading
import unicodedata
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from prodata.errors import ConflictError, InvalidInputError, NotFoundError
from prodata.ingestion.detect import EXTENSIONS
from prodata.ingestion.options import ReadOptions

FOLDER_PREFIX = "folder:"
MAX_FILES = 500
MAX_SOURCES = 500


def source_folder_id(source: str) -> str | None:
    """``folder:fechamento`` → ``fechamento``; outra fonte → None."""
    return source[len(FOLDER_PREFIX) :] if source.startswith(FOLDER_PREFIX) else None


def check_pattern(pattern: str) -> str:
    pattern = pattern.strip() or "*"
    if any(c in pattern for c in "/\\") or ".." in pattern:
        raise InvalidInputError("O padrão vale para o nome do arquivo: não pode ter barras nem '..'.")
    return pattern


def folder_files(folder: str, pattern: str) -> list[Path]:
    """Arquivos da pasta que casam com o padrão, em ordem de nome. Só a pasta escolhida, sem subpastas."""
    raw = folder.strip()
    if not raw:
        raise InvalidInputError("Escolha a pasta.")
    path = Path(raw)
    if not path.is_absolute():
        raise InvalidInputError("A pasta precisa ser um caminho completo, como D:\\Fechamento\\2026-10.")
    if not path.is_dir():
        raise NotFoundError(f"A pasta não existe: {path}. Ela foi movida ou renomeada?")
    wanted = check_pattern(pattern)
    found = sorted(
        (
            p
            for p in path.iterdir()
            if p.is_file()
            and p.suffix.lower() in EXTENSIONS
            and not p.name.startswith("~$")  # arquivo temporário do Excel aberto
            and fnmatch.fnmatch(p.name.lower(), wanted.lower())
        ),
        key=lambda p: p.name.lower(),
    )
    if len(found) > MAX_FILES:
        raise InvalidInputError(
            f"{len(found)} arquivos casam com '{wanted}': o limite é {MAX_FILES}. Use um padrão mais específico."
        )
    return found


def files_signature(files: list[Path]) -> str:
    return "|".join(f"{p.name}:{p.stat().st_size}:{p.stat().st_mtime_ns}" for p in files)


def read_folder(
    files: list[Path],
    options: ReadOptions,
    file_column: str,
    *,
    limit: int | None = None,
    report: Callable[[str], None] | None = None,
    seen: dict[str, list[str]] | None = None,
    notes: list[str] | None = None,
    companies: pl.Series | None = None,
    budget: int | None = None,
) -> tuple[pl.DataFrame, list[str]]:
    """Empilha os arquivos. Devolve a tabela e os arquivos com colunas diferentes das do primeiro.
    ``seen`` recebe as colunas de cada arquivo (spec 046: quais arquivos não têm uma coluna); ``notes``, os avisos
    da leitura com leiaute (spec 049: o leiaute da Receita mudou)."""
    from prodata.ingestion.readers import read_table  # evita ciclo na carga do pacote

    layout = getattr(options, "layout", "")

    column = file_column.strip()
    frames: list[pl.DataFrame] = []
    odd: list[str] = []
    first: list[str] = []
    for i, path in enumerate(files, start=1):
        if report:
            report(f"{i}/{len(files)} arquivos")
        if layout:
            from prodata.catalog import cnpj

            frame, said = cnpj.read_file(
                path, layout, limit, getattr(options, "layout_filter", {}), companies
            )
            if notes is not None:
                notes.extend(said)
        else:
            frame = read_table(path, options, n_rows=limit)
        if seen is not None:
            seen[path.name] = list(frame.columns)
        if not frames:
            first = frame.columns
        elif set(frame.columns) != set(first):
            odd.append(path.name)
        if column:
            if column in frame.columns:
                raise InvalidInputError(
                    f"'{path.name}' já tem uma coluna '{column}': troque o nome da coluna do arquivo."
                )
            frame = frame.with_columns(pl.lit(path.name).alias(column))
        frames.append(frame)
        if budget is not None and layout and sum(f.estimated_size() for f in frames) > budget:
            from prodata.catalog import (
                cnpj,
            )  # CNPJ (spec 049, RF-4957): para antes de usar o disco como memória

            used = int(sum(f.estimated_size() for f in frames))
            raise cnpj.memory_question(used, budget * cnpj.MEMORY_SHARE, layout, read_so_far=True)
    if not frames:
        return pl.DataFrame(), []
    try:
        return pl.concat(frames, how="diagonal_relaxed"), odd
    except pl.exceptions.PolarsError as exc:
        raise InvalidInputError(
            f"Os arquivos têm colunas com tipos que não combinam: {str(exc).splitlines()[0]}"
        ) from exc


def _companies(
    source: FolderSource, lookup: Callable[[str], FolderSource] | None, report: Callable[[str], None] | None
) -> pl.Series:
    """Os CNPJs básicos da fonte de Estabelecimentos escolhida em Só as empresas destes estabelecimentos."""
    from prodata.catalog import cnpj

    if lookup is None:
        raise InvalidInputError(
            "Só as empresas destes estabelecimentos precisa da fonte cadastrada na vista Dados."
        )
    other = lookup(source.layout_companies_of)
    if other.layout != f"{cnpj.LAYOUT_PREFIX}estabelecimentos":
        raise InvalidInputError(f"'{other.name}' não é uma fonte de Estabelecimentos do CNPJ.")
    if report:
        report(f"lendo os CNPJs de {other.name}")
    return cnpj.companies_in(other.files(), other.layout_filter)


def read_source(
    source: FolderSource,
    limit: int,
    report: Callable[[str], None] | None,
    read_at: str,
    lookup: Callable[[str], FolderSource] | None = None,
    memory_ok: bool = False,
) -> tuple[pl.DataFrame, dict[str, Any]]:
    """Lê uma pasta cadastrada na vista Dados: a tabela e o que a caixa mostra (arquivos, avisos, leiaute)."""
    files = source.files()
    if not files:
        raise InvalidInputError(f"Nenhum arquivo em {source.folder} casa com '{source.pattern}'.")
    seen: dict[str, list[str]] = {}
    notes: list[str] = []
    companies = _companies(source, lookup, report) if source.layout_companies_of else None
    budget = None
    if (
        source.layout and not limit and not memory_ok
    ):  # CNPJ (spec 049, RF-4957): acima de 1/4 da memória, pergunta
        from prodata.catalog import cnpj
        from prodata.engine.cache import total_memory

        memory = total_memory()
        budget = cnpj.memory_budget(memory)
        if (expected := cnpj.estimate(files, source.layout, source.layout_filter, companies)) > budget:
            raise cnpj.memory_question(expected, memory, source.layout)
    table, odd = read_folder(
        files,
        source,
        source.file_column,
        limit=limit or None,
        report=report,
        seen=seen,
        notes=notes,
        companies=companies,
        budget=budget,
    )
    extra: dict[str, Any] = {"source": source.name, "source_read_at": read_at, "source_linked": source.folder}
    extra["folder_files"] = [p.name for p in files]
    extra = folder_warnings(extra, odd, seen, files[0].name)
    if source.layout:  # CNPJ da Receita (spec 049): dicionário de colunas, citação e aviso de leiaute
        from prodata.catalog import cnpj

        extra = cnpj.with_layout(extra, source.layout, Path(source.folder), notes)
        other = lookup(source.layout_companies_of).name if lookup and source.layout_companies_of else ""
        if words := cnpj.filter_words(source.layout, source.layout_filter, other):
            extra["leitura_filtrada"] = words
    return table, extra


def odd_warning(odd: list[str], first: str) -> str:
    shown = ", ".join(odd[:5]) + ("…" if len(odd) > 5 else "")
    return f"{len(odd)} arquivo(s) com colunas diferentes de {first}: {shown}. O que falta fica vazio."


class FolderSource(ReadOptions):
    """O cadastro. As opções de leitura valem para todos os arquivos da pasta."""

    id: str = Field("", pattern=r"^[a-z0-9_-]{0,60}$")
    name: str = Field(min_length=1, max_length=80)
    folder: str = Field(min_length=1, max_length=400)
    pattern: str = Field("*.xlsx", max_length=120)
    file_column: str = Field("arquivo", max_length=60)
    # Leiaute conhecido pelo programa (spec 049): o CNPJ da Receita, com nomes, tipos e o dicionário de colunas.
    layout: str = Field("", pattern=r"^(receita\.cnpj/[a-z]{3,20})?$")
    # Filtro na leitura do CNPJ (RF-4957): campo → valores; e a fonte de Estabelecimentos cujas empresas entram.
    layout_filter: dict[str, list[str]] = Field(default_factory=dict)
    layout_companies_of: str = Field("", pattern=r"^[a-z0-9_-]{0,60}$")

    @model_validator(mode="after")
    def _filter(self) -> FolderSource:
        from prodata.catalog import cnpj

        self.layout_filter = {k: list(dict.fromkeys(v)) for k, v in self.layout_filter.items() if v}
        try:
            cnpj.check_filter(self.layout, self.layout_filter, self.layout_companies_of)
        except ValueError as exc:
            raise ValueError(str(exc)) from None
        return self

    @field_validator("name", "file_column")
    @classmethod
    def _line(cls, value: str) -> str:
        return " ".join("".join(c if c.isprintable() else " " for c in value).split())

    def digest(self) -> str:
        raw = json.dumps(self.model_dump(mode="json"), sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:12]

    def files(self) -> list[Path]:
        return folder_files(self.folder, self.pattern)


class FolderStatus(BaseModel):
    files: int = 0
    newest: datetime | None = None
    missing: bool = False
    error: str = ""


class FolderEntry(FolderSource):
    status: FolderStatus = Field(default_factory=FolderStatus)


def status_of(source: FolderSource) -> FolderStatus:
    try:
        files = source.files()
    except NotFoundError as exc:
        return FolderStatus(missing=True, error=str(exc))
    except InvalidInputError as exc:
        return FolderStatus(error=str(exc))
    newest = max((p.stat().st_mtime for p in files), default=None)
    return FolderStatus(files=len(files), newest=datetime.fromtimestamp(newest, tz=UTC) if newest else None)


def _slug(name: str) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")[:40] or "pasta"


class FolderSources:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def _read(self) -> dict[str, FolderSource]:
        if not self.path.is_file():
            return {}
        try:
            data: Any = json.loads(self.path.read_text(encoding="utf-8"))
            return {s.id: s for s in (FolderSource.model_validate(item) for item in data)}
        except (OSError, ValueError, TypeError, ValidationError) as exc:
            raise InvalidInputError(f"Lista de pastas de arquivos corrompida: {self.path}") from exc

    def _write(self, sources: dict[str, FolderSource]) -> None:
        tmp = self.path.with_name(self.path.name + ".tmp")
        items = [s.model_dump(mode="json") for s in sorted(sources.values(), key=lambda s: s.name.lower())]
        tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def list(self) -> list[FolderSource]:
        return sorted(self._read().values(), key=lambda s: s.name.lower())

    def get(self, source_id: str) -> FolderSource:
        found = self._read().get(source_id)
        if found is None:
            raise NotFoundError(
                f"A pasta de arquivos '{source_id}' não está cadastrada neste computador. Cadastre na vista Dados."
            )
        return found

    def save(self, source: FolderSource, previous: str | None = None) -> FolderSource:
        """Cria (sem id) ou atualiza (com o id de antes). A pasta precisa existir na hora de salvar."""
        path = Path(source.folder.strip())
        if not path.is_absolute():
            raise InvalidInputError("A pasta precisa ser um caminho completo, como D:\\Fechamento\\2026-10.")
        if not path.is_dir():
            raise NotFoundError(f"A pasta não existe: {path}")
        clean = source.model_copy(update={"folder": str(path), "pattern": check_pattern(source.pattern)})
        with self._lock:
            sources = self._read()
            if previous:
                if previous not in sources:
                    raise NotFoundError("Esta pasta de arquivos não existe mais.")
                clean = clean.model_copy(update={"id": previous})
            else:
                if len(sources) >= MAX_SOURCES:
                    raise InvalidInputError(f"O limite é de {MAX_SOURCES} pastas de arquivos.")
                base = clean.id or _slug(clean.name)
                new_id, n = base, 2
                while new_id in sources:
                    new_id, n = f"{base}_{n}", n + 1
                clean = clean.model_copy(update={"id": new_id})
            if any(s.id != clean.id and s.name.casefold() == clean.name.casefold() for s in sources.values()):
                raise ConflictError(f"Já existe uma pasta de arquivos chamada '{clean.name}'.")
            sources[clean.id] = clean
            self._write(sources)
        return clean

    def delete(self, source_id: str) -> None:
        """Só esquece o cadastro: a pasta e os arquivos ficam intactos."""
        with self._lock:
            sources = self._read()
            if sources.pop(source_id, None) is None:
                raise NotFoundError("Esta pasta de arquivos não existe mais.")
            self._write(sources)

    def signature(self, source_id: str) -> str:
        """Muda quando o cadastro muda ou quando entra, sai ou muda um arquivo da pasta."""
        source = self.get(source_id)
        try:
            files = source.files()
        except InvalidInputError as exc:  # padrão demais: a execução mostra o erro, a assinatura só registra
            return f"{source.digest()}#erro:{exc}"
        mine = f"{source.digest()}#{files_signature(files)}"
        if source.layout_companies_of:  # Só as empresas destes estabelecimentos: muda junto com a outra fonte
            try:
                return f"{mine}#{self.signature(source.layout_companies_of)}"
            except (NotFoundError, InvalidInputError) as exc:
                return f"{mine}#erro:{exc}"
        return mine


def missing_columns(seen: dict[str, list[str]]) -> tuple[dict[str, list[str]], list[str]]:
    """Por coluna da pasta, os arquivos que não a têm, e uma frase por coluna (spec 046, RF-4609).
    O formato da pasta é o conjunto das colunas de todos os arquivos, não o do último arquivo."""
    every = list(dict.fromkeys(c for columns in seen.values() for c in columns))
    out: dict[str, list[str]] = {}
    for column in every:
        without = [name for name, columns in seen.items() if column not in columns]
        if without:
            out[column] = without
    phrases = [
        f"{len(files)} arquivo{'s' if len(files) > 1 else ''} sem a coluna '{column}' "
        f"({', '.join(files[:3])}{'…' if len(files) > 3 else ''}): nesses arquivos ela fica vazia."
        for column, files in out.items()
    ]
    return out, phrases


def folder_warnings(
    extra: dict[str, Any], odd: list[str], seen: dict[str, list[str]], first: str
) -> dict[str, Any]:
    """Arquivos sem uma coluna que os outros têm, coluna por coluna (spec 046, RF-4609)."""
    if not odd:
        return extra
    missing, phrases = missing_columns(seen)
    extra["folder_missing"] = missing
    extra["warnings"] = phrases or [odd_warning(odd, first)]
    return extra
