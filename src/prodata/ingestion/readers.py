"""Leitores por formato. ``read_table`` é usado tanto pelo nó Input Data quanto pelo preview."""

from __future__ import annotations

import io
from collections.abc import Callable
from pathlib import Path
from typing import Any

import fastexcel
import polars as pl

from prodata.engine.profiling import schema_of
from prodata.engine.serialize import json_rows
from prodata.errors import InvalidInputError
from prodata.ingestion import detect
from prodata.ingestion.options import ReadOptions

PREVIEW_BYTES = 8 * 1024 * 1024
# Acima disso, contar linhas de um CSV não-UTF-8 exigiria reencodar o arquivo inteiro.
COUNT_REENCODE_MAX_BYTES = 50 * 1024 * 1024


def resolve_options(path: Path, options: ReadOptions) -> ReadOptions:
    """Substitui todos os valores ``auto`` pelo que foi detectado no arquivo."""
    fmt = detect.detect_format(path) if options.format == "auto" else options.format
    resolved = options.model_copy(update={"format": fmt})
    if fmt != "csv":
        return resolved

    sample = detect.read_sample(path)
    encoding = detect.detect_encoding(sample) if options.encoding == "auto" else options.encoding
    text = sample.decode(encoding, errors="replace")
    # Título e linhas puladas não entram na detecção de delimitador e decimal.
    if options.skip_rows:
        text = "\n".join(text.splitlines()[options.skip_rows :])
    delimiter = detect.sniff_delimiter(text) if options.delimiter == "auto" else options.delimiter
    decimal = detect.sniff_decimal(text, delimiter) if options.decimal == "auto" else options.decimal
    return resolved.model_copy(update={"encoding": encoding, "delimiter": delimiter, "decimal": decimal})


def read_table(path: Path, options: ReadOptions, n_rows: int | None = None) -> pl.DataFrame:
    return read_table_noted(path, options, n_rows)[0]


def read_table_noted(
    path: Path, options: ReadOptions, n_rows: int | None = None
) -> tuple[pl.DataFrame, list[str]]:
    """Como ``read_table``, e as notas da leitura para a caixa mostrar (colunas protegidas como texto)."""
    opts = resolve_options(path, options)
    notes: list[str] = []
    try:
        if opts.format == "csv":
            df = _read_csv(path, opts, n_rows, notes)
        else:
            df = _READERS[opts.format](path, opts, n_rows)
    except (pl.exceptions.PolarsError, fastexcel.FastExcelError, OSError, ValueError) as exc:
        raise InvalidInputError(f"Falha ao ler '{path.name}' como {opts.format}: {exc}") from exc
    return _skip_columns(df, opts), notes


def _skip_columns(df: pl.DataFrame, opts: ReadOptions) -> pl.DataFrame:
    """Descarta as primeiras colunas da tabela lida (spec 011)."""
    if not opts.skip_columns or opts.format not in ("csv", "excel"):
        return df
    if opts.skip_columns >= df.width:
        raise InvalidInputError(
            f"Pular {opts.skip_columns} coluna(s) não deixa nada: a tabela lida tem {df.width}."
        )
    return df.select(df.columns[opts.skip_columns :])


def inspect_file(path: Path, options: ReadOptions, rows: int = 50) -> dict[str, Any]:
    opts = resolve_options(path, options)
    df = read_table(path, opts, n_rows=rows)
    return {
        "name": path.name,
        "options": opts.model_dump(),
        "sheets": excel_sheets(path) if opts.format == "excel" else [],
        "columns": schema_of(df),
        "rows": json_rows(df.head(rows)),
        "row_count": count_rows(path, opts),
    }


def excel_sheets(path: Path) -> list[str]:
    return list(fastexcel.read_excel(path).sheet_names)


def count_rows(path: Path, opts: ReadOptions) -> int | None:
    """Conta linhas sem materializar a tabela inteira, quando o formato permite."""
    try:
        match opts.format:
            case "parquet":
                return int(pl.scan_parquet(path).select(pl.len()).collect().item())
            case "arrow":
                return int(pl.scan_ipc(path).select(pl.len()).collect().item())
            case "excel":
                return int(_load_sheet(path, opts, None).total_height)
            case "csv" if opts.encoding in ("utf-8", "utf-8-sig"):
                return int(pl.scan_csv(path, **_csv_kwargs(opts)).select(pl.len()).collect().item())
            case "csv" if path.stat().st_size <= COUNT_REENCODE_MAX_BYTES:
                return _read_csv(path, opts, None).height
            case _:
                return None
    except pl.exceptions.PolarsError, fastexcel.FastExcelError, OSError:
        return None


def _csv_kwargs(opts: ReadOptions) -> dict[str, Any]:
    return {
        "separator": opts.delimiter,
        "has_header": opts.has_header,
        "skip_rows": opts.skip_rows,
        "null_values": opts.null_tokens() or None,
        "infer_schema_length": opts.infer_schema_rows or None,
        "try_parse_dates": opts.parse_dates,
        "decimal_comma": opts.decimal == ",",
        "truncate_ragged_lines": True,
    }


