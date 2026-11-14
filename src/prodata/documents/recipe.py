"""Extração: o objeto declarativo e versionado que diz como tirar dados de um tipo de PDF (spec 037).

A fonte aponta para uma extração (``id`` e ``revisao``); a extração não sabe de arquivos. O ``digest`` resume só o que
muda o resultado (campos e tabelas, mais a versão do esquema) e entra na assinatura do cache.
"""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from prodata.documents.types import FieldType

SCHEMA_VERSION = 1
ENGINE_VERSION = 1  # muda quando o motor passa a ler diferente: o cache antigo deixa de valer


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LabelRule(_Model):
    """'À direita de "Total líquido"' ou 'abaixo de "Competência"'."""

    tipo: Literal["rotulo"] = "rotulo"
    rotulos: list[str] = Field(min_length=1)  # variações aceitas: "Total líquido", "Valor líquido"
    direcao: Literal["direita", "abaixo"] = "direita"
    distancia: float = Field(default=0.3, gt=0, le=1)  # até onde procurar o valor, em fração da página

    @field_validator("rotulos")
    @classmethod
    def _no_blank(cls, value: list[str]) -> list[str]:
        cleaned = [" ".join(v.split()) for v in value if v.strip()]
        if not cleaned:
            raise ValueError("informe ao menos um rótulo")
        return cleaned


class SectionRule(LabelRule):
    """O mesmo, mas só dentro do bloco que começa num título ('dentro da seção "Resumo"')."""

    tipo: Literal["secao"] = "secao"  # type: ignore[assignment]
    inicio: list[str] = Field(min_length=1)
    fim: list[str] = Field(default_factory=list)


class PositionRule(_Model):
    """Área fixa na página. Frágil: qualquer mudança de layout erra o lugar (RF-3722)."""

    tipo: Literal["posicao"] = "posicao"
    pagina: int = Field(ge=0)
    area: tuple[float, float, float, float]

    @field_validator("area")
    @classmethod
    def _inside_page(cls, value: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
        x0, y0, x1, y1 = value
        if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
            raise ValueError("área fora da página")
        return value


Rule = Annotated[LabelRule | SectionRule | PositionRule, Field(discriminator="tipo")]


class FieldSpec(_Model):
    nome: str = Field(min_length=1, max_length=80)
    tipo: FieldType = "texto"
    obrigatorio: bool = False
    regra: Rule


class Column(_Model):
    nome: str = Field(min_length=1, max_length=80)
    tipo: FieldType = "texto"


class TableSpec(_Model):
    """Tabela: começa no cabeçalho, corta as colunas pelas guias e termina num texto ou num espaço grande."""

    nome: str = Field(min_length=1, max_length=80)
    cabecalho: list[str] = Field(min_length=1)  # textos que identificam a linha de cabeçalho, na ordem
    colunas: list[Column] = Field(min_length=1)
    guias: list[float] = Field(
        default_factory=list
    )  # cortes verticais, em fração da largura; len = colunas - 1
    limites: tuple[float, float] = (0.0, 1.0)  # faixa horizontal da tabela
    coluna_inicio: str | None = None  # "nova linha começa quando esta coluna tem valor"
    excluir: list[str] = Field(default_factory=list)  # linhas que começam com estes textos (subtotal, rodapé)
    fim: list[str] = Field(default_factory=list)  # texto que encerra a tabela ("Total geral")
    continua: bool = True  # segue nas páginas seguintes

    @model_validator(mode="after")
    def _consistent(self) -> TableSpec:
        if len(self.guias) != len(self.colunas) - 1:
            raise ValueError("o número de guias deve ser o número de colunas menos um")
        if self.guias != sorted(self.guias) or any(
            not self.limites[0] < g < self.limites[1] for g in self.guias
        ):
            raise ValueError("as guias precisam estar em ordem e dentro da tabela")
        names = [c.nome for c in self.colunas]
        if len(set(names)) != len(names):
            raise ValueError("colunas com o mesmo nome")
        if self.coluna_inicio is not None and self.coluna_inicio not in names:
            raise ValueError("a coluna que inicia linha não existe")
        return self


class Recipe(_Model):
    schema_version: Literal[1] = 1
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    revisao: int = Field(default=1, ge=1)
    nome: str = Field(min_length=1, max_length=120)
    campos: list[FieldSpec] = Field(default_factory=list)
    tabelas: list[TableSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_names(self) -> Recipe:
        names = [f.nome for f in self.campos] + [t.nome for t in self.tabelas]
        if len(set(names)) != len(names):
            raise ValueError("campos e tabelas precisam de nomes diferentes")
        return self

    def digest(self) -> str:
        """Resumo do que muda o resultado. Nome e revisão ficam de fora: renomear não refaz a leitura."""
        payload = self.model_dump(mode="json", include={"schema_version", "campos", "tabelas"})
        payload["motor"] = ENGINE_VERSION
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
