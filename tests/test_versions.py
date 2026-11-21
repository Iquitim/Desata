"""Versões anteriores do fluxo (spec 046, RF-4631..4634)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest
from fastapi.testclient import TestClient

from prodata.domain.samples import SourceSample
from prodata.domain.workflow import Workflow
from prodata.errors import InvalidInputError, NotFoundError
from prodata.services.versions import MAX_VERSIONS, VersionStore, changes_between


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 20, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kw: float) -> None:
        self.now += timedelta(**kw)


def flow(nodes: int = 2, name: str = "Vendas") -> Workflow:
    return Workflow.model_validate(
        {
            "id": "vendas",
            "name": name,
            "nodes": [{"id": f"n{i}", "type": "prep.select", "x": i * 100, "y": 0} for i in range(nodes)],
            "edges": [{"id": f"e{i}", "source": f"n{i}", "target": f"n{i + 1}"} for i in range(nodes - 1)],
        }
    )


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def versions(tmp_path: Path, clock: Clock) -> VersionStore:
    return VersionStore(tmp_path / "versoes", clock=clock)


def test_manual_save_records_and_identical_does_not(versions: VersionStore, clock: Clock) -> None:
    assert versions.record(flow(), "manual") is not None
    clock.advance(minutes=1)
    assert versions.record(flow(), "manual") is None  # igual à última: nada novo para guardar
    clock.advance(minutes=1)
    assert versions.record(flow(3), "manual") is not None
    assert [v.node_count for v in versions.history("vendas")] == [3, 2]


def test_autosave_keeps_one_version_per_ten_minutes(versions: VersionStore, clock: Clock) -> None:
    versions.record(flow(1), "auto")
    clock.advance(minutes=4)
    assert versions.record(flow(2), "auto") is None
    clock.advance(minutes=7)
    assert versions.record(flow(3), "auto") is not None
    clock.advance(minutes=1)
    assert versions.record(flow(4), "manual") is not None  # o Salvar manual sempre guarda
    assert [v.origin for v in versions.history("vendas")] == ["manual", "auto", "auto"]


def test_keeps_only_the_most_recent(versions: VersionStore, clock: Clock) -> None:
    for i in range(MAX_VERSIONS + 5):
        versions.record(flow(1, name=f"v{i}"), "manual")
        clock.advance(seconds=1)
    listed = versions.history("vendas")
    assert len(listed) == MAX_VERSIONS
    assert listed[0].name == f"v{MAX_VERSIONS + 4}" and listed[-1].name == "v5"


def test_version_never_keeps_the_data_sample(versions: VersionStore) -> None:
    wf = flow()
    wf.samples["dataset:a"] = SourceSample.of(pl.DataFrame({"a": [1, 2]}), "a.csv")
    info = versions.record(wf, "manual")
    assert info is not None
    assert versions.get("vendas", info.id).samples == {}


def test_example_and_lessons_do_not_keep_versions(versions: VersionStore) -> None:
    assert versions.record(flow().model_copy(update={"id": "demo_pipeline_360"}), "manual") is None
    assert versions.record(flow().model_copy(update={"id": "licao_ranking"}), "manual") is None


def test_changes_summary() -> None:
    old = flow(3)
    new = flow(3, name="Vendas 2")
    new.nodes[0].x += 50  # mexeu de lugar
    new.nodes[1].config = {"fields": [{"name": "a", "keep": False}]}  # mudou a configuração
    new.nodes = [n for n in new.nodes if n.id != "n2"]  # removida
    new.edges = [e for e in new.edges if e.target != "n2"]
    new.nodes.append(new.nodes[0].model_copy(update={"id": "n9"}))  # nova
    changes = changes_between(old, new)
    assert (changes.added, changes.removed, changes.changed, changes.moved) == (1, 1, 1, 1)
    assert (changes.wires_added, changes.wires_removed, changes.renamed) == (0, 1, True)
    assert changes_between(old, old).empty


def test_bad_ids_are_refused(versions: VersionStore) -> None:
    with pytest.raises(InvalidInputError):
        versions.get("vendas", "../../segredo")
    with pytest.raises(InvalidInputError):
        versions.history("../fora")
    with pytest.raises(NotFoundError):
        versions.get("vendas", "20260101-000000-000000-manual")


# ---------------------------------------------------------------- API


def test_save_records_version_and_restore_flow(client: TestClient) -> None:
    wf = flow(3).model_dump(mode="json", by_alias=True)
    assert client.put("/api/workflows/vendas", json=wf).status_code == 200
    smaller = flow(1).model_dump(mode="json", by_alias=True)
    assert (
        client.put("/api/workflows/vendas?origem=auto", json=smaller).status_code == 200
    )  # cedo: não guarda
    listed = client.post("/api/workflows/vendas/versions/compare", json={"current": smaller}).json()
    assert len(listed) == 1 and listed[0]["origin"] == "manual" and listed[0]["node_count"] == 3
    assert listed[0]["changes"]["removed"] == 2
    back = client.get(f"/api/workflows/vendas/versions/{listed[0]['id']}").json()
    assert len(back["nodes"]) == 3
    # antes de restaurar, a tela guarda o que está aberto
    rec = client.post("/api/workflows/vendas/versions", json={"workflow": smaller, "origin": "restore"})
    assert rec.json()["origin"] == "restore"
    assert client.get("/api/workflows/vendas/versions/../../x").status_code == 404
    assert client.delete("/api/workflows/vendas").status_code == 204
    assert client.get("/api/workflows/vendas/versions").json() == []  # excluir o fluxo leva as versões


def test_each_file_has_its_own_history(versions: VersionStore, clock: Clock, tmp_path: Path) -> None:
    """Salvar como para outra pasta mantém o id do fluxo: o histórico não pode misturar as duas cópias."""
    a, b = str(tmp_path / "a" / "vendas.prodata.json"), str(tmp_path / "b" / "vendas.prodata.json")
    versions.record(flow(1), "manual", path=a)
    clock.advance(seconds=1)
    versions.record(flow(2), "manual", path=b)
    clock.advance(seconds=1)
    versions.record(flow(3), "manual")  # o mesmo id na biblioteca
    assert [v.node_count for v in versions.history("vendas", path=a)] == [1]
    assert [v.node_count for v in versions.history("vendas", path=b)] == [2]
    assert [v.node_count for v in versions.history("vendas")] == [3]
    # o caminho nunca é gravado em texto: só a impressão dele dá nome à pasta
    stored = [p.name for p in (tmp_path / "versoes" / "arquivos").iterdir()]
    assert len(stored) == 2 and all(len(name) == 32 and "vendas" not in name for name in stored)
    versions.delete_all("vendas")  # excluir da biblioteca não mexe no histórico dos arquivos
    assert versions.history("vendas") == [] and len(versions.history("vendas", path=a)) == 1


def test_file_history_through_the_api(client: TestClient, tmp_path: Path) -> None:
    target = tmp_path / "pasta" / "vendas.prodata.json"
    target.parent.mkdir()
    body = {"path": str(target), "workflow": flow(2).model_dump(mode="json", by_alias=True)}
    saved = client.post("/api/files/workflow/save", json=body).json()
    assert client.get("/api/workflows/vendas/versions").json() == []  # nada na biblioteca
    listed = client.get("/api/workflows/vendas/versions", params={"arquivo": saved["path"]}).json()
    assert len(listed) == 1
    got = client.get(f"/api/workflows/vendas/versions/{listed[0]['id']}", params={"arquivo": saved["path"]})
    assert len(got.json()["nodes"]) == 2
