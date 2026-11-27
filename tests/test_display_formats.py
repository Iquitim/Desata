"""Spec 050: formato de exibição da coluna — modelo, herança, arquivo do fluxo e formato de número do Excel."""

import json
from datetime import date
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from openpyxl import Workbook, load_workbook
from pydantic import ValidationError

from prodata.domain.display_formats import DisplayFormat, effective_formats
from prodata.domain.workflow import Edge, Node, Workflow
from prodata.ingestion import DatasetStore
from prodata.nodes import REGISTRY, NodeContext, formats_for
from prodata.nodes.excel_output import excel_formats, excel_number_format
from prodata.nodes.excel_template import write_template
from prodata.services.trust import fingerprint

CASES = json.loads((Path(__file__).parent / "fixtures" / "formatos_heranca.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ modelo


@pytest.mark.parametrize(
    "bad",
    [
        {"kind": "currency", "symbol": "<b>"},
        {"kind": "currency", "symbol": 'R"$'},
        {"kind": "currency", "symbol": "1234567"},
    ],
)
def test_symbol_is_checked(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        DisplayFormat.model_validate(bad)


@pytest.mark.parametrize("bad", ["sem digito", "<###>", "#" * 41, "##'#"])
def test_mask_is_checked(bad: str) -> None:
    with pytest.raises(ValidationError):
        DisplayFormat.model_validate({"kind": "document", "mask": bad})


def test_presets_and_free_mask_are_accepted() -> None:
    for mask in ("cpf", "cnpj", "cep", "phone", "###.###-#", "AB-####"):
        assert DisplayFormat.model_validate({"kind": "document", "mask": mask}).mask == mask


def test_only_the_fields_of_the_kind_are_saved() -> None:
    spec = DisplayFormat.model_validate({"kind": "date", "pattern": "my", "symbol": "US$", "decimals": 4})
    assert spec.compact() == {"kind": "date", "pattern": "my"}
    assert DisplayFormat(kind="none").compact() == {"kind": "none"}


# ------------------------------------------------------------------ herança (mesmos casos da tela)


@pytest.mark.parametrize("case", CASES["cases"], ids=[c["name"] for c in CASES["cases"]])
def test_inheritance(case: dict[str, Any]) -> None:
    wf = Workflow.model_validate(
        {
            "id": "f",
            "nodes": [{"id": i, "type": t} for i, t in case["nodes"]],
            "edges": [
                {"id": f"e{k}", "source": s, "target": t, "targetHandle": h}
                for k, (s, t, h) in enumerate(case["edges"])
            ],
            "column_formats": case["formats"],
        }
    )
    ports = CASES["ports"]
    for node_id, expected in case["expect"].items():
        found = effective_formats(wf.column_formats, wf.nodes, wf.edges, node_id, lambda t: ports.get(t, []))
        assert {c: f.kind for c, f in found.items()} == expected, node_id


def test_formats_for_uses_the_port_order_of_the_tool() -> None:
    """Na Junção a entrada L ganha da R, mesmo com a R ligada antes."""
    wf = Workflow(
        id="f",
        nodes=[
            Node(id="l", type="io.input_data"),
            Node(id="r", type="io.input_data"),
            Node(id="j", type="transform.join"),
        ],
        edges=[
            Edge(id="e1", source="r", target="j", target_handle="R"),
            Edge(id="e2", source="l", target="j", target_handle="L"),
        ],
        column_formats={
            "l": {"valor": DisplayFormat(kind="currency")},
            "r": {"valor": DisplayFormat(kind="percent")},
        },
    )
    assert [p.id for p in REGISTRY["transform.join"].inputs] == ["L", "R"]
    assert formats_for(wf, "j")["valor"].kind == "currency"


# ------------------------------------------------------------------ arquivo do fluxo


def test_flow_without_formats_keeps_its_fingerprint() -> None:
    raw = {"id": "f", "nodes": [{"id": "a", "type": "io.input_data"}]}
    before = Workflow.model_validate(raw)
    assert "column_formats" not in before.model_dump(mode="json", by_alias=True)
    assert fingerprint(before) == fingerprint(Workflow.model_validate({**raw, "column_formats": {}}))


def test_formats_are_saved_compact_and_follow_deleted_boxes() -> None:
    wf = Workflow.model_validate(
        {
            "id": "f",
            "nodes": [{"id": "a", "type": "io.input_data"}],
            "column_formats": {
                "a": {"valor": {"kind": "currency", "symbol": "US$", "decimals": 2, "mask": "cnpj"}},
                "apagada": {"cpf": {"kind": "document"}},
            },
        }
    )
    dumped = wf.model_dump(mode="json", by_alias=True)["column_formats"]
    assert dumped == {"a": {"valor": {"kind": "currency", "decimals": 2, "symbol": "US$"}}}
    again = Workflow.model_validate(wf.model_dump(mode="json", by_alias=True))
    assert again.model_dump(mode="json", by_alias=True)["column_formats"] == dumped


# ------------------------------------------------------------------ Excel (RF-5027)

TABLE = pl.DataFrame(
    {
        "valor": [1234.5, -10.0],
        "cpf": [1234567890, 12345678901],
        "cpf_texto": ["123.456.789-01", "x"],
        "taxa": [0.15, 0.2],
        "data": [date(2026, 11, 26), date(2026, 1, 2)],
    }
)
FORMATS = {
    "valor": DisplayFormat(kind="currency", symbol="R$", decimals=2),
    "cpf": DisplayFormat(kind="document", mask="cpf"),
    "cpf_texto": DisplayFormat(kind="document", mask="cpf"),
    "taxa": DisplayFormat(kind="percent", decimals=1),
    "data": DisplayFormat(kind="date", pattern="dmy"),
}
CODES = {
    "valor": '"R$" #,##0.00;-"R$" #,##0.00',
    "cpf": '000"."000"."000"-"00',
    "taxa": "0.0%",
    "data": "dd/mm/yyyy",
}


def test_excel_codes() -> None:
    assert excel_formats(TABLE, FORMATS) == CODES  # texto fica como está: o Excel não formata texto
    assert excel_number_format(DisplayFormat(kind="number", decimals=0, thousands=False), pl.Int64()) == "0"
    assert (
        excel_number_format(DisplayFormat(kind="percent", base="hundred", decimals=0), pl.Float64()) == '0"%"'
    )
    assert excel_number_format(DisplayFormat(kind="document", mask="AB-##"), pl.Int64()) == '"AB-"00'
    assert excel_number_format(DisplayFormat(kind="date", pattern="long"), pl.Date()).startswith("[$-416]")
    assert excel_number_format(DisplayFormat(kind="currency"), pl.String()) is None


def _formats_in(path: Path, sheet: str | None = None, first_row: int = 2) -> dict[str, str]:
    ws = load_workbook(path)[sheet] if sheet else load_workbook(path).active
    assert ws is not None
    heads = {ws.cell(first_row - 1, c).value: c for c in range(1, ws.max_column + 1)}
    return {name: ws.cell(first_row, col).number_format for name, col in heads.items() if name in CODES}


def _export(tmp_path: Path, df: pl.DataFrame, **config: Any) -> Path:
    spec = REGISTRY["io.output_data"]
    exports = tmp_path / "exports"
    exports.mkdir(exist_ok=True)
    ctx = NodeContext({"in": df}, {}, DatasetStore(tmp_path / "d", 10), exports, column_formats=FORMATS)
    spec.run(ctx, spec.config.model_validate({"filename": "relatorio", **config}))
    return exports / "relatorio.xlsx"


def test_excel_new_file_and_added_sheet_keep_numbers(tmp_path: Path) -> None:
    path = _export(tmp_path, TABLE, sheet_name="Um")
    assert _formats_in(path, "Um") == CODES
    _export(tmp_path, TABLE, sheet_name="Dois", if_exists="add_sheet")
    assert _formats_in(path, "Dois") == CODES
    ws = load_workbook(path)["Dois"]
    assert ws["A2"].value == 1234.5 and ws["B2"].value == 1234567890  # a célula continua número


def test_excel_template_gets_the_formats(tmp_path: Path) -> None:
    template = tmp_path / "modelo.xlsx"
    book = Workbook()
    book.save(template)
    target = tmp_path / "saida.xlsx"
    write_template(
        TABLE, template.resolve(), target, sheet="", cell="B3", header=True, clear=False, formats=FORMATS
    )
    ws = load_workbook(target).active
    assert ws is not None
    assert ws["B4"].number_format == CODES["valor"] and ws["F4"].number_format == CODES["data"]
