"""Juntar duas versões de um fluxo caixa por caixa (spec 048, RF-4821..4825).

Compara a minha versão e a do colega com a versão de onde as duas partiram (a base):

- o que só um dos dois mudou entra sozinho: caixa nova, caixa excluída, configuração mudada, fio novo ou removido;
- o que os dois mudaram do mesmo jeito entra uma vez;
- o que os dois mudaram de jeitos diferentes vira uma **escolha** (a caixa inteira: a minha ou a dele), assim como a
  caixa que um mudou e o outro excluiu. A posição das caixas nunca pergunta: fica a minha.

Sem base conhecida (cópia de conflito sem histórico), toda caixa diferente vira uma escolha (RF-4825). Funções puras,
sobre os modelos ``Workflow``: a API só recalcula e aplica as escolhas.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from prodata.domain.workflow import Workflow
from prodata.nodes import REGISTRY

Side = Literal["minha", "dele"]
_SKIP_TOP = {"nodes", "edges", "containers", "samples", "id"}


class AutoChange(BaseModel):
    """Uma mudança juntada sozinha, para o resumo ("3 do Bruno, 5 suas")."""

    tipo: Literal["caixa", "fio", "etapa", "fluxo"]
    id: str
    rotulo: str
    de: Side
    acao: Literal["nova", "mudou", "saiu"]


class Conflict(BaseModel):
    """Uma caixa que os dois mexeram: a escolha é a caixa inteira."""

    id: str
    rotulo: str
    caso: Literal["mudaram_os_dois", "minha_saiu", "dele_saiu", "sem_base"]
    minha: str | None  # a configuração em palavras (None: a caixa saiu desse lado)
    dele: str | None
    diferencas: list[str] = Field(default_factory=list)


class MergeResult(BaseModel):
    auto: list[AutoChange] = Field(default_factory=list)
    conflitos: list[Conflict] = Field(default_factory=list)
    sem_base: bool = False
    fios_descartados: int = 0


_DEFAULTS: dict[str, dict[str, Any]] = {}


def _config(node: Any) -> dict[str, Any]:
    """A configuração completada com os padrões da ferramenta, como a tela faz ao abrir: um campo que só uma das
    versões traz explícito (com o valor padrão) não conta como mudança."""
    if node.type not in _DEFAULTS:
        spec = REGISTRY.get(node.type)
        try:
            _DEFAULTS[node.type] = spec.config().model_dump(mode="json") if spec is not None else {}
        except ValueError:  # ferramenta sem padrão completo (algum campo obrigatório)
            _DEFAULTS[node.type] = {}
    return {**_DEFAULTS[node.type], **node.config}


def _content(node: Any) -> str:
    data = {
        "type": node.type,
        "label": node.label or "",
        "disabled": bool(node.disabled),
        "config": _config(node),
    }
    return json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)


def _label(node: Any) -> str:
    spec = REGISTRY.get(node.type)
    return str(node.label or (spec.name if spec else node.type))


def _title(node_type: str, key: str) -> str:
    spec = REGISTRY.get(node_type)
    field = spec.config.model_fields.get(key) if spec is not None else None
    return str(field.title) if field is not None and field.title else key


def _short(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    text = " ".join(str(text).split())
    return text if len(text) <= 80 else f"{text[:77]}…"


def describe(node: Any, other: Any | None) -> tuple[str, list[str]]:
    """A caixa em palavras e, comparada com a outra, o que difere ("Expressão: `[valor] > 100`")."""
    if node is None:
        return "", []
    diffs: list[str] = []
    if other is not None:
        if (node.label or "") != (other.label or ""):
            diffs.append(f"Nome: {node.label or _label(node)}")
        if bool(node.disabled) != bool(other.disabled):
            diffs.append("Desabilitada" if node.disabled else "Habilitada")
        mine, theirs = _config(node), _config(other)
        for key in sorted(set(mine) | set(theirs)):
            if mine.get(key) != theirs.get(key):
                diffs.append(f"{_title(node.type, key)}: {_short(mine.get(key, ''))}")
    summary = "; ".join(diffs) if diffs else _label(node)
    return summary, diffs


def _edges(workflow: Workflow | None) -> dict[tuple[str, str, str, str], Any]:
    if workflow is None:
        return {}
    return {(e.source, e.source_handle, e.target, e.target_handle): e for e in workflow.edges}


def _three(base: Any, mine: Any, theirs: Any) -> tuple[str, Side | None]:
    """Decide um item: ``("igual"|"minha"|"dele"|"conflito", lado que mudou)``."""
    if mine == theirs:
        return "igual", None
    if base == mine:
        return "dele", "dele"
    if base == theirs:
        return "minha", "minha"
    return "conflito", None


def merge(base: Workflow | None, mine: Workflow, theirs: Workflow) -> MergeResult:
    result = MergeResult(sem_base=base is None)
    b_nodes = {n.id: n for n in base.nodes} if base else {}
    m_nodes = {n.id: n for n in mine.nodes}
    t_nodes = {n.id: n for n in theirs.nodes}
    for node_id in sorted(set(b_nodes) | set(m_nodes) | set(t_nodes)):
        b, m, t = b_nodes.get(node_id), m_nodes.get(node_id), t_nodes.get(node_id)
        keys = tuple(_content(x) if x is not None else None for x in (b, m, t))
        if base is None and keys[1] != keys[2]:
            outcome: str = "conflito"
            side: Side | None = None
        else:
            outcome, side = _three(*keys)
        label = _label(m or t or b)
        if outcome in ("minha", "dele") and side is not None:
            chosen = m if side == "minha" else t
            acao = "saiu" if chosen is None else "nova" if b is None else "mudou"
            result.auto.append(AutoChange(tipo="caixa", id=node_id, rotulo=label, de=side, acao=acao))
        elif outcome == "conflito":
            caso = (
                "sem_base"
                if base is None
                else "minha_saiu"
                if m is None
                else "dele_saiu"
                if t is None
                else "mudaram_os_dois"
            )
            mine_text, diffs_m = describe(m, t)
            their_text, diffs_t = describe(t, m)
            result.conflitos.append(Conflict(id=node_id, rotulo=label, caso=caso, minha=mine_text if m else None,
                                             dele=their_text if t else None, diferencas=diffs_m or diffs_t))  # fmt: skip
    b_e, m_e, t_e = _edges(base), _edges(mine), _edges(theirs)
    for key in sorted(set(m_e) ^ set(t_e)):
        side_e: Side = "minha" if key in m_e else "dele"
        in_base = key in b_e
        if base is not None and in_base:  # estava na base e um dos dois tirou
            result.auto.append(AutoChange(tipo="fio", id="→".join(key[::2]), rotulo=f"{key[0]} → {key[2]}",
                                          de="dele" if key in m_e else "minha", acao="saiu"))  # fmt: skip
        elif not in_base:
            result.auto.append(
                AutoChange(
                    tipo="fio", id="→".join(key[::2]), rotulo=f"{key[0]} → {key[2]}", de=side_e, acao="nova"
                )
            )
    return result


def apply(
    base: Workflow | None, mine: Workflow, theirs: Workflow, choices: dict[str, Side]
) -> tuple[Workflow, int]:
    """O fluxo juntado com as escolhas (caixa sem escolha fica com a minha). Devolve também quantos fios foram
    descartados por ligarem uma caixa que saiu."""
    plan = merge(base, mine, theirs)
    conflicted = {c.id for c in plan.conflitos}
    b_nodes = {n.id: n for n in base.nodes} if base else {}
    m_nodes = {n.id: n for n in mine.nodes}
    t_nodes = {n.id: n for n in theirs.nodes}
    order = [n.id for n in mine.nodes] + [n.id for n in theirs.nodes if n.id not in m_nodes]
    nodes = []
    for node_id in order:
        b, m, t = b_nodes.get(node_id), m_nodes.get(node_id), t_nodes.get(node_id)
        if node_id in conflicted:
            chosen = m if choices.get(node_id, "minha") == "minha" else t
        else:
            _, side = _three(*(None if x is None else _content(x) for x in (b, m, t)))
            chosen = t if side == "dele" else m  # "minha" ou igual: a minha (inclusive quando eu excluí)
        if chosen is None:
            continue
        if m is not None and chosen is not m:  # a posição fica a minha
            chosen = chosen.model_copy(update={"x": m.x, "y": m.y})
        nodes.append(chosen)
    alive = {n.id for n in nodes}
    b_e, m_e, t_e = _edges(base), _edges(mine), _edges(theirs)
    keep = [k for k in dict.fromkeys([*m_e, *t_e])
            if (k in m_e and k in t_e) or (k in m_e and (base is None or k not in b_e)) or (k in t_e and (base is None or k not in b_e))]  # fmt: skip
    edges = [m_e.get(k) or t_e[k] for k in keep]
    dropped = sum(1 for e in edges if e.source not in alive or e.target not in alive)
    edges = [e for e in edges if e.source in alive and e.target in alive]
    seen: set[str] = set()
    for i, e in enumerate(edges):  # dois fios diferentes com o mesmo id (um de cada lado): renomeia o segundo
        if e.id in seen:
            edges[i] = e.model_copy(update={"id": f"{e.id}_j{i}"})
        seen.add(edges[i].id)
    containers = _merge_containers(base, mine, theirs, alive)
    top = _merge_top(base, mine, theirs)
    merged = mine.model_copy(update={**top, "nodes": nodes, "edges": edges, "containers": containers})
    return Workflow.model_validate(merged.model_dump(mode="json", by_alias=True)), dropped


def _merge_containers(base: Workflow | None, mine: Workflow, theirs: Workflow, alive: set[str]) -> list[Any]:
    b = {c.id: c for c in (base.containers if base else [])}
    m = {c.id: c for c in mine.containers}
    t = {c.id: c for c in theirs.containers}
    out = []
    for cid in [*m, *(k for k in t if k not in m)]:
        keys = [None if x is None else x.model_dump_json() for x in (b.get(cid), m.get(cid), t.get(cid))]
        _, side = _three(*keys)
        chosen = t.get(cid) if side == "dele" else m.get(cid) or t.get(cid)
        if chosen is not None:
            out.append(chosen)
    return out


def _merge_top(base: Workflow | None, mine: Workflow, theirs: Workflow) -> dict[str, Any]:
    """Nome, descrição e o resto do fluxo: o que só o colega mudou entra; empate fica o meu."""
    b = base.model_dump(mode="json", by_alias=True) if base else {}
    m = mine.model_dump(mode="json", by_alias=True)
    t = theirs.model_dump(mode="json", by_alias=True)
    update: dict[str, Any] = {}
    for key in m:
        if key in _SKIP_TOP:
            continue
        _, side = _three(json.dumps(b.get(key), sort_keys=True, default=str) if base else None,
                         json.dumps(m.get(key), sort_keys=True, default=str),
                         json.dumps(t.get(key), sort_keys=True, default=str))  # fmt: skip
        if side == "dele" and base is not None:
            update[key] = getattr(theirs, key) if hasattr(theirs, key) else t.get(key)
    return update
