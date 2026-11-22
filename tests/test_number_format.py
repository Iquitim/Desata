"""Número em texto: brasileiro por padrão, estrangeiro reconhecido pela coluna (spec 048, RF-4836)."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from prodata.engine.cleaning import recommend
from prodata.engine.convert import convert, number_format_of
from prodata.ingestion import DatasetStore
from test_sql_equivalence import assert_same, run_both

BR = pl.Series("v", ["1.234,56", "12,5", "1.200", "R$ 1.500,00", "3"])
US = pl.Series("v", ["1,234.56", "12.5", "1,200", "$1,500.00".replace("$", ""), "3.75"])
AMBIGUOUS = pl.Series("v", ["1.200", "2.500", "30"])


def test_brazilian_column() -> None:
    assert number_format_of(BR) == "br"
    assert convert(BR, pl.Float64).series.to_list() == [1234.56, 12.5, 1200.0, 1500.0, 3.0]


def test_american_column_is_recognized() -> None:
    result = convert(US, pl.Float64)
    assert result.number_format == "us" and result.series.to_list() == [1234.56, 12.5, 1200.0, 1500.0, 3.75]


def test_ambiguous_column_stays_brazilian() -> None:
    assert number_format_of(AMBIGUOUS) == "br"
    assert convert(AMBIGUOUS, pl.Float64).series.to_list() == [1200.0, 2500.0, 30.0]


def test_forced_format_wins() -> None:
    assert convert(AMBIGUOUS, pl.Float64, "us").series.to_list() == [1.2, 2.5, 30.0]
    assert convert(pl.Series("v", ["3.75"]), pl.Float64, "br").series.to_list() == [375.0]


def test_mixed_column_goes_with_the_majority() -> None:
    mixed = pl.Series("v", ["1,234.56", "9.99", "12,5"])
    assert number_format_of(mixed) == "us"


def test_select_warns_when_reading_american(store: DatasetStore, tmp_path: Path) -> None:
    from prodata.nodes import REGISTRY, NodeContext

    spec = REGISTRY["prep.select"]
    cfg = spec.config.model_validate({"fields": [{"name": "v", "cast": "Float64"}]})
    out = spec.run(NodeContext({"in": pl.DataFrame({"v": US})}, {}, store, tmp_path), cfg)
    assert out.tables["out"]["v"].to_list()[0] == 1234.56
    assert any("formato americano" in w for w in out.extra.get("warnings", []))


def test_cleaning_shows_american_values_right() -> None:
    rec = next(r for r in recommend(pl.DataFrame({"v": US})) if r["tipo"] == "numero_texto")
    assert {"antes": '"1,234.56"', "depois": "1234,56"} in rec["exemplos"]


@pytest.mark.parametrize("fmt", ["auto", "br", "us"])
@pytest.mark.parametrize("column", [BR, US, AMBIGUOUS], ids=["br", "us", "ambiguo"])
def test_sql_matches_engine(fmt: str, column: pl.Series, store: DatasetStore, tmp_path: Path) -> None:
    table = pl.DataFrame({"v": column, "n": list(range(column.len()))})
    for cast in ("Float64", "Int64"):
        assert_same(run_both("prep.select", {"in": table}, store, tmp_path,
                             fields=[{"name": "v", "cast": cast}], number_format=fmt))  # fmt: skip
