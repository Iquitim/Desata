"""Caixa Dados públicos (spec 049, RF-4915, RF-4925, RF-4938, RF-4948, RF-4971, RF-4973).

O fluxo guarda só a referência da fonte e as escolhas (sem endereço montado, sem dados, sem segredo: não há segredo).
A execução lê pelo mesmo caminho da prévia do catálogo (``catalog.sources.read``), guarda a leitura bem-sucedida na
pasta de dados deste computador e, com o órgão fora do ar, usa a última leitura guardada da mesma consulta, com o
aviso e a data (a menos que a pessoa peça "Exigir dados atuais"). O período relativo é resolvido na hora da execução:
no agendamento, sempre o mais recente.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from prodata.catalog import cache, hosts, sources
from prodata.catalog.http import CatalogClient, CatalogError
from prodata.catalog.model import SourceNotFoundError
from prodata.catalog.readers.files import FormatChangedError
from prodata.forms import ui
from prodata.nodes.base import NodeContext, NodeOutput, Port, ToolConfig, tool

FORMAT_CHANGED = "O órgão mudou o arquivo"


class PublicSelection(BaseModel):
    """A fonte escolhida no catálogo, como vai no arquivo do fluxo."""

    id: str = Field("", max_length=300)
    nome: str = Field("", max_length=300)
    orgao: str = Field("", max_length=300)
    citacao: str = Field("", max_length=500)
    licenca: str = Field("", max_length=500)
    escolhas: dict[str, Any] = Field(default_factory=dict)


class PublicDataConfig(ToolConfig):
    fonte: PublicSelection = Field(
        default_factory=PublicSelection,
        title="Fonte",
        description="Escolha no catálogo Dados públicos do Brasil: a fonte e as escolhas (período, variável, local...).",
        json_schema_extra=ui(widget="public_source"),
    )
    exigir_atual: bool = Field(
        False,
        title="Exigir dados atuais",
        description="Com o órgão fora do ar, a caixa falha em vez de usar a última leitura guardada.",
        json_schema_extra=ui(widget="toggle"),
    )
    limit: int = Field(0, ge=0, title="Limite de linhas", description="0 = todas as linhas.")


def _period_words(choice: dict[str, Any] | None) -> str:
    if not choice:
        return ""
    kind = choice.get("kind")
    if kind == "ultimos_anos":
        years = int(choice.get("anos") or 5)
        return "último ano" if years == 1 else f"últimos {years} anos"
    if kind == "desde":
        return f"desde {choice.get('inicio', '')}"
    if kind == "intervalo":
        return f"{choice.get('inicio', '')} a {choice.get('fim', '')}"
    return "todo o período"


def _annotation(cfg: PublicDataConfig) -> str:
    """A segunda linha da caixa: o órgão e o período (o nome da fonte já é o título da caixa)."""
    if not cfg.fonte.id:
        return "Escolha uma fonte no catálogo"
    parts = [cfg.fonte.orgao or "Dados públicos", _period_words(cfg.fonte.escolhas.get("periodo"))]
    return " · ".join(p for p in parts if p)


def _signature(ctx: NodeContext, cfg: PublicDataConfig) -> str:
    """A mesma fonte com as mesmas escolhas vale pelo dia: no dia seguinte (ou com outra escolha), lê de novo."""
    text = json.dumps(
        {"f": cfg.fonte.id, "e": cfg.fonte.escolhas, "d": date.today().isoformat()},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def _agency(source_id: str) -> str:
    try:
        service = hosts.SERVICES[sources.service_of(source_id)]
    except KeyError, SourceNotFoundError:
        return "o órgão"
    return service.short


@tool(
    type="io.public_data",
    name="Dados públicos",
    category="inout",
    icon="landmark",
    description="Lê uma fonte do catálogo Dados públicos do Brasil (Banco Central, IBGE, Ipeadata, Tesouro, portais de dados abertos, feriados), direto do órgão, sem configurar API.",
    config=PublicDataConfig,
    inputs=[],
    outputs=[Port("out", "O", "Dados")],
    annotate=_annotation,
    fingerprint=_signature,
)
def public_data(ctx: NodeContext, cfg: PublicDataConfig) -> NodeOutput:
    source_id = cfg.fonte.id
    if not source_id:
        raise ValueError("Escolha uma fonte: Configurar → Escolher no catálogo.")
    if ctx.catalog_root is None:
        raise ValueError("O catálogo de dados públicos não está disponível neste ambiente.")
    choices = cfg.fonte.escolhas
    warnings: list[str] = []
    now = datetime.now()
    try:
        with CatalogClient(timeout=120) as client:
            result = sources.read(
                client, source_id, choices, ctx.catalog_root, team_holidays=ctx.team_holidays
            )
    except FormatChangedError as exc:
        raise ValueError(
            f"{exc} Abra o Configurar e use Aceitar o novo formato depois de conferir."
        ) from None
    except SourceNotFoundError as exc:
        raise ValueError(str(exc)) from None
    except CatalogError as exc:
        if exc.kind == "recusado" or cfg.exigir_atual:
            raise ValueError(exc.message) from None
        saved = cache.load(ctx.catalog_root, source_id, choices)
        if saved is None:
            raise ValueError(
                f"{exc.message} Ainda não há leitura guardada desta consulta para usar no lugar."
            ) from None
        frame = saved.frame
        read_at = saved.read_at
        warnings.append(
            f"{_agency(source_id)} fora do ar: usando os dados lidos em {read_at:%d/%m/%Y %H:%M}. ({exc.message})"
        )
    else:
        frame = result.frame
        read_at = now
        warnings += result.warnings
        cache.save(ctx.catalog_root, source_id, choices, frame, now, result.warnings)
    extra: dict[str, Any] = {
        "source": cfg.fonte.nome or source_id,
        "source_read_at": read_at.isoformat(timespec="seconds"),
        # Para o Perfil, o dicionário e a citação no dashboard (RF-4912, RF-4963).
        "fonte_publica": {
            "id": source_id,
            "nome": cfg.fonte.nome,
            "orgao": cfg.fonte.orgao,
            "citacao": cfg.fonte.citacao,
            "licenca": cfg.fonte.licenca,
            "lido_em": read_at.isoformat(timespec="seconds"),
        },
    }
    if warnings:
        extra["warnings"] = warnings
    return NodeOutput(tables={"out": frame.head(cfg.limit) if cfg.limit else frame}, extra=extra)
