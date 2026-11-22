"""Comentários nas caixas de um fluxo do espaço (spec 048, RF-4811..4816).

Cada ação é um **evento** num arquivo próprio, assinado por quem escreveu: ``_equipe/comentarios/<fluxo>/
<AAAAMMDD-HHMMSS-ffffff>-<usuário>-<acaso>.json``. Os arquivos só são acrescentados, então duas pessoas comentando ao
mesmo tempo nunca escrevem no mesmo arquivo e a sincronização não cria cópia de conflito. A conversa é a dobra dos
eventos em ordem; evento sem assinatura válida, de quem não é membro ou de quem não podia (apagar comentário de outra
pessoa sem ser administrador) é ignorado. Nada disso vai no arquivo do fluxo: comentar não cria versão.
"""

from __future__ import annotations

import json
import re
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from prodata.domain.workflow import ID_PATTERN
from prodata.errors import InvalidInputError, NotFoundError
from prodata.team.identity import USER_PATTERN, IdentityStore, verify
from prodata.team.repository import HeldFileError, atomic_write
from prodata.team.signing import Members
from prodata.team.workspaces import CONTROL

EventKind = Literal["comentario", "resposta", "editar", "resolver", "reabrir", "apagar"]
COMMENTS_DIR = "comentarios"
MAX_TEXT = 2000
_ID = re.compile(ID_PATTERN)
_EVENT = re.compile(r"^\d{8}-\d{6}-\d{6}-[A-Za-z0-9._-]{1,64}-[a-f0-9]{8}$")


class CommentEvent(BaseModel):
    id: str = ""
    tipo: EventKind
    espaco: str
    fluxo: str = Field(pattern=ID_PATTERN)
    alvo: str = ""  # o comentário a que a resposta, a edição, o resolver ou o apagar se referem
    caixa: str = ""
    rotulo: str = Field("", max_length=120)  # o nome da caixa quando comentou (para caixa removida)
    texto: str = Field("", max_length=MAX_TEXT)
    usuario: str = Field("x", pattern=USER_PATTERN)
    nome: str = ""
    chave_publica: str = ""
    quando: datetime = Field(default_factory=lambda: datetime.now(UTC))
    assinatura: str = ""


def _payload(event: CommentEvent) -> bytes:
    data = event.model_dump(mode="json", exclude={"assinatura"})
    return (
        b"comentario|" + json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    )


class Reply(BaseModel):
    id: str
    texto: str
    autor: str
    nome: str
    quando: datetime
    editado: bool = False
    minha: bool = False


class Thread(BaseModel):
    id: str
    caixa: str
    rotulo: str
    texto: str
    autor: str
    nome: str
    quando: datetime
    editado: bool = False
    resolvido: bool = False
    resolvido_por: str = ""
    minha: bool = False
    respostas: list[Reply] = Field(default_factory=list)
    ultima: datetime | None = None  # o momento da mensagem mais nova da conversa


class CommentStore:
    def __init__(self, space_root: Path, space_id: str) -> None:
        self.root = space_root / CONTROL / COMMENTS_DIR
        self.space_id = space_id

    def _dir(self, workflow_id: str) -> Path:
        if not _ID.match(workflow_id):
            raise InvalidInputError("Identificador de fluxo inválido.")
        return self.root / workflow_id

    def add(self, event: CommentEvent, identity: IdentityStore) -> CommentEvent:
        """Assina e grava um evento novo (nunca reescreve um arquivo que já existe)."""
        me = identity.current()
        now = datetime.now(UTC)
        event_id = f"{now.strftime('%Y%m%d-%H%M%S-%f')}-{me.usuario}-{secrets.token_hex(4)}"
        signed = event.model_copy(update={"id": event_id, "espaco": self.space_id, "usuario": me.usuario,
                                          "nome": me.nome, "chave_publica": me.chave_publica, "quando": now,
                                          "assinatura": ""})  # fmt: skip
        signed = signed.model_copy(update={"assinatura": identity.sign(_payload(signed))})
        folder = self._dir(event.fluxo)
        folder.mkdir(parents=True, exist_ok=True)
        try:
            atomic_write(folder / f"{event_id}.json", signed.model_dump_json(indent=1))
        except PermissionError as exc:
            raise HeldFileError("A pasta do espaço segurou o arquivo: tente de novo em instantes.") from exc
        return signed

    def events(self, workflow_id: str, members: Members | None) -> list[CommentEvent]:
        """Os eventos que valem, em ordem: assinatura válida, deste espaço e deste fluxo, de quem é membro."""
        folder = self._dir(workflow_id)
        if members is None or not folder.is_dir():
            return []
        out: list[CommentEvent] = []
        for path in folder.glob("*.json"):
            if not _EVENT.match(path.stem):
                continue
            try:
                event = CommentEvent.model_validate_json(path.read_text(encoding="utf-8"))
            except OSError, ValidationError, ValueError:
                continue
            if (event.id != path.stem or event.espaco != self.space_id or event.fluxo != workflow_id
                    or not verify(event.chave_publica, _payload(event), event.assinatura)
                    or members.member(event.usuario, event.chave_publica) is None):  # fmt: skip
                continue
            out.append(event)
        out.sort(key=lambda e: (e.quando, e.id))
        return out


