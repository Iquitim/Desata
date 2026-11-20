"""Agendador visual (spec 044, RF-4431..4438), com um Agendador do Windows falso."""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from prodata import cli
from prodata.config import Settings
from prodata.domain.workflow import Workflow
from prodata.scheduling.model import ScheduleIn, next_run, sentence, when_text
from prodata.scheduling.service import SchedulingService, task_command
from prodata.scheduling.store import ScheduleStore
from prodata.scheduling.task_xml import NS, task_xml
from prodata.scheduling.windows import TaskScheduler
from prodata.services.trust import TrustRegistry
from prodata.services.workflows import WorkflowRepository

NOW = datetime(2026, 11, 19, 10, 30)  # quinta-feira


def plan(**kw: Any) -> ScheduleIn:
    return ScheduleIn(workflow_id="meu_fluxo", name="Meu fluxo", **kw)


# ---------------------------------------------------------------- frase e próxima execução


@pytest.mark.parametrize(
    ("kw", "text"),
    [
        ({}, "Todo dia às 06:00"),
        ({"frequency": "weekly"}, "De segunda a sexta às 06:00"),
        ({"frequency": "weekly", "weekdays": [0, 2]}, "Às segundas e quartas às 06:00"),
        ({"frequency": "weekly", "weekdays": [5, 6]}, "Aos sábados e domingos às 06:00"),
        ({"frequency": "monthly", "month_day": 5, "time": "08:15"}, "Todo dia 5 do mês às 08:15"),
        ({"frequency": "hourly", "every_hours": 4}, "A cada 4 horas, a partir das 06:00"),
        ({"frequency": "hourly", "every_hours": 1}, "A cada hora, a partir das 06:00"),
    ],
)
def test_sentence(kw: dict[str, Any], text: str) -> None:
    assert sentence(plan(**kw)) == text


@pytest.mark.parametrize(
    ("kw", "expected"),
    [
        ({"time": "06:00"}, datetime(2026, 11, 20, 6, 0)),  # já passou hoje: amanhã
        ({"time": "18:00"}, datetime(2026, 11, 19, 18, 0)),
        ({"frequency": "weekly", "weekdays": [0], "time": "06:00"}, datetime(2026, 11, 23, 6, 0)),
        ({"frequency": "monthly", "month_day": 1}, datetime(2026, 12, 1, 6, 0)),
        ({"frequency": "hourly", "every_hours": 4}, datetime(2026, 11, 19, 14, 0)),
        ({"frequency": "hourly", "every_hours": 12, "time": "08:00"}, datetime(2026, 11, 19, 20, 0)),
    ],
)
def test_next_run(kw: dict[str, Any], expected: datetime) -> None:
    assert next_run(plan(**kw), NOW) == expected


def test_when_text() -> None:
    assert when_text(datetime(2026, 11, 19, 18, 0), NOW) == "hoje, 18:00"
    assert when_text(datetime(2026, 11, 20, 6, 0), NOW) == "amanhã, 06:00"
    assert when_text(datetime(2026, 11, 23, 6, 0), NOW) == "segunda, 06:00"
    assert when_text(datetime(2026, 12, 5, 6, 0), NOW) == "05/12, 06:00"


def test_invalid_choices() -> None:
    with pytest.raises(ValueError):
        plan(frequency="weekly", weekdays=[])
    with pytest.raises(ValueError):
        plan(every_hours=5)
    with pytest.raises(ValueError):
        plan(month_day=31)
    with pytest.raises(ValueError):
        ScheduleIn(workflow_id="../fora", name="x")
    with pytest.raises(ValueError):
        ScheduleIn(name="sem alvo")


# ---------------------------------------------------------------- XML da tarefa


def _xml(**kw: Any) -> ET.Element:
    text = task_xml(
        plan(**kw),
        command=r"C:\App\prodata-tarefa.exe",
        arguments="run meu_fluxo --agendamento 0a1b2c3d",
        workdir=r"C:\App",
        author="Desata",
        description='Fluxo "Meu" & cia',
        start=NOW,
    )
    assert text.startswith('<?xml version="1.0" encoding="UTF-16"?>')
    return ET.fromstring(text.split("?>", 1)[1])


