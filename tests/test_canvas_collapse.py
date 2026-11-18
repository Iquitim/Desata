"""Spec 041, RF-4104: recolher caixa e etapa é só desenho."""

from prodata.domain.workflow import Workflow
from prodata.engine.graph import upstream_signature


def _wf(collapsed: bool) -> Workflow:
    return Workflow.model_validate(
        {
            "id": "t",
            "containers": [
                {"id": "c1", "title": "Etapa", "collapsed": collapsed, "width": 600, "height": 300}
            ],
            "nodes": [
                {"id": "a", "type": "io.browse", "x": 20, "y": 40, "collapsed": collapsed},
                {"id": "b", "type": "io.browse", "x": 260, "y": 40},
            ],
            "edges": [{"id": "ab", "source": "a", "target": "b"}],
        }
    )


def test_old_files_open_expanded() -> None:
    wf = Workflow.model_validate(
        {"id": "t", "containers": [{"id": "c"}], "nodes": [{"id": "a", "type": "io.browse"}]}
    )
    assert wf.containers[0].collapsed is False
    assert wf.nodes[0].collapsed is False


def test_collapsing_keeps_the_cache_signature() -> None:
    assert upstream_signature(_wf(False), "b") == upstream_signature(_wf(True), "b")


def test_collapsed_state_is_saved() -> None:
    data = _wf(True).model_dump(by_alias=True)
    assert data["containers"][0]["collapsed"] is True
    assert data["nodes"][0]["collapsed"] is True
    assert data["nodes"][1]["collapsed"] is False


def test_item_names_and_collapsed_keep_the_cache_signature() -> None:
    """RF-4108: nome e recolhido dos blocos de lista ficam em `_ui`, que o cache não olha."""

    def wf(ui: dict[str, object] | None) -> Workflow:
        item: dict[str, object] = {"target": "new", "column": "x", "expression": "1"}
        if ui:
            item["_ui"] = ui
        return Workflow.model_validate(
            {"id": "t", "nodes": [{"id": "f", "type": "prep.formula", "config": {"formulas": [item]}}]}
        )

    plain = upstream_signature(wf(None), "f")
    assert upstream_signature(wf({"name": "Receita anual", "collapsed": True}), "f") == plain
    changed = wf(None)
    changed.nodes[0].config["formulas"][0]["expression"] = "2"
    assert upstream_signature(changed, "f") != plain
