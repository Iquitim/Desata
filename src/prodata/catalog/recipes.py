"""Receitas prontas (spec 049, RF-4961): Corrigir valores pelo IPCA e Converter para dólar pela PTAX.

A receita monta caixas comuns (Dados públicos, Select, Join, Summarize, Append Fields, Formula) numa etapa nomeada,
ligadas depois da caixa escolhida. A pessoa pode abrir e mudar cada uma. Nada aqui executa nem acessa a rede: a
leitura acontece quando o fluxo executa, como em qualquer caixa Dados públicos.
"""

from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from prodata.catalog import curated, hosts

IPCA_ID = "ibge.agregado/1737"
IPCA_INDEX = 2266  # número-índice (dez/1993 = 100)
PTAX_ID = "bcb.ptax/moeda"
COLUMN = r"^[^\[\]\n]{1,120}$"


class RecipeRequest(BaseModel):
    receita: Literal["ipca", "ptax"]
    valor: str = Field(pattern=COLUMN)
    data: str = Field(pattern=COLUMN)
    # IPCA: o mês de referência (AAAA-MM); vazio = o mais recente publicado, a cada execução.
    referencia: str = Field("", pattern=r"^(\d{4}-\d{2})?$")
    moeda: str = Field("USD", pattern=r"^[A-Z]{3}$")
    # A data mais antiga da tabela, para ler o índice ou a cotação só desde ali.
    desde: date | None = None
    x: float = 0
    y: float = 0

    @field_validator("valor", "data")
    @classmethod
    def _plain(cls, value: str) -> str:
        return value.strip()


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _public(source_id: str, choices: dict[str, Any]) -> dict[str, Any]:
    source = curated.get(source_id)
    assert source is not None
    return {"fonte": {"id": source.id, "nome": source.nome, "orgao": hosts.SERVICES[source.servico].agency,
                      "citacao": source.citacao, "licenca": source.licenca, "escolhas": choices}}  # fmt: skip


def _since(req: RecipeRequest, margin_days: int) -> str:
    start = req.desde or date(2000, 1, 1)
    return date.fromordinal(max(1, start.toordinal() - margin_days)).isoformat()


def _formula(column: str, expression: str, kind: str = "Auto") -> dict[str, Any]:
    return {"formulas": [{"target": "new", "column": column, "type": kind, "expression": expression}]}


def _safe(name: str) -> str:
    return re.sub(r"[^0-9A-Za-z_]+", "_", name).strip("_") or "valor"


def build(req: RecipeRequest) -> dict[str, Any]:
    """As caixas, os fios entre elas, a etapa e por onde a receita entra e sai."""
    return _ipca(req) if req.receita == "ipca" else _ptax(req)


def _ipca(req: RecipeRequest) -> dict[str, Any]:
    v, d = req.valor, req.data
    month, data, select, join, summary, append, result = (
        _id(p) for p in ("mes", "ipca", "sel", "join", "ref", "junta", "corr")
    )
    filt = _id("filtro") if req.referencia else None
    x, y = req.x, req.y
    nodes = [
        {"id": month, "type": "prep.formula", "label": "Mês da data", "x": x, "y": y,
         "config": _formula("ipca_mes", f"StartOfMonth([{d}])", "Date")},
        {"id": data, "type": "io.public_data", "label": "IPCA (número-índice)", "x": x, "y": y + 170,
         "config": _public(IPCA_ID, {"variavel": IPCA_INDEX, "nivel": "N1",
                                     "periodo": {"kind": "desde", "inicio": _since(req, 62)}})},
        {"id": select, "type": "prep.select", "label": "Índice do mês", "x": x + 260, "y": y + 170,
         "config": {"fields": [{"name": "codigo", "keep": False}, {"name": "localidade", "keep": False},
                               {"name": "periodo", "keep": False}, {"name": "valor", "rename": "ipca_indice_mes"}]}},
        {"id": join, "type": "transform.join", "label": "Junta pelo mês", "x": x + 260, "y": y,
         "config": {"keys": [{"left": "ipca_mes", "right": "data"}], "keys_mode": "left", "stack": "LJ", "stack_column": ""}},
        {"id": summary, "type": "transform.summarize", "label": "Índice de referência", "x": x + 520 + (260 if filt else 0), "y": y + 170,
         "config": {"group_by": [], "aggregations": [{"column": "ipca_indice_mes", "agg": "last", "alias": "ipca_indice_ref"},
                                                     {"column": "data", "agg": "last", "alias": "ipca_mes_ref"}]}},
        {"id": append, "type": "transform.append_fields", "label": "Leva a referência", "x": x + 520 + (260 if filt else 0), "y": y,
         "config": {"prefix": "s_"}},
        {"id": result, "type": "prep.formula", "label": f"{v} corrigido pelo IPCA", "x": x + 780 + (260 if filt else 0), "y": y,
         "config": _formula(f"{_safe(v)}_corrigido", f"[{v}] * [ipca_indice_ref] / [ipca_indice_mes]", "Float64")},
    ]  # fmt: skip
    edges = [(data, "out", select, "in"), (month, "out", join, "L"), (select, "out", join, "R"),
             (join, "U", append, "T"), (summary, "out", append, "S"), (append, "out", result, "in")]  # fmt: skip
    if filt:
        nodes.append({"id": filt, "type": "prep.filter", "label": f"Mês {req.referencia}", "x": x + 520, "y": y + 170,
                      "config": {"mode": "simple", "column": "data", "operator": "==", "value": f"{req.referencia}-01"}})  # fmt: skip
        edges += [(select, "out", filt, "in"), (filt, "T", summary, "in")]
    else:
        edges.append((select, "out", summary, "in"))
    ref = f"de {req.referencia}" if req.referencia else "do mês mais recente publicado"
    title = f"Corrigir {v} pelo IPCA"
    note = (f"{v} em valores {ref}: {v} × índice de referência ÷ índice do mês de {d}. Meses ainda sem IPCA publicado "
            f"ficam com o valor corrigido vazio.")  # fmt: skip
    return _pack(nodes, edges, month, "in", result, title, note)


