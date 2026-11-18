"""Modelo do arquivo de workflow (``.prodata.json``)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from prodata.domain.constants import Constant, ConstantValue
from prodata.domain.dashboard import Dashboard
from prodata.domain.samples import MAX_BYTES as MAX_SAMPLE_BYTES
from prodata.domain.samples import SourceSample

ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


class Container(BaseModel):
    id: str
    title: str = ""
    description: str = ""
    color: str = "#64748b"
    opacity: float = Field(0.05, ge=0, le=0.4, description="Opacidade do fundo da caixa.")
    # Caixa desligada: a interface desativa os nós de dentro (ver spec 007, RF-712).
    disabled: bool = False
    # Recolhida (spec 041): a etapa vira um cartão. Só desenho; não muda a execução.
    collapsed: bool = False
    x: float = 0
    y: float = 0
    width: float = 300
    height: float = 200


class Node(BaseModel):
    id: str = Field(pattern=ID_PATTERN)
    type: str
    label: str = ""
    x: float = 0
    y: float = 0
    config: dict[str, Any] = Field(default_factory=dict)
    disabled: bool = False
    # Ponto de cache (spec 012): entrega o resultado congelado e dispensa as caixas anteriores.
    cache_point: bool = False
    # Renovação do ponto de cache (spec 017): além de mudanças antes dele, também todo dia ou a cada hora.
    cache_refresh: Literal["changes", "daily", "hourly"] = "changes"
    # Compacta (spec 041): só o ícone e as portas no canvas. Só desenho; não muda a execução.
    collapsed: bool = False


class Edge(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    id: str
    source: str
    source_handle: str = Field("out", alias="sourceHandle")
    target: str
    target_handle: str = Field("in", alias="targetHandle")


class Workflow(BaseModel):
    id: str = Field(pattern=ID_PATTERN)
    name: str = "Novo fluxo"
    description: str = ""
    containers: list[Container] = Field(default_factory=list)
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    # Layout do dashboard (spec 014). Ausente em fluxos antigos: a interface monta um automático.
    dashboard: Dashboard | None = None
    # Constantes do fluxo e o valor das compartilhadas que ele usa (spec 028). Ausentes em fluxos antigos.
    constants: list[Constant] = Field(default_factory=list)
    shared_constants: dict[str, ConstantValue] = Field(default_factory=dict)
    # Amostra das fontes, só em "Salvar com amostra dos dados" (spec 040). Chave: a fonte, como no Input Data.
    samples: dict[str, SourceSample] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_references(self) -> Workflow:
        ids = [n.id for n in self.nodes]
        duplicated = {i for i in ids if ids.count(i) > 1}
        if duplicated:
            raise ValueError(f"Caixas com o mesmo ID: {', '.join(sorted(duplicated))}")
        known = set(ids)
        for e in self.edges:
            if e.source not in known or e.target not in known:
                raise ValueError(f"Conexão '{e.id}' liga uma caixa que não existe.")
            if e.source == e.target:
                raise ValueError(f"Conexão '{e.id}' liga uma caixa a ela mesma.")
        names = [c.name for c in self.constants]
        if repeated := sorted({n for n in names if names.count(n) > 1}):
            raise ValueError(f"Constantes do fluxo com o mesmo nome: {', '.join(repeated)}")
        if self.dashboard:
            self.dashboard.prune(known)
        if sum(s.size() for s in self.samples.values()) > MAX_SAMPLE_BYTES:
            raise ValueError("A amostra do fluxo passa de 5 MB: tire fontes da amostra.")
        return self

    def node(self, node_id: str) -> Node:
        for n in self.nodes:
            if n.id == node_id:
                return n
        raise KeyError(node_id)