def _find(root: ET.Element, path: str) -> ET.Element | None:
    return root.find("/".join(f"{{{NS}}}{p}" for p in path.split("/")))


def test_task_runs_only_logged_in_without_password() -> None:
    root = _xml()
    assert _find(root, "Principals/Principal/LogonType").text == "InteractiveToken"  # type: ignore[union-attr]
    assert _find(root, "Principals/Principal/RunLevel").text == "LeastPrivilege"  # type: ignore[union-attr]
    assert "Password" not in ET.tostring(root, encoding="unicode")
    assert _find(root, "Actions/Exec/Command").text == r"C:\App\prodata-tarefa.exe"  # type: ignore[union-attr]
    assert _find(root, "RegistrationInfo/Description").text == 'Fluxo "Meu" & cia'  # type: ignore[union-attr]


def test_task_options_and_triggers() -> None:
    root = _xml(
        frequency="weekly",
        weekdays=[0, 4],
        time="07:45",
        options={"catch_up": False, "wake": True, "on_battery": False},
    )
    assert _find(root, "Settings/StartWhenAvailable").text == "false"  # type: ignore[union-attr]
    assert _find(root, "Settings/WakeToRun").text == "true"  # type: ignore[union-attr]
    assert _find(root, "Settings/DisallowStartIfOnBatteries").text == "true"  # type: ignore[union-attr]
    days = _find(root, "Triggers/CalendarTrigger/ScheduleByWeek/DaysOfWeek")
    assert [d.tag.split("}")[1] for d in days] == ["Monday", "Friday"]  # type: ignore[union-attr]
    assert _find(root, "Triggers/CalendarTrigger/StartBoundary").text == "2026-11-19T07:45:00"  # type: ignore[union-attr]
    hourly = _xml(frequency="hourly", every_hours=3)
    assert _find(hourly, "Triggers/CalendarTrigger/Repetition/Interval").text == "PT3H"  # type: ignore[union-attr]
    monthly = _xml(frequency="monthly", month_day=10)
    assert _find(monthly, "Triggers/CalendarTrigger/ScheduleByMonth/DaysOfMonth/Day").text == "10"  # type: ignore[union-attr]


def test_dev_command_has_no_shell() -> None:
    exe, args, _ = task_command("0a1b2c3d", r"C:\Meus fluxos\vendas.prodata.json")
    assert exe.lower().endswith(("python.exe", "pythonw.exe", "python", "pythonw"))
    assert '"C:\\Meus fluxos\\vendas.prodata.json"' in args and args.endswith("--agendamento 0a1b2c3d")


# ---------------------------------------------------------------- serviço com Agendador falso