# Identificador: só dígitos, com zero à esquerda ou com 12 dígitos ou mais (CNPJ, CEP, código do IBGE, matrícula).
IDENTIFIER_DIGITS = 12
_LEADING_ZERO = r"^\s*-?0\d"


def identifier_example(text: pl.Series) -> str | None:
    """Um valor que mostra por que a coluna é identificador (zero à esquerda ou dígitos demais), ou None."""
    filled = text.str.strip_chars().drop_nulls()
    filled = filled.filter(filled != "")
    if filled.is_empty() or not filled.str.contains(r"^-?\d+$").all():
        return None
    hit = filled.filter(filled.str.contains(_LEADING_ZERO) | (filled.str.len_chars() >= IDENTIFIER_DIGITS))
    return str(hit[0]) if hit.len() else None


def _read_csv(
    path: Path, opts: ReadOptions, n_rows: int | None, notes: list[str] | None = None
) -> pl.DataFrame:
    """Lê o CSV preservando os zeros à esquerda (spec 049, RF-4995).

    O leitor decide os tipos pelas primeiras linhas e transformaria "0012" em 12. Toda coluna que a amostra diz ser
    inteira é lida como texto e conferida **no arquivo inteiro**: com um valor de zero à esquerda ou com 12 dígitos
    ou mais, fica texto (e a nota diz qual); senão, vira inteiro como sempre foi.
    """
    if opts.decimal == "," and opts.delimiter == ",":
        raise InvalidInputError("Decimal com vírgula exige um delimitador diferente de vírgula.")
    kwargs = _csv_kwargs(opts)
    if opts.encoding == "utf-8":
        source: Path | bytes = path
    else:
        # Polars lê apenas UTF-8: decodifica e reencoda em memória.
        raw = detect.read_sample(path, PREVIEW_BYTES) if n_rows is not None else path.read_bytes()
        if n_rows is not None and len(raw) == PREVIEW_BYTES:
            raw = raw[: raw.rfind(b"\n") + 1]
        source = raw.decode(opts.encoding, errors="replace").encode("utf-8")

    def read(**extra: Any) -> pl.DataFrame:
        data = io.BytesIO(source) if isinstance(source, bytes) else source
        return pl.read_csv(data, **kwargs, **extra)

    sample_rows = opts.infer_schema_rows or None
    if n_rows is not None:
        sample_rows = min(n_rows, sample_rows) if sample_rows else n_rows
    integers = [c for c, t in read(n_rows=sample_rows).schema.items() if t.is_integer()]
    if not integers:
        return read(n_rows=n_rows)
    df = read(n_rows=n_rows, schema_overrides=dict.fromkeys(integers, pl.String))
    protected: list[str] = []
    casts = []
    for name in integers:
        example = identifier_example(df[name])
        if example is not None:
            protected.append(f"{name} (ex.: {example})")
        else:
            casts.append(pl.col(name).str.strip_chars().cast(pl.Int64, strict=False))
    if casts:
        df = df.with_columns(casts)
    if protected and notes is not None:
        notes.append(
            f"Lida(s) como texto para manter os zeros à esquerda e os códigos longos: {', '.join(protected)}."
        )
    return df


def _load_sheet(path: Path, opts: ReadOptions, n_rows: int | None) -> fastexcel.ExcelSheet:
    reader = fastexcel.read_excel(path)
    sheet: int | str = opts.sheet or 0
    if opts.has_header:
        return reader.load_sheet(sheet, header_row=opts.skip_rows, n_rows=n_rows)
    return reader.load_sheet(sheet, header_row=None, skip_rows=opts.skip_rows or None, n_rows=n_rows)


def _read_excel(path: Path, opts: ReadOptions, n_rows: int | None) -> pl.DataFrame:
    return _load_sheet(path, opts, n_rows).to_polars()


def _read_parquet(path: Path, opts: ReadOptions, n_rows: int | None) -> pl.DataFrame:
    return pl.read_parquet(path, n_rows=n_rows)


def _read_arrow(path: Path, opts: ReadOptions, n_rows: int | None) -> pl.DataFrame:
    return pl.read_ipc(path, n_rows=n_rows)


def _read_json(path: Path, opts: ReadOptions, n_rows: int | None) -> pl.DataFrame:
    df = pl.read_json(path, infer_schema_length=opts.infer_schema_rows or None)
    return df.head(n_rows) if n_rows is not None else df


def _read_ndjson(path: Path, opts: ReadOptions, n_rows: int | None) -> pl.DataFrame:
    return pl.read_ndjson(path, n_rows=n_rows, infer_schema_length=opts.infer_schema_rows or None)


_READERS: dict[str, Callable[[Path, ReadOptions, int | None], pl.DataFrame]] = {
    "csv": _read_csv,
    "excel": _read_excel,
    "parquet": _read_parquet,
    "arrow": _read_arrow,
    "json": _read_json,
    "ndjson": _read_ndjson,
}
