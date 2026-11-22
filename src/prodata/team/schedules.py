"""Agendamentos visíveis para o time (spec 047, RF-4753).

Cada computador publica na pasta do espaço o estado dos agendamentos que tem de fluxos do espaço:
``_equipe/agendamentos/<id>.json`` — de quem é, em que computador roda, o plano (frase e horários), a próxima e a última
execução. Nunca caminhos locais, dados ou senhas (RF-4705).

Quando alguém **assume** um agendamento, grava ao lado ``<id>.substituido.json``: o computador anterior lê e deixa de
rodar aquele agendamento. Os dois documentos são assinados por quem grava: um estado ou uma substituição forjados à
mão não valem (para substituir, quem assina precisa ser Publicador na lista de membros vigente).
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from prodata.domain.workflow import ID_PATTERN
from prodata.errors import InvalidInputError
from prodata.team.identity import USER_PATTERN, IdentityStore, verify
from prodata.team.repository import atomic_write
from prodata.team.signing import RANK, Members
from prodata.team.workspaces import CONTROL

SCHEDULES_DIR = "agendamentos"
_SCHEDULE_ID = re.compile(r"^[a-f0-9]{8}$")


class TeamSchedule(BaseModel):
    """O estado publicado de um agendamento, assinado pelo dono."""

    id: str = Field(pattern=r"^[a-f0-9]{8}$")
    espaco: str
    fluxo: str = Field(pattern=ID_PATTERN)
    fluxo_nome: str = ""
    frase: str = ""
    plano: dict[str, Any] = Field(default_factory=dict)  # frequência, horário, dias e opções: para Assumir
    pausado: bool = False
    proxima: str | None = None
    ultima: dict[str, Any] | None = None  # {"quando", "status", "mensagem"}
    usuario: str = Field(pattern=USER_PATTERN)
    nome: str = ""
    maquina: str = ""
    atualizado_em: datetime = Field(default_factory=lambda: datetime.now(UTC))
    chave_publica: str = ""
    assinatura: str = ""


class Substitution(BaseModel):
    """ "Bruno assumiu este agendamento": assinado por quem assumiu (Publicador)."""

    id: str = Field(pattern=r"^[a-f0-9]{8}$")
    espaco: str
    novo_id: str = Field(pattern=r"^[a-f0-9]{8}$")
    usuario: str = Field(pattern=USER_PATTERN)
    nome: str = ""
    maquina: str = ""
    quando: datetime = Field(default_factory=lambda: datetime.now(UTC))
    chave_publica: str = ""
    assinatura: str = ""


def _payload(kind: str, doc: BaseModel) -> bytes:
    data = doc.model_dump(mode="json", exclude={"assinatura"})
    return (
        f"{kind}|".encode()
        + json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    )


def _signed(kind: str, doc: Any, identity: IdentityStore) -> Any:
    me = identity.current()
    doc = doc.model_copy(update={"usuario": me.usuario, "nome": me.nome, "chave_publica": me.chave_publica,
                                 "assinatura": ""})  # fmt: skip
    return doc.model_copy(update={"assinatura": identity.sign(_payload(kind, doc))})


def _valid(kind: str, doc: Any, espaco: str, members: Members | None, need: str = "leitor") -> bool:
    if members is None or doc.espaco != espaco or not doc.assinatura:
        return False
    if not verify(doc.chave_publica, _payload(kind, doc), doc.assinatura):
        return False
    member = members.member(doc.usuario, doc.chave_publica)
    return member is not None and RANK[member.papel] >= RANK[need]


class TeamSchedules:
    def __init__(self, space_root: Path, space_id: str) -> None:
        self.folder = space_root / CONTROL / SCHEDULES_DIR
        self.space_id = space_id

    def _path(self, schedule_id: str, suffix: str = "") -> Path:
        if not _SCHEDULE_ID.match(schedule_id):
            raise InvalidInputError("Agendamento inválido.")
        return self.folder / f"{schedule_id}{suffix}.json"

    def publish(self, state: TeamSchedule, identity: IdentityStore) -> bool:
        """Grava o estado assinado, só se mudou algo que o time vê (a pasta pode ser lenta). Devolve se gravou."""
        path = self._path(state.id)
        try:
            old = TeamSchedule.model_validate_json(path.read_text(encoding="utf-8"))
            keep = {"atualizado_em", "assinatura", "chave_publica", "usuario", "nome"}
            if old.model_dump(mode="json", exclude=keep) == state.model_dump(mode="json", exclude=keep):
                return False
        except OSError, ValidationError, ValueError:
            pass
        signed = _signed(
            "agendamento", state.model_copy(update={"atualizado_em": datetime.now(UTC)}), identity
        )
        self.folder.mkdir(parents=True, exist_ok=True)
        atomic_write(path, signed.model_dump_json(indent=1))
        return True

    def remove(self, schedule_id: str) -> None:
        self._path(schedule_id).unlink(missing_ok=True)

    def substitute(self, schedule_id: str, new_id: str, identity: IdentityStore, machine: str) -> None:
        doc = Substitution(id=schedule_id, espaco=self.space_id, novo_id=new_id, usuario="x", maquina=machine)
        self.folder.mkdir(parents=True, exist_ok=True)
        atomic_write(self._path(schedule_id, ".substituido"),
                     _signed("substituicao", doc, identity).model_dump_json(indent=1))  # fmt: skip

    def substitution(self, schedule_id: str, members: Members | None) -> Substitution | None:
        """A substituição que vale: assinada por um Publicador da lista vigente."""
        try:
            doc = Substitution.model_validate_json(
                self._path(schedule_id, ".substituido").read_text(encoding="utf-8")
            )
        except OSError, ValidationError, ValueError:
            return None
        ok = doc.id == schedule_id and _valid("substituicao", doc, self.space_id, members, "publicador")
        return doc if ok else None

    def get(self, schedule_id: str, members: Members | None) -> TeamSchedule | None:
        try:
            doc = TeamSchedule.model_validate_json(self._path(schedule_id).read_text(encoding="utf-8"))
        except OSError, ValidationError, ValueError:
            return None
        return doc if doc.id == schedule_id and _valid("agendamento", doc, self.space_id, members) else None

    def all(self, members: Members | None) -> list[tuple[TeamSchedule, bool, Substitution | None]]:
        """Todos os estados publicados: (estado, assinatura confere, substituição que vale)."""
        out: list[tuple[TeamSchedule, bool, Substitution | None]] = []
        if not self.folder.is_dir():
            return out
        for path in sorted(self.folder.glob("*.json")):
            if not _SCHEDULE_ID.match(path.stem):
                continue
            try:
                doc = TeamSchedule.model_validate_json(path.read_text(encoding="utf-8"))
            except OSError, ValidationError, ValueError:
                continue
            ok = doc.id == path.stem and _valid("agendamento", doc, self.space_id, members)
            out.append((doc, ok, self.substitution(path.stem, members)))
        return out
