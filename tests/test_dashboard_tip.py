"""Spec 041, RF-4141: colunas extras na dica, agregadas como o valor do gráfico."""

from pathlib import Path
from typing import Any

import polars as pl

from prodata.dashboard.filters import used_columns
from prodata.ingestion import DatasetStore
from prodata.nodes import REGISTRY, NodeContext
from prodata.nodes.bi import ChartConfig

DF = pl.DataFrame(
    {
        "regiao": ["N", "N", "S", "S", "S", "L", "O"],
        "receita": [10.0, 20.0, 5.0, 5.0, 5.0, 7.0, 1.0],
        "pedidos": [1, 2, 1, 1, 1, 3, 1],
        "margem": [0.1, 0.3, 0.2, 0.2, None, 0.5, 0.4],
    }
)


def widget(tmp_path: Path, **config: Any) -> dict[str, Any]:
    spec = REGISTRY["bi.chart"]
    ctx = NodeContext({"in": DF}, {}, DatasetStore(tmp_path / "d", 10), tmp_path)
    return spec.run(ctx, spec.config.model_validate(config)).extra["bi_widget"]


def test_extra_columns_use_the_chart_aggregation(tmp_path: Path) -> None:
    w = widget(tmp_path, x_column="regiao", y_column="receita", agg="sum", tip_columns=["pedidos", "margem"])
    by = {s["label"]: s for s in w["series"]}
    assert by["N"]["value"] == 30 and by["N"]["tip"] == {"pedidos": 3.0, "margem": 0.4}
    assert by["S"]["tip"]["pedidos"] == 3.0


def test_count_sums_the_extra_columns_and_mean_averages(tmp_path: Path) -> None:
    w = widget(tmp_path, x_column="regiao", agg="count", tip_columns=["pedidos"])
    assert {s["label"]: s["tip"]["pedidos"] for s in w["series"]}["S"] == 3.0
    w = widget(tmp_path, x_column="regiao", y_column="receita", agg="mean", tip_columns=["margem"])
    assert {s["label"]: s["tip"]["margem"] for s in w["series"]}["S"] == 0.2


def test_others_add_up_the_extras(tmp_path: Path) -> None:
    w = widget(
        tmp_path, x_column="regiao", y_column="receita", agg="sum", max_items=2, tip_columns=["pedidos"]
    )
    others = w["series"][-1]
    assert others["label"] == "Outros" and others["tip"]["pedidos"] == 4.0  # L (3) + O (1)


def test_without_extras_nothing_changes(tmp_path: Path) -> None:
    w = widget(tmp_path, x_column="regiao", y_column="receita", tip_columns=["nao_existe", "regiao"])
    assert all("tip" not in s for s in w["series"])


def test_extra_columns_go_to_the_html_file() -> None:
    cfg = ChartConfig(x_column="regiao", y_column="receita", tip_columns=["pedidos"])
    assert "pedidos" in used_columns("bi.chart", cfg, DF, [])
