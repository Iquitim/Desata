"""Benchmark (spec 048, RF-4841..4843, CA-07): o relatório e a comparação, sem medir nada de verdade."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import polars as pl

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "benchmark.py"


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("benchmark_script", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RESULT = {"versao": "0.9.5", "data": "2026-11-22 10:00",
          "maquina": {"sistema": "Windows 11", "processador": "x", "nucleos": 8, "python": "3.14", "polars": "1"},
          "medidas": [{"fluxo": "Join", "linhas": 1_000_000, "segundos": 1.3, "memoria_mb": 200},
                      {"fluxo": "Sort", "linhas": 1_000_000, "segundos": 0.5, "memoria_mb": 100}]}  # fmt: skip


def test_compare_points_out_changes_over_twenty_percent() -> None:
    bench = load()
    previous = {"medidas": [{"fluxo": "Join", "linhas": 1_000_000, "segundos": 1.0},
                            {"fluxo": "Sort", "linhas": 1_000_000, "segundos": 0.55}]}  # fmt: skip
    lines = bench.compare(RESULT, previous)
    assert len(lines) == 1 and "Join" in lines[0] and "30% mais lento" in lines[0]


def test_markdown_table_reads_in_portuguese() -> None:
    text = load().markdown(RESULT, [])
    assert "| Join | 1.000.000 | 1,3 | 200 |" in text and "Windows 11" in text


def test_generated_data_has_the_expected_shape(tmp_path: Path) -> None:
    bench = load()
    bench.make_data(tmp_path, 1000)
    sales = pl.read_csv(tmp_path / "vendas_1000.csv")
    assert sales.height == 1000 and set(sales.columns) == {"uf", "produto", "data", "valor", "quantidade"}
    assert pl.read_csv(tmp_path / "regioes.csv").height == 10
