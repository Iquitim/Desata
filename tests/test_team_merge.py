"""Juntar duas versões caixa por caixa (spec 048, RF-4821..4825, CA-05)."""

from __future__ import annotations

from typing import Any

from prodata.domain.workflow import Workflow
from prodata.team.merge import apply, merge


def wf(
    nodes: list[dict[str, Any]], edges: list[tuple[str, str]] | None = None, name: str = "Fechamento"
) -> Workflow:
    return Workflow.model_validate({
        "id": "fechamento", "name": name, "nodes": nodes,
        "edges": [{"id": f"e_{s}_{t}", "source": s, "target": t} for s, t in (edges or [])],
    })  # fmt: skip


def node(node_id: str, x: float = 0, **config: Any) -> dict[str, Any]:
    kind = "prep.filter" if node_id.startswith("filtro") else "prep.select"
    return {"id": node_id, "type": kind, "x": x, "y": 0, "config": config}


BASE = wf([node("entrada"), node("filtro", expression="[valor] > 0"), node("resumo")],
          [("entrada", "filtro"), ("filtro", "resumo")])  # fmt: skip


def test_changes_in_different_boxes_join_by_themselves() -> None:
    mine = wf(
        [node("entrada"), node("filtro", expression="[valor] > 10"), node("resumo")],
        [("entrada", "filtro"), ("filtro", "resumo")],
    )
    theirs = wf(
        [node("entrada"), node("filtro", expression="[valor] > 0"), node("resumo", fields=["uf"])],
        [("entrada", "filtro"), ("filtro", "resumo")],
    )
    plan = merge(BASE, mine, theirs)
    assert plan.conflitos == []
    assert {(a.id, a.de, a.acao) for a in plan.auto} == {
        ("filtro", "minha", "mudou"),
        ("resumo", "dele", "mudou"),
    }
    joined, dropped = apply(BASE, mine, theirs, {})
    by_id = {n.id: n for n in joined.nodes}
    assert (
        by_id["filtro"].config["expression"] == "[valor] > 10"
        and by_id["resumo"].config["fields"] == ["uf"]
        and dropped == 0
    )


def test_same_box_changed_by_both_asks_and_applies_the_choice() -> None:
    mine = wf(
        [node("entrada"), node("filtro", expression="[valor] > 10"), node("resumo")],
        [("entrada", "filtro"), ("filtro", "resumo")],
    )
    theirs = wf(
        [node("entrada"), node("filtro", x=500, expression="[valor] > 100"), node("resumo")],
        [("entrada", "filtro"), ("filtro", "resumo")],
    )
    plan = merge(BASE, mine, theirs)
    assert [(c.id, c.caso) for c in plan.conflitos] == [("filtro", "mudaram_os_dois")]
    assert "[valor] > 10" in (plan.conflitos[0].minha or "") and "[valor] > 100" in (
        plan.conflitos[0].dele or ""
    )
    kept_mine, _ = apply(BASE, mine, theirs, {})
    took_theirs, _ = apply(BASE, mine, theirs, {"filtro": "dele"})
    assert {n.id: n for n in kept_mine.nodes}["filtro"].config["expression"] == "[valor] > 10"
    chosen = {n.id: n for n in took_theirs.nodes}["filtro"]
    assert chosen.config["expression"] == "[valor] > 100" and chosen.x == 0  # a posição fica a minha


def test_changed_by_one_and_deleted_by_the_other_asks() -> None:
    mine = wf([node("entrada"), node("resumo")], [])
    theirs = wf(
        [node("entrada"), node("filtro", expression="[valor] > 5"), node("resumo")],
        [("entrada", "filtro"), ("filtro", "resumo")],
    )
    plan = merge(BASE, mine, theirs)
    assert [(c.id, c.caso, c.minha) for c in plan.conflitos] == [("filtro", "minha_saiu", None)]
    gone, dropped = apply(BASE, mine, theirs, {"filtro": "minha"})
    assert "filtro" not in {n.id for n in gone.nodes} and not gone.edges and dropped == 0
    back, _ = apply(BASE, mine, theirs, {"filtro": "dele"})
    assert "filtro" in {n.id for n in back.nodes}


def test_box_deleted_only_by_me_stays_deleted() -> None:
    mine = wf([node("entrada"), node("resumo")], [])
    joined, _ = apply(BASE, mine, BASE, {})
    assert [n.id for n in joined.nodes] == ["entrada", "resumo"]