class FakeWindows:
    def __init__(self) -> None:
        self.tasks: dict[str, bool] = {}
        self.calls: list[list[str]] = []
        self.refuse = False

    def __call__(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        self.calls.append(args)
        verb, name = args[0], args[2]
        if self.refuse:
            return subprocess.CompletedProcess(args, 1, "", "ERRO: Acesso negado.")
        if verb == "/Create":
            xml = Path(args[4]).read_text(encoding="utf-16")
            assert "InteractiveToken" in xml
            self.tasks[name] = True
        elif verb == "/Query":
            if name not in self.tasks:
                return subprocess.CompletedProcess(args, 1, "", "ERRO: não encontrado")
            flag = "true" if self.tasks[name] else "false"
            body = f'<?xml version="1.0" encoding="UTF-16"?><Task xmlns="{NS}"><Settings><Enabled>{flag}</Enabled></Settings></Task>'
            return subprocess.CompletedProcess(args, 0, body, "")
        elif verb == "/Change":
            self.tasks[name] = args[3] == "/ENABLE"
        elif verb == "/Delete":
            self.tasks.pop(name, None)
        return subprocess.CompletedProcess(args, 0, "", "")


@pytest.fixture
def fake() -> FakeWindows:
    return FakeWindows()


@pytest.fixture
def service(tmp_path: Path, fake: FakeWindows) -> SchedulingService:
    workflows = WorkflowRepository(tmp_path / "workflows")
    workflows.save(
        Workflow.model_validate({"id": "meu_fluxo", "name": "Meu fluxo", "nodes": [], "edges": []})
    )
    trust = TrustRegistry(tmp_path / "confianca.json")
    trust.start([workflows.get("meu_fluxo")])
    store = ScheduleStore(tmp_path / "agendamentos.json", tmp_path / "logs" / "agendamentos.jsonl")
    return SchedulingService(
        store, workflows, trust, TaskScheduler(fake), clock=lambda: NOW, windows=lambda: True
    )


def test_create_pause_resume_run_delete(service: SchedulingService, fake: FakeWindows) -> None:
    item = service.create(plan(frequency="weekly"))
    assert item["task"] == "active" and item["next_text"] == "amanhã, 06:00"
    assert item["sentence"] == "De segunda a sexta às 06:00"
    name = item["task_name"]
    assert name.endswith(f"({item['id']})") and fake.tasks[name] is True
    paused = service.set_paused(item["id"], True)
    assert paused["paused"] and paused["next_run"] is None and fake.tasks[name] is False
    assert service.set_paused(item["id"], False)["task"] == "active"
    service.run_now(item["id"])
    assert fake.calls[-1][:3] == ["/Run", "/TN", name]
    service.delete(item["id"])
    assert name not in fake.tasks and service.items() == []


def test_task_removed_in_windows_shows_and_recreates(service: SchedulingService, fake: FakeWindows) -> None:
    item = service.create(plan())
    fake.tasks.clear()
    assert service.items()[0]["task"] == "missing"
    assert service.recreate(item["id"])["task"] == "active"


def test_refuses_untrusted_missing_and_other_systems(tmp_path: Path, service: SchedulingService) -> None:
    with pytest.raises(Exception, match="Salve o fluxo"):
        service.create(ScheduleIn(workflow_id="nao_existe", name="x"))
    service.workflows.save(
        Workflow.model_validate({"id": "de_fora", "name": "De fora", "nodes": [], "edges": []})
    )
    with pytest.raises(Exception, match="confiado"):
        service.create(ScheduleIn(workflow_id="de_fora", name="De fora"))
    service.windows = lambda: False
    with pytest.raises(Exception, match="só no Windows"):
        service.create(plan())


def test_company_policy_message(service: SchedulingService, fake: FakeWindows) -> None:
    fake.refuse = True
    with pytest.raises(Exception, match="regra da empresa"):
        service.create(plan())
    assert service.store.list() == []  # nada fica cadastrado sem a tarefa


def test_failures_since_last_seen(service: SchedulingService, monkeypatch: pytest.MonkeyPatch) -> None:
    item = service.create(plan())
    args = cli.parser().parse_args(["run", "nao_existe", "--agendamento", item["id"]])
    monkeypatch.setenv("PRODATA_STORAGE_DIR", str(service.store.path.parent))
    cli._record(args, NOW, "failed", "Meu fluxo", "conexão recusada")
    failures = service.failures()
    assert [f["message"] for f in failures] == ["conexão recusada"] and failures[0]["name"] == "Meu fluxo"
    assert service.items()[0]["last"]["status"] == "failed"
    service.clock = lambda: datetime(2030, 1, 1)
    service.mark_seen()
    assert service.failures() == []


# ---------------------------------------------------------------- linha de comando e API


def test_cli_records_refusal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, settings: Settings) -> None:
    monkeypatch.setenv("PRODATA_STORAGE_DIR", str(settings.storage_dir))
    code = cli.main(["run", "nao_existe", "--agendamento", "0a1b2c3d"])
    assert code == cli.REFUSED
    store = ScheduleStore(
        settings.storage_dir / "agendamentos.json", settings.storage_dir / "logs" / "agendamentos.jsonl"
    )
    [record] = store.records()
    assert record.status == "refused" and "não encontrado" in record.message


def test_api_preview_and_list(client: TestClient) -> None:
    body = {"workflow_id": "meu_fluxo", "name": "x", "frequency": "monthly", "month_day": 3, "time": "09:00"}
    preview = client.post("/api/schedules/preview", json=body).json()
    assert preview["sentence"] == "Todo dia 3 do mês às 09:00" and preview["next_text"]
    listed = client.get("/api/schedules").json()
    assert listed["items"] == [] and "supported" in listed
    assert client.post("/api/schedules/preview", json={**body, "every_hours": 5}).status_code == 422
