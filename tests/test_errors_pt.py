"""Erros do motor em português (spec 046, RF-4621..4623)."""

from __future__ import annotations

import errno

import polars as pl
import pytest
from pydantic import BaseModel, Field, ValidationError

from prodata.domain.workflow import Workflow
from prodata.engine import errors_pt
from prodata.engine.runner import WorkflowRunner


def test_column_missing_brings_similar_columns() -> None:
    f = errors_pt.translate(ValueError("Coluna(s) inexistente(s): valr"), ["uf", "valor", "Valor_total"])
    assert f.message == "Coluna(s) inexistente(s): valr" and f.technical is None  # já estava em português
    assert f.hint == {"kind": "column_missing", "columns": ["valr"], "similar": {"valr": ["valor"]}}


def test_polars_column_error_is_translated() -> None:
    with pytest.raises(pl.exceptions.ColumnNotFoundError) as caught:
        pl.DataFrame({"valor": [1]}).select("valr")
    f = errors_pt.translate(caught.value, ["valor"])
    assert f.message == "A coluna 'valr' não existe na entrada."
    assert "valr" in (f.technical or "") and f.hint["similar"] == {"valr": ["valor"]}


def test_formula_unknown_function_keeps_the_prefix() -> None:
    raw = 'Fórmula de [x]: Catalog Error: Scalar Function with name tonumbr does not exist!\nDid you mean "abs"?'
    f = errors_pt.translate(ValueError(raw))
    assert f.message.startswith("Fórmula de [x]: A função tonumbr não existe nas fórmulas.")
    assert "ToNumber" in f.message and f.technical == raw


def test_sql_messages() -> None:
    f = errors_pt.translate(
        ValueError('Catalog Error: Table with name vendas does not exist!\nDid you mean "x"?')
    )
    assert "input_1" in f.message
    f = errors_pt.translate(ValueError('Parser Error: syntax error at or near "SELEC"'))
    assert f.message == 'Erro de sintaxe perto de "SELEC". Confira vírgulas, aspas e palavras-chave.'


def test_file_open_in_excel_and_memory() -> None:
    exc = PermissionError(errno.EACCES, "Permission denied", r"D:\saida\fechamento.xlsx")
    f = errors_pt.translate(exc)
    assert "fechamento.xlsx" in f.message and "Excel" in f.message and f.technical
    assert errors_pt.translate(MemoryError()).message.startswith("Faltou memória")


def test_unknown_errors_stay_as_they_are() -> None:
    f = errors_pt.translate(ValueError("algo que ninguém previu"))
    assert f.message == "algo que ninguém previu" and f.technical is None and f.hint == {}


class Cfg(BaseModel):
    mode: str = Field("a", pattern="^(a|b)$")
    top: int = Field(3, ge=1)


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"top": 0}, "use um valor a partir de 1"),
        ({"top": "x"}, "use um número inteiro"),
        ({"mode": "z"}, "formato não aceito"),
    ],
)
def test_validation_messages_in_portuguese(data: dict, expected: str) -> None:
    with pytest.raises(ValidationError) as caught:
        Cfg.model_validate(data)
    message, _field = errors_pt.validation_message(caught.value)
    assert expected in message and message.startswith("Configuração inválida em")


def test_runner_keeps_the_technical_text(runner: WorkflowRunner) -> None:
    wf = Workflow.model_validate({
        "id": "e", "nodes": [
            {"id": "t", "type": "io.text_input", "config": {"table": {"columns": ["valor"], "rows": [["1"]]}}},
            {"id": "q", "type": "transform.sql_query", "config": {"sql": "SELEC * FROM input_1"}},
        ], "edges": [{"id": "e1", "source": "t", "target": "q"}],
    })  # fmt: skip
    r = runner.run(wf).node_results["q"]
    assert r.status == "error" and r.error and r.error.startswith("Erro de sintaxe")
    assert "Parser Error" in r.extra["error_detail"]
