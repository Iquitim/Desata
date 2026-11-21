"""Mudanças no formato das fontes (spec 046, RF-4601..4609).

Puro (sem HTTP): lembra o formato de uma tabela, compara com o atual, sugere renomes só com sinal forte, acha as
caixas que usam uma coluna (pela descrição declarativa das ferramentas e pelas fórmulas) e troca a coluna nelas.
"""

from __future__ import annotations

import re
import types
import typing
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import polars as pl
from pydantic import BaseModel

from prodata.domain.schemas import ColumnSpec, RememberedSchema
from prodata.engine.convert import convert
from prodata.engine.formula import _COLUMN_REF, _STRING_LITERAL
from prodata.engine.profiling import simple_type

# Caixas que leem uma fonte de fora: o formato delas é lembrado e comparado.
SOURCE_TYPES = frozenset({"io.input_data", "io.input_folder", "io.database_input"})
OUTPUT_TYPES = frozenset({"io.output_data"})
_POLARS = {"Int64": pl.Int64, "Float64": pl.Float64, "Boolean": pl.Boolean, "Date": pl.Date,
           "Datetime": pl.Datetime, "String": pl.String}  # fmt: skip
_ROW_PREFIX = re.compile(r"^(Row[+-]\d+:)(.+)$")


def schema_of(df: pl.DataFrame) -> list[ColumnSpec]:
    return [ColumnSpec(name=name, type=simple_type(dtype)) for name, dtype in df.schema.items()]


# ---------------------------------------------------------------- diferença


@dataclass
class Retyped:
    name: str
    old: str
    new: str
    examples: list[str] = field(default_factory=list)


@dataclass
class SchemaDiff:
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    retyped: list[Retyped] = field(default_factory=list)
    renames: list[tuple[str, str]] = field(default_factory=list)  # (antiga, nova): só sugestão

    @property
    def empty(self) -> bool:
        return not (self.added or self.removed or self.retyped)


def diff(old: list[ColumnSpec], new: list[ColumnSpec]) -> SchemaDiff:
    before = {c.name: c for c in old}
    after = {c.name: c for c in new}
    out = SchemaDiff(
        added=[c.name for c in new if c.name not in before],
        removed=[c.name for c in old if c.name not in after],
        retyped=[Retyped(c.name, before[c.name].type, c.type) for c in new
                 if c.name in before and before[c.name].type != c.type],
    )  # fmt: skip
    out.renames = rename_hints(old, new, out.removed, out.added)
    return out


def rename_hints(
    old: list[ColumnSpec], new: list[ColumnSpec], removed: list[str], added: list[str]
) -> list[tuple[str, str]]:
    """Renome só com sinal forte (RF-4604): o mesmo tipo e, havendo mais de uma candidata, a mesma posição.
    Nunca só pela semelhança do nome."""
    type_old = {c.name: c.type for c in old}
    type_new = {c.name: c.type for c in new}
    pos_old = {c.name: i for i, c in enumerate(old)}
    pos_new = {c.name: i for i, c in enumerate(new)}
    hints: list[tuple[str, str]] = []
    used: set[str] = set()
    for gone in removed:
        same_type = [a for a in added if type_new[a] == type_old[gone] and a not in used]
        if len(same_type) == 1 and len([g for g in removed if type_old[g] == type_old[gone]]) == 1:
            pick: str | None = same_type[0]
        else:
            pick = next((a for a in same_type if pos_new[a] == pos_old[gone]), None)
        if pick:
            hints.append((gone, pick))
            used.add(pick)
    return hints


def type_examples(series: pl.Series, old_type: str) -> list[str]:
    """Até 3 valores que impedem o tipo antigo (ex.: "N/D" numa coluna que era número)."""
    target = _POLARS.get(old_type)
    if target is None or old_type == "String":
        return []
    return convert(series, target).examples[:3]


# ---------------------------------------------------------------- onde a configuração cita colunas


@dataclass(frozen=True)
class _Slot:
    """Um lugar da configuração que cita colunas: ``path`` até o valor, ``kind`` e de qual porta vêm."""

    path: tuple[str | int, ...]
    kind: str  # column | columns | expression | select | sql
    port: str | None