def test_new_boxes_and_wires_from_both_sides() -> None:
    mine = wf(
        [*BASE.model_dump()["nodes"], node("novo_meu")],
        [("entrada", "filtro"), ("filtro", "resumo"), ("resumo", "novo_meu")],
    )
    theirs = wf(
        [*BASE.model_dump()["nodes"], node("novo_dele")], [("entrada", "filtro"), ("resumo", "novo_dele")]
    )
    plan = merge(BASE, mine, theirs)
    assert plan.conflitos == []
    joined, _ = apply(BASE, mine, theirs, {})
    assert {n.id for n in joined.nodes} >= {"novo_meu", "novo_dele"}
    links = {(e.source, e.target) for e in joined.edges}
    assert (
        ("resumo", "novo_meu") in links
        and ("resumo", "novo_dele") in links
        and ("filtro", "resumo") not in links
    )


def test_same_change_on_both_sides_is_not_a_conflict() -> None:
    same = wf(
        [node("entrada"), node("filtro", expression="[valor] > 7"), node("resumo")],
        [("entrada", "filtro"), ("filtro", "resumo")],
    )
    assert merge(BASE, same, same.model_copy(deep=True)).conflitos == []


def test_without_base_every_different_box_is_a_choice() -> None:
    mine = wf([node("entrada"), node("filtro", expression="[valor] > 10")], [("entrada", "filtro")])
    theirs = wf(
        [node("entrada"), node("filtro", expression="[valor] > 0"), node("resumo")], [("entrada", "filtro")]
    )
    plan = merge(None, mine, theirs)
    assert plan.sem_base and {c.id for c in plan.conflitos} == {"filtro", "resumo"}


def test_flow_name_changed_only_by_colleague_comes_along() -> None:
    theirs = BASE.model_copy(update={"name": "Fechamento do mês"})
    joined, _ = apply(BASE, BASE.model_copy(deep=True), theirs, {})
    assert joined.name == "Fechamento do mês"


def test_defaults_filled_by_the_screen_are_not_a_change() -> None:
    """A tela completa a configuração com os padrões ao abrir: isso não pode parecer mudança minha."""
    from prodata.nodes import REGISTRY

    filled = REGISTRY["prep.filter"].config().model_dump(mode="json") | {"expression": "[valor] > 0"}
    mine = wf(
        [node("entrada"), {**node("filtro"), "config": filled}, node("resumo")],
        [("entrada", "filtro"), ("filtro", "resumo")],
    )
    theirs = wf(
        [node("entrada"), node("filtro", expression="[valor] > 50"), node("resumo")],
        [("entrada", "filtro"), ("filtro", "resumo")],
    )
    plan = merge(BASE, mine, theirs)
    assert plan.conflitos == [] and [(a.id, a.de) for a in plan.auto] == [("filtro", "dele")]


def test_api_merge_apply_keeps_both_sides(client: Any, tmp_path: Any) -> None:
    folder = tmp_path / "Compartilhada"
    folder.mkdir()
    sid = client.post(
        "/api/equipe/espacos", json={"acao": "criar", "caminho": str(folder), "nome": "Time"}
    ).json()["id"]
    flow = {"id": "fx", "name": "F", "edges": [], "nodes": [
        {"id": "n1", "type": "prep.select", "config": {}},
        {"id": "q1", "type": "transform.sql_query", "config": {"sql": "SELECT 1"}}]}  # fmt: skip
    url = f"/api/equipe/espacos/{sid}/fluxos/fx"
    client.put(url, json=flow)
    base = client.get(f"{url}/abrir").json()["sha256"]
    theirs = {**flow, "nodes": [flow["nodes"][0], {**flow["nodes"][1], "config": {"sql": "SELECT 2"}}]}
    client.put(url, json=theirs)
    mine = {**flow, "nodes": [{**flow["nodes"][0], "label": "Colunas"}, flow["nodes"][1]]}
    plan = client.post(f"{url}/juntar", json={"atual": mine, "base": base}).json()
    assert plan["conflitos"] == [] and len(plan["auto"]) == 2, plan
    res = client.post(f"{url}/juntar/aplicar", json={"atual": mine, "base": base}).json()
    nodes = {n["id"]: n for n in res["fluxo"]["nodes"]}
    assert nodes["n1"]["label"] == "Colunas" and nodes["q1"]["config"]["sql"] == "SELECT 2"
