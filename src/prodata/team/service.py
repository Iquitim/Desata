"""Serviço da equipe: espaços, identidade, membros e fluxos de cada espaço (spec 047).

Sem nenhum espaço configurado, nada aqui toca a rede nem o cofre: a identidade só é gerada quando a pessoa cria ou
entra num espaço (constituição, princípio VIII; RF-4702).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from prodata.domain.workflow import Workflow
from prodata.errors import ConflictError, InvalidInputError, NotFoundError
from prodata.services.workflows import WorkflowRepository
from prodata.team.identity import Identity, IdentityStore
from prodata.team.local_state import LocalState
from prodata.team.locks import LockStore
from prodata.team.members import MembersStore
from prodata.team.repository import HeldFileError, SpaceFlow, SpaceRepository
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
from prodata.team.trust_diff import changed_parts, sensitive_parts
from prodata.team.versions import SpaceOrigin, SpaceVersionInfo, SpaceVersions, content_sha
from prodata.team.workspaces import Space, Workspaces

READABLE = ("ok", "somente_leitura")
log = logging.getLogger(__name__)


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
        """Os fluxos do espaço, com quem está editando cada um agora (RF-4724)."""
        _, repo, _ = self._require(space_id, "leitor")
        self.flush_pending(space_id)  # o que a sincronização segurou antes vai agora, se der (RF-4763)
        self.adopt_conflict_copies(space_id)  # cópias de conflito viram versões, não fluxos soltos (RF-4762)
        locks = LockStore(repo.root).all()
        me = self.identity.current()
        out = []
        for f in repo.flows():
            lock = locks.get(f.id)
            if lock and lock.usuario != me.usuario:
                f = f.model_copy(update={"editando": lock.nome, "editando_desde": lock.desde})
            out.append(f)
        return out

    # ------------------------------------------------------------------ quem está editando (RF-4721..4723)

    def editing(self, space_id: str, workflow_id: str, action: str, *, force: bool = False) -> dict[str, Any]:
        """``abrir``: diz se o fluxo abre para editar, só para ver (papel ou pasta) ou se outra pessoa está editando;
        ``renovar``/``soltar``: a minha marca; ``estado``: quem está editando agora."""
        space = self.workspaces.get(space_id)
        if space.estado not in READABLE:
            raise InvalidInputError(space.motivo or "O espaço não está disponível agora.")
        members, reason = self.members(space_id)
        role = self.my_role(members)
        if role is None:
            raise InvalidInputError(reason or "Você ainda não é membro deste espaço.")
        locks = LockStore(self.workspaces.root(space_id))
        me = self.identity.current()

        def who(lock: Any) -> dict[str, Any] | None:
            return (
                {"nome": lock.nome, "desde": lock.desde.isoformat(), "maquina": lock.maquina}
                if lock
                else None
            )

        if action == "estado":  # também diz qual é a versão de trabalho de agora, para o Recarregar (RF-4733)
            return {
                "editando": who(locks.other(workflow_id, me)),
                "versao": self.latest(space_id, workflow_id),
            }
        if action == "soltar":
            locks.release(workflow_id, me)
            return {"editando": None}
        if action == "renovar":
            can = RANK[role] >= RANK["editor"] and space.estado == "ok"  # Leitor não marca nada
            sent = self.flush_pending(space_id) if can else []
            return {"ok": can and locks.renew(workflow_id, me), "editando": who(locks.other(workflow_id, me)),
                    "versao": self.latest(space_id, workflow_id), "enviados": sent,
                    "pendente": workflow_id in self._local(space_id).pending()}  # fmt: skip
        if RANK[role] < RANK["editor"]:
            return {
                "modo": "ver",
                "motivo": f"Seu papel neste espaço é {ROLE_NAMES[role]}: você abre só para ver.",
            }
        if space.estado != "ok":
            return {"modo": "ver", "motivo": space.motivo}
        theirs = locks.acquire(workflow_id, me, force=force)
        if theirs:
            return {"modo": "conflito", "editando": who(theirs)}
        return {"modo": "editar"}

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

    # ------------------------------------------------------------------ versões, conflito e envio adiado (RF-4731..4763)

    def _local(self, space_id: str) -> LocalState:
        return LocalState(self.state_dir, space_id)

    def _versions(self, space_id: str) -> SpaceVersions:
        return SpaceVersions(self.workspaces.root(space_id), space_id)

    @staticmethod
    def _signature_of(raw: str | None) -> Signature | None:
        try:
            return Signature.model_validate_json(raw) if raw else None
        except ValidationError, ValueError:
            return None

    def _current_sha(self, repo: SpaceRepository, workflow_id: str) -> str | None:
        try:
            return content_sha(repo.get(workflow_id)) if repo.exists(workflow_id) else None
        except InvalidInputError:
            return "ilegivel"  # arquivo estragado no espaço: qualquer base é diferente, nada é sobrescrito sem aviso

    def _author_name(self, repo: SpaceRepository, workflow_id: str) -> str:
        sig = self._signature_of(repo.signature(workflow_id))
        return (sig.nome or sig.autor) if sig else "Outra pessoa"

    def _record(self, space_id: str, workflow: Workflow, origin: SpaceOrigin, sig: Signature | None,
                author: str | None = None) -> None:  # fmt: skip
        """Guardar a versão nunca impede o Salvar: se a pasta segurar, a versão de trabalho já foi gravada."""
        try:
            self._versions(space_id).record(workflow, origin, sig, author)
        except (OSError, InvalidInputError) as exc:
            log.warning("Versão do espaço não guardada: %s (%s)", workflow.id, exc)

    def save(self, space_id: str, workflow: Workflow, *, base: str | None = None, force: bool = False,
             origin: SpaceOrigin = "manual") -> dict[str, Any]:  # fmt: skip
        """Assina e grava. ``base``: a impressão do que a pessoa abriu; se o arquivo do espaço mudou desde então
        (outra pessoa salvou), nada é sobrescrito: a versão dela vira uma versão do fluxo e o Salvar avisa (RF-4761).
        Arquivo preso pela sincronização: a versão fica neste computador e o envio é adiado (RF-4763)."""
        _, repo, _ = self._require(space_id, "editor")
        clean = workflow.model_copy(update={"samples": {}})
        sig = sign_flow(self.identity, space_id, clean)
        local = self._local(space_id)
        current = self._current_sha(repo, clean.id)
        if base is not None and not force and current not in (None, base, sig.sha256):
            who = self._author_name(repo, clean.id)
            self._record(space_id, clean, "conflito", sig)
            local.drop_pending(clean.id)
            raise ConflictError(
                f"{who} salvou enquanto você editava: as duas versões estão em Versões anteriores. Nada foi perdido."
            )
        adiado = False
        try:
            repo.save(clean, sig.model_dump_json(indent=1))
            local.drop_pending(clean.id)
        except HeldFileError:
            local.add_pending(clean.id, {"base": current, "fluxo": clean.model_dump(mode="json", by_alias=True),
                                         "assinatura": sig.model_dump(mode="json")})  # fmt: skip
            adiado = True
        if not adiado:
            self._record(space_id, clean, origin, sig)
        local.set_seen(clean.id, sig.sha256)
        local.set_trusted(clean.id, sensitive_parts(clean))  # o que eu mesmo mudei não pede conferência
        return {"fluxo": clean, "sha256": sig.sha256, "adiado": adiado}

    def flush_pending(self, space_id: str) -> list[str]:
        """Tenta enviar o que ficou adiado (RF-4763). Se outra pessoa salvou nesse meio-tempo, a versão adiada entra
        como versão de conflito em vez de sobrescrever. Devolve os fluxos enviados."""
        local = self._local(space_id)
        pending = local.pending()
        if not pending:
            return []
        try:
            _, repo, _ = self._require(space_id, "editor")
        except InvalidInputError:
            return []
        sent: list[str] = []
        for wid, item in pending.items():
            try:
                wf = Workflow.model_validate(item.get("fluxo"))
                sig = Signature.model_validate(item.get("assinatura"))
            except ValidationError, ValueError:
                local.drop_pending(wid)
                continue
            current = self._current_sha(repo, wid)
            try:
                if current not in (None, item.get("base"), sig.sha256):
                    self._versions(space_id).record(wf, "conflito", sig)
                else:
                    repo.save(wf, sig.model_dump_json(indent=1))
                    self._versions(space_id).record(wf, "manual", sig)
            except OSError, InvalidInputError:
                continue  # ainda preso: fica para a próxima volta
            local.drop_pending(wid)
            sent.append(wid)
        return sent

    def adopt_conflict_copies(self, space_id: str) -> int:
        """Cópias de conflito da sincronização viram versões do fluxo e saem da pasta (RF-4762)."""
        try:
            _, repo, _ = self._require(space_id, "editor")
        except InvalidInputError:
            return 0
        adopted = 0
        for path, wf in repo.conflict_copies():
            sig = self._signature_of(repo.copy_signature(path))
            if sig is not None and (sig.fluxo != wf.id or sig.sha256 != content_sha(wf)):
                sig = None  # assinatura de outro conteúdo: a cópia entra sem autor
            try:
                self._versions(space_id).record(wf, "copia", sig)
                repo.remove_copy(path)
            except (OSError, InvalidInputError) as exc:
                log.warning("Cópia de conflito não adotada: %s (%s)", path.name, exc)
                continue
            adopted += 1
        return adopted

    def history(
        self, space_id: str, workflow_id: str, current: Workflow | None = None
    ) -> list[SpaceVersionInfo]:
        self._require(space_id, "leitor")
        members, _ = self.members(space_id)
        return self._versions(space_id).history(workflow_id, members, current)

    def version(self, space_id: str, workflow_id: str, version_id: str) -> Workflow:
        self._require(space_id, "leitor")
        return self._versions(space_id).get(workflow_id, version_id)

    def record_version(self, space_id: str, workflow: Workflow, origin: SpaceOrigin) -> None:
        """Antes de restaurar: o que estava aberto vira versão (spec 046), com a minha assinatura."""
        self._require(space_id, "editor")
        clean = workflow.model_copy(update={"samples": {}})
        self._record(space_id, clean, origin, sign_flow(self.identity, space_id, clean))

    # ------------------------------------------------------------------ abrir: atualizado por, confiança por diferença

    def opened(self, space_id: str, workflow: Workflow, reason: str | None) -> dict[str, Any]:
        """O que a tela mostra ao abrir (RF-4732, RF-4741): a impressão de base, quem salvou por último, se mudou desde
        a última vez que esta pessoa viu e as partes sensíveis a conferir (vazio quando não precisa)."""
        repo = SpaceRepository(self.workspaces.root(space_id))
        local = self._local(space_id)
        me = self.identity.current()
        sha = content_sha(workflow)
        sig = self._signature_of(repo.signature(workflow.id))
        author = None
        if sig:
            author = {"usuario": sig.autor, "nome": sig.nome or sig.autor, "quando": sig.quando.isoformat(),
                      "minha": sig.autor == me.usuario}  # fmt: skip
        seen = local.seen(workflow.id)
        updated = None
        if seen and seen != sha and author and not author["minha"]:
            updated = {**author, "versao_vista": self._versions(space_id).find(workflow.id, seen)}
        local.set_seen(workflow.id, sha)
        check: list[str] = []
        motive = None
        if reason is None:
            parts = sensitive_parts(workflow)
            before = local.trusted(workflow.id)
            check = (
                changed_parts(before, parts) if before is not None and author and not author["minha"] else []
            )
            if check:
                who = author["nome"] if author else "Outra pessoa"
                n = len(check)
                what = "uma parte sensível" if n == 1 else f"{n} partes sensíveis"
                motive = f"{who} mudou {what} desde a última vez que você conferiu."
            else:
                local.set_trusted(workflow.id, parts)
        return {"sha256": sha, "autor": author, "atualizado": updated, "conferir": check, "motivo": motive}

    def accept_sensitive(self, space_id: str, workflow_id: str) -> None:
        """A pessoa conferiu e confiou: as partes sensíveis da versão do espaço passam a ser a referência."""
        try:
            workflow = SpaceRepository(self.workspaces.root(space_id)).get(workflow_id)
        except InvalidInputError, NotFoundError:
            return
        self._local(space_id).set_trusted(workflow_id, sensitive_parts(workflow))

    def latest(self, space_id: str, workflow_id: str) -> dict[str, Any] | None:
        """A versão de trabalho de agora, para o Recarregar (RF-4733)."""
        repo = SpaceRepository(self.workspaces.root(space_id))
        current = self._current_sha(repo, workflow_id)
        if current is None:
            return None
        sig = self._signature_of(repo.signature(workflow_id))
        me = self.identity.current()
        return {
            "sha256": current,
            "nome": (sig.nome or sig.autor) if sig else "Outra pessoa",
            "quando": sig.quando.isoformat() if sig else None,
            "minha": bool(sig and sig.autor == me.usuario and sig.sha256 == current),
        }

    def move_from_library(self, space_id: str, workflow_id: str) -> Workflow:
        """Leva um fluxo de Meus fluxos para o espaço: grava lá primeiro e só então tira da biblioteca."""
        _, repo, _ = self._require(space_id, "editor")
        if repo.exists(workflow_id):
            raise InvalidInputError(
                "Já existe um fluxo com o mesmo identificador no espaço: use Salvar no espaço como cópia."
            )
        saved: Workflow = self.save(space_id, self.library.get(workflow_id))["fluxo"]
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