def _item_model(annotation: Any) -> type[BaseModel] | None:
    annotation = _unwrap(annotation)
    if typing.get_origin(annotation) is list:
        (item,) = typing.get_args(annotation) or (None,)
        if isinstance(item, type) and issubclass(item, BaseModel):
            return item
    return None


def _unwrap(annotation: Any) -> Any:
    if typing.get_origin(annotation) in (typing.Union, types.UnionType):
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return annotation


def _slots(model: type[BaseModel], data: Any, prefix: tuple[str | int, ...] = ()) -> Iterator[_Slot]:
    if not isinstance(data, dict):
        return
    for name, info in model.model_fields.items():
        extra = info.json_schema_extra if isinstance(info.json_schema_extra, dict) else {}
        widget = extra.get("widget")
        raw_port = extra.get("port")
        port = raw_port if isinstance(raw_port, str) else None
        value = data.get(name)
        path = (*prefix, name)
        item = _item_model(info.annotation)
        if item is not None and isinstance(value, list):
            for i, element in enumerate(value):
                yield from _slots(item, element, (*path, i))
            if widget == "select_columns":
                yield _Slot(path, "select", port)
            continue
        if widget in ("column", "columns", "expression", "sql"):
            yield _Slot(path, widget, port)
        elif widget == "select_columns":
            yield _Slot(path, "select", port)


def _get(data: Any, path: tuple[str | int, ...]) -> Any:
    for key in path:
        if isinstance(key, int):
            data = data[key] if isinstance(data, list) and key < len(data) else None
        else:
            data = data.get(key) if isinstance(data, dict) else None
    return data


def _set(data: Any, path: tuple[str | int, ...], value: Any) -> None:
    for key in path[:-1]:
        data = data[key]
    data[path[-1]] = value


def expression_columns(expression: str) -> set[str]:
    """Colunas citadas numa fórmula: ``[coluna]`` e ``[Row-1:coluna]``; constantes ``[#nome]`` não contam."""
    masked = _STRING_LITERAL.sub(lambda m: " " * len(m.group()), expression or "")
    out = set()
    for token in _COLUMN_REF.findall(masked):
        m = _ROW_PREFIX.match(token)
        name = m.group(2) if m else token
        if not name.startswith("#"):
            out.add(name)
    return out


def rename_in_expression(expression: str, old: str, new: str) -> str:
    """Troca ``[old]`` (e ``[Row-k:old]``) por ``new``, fora dos textos entre aspas; o resto fica igual."""
    masked = _STRING_LITERAL.sub(lambda m: " " * len(m.group()), expression or "")
    pieces: list[str] = []
    last = 0
    for m in _COLUMN_REF.finditer(masked):
        token = expression[m.start(1) : m.end(1)]
        row = _ROW_PREFIX.match(token)
        name = row.group(2) if row else token
        if name != old:
            continue
        pieces.append(expression[last : m.start(1)])
        pieces.append((row.group(1) if row else "") + new)
        last = m.end(1)
    pieces.append(expression[last:])
    return "".join(pieces)


def _sql_mentions(sql: str, column: str) -> bool:
    return bool(re.search(rf'(?<![\w"]){re.escape(column)}(?![\w"])|"{re.escape(column)}"', sql or ""))


def _select_names(value: Any) -> set[str]:
    return {f.get("name", "") for f in value or [] if isinstance(f, dict)}


def node_refs(node_type: str, config: dict[str, Any], first_port: str | None) -> dict[str, set[str]]:
    """Colunas que a caixa cita, por porta de entrada (a porta do campo, ou a primeira entrada)."""
    from prodata.nodes import REGISTRY

    spec = REGISTRY.get(node_type)
    out: dict[str, set[str]] = {}
    if spec is None:
        return out
    for slot in _slots(spec.config, config):
        value = _get(config, slot.path)
        port = slot.port or first_port or "in"
        names: set[str] = set()
        if slot.kind == "column" and isinstance(value, str) and value:
            names = {value}
        elif slot.kind == "columns" and isinstance(value, list):
            names = {v for v in value if isinstance(v, str)}
        elif slot.kind == "expression" and isinstance(value, str):
            names = expression_columns(value)
        elif slot.kind == "select":
            names = _select_names(value)
        if names:
            out.setdefault(port, set()).update(names)
    return out


