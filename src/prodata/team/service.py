"""Serviço da equipe: espaços, identidade, membros e fluxos de cada espaço (spec 047).

Sem nenhum espaço configurado, nada aqui toca a rede nem o cofre: a identidade só é gerada quando a pessoa cria ou
entra num espaço (constituição, princípio VIII; RF-4702).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import ValidationError

from prodata.domain.workflow import Workflow
from prodata.errors import InvalidInputError, NotFoundError
from prodata.services.workflows import WorkflowRepository
from prodata.team.identity import Identity, IdentityStore
from prodata.team.members import MembersStore
from prodata.team.repository import SpaceFlow, SpaceRepository
from prodata.team.signing import (
    RANK,
    ROLE_NAMES,
    Member,
    Members,
    Role,
    Signature,
    check_flow,
    sign_flow,
    sign_members,
)
from prodata.team.workspaces import Space, Workspaces

READABLE = ("ok", "somente_leitura")


class TeamService:
    def __init__(self, workspaces: Workspaces, identity: IdentityStore, library: WorkflowRepository,
                 state_dir: Path | None = None) -> None:  # fmt: skip
        self.workspaces = workspaces
        self.identity = identity
        self.library = library
        self.state_dir = state_dir or Path("equipe")  # listas de membros aceitas: só neste computador

    # ------------------------------------------------------------------ espaços e papéis

    def _members_store(self, space_id: str) -> MembersStore:
        return MembersStore(
            self.workspaces.root(space_id), space_id, self.state_dir / f"{space_id}-membros.json"
        )

    def members(self, space_id: str) -> tuple[Members | None, str | None]:
        return self._members_store(space_id).current()

    def my_role(self, members: Members | None) -> Role | None:
        if members is None:
            return None
        me = self.identity.current()
        found = members.member(me.usuario, me.chave_publica)
        return found.papel if found else None

    def describe(self, space: Space) -> dict[str, Any]:
        """O espaço com o que a tela precisa: estado da pasta, papel, pedido pendente e proteção (RF-4713)."""
        out: dict[str, Any] = {**space.model_dump(), "papel": None, "pedido": False, "protegido": None}
        if space.estado not in READABLE:
            return out
        members, reason = self.members(space.id)
        if reason:
            out["protegido"] = reason
            return out
        role = self.my_role(members)
        out["papel"] = role
        if role is None:
            me = self.identity.current()
            out["pedido"] = any(r.usuario == me.usuario for r in self._members_store(space.id).requests())
        return out

    def overview(self) -> dict[str, object]:
        """O que a tela precisa saber. Sem espaço: só ``configurado: false`` (nenhuma chave gerada)."""
        if not self.workspaces.configured():
            return {"configurado": False, "espacos": []}
        me = self.identity.current()
        return {
            "configurado": True,
            "identidade": {"usuario": me.usuario, "nome": me.nome, "tem_nome": self.identity.has_name()},
            "espacos": [self.describe(s) for s in self.workspaces.spaces()],
        }

    def me(self) -> Identity:
        return self.identity.current()

    def create(self, raw_path: str, nome: str) -> dict[str, Any]:
        """Cria o espaço; quem cria é o primeiro administrador, na lista de membros assinada (RF-4711)."""
        space = self.workspaces.create(raw_path, nome)
        me = self.identity.current()
        first = [
            Member(usuario=me.usuario, nome=me.nome, chave_publica=me.chave_publica, papel="administrador")
        ]
        self._members_store(space.id).write(sign_members(self.identity, space.id, 1, first))
        return self.describe(self.workspaces.get(space.id))

    def join(self, raw_path: str) -> dict[str, Any]:
        """Entra no espaço; quem não está na lista deixa um pedido de entrada para um administrador (RF-4712)."""
        space = self.workspaces.join(raw_path)
        members, reason = self.members(space.id)
        if reason is None and self.my_role(members) is None and space.estado == "ok":
            self._members_store(space.id).add_request(self.identity.current())
        return self.describe(self.workspaces.get(space.id))

    def _require(self, space_id: str, need: Role) -> tuple[Space, SpaceRepository, Members]:
        space = self.workspaces.get(space_id)
        if space.estado not in READABLE:
            raise InvalidInputError(space.motivo or "O espaço não está disponível agora.")
        members, reason = self.members(space_id)
        if members is None:
            raise InvalidInputError(f"{reason} O espaço está protegido.")
        role = self.my_role(members)
        if role is None:
            raise InvalidInputError(
                "Você ainda não é membro deste espaço: um administrador precisa aceitar o seu pedido."
            )
        if RANK[role] < RANK[need]:
            raise InvalidInputError(
                f"Seu papel neste espaço é {ROLE_NAMES[role]}: isso é para {ROLE_NAMES[need]} ou acima."
            )
        if RANK[need] >= RANK["editor"] and space.estado != "ok":
            raise InvalidInputError(space.motivo or "O espaço está só para leitura.")
        return space, SpaceRepository(self.workspaces.root(space_id)), members

    # ------------------------------------------------------------------ fluxos

    def flows(self, space_id: str) -> list[SpaceFlow]:
        return self._require(space_id, "leitor")[1].flows()

    def get(self, space_id: str, workflow_id: str) -> tuple[Workflow, str | None]:
        """O fluxo e, se a versão não confere, o motivo (abre protegido e não executa, RF-4715)."""
        space = self.workspaces.get(space_id)
        if space.estado not in READABLE:
            raise InvalidInputError(space.motivo or "O espaço não está disponível agora.")
        repo = SpaceRepository(self.workspaces.root(space_id))
        workflow = repo.get(workflow_id)
        members, reason = self.members(space_id)
        if members is None:
            return workflow, f"{reason} Nada do espaço executa até um administrador conferir."
        raw = repo.signature(workflow_id)
        try:
            signature = Signature.model_validate_json(raw) if raw else None
        except ValidationError, ValueError:
            signature = None
        return workflow, check_flow(signature, space_id, workflow, members)

    def save(self, space_id: str, workflow: Workflow) -> Workflow:
        _, repo, _ = self._require(space_id, "editor")
        clean = workflow.model_copy(update={"samples": {}})
        return repo.save(clean, sign_flow(self.identity, space_id, clean).model_dump_json(indent=1))

    def move_from_library(self, space_id: str, workflow_id: str) -> Workflow:
        """Leva um fluxo de Meus fluxos para o espaço: grava lá primeiro e só então tira da biblioteca."""
        _, repo, _ = self._require(space_id, "editor")
        if repo.exists(workflow_id):
            raise InvalidInputError(
                "Já existe um fluxo com o mesmo identificador no espaço: use Salvar no espaço como cópia."
            )
        saved = self.save(space_id, self.library.get(workflow_id))
        self.library.delete(workflow_id)
        return saved

    def copy_to_library(self, space_id: str, workflow_id: str, new_id: str) -> Workflow:
        """Faz uma cópia do fluxo do espaço em Meus fluxos, com outro id (a do espaço continua lá)."""
        workflow = self._require(space_id, "leitor")[1].get(workflow_id)
        copy = workflow.model_copy(update={"id": new_id, "name": f"{workflow.name} (cópia)"})
        return self.library.save(copy)

    # ------------------------------------------------------------------ membros (administradores)

    def members_view(self, space_id: str) -> dict[str, Any]:
        members, reason = self.members(space_id)
        store = self._members_store(space_id)
        role = self.my_role(members)
        admins = members.admins() if members else []
        return {
            "protegido": reason,
            "papel": role,
            "membros": [m.model_dump(exclude={"chave_publica"}) for m in members.membros] if members else [],
            "pedidos": [r.model_dump(mode="json", exclude={"chave_publica"}) for r in store.requests()]
            if role == "administrador"
            else [],
            "um_administrador": len(admins) == 1,
        }

    def change_members(
        self, space_id: str, action: str, usuario: str, papel: Role = "leitor"
    ) -> dict[str, Any]:
        """Aceitar ou recusar um pedido, mudar o papel, remover alguém: uma lista nova, assinada por um administrador."""
        _, _, members = self._require(space_id, "administrador")
        store = self._members_store(space_id)
        people = [m.model_copy() for m in members.membros]
        if action == "recusar":
            store.remove_request(usuario)
            return self.members_view(space_id)
        if action == "aceitar":
            request = next((r for r in store.requests() if r.usuario == usuario), None)
            if request is None:
                raise NotFoundError("Esse pedido não está mais no espaço.")
            people = [m for m in people if m.usuario != usuario]
            people.append(
                Member(
                    usuario=request.usuario,
                    nome=request.nome,
                    chave_publica=request.chave_publica,
                    papel=papel,
                )
            )
        elif action in ("papel", "remover"):
            target = next((m for m in people if m.usuario == usuario), None)
            if target is None:
                raise NotFoundError("Essa pessoa não está na lista de membros.")
            if action == "papel":
                target.papel = papel
            else:
                people = [m for m in people if m.usuario != usuario]
        else:
            raise InvalidInputError("Ação desconhecida.")
        if not any(m.papel == "administrador" for m in people):
            raise InvalidInputError(
                "O espaço precisa de pelo menos um administrador: promova outra pessoa antes."
            )
        store.write(sign_members(self.identity, space_id, members.versao + 1, people))
        if action == "aceitar":
            store.remove_request(usuario)
        return self.members_view(space_id)
