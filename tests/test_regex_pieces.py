"""Spec 039: o Regex montado por peças. O mesmo padrão vale no motor, no SQL e na tela."""

import re
from pathlib import Path
from typing import Any

import duckdb
import polars as pl
import pytest

from prodata.engine.sql.fragment import SQL_REGISTRY, SqlContext, SqlInput
from prodata.engine.sql.macros import install_all
from prodata.engine.sql.verify import SAME, compare
from prodata.ingestion import DatasetStore
from prodata.nodes import REGISTRY, NodeContext
from prodata.nodes.regex_pieces import PIECES, RegexPiece, escape, names_of, pattern_of

# cada peça pronta: o que ela acha e o que ela não pode achar
READY = {
    "date": (["vence 31/10/2026", "01/01/2025"], ["2026-10-31", "31/10/26"]),
    "cpf": (["CPF 123.456.789-09", "12345678909"], ["123.456.78-09"]),
    "cnpj": (["12.345.678/0001-90", "12345678000190"], ["12.345.678/0001"]),
    "cep": (["CEP 01310-100", "01310100"], ["0131-100"]),
    "email": (["ana@empresa.com.br", "x.y+z@a-b.io"], ["ana@empresa", "@empresa.com"]),
    "phone": (["(11) 98765-4321", "11987654321", "(21)3333-4444"], ["98765"]),
    "decimal": (["R$ 1.234,56", "12,5", "1.234.567,89"], ["1234", "12.5"]),
}


def _find(pattern: str, values: list[str]) -> list[bool]:
    return [re.search(pattern, v) is not None for v in values]


@pytest.mark.parametrize("kind", sorted(READY))
def test_ready_pieces_find_their_examples(kind: str) -> None:
    good, bad = READY[kind]
    pattern = pattern_of([RegexPiece(kind=kind, take=True, name="x")])
    assert all(_find(pattern, good)), (kind, pattern)
    full = f"^{pattern}$"
    assert not any(re.search(full, v) for v in bad), (kind, full)
    series = pl.Series("v", good + bad)
    assert series.str.contains(pattern).to_list()[: len(good)] == [True] * len(good)  # o motor (Rust)
    with duckdb.connect(":memory:") as con:  # o SQL (RE2)
        found = [
            r[0]
            for r in con.execute(
                "SELECT regexp_matches(v, ?) FROM (SELECT unnest(?) AS v)", [pattern, good]
            ).fetchall()
        ]
    assert found == [True] * len(good)


def test_example_of_every_ready_piece_matches_itself() -> None:
    for kind, spec in PIECES.items():
        if spec.get("ready"):
            assert re.fullmatch(pattern_of([RegexPiece(kind=kind)]), spec["example"]), kind


def test_pieces_compose_the_pattern_and_the_names() -> None:
    """CA-01/CA-02: "NF 10/2026" descrito por peças, com mês e ano virando colunas."""
    pieces = [
        RegexPiece(kind="literal", text="NF "),
        RegexPiece(kind="digits", count=2, take=True, name="mes"),
        RegexPiece(kind="literal", text="/"),
        RegexPiece(kind="digits", count=4, take=True, name="ano"),
    ]
    assert pattern_of(pieces) == r"NF (\d{2})/(\d{4})"
    assert names_of(pieces) == ["mes", "ano"]
    assert names_of([RegexPiece(take=True), RegexPiece(take=True, name="b")]) == ["grupo_1", "b"]
    assert names_of([RegexPiece(kind="cpf")]) == ["trecho"] and names_of([]) == []
    assert (
        pattern_of(
            [RegexPiece(kind="word"), RegexPiece(kind="space", count=1), RegexPiece(kind="digits", count=1)]
        )
        == r"[A-Za-zÀ-ÿ]+\s\d"
    )


def test_fixed_text_is_escaped_only_where_needed() -> None:
    assert escape("R$ 1.000 (total)?") == r"R\$ 1\.000 \(total\)\?"
    assert escape("a/b-c") == "a/b-c"
    assert re.fullmatch(escape("[x]{2}+*|^"), "[x]{2}+*|^")


