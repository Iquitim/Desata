"""Lojas embrulhadas para executar um fluxo do espaço (spec 048, RF-4803, RF-4804, RF-4807).

Num fluxo do espaço, a definição da equipe (que confere) vale sobre a deste computador com o mesmo identificador; fora
do espaço, nada disto é usado. O segredo de uma conexão ou API da equipe é de cada pessoa: fica no cofre deste
computador, numa chave própria do espaço, e nunca na pasta.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from prodata.connectors.api_model import SavedApi
from prodata.connectors.api_store import ApiStore
from prodata.connectors.models import Connection
from prodata.connectors.queries import QueryStore, SavedQuery
from prodata.connectors.secrets import SecretStore
from prodata.connectors.store import ConnectionStore
from prodata.domain.constants import Constant
from prodata.errors import ProdataError
from prodata.services.constants import ConstantStore
from prodata.team.definitions import AnyDefinition, TeamDefinitions
from prodata.team.signing import Members


class NeedsSecretError(ProdataError):
    """Falta o segredo desta pessoa para uma conexão ou API da equipe (RF-4804)."""

    code = "needs_secret"


def secret_key(space_id: str, kind: str, key: str, slot: str = "") -> str:
    return f"equipe:{space_id}:{kind}:{key}" + (f":{slot}" if slot else "")


class SpaceDefinitions:
    """As definições do espaço que conferem, lidas uma vez por execução (a pasta pode ser lenta)."""

    def __init__(self, definitions: TeamDefinitions, members: Members | None) -> None:
        self.definitions = definitions
        self.members = members
        self._cache: dict[tuple[str, str], AnyDefinition | None] = {}

    @property
    def space_id(self) -> str:
        return self.definitions.space_id

    def get(self, kind: str, key: str) -> AnyDefinition | None:
        if (kind, key) not in self._cache:
            try:
                self._cache[(kind, key)] = self.definitions.get(kind, key, self.members)
            except ProdataError:
                self._cache[(kind, key)] = None
        return self._cache[(kind, key)]

    def all(self, kind: str) -> list[AnyDefinition]:
        return [d for d in (self.get(kind, k) for k in self.definitions.keys(kind)) if d is not None]


class OverlayConnections:
    def __init__(self, local: ConnectionStore, team: SpaceDefinitions, secrets: SecretStore) -> None:
        self.local, self.team, self.secrets = local, team, secrets

    def _team(self, connection_id: str) -> Connection | None:
        found = self.team.get("conexoes", connection_id)
        return found if isinstance(found, Connection) else None

    def get(self, connection_id: str) -> Connection:
        return self._team(connection_id) or self.local.get(connection_id)

    def password(self, connection_id: str) -> str:
        conn = self._team(connection_id)
        if conn is None:
            return self.local.password(connection_id)
        value = self.secrets.get(secret_key(self.team.space_id, "conexoes", connection_id))
        if not value and conn.kind != "odbc":
            where = f"servidor {conn.host}, usuário {conn.user}" if conn.host else f"usuário {conn.user}"
            raise NeedsSecretError(
                f"Falta a sua senha para a conexão {conn.name} da equipe ({where}). Abra o fluxo no programa e "
                "digite a senha: ela fica só no cofre deste computador."
            )
        return value or ""

    def __getattr__(self, name: str) -> Any:  # o resto (salvar, excluir) é da loja deste computador
        return getattr(self.local, name)


class OverlayQueries:
    def __init__(self, local: QueryStore, team: SpaceDefinitions) -> None:
        self.local, self.team = local, team

    def get(self, query_id: str) -> SavedQuery:
        found = self.team.get("consultas", query_id)
        return found if isinstance(found, SavedQuery) else self.local.get(query_id)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.local, name)


class OverlayApis:
    def __init__(self, local: ApiStore, team: SpaceDefinitions, secrets: SecretStore) -> None:
        self.local, self.team, self.secrets = local, team, secrets

    def _team(self, api_id: str) -> SavedApi | None:
        found = self.team.get("apis", api_id)
        return found if isinstance(found, SavedApi) else None

    def get(self, api_id: str) -> SavedApi:
        return self._team(api_id) or self.local.get(api_id)

    def secret_reader(self, api_id: str, typed: dict[str, str] | None = None) -> Callable[[str], str | None]:
        api = self._team(api_id)
        if api is None:
            return self.local.secret_reader(api_id, typed)
        space = self.team.space_id

        def read(slot: str) -> str | None:
            if typed and typed.get(slot):
                return typed[slot]
            value = self.secrets.get(secret_key(space, "apis", api_id, slot))
            if not value and slot in api.secret_slots():
                raise NeedsSecretError(
                    f"Falta o seu segredo ({slot}) para a API {api.name} da equipe. Abra o fluxo no programa e "
                    "digite: ele fica só no cofre deste computador."
                )
            return value

        return read

    def __getattr__(self, name: str) -> Any:
        return getattr(self.local, name)


class OverlayConstants:
    def __init__(self, local: ConstantStore | None, team: SpaceDefinitions) -> None:
        self.local, self.team = local, team

    def all(self) -> dict[str, Constant]:
        out = dict(self.local.all()) if self.local else {}
        out.update({c.name: c for c in self.team.all("constantes") if isinstance(c, Constant)})
        return out

    def __getattr__(self, name: str) -> Any:
        return getattr(self.local, name)


def missing_secrets(team: SpaceDefinitions, secrets: SecretStore, connections: list[str],
                    apis: list[str]) -> list[dict[str, Any]]:  # fmt: skip
    """As conexões e APIs da equipe que o fluxo usa e para as quais falta o segredo desta pessoa (a tela pede antes
    de executar)."""
    out: list[dict[str, Any]] = []
    for cid in dict.fromkeys(connections):
        conn = team.get("conexoes", cid)
        needs = isinstance(conn, Connection) and conn.kind != "odbc"
        if (
            needs
            and isinstance(conn, Connection)
            and not secrets.get(secret_key(team.space_id, "conexoes", cid))
        ):
            out.append({"tipo": "conexoes", "id": cid, "nome": conn.name, "servidor": conn.host,
                        "usuario": conn.user, "campos": ["senha"]})  # fmt: skip
    for aid in dict.fromkeys(apis):
        api = team.get("apis", aid)
        if isinstance(api, SavedApi):
            lacking = [
                s for s in api.secret_slots() if not secrets.get(secret_key(team.space_id, "apis", aid, s))
            ]
            if lacking:
                out.append({"tipo": "apis", "id": aid, "nome": api.name, "servidor": api.url, "usuario": "",
                            "campos": lacking})  # fmt: skip
    return out
