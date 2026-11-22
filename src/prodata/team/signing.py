"""Assinaturas do espaço da equipe (spec 047, RF-4711..4715; constituição, princípio VIII).

Duas coisas são assinadas:

- **a lista de membros e papéis**, por um administrador. Cada computador guarda a última lista que aceitou e só
  aceita uma nova se ela vier assinada por um administrador da lista aceita e tiver número de versão maior: ninguém
  se promove editando o arquivo à mão, nem restaura uma lista antiga de quando ainda era administrador;
- **cada versão salva de um fluxo**, por quem salvou. Vale só se a assinatura confere, se o conteúdo é o mesmo que foi
  assinado e se quem assinou tinha o papel para isso na lista vigente.

O que se assina é o conteúdo canônico (JSON com chaves ordenadas, sem a amostra dos dados) mais o contexto — o espaço,
o fluxo e o tipo —, para uma assinatura não servir em outro espaço, outro fluxo ou outro papel.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from prodata.domain.workflow import Workflow
from prodata.team.identity import USER_PATTERN, Identity, IdentityStore, verify

Role = Literal["leitor", "editor", "publicador", "administrador"]
RANK: dict[str, int] = {"leitor": 0, "editor": 1, "publicador": 2, "administrador": 3}
ROLE_NAMES = {
    "leitor": "Leitor",
    "editor": "Editor",
    "publicador": "Publicador",
    "administrador": "Administrador",
}
FORMAT = 1


def _canonical(data: Any) -> bytes:
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


# ---------------------------------------------------------------- membros


class Member(BaseModel):
    usuario: str = Field(pattern=USER_PATTERN)
    nome: str = Field(min_length=1, max_length=80)
    chave_publica: str = Field(min_length=40, max_length=60)
    papel: Role = "leitor"


class Members(BaseModel):
    formato: int = FORMAT
    espaco: str
    versao: int = Field(ge=1)
    membros: list[Member]
    assinada_por: str = Field(pattern=USER_PATTERN)
    chave_publica: str
    assinatura: str
    quando: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def member(self, usuario: str, chave: str | None = None) -> Member | None:
        """O membro com este usuário (e, se informada, esta chave: a mesma pessoa, não alguém com o mesmo nome)."""
        return next(
            (m for m in self.membros if m.usuario == usuario and (chave is None or m.chave_publica == chave)),
            None,
        )

    def admins(self) -> list[Member]:
        return [m for m in self.membros if m.papel == "administrador"]


def members_payload(espaco: str, versao: int, membros: list[Member]) -> bytes:
    people = sorted((m.model_dump() for m in membros), key=lambda m: m["usuario"])
    return b"membros|" + _canonical({"espaco": espaco, "versao": versao, "membros": people})


def sign_members(identity: IdentityStore, espaco: str, versao: int, membros: list[Member]) -> Members:
    me = identity.current()
    return Members(espaco=espaco, versao=versao, membros=membros, assinada_por=me.usuario,
                   chave_publica=me.chave_publica, assinatura=identity.sign(members_payload(espaco, versao, membros)))  # fmt: skip


def members_digest(m: Members) -> str:
    return hashlib.sha256(members_payload(m.espaco, m.versao, m.membros)).hexdigest()


def check_members(new: Members, accepted: Members | None, espaco: str) -> str | None:
    """Motivo para recusar a lista de membros, ou None se ela vale.

    Sem lista aceita neste computador (primeira vez no espaço), vale a lista que se sustenta sozinha: assinada por um
    administrador dela mesma. Depois disso, só uma lista assinada por um administrador da lista aceita e com versão
    maior (ou a mesma lista de novo)."""
    if new.espaco != espaco:
        return "A lista de membros é de outro espaço."
    if not verify(new.chave_publica, members_payload(new.espaco, new.versao, new.membros), new.assinatura):
        return "A lista de membros foi alterada fora do programa (a assinatura não confere)."
    if accepted is None:
        signer = new.member(new.assinada_por, new.chave_publica)
        if signer is None or signer.papel != "administrador":
            return "A lista de membros não foi assinada por um administrador do espaço."
        return None
    if new.versao == accepted.versao:
        return (
            None
            if members_digest(new) == members_digest(accepted)
            else "A lista de membros foi trocada por outra com o mesmo número de versão."
        )
    if new.versao < accepted.versao:
        return "A lista de membros é mais antiga que a já aceita neste computador (alguém restaurou uma lista antiga?)."
    signer = accepted.member(new.assinada_por, new.chave_publica)
    if signer is None or signer.papel != "administrador":
        return "A lista de membros foi mudada por alguém que não era administrador."
    return None


# ---------------------------------------------------------------- versões dos fluxos

Kind = Literal["versao", "oficial", "definicao"]


class Signature(BaseModel):
    formato: int = FORMAT
    tipo: Kind = "versao"
    espaco: str
    fluxo: str
    autor: str = Field(pattern=USER_PATTERN)
    nome: str = ""
    chave_publica: str
    sha256: str
    assinatura: str
    quando: datetime = Field(default_factory=lambda: datetime.now(UTC))


def flow_content(workflow: Workflow) -> bytes:
    return _canonical(workflow.model_dump(mode="json", by_alias=True, exclude={"samples"}))


def flow_payload(espaco: str, fluxo: str, kind: Kind, content: bytes) -> bytes:
    return f"{kind}|{espaco}|{fluxo}|".encode() + content


def sign_flow(identity: IdentityStore, espaco: str, workflow: Workflow, kind: Kind = "versao") -> Signature:
    me: Identity = identity.current()
    content = flow_content(workflow)
    return Signature(tipo=kind, espaco=espaco, fluxo=workflow.id, autor=me.usuario, nome=me.nome,
                     chave_publica=me.chave_publica, sha256=hashlib.sha256(content).hexdigest(),
                     assinatura=identity.sign(flow_payload(espaco, workflow.id, kind, content)))  # fmt: skip


def check_flow(signature: Signature | None, espaco: str, workflow: Workflow, members: Members | None,
               kind: Kind = "versao") -> str | None:  # fmt: skip
    """Motivo para não executar o fluxo, ou None se a versão confere (RF-4714, RF-4715)."""
    if members is None:
        return (
            "A lista de membros do espaço não confere: nada do espaço executa até um administrador conferir."
        )
    if signature is None:
        return "Este fluxo foi alterado fora do programa: não tem assinatura de quem salvou."
    content = flow_content(workflow)
    if (signature.tipo != kind or signature.espaco != espaco or signature.fluxo != workflow.id
            or hashlib.sha256(content).hexdigest() != signature.sha256
            or not verify(signature.chave_publica, flow_payload(espaco, workflow.id, kind, content), signature.assinatura)):  # fmt: skip
        who = signature.nome or signature.autor
        return f"Este fluxo foi alterado fora do programa depois de salvo por {who}."
    author = members.member(signature.autor, signature.chave_publica)
    if author is None:
        return f"Salvo por {signature.nome or signature.autor}, que não é membro do espaço."
    need = "publicador" if kind == "oficial" else "editor"
    if RANK[author.papel] < RANK[need]:
        what = "publicar a versão oficial" if kind == "oficial" else "editar"
        return f"Salvo por {author.nome}, que não tem permissão para {what} ({ROLE_NAMES[author.papel]})."
    return None


# ---------------------------------------------------------------- definições da equipe (spec 048)


def document_content(data: dict[str, Any]) -> bytes:
    return _canonical(data)


def sign_document(identity: IdentityStore, espaco: str, path: str, data: dict[str, Any]) -> Signature:
    """Assina uma definição compartilhada (``path``: ``conexoes/vendas``), no mesmo formato da versão de um fluxo."""
    me: Identity = identity.current()
    content = document_content(data)
    return Signature(tipo="definicao", espaco=espaco, fluxo=path, autor=me.usuario, nome=me.nome,
                     chave_publica=me.chave_publica, sha256=hashlib.sha256(content).hexdigest(),
                     assinatura=identity.sign(flow_payload(espaco, path, "definicao", content)))  # fmt: skip


def check_document(signature: Signature | None, espaco: str, path: str, data: dict[str, Any],
                   members: Members | None) -> str | None:  # fmt: skip
    """Motivo para não usar a definição, ou None se confere: assinada por um Editor da lista vigente (RF-4805)."""
    if members is None:
        return "A lista de membros do espaço não confere."
    if signature is None:
        return "Foi alterada fora do programa: não tem assinatura de quem salvou."
    content = document_content(data)
    if (signature.tipo != "definicao" or signature.espaco != espaco or signature.fluxo != path
            or hashlib.sha256(content).hexdigest() != signature.sha256
            or not verify(signature.chave_publica, flow_payload(espaco, path, "definicao", content), signature.assinatura)):  # fmt: skip
        return f"Foi alterada fora do programa depois de salva por {signature.nome or signature.autor}."
    author = members.member(signature.autor, signature.chave_publica)
    if author is None:
        return f"Salva por {signature.nome or signature.autor}, que não é membro do espaço."
    if RANK[author.papel] < RANK["editor"]:
        return f"Salva por {author.nome}, que não tem permissão para editar ({ROLE_NAMES[author.papel]})."
    return None
