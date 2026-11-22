"""Arquivos dos portais: prévia, formato aceito e conferência a cada execução (spec 049, RF-4938, RF-4940).

- O arquivo é baixado para o cache do catálogo (``<pasta de dados>/catalogo/arquivos``), com nome fixo derivado do
  endereço, e lido pela **mesma leitura da vista Dados** (``ingestion.readers.read_table``): separador, codificação,
  cabeçalho e decimal detectados, ou os que a pessoa escolheu na prévia.
- Até 200 MB, direto; acima disso o cliente para e diz que é grande (o download com pasta cuida, RF-4952).
- ZIP é conferido antes de abrir: caminhos sem ``..`` nem absolutos, tamanho descompactado e proporção máximos, e só
  arquivos que o programa lê lá dentro. Com mais de um, a pessoa escolhe qual.
- O **formato aceito** (opções de leitura, arquivo de dentro do ZIP e colunas com tipo) vai na configuração da caixa.
  Na execução, se as colunas mudaram, a leitura **para** e diz o que mudou (``FormatChangedError``); nunca entrega
  uma tabela diferente em silêncio.
"""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

import polars as pl
from pydantic import BaseModel, Field

from prodata.catalog.http import CatalogClient, CatalogError
from prodata.catalog.model import ReadResult
from prodata.engine.convert import parse_date, parse_number
from prodata.engine.profiling import schema_of
from prodata.engine.serialize import json_rows
from prodata.errors import InvalidInputError
from prodata.ingestion import detect, readers
from prodata.ingestion.options import ReadOptions

MAX_DIRECT_BYTES = 200 * 1024 * 1024
MAX_UNZIPPED_BYTES = 2 * 1024 * 1024 * 1024
MAX_ZIP_RATIO = 200
PREVIEW_ROWS = 50
_SUFFIX = {
    "csv": ".csv", "txt": ".csv", "tsv": ".csv", "xlsx": ".xlsx", "xls": ".xls", "xlsb": ".xlsb", "xlsm": ".xlsm",
    "parquet": ".parquet", "json": ".json", "ndjson": ".ndjson", "zip": ".zip",
}  # fmt: skip
_INNER = {".csv", ".txt", ".tsv", ".xlsx", ".xls", ".xlsb", ".xlsm", ".parquet", ".json", ".ndjson"}
# Ordem de preferência dentro de um ZIP: tabela de verdade antes de texto solto (que costuma ser leia-me).
_PREFER = {".csv": 0, ".parquet": 0, ".xlsx": 1, ".xls": 1, ".xlsb": 1, ".xlsm": 1, ".tsv": 2, ".json": 3,
           ".ndjson": 3, ".txt": 4}  # fmt: skip


class AcceptedFormat(BaseModel):
    """O que a pessoa viu e aceitou na prévia; a execução confere contra isto."""

    opcoes: dict[str, Any] = Field(default_factory=dict)
    membro: str = ""
    colunas: list[tuple[str, str]] = Field(default_factory=list)


class FormatChangedError(Exception):
    """O órgão mudou as colunas do arquivo: a caixa para e oferece Aceitar o novo formato."""

    def __init__(self, changes: list[str], new_format: AcceptedFormat) -> None:
        super().__init__("O órgão mudou o arquivo: " + "; ".join(changes) + ".")
        self.changes = changes
        self.new_format = new_format


def kind_of(dtype: pl.DataType) -> str:
    if dtype.is_integer():
        return "inteiro"
    if dtype.is_numeric():
        return "numero"
    if dtype.is_temporal():
        return "data"
    if dtype == pl.Boolean:
        return "logico"
    return "texto"


def signature(frame: pl.DataFrame) -> list[tuple[str, str]]:
    """Colunas e tipos. Coluna toda vazia fica "vazio": na prévia não dá para saber o tipo dela."""
    return [
        (name, "vazio" if frame.height and frame[name].null_count() == frame.height else kind_of(dtype))
        for name, dtype in frame.schema.items()
    ]


_KIND_WORDS = {"inteiro": "número", "numero": "número", "texto": "texto", "data": "data", "logico": "sim/não"}


def changes_between(old: list[tuple[str, str]], new: list[tuple[str, str]]) -> list[str]:
    """As mudanças em palavras. Inteiro e decimal são o mesmo tipo para a pessoa (não contam como mudança)."""
    before, after = dict(old), dict(new)
    out = [f"saiu a coluna {name}" for name in before if name not in after]
    out += [f"entrou a coluna {name}" for name in after if name not in before]
    for name, kind in before.items():
        if name not in after or "vazio" in (kind, after[name]):
            continue
        if _KIND_WORDS[kind] != _KIND_WORDS[after[name]]:
            out.append(f"a coluna {name} mudou de {_KIND_WORDS[kind]} para {_KIND_WORDS[after[name]]}")
    return out


