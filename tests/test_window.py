"""Rank (spec 044, RF-4401..4404): empates, grupos, top N e vazios."""

from pathlib import Path
from typing import Any

import polars as pl
import pytest

from prodata.ingestion import DatasetStore
from prodata.nodes import REGISTRY, NodeContext

SALES = pl.DataFrame(
    {
        "vendedor": ["Ana", "Bia", "Caio", "Davi", "Eva", "Fábio", "Gil"],
        "regiao": ["Sul", "Sul", "Sul", "Norte", "Norte", "Norte", "Sul"],
        "vendas": [100.0, 300.0, 300.0, 50.0, 80.0, None, 200.0],
    }
)


def rank(store: DatasetStore, tmp_path: Path, **config: Any) -> pl.DataFrame:
    spec = REGISTRY["prep.rank"]
    cfg = spec.config.model_validate(config)
    return spec.run(NodeContext({"in": SALES}, {}, store, tmp_path), cfg).tables["out"]


DESC = [{"column": "vendas", "descending": True}]


@pytest.mark.parametrize(
    ("method", "expected"),
    [("row", [1, 2, 3, 4, 5, 6, 7]), ("rank", [1, 1, 3, 4, 5, 6, 7]), ("dense", [1, 1, 2, 3, 4, 5, 6])],
)
def test_three_ways_to_handle_ties(
    method: str, expected: list[int], store: DatasetStore, tmp_path: Path
) -> None:
    out = rank(store, tmp_path, order_by=DESC, method=method)
    assert out["posicao"].to_list() == expected
    # Empate pela ordem de chegada: Bia antes de Caio; o vazio fica por último.
    assert out["vendedor"].to_list()[:3] == ["Bia", "Caio", "Gil"]
    assert out["vendedor"].to_list()[-1] == "Fábio"


def test_restarts_in_each_group_and_keeps_top(store: DatasetStore, tmp_path: Path) -> None:
    out = rank(store, tmp_path, order_by=DESC, method="rank", group_by=["regiao"], keep_top=True, top=2)
    rows = list(zip(out["regiao"], out["vendedor"], out["posicao"], strict=True))
    # Norte: Eva 1, Davi 2. Sul: Bia e Caio empatam em 1 (o 3º, Gil, fica de fora no top 2).
    assert rows == [("Norte", "Eva", 1), ("Norte", "Davi", 2), ("Sul", "Bia", 1), ("Sul", "Caio", 1)]


def test_empty_values_go_last_also_ascending(store: DatasetStore, tmp_path: Path) -> None:
    out = rank(store, tmp_path, order_by=[{"column": "vendas"}], method="dense")
    assert out["vendedor"].to_list()[0] == "Davi"
    assert out["vendedor"].to_list()[-1] == "Fábio"


def test_moving_average_recipe_formula(store: DatasetStore, tmp_path: Path) -> None:
    """RF-4411/4412: a fórmula da receita (como a tela escreve) dá vazio até completar a janela, em cada grupo."""
    table = pl.DataFrame(
        {
            "uf": ["SP", "RJ", "SP", "RJ", "SP", "SP"],
            "mes": [1, 1, 2, 2, 3, 4],
            "v": [3.0, 10.0, 6.0, 20.0, 9.0, None],
        }
    )
    spec = REGISTRY["prep.multirow"]
    cfg = spec.config.model_validate(
        {
            "recipe": "mavg",
            "base": "v",
            "window": 3,
            "order_by": [{"column": "mes"}],
            "group_by": ["uf"],
            "column": "mm",
            "type": "Float64",
            "expression": "IF IsNull([Row-2:v]) THEN Null ELSE ([v] + [Row-1:v] + [Row-2:v]) / 3 ENDIF",
        }
    )
    out = spec.run(NodeContext({"in": table}, {}, store, tmp_path), cfg).tables["out"]
    got = {(r["uf"], r["mes"]): r["mm"] for r in out.iter_rows(named=True)}
    assert got[("SP", 1)] is None and got[("SP", 2)] is None
    assert got[("SP", 3)] == pytest.approx(6.0)
    assert got[("SP", 4)] is None  # valor vazio dentro da janela
    assert got[("RJ", 2)] is None  # o RJ só tem duas linhas


def test_window_field_limits() -> None:
    spec = REGISTRY["prep.multirow"]
    with pytest.raises(ValueError):
        spec.config.model_validate({"recipe": "mavg", "window": 1})
    with pytest.raises(ValueError):
        spec.config.model_validate({"recipe": "mavg", "window": 25})


@pytest.mark.parametrize(
    ("t", "s", "level"), [(100, 10, None), (1000, 200, "pesado"), (2000, 1000, "muito grande")]
)
def test_append_fields_warns_by_volume(
    t: int, s: int, level: str | None, store: DatasetStore, tmp_path: Path
) -> None:
    """RF-4422: até 100 mil, nada; acima, aviso; acima de 1 milhão, aviso forte."""
    spec = REGISTRY["transform.append_fields"]
    tables = {"T": pl.DataFrame({"a": range(t)}), "S": pl.DataFrame({"b": range(s)})}
    out = spec.run(NodeContext(tables, {}, store, tmp_path), spec.config())
    assert out.tables["out"].height == t * s
    warnings = out.extra.get("warnings") or []
    if level is None:
        assert not warnings
    else:
        assert level in warnings[0].lower() and f"{t * s:,}".replace(",", ".") in warnings[0]


def test_without_order_the_data_passes_with_a_hint(store: DatasetStore, tmp_path: Path) -> None:
    """Recém-ligado, sem configurar: nada de erro vermelho; os dados passam e a caixa diz o que falta."""
    spec = REGISTRY["prep.rank"]
    out = spec.run(NodeContext({"in": SALES}, {}, store, tmp_path), spec.config())
    assert out.tables["out"].equals(SALES)
    assert "Classificar por" in out.extra["warnings"][0]


def test_clear_errors(store: DatasetStore, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="inexistente"):
        rank(store, tmp_path, order_by=[{"column": "lucro"}])
    with pytest.raises(ValueError, match="Já existe"):
        rank(store, tmp_path, order_by=DESC, column="vendas")