# ---------------------------------------------------------------- caixas atingidas


@dataclass
class Impact:
    """Para uma coluna: caixas que a usam (com as portas por onde ela chega) e caixas SQL que talvez usem."""

    nodes: dict[str, set[str]] = field(default_factory=dict)
    maybe: set[str] = field(default_factory=set)


def _cuts(node_type: str, config: dict[str, Any], column: str) -> bool:
    """A coluna deixa de existir com o mesmo nome depois desta caixa (Select ou Join que descarta ou renomeia)."""
    if node_type == "prep.select" or (node_type == "transform.join"):
        for rule in config.get("fields") or []:
            if (
                isinstance(rule, dict)
                and rule.get("name") == column
                and (rule.get("keep") is False or rule.get("rename"))
            ):
                return True
    if node_type == "transform.summarize":
        aggregated = {a.get("column") for a in config.get("aggregations") or [] if isinstance(a, dict)}
        return column not in set(config.get("group_by") or []) | aggregated
    if node_type == "transform.crosstab":
        return column not in set(config.get("group_by") or [])
    if node_type == "transform.transpose":
        return column not in set(config.get("keys") or [])
    return node_type in ("transform.sql_query", "flow.subflow") or node_type.startswith("ml.")


def impact(workflow: Any, source_id: str, columns: list[str]) -> dict[str, Impact]:
    """Por coluna da fonte: as caixas adiante que a usam, seguindo os fios enquanto ela tiver o mesmo nome."""
    from prodata.nodes import REGISTRY

    nodes = {n.id: n for n in workflow.nodes}
    out_edges: dict[str, list[Any]] = {}
    for e in workflow.edges:
        out_edges.setdefault(e.source, []).append(e)
    result: dict[str, Impact] = {}
    for column in columns:
        found = Impact()
        seen: set[tuple[str, str]] = set()
        queue = [source_id]
        while queue:
            current = queue.pop()
            for e in out_edges.get(current, []):
                target = nodes.get(e.target)
                if target is None or (target.id, e.target_handle) in seen:
                    continue
                seen.add((target.id, e.target_handle))
                spec = REGISTRY.get(target.type)
                first = spec.inputs[0].id if spec and spec.inputs else None
                refs = node_refs(target.type, target.config, first)
                if column in refs.get(e.target_handle, set()):
                    found.nodes.setdefault(target.id, set()).add(e.target_handle)
                if target.type == "transform.sql_query" and _sql_mentions(
                    target.config.get("sql", ""), column
                ):
                    found.maybe.add(target.id)
                if not _cuts(target.type, target.config, column):
                    queue.append(target.id)
        result[column] = found
    return result


# ---------------------------------------------------------------- trocar a coluna


def rename_column(
    config: dict[str, Any], node_type: str, ports: set[str], first_port: str | None, old: str, new: str
) -> bool:
    """Troca ``old`` por ``new`` nos campos da caixa que leem das portas indicadas. Devolve se mudou algo.
    O texto livre da caixa SQL nunca é alterado."""
    from prodata.nodes import REGISTRY

    spec = REGISTRY.get(node_type)
    if spec is None:
        return False
    changed = False
    for slot in list(_slots(spec.config, config)):
        if (slot.port or first_port or "in") not in ports:
            continue
        value = _get(config, slot.path)
        if slot.kind == "column" and value == old:
            _set(config, slot.path, new)
            changed = True
        elif slot.kind == "columns" and isinstance(value, list) and old in value:
            _set(config, slot.path, [new if v == old else v for v in value])
            changed = True
        elif slot.kind == "expression" and isinstance(value, str) and old in expression_columns(value):
            _set(config, slot.path, rename_in_expression(value, old, new))
            changed = True
        elif slot.kind == "select" and isinstance(value, list):
            for rule in value:
                if isinstance(rule, dict) and rule.get("name") == old:
                    rule["name"] = new
                    changed = True
    if node_type == "prep.select" and old in (config.get("order") or []):
        config["order"] = [new if v == old else v for v in config["order"]]
        changed = True
    return changed


