"""Spec 040: data digitada de outro jeito nunca dá resultado errado em silêncio (Filter básico, motor e SQL)."""

from datetime import date, datetime
from pathlib import Path
from typing import Any

import duckdb
import polars as pl
import pytest

from prodata.engine.dates import parse_user_date
from prodata.engine.sql.fragment import SQL_REGISTRY, SqlContext, SqlInput, kind_of
from prodata.engine.sql.macros import install_all
from prodata.engine.sql.verify import SAME, compare
from prodata.ingestion import DatasetStore
from prodata.nodes import REGISTRY, NodeContext

DF = pl.DataFrame(
    {
        "dia": [date(2026, 7, 8), date(2026, 8, 7), date(2026, 7, 1), None],
        "quando": [
            datetime(2026, 7, 8, 9, 30),
            datetime(2026, 8, 7, 0, 0),
            datetime(2026, 7, 1, 23, 59),
            None,
        ],
        "n": [1, 2, 3, 4],
    }
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026-07-08", date(2026, 7, 8)),
        ("'2026-07-08'", date(2026, 7, 8)),
        ('"07/08/2026"', date(2026, 8, 7)),  # dia/mês, como no Brasil
        ("7/8/2026", date(2026, 8, 7)),
        ("07-08-2026", date(2026, 8, 7)),
        (" 2026-7-8 ", date(2026, 7, 8)),
        ("31/02/2026", None),
        ("jul/26", None),
        ("NF 07/08", None),
        ("", None),
    ],
)
def test_reads_the_date_people_type(text: str, expected: date | None) -> None:
    assert parse_user_date(text) == expected


def _run(store: DatasetStore, tmp_path: Path, **config: Any) -> pl.DataFrame:
    spec = REGISTRY["prep.filter"]
    cfg = spec.config.model_validate({"mode": "simple", **config})
    return spec.run(NodeContext({"in": DF}, {}, store, tmp_path), cfg).tables["T"]


def _sql(**config: Any) -> pl.DataFrame:
    cfg = REGISTRY["prep.filter"].config.model_validate({"mode": "simple", **config})
    with duckdb.connect(":memory:") as con:
        install_all(con)
        con.register("entrada", DF)
        kinds = {str(r[0]): kind_of(str(r[1])) for r in con.execute("DESCRIBE entrada").fetchall()}
        ctx = SqlContext({"in": SqlInput("entrada", list(DF.columns), kinds)})
        return con.sql(SQL_REGISTRY["prep.filter"](ctx, cfg)["T"].sql).pl()


@pytest.mark.parametrize("value", ["2026-07-08", "08/07/2026", "'2026-07-08'"])
@pytest.mark.parametrize("column", ["dia", "quando"])
def test_filter_compares_dates_as_dates(store: DatasetStore, tmp_path: Path, column: str, value: str) -> None:
    """CA-01/CA-02: o mesmo dia, escrito de jeitos diferentes, filtra as mesmas linhas; o SQL dá o mesmo."""
    equal = _run(store, tmp_path, column=column, operator="==", value=value)
    assert equal["n"].to_list() == [1]
    after = _run(store, tmp_path, column=column, operator=">", value=value)
    assert after["n"].to_list() == [2]  # 7 de agosto; texto "08/07/2026" contra "2026-..." daria outra coisa
    for op in ("==", ">", "<="):
        engine = _run(store, tmp_path, column=column, operator=op, value=value)
        assert compare(_sql(column=column, operator=op, value=value), engine).state == SAME, (
            column,
            op,
            value,
        )


def test_value_that_is_not_a_date_says_so(store: DatasetStore, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="não é uma data"):
        _run(store, tmp_path, column="dia", operator="==", value="jul/26")
    with pytest.raises(ValueError, match="não é uma data"):
        _sql(column="dia", operator="==", value="31/02/2026")


def test_filter_value_field_offers_the_calendar() -> None:
    field = next(f for f in REGISTRY["prep.filter"].describe()["config_fields"] if f["name"] == "value")
    assert field["widget"] == "filter_value" and field["source"] == "column"


