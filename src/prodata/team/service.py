"""Serviço da equipe: junta os espaços configurados, a identidade e os fluxos de cada espaço (spec 047).

Sem nenhum espaço configurado, nada aqui toca a rede nem o cofre: a identidade só é gerada quando a pessoa cria ou
entra num espaço (constituição, princípio VIII; RF-4702).
"""

from __future__ import annotations

from prodata.domain.workflow import Workflow
from prodata.errors import InvalidInputError
from prodata.services.workflows import WorkflowRepository
from prodata.team.identity import Identity, IdentityStore
from prodata.team.repository import SpaceFlow, SpaceRepository
from prodata.team.workspaces import Space, Workspaces

READABLE = ("ok", "somente_leitura")


class TeamService:
    def __init__(self, workspaces: Workspaces, identity: IdentityStore, library: WorkflowRepository) -> None:
        self.workspaces = workspaces
        self.identity = identity
        self.library = library

    def overview(self) -> dict[str, object]:
        """O que a tela precisa saber. Sem espaço: só ``configurado: false`` (nenhuma chave gerada)."""
        if not self.workspaces.configured():
            return {"configurado": False, "espacos": []}
        me = self.identity.current()
        return {
            "configurado": True,
            "identidade": {"usuario": me.usuario, "nome": me.nome, "tem_nome": self.identity.has_name()},
            "espacos": [s.model_dump() for s in self.workspaces.spaces()],
        }

    def me(self) -> Identity:
        return self.identity.current()

    def _space(self, space_id: str, *, write: bool = False) -> tuple[Space, SpaceRepository]:
        space = self.workspaces.get(space_id)
        if space.estado not in READABLE:
            raise InvalidInputError(space.motivo or "O espaço não está disponível agora.")
        if write and space.estado != "ok":
            raise InvalidInputError(space.motivo or "O espaço está só para leitura.")
        return space, SpaceRepository(self.workspaces.root(space_id))

    def flows(self, space_id: str) -> list[SpaceFlow]:
        return self._space(space_id)[1].flows()

    def get(self, space_id: str, workflow_id: str) -> Workflow:
        return self._space(space_id)[1].get(workflow_id)

    def save(self, space_id: str, workflow: Workflow) -> Workflow:
        return self._space(space_id, write=True)[1].save(workflow)

    def move_from_library(self, space_id: str, workflow_id: str) -> Workflow:
        """Leva um fluxo de Meus fluxos para o espaço: grava lá primeiro e só então tira da biblioteca."""
        _, repo = self._space(space_id, write=True)
        if repo.exists(workflow_id):
            raise InvalidInputError(
                "Já existe um fluxo com o mesmo identificador no espaço: use Salvar no espaço como cópia."
            )
        saved = repo.save(self.library.get(workflow_id))
        self.library.delete(workflow_id)
        return saved

    def copy_to_library(self, space_id: str, workflow_id: str, new_id: str) -> Workflow:
        """Faz uma cópia do fluxo do espaço em Meus fluxos, com outro id (a do espaço continua lá)."""
        workflow = self._space(space_id)[1].get(workflow_id)
        copy = workflow.model_copy(update={"id": new_id, "name": f"{workflow.name} (cópia)"})
        return self.library.save(copy)
