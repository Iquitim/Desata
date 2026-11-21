"""Espaço da equipe, marco 4 (spec 047, RF-4731..4733, RF-4741, RF-4742, RF-4761..4763): versões com autor,
"Atualizado por", confiança por diferença, conflito, cópias de conflito e envio adiado."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from prodata.domain.workflow import Workflow
from prodata.errors import ConflictError
from prodata.team.repository import HeldFileError, SpaceRepository
from prodata.team.versions import content_sha
from sync_sim import SyncSim
from test_team_roles import Person

Team = tuple[Person, Person, Path, str]


@pytest.fixture
def team(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Team:
    """Ana cria o espaço e Bruno pede para entrar (como em test_team_roles)."""
    folder = tmp_path / "pasta_da_equipe"
    folder.mkdir()
    ana = Person(tmp_path, "ana", "Ana Souza", monkeypatch)
    bruno = Person(tmp_path, "bruno", "Bruno Lima", monkeypatch)
    with ana.acting() as t:
        space_id = t.create(str(folder), "Controladoria")["id"]
    with bruno.acting() as t:
        t.join(str(folder))
    return ana, bruno, folder, space_id


def flow(name: str = "Fechamento", folder: str = "C:/relatorios", condition: str = "[valor] > 0") -> Workflow:
    return Workflow.model_validate(
        {
            "id": "fechamento",
            "name": name,
            "nodes": [
                {"id": "filtro", "type": "prep.filter", "config": {"expression": condition}},
                {
                    "id": "saida",
                    "type": "io.output_data",
                    "config": {"filename": "fechamento", "folder": folder},
                },
            ],
        }
    )


def editors(team: Team) -> tuple[Person, Person, str]:
    ana, bruno, _, sid = team
    with ana.acting() as t:
        t.change_members(sid, "aceitar", "bruno", "editor")
    return ana, bruno, sid


def open_flow(person: Person, sid: str) -> dict[str, Any]:
    with person.acting() as t:
        workflow, reason = t.get(sid, "fechamento")
        return {"fluxo": workflow, "motivo_assinatura": reason, **t.opened(sid, workflow, reason)}


def test_versions_carry_the_author(team: Team) -> None:
    ana, bruno, sid = editors(team)
    with ana.acting() as t:
        t.save(sid, flow())
    with bruno.acting() as t:
        t.save(sid, flow(condition="[valor] > 10"))
        t.save(sid, flow(condition="[valor] > 10"))  # igual à última: não vira outra versão
    with ana.acting() as t:
        history = t.history(sid, "fechamento", flow(condition="[valor] > 10"))
    assert [(v.autor_nome, v.origin, v.confere) for v in history] == [
        ("Bruno Lima", "manual", True),
        ("Ana Souza", "manual", True),
    ]
    assert history[0].changes is not None and history[0].changes.empty
    assert history[1].changes is not None and history[1].changes.changed == 1


def test_updated_by_shows_who_changed_since_last_open(team: Team) -> None:
    ana, bruno, sid = editors(team)
    with ana.acting() as t:
        t.save(sid, flow())
    assert open_flow(ana, sid)["atualizado"] is None  # foi ela mesma
    with bruno.acting() as t:
        t.save(sid, flow(condition="[valor] > 10"))  # filtro: mudança comum
    opened = open_flow(ana, sid)
    assert opened["atualizado"]["nome"] == "Bruno Lima" and opened["atualizado"]["versao_vista"]
    assert opened["conferir"] == [] and opened["motivo"] is None  # filtro não pede conferência (CA-06)
    assert open_flow(ana, sid)["atualizado"] is None  # já viu


def test_sensitive_change_asks_to_check_only_that(team: Team) -> None:
    ana, bruno, sid = editors(team)
    with ana.acting() as t:
        t.save(sid, flow())
    open_flow(ana, sid)
    with bruno.acting() as t:
        t.save(sid, flow(folder="\\\\servidor\\publico"))  # trocou a pasta de destino do Output
    opened = open_flow(ana, sid)
    assert opened["conferir"] == ["saida"] and "Bruno Lima mudou uma parte sensível" in opened["motivo"]
    with ana.acting() as t:
        t.accept_sensitive(sid, "fechamento")
    assert open_flow(ana, sid)["conferir"] == []


def test_my_own_sensitive_change_needs_no_check(team: Team) -> None:
    ana, _, sid = editors(team)
    with ana.acting() as t:
        t.save(sid, flow())
        t.save(sid, flow(folder="D:/outra"))
    assert open_flow(ana, sid)["conferir"] == []


def test_save_over_a_colleague_keeps_both_versions(team: Team) -> None:
    ana, bruno, sid = editors(team)
    with ana.acting() as t:
        t.save(sid, flow())
    base = open_flow(ana, sid)["sha256"]
    with bruno.acting() as t:
        t.save(sid, flow("do Bruno"), base=base)
    with ana.acting() as t, pytest.raises(ConflictError, match="Bruno Lima salvou enquanto você editava"):
        t.save(sid, flow("da Ana"), base=base)
    with ana.acting() as t:
        assert t.get(sid, "fechamento")[0].name == "do Bruno"  # nada sobrescrito
        history = t.history(sid, "fechamento")
    assert ("conflito", "Ana Souza", "da Ana") in [(v.origin, v.autor_nome, v.name) for v in history]
    with ana.acting() as t:
        t.save(sid, flow("da Ana"), base=base, force=True)  # Ficar com a minha
        assert t.get(sid, "fechamento")[0].name == "da Ana"


def test_conflict_copies_become_versions(team: Team) -> None:
    ana, _, sid = editors(team)
    _, _, folder, _ = team
    with ana.acting() as t:
        t.save(sid, flow())
    copy = folder / "fechamento-NOTEBRUNO.prodata.json"
    copy.write_text(flow("cópia do Bruno").model_dump_json(by_alias=True), encoding="utf-8")
    with ana.acting() as t:
        listed = t.flows(sid)
        history = t.history(sid, "fechamento")
    assert [f.id for f in listed] == ["fechamento"] and not copy.exists()
    assert history[0].origin == "copia" and history[0].name == "cópia do Bruno" and not history[0].confere


def test_held_file_is_sent_later(team: Team, monkeypatch: pytest.MonkeyPatch) -> None:
    ana, _, sid = editors(team)
    with ana.acting() as t:
        t.save(sid, flow())
    real = SpaceRepository.save

    def held(self: SpaceRepository, workflow: Workflow, signature: str | None = None) -> Workflow:
        raise HeldFileError("presa")

    monkeypatch.setattr(SpaceRepository, "save", held)
    with ana.acting() as t:
        res = t.save(sid, flow("nova"))
        assert res["adiado"] and t.get(sid, "fechamento")[0].name == "Fechamento"
        assert t.flush_pending(sid) == []  # ainda presa
    monkeypatch.setattr(SpaceRepository, "save", real)
    with ana.acting() as t:
        assert t.flush_pending(sid) == ["fechamento"]
        assert t.get(sid, "fechamento")[0].name == "nova" and t.get(sid, "fechamento")[1] is None


def test_held_file_does_not_overwrite_a_colleague(team: Team, monkeypatch: pytest.MonkeyPatch) -> None:
    ana, bruno, sid = editors(team)
    with ana.acting() as t:
        t.save(sid, flow())
    real = SpaceRepository.save
    monkeypatch.setattr(
        SpaceRepository, "save", lambda *a, **k: (_ for _ in ()).throw(HeldFileError("presa"))
    )
    with ana.acting() as t:
        assert t.save(sid, flow("da Ana"))["adiado"]
    monkeypatch.setattr(SpaceRepository, "save", real)
    with bruno.acting() as t:
        t.save(sid, flow("do Bruno"))
    with ana.acting() as t:
        t.flush_pending(sid)
        assert t.get(sid, "fechamento")[0].name == "do Bruno"
        assert "da Ana" in [v.name for v in t.history(sid, "fechamento") if v.origin == "conflito"]


def test_api_open_save_conflict_and_versions(client: TestClient, tmp_path: Path) -> None:
    folder = tmp_path / "Compartilhada"
    folder.mkdir()
    sid = client.post(
        "/api/equipe/espacos", json={"acao": "criar", "caminho": str(folder), "nome": "Time"}
    ).json()["id"]
    url = f"/api/equipe/espacos/{sid}/fluxos/fechamento"
    first = client.put(url, json=flow().model_dump(mode="json", by_alias=True)).json()
    assert first["sha256"] == content_sha(flow()) and first["adiado"] is False
    opened = client.get(f"{url}/abrir").json()
    assert opened["sha256"] == first["sha256"] and opened["autor"]["minha"]
    second = client.put(
        f"{url}?base={opened['sha256']}", json=flow("2").model_dump(mode="json", by_alias=True)
    )
    assert second.status_code == 200
    stale = client.put(
        f"{url}?base={opened['sha256']}", json=flow("3").model_dump(mode="json", by_alias=True)
    )
    assert stale.status_code == 409 and stale.json()["code"] == "conflict"
    versions = client.post(f"{url}/versoes/comparar", json={"current": None}).json()
    assert [v["origin"] for v in versions] == ["conflito", "manual", "manual"]
    one = client.get(f"{url}/versoes/{versions[-1]['id']}").json()
    assert one["name"] == "Fechamento"
    assert client.get(f"{url}/versoes/..%2Fx").status_code in (404, 422)
    assert (
        client.put(f"{url}?base=nao-e-sha", json=flow().model_dump(mode="json", by_alias=True)).status_code
        == 422
    )


def test_both_save_while_sync_is_late(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """CA-08: com a sincronização atrasada, Ana e Bruno salvam o mesmo fluxo; nenhum dos dois perde a versão."""
    sim = SyncSim(tmp_path / "sync")
    ana = Person(tmp_path, "ana", "Ana Souza", monkeypatch)
    bruno = Person(tmp_path, "bruno", "Bruno Lima", monkeypatch)
    with ana.acting() as t:
        sid = t.create(str(sim.path("NOTEANA")), "Controladoria")["id"]
        t.save(sid, flow())
    sim.sync_all()
    with bruno.acting() as t:
        t.join(str(sim.path("NOTEBRUNO")))
    sim.sync_all()
    with ana.acting() as t:
        t.change_members(sid, "aceitar", "bruno", "editor")
    sim.sync_all()
    base_ana, base_bruno = open_flow(ana, sid)["sha256"], open_flow(bruno, sid)["sha256"]
    with ana.acting() as t:
        t.save(sid, flow("da Ana"), base=base_ana)
    with bruno.acting() as t:
        t.save(sid, flow("do Bruno"), base=base_bruno)  # a marca e o arquivo da Ana ainda não chegaram
    sim.sync("NOTEANA")
    sim.sync(
        "NOTEBRUNO"
    )  # conflito: a nuvem fica com a da Ana, a do Bruno vira cópia com o nome do computador
    sim.sync_all()
    assert sim.conflicts
    with ana.acting() as t:
        assert [f.id for f in t.flows(sid)] == ["fechamento"]  # a cópia não vira fluxo solto
        history = t.history(sid, "fechamento")
        working = t.get(sid, "fechamento")[0].name
    names = {(v.name, v.autor_nome) for v in history}
    assert working == "da Ana" and ("do Bruno", "Bruno Lima") in names and ("da Ana", "Ana Souza") in names
