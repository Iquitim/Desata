"""Executar um fluxo do espaço com as definições da equipe (spec 048, RF-4803).

Todos os caminhos de execução de um fluxo do espaço (Executar, executar até aqui, salvar com as constantes, o
agendamento) passam por ``runner_for``: com o espaço, as lojas da equipe; sem ele, o executor de sempre.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from prodata.connectors.api_model import source_api_id
from prodata.connectors.queries import source_query_id
from prodata.domain.workflow import Workflow
from prodata.errors import ProdataError
from prodata.team.overlay import OverlayApis, OverlayConnections, OverlayConstants, OverlayQueries

if TYPE_CHECKING:
    from prodata.api.deps import Services
    from prodata.engine.runner import WorkflowRunner


def runner_for(services: Services, space_id: str | None) -> WorkflowRunner:
    if not space_id:
        return services.runner
    defs = services.team.space_definitions(space_id)
    if defs is None:  # não sou membro ou a pasta não está acessível: só o que é deste computador
        return services.runner
    secrets = services.team.identity.secrets
    return services.runner.with_stores(
        connections=OverlayConnections(services.connections, defs, secrets),
        queries=OverlayQueries(services.queries, defs),
        apis=OverlayApis(services.apis, defs, secrets),
        constants=OverlayConstants(services.constants, defs),
        # Feriados da equipe (spec 049, RF-4948): num fluxo do espaço, Feriados e Dias úteis usam a lista da equipe.
        team_holidays=_team_holidays(defs),
    )


def _team_holidays(defs: Any) -> Any:
    item = defs.get("feriados", "calendario")
    return item.edits() if item is not None else None


def used_sources(workflow: Workflow, queries: Any) -> tuple[list[str], list[str]]:
    """As conexões e APIs que o fluxo usa (pelas consultas, pelo Database Input e pelo API Loop)."""
    connections: list[str] = []
    apis: list[str] = []
    for node in workflow.nodes:
        cfg = node.config
        if node.type == "io.input_data":
            dataset = str(cfg.get("dataset") or "")
            if (query_id := source_query_id(dataset)) is not None:
                try:
                    connections.append(queries.get(query_id).connection)
                except ProdataError:
                    continue
            elif (api_id := source_api_id(dataset)) is not None:
                apis.append(api_id)
        elif node.type == "io.api_loop" and cfg.get("source"):
            apis.append(str(cfg["source"]))
        elif node.type == "io.database_input" and cfg.get("connection"):
            connections.append(str(cfg["connection"]))
    return connections, apis


class SpaceView:
    """Os serviços como um fluxo do espaço os vê: as lojas da equipe no lugar das deste computador; o resto igual."""

    def __init__(self, services: Services, runner: WorkflowRunner) -> None:
        self._services = services
        self.runner = runner
        self.queries = runner.queries
        self.apis = runner.apis
        self.connections = runner.connections
        self.constants = runner.constants

    def __getattr__(self, name: str) -> Any:
        return getattr(self._services, name)