DF = pl.DataFrame(
    {"nota": ["NF 10/2026", "NF 03/2025", "sem data", None, "nf 12/2024"], "n": [1, 2, 3, 4, 5]}
)


def _run(store: DatasetStore, tmp_path: Path, **config: Any) -> pl.DataFrame:
    spec = REGISTRY["prep.regex"]
    cfg = spec.config.model_validate(config)
    return spec.run(NodeContext({"in": DF}, {}, store, tmp_path), cfg).tables["out"]


def _sql(**config: Any) -> pl.DataFrame:
    cfg = REGISTRY["prep.regex"].config.model_validate(config)
    with duckdb.connect(":memory:") as con:
        install_all(con)
        con.register("entrada", DF)
        ctx = SqlContext({"in": SqlInput("entrada", list(DF.columns), {"nota": "String", "n": "Int"})})
        return con.sql(SQL_REGISTRY["prep.regex"](ctx, cfg)["out"].sql).pl()


PIECES_NF = [
    {"kind": "literal", "text": "NF "},
    {"kind": "digits", "count": 2, "take": True, "name": "mes"},
    {"kind": "literal", "text": "/"},
    {"kind": "digits", "count": 4, "take": True, "name": "ano"},
]


def test_engine_and_sql_follow_the_pieces_without_a_written_pattern(
    store: DatasetStore, tmp_path: Path
) -> None:
    """Fluxo montado sem a tela (só as peças): o motor e o SQL geram o padrão do mesmo jeito."""
    out = _run(store, tmp_path, column="nota", pieces=PIECES_NF)
    assert out["mes"].to_list() == ["10", "03", None, None, None]
    assert out["ano"].to_list() == ["2026", "2025", None, None, None]
    assert compare(_sql(column="nota", pieces=PIECES_NF), out).state == SAME
    case = _run(store, tmp_path, column="nota", pieces=PIECES_NF, ignore_case=True)
    assert case["mes"].to_list()[-1] == "12"


def test_written_pattern_still_wins(store: DatasetStore, tmp_path: Path) -> None:
    """CA-04: fluxo salvo com a expressão escrita à mão dá o mesmo resultado de antes."""
    old = _run(store, tmp_path, column="nota", pattern=r"(\d{2})/(\d{4})", names=["m", "a"])
    assert old.columns[-2:] == ["m", "a"] and old["a"].to_list()[0] == "2026"
    both = _run(store, tmp_path, column="nota", pattern=r"(\d{4})", pieces=PIECES_NF)
    assert both.columns[-1] == "grupo_1" and both["grupo_1"].to_list()[0] == "2026"


def test_replace_and_match_with_pieces(store: DatasetStore, tmp_path: Path) -> None:
    cpf = [{"kind": "cpf"}]
    df = pl.DataFrame({"t": ["cliente 123.456.789-09 ok", "sem documento"]})
    spec = REGISTRY["prep.regex"]

    def run(**c: Any) -> pl.DataFrame:
        return spec.run(
            NodeContext({"in": df}, {}, store, tmp_path), spec.config.model_validate({"column": "t", **c})
        ).tables["out"]

    assert run(pieces=cpf, mode="replace", replacement="***")["t"].to_list() == [
        "cliente *** ok",
        "sem documento",
    ]
    assert run(pieces=cpf, mode="match", output="tem_cpf")["tem_cpf"].to_list() == [True, False]


def test_catalog_sends_the_piece_table_to_the_screen() -> None:
    field = next(f for f in REGISTRY["prep.regex"].describe()["config_fields"] if f["name"] == "pieces")
    assert field["widget"] == "regex_builder"
    assert field["catalog"]["cpf"]["base"] == PIECES["cpf"]["base"]
    assert {f["name"]: f.get("group") for f in REGISTRY["prep.regex"].describe()["config_fields"]}[
        "pattern"
    ] == "Avançado"
