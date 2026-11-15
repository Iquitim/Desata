"""Spec 038: separador decimal. O CSV gravado escolhe o próprio; o perfil manda os limites como número."""

from pathlib import Path

import duckdb
import polars as pl

from prodata.engine.profiling import profile_column
from prodata.engine.sql.fragment import SQL_REGISTRY, SqlContext, SqlInput
from prodata.ingestion import DatasetStore
from prodata.nodes import REGISTRY, NodeContext

DF = pl.DataFrame({"produto": ["a", "b"], "valor": [1234.56, 7.5], "qtd": [3, 4]})


def _write(store: DatasetStore, tmp_path: Path, **config: object) -> str:
    spec = REGISTRY["io.output_data"]
    cfg = spec.config.model_validate({"filename": "saida", "format": "csv", **config})
    spec.run(NodeContext({"in": DF}, {}, store, tmp_path), cfg)
    return (tmp_path / "saida.csv").read_text(encoding="utf-8")


def test_csv_keeps_the_point_by_default(store: DatasetStore, tmp_path: Path) -> None:
    """CA-04: sem mexer, o arquivo continua como sempre foi."""
    text = _write(store, tmp_path)
    assert text.splitlines() == ["produto;valor;qtd", "a;1234.56;3", "b;7.5;4"]


def test_csv_with_decimal_comma(store: DatasetStore, tmp_path: Path) -> None:
    """CA-04: com vírgula, o Excel em português abre o número como número."""
    text = _write(store, tmp_path, decimal=",")
    assert text.splitlines() == ["produto;valor;qtd", "a;1234,56;3", "b;7,5;4"]
    back = pl.read_csv(tmp_path / "saida.csv", separator=";", decimal_comma=True)
    assert back["valor"].to_list() == [1234.56, 7.5]


def test_sql_note_shows_a_copy_that_really_runs(tmp_path: Path) -> None:
    cfg = REGISTRY["io.output_data"].config.model_validate(
        {"filename": "saida", "format": "csv", "decimal": ","}
    )
    ctx = SqlContext(
        {"in": SqlInput("dados", list(DF.columns), {"produto": "String", "valor": "Float", "qtd": "Int"})}
    )
    fragment = SQL_REGISTRY["io.output_data"](ctx, cfg)["out"]
    note = next(n for n in fragment.notes if "vírgula decimal" in n)
    expr = note[note.index("replace(") : note.index(", e use")]
    target = (tmp_path / "x.csv").as_posix()
    with duckdb.connect(":memory:") as con:  # a orientação da ressalva funciona de verdade
        con.register("dados", DF)
        con.execute(
            f"COPY (SELECT * REPLACE ({expr} AS valor) FROM dados) TO '{target}' (FORMAT csv, DELIMITER ';')"
        )
    assert (tmp_path / "x.csv").read_text(encoding="utf-8").splitlines()[1] == "a;1234,56;3"
    plain = REGISTRY["io.output_data"].config.model_validate({"filename": "saida", "format": "csv"})
    assert not any("vírgula decimal" in n for n in SQL_REGISTRY["io.output_data"](ctx, plain)["out"].notes)


def test_histogram_sends_the_bounds_as_numbers() -> None:
    """A tela formata os limites com o separador escolhido; o texto pronto fica só como apoio."""
    column = profile_column(pl.Series("v", [0.5, 1.25, 2.5, 1000.0]))
    bins = column["histogram"]
    assert all(isinstance(b["lo"], float) and isinstance(b["hi"], float) for b in bins)
    assert bins[0]["lo"] == 0.5 and bins[-1]["hi"] == 1000.0
    single = profile_column(pl.Series("v", [2.5, 2.5]))
    assert single["histogram"][0]["lo"] == single["histogram"][0]["hi"] == 2.5
