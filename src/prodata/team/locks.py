"""Marcas de edição: quem está editando cada fluxo do espaço (spec 047, RF-4721..4724).

Uma marca é um aviso, não uma trava: a sincronização pode atrasar e duas pessoas podem acabar editando ao mesmo tempo
(o conflito é tratado no Salvar, RF-4761). A marca se renova enquanto o fluxo está aberto e expira sozinha se não for
renovada, com folga para o atraso da sincronização: nunca fica presa para sempre.
"""

from __future__ import annotations

import re
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from prodata.domain.workflow import ID_PATTERN
from prodata.errors import InvalidInputError
from prodata.team.identity import USER_PATTERN, Identity
from prodata.team.repository import atomic_write
from prodata.team.workspaces import CONTROL

LOCKS_DIR = "edicao"
RENEW_EVERY = timedelta(seconds=30)  # a tela renova nesse ritmo enquanto o fluxo está aberto
EXPIRES_AFTER = timedelta(
    minutes=3
)  # sem renovação por esse tempo, a marca não vale (folga para a sincronização)
_ID = re.compile(ID_PATTERN)
# Quando este computador viu cada marca (fluxo, pessoa, renovação) pela primeira vez: só neste processo, em memória.
_FIRST_SEEN: dict[tuple[str, str, str], datetime] = {}


class Lock(BaseModel):
    usuario: str = Field(pattern=USER_PATTERN)
    nome: str
    maquina: str = ""
    desde: datetime
    renovado_em: datetime

    def expired(self, now: datetime, first_seen: datetime) -> bool:
        """Vencida pela data escrita nela (relógios em dia) ou por estar parada, sem renovação, há mais que o prazo
        desde que este computador a viu assim. A segunda regra cobre o relógio adiantado de outro computador, que
        deixaria a marca valendo para sempre."""
        written = now - self.renovado_em > EXPIRES_AFTER
        stale_here = now - first_seen > EXPIRES_AFTER
        return written or stale_here


class LockStore:
    def __init__(self, space_root: Path, clock: type[datetime] = datetime) -> None:
        self.folder = space_root / CONTROL / LOCKS_DIR
        self._clock = clock

    def _now(self) -> datetime:
        return self._clock.now(UTC)

    def _path(self, workflow_id: str) -> Path:
        if not _ID.match(workflow_id):
            raise InvalidInputError("Identificador de fluxo inválido.")
        return self.folder / f"{workflow_id}.json"

    def current(self, workflow_id: str) -> Lock | None:
        """A marca que vale agora (não expirada), ou None."""
        path = self._path(workflow_id)
        try:
            lock = Lock.model_validate_json(path.read_text(encoding="utf-8"))
        except OSError, ValidationError, ValueError:
            return None
        now = self._now()
        key = (str(path), lock.usuario, lock.renovado_em.isoformat())  # muda a cada renovação
        if (
            key not in _FIRST_SEEN and len(_FIRST_SEEN) > 2000
        ):  # sessão longa: esquece o que já venceu há tempo
            for old in [k for k, seen in _FIRST_SEEN.items() if now - seen > EXPIRES_AFTER * 4]:
                del _FIRST_SEEN[old]
        first_seen = _FIRST_SEEN.setdefault(key, now)
        return None if lock.expired(now, first_seen) else lock

    def other(self, workflow_id: str, me: Identity) -> Lock | None:
        """A marca de outra pessoa, se houver; a minha não conta."""
        lock = self.current(workflow_id)
        return lock if lock and lock.usuario != me.usuario else None

    def acquire(self, workflow_id: str, me: Identity, *, force: bool = False) -> Lock | None:
        """Marca o fluxo como sendo editado por mim. Se outra pessoa está editando e não é para forçar, devolve a
        marca dela sem mexer em nada (RF-4721)."""
        theirs = self.other(workflow_id, me)
        if theirs and not force:
            return theirs
        now = self._now()
        mine = self.current(workflow_id)
        since = mine.desde if mine and mine.usuario == me.usuario else now
        lock = Lock(
            usuario=me.usuario, nome=me.nome, maquina=socket.gethostname()[:64], desde=since, renovado_em=now
        )
        self.folder.mkdir(parents=True, exist_ok=True)
        atomic_write(self._path(workflow_id), lock.model_dump_json())
        return None

    def renew(self, workflow_id: str, me: Identity) -> bool:
        """Renova a minha marca. Devolve False se ela não é mais minha (outra pessoa marcou por cima)."""
        lock = self.current(workflow_id)
        if lock is not None and lock.usuario != me.usuario:
            return False
        self.acquire(workflow_id, me, force=True)
        return True

    def release(self, workflow_id: str, me: Identity) -> None:
        """Solta a minha marca. A de outra pessoa fica como está."""
        path = self._path(workflow_id)
        lock = self.current(workflow_id)
        if lock is None or lock.usuario == me.usuario:
            path.unlink(missing_ok=True)

    def all(self) -> dict[str, Lock]:
        """Fluxo → marca que vale agora, para a biblioteca mostrar quem está editando (RF-4724)."""
        out: dict[str, Lock] = {}
        if not self.folder.is_dir():
            return out
        for path in self.folder.glob("*.json"):
            lock = self.current(path.stem) if _ID.match(path.stem) else None
            if lock:
                out[path.stem] = lock
        return out
