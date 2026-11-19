"""Linha de referência do Chart (spec 042, RF-4258): valor fixo, constante ou calculado dos valores do gráfico."""

from __future__ import annotations

import statistics
from typing import Any, Literal

from pydantic import Field

from prodata.forms import ui
from prodata.nodes.base import ToolConfig

# Gráficos com um eixo de valor contínuo, onde uma linha de referência faz sentido.
REF_CHARTS = ["bar", "hbar", "line", "area", "grouped", "scatter"]
REF_LABELS = {"value": "Meta", "mean": "Média", "median": "Mediana"}


class RefLineFields(ToolConfig):
    """Campos da linha de referência, herdados pelo ChartConfig."""

    # Linha de referência (spec 042, RF-4258): as cores acima e abaixo ficam no painel Formato do Dashboard.
    ref_line: Literal["none", "value", "mean", "median"] = Field(
        "none",
        title="Linha de referência",
        description="Uma linha no gráfico; o que fica acima e abaixo dela ganha cores próprias.",
        json_schema_extra=ui(
            group="Linha de referência",
            labels={
                "none": "Nenhuma",
                "value": "Valor fixo ou constante",
                "mean": "Média dos valores do gráfico",
                "median": "Mediana dos valores do gráfico",
            },
            show_if={"chart_type": REF_CHARTS},
        ),
    )
    ref_value: str = Field(
        "",
        title="Valor da linha",
        json_schema_extra=ui(
            group="Linha de referência", placeholder="100 ou [#meta]", show_if={"ref_line": ["value"]}
        ),
    )
    ref_label: str = Field(
        "",
        max_length=40,
        title="Rótulo da linha",
        json_schema_extra=ui(
            group="Linha de referência",
            placeholder="Meta, Média ou Mediana",
            show_if={"ref_line": ["value", "mean", "median"]},
        ),
    )


def _number(text: str) -> float:
    """Aceita 1.234,5 e 1234.5: o valor pode ter vindo de uma constante escrita do jeito brasileiro."""
    raw = text.strip().replace(" ", "")
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(
            f"Linha de referência: '{text}' não é um número. Use um valor como 100 ou uma constante [#meta]."
        ) from exc


def reference(kind: str, value: str, label: str, widget: dict[str, Any]) -> dict[str, Any] | None:
    """O valor e o rótulo da linha, ou None sem linha (ou sem dados para calcular)."""
    if kind == "none":
        return None
    if kind == "value":
        if not value.strip():
            raise ValueError("Linha de referência: escreva o valor (ou uma constante, como [#meta]).")
        number = _number(value)
    else:
        if widget.get("chart_type") == "scatter":
            values = [p["y"] for p in widget.get("points", []) if p.get("y") is not None]
        else:
            values = [s["value"] for s in widget.get("series", []) if s.get("value") is not None]
        if not values:
            return None
        number = statistics.fmean(values) if kind == "mean" else statistics.median(values)
    return {"kind": kind, "value": float(number), "label": label.strip() or REF_LABELS[kind]}