def test_quick_filter_of_the_results_compares_dates_as_dates() -> None:
    """RF-4006: o filtro rápido da tabela, no servidor, lê a data nos dois formatos e compara como data."""
    from prodata.engine.results import ExploreFilter, apply_filters
    from prodata.errors import InvalidInputError

    for value in ("2026-07-08", "08/07/2026"):
        out = apply_filters(DF, [ExploreFilter(column="dia", op="gt", value=value)])
        assert out["n"].to_list() == [2]
        out = apply_filters(DF, [ExploreFilter(column="quando", op="eq", value=value)])
        assert out["n"].to_list() == [1]
    with pytest.raises(InvalidInputError, match="não é uma data"):
        apply_filters(DF, [ExploreFilter(column="dia", op="eq", value="amanhã")])


def test_quality_date_range_takes_both_formats(store: DatasetStore, tmp_path: Path) -> None:
    spec = REGISTRY["prep.data_quality"]
    for low, high in (("2026-07-02", "2026-08-01"), ("02/07/2026", "01/08/2026")):
        cfg = spec.config.model_validate(
            {"rules": [{"kind": "date", "column": "dia", "date_min": low, "date_max": high}]}
        )
        out = spec.run(NodeContext({"in": DF}, {}, store, tmp_path), cfg).tables
        # 7/8 e 1/7 ficam fora do período; 8/7 está dentro, e o vazio passa nas regras de formato
        assert sorted(out["F"]["n"].to_list()) == [2, 3]
    field = next(f for f in spec.describe()["config_fields"][0]["item_fields"] if f["name"] == "date_min")
    assert field["widget"] == "date"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("08/07/2026 14:30", datetime(2026, 7, 8, 14, 30)),
        ("'2026-07-08T14:30:15'", datetime(2026, 7, 8, 14, 30, 15)),
        ("8/7/26 9:05", datetime(2026, 7, 8, 9, 5)),
        ("08/07/2026", date(2026, 7, 8)),
        ("8/7/26", date(2026, 7, 8)),  # ano com dois dígitos (RF-4008)
        ("08/07/2026 25:00", None),
    ],
)
def test_reads_date_and_time(text: str, expected: object) -> None:
    from prodata.engine.dates import parse_user_moment

    assert parse_user_moment(text) == expected


def test_datetime_filter_with_and_without_time(store: DatasetStore, tmp_path: Path) -> None:
    """CA-08: sem hora, o dia inteiro; com hora, o instante. O SQL dá o mesmo."""
    day = _run(store, tmp_path, column="quando", operator="==", value="08/07/2026")
    assert day["n"].to_list() == [1]
    exact = _run(store, tmp_path, column="quando", operator="==", value="08/07/2026 09:30")
    assert exact["n"].to_list() == [1]
    none = _run(store, tmp_path, column="quando", operator="==", value="08/07/2026 09:31")
    assert none["n"].to_list() == []
    for value in ("08/07/2026 09:30", "2026-07-01 23:00"):
        for op in ("==", ">", "<="):
            engine = _run(store, tmp_path, column="quando", operator=op, value=value)
            assert compare(_sql(column="quando", operator=op, value=value), engine).state == SAME, (op, value)


def test_quick_filter_with_time() -> None:
    from prodata.engine.results import ExploreFilter, apply_filters

    out = apply_filters(DF, [ExploreFilter(column="quando", op="ge", value="2026-07-08 09:30")])
    assert out["n"].to_list() == [1, 2]
    out = apply_filters(DF, [ExploreFilter(column="quando", op="gt", value="2026-07-08")])  # depois do dia 8
    assert out["n"].to_list() == [2]


def test_todatetime_in_a_formula_runs_in_the_engine_and_in_sql(store: DatasetStore, tmp_path: Path) -> None:
    spec = REGISTRY["prep.formula"]
    cfg = spec.config.model_validate(
        {
            "formulas": [
                {
                    "column": "depois",
                    "expression": "[quando] >= ToDateTime('2026-07-08 09:30:00')",
                    "type": "Auto",
                }
            ]
        }
    )
    engine = spec.run(NodeContext({"in": DF}, {}, store, tmp_path), cfg).tables["out"]
    assert engine["depois"].to_list() == [True, True, False, None]
    with duckdb.connect(":memory:") as con:
        install_all(con)
        con.register("entrada", DF)
        kinds = {str(r[0]): kind_of(str(r[1])) for r in con.execute("DESCRIBE entrada").fetchall()}
        sql = SQL_REGISTRY["prep.formula"](
            SqlContext({"in": SqlInput("entrada", list(DF.columns), kinds)}), cfg
        )["out"].sql
        assert compare(con.sql(sql).pl(), engine).state == SAME