def _ptax(req: RecipeRequest) -> dict[str, Any]:
    v, d = req.valor, req.data
    day, data, select, join, result = (_id(p) for p in ("dia", "ptax", "sel", "join", "conv"))
    x, y = req.x, req.y
    column = f"ptax_venda_{req.moeda.lower()}"
    nodes = [
        {"id": day, "type": "prep.formula", "label": "Dia da data", "x": x, "y": y,
         "config": _formula("ptax_dia", f"ToDate([{d}])", "Date")},
        {"id": data, "type": "io.public_data", "label": f"PTAX {req.moeda}", "x": x, "y": y + 170,
         "config": _public(PTAX_ID, {"moeda": req.moeda, "periodo": {"kind": "desde", "inicio": _since(req, 15)}})},
        {"id": select, "type": "prep.select", "label": "Cotação de venda", "x": x + 260, "y": y + 170,
         "config": {"fields": [{"name": "data", "rename": "ptax_data"}, {"name": "cotacao_venda", "rename": column},
                               *({"name": c, "keep": False} for c in ("moeda", "cotacao_compra", "paridade_compra",
                                                                      "paridade_venda", "boletim", "data_hora"))]}},
        {"id": join, "type": "transform.join", "label": "Cotação do dia ou do dia útil anterior", "x": x + 260, "y": y,
         "config": {"keys": [{"left": "ptax_dia", "right": "ptax_data"}], "match": "previous", "keys_mode": "both", "stack": "LJ",
                    "stack_column": ""}},
        {"id": result, "type": "prep.formula", "label": f"{v} em {req.moeda}", "x": x + 520, "y": y,
         "config": _formula(f"{_safe(v)}_{req.moeda.lower()}", f"[{v}] / [{column}]", "Float64")},
    ]  # fmt: skip
    edges = [
        (day, "out", join, "L"),
        (data, "out", select, "in"),
        (select, "out", join, "R"),
        (join, "U", result, "in"),
    ]
    title = f"Converter {v} para {req.moeda} pela PTAX"
    note = (f"{v} ÷ PTAX de venda de {req.moeda} (boletim de fechamento) do dia de {d} ou, sem cotação nesse dia, "
            "do último dia útil anterior: o Join avisa quantas linhas usaram o dia anterior.")  # fmt: skip
    return _pack(nodes, edges, day, "in", result, title, note)


def _pack(
    nodes: list[dict[str, Any]], edges: list[tuple[str, str, str, str]], entry: str, entry_port: str,
    exit_node: str, title: str, note: str,
) -> dict[str, Any]:  # fmt: skip
    xs = [n["x"] for n in nodes]
    ys = [n["y"] for n in nodes]
    container = {"id": _id("etapa"), "title": title, "description": note, "color": "#2f7d6d",
                 "x": min(xs) - 30, "y": min(ys) - 50, "width": max(xs) - min(xs) + 250, "height": max(ys) - min(ys) + 140}  # fmt: skip
    return {
        "nodes": nodes,
        "edges": [
            {"id": _id("e"), "source": s, "sourceHandle": sp, "target": t, "targetHandle": tp}
            for s, sp, t, tp in edges
        ],
        "container": container,
        "entrada": {"node": entry, "port": entry_port},
        "saida": {"node": exit_node, "port": "out"},
        "largura": max(xs) - min(xs) + 260,
        "nota": note,
    }