# ------------------------------------------------------------------ arquivo no cache


def cache_file(root: Path, url: str, fmt: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    return root / "arquivos" / f"{digest}{_SUFFIX.get(fmt, '.bin')}"


def sniff(path: Path, declared: str) -> str:
    """O formato de verdade, pelos primeiros bytes: o rótulo do portal pode mentir (o IBAMA chama ZIP de CSV)."""
    with path.open("rb") as fh:
        head = fh.read(512)
    if head.startswith(b"PK\x03\x04"):
        # XLSX também é um ZIP por dentro: só é Excel se tiver a pasta de trabalho.
        try:
            with zipfile.ZipFile(path) as archive:
                names = set(archive.namelist())
        except zipfile.BadZipFile:
            raise InvalidInputError("O arquivo do portal está corrompido.") from None
        if "xl/workbook.xml" in names or "xl/workbook.bin" in names:
            return declared if declared in ("xlsx", "xlsm", "xlsb") else "xlsx"
        return "zip"
    if head.startswith(b"\x1f\x8b"):
        return "gzip"
    if head.startswith(b"%PDF"):
        raise InvalidInputError("O arquivo é um PDF, não uma tabela: abra no navegador.")
    lowered = head.lstrip(b"\xef\xbb\xbf \r\n\t").lower()
    if lowered.startswith((b"<!doctype html", b"<html")):
        raise InvalidInputError("O portal devolveu uma página da web em vez do arquivo: abra no navegador.")
    if head.startswith(b"PAR1"):
        return "parquet"
    return declared


def _gunzip(path: Path, declared: str) -> Path:
    import gzip

    inner = declared if declared not in ("zip", "gzip") else "csv"
    dest = path.with_name(path.stem + "-gz" + _SUFFIX.get(inner, ".csv"))
    written = 0
    with gzip.open(path, "rb") as src, dest.open("wb") as out:
        while chunk := src.read(1024 * 1024):
            written += len(chunk)
            if written > MAX_UNZIPPED_BYTES:
                out.close()
                dest.unlink(missing_ok=True)
                raise InvalidInputError("O arquivo compactado ficaria grande demais: recusado por segurança.")
            out.write(chunk)
    return dest


def fetch(client: CatalogClient, url: str, root: Path, fmt: str) -> tuple[Path, str]:
    """Baixa para o cache e devolve o arquivo e o formato de verdade (conferido pelos primeiros bytes)."""
    if fmt not in _SUFFIX:
        raise InvalidInputError(f"Formato {fmt!r}: o programa não lê arquivos assim.")
    dest = cache_file(root, url, fmt)
    client.download_to(url, dest, max_bytes=MAX_DIRECT_BYTES, timeout=180)
    actual = sniff(dest, fmt)
    if actual == "gzip":
        return _gunzip(dest, fmt), ("csv" if fmt in ("zip", "gzip") else fmt)
    if actual != fmt:
        right = dest.with_suffix(_SUFFIX[actual])
        dest.replace(right)
        return right, actual
    return dest, fmt


def zip_members(path: Path) -> list[str]:
    """Os arquivos legíveis dentro do ZIP, depois de conferir caminhos e tamanhos."""
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        raise InvalidInputError("O arquivo ZIP do portal está corrompido.") from None
    with archive:
        total = 0
        packed = max(path.stat().st_size, 1)
        readable: list[str] = []
        sizes: dict[str, int] = {}
        for info in archive.infolist():
            name = info.filename
            pure = PurePosixPath(name.replace("\\", "/"))
            if pure.is_absolute() or ".." in pure.parts or re.match(r"^[A-Za-z]:", name):
                raise InvalidInputError(f"O ZIP tem um caminho perigoso ({name!r}): recusado por segurança.")
            total += info.file_size
            if total > MAX_UNZIPPED_BYTES or total / packed > MAX_ZIP_RATIO:
                raise InvalidInputError("O ZIP descompactado ficaria grande demais: recusado por segurança.")
            if not info.is_dir() and pure.suffix.lower() in _INNER:
                readable.append(name)
                sizes[name] = info.file_size
    if not readable:
        raise InvalidInputError(
            "O ZIP não tem nenhum arquivo que o programa lê (CSV, Excel, Parquet ou JSON)."
        )
    return sorted(
        readable, key=lambda n: (_PREFER.get(PurePosixPath(n).suffix.lower(), 9), -sizes.get(n, 0), n)
    )


def extract(path: Path, member: str, root: Path) -> Path:
    members = zip_members(path)
    if member not in members:
        raise InvalidInputError(f"O ZIP não tem mais o arquivo {member!r}.")
    suffix = PurePosixPath(member.replace("\\", "/")).suffix.lower()
    suffix = ".csv" if suffix in (".txt", ".tsv") else suffix
    digest = hashlib.sha256(f"{path.name}/{member}".encode()).hexdigest()[:24]
    dest = root / "arquivos" / f"{digest}{suffix}"
    with zipfile.ZipFile(path) as archive, archive.open(member) as src, dest.open("wb") as out:
        written = 0
        while chunk := src.read(1024 * 1024):
            written += len(chunk)
            if written > MAX_UNZIPPED_BYTES:
                out.close()
                dest.unlink(missing_ok=True)
                raise InvalidInputError("O arquivo de dentro do ZIP é grande demais.")
            out.write(chunk)
    return dest


def _table_path(path: Path, fmt: str, member: str, root: Path) -> tuple[Path, list[str], str]:
    if fmt != "zip":
        return path, [], ""
    members = zip_members(path)
    chosen = member or members[0]
    return extract(path, chosen, root), members, chosen


def _options(options: dict[str, Any] | None) -> ReadOptions:
    return ReadOptions.model_validate(options or {})


def numbers_in_text(frame: pl.DataFrame) -> tuple[pl.DataFrame, list[str]]:
    """Colunas de texto que são, inteiras, números com milhar ou vírgula ("1.234,56") viram número.

    O leitor de CSV não entende o ponto de milhar, e quase todo arquivo de governo usa. A regra é a do programa
    (spec 048, RF-4836: formato decidido pela coluna, brasileiro no ambíguo), com uma trava a mais: só converte se
    **todo** valor preenchido virar número e pelo menos um tiver separador (código como "0012" fica texto).
    Devolve as colunas convertidas, para a prévia dizer quais foram.
    """
    changed: list[str] = []
    out = frame
    for name, dtype in frame.schema.items():
        if dtype != pl.String:
            continue
        text = frame[name].str.strip_chars()
        filled = text.filter(text.is_not_null() & (text != ""))
        if filled.is_empty() or not filled.str.contains(r"^(?:R\$\s*)?-?[\d.,]+$").all():
            continue
        if not filled.str.contains(r"[.,]").any() or filled.str.contains(r"^0\d").any():
            continue
        parsed = parse_number(text)
        if parsed.filter(text.is_not_null() & (text != "")).null_count():
            continue
        out = out.with_columns(parsed.alias(name))
        changed.append(name)
    return out, changed


_INTEGER = r"^-?\d+$"


def type_text_columns(frame: pl.DataFrame) -> tuple[pl.DataFrame, list[str]]:
    """Os tipos das colunas de um CSV lido todo como texto, decididos pela coluna inteira.

    O leitor comum transforma "0012" em 12: em dados de governo isso estraga CNPJ, CEP, código do IBGE e matrícula.
    Aqui: inteiro só se nenhum valor tem zero à esquerda nem 12 dígitos ou mais (identificador); número com milhar ou
    vírgula pela regra do programa; data só se todos os valores forem datas; o resto continua texto.
    """
    frame, converted = numbers_in_text(frame)
    out = frame
    for name, dtype in frame.schema.items():
        if dtype != pl.String:
            continue
        text = frame[name].str.strip_chars()
        filled = text.filter(text.is_not_null() & (text != ""))
        if filled.is_empty():
            continue
        if filled.str.contains(_INTEGER).all():
            digits = filled.str.replace("-", "")
            if filled.str.contains(r"^-?0\d").any() or (digits.str.len_chars() >= 12).any():
                continue  # identificador: fica texto, com os zeros
            out = out.with_columns(text.cast(pl.Int64, strict=False).alias(name))
            continue
        if filled.str.contains(r"\d").all() and filled.str.contains(r"[/-]").all():
            dates = parse_date(text)
            if dates.filter(text.is_not_null() & (text != "")).null_count() == 0:
                out = out.with_columns(dates.alias(name))
                converted.append(name)
    return out, converted


def _read_csv_as_text(path: Path, opts: ReadOptions, n_rows: int | None) -> pl.DataFrame:
    if opts.decimal == "," and opts.delimiter == ",":
        raise InvalidInputError("Decimal com vírgula exige um delimitador diferente de vírgula.")
    kwargs: dict[str, Any] = {
        "separator": opts.delimiter,
        "has_header": opts.has_header,
        "skip_rows": opts.skip_rows,
        "null_values": opts.null_tokens() or None,
        "infer_schema": False,
        "truncate_ragged_lines": True,
        "n_rows": n_rows,
    }
    if opts.encoding == "utf-8":
        frame = pl.read_csv(path, **kwargs)
    else:
        raw = path.read_bytes() if n_rows is None else detect.read_sample(path, readers.PREVIEW_BYTES)
        if n_rows is not None and len(raw) == readers.PREVIEW_BYTES:
            raw = raw[: raw.rfind(b"\n") + 1]
        frame = pl.read_csv(io.BytesIO(raw.decode(opts.encoding, errors="replace").encode("utf-8")), **kwargs)
    if opts.skip_columns:
        if opts.skip_columns >= frame.width:
            raise InvalidInputError(
                f"Pular {opts.skip_columns} coluna(s) não deixa nada: a tabela tem {frame.width}."
            )
        frame = frame.select(frame.columns[opts.skip_columns :])
    return frame


def _read(table: Path, opts: ReadOptions, n_rows: int | None = None) -> tuple[pl.DataFrame, list[str]]:
    """CSV: lido como texto e tipado pela coluna (``type_text_columns``); os outros formatos já trazem tipo."""
    if opts.format == "csv":
        try:
            raw = _read_csv_as_text(table, opts, n_rows)
        except (pl.exceptions.PolarsError, OSError, ValueError) as exc:
            raise InvalidInputError(f"Falha ao ler '{table.name}' como CSV: {exc}") from exc
        return type_text_columns(raw)
    return numbers_in_text(readers.read_table(table, opts, n_rows=n_rows))


# ------------------------------------------------------------------ prévia e leitura


def preview(
    client: CatalogClient,
    url: str,
    root: Path,
    fmt: str,
    *,
    options: dict[str, Any] | None = None,
    member: str = "",
) -> dict[str, Any]:
    """A prévia obrigatória (RF-4938): como o arquivo foi lido, com as opções detectadas para a pessoa trocar."""
    path, fmt = fetch(client, url, root, fmt)
    table, members, chosen = _table_path(path, fmt, member, root)
    resolved = readers.resolve_options(table, _options(options))
    frame, converted = _read(table, resolved, PREVIEW_ROWS)
    accepted = AcceptedFormat(opcoes=resolved.model_dump(), membro=chosen, colunas=signature(frame))
    return {
        "opcoes": resolved.model_dump(),
        "membros": members,
        "membro": chosen,
        "colunas": schema_of(frame),
        "linhas": json_rows(frame),
        "linhas_total": readers.count_rows(table, resolved),
        "tamanho": path.stat().st_size,
        "formato": fmt,
        "formato_aceito": accepted.model_dump(),
        # "valor_pago: número no padrão brasileiro (1.234,56)": a pessoa confere na prévia.
        "numeros_convertidos": converted,
    }


def read(client: CatalogClient, url: str, root: Path, fmt: str, accepted: AcceptedFormat) -> ReadResult:
    """Lê o arquivo inteiro com o formato aceito e confere as colunas (RF-4938)."""
    path, fmt = fetch(client, url, root, fmt)
    table, _members, chosen = _table_path(path, fmt, accepted.membro, root)
    opts = _options(accepted.opcoes)
    try:
        frame, _converted = _read(table, readers.resolve_options(table, opts))
        frame, warnings = _keep_accepted_types(frame, accepted)
    except InvalidInputError as exc:
        raise CatalogError(f"O arquivo não pôde ser lido com o formato aceito: {exc}", "resposta") from None
    now = signature(frame)
    if accepted.colunas:
        changes = changes_between(accepted.colunas, now)
        if changes:
            raise FormatChangedError(
                changes, AcceptedFormat(opcoes=opts.model_dump(), membro=chosen, colunas=now)
            )
    return ReadResult(frame, [url], warnings, info={"arquivo": chosen or path.name})


def _keep_accepted_types(frame: pl.DataFrame, accepted: AcceptedFormat) -> tuple[pl.DataFrame, list[str]]:
    """Coluna aceita como número, inteiro ou data que veio como texto (um "N/D" ou "00/00/0000" depois das linhas da
    prévia): converte, e o que não serve fica vazio, com o aviso e a contagem, como no Select. Não é mudança de
    formato do órgão."""
    warnings: list[str] = []
    words = {"numero": "número", "inteiro": "número inteiro", "data": "data"}
    for name, kind in accepted.colunas:
        if kind not in words or name not in frame.columns or frame.schema[name] != pl.String:
            continue
        text = frame[name].str.strip_chars()
        if kind == "data":
            parsed = parse_date(text)
        elif kind == "inteiro":
            parsed = text.cast(pl.Int64, strict=False)
        else:
            parsed = parse_number(text)
        lost = int((text.is_not_null() & (text != "") & parsed.is_null()).sum())
        frame = frame.with_columns(parsed.alias(name))
        if lost:
            warnings.append(f"{lost} valor(es) de {name} não são {words[kind]} e ficaram vazios.")
    return frame, warnings
