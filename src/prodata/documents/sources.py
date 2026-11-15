"""Leitor de PDF como fonte da vista Dados (spec 037, RF-3701..3704, RF-3761, RF-3762, RF-3770..3772, RF-3783).

Três cadastros, em arquivos separados ao lado da lista de arquivos vinculados:

- **fontes** (``_pdfs.json``): de onde vêm os PDFs (um arquivo, enviado ou vinculado, ou uma pasta com padrão) e qual
  extração usam;
- **extrações** (``_extracoes.json``): o objeto declarativo e versionado (``Recipe``), sem caminho nem segredo;
- **correções** (``_pdf_correcoes.json``): "corrigir só neste documento", com quem, quando, valor original e corrigido,
  presas à assinatura do conteúdo do PDF (mudou o PDF, a correção deixa de valer sozinha).

Os fluxos guardam só ``pdf:<id>/<saída>``. O PDF é lido onde está e nunca é alterado.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import unicodedata
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from prodata.documents.extract import APROVADO, FALHOU, REVISAR
from prodata.documents.recipe import Recipe
from prodata.errors import InvalidInputError

PDF_PREFIX = "pdf:"
MAIN_OUTPUT = "campos"
MAX_FILES = 500
MAX_SOURCES = 500
MAX_EXAMPLES = 20
STATE_LABELS = {APROVADO: "Aprovado", REVISAR: "Revisar", FALHOU: "Falhou"}
FIELD_LABELS = {
    "encontrado": "Encontrado",
    "ausente": "Ausente",
    "ambiguo": "Ambíguo",
    "invalido": "Inválido",
    "nao_suportado": "Não suportado",
}


def source_pdf_ref(value: str) -> tuple[str, str] | None:
    """``pdf:relatorios/campos`` → (``relatorios``, ``campos``); sem saída, a principal. Outra fonte → None."""
    if not value.startswith(PDF_PREFIX):
        return None
    rest = value[len(PDF_PREFIX) :]
    source, _, output = rest.partition("/")
    return source, output or MAIN_OUTPUT


def _slug(name: str, fallback: str) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")[:40] or fallback


def check_pattern(pattern: str) -> str:
    pattern = pattern.strip() or "*.pdf"
    if any(c in pattern for c in "/\\") or ".." in pattern:
        raise InvalidInputError("O padrão vale para o nome do arquivo: não pode ter barras nem '..'.")
    return pattern


# ------------------------------------------------------------------ modelos


class PdfSource(BaseModel):
    id: str = Field("", pattern=r"^[a-z0-9_-]{0,60}$")
    name: str = Field(min_length=1, max_length=80)
    mode: Literal["arquivo", "pasta"] = "arquivo"
    path: str = Field(min_length=1, max_length=400)  # o PDF (arquivo) ou a pasta
    pattern: str = Field("*.pdf", max_length=120)
    stored: bool = False  # cópia enviada, guardada pelo programa (some junto com a fonte)
    recipe: str = Field("", max_length=64)  # extração usada; vazia = rascunho
    policy: Literal["parar", "aprovados", "todos"] = "parar"
    examples: list[str] = Field(default_factory=list, max_length=MAX_EXAMPLES)  # só para testar (RF-3741)
    page_column: bool = False  # coluna "pagina" nas saídas de tabela (RF-3752)
    # documentos um a um (RF-3706): cópias que a pessoa somou à fonte (guardadas pelo programa) e nomes tirados dela,
    # sem apagar o arquivo de ninguém. Mudam só pelas rotas próprias, nunca pelo formulário do cadastro.
    added: list[str] = Field(default_factory=list, max_length=MAX_FILES)
    left_out: list[str] = Field(default_factory=list, max_length=MAX_FILES)

    @field_validator("name")
    @classmethod
    def _line(cls, value: str) -> str:
        return " ".join("".join(c if c.isprintable() else " " for c in value).split())

    def options_digest(self) -> str:
        raw = json.dumps(self.model_dump(mode="json", include={"policy", "page_column"}), sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:8]


class Correction(BaseModel):
    """'Corrigir só neste documento' (RF-3762): vale enquanto o conteúdo do PDF for o mesmo."""

    id: str = Field(default_factory=lambda: secrets.token_hex(4))
    source: str
    documento: str  # nome do arquivo
    assinatura: str  # conteúdo do PDF quando a correção foi feita
    campo: str
    valor: str  # o texto informado pela pessoa (convertido pelo tipo do campo)
    original: str | None = None
    estado_original: str = ""
    quem: str = ""
    quando: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PdfStatus(BaseModel):
    files: int = 0
    left_out: int = 0  # documentos tirados da fonte (RF-3706)
    missing: bool = False
    error: str = ""
    draft: bool = True
    revision: int = 0
    fields: int = 0
    tables: int = 0
    outputs: list[str] = Field(default_factory=lambda: [MAIN_OUTPUT])
    summary: dict[str, int] | None = None  # aprovado/revisar/falhou da última avaliação completa
    checked_at: datetime | None = None


class PdfEntry(PdfSource):
    status: PdfStatus = Field(default_factory=PdfStatus)


def outputs_of(recipe: Recipe | None) -> list[str]:
    tables = [f"itens_{t.nome}" for t in recipe.tabelas] if recipe else []
    return [MAIN_OUTPUT, *tables, "falhas", "origem"]
