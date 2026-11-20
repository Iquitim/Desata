"""XML da tarefa do Agendador do Windows (spec 044, plano). Montado com ``xml.etree``, nunca por concatenação.

Roda só com a pessoa conectada (``InteractiveToken``), sem privilégio extra e sem senha (RF-4438).
"""

from __future__ import annotations

import re
from datetime import datetime
from xml.etree import ElementTree as ET

from prodata.scheduling.model import ScheduleIn

NS = "http://schemas.microsoft.com/windows/2004/02/mit/task"
_DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
TIME_LIMIT = "PT4H"


def _sub(parent: ET.Element, tag: str, text: str | None = None) -> ET.Element:
    el = ET.SubElement(parent, tag)
    if text is not None:
        el.text = text
    return el


def _flag(value: bool) -> str:
    return "true" if value else "false"


def _trigger(triggers: ET.Element, s: ScheduleIn, start: datetime) -> None:
    trig = _sub(triggers, "CalendarTrigger")
    if s.frequency == "hourly":
        rep = _sub(trig, "Repetition")
        _sub(rep, "Interval", f"PT{s.every_hours}H")
        _sub(rep, "Duration", "P1D")
        _sub(rep, "StopAtDurationEnd", "false")
    _sub(trig, "StartBoundary", start.strftime("%Y-%m-%dT") + f"{s.time}:00")
    _sub(trig, "Enabled", "true")
    if s.frequency == "weekly":
        week = _sub(trig, "ScheduleByWeek")
        days = _sub(week, "DaysOfWeek")
        for d in s.weekdays:
            _sub(days, _DAYS[d])
        _sub(week, "WeeksInterval", "1")
    elif s.frequency == "monthly":
        month = _sub(trig, "ScheduleByMonth")
        _sub(_sub(month, "DaysOfMonth"), "Day", str(s.month_day))
        months = _sub(month, "Months")
        for m in _MONTHS:
            _sub(months, m)
    else:
        _sub(_sub(trig, "ScheduleByDay"), "DaysInterval", "1")


def task_xml(
    s: ScheduleIn,
    *,
    command: str,
    arguments: str,
    workdir: str,
    author: str,
    description: str,
    start: datetime,
) -> str:
    task = ET.Element("Task", {"version": "1.2", "xmlns": NS})
    info = _sub(task, "RegistrationInfo")
    _sub(info, "Author", author)
    _sub(info, "Description", description)
    _trigger(_sub(task, "Triggers"), s, start)
    principal = _sub(_sub(task, "Principals"), "Principal", None)
    principal.set("id", "Author")
    _sub(principal, "LogonType", "InteractiveToken")
    _sub(principal, "RunLevel", "LeastPrivilege")
    settings = _sub(task, "Settings")
    _sub(settings, "MultipleInstancesPolicy", "IgnoreNew")
    _sub(settings, "DisallowStartIfOnBatteries", _flag(not s.options.on_battery))
    _sub(settings, "StopIfGoingOnBatteries", "false")
    _sub(settings, "AllowHardTerminate", "true")
    _sub(settings, "StartWhenAvailable", _flag(s.options.catch_up))
    _sub(settings, "RunOnlyIfNetworkAvailable", "false")
    idle = _sub(settings, "IdleSettings")
    _sub(idle, "StopOnIdleEnd", "false")
    _sub(idle, "RestartOnIdle", "false")
    _sub(settings, "AllowStartOnDemand", "true")
    _sub(settings, "Enabled", "true")
    _sub(settings, "Hidden", "false")
    _sub(settings, "RunOnlyIfIdle", "false")
    _sub(settings, "WakeToRun", _flag(s.options.wake))
    _sub(settings, "ExecutionTimeLimit", TIME_LIMIT)
    _sub(settings, "Priority", "7")
    actions = _sub(task, "Actions")
    actions.set("Context", "Author")
    run = _sub(actions, "Exec")
    _sub(run, "Command", command)
    _sub(run, "Arguments", arguments)
    _sub(run, "WorkingDirectory", workdir)
    body = ET.tostring(task, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-16"?>\n' + body


def enabled_from_xml(text: str) -> bool:
    """A tarefa está ativa? Lê o ``Settings/Enabled`` do XML que o ``schtasks /Query /XML`` devolve.

    Sem parser de XML: basta achar o ``Enabled`` do bloco ``Settings`` (os gatilhos têm o seu próprio).
    """
    settings = re.search(r"<Settings>(.*?)</Settings>", text, re.S)
    found = re.search(r"<Enabled>\s*(true|false)\s*</Enabled>", settings.group(1) if settings else "", re.I)
    return not (found and found.group(1).lower() == "false")
