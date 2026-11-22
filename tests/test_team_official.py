"""Espaço da equipe, marco 5 (spec 047, RF-4751..4753, CA-07): versão oficial, agendamentos que rodam só a oficial,
agendamentos visíveis para o time e Assumir."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from prodata import cli
from prodata.domain.workflow import Workflow
from prodata.errors import InvalidInputError
from prodata.scheduling.model import ScheduleIn
from prodata.scheduling.service import SchedulingService, space_target, task_command
from prodata.scheduling.store import RunRecord, ScheduleStore
from prodata.scheduling.windows import TaskScheduler
from prodata.services.trust import TrustRegistry
from prodata.services.workflows import WorkflowRepository
from prodata.team.workspaces import CONTROL
from test_scheduling import FakeWindows
from test_team_roles import Person

NOW = datetime(2026, 11, 23, 9, 0)
Team = tuple[Person, Person, Path, str]


def flow(name: str = "Fechamento") -> Workflow:
    return Workflow.model_validate(
        {"id": "fechamento", "name": name, "nodes": [{"id": "n1", "type": "prep.select"}]}
    )


@pytest.fixture
def team(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Team:
    """Ana (administradora) e Bruno (Editor) num espaço com o fluxo salvo pela Ana."""
    folder = tmp_path / "pasta_da_equipe"
    folder.mkdir()
    ana = Person(tmp_path, "ana", "Ana Souza", monkeypatch)
    bruno = Person(tmp_path, "bruno", "Bruno Lima", monkeypatch)
    with ana.acting() as t:
        sid = t.create(str(folder), "Controladoria")["id"]
    with bruno.acting() as t:
        t.join(str(folder))
    with ana.acting() as t:
        t.change_members(sid, "aceitar", "bruno", "editor")
        t.save(sid, flow())
    return ana, bruno, folder, sid


def scheduling(person: Person, tmp_path: Path, fake: FakeWindows) -> SchedulingService:
    home = tmp_path / f"agenda-{person.user}"
    store = ScheduleStore(home / "agendamentos.json", home / "logs" / "agendamentos.jsonl")
    home.mkdir(parents=True, exist_ok=True)
    return SchedulingService(store, WorkflowRepository(home / "biblioteca"), TrustRegistry(home / "confianca.json"),
                             TaskScheduler(fake), clock=lambda: NOW, windows=lambda: True, team=person.team)  # fmt: skip


def plan(sid: str) -> ScheduleIn:
    return ScheduleIn(
        space_id=sid, workflow_id="fechamento", name="Fechamento", frequency="daily", time="06:00"
    )


def test_only_a_publisher_publishes_the_official(team: Team) -> None:
    ana, bruno, _, sid = team
    with bruno.acting() as t, pytest.raises(InvalidInputError, match="Publicador"):
        t.publish(sid, "fechamento")
    with ana.acting() as t:
        info = t.publish(sid, "fechamento")
        assert info and info["nome"] == "Ana Souza" and info["confere"] and info["atual"]
    with bruno.acting() as t:
        t.save(sid, flow("à frente"))
        listed = t.flows(sid)[0]
        official, reason = t.official(sid, "fechamento")
    assert listed.oficial and listed.oficial["atual"] is False  # a de trabalho passou a oficial
    assert official is not None and official.name == "Fechamento" and reason is None


def test_tampered_or_demoted_official_does_not_run(team: Team) -> None:
    ana, bruno, folder, sid = team
    with ana.acting() as t:
        t.change_members(sid, "papel", "bruno", "publicador")
    with bruno.acting() as t:
        t.publish(sid, "fechamento")
    with ana.acting() as t:
        t.change_members(sid, "papel", "bruno", "editor")  # Bruno deixou de ser Publicador
        assert "não confere" in (t.official(sid, "fechamento")[1] or "")
        t.publish(sid, "fechamento")
    path = folder / CONTROL / "oficiais" / "fechamento.prodata.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["name"] = "Adulterado"
    path.write_text(json.dumps(data), encoding="utf-8")
    with ana.acting() as t:
        workflow, reason = t.official(sid, "fechamento")
    assert workflow is None and "alterado fora do programa" in (reason or "")


def test_schedule_needs_an_official_and_is_shared(team: Team, tmp_path: Path) -> None:
    ana, bruno, folder, sid = team
    fake = FakeWindows()
    with ana.acting():
        agenda = scheduling(ana, tmp_path, fake)
        with pytest.raises(InvalidInputError, match="ainda não tem versão oficial"):
            agenda.create(plan(sid))
        ana.team.publish(sid, "fechamento")
        item = agenda.create(plan(sid))
    assert item["space_id"] == sid
    assert f"espaco:{sid}/fechamento" in task_command(item["id"], space_target(sid, "fechamento"))[1]
    state = (folder / CONTROL / "agendamentos" / f"{item['id']}.json").read_text(encoding="utf-8")
    assert (
        "Ana Souza" in state and str(tmp_path) not in state and '"assinatura"' in state
    )  # nada de caminho local
    with bruno.acting() as t:
        seen = t.team_schedules(sid)["agendamentos"]
    assert [(s["fluxo"], s["nome"], s["confere"], s["meu"]) for s in seen] == [
        ("fechamento", "Ana Souza", True, False)
    ]


def test_publisher_assumes_and_the_old_one_stops(team: Team, tmp_path: Path) -> None:
    ana, bruno, _, sid = team
    fake = FakeWindows()
    with ana.acting():
        ana.team.publish(sid, "fechamento")
        old = scheduling(ana, tmp_path, fake).create(plan(sid))
    with bruno.acting(), pytest.raises(InvalidInputError, match="Publicador"):
        scheduling(bruno, tmp_path, fake).assume(sid, old["id"])  # Editor não assume
    with ana.acting():
        ana.team.change_members(sid, "papel", "bruno", "publicador")
    with bruno.acting():
        new = scheduling(bruno, tmp_path, fake).assume(sid, old["id"])
        assert new["space_id"] == sid and new["sentence"] == "Todo dia às 06:00"
        seen = {s["id"]: s for s in bruno.team.team_schedules(sid)["agendamentos"]}
    assert seen[old["id"]]["substituido_por"]["nome"] == "Bruno Lima" and seen[new["id"]]["meu"]
    with ana.acting():
        mine = scheduling(ana, tmp_path, fake).items()
        assert mine[0]["substituido_por"]["nome"] == "Bruno Lima"
        services = SimpleNamespace(team=ana.team, trust=TrustRegistry(tmp_path / "c.json"))
        args = argparse.Namespace(agendamento=old["id"])
        with pytest.raises(InvalidInputError, match="assumido por Bruno Lima"):
            cli._space_official(services, args, sid, "fechamento")  # type: ignore[arg-type]


def test_forged_substitution_does_not_stop_a_schedule(team: Team, tmp_path: Path) -> None:
    ana, bruno, folder, sid = team
    fake = FakeWindows()
    with ana.acting():
        ana.team.publish(sid, "fechamento")
        old = scheduling(ana, tmp_path, fake).create(plan(sid))
    with bruno.acting():  # Bruno é Editor e escreve a substituição direto na pasta
        from prodata.team.schedules import TeamSchedules

        TeamSchedules(folder, sid).substitute(old["id"], "0a0b0c0d", bruno.identity, "NOTEBRUNO")
    with ana.acting():
        assert ana.team.substitution(sid, old["id"]) is None
        services = SimpleNamespace(team=ana.team, trust=TrustRegistry(tmp_path / "c.json"))
        workflow = cli._space_official(services, argparse.Namespace(agendamento=old["id"]), sid, "fechamento")  # type: ignore[arg-type]
    assert workflow.name == "Fechamento"


def test_last_run_is_shared_with_the_team(team: Team, tmp_path: Path) -> None:
    ana, bruno, _, sid = team
    fake = FakeWindows()
    with ana.acting():
        ana.team.publish(sid, "fechamento")
        agenda = scheduling(ana, tmp_path, fake)
        item = agenda.create(plan(sid))
        agenda.store.record(RunRecord(schedule_id=item["id"], workflow="Fechamento", started_at=NOW, finished_at=NOW,
                                      status="refused", message="A versão oficial não confere."))  # fmt: skip
        agenda.share_after_run(item["id"])
    with bruno.acting():
        seen = bruno.team.team_schedules(sid)["agendamentos"][0]
    assert seen["ultima"]["status"] == "refused" and "não confere" in seen["ultima"]["message"]