def fold(events: list[CommentEvent], members: Members, me: str) -> list[Thread]:
    """A conversa de cada comentário, aplicando as respostas, edições, resolver, reabrir e apagar em ordem."""
    threads: dict[str, Thread] = {}
    replies: dict[str, tuple[str, Reply]] = {}  # resposta → (comentário, resposta)
    admins = {m.usuario for m in members.admins()}
    authors: dict[str, str] = {}
    for e in events:
        if e.tipo == "comentario" and e.texto.strip():
            threads[e.id] = Thread(id=e.id, caixa=e.caixa, rotulo=e.rotulo, texto=e.texto, autor=e.usuario,
                                   nome=e.nome, quando=e.quando, minha=e.usuario == me, ultima=e.quando)  # fmt: skip
            authors[e.id] = e.usuario
        elif e.tipo == "resposta" and e.alvo in threads and e.texto.strip():
            reply = Reply(
                id=e.id, texto=e.texto, autor=e.usuario, nome=e.nome, quando=e.quando, minha=e.usuario == me
            )
            threads[e.alvo].respostas.append(reply)
            threads[e.alvo].ultima = e.quando
            replies[e.id] = (e.alvo, reply)
            authors[e.id] = e.usuario
        elif e.tipo == "editar" and authors.get(e.alvo) == e.usuario and e.texto.strip():
            if e.alvo in threads:
                threads[e.alvo].texto, threads[e.alvo].editado = e.texto, True
            elif e.alvo in replies:
                replies[e.alvo][1].texto, replies[e.alvo][1].editado = e.texto, True
        elif e.tipo in ("resolver", "reabrir") and e.alvo in threads:
            threads[e.alvo].resolvido = e.tipo == "resolver"
            threads[e.alvo].resolvido_por = e.nome if e.tipo == "resolver" else ""
        elif e.tipo == "apagar" and (authors.get(e.alvo) == e.usuario or e.usuario in admins):
            if e.alvo in threads:
                del threads[e.alvo]
            elif e.alvo in replies:
                thread_id, reply = replies.pop(e.alvo)
                if thread_id in threads:
                    threads[thread_id].respostas = [
                        r for r in threads[thread_id].respostas if r.id != reply.id
                    ]
    return sorted(threads.values(), key=lambda t: (t.resolvido, -(t.ultima or t.quando).timestamp()))


def new_since(events: list[CommentEvent], since: str | None, me: str) -> list[str]:
    """Os comentários e respostas de outras pessoas depois da última vez que eu vi a conversa (RF-4814)."""
    stamp = datetime.fromisoformat(since) if since else None
    return [e.id for e in events if e.tipo in ("comentario", "resposta") and e.usuario != me
            and (stamp is None or e.quando > stamp)]  # fmt: skip


def check_event(tipo: str, texto: str, alvo: str, caixa: str) -> None:
    if tipo in ("comentario", "resposta", "editar") and not texto.strip():
        raise InvalidInputError("Escreva o comentário.")
    if tipo == "comentario" and not caixa:
        raise InvalidInputError("Escolha a caixa do comentário.")
    if tipo != "comentario" and not _EVENT.match(alvo):
        raise NotFoundError("Esse comentário não existe mais.")


def view(threads: list[Thread], new_ids: list[str]) -> dict[str, Any]:
    open_by_box: dict[str, int] = {}
    for t in threads:
        if not t.resolvido:
            open_by_box[t.caixa] = open_by_box.get(t.caixa, 0) + 1
    return {"conversas": [t.model_dump(mode="json") for t in threads], "por_caixa": open_by_box,
            "novos": len(new_ids), "novos_ids": new_ids}  # fmt: skip
