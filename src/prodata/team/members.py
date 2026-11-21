"""Membros e pedidos de entrada de um espaço da equipe (spec 047, RF-4711..4713, RF-4717).

A lista vale só assinada (``signing.check_members``). Cada computador guarda, na própria pasta de dados, a última lista
que aceitou: é ela que decide quem pode mudar a próxima. Os pedidos de entrada ficam em ``_equipe/pedidos/``: quem
entra no espaço sem estar na lista deixa o seu, e um administrador aceita com um papel.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from prodata.errors import InvalidInputError
from prodata.team.identity import USER_PATTERN, Identity
from prodata.team.repository import atomic_write
from prodata.team.signing import Members, check_members
from prodata.team.workspaces import CONTROL

MEMBERS_FILE = "membros.json"
REQUESTS_DIR = "pedidos"
_USER = re.compile(USER_PATTERN)


class Request(BaseModel):
    usuario: str = Field(pattern=USER_PATTERN)
    nome: str = Field(min_length=1, max_length=80)
    chave_publica: str = Field(min_length=40, max_length=60)
    quando: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MembersStore:
    def __init__(self, space_root: Path, space_id: str, accepted_path: Path) -> None:
        self.control = space_root / CONTROL
        self.space_id = space_id
        self.accepted_path = accepted_path  # na pasta de dados deste computador, nunca na pasta do espaço

    def _read(self, path: Path) -> Members | None:
        try:
            return Members.model_validate_json(path.read_text(encoding="utf-8"))
        except OSError, ValidationError, ValueError:
            return None

    def accepted(self) -> Members | None:
        return self._read(self.accepted_path)

    def current(self) -> tuple[Members | None, str | None]:
        """A lista vigente, se confere, ou o motivo de recusa. Uma lista nova e válida passa a ser a aceita."""
        path = self.control / MEMBERS_FILE
        if not path.is_file():
            return None, "O espaço ainda não tem lista de membros (a sincronização ainda não trouxe?)."
        new = self._read(path)
        if new is None:
            return None, "A lista de membros do espaço está ilegível ou foi alterada fora do programa."
        accepted = self.accepted()
        reason = check_members(new, accepted, self.space_id)
        if reason:
            return None, reason
        if accepted is None or new.versao > accepted.versao:
            self._accept(new)
        return new, None

    def _accept(self, members: Members) -> None:
        self.accepted_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(self.accepted_path, members.model_dump_json(indent=1))

    def write(self, members: Members) -> None:
        """Grava uma lista nova (já assinada por quem pode) e a aceita aqui."""
        try:
            atomic_write(self.control / MEMBERS_FILE, members.model_dump_json(indent=1))
        except PermissionError as exc:
            raise InvalidInputError(
                "A pasta do espaço não deixou gravar a lista de membros agora. Tente de novo."
            ) from exc
        self._accept(members)

    # ------------------------------------------------------------------ pedidos de entrada

    def requests(self) -> list[Request]:
        folder = self.control / REQUESTS_DIR
        out: list[Request] = []
        for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
            try:
                out.append(Request.model_validate_json(path.read_text(encoding="utf-8")))
            except OSError, ValidationError, ValueError:
                continue
        return out

    def add_request(self, me: Identity) -> None:
        folder = self.control / REQUESTS_DIR
        folder.mkdir(parents=True, exist_ok=True)
        request = Request(usuario=me.usuario, nome=me.nome, chave_publica=me.chave_publica)
        atomic_write(
            folder / f"{me.usuario}.json", json.dumps(request.model_dump(mode="json"), ensure_ascii=False)
        )

    def remove_request(self, usuario: str) -> None:
        if _USER.match(usuario):
            (self.control / REQUESTS_DIR / f"{usuario}.json").unlink(missing_ok=True)
