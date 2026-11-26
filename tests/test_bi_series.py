"""Linha e área no tempo (0.9.6): a série inteira, na ordem do eixo, e o aviso quando algo fica de fora.

Antes, o "Máximo de categorias" (12) também cortava a linha: a Selic de um ano virava duas semanas, sem aviso.
"""

from datetime import date, timedelta
from typing import Any

import polars as pl

from prodata.nodes.base import NodeContext
from prodata.nodes.bi import ChartConfig, chart
from prodata.nodes.bi_series import continuous, spread


def widget(frame: pl.DataFrame, **kw: Any) -> dict[str, Any]:
    ctx = NodeContext({"in": frame}, {}, None, None)  # type: ignore[arg-type]
    return chart(ctx, ChartConfig(**kw)).extra["bi_widget"]


def _days(n: int) -> pl.DataFrame:
    start = date(2025, 11, 26)
    return pl.DataFrame(
        {"data": [start + timedelta(days=i) for i in range(n)], "valor": [0.05 + i / 1e5 for i in range(n)]}
    )


def test_linha_de_datas_mostra_a_serie_inteira_em_ordem() -> None:
    w = widget(_days(249), chart_type="line", x_column="data", y_column="valor", agg="mean")
    labels = [s["label"] for s in w["series"]]
    assert len(labels) == 249 and labels == sorted(labels)
    assert labels[0] == "2025-11-26" and labels[-1] == str(date(2025, 11, 26) + timedelta(days=248))
    assert w["point_count"] == 249 and w["sampled"] is False and "category_count" not in w


def test_linha_segue_o_eixo_mesmo_com_ordenacao_por_valor() -> None:
    """Uma linha no tempo ordenada pelo valor não faz sentido: a ordem é a do eixo."""
    frame = pl.DataFrame({"mes": ["2026-03", "2026-01", "2026-02"], "valor": [1.0, 3.0, 2.0]})
    w = widget(frame, chart_type="area", x_column="mes", y_column="valor", sort="value_desc")
    assert [s["label"] for s in w["series"]] == ["2026-01", "2026-02", "2026-03"]


def test_numeros_no_eixo_em_ordem_numerica() -> None:
    frame = pl.DataFrame({"semana": list(range(30, 0, -1)), "valor": [float(i) for i in range(30)]})
    w = widget(frame, chart_type="line", x_column="semana", y_column="valor", sort="label")
    assert [s["label"] for s in w["series"]][:11] == [
        str(i) for i in range(1, 12)
    ]  # 10 depois de 9, não de 1
    assert len(w["series"]) == 30


def test_serie_longa_vira_amostra_espalhada_com_primeiro_e_ultimo() -> None:
    w = widget(_days(2500), chart_type="line", x_column="data", y_column="valor", agg="mean")
    labels = [s["label"] for s in w["series"]]
    assert len(labels) == 2000 and w["sampled"] is True and w["point_count"] == 2500
    assert labels[0] == "2025-11-26" and labels[-1] == str(date(2025, 11, 26) + timedelta(days=2499))
    assert labels == sorted(labels)


def test_linha_com_varias_series_tambem_vai_inteira() -> None:
    frame = pl.concat([_days(40).with_columns(pl.lit(s).alias("serie")) for s in ("A", "B")])
    w = widget(frame, chart_type="line", x_column="data", y_column="valor", series_column="serie", agg="sum")
    assert len(w["series"]) == 40 and sorted(w["series_names"]) == ["A", "B"]
    assert [s["label"] for s in w["series"]] == sorted(s["label"] for s in w["series"])
    assert w["point_count"] == 40 and w["sampled"] is False


def test_linha_de_texto_continua_com_o_limite_e_avisa() -> None:
    frame = pl.DataFrame(
        {"loja": [f"Loja {i:02d}" for i in range(20)], "valor": [float(i) for i in range(20)]}
    )
    w = widget(frame, chart_type="line", x_column="loja", y_column="valor", agg="mean")
    assert len(w["series"]) == 12 and w["category_count"] == 20 and "sampled" not in w


def test_colunas_cortadas_avisam_quantas_eram() -> None:
    frame = pl.DataFrame({"uf": [f"U{i:02d}" for i in range(20)], "valor": [float(i) for i in range(20)]})
    w = widget(frame, chart_type="bar", x_column="uf", y_column="valor", agg="sum")
    assert w["category_count"] == 20 and w["series"][-1]["label"] == "Outros" and len(w["series"]) == 13
    small = widget(frame.head(5), chart_type="bar", x_column="uf", y_column="valor")
    assert "category_count" not in small


def test_o_que_conta_como_eixo_continuo() -> None:
    frame = pl.DataFrame(
        {"d": [date(2026, 1, 1)], "n": [1], "t": ["2026-01-01 10:00:00"], "x": ["jan/26"], "b": [True]}
    )
    assert (
        continuous(frame, "d", "line") and continuous(frame, "n", "area") and continuous(frame, "t", "line")
    )
    assert not continuous(frame, "x", "line") and not continuous(frame, "b", "line")
    assert not continuous(frame, "d", "bar")


def test_amostra_espalhada() -> None:
    assert spread(list(range(5)), 10) == [0, 1, 2, 3, 4]
    picked = spread(list(range(1001)), 3)
    assert picked == [0, 500, 1000]
