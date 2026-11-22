"""Agendamentos (spec 044, RF-4431..4438): camada fina sobre o ``SchedulingService``."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from prodata.api.deps import ServicesDep
from prodata.scheduling.model import ScheduleIn
from prodata.scheduling.windows import supported

router = APIRouter(prefix="/api/schedules", tags=["agendamentos"])


@router.get("")
def list_schedules(services: ServicesDep) -> dict[str, Any]:
    return {"supported": supported(), "items": services.schedules.items()}


@router.post("/preview")
def preview(data: ScheduleIn, services: ServicesDep) -> dict[str, Any]:
    return services.schedules.preview(data)


@router.post("")
def create(data: ScheduleIn, services: ServicesDep) -> dict[str, Any]:
    return services.schedules.create(data)


@router.put("/{schedule_id}")
def update(schedule_id: str, data: ScheduleIn, services: ServicesDep) -> dict[str, Any]:
    return services.schedules.update(schedule_id, data)


@router.post("/{schedule_id}/pause")
def pause(schedule_id: str, services: ServicesDep) -> dict[str, Any]:
    return services.schedules.set_paused(schedule_id, True)


@router.post("/{schedule_id}/resume")
def resume(schedule_id: str, services: ServicesDep) -> dict[str, Any]:
    return services.schedules.set_paused(schedule_id, False)


@router.post("/{schedule_id}/run")
def run_now(schedule_id: str, services: ServicesDep) -> dict[str, bool]:
    services.schedules.run_now(schedule_id)
    return {"ok": True}


@router.post("/{schedule_id}/recreate")
def recreate(schedule_id: str, services: ServicesDep) -> dict[str, Any]:
    return services.schedules.recreate(schedule_id)


@router.delete("/{schedule_id}")
def delete(schedule_id: str, services: ServicesDep) -> dict[str, bool]:
    services.schedules.delete(schedule_id)
    return {"ok": True}


@router.get("/failures/unseen")
def failures(services: ServicesDep) -> list[dict[str, Any]]:
    return services.schedules.failures()


@router.post("/failures/seen")
def seen(services: ServicesDep) -> dict[str, bool]:
    services.schedules.mark_seen()
    return {"ok": True}


class AssumeRequest(BaseModel):
    space_id: str = Field(pattern=r"^[a-f0-9]{16}$")
    schedule_id: str = Field(pattern=r"^[a-f0-9]{8}$")


@router.post("/assumir")
def assume(req: AssumeRequest, services: ServicesDep) -> dict[str, Any]:
    """Assumir este agendamento (spec 047, RF-4753): cria a tarefa aqui e o computador anterior deixa de rodar."""
    return services.schedules.assume(req.space_id, req.schedule_id)
