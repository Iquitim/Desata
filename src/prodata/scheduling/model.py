"""O agendamento, a frase que o descreve e a próxima execução (spec 044, RF-4431/4432)."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from datetime import time as clock_time
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from prodata.domain.workflow import ID_PATTERN

Frequency = Literal["daily", "weekly", "monthly", "hourly"]
EVERY_HOURS = (1, 2, 3, 4, 6, 8, 12)
SCHEDULE_ID = r"^[a-f0-9]{8}$"
DAY_NAMES = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")
DAY_PLURAL = ("segundas", "terças", "quartas", "quintas", "sextas", "sábados", "domingos")


class ScheduleOptions(BaseModel):
    catch_up: bool = Field(
        True, description="Se o computador estiver desligado na hora, rodar assim que ligar."
    )
    wake: bool = Field(False, description="Acordar o computador para rodar.")
    on_battery: bool = Field(True, description="Rodar também na bateria.")


class ScheduleIn(BaseModel):
    """O que a pessoa escolhe no diálogo."""

    workflow_id: str = Field("", max_length=64)
    space_id: str = Field(
        "", pattern=r"^([a-f0-9]{16})?$", description="Fluxo de um espaço da equipe (spec 047)."
    )
    file_path: str = Field("", max_length=1024)
    name: str = Field("", max_length=120)
    frequency: Frequency = "daily"
    time: str = Field("06:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    weekdays: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])
    month_day: int = Field(1, ge=1, le=28, description="Até 28, para valer em todos os meses.")
    every_hours: int = 4
    options: ScheduleOptions = Field(default_factory=ScheduleOptions)

    @field_validator("weekdays")
    @classmethod
    def _days(cls, value: list[int]) -> list[int]:
        days = sorted(set(value))
        if any(d < 0 or d > 6 for d in days):
            raise ValueError("Dias da semana vão de 0 (segunda) a 6 (domingo).")
        return days

    @field_validator("every_hours")
    @classmethod
    def _hours(cls, value: int) -> int:
        if value not in EVERY_HOURS:
            raise ValueError(f"Escolha um destes intervalos: {', '.join(map(str, EVERY_HOURS))} horas.")
        return value

    @model_validator(mode="after")
    def _target(self) -> ScheduleIn:
        if bool(self.workflow_id) == bool(self.file_path):
            raise ValueError("Informe o fluxo da biblioteca ou o arquivo do fluxo, um dos dois.")
        if self.space_id and not self.workflow_id:
            raise ValueError("Informe o fluxo do espaço da equipe.")
        if self.workflow_id and not re.fullmatch(ID_PATTERN, self.workflow_id):
            raise ValueError("Identificador de fluxo inválido.")
        if self.frequency == "weekly" and not self.weekdays:
            raise ValueError("Escolha ao menos um dia da semana.")
        return self

    @property
    def at(self) -> clock_time:
        hour, minute = self.time.split(":")
        return clock_time(int(hour), int(minute))


class Schedule(ScheduleIn):
    id: str = Field(pattern=SCHEDULE_ID)
    created_at: datetime
    paused: bool = False


def _days_text(days: list[int]) -> str:
    if days == [0, 1, 2, 3, 4]:
        return "De segunda a sexta"
    if days == [5, 6]:
        return "Aos sábados e domingos"
    if len(days) == 7:
        return "Todo dia"
    names = [DAY_PLURAL[d] for d in days]
    joined = names[0] if len(names) == 1 else f"{', '.join(names[:-1])} e {names[-1]}"
    return f"Às {joined}" if days[0] < 5 else f"Aos {joined}"


def sentence(s: ScheduleIn) -> str:
    """A frase de resumo: "Roda de segunda a sexta às 06:00"."""
    if s.frequency == "daily":
        return f"Todo dia às {s.time}"
    if s.frequency == "weekly":
        return f"{_days_text(s.weekdays)} às {s.time}"
    if s.frequency == "monthly":
        return f"Todo dia {s.month_day} do mês às {s.time}"
    hours = "hora" if s.every_hours == 1 else f"{s.every_hours} horas"
    return f"A cada {hours}, a partir das {s.time}"


def _runs_on(s: ScheduleIn, day: date) -> bool:
    if s.frequency == "weekly":
        return day.weekday() in s.weekdays
    if s.frequency == "monthly":
        return day.day == s.month_day
    return True


def next_run(s: ScheduleIn, now: datetime) -> datetime:
    """A próxima vez depois de ``now`` (hora local, sem fuso)."""
    day = now.date()
    for _ in range(400):
        start = datetime.combine(day, s.at)
        if _runs_on(s, day):
            if s.frequency == "hourly":
                step = timedelta(hours=s.every_hours)
                moment = start
                while moment.date() == day:
                    if moment > now:
                        return moment
                    moment += step
            elif start > now:
                return start
        day += timedelta(days=1)
    raise ValueError("Não foi possível calcular a próxima execução.")


def when_text(moment: datetime, now: datetime) -> str:
    """ "hoje, 18:00", "amanhã, 06:00", "segunda, 06:00" ou "05/12, 06:00"."""
    days = (moment.date() - now.date()).days
    clock = moment.strftime("%H:%M")
    if days == 0:
        return f"hoje, {clock}"
    if days == 1:
        return f"amanhã, {clock}"
    if days < 7:
        return f"{DAY_NAMES[moment.weekday()]}, {clock}"
    return f"{moment.strftime('%d/%m')}, {clock}"
