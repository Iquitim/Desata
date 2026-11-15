"""Saídas do leitor de PDF (spec 037, RF-3770): campos, itens de cada tabela, falhas e origem, e a política de falha."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import polars as pl

from prodata.documents.extract import APROVADO, ENCONTRADO, FALHOU, REVISAR
from prodata.documents.recipe import Recipe
from prodata.documents.sources import (
    FIELD_LABELS,
    MAIN_OUTPUT,
    STATE_LABELS,
    Correction,
    PdfSource,
)
from prodata.documents.types import InvalidValueError, convert

# ------------------------------------------------------------------ execução: documentos → tabelas


@dataclass
class DocRun:
    name: str
    path: Path
    result: dict[str, Any]
    corrected: list[str] = field(default_factory=list)


def apply_corrections(doc: DocRun, recipe: Recipe, corrections: list[Correction]) -> None:
    """Troca o valor do campo pelo corrigido, marca e reavalia o documento. Assinatura diferente: não vale."""
    mine = {
        c.campo: c
        for c in corrections
        if c.documento == doc.name and c.assinatura == doc.result.get("assinatura")
    }
    if not mine:
        return
    specs = {f.nome: f for f in recipe.campos}
    for item in doc.result["campos"]:
        fix = mine.get(item["nome"])
        if fix is None or item["nome"] not in specs:
            continue
        try:
            value = convert(fix.valor, specs[item["nome"]].tipo)
        except InvalidValueError:
            continue
        from prodata.documents.types import to_json

        item.update(
            estado=ENCONTRADO,
            valor=to_json(value),
            texto=fix.valor,
            corrigido={"por": fix.quem, "em": fix.quando.isoformat(), "original": fix.original, "id": fix.id},
            motivo="corrigido só neste documento",
        )
        doc.corrected.append(item["nome"])
    required = [f["nome"] for f in doc.result["campos"] if f["obrigatorio"] and f["estado"] != ENCONTRADO]
    others = [f["nome"] for f in doc.result["campos"] if f["estado"] != ENCONTRADO]
    others += [
        t["nome"] for t in doc.result["tabelas"] if t["problema"] or any(r["duvida"] for r in t["linhas"])
    ]
    if doc.result.get("erro"):
        return
    if required:
        doc.result.update(estado=FALHOU, motivo="obrigatório sem valor: " + ", ".join(required))
    elif others:
        doc.result.update(estado=REVISAR, motivo="conferir: " + ", ".join(others))
    else:
        doc.result.update(estado=APROVADO, motivo="")


_POLARS = {
    "texto": pl.Utf8,
    "inteiro": pl.Int64,
    "decimal": pl.Float64,
    "moeda": pl.Decimal(precision=38, scale=2),
    "data": pl.Date,
    "mes_ano": pl.Date,
    "sim_nao": pl.Boolean,
}


def _typed(value: Any, kind: str) -> Any:
    if value is None:
        return None
    if kind in ("data", "mes_ano"):
        return date.fromisoformat(value)
    if kind == "moeda":
        return Decimal(value)
    if kind == "decimal":
        return float(value)
    return value


def _doc_id(result: dict[str, Any]) -> str:
    return str(result.get("assinatura", ""))[:12]


def _first_page(origin: list[dict[str, Any]]) -> int | None:
    return origin[0]["p"] + 1 if origin else None


def _campos(recipe: Recipe, chosen: list[DocRun]) -> pl.DataFrame:
    """Uma linha por documento."""
    schema: dict[str, Any] = {
        "documento": pl.Utf8,
        "documento_id": pl.Utf8,
        "situacao": pl.Utf8,
        "motivo": pl.Utf8,
    }
    schema |= {f.nome: _POLARS[f.tipo] for f in recipe.campos}
    schema |= {"corrigidos": pl.Utf8, "revisao": pl.Int64}
    rows = []
    for d in chosen:
        row: dict[str, Any] = {
            "documento": d.name,
            "documento_id": _doc_id(d.result),
            "situacao": STATE_LABELS.get(d.result["estado"], d.result["estado"]),
            "motivo": d.result.get("motivo", ""),
        }
        by_name = {f["nome"]: f for f in d.result["campos"]}
        for spec in recipe.campos:
            item = by_name.get(spec.nome)
            row[spec.nome] = (
                _typed(item["valor"], spec.tipo) if item and item["estado"] == ENCONTRADO else None
            )
        row |= {"corrigidos": ", ".join(d.corrected), "revisao": recipe.revisao}
        rows.append(row)
    return pl.DataFrame(rows, schema=schema, orient="row")


def _items(source: PdfSource, recipe: Recipe, t_index: int, chosen: list[DocRun]) -> pl.DataFrame:
    """Uma linha por item da tabela, com o documento de origem."""
    spec = recipe.tabelas[t_index]
    schema: dict[str, Any] = {"documento": pl.Utf8, "documento_id": pl.Utf8, "linha": pl.Int64}
    schema |= {c.nome: _POLARS[c.tipo] for c in spec.colunas}
    if source.page_column:
        schema["pagina"] = pl.Int64
    schema |= {"duvida": pl.Utf8, "revisao": pl.Int64}
    rows = []
    for d in chosen:
        tables = d.result["tabelas"]
        if t_index >= len(tables):
            continue
        for n, line in enumerate(tables[t_index]["linhas"], start=1):
            cells = line["celulas"]
            r: dict[str, Any] = {"documento": d.name, "documento_id": _doc_id(d.result), "linha": n}
            for col in spec.colunas:
                cell = cells.get(col.nome, {})
                r[col.nome] = _typed(cell.get("valor"), col.tipo) if not cell.get("erro") else None
            if source.page_column:
                r["pagina"] = _first_page(next((c["origem"] for c in cells.values() if c["origem"]), []))
            r |= {"duvida": line["duvida"] or "", "revisao": recipe.revisao}
            rows.append(r)
    return pl.DataFrame(rows, schema=schema, orient="row")


_FAILURE_SCHEMA = {
    "documento": pl.Utf8,
    "documento_id": pl.Utf8,
    "situacao": pl.Utf8,
    "item": pl.Utf8,
    "nome": pl.Utf8,
    "estado": pl.Utf8,
    "motivo": pl.Utf8,
    "pagina": pl.Int64,
    "revisao": pl.Int64,
}


def _doc_failures(d: DocRun, rev: int) -> list[dict[str, Any]]:
    base = {
        "documento": d.name,
        "documento_id": _doc_id(d.result),
        "situacao": STATE_LABELS[d.result["estado"]],
    }
    if d.result.get("erro"):
        return [
            base
            | {
                "item": "documento",
                "nome": "",
                "estado": "Não suportado",
                "motivo": d.result["motivo"],
                "pagina": None,
                "revisao": rev,
            }
        ]
    rows = []
    for item in d.result["campos"]:
        if item["estado"] != ENCONTRADO:
            origin = item["candidatos"][0]["origem"] if item["candidatos"] else []
            rows.append(
                base
                | {
                    "item": "campo",
                    "nome": item["nome"],
                    "estado": FIELD_LABELS[item["estado"]],
                    "motivo": item["motivo"],
                    "pagina": _first_page(origin),
                    "revisao": rev,
                }
            )
    for table in d.result["tabelas"]:
        if table["problema"]:
            rows.append(
                base
                | {
                    "item": "tabela",
                    "nome": table["nome"],
                    "estado": "Ajustar",
                    "motivo": table["problema"],
                    "pagina": None,
                    "revisao": rev,
                }
            )
        for n, line in enumerate(table["linhas"], start=1):
            if line["duvida"]:
                origin = next((c["origem"] for c in line["celulas"].values() if c["origem"]), [])
                rows.append(
                    base
                    | {
                        "item": "linha",
                        "nome": f"{table['nome']} #{n}",
                        "estado": "Revisar",
                        "motivo": line["duvida"],
                        "pagina": _first_page(origin),
                        "revisao": rev,
                    }
                )
    return rows


_ORIGIN_SCHEMA = {
    "documento": pl.Utf8,
    "documento_id": pl.Utf8,
    "saida": pl.Utf8,
    "linha": pl.Int64,
    "coluna": pl.Utf8,
    "texto": pl.Utf8,
    "pagina": pl.Int64,
    "x0": pl.Float64,
    "y0": pl.Float64,
    "x1": pl.Float64,
    "y1": pl.Float64,
    "regra": pl.Utf8,
    "revisao": pl.Int64,
}


def _place(part: dict[str, Any]) -> dict[str, Any]:
    x0, y0, x1, y1 = part["b"]
    return {"pagina": part["p"] + 1, "x0": x0, "y0": y0, "x1": x1, "y1": y1}


def _doc_origins(d: DocRun, recipe: Recipe, rules: dict[str, str]) -> list[dict[str, Any]]:
    doc = {"documento": d.name, "documento_id": _doc_id(d.result), "revisao": recipe.revisao}
    rows = []
    for item in d.result["campos"]:
        if item["estado"] != ENCONTRADO:
            continue
        cell = doc | {"saida": MAIN_OUTPUT, "linha": 1, "coluna": item["nome"], "texto": item["texto"]}
        if item.get("corrigido"):
            nowhere = {"pagina": None, "x0": None, "y0": None, "x1": None, "y1": None}
            rows.append(cell | nowhere | {"regra": "corrigido só neste documento"})
            continue
        rows += [
            cell | _place(part) | {"regra": rules.get(item["nome"], "")}
            for part in item["candidatos"][0]["origem"]
        ]
    for t_index, spec in enumerate(recipe.tabelas):
        if t_index >= len(d.result["tabelas"]):
            continue
        for n, line in enumerate(d.result["tabelas"][t_index]["linhas"], start=1):
            for col, c in line["celulas"].items():
                where = doc | {
                    "saida": f"itens_{spec.nome}",
                    "linha": n,
                    "coluna": col,
                    "texto": c["texto"],
                    "regra": "tabela",
                }
                rows += [where | _place(part) for part in c["origem"]]
    return rows


def build_outputs(source: PdfSource, recipe: Recipe, docs: list[DocRun]) -> dict[str, pl.DataFrame]:
    """As saídas da fonte (RF-3770). A política decide quais documentos entram em campos, itens e origem."""
    chosen = [d for d in docs if source.policy != "aprovados" or d.result["estado"] == APROVADO]
    out = {MAIN_OUTPUT: _campos(recipe, chosen)}
    for t_index, spec in enumerate(recipe.tabelas):
        out[f"itens_{spec.nome}"] = _items(source, recipe, t_index, chosen)
    failures = [row for d in docs for row in _doc_failures(d, recipe.revisao)]  # o motivo, nunca o conteúdo
    out["falhas"] = pl.DataFrame(failures, schema=_FAILURE_SCHEMA, orient="row")
    rules = {f.nome: describe_rule(f.regra.model_dump()) for f in recipe.campos}
    origins = [row for d in chosen for row in _doc_origins(d, recipe, rules)]
    out["origem"] = pl.DataFrame(origins, schema=_ORIGIN_SCHEMA, orient="row")
    return out


def describe_rule(rule: dict[str, Any]) -> str:
    """Como encontrar, em linguagem simples (a mesma frase da tela)."""
    if rule["tipo"] == "posicao":
        return f"posição fixa na página {rule['pagina'] + 1} (frágil)"
    where = "à direita de" if rule.get("direcao") == "direita" else "abaixo de"
    labels = " ou ".join(f"“{r}”" for r in rule["rotulos"])
    if rule["tipo"] == "secao":
        return f"{where} {labels}, dentro de “{rule['inicio'][0]}”"
    return f"{where} {labels}"


def stop_message(source: PdfSource, docs: list[DocRun]) -> str:
    failed = [d for d in docs if d.result["estado"] == FALHOU]
    shown = "; ".join(f"{d.name} ({d.result.get('motivo', '')})" for d in failed[:5])
    more = f" e mais {len(failed) - 5}" if len(failed) > 5 else ""
    return (
        f"{len(failed)} de {len(docs)} documento(s) de '{source.name}' falharam: {shown}{more}. "
        "A política desta fonte é parar a execução. Corrija na vista Dados, ou leia a saída 'falhas' para ver o "
        "relatório, ou troque a política para entregar só os aprovados."
    )
