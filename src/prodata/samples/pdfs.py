"""Leitor de PDF do exemplo (spec 037): relatórios reais da Receita Federal, com a extração pronta.

Os PDFs vão no pacote (``samples/pdf_receita``, sem alteração; fonte e licença em ``FONTE.txt``). A fonte aponta para
essa pasta e é reapontada a cada abertura, porque a versão portátil pode ser descompactada em qualquer lugar.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from prodata.documents.recipe import Recipe
from prodata.documents.sources import PdfSource
from prodata.documents.store import PdfStore

FOLDER = Path(__file__).resolve().parent / "pdf_receita"
SOURCE_ID = "arrecadacao_federal"
NAME = "Arrecadação federal (Receita Federal)"
DESCRIPTION = (
    "Análise da Arrecadação das Receitas Federais, publicada todo mês pela Receita Federal (gov.br). "
    "Reprodução autorizada com citação da fonte."
)

RECIPE: dict[str, Any] = {
    "id": SOURCE_ID,
    "nome": NAME,
    "campos": [
        {
            "nome": "competencia",
            "tipo": "mes_ano",
            "obrigatorio": True,
            "regra": {
                "tipo": "rotulo",
                "rotulos": ["ANÁLISE DA ARRECADAÇÃO DAS RECEITAS FEDERAIS"],
                "direcao": "abaixo",
            },
        },
        {
            "nome": "receita_administrada_rfb",
            "tipo": "inteiro",
            "regra": {
                "tipo": "rotulo",
                "rotulos": ["RECEITA ADMINISTRADA PELA RFB [1]"],
                "direcao": "direita",
            },
        },
    ],
    "tabelas": [
        {
            "nome": "acumulado_no_ano",
            # só o que não muda de um mês (ou de um ano) para outro: o cabeçalho de setembro mudou de formato
            "cabecalho": ["VAR.", "PARTICIPAÇÃO"],
            "colunas": [
                {"nome": "receita", "tipo": "texto"},
                {"nome": "arrecadado_ano_atual", "tipo": "inteiro"},
                {"nome": "arrecadado_ano_anterior", "tipo": "inteiro"},
                {"nome": "variacao_pct", "tipo": "decimal"},
                {"nome": "participacao_ano_atual_pct", "tipo": "decimal"},
                {"nome": "participacao_ano_anterior_pct", "tipo": "decimal"},
            ],
            "guias": [0.4638, 0.5898, 0.6946, 0.8052, 0.9021],
            "limites": [0.03, 0.97],
            "excluir": ["RECEITAS", "[A] [B]"],  # as outras linhas do cabeçalho, quando ele vem em três
            "fim": ["TOTAL GERAL"],
        }
    ],
}


def seed_example_pdfs(store: PdfStore) -> None:
    """Cria a fonte do exemplo com a extração pronta, se ainda não existe; se existe, só confere a pasta."""
    if not FOLDER.is_dir():
        return
    try:
        current = store.get(SOURCE_ID)
    except Exception:  # não cadastrada ainda
        current = None
    if current is None:
        saved = store.save(
            PdfSource(
                id=SOURCE_ID,
                name=NAME,
                mode="pasta",
                path=str(FOLDER),
                pattern="arrecadacao_*.pdf",
                policy="todos",
            )
        )
        store.save_recipe(saved.id, Recipe.model_validate(RECIPE))
        return
    refresh_example_pdfs(store)


def refresh_example_pdfs(store: PdfStore) -> None:
    """Programa reinstalado ou portátil em outra pasta: a fonte do exemplo volta a apontar para os PDFs do pacote."""
    if not FOLDER.is_dir():
        return
    for source in store.all_sources():
        if source.id == SOURCE_ID and Path(source.path) != FOLDER and Path(source.path).name == FOLDER.name:
            store.save(source.model_copy(update={"path": str(FOLDER)}), previous=source.id)