# ---------------------------------------------------------------- o que a execução devolve


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def source_extra(workflow: Any, node: Any, frame: pl.DataFrame) -> dict[str, Any]:
    """O formato atual da fonte e, se mudou em relação ao lembrado, a diferença com as caixas atingidas."""
    current = schema_of(frame)
    extra: dict[str, Any] = {"schema": {"out": [c.model_dump() for c in current]}}
    remembered = workflow.schemas.get(node.id)
    old = remembered.ports.get("out") if remembered else None
    if not old:
        return extra  # primeira leitura: só lembra (RF-4602)
    d = diff(old, current)
    if d.empty:
        return extra
    for r in d.retyped:
        r.examples = type_examples(frame[r.name], r.old)
    watched = [*d.removed, *(r.name for r in d.retyped)]
    found = impact(workflow, node.id, watched)
    extra["schema_change"] = {
        "added": d.added,
        "removed": d.removed,
        "retyped": [{"name": r.name, "old": r.old, "new": r.new, "examples": r.examples} for r in d.retyped],
        "renames": [
            {
                "old": a,
                "new": b,
                "type": next(c.type for c in current if c.name == b),
                "values": [str(v) for v in frame[b].drop_nulls().head(3).to_list()],
            }
            for a, b in d.renames
        ],
        "affected": {c: {n: sorted(p) for n, p in found[c].nodes.items()} for c in watched},
        "maybe": {c: sorted(found[c].maybe) for c in watched if found[c].maybe},
    }
    return extra


def unattended_stop(change: dict[str, Any], policy: str, source_name: str) -> str | None:
    """Por que uma execução sem ninguém olhando deve parar antes de gravar saídas (RF-4607), ou None."""
    for column in change.get("removed", []):
        used = change.get("affected", {}).get(column) or {}
        if used:
            return (f"A coluna '{column}' sumiu de {source_name} (usada em {_plural(len(used), 'caixa', 'caixas')}). "
                    "Nada foi gravado: abra o fluxo para trocar a coluna ou aceitar o formato novo.")  # fmt: skip
    added = change.get("added", [])
    if added and policy == "parar":
        names = ", ".join(f"'{c}'" for c in added[:5]) + ("…" if len(added) > 5 else "")
        return (f"Apareceu {_plural(len(added), 'coluna nova', 'colunas novas')} em {source_name}: {names}. "
                "A entrada está configurada para parar nesse caso; nada foi gravado.")  # fmt: skip
    return None


def output_change(
    remembered: RememberedSchema | None, current: dict[str, list[ColumnSpec]]
) -> tuple[dict[str, Any] | None, str]:
    """Diferença entre o que o Output gravou da última vez e o que vai gravar agora (RF-4608), com a frase."""
    if remembered is None:
        return None, ""
    parts: list[str] = []
    change: dict[str, Any] = {}
    for port, columns in current.items():
        old = remembered.ports.get(port)
        if not old:
            continue
        d = diff(old, columns)
        if d.empty:
            continue
        change[port] = {"added": d.added, "removed": d.removed,
                        "retyped": [{"name": r.name, "old": r.old, "new": r.new} for r in d.retyped]}  # fmt: skip
        if d.added:
            parts.append(
                f"{_plural(len(d.added), 'coluna nova', 'colunas novas')} ({', '.join(d.added[:4])})"
            )
        if d.removed:
            parts.append(
                f"{_plural(len(d.removed), 'coluna a menos', 'colunas a menos')} ({', '.join(d.removed[:4])})"
            )
        if d.retyped:
            parts.append(f"{_plural(len(d.retyped), 'coluna com outro tipo', 'colunas com outro tipo')} "
                         f"({', '.join(r.name for r in d.retyped[:4])})")  # fmt: skip
    if not change:
        return None, ""
    return change, ("O arquivo vai sair com formato diferente da última gravação: " + "; ".join(parts)
                    + ". Quem consome este arquivo (um relatório, outro fluxo) pode ser afetado.")  # fmt: skip
