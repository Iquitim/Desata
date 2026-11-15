"""Entradas sem fonte cadastrada (spec 033): linhas geradas e a caixa antiga de pasta.

Desde a spec 035, a pasta é cadastrada na aba Dados e lida pelo Input Data. A caixa Input Folder fica fora
da paleta, só para os fluxos que já a usam continuarem executando.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

import polars as pl
from pydantic import Field

from prodata.brand import marca
from prodata.engine.sql.fragment import Fragment, SqlContext, lit, q, sql_for
from prodata.errors import InvalidInputError, NotFoundError
from prodata.forms import ui
from prodata.ingestion.folders import files_signature, folder_files, odd_warning, read_folder
from prodata.ingestion.options import ReadOptions
from prodata.nodes.base import NodeContext, NodeOutput, Port, ToolConfig, tool

MAX_FILES = 500
MAX_ROWS = 5_000_000

# ------------------------------------------------------------------ Input Folder


class InputFolderConfig(ReadOptions, ToolConfig):
    folder: str = Field(
        "",
        title="Pasta",
        description=f"Caminho completo. O {marca().nome} só lê: nunca grava, move ou apaga o que está nela.",
        json_schema_extra=ui(widget="folder", placeholder="D:\\Fechamento\\2026-10"),
    )
    pattern: str = Field(
        "*.xlsx",
        title="Arquivos",
        description="Padrão do nome: * vale qualquer trecho e ? um caractere. Ex.: vendas_*.xlsx",
        json_schema_extra=ui(placeholder="vendas_*.xlsx"),
    )
    file_column: str = Field(
        "arquivo",
        title="Coluna com o nome do arquivo",
        description="Vazio = não criar. Serve para saber de qual arquivo veio cada linha.",
    )
    limit: int = Field(0, ge=0, title="Limite de linhas por arquivo", description="0 = todas as linhas.")


def _folder_signature(_ctx: NodeContext, cfg: InputFolderConfig) -> str:
    try:
        return files_signature(folder_files(cfg.folder, cfg.pattern))
    except InvalidInputError, NotFoundError:
        return ""


@tool(
    type="io.input_folder",
    explainer="input_folder",
    name="Input Folder",
    category="inout",
    icon="directory",
    description="(Antiga) Lê os arquivos de uma pasta que casam com um padrão. Cadastre a pasta na vista Dados e use o Input Data.",
    config=InputFolderConfig,
    inputs=[],
    outputs=[Port("out", "O", "Dados")],
    annotate=lambda c: c.pattern or "Escolha a pasta",
    fingerprint=_folder_signature,
    hidden=True,
)
def input_folder(ctx: NodeContext, cfg: InputFolderConfig) -> NodeOutput:
    files = folder_files(cfg.folder, cfg.pattern)
    if not files:
        raise InvalidInputError(
            f"Nenhum arquivo em {cfg.folder.strip()} casa com '{cfg.pattern.strip() or '*'}'."
        )
    table, odd = read_folder(files, cfg, cfg.file_column, limit=cfg.limit or None, report=ctx.report)
    extra: dict[str, Any] = {"folder_files": [p.name for p in files], "source_read_at": _now()}
    if odd:
        extra["warnings"] = [odd_warning(odd, files[0].name)]
    return NodeOutput(tables={"out": table}, extra=extra)


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


# ------------------------------------------------------------------ Generate Rows

_WEEKDAYS = [
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
]
_MONTHS = [
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
]
_STEP = {"day": "1d", "week": "1w", "month": "1mo", "quarter": "1q", "year": "1y"}
CALENDAR_COLUMNS = (
    "ano",
    "mes",
    "dia",
    "trimestre",
    "ano_mes",
    "nome_mes",
    "dia_semana",
    "nome_dia",
    "fim_de_semana",
    "ultimo_dia_do_mes",
)


def check_calendar_name(name: str, calendar: bool) -> None:
    """Com as colunas de calendário, a coluna de datas não pode ter o nome de uma delas: seria sobrescrita."""
    if calendar and name in CALENDAR_COLUMNS:
        raise InvalidInputError(
            f"'{name}' é o nome de uma coluna do calendário: escolha outro nome para a coluna de datas."
        )


class GenerateRowsConfig(ToolConfig):
    mode: Literal["dates", "numbers"] = Field(
        "dates",
        title="Gerar",
        json_schema_extra=ui(labels={"dates": "Datas (calendário)", "numbers": "Números em sequência"}),
    )
    column: str = Field("data", title="Nome da coluna")
    start_date: str = Field(
        "",
        title="De",
        description="2026-01-01 ou 01/01/2026. Aceita constante, como [#mes_referencia].",
        json_schema_extra=ui(show_if={"mode": ["dates"]}, placeholder="2026-01-01"),
    )
    end_date: str = Field(
        "",
        title="Até",
        description="Vazio = hoje.",
        json_schema_extra=ui(show_if={"mode": ["dates"]}, placeholder="2026-12-31"),
    )
    every: Literal["day", "week", "month", "quarter", "year"] = Field(
        "day",
        title="Uma linha por",
        json_schema_extra=ui(
            show_if={"mode": ["dates"]},
            labels={"day": "Dia", "week": "Semana", "month": "Mês", "quarter": "Trimestre", "year": "Ano"},
        ),
    )
    calendar: bool = Field(
        True,
        title="Colunas de calendário",
        description="Ano, mês, dia, trimestre, dia da semana, fim de semana e ano-mês.",
        json_schema_extra=ui(show_if={"mode": ["dates"]}),
    )
    start: float = Field(1, title="De", json_schema_extra=ui(show_if={"mode": ["numbers"]}, step=1))
    end: float = Field(10, title="Até", json_schema_extra=ui(show_if={"mode": ["numbers"]}, step=1))
    step: float = Field(
        1, title="De quanto em quanto", json_schema_extra=ui(show_if={"mode": ["numbers"]}, step=1)
    )


def parse_day(text: str, what: str) -> date:
    raw = text.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise InvalidInputError(f"'{raw}' não é uma data em {what}: use 2026-01-31 ou 31/01/2026.")


def _dates(cfg: GenerateRowsConfig, name: str) -> pl.DataFrame:
    if not cfg.start_date.strip():
        raise InvalidInputError("Informe a data inicial em 'De'.")
    check_calendar_name(name, cfg.calendar)
    start = parse_day(cfg.start_date, "'De'")
    end = parse_day(cfg.end_date, "'Até'") if cfg.end_date.strip() else date.today()
    if end < start:
        raise InvalidInputError("A data final é anterior à inicial.")
    if cfg.every == "day" and (end - start).days + 1 > MAX_ROWS:
        raise InvalidInputError(f"O intervalo passa de {MAX_ROWS:,} linhas.".replace(",", "."))
    days = pl.date_range(start, end, interval=_STEP[cfg.every], eager=True).alias(name)
    table = pl.DataFrame([days])
    if not cfg.calendar:
        return table
    d = pl.col(name)
    return table.with_columns(
        d.dt.year().cast(pl.Int64).alias("ano"),
        d.dt.month().cast(pl.Int64).alias("mes"),
        d.dt.day().cast(pl.Int64).alias("dia"),
        d.dt.quarter().cast(pl.Int64).alias("trimestre"),
        d.dt.strftime("%Y-%m").alias("ano_mes"),
        d.dt.month()
        .replace_strict(dict(enumerate(_MONTHS, start=1)), return_dtype=pl.String)
        .alias("nome_mes"),
        d.dt.weekday().cast(pl.Int64).alias("dia_semana"),
        d.dt.weekday()
        .replace_strict(dict(enumerate(_WEEKDAYS, start=1)), return_dtype=pl.String)
        .alias("nome_dia"),
        (d.dt.weekday() >= 6).alias("fim_de_semana"),
        (d == d.dt.month_end()).alias("ultimo_dia_do_mes"),
    )


def _numbers(cfg: GenerateRowsConfig, name: str) -> pl.DataFrame:
    if cfg.step == 0:
        raise InvalidInputError("O passo não pode ser zero.")
    count = int((cfg.end - cfg.start) / cfg.step) + 1
    if count < 1:
        raise InvalidInputError("Com esse passo, a sequência nunca chega ao valor final.")
    if count > MAX_ROWS:
        raise InvalidInputError(f"A sequência passa de {MAX_ROWS:,} linhas.".replace(",", "."))
    whole = all(float(v).is_integer() for v in (cfg.start, cfg.end, cfg.step))
    values = [cfg.start + i * cfg.step for i in range(count)]
    return pl.DataFrame({name: [int(v) for v in values] if whole else values})


@tool(
    type="io.generate_rows",
    explainer="generate_rows",
    name="Generate Rows",
    category="inout",
    icon="list",
    description="Cria linhas sem ler arquivo: um calendário entre duas datas ou números em sequência.",
    config=GenerateRowsConfig,
    inputs=[],
    outputs=[Port("out", "O", "Linhas")],
    annotate=lambda c: (
        f"{c.start_date or '?'} a {c.end_date or 'hoje'}" if c.mode == "dates" else f"{c.start:g} a {c.end:g}"
    ),
    # Sem data final, o calendário vai até hoje: muda quando o dia muda.
    fingerprint=lambda _ctx, c: (
        date.today().isoformat() if c.mode == "dates" and not c.end_date.strip() else ""
    ),
)
def generate_rows(ctx: NodeContext, cfg: GenerateRowsConfig) -> NodeOutput:
    name = cfg.column.strip() or ("data" if cfg.mode == "dates" else "numero")
    return NodeOutput(tables={"out": _dates(cfg, name) if cfg.mode == "dates" else _numbers(cfg, name)})


# ------------------------------------------------------------------ Generate Rows em SQL (spec 033)

# Cada data sai da inicial mais N passos (31/01 + 1 mês = 28/02, + 2 meses = 31/03), como o motor.
_SQL_STEP = {
    "day": ("day", 1),
    "week": ("day", 7),
    "month": ("month", 1),
    "quarter": ("month", 3),
    "year": ("year", 1),
}


def _sql_day(text: str, what: str) -> str:
    return f"DATE {lit(parse_day(text, what).isoformat())}"


@sql_for("io.generate_rows")
def generate_rows_sql(_ctx: SqlContext, cfg: GenerateRowsConfig) -> dict[str, Fragment]:
    name = cfg.column.strip() or ("data" if cfg.mode == "dates" else "numero")
    if cfg.mode == "numbers":
        table = _numbers(cfg, name)  # mesmas validações e a mesma contagem do motor
        count = table.height
        whole = table.schema[name] == pl.Int64
        value = (
            f"CAST({lit(int(cfg.start))} + i * {lit(int(cfg.step))} AS BIGINT)"
            if whole
            else f"CAST({lit(float(cfg.start))} AS DOUBLE) + i * CAST({lit(float(cfg.step))} AS DOUBLE)"
        )
        sql = f"SELECT {value} AS {q(name)}\nFROM range({count}) AS t(i)"
        return {"out": Fragment(sql, f"Gera {count} números em sequência")}
    if not cfg.start_date.strip():
        raise ValueError("Informe a data inicial em 'De'.")
    check_calendar_name(name, cfg.calendar)
    start = _sql_day(cfg.start_date, "'De'")
    notes = []
    if cfg.end_date.strip():
        end = _sql_day(cfg.end_date, "'Até'")
        if parse_day(cfg.end_date, "'Até'") < parse_day(cfg.start_date, "'De'"):
            raise ValueError("A data final é anterior à inicial.")
    else:
        end = "CURRENT_DATE"
        notes.append(
            "Sem data final, o calendário vai até hoje: o resultado muda conforme o dia em que roda."
        )
    unit, size = _SQL_STEP[cfg.every]
    steps = f"date_diff('{unit}', {start}, {end})" + (f" // {size}" if size > 1 else "")
    day = f"CAST({start} + to_{unit}s(CAST(i * {size} AS INTEGER)) AS DATE)"
    base = f"SELECT {day} AS {q(name)}\nFROM range({steps} + 1) AS t(i)\nWHERE {day} <= {end}"
    if not cfg.calendar:
        return {"out": Fragment(base, "Gera um calendário", notes)}
    d = q(name)
    months = "[" + ", ".join(lit(m) for m in _MONTHS) + "]"
    weekdays = "[" + ", ".join(lit(w) for w in _WEEKDAYS) + "]"
    cols = [
        f"CAST(year({d}) AS BIGINT) AS ano",
        f"CAST(month({d}) AS BIGINT) AS mes",
        f"CAST(day({d}) AS BIGINT) AS dia",
        f"CAST(quarter({d}) AS BIGINT) AS trimestre",
        f"strftime({d}, '%Y-%m') AS ano_mes",
        f"{months}[month({d})] AS nome_mes",
        f"CAST(isodow({d}) AS BIGINT) AS dia_semana",
        f"{weekdays}[isodow({d})] AS nome_dia",
        f"isodow({d}) >= 6 AS fim_de_semana",
        f"{d} = last_day({d}) AS ultimo_dia_do_mes",
    ]
    sql = "SELECT\n  " + ",\n  ".join([d, *cols]) + f"\nFROM ({base}) AS dias"
    return {"out": Fragment(sql, "Gera um calendário com as colunas de data", notes)}
