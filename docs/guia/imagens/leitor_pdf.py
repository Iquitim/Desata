"""Capturas do leitor de PDF na vista Dados (spec 037): o editor, a tabela com guias, o teste nos outros arquivos e a
visão geral. Usado por ``gerar_imagens.py``. Usa os PDFs de exemplo que vão no pacote (Usar os PDFs de exemplo).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

SID_JS = "window.__pdfId"


def _word(pg: Any, doc: str, text: str, last: bool = False) -> int:
    index: int = pg.evaluate(
        """async ([doc, t, last]) => {
          const info = await (await fetch(`/api/pdfs/${window.__pdfId}/docs/words?doc=${encodeURIComponent(doc)}`)).json();
          const hit = (w) => w.t === t && w.p === 0;
          return last ? info.words.findLastIndex(hit) : info.words.findIndex(hit);
        }""",
        [doc, text, last],
    )
    return index


def part_pdf_reader(pg: Any, shot: Callable[..., None]) -> None:
    pg.click("#viewSwitch .segment[data-view=data]")
    pg.wait_for_timeout(600)
    pg.get_by_role("button", name="Adicionar").first.click()
    pg.get_by_text("PDF (extrair campos e tabelas)").click()
    pg.wait_for_timeout(500)
    pg.get_by_role("button", name="Usar os PDFs de exemplo").click()
    pg.wait_for_selector(".pv-w", timeout=30000)
    pg.evaluate(
        "async () => { window.__pdfId = (await (await fetch('/api/pdfs')).json()).find((p) => p.name.startsWith('Relatórios de exemplo')).id; }"
    )
    doc = "relatorio_2026-10.pdf"
    pg.locator(".pe-doc-select").select_option(doc)
    pg.wait_for_timeout(1500)
    # o total, pela prévia em cima da seleção
    pg.locator(f'.pv-w[data-i="{_word(pg, doc, "834.086,00")}"]').click()
    pg.wait_for_function(
        "() => !document.querySelector('.pv-action small')?.textContent.includes('lendo')", timeout=10000
    )
    pg.keyboard.press("Enter")
    pg.wait_for_selector('[data-field="total_liquido"]', timeout=10000)
    pg.locator('[data-field="total_liquido"] .pe-check input').set_checked(True)
    pg.wait_for_timeout(800)
    # a competência, pelo teclado
    pg.locator(f'.pv-w[data-i="{_word(pg, doc, "Competência:")}"]').click()
    pg.keyboard.press("ArrowRight")
    pg.wait_for_timeout(600)
    pg.keyboard.press("Enter")
    pg.wait_for_selector('[data-field="competencia"]', timeout=10000)
    pg.wait_for_timeout(800)
    # a tabela, arrastando do cabeçalho até o fim da página
    first = pg.locator(f'.pv-w[data-i="{_word(pg, doc, "Filial")}"]').bounding_box()
    # até a última linha da página: a tabela segue nas páginas seguintes (marcar só parte corta, RF-3735)
    last = pg.locator(f'.pv-w[data-i="{_word(pg, doc, "semanas", last=True)}"]').bounding_box()
    pg.mouse.move(first["x"] - 12, first["y"] - 6)
    pg.mouse.down()
    pg.mouse.move(last["x"] + 300, last["y"] + last["height"] + 4, steps=10)
    pg.mouse.up()
    pg.wait_for_timeout(700)
    pg.keyboard.press("t")
    pg.wait_for_selector(".pe-out[data-table] tbody tr", timeout=15000)
    pg.wait_for_timeout(3000)
    pg.evaluate("() => document.querySelectorAll('.toast').forEach((t) => t.remove())")
    # o valor do total em foco, com a etiqueta na página
    pg.locator('[data-field="total_liquido"]').hover()
    pg.wait_for_timeout(400)
    shot(pg.locator(".pe"), "pdf-editor")
    pg.mouse.move(5, 500)
    doc_pane = pg.locator(".pe-doc")
    shot(doc_pane, "pdf-tabela")
    pg.get_by_role("tab", name="Testar em outros arquivos").click()
    pg.wait_for_timeout(1500)
    top = pg.locator(".pe-result").bounding_box()
    end = pg.locator(".pe-matrix-wrap").bounding_box()
    shot(
        pg,
        "pdf-teste",
        clip={
            "x": top["x"],
            "y": top["y"],
            "width": top["width"],
            "height": end["y"] + end["height"] + 14 - top["y"],
        },
    )
    pg.get_by_role("tab", name="Visão geral").click()
    pg.wait_for_selector(".pdf-doc-row", timeout=30000)
    pg.wait_for_timeout(1200)
    shot(pg.locator(".dv-main"), "pdf-visao")
    # documentos um a um (RF-3706): um tirado da fonte aparece em "Fora da fonte"; depois volta
    docs = pg.locator(".pdf-docs .pdf-doc-item")
    first = docs.count()
    docs.last.locator("> .btn").click()
    pg.wait_for_function(
        f"() => document.querySelectorAll('.pdf-docs .pdf-doc-item').length === {first - 1}", timeout=30000
    )
    pg.wait_for_selector(".pdf-docs .pdf-counts", timeout=30000)
    pg.wait_for_timeout(800)
    pg.evaluate("() => document.querySelectorAll('.toast').forEach((t) => t.remove())")
    pg.locator(".pdf-docs .pdf-doc-item").first.hover()
    shot(pg.locator(".pdf-docs"), "pdf-documentos")
    pg.locator(".pdf-left-out button").first.click()
    pg.wait_for_function(
        f"() => document.querySelectorAll('.pdf-docs .pdf-doc-item').length === {first}", timeout=30000
    )
    pg.wait_for_timeout(800)
    pg.get_by_role("button", name="Extrações salvas…").click()
    pg.wait_for_selector(".pdf-recipe", timeout=10000)
    pg.wait_for_timeout(600)
    shot(pg.locator("dialog[open]"), "pdf-extracoes")
    pg.locator("dialog[open]").get_by_role("button", name="Fechar").last.click()
