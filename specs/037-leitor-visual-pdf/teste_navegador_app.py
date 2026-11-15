"""Teste de navegador do leitor de PDF no app de verdade (spec 037, T13).

    uv run --with playwright python specs/037-leitor-visual-pdf/teste_navegador_app.py [pasta-de-prints]

Sobe o servidor numa pasta de dados temporária, usa os PDFs de exemplo do pacote e percorre: criar a fonte, marcar
um campo pelo mouse e outro pelo teclado (CA-01, CA-07), criar a tabela com guias (CA-04, CA-05), ambiguidade
(CA-03), corrigir só neste documento (CA-16), usar como rótulo e desfazer (CA-10), a guia com prévia ao vivo, a volta
à origem (CA-06), o teste nos outros arquivos (CA-09), a política "parar" no Designer (CA-12) e erros de console.
Sai com código 1 se alguma conferência falhar.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
PORT = 8798
URL = f"http://127.0.0.1:{PORT}/"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else None
failures: list[str] = []
errors: list[str] = []


def check(ok: bool, what: str) -> None:
    print(("OK   " if ok else "FALHA") + f" {what}")
    if not ok:
        failures.append(what)


def shot(page: Page, name: str) -> None:
    if OUT:
        OUT.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=OUT / f"{name}.png")


def word(page: Page, doc: str, text: str, last: bool = False) -> int:
    index: int = page.evaluate(
        """async ([doc, t, last]) => {
          const id = (await (await fetch('/api/pdfs')).json()).find((p) => p.name.startsWith('Relatórios de exemplo')).id;
          const info = await (await fetch(`/api/pdfs/${id}/docs/words?doc=${encodeURIComponent(doc)}`)).json();
          const hit = (w) => w.t === t && w.p === 0;
          return last ? info.words.findLastIndex(hit) : info.words.findIndex(hit);
        }""",
        [doc, text, last],
    )
    return index


def settled(page: Page) -> None:
    page.wait_for_function("() => !document.querySelector('.pv-action small')?.textContent.includes('lendo')", timeout=10000)


def run(page: Page) -> None:
    page.goto(URL)
    page.wait_for_selector(".node", timeout=60000)
    page.wait_for_timeout(1500)
    page.locator('#viewSwitch .segment[data-view="data"]').click()
    page.get_by_role("button", name="Adicionar").first.click()
    page.get_by_text("PDF (extrair campos e tabelas)").click()
    page.get_by_role("button", name="Usar os PDFs de exemplo").click()
    page.wait_for_selector(".pv-w", timeout=30000)
    doc = "relatorio_2026-10.pdf"
    page.locator(".pe-doc-select").select_option(doc)
    page.wait_for_timeout(1500)

    # CA-01: marcar o valor, ver o valor convertido na barra e criar o campo
    page.locator(f'.pv-w[data-i="{word(page, doc, "834.086,00")}"]').click()
    settled(page)
    check("Moeda (R$)" in page.inner_text(".pv-action") and "Total líquido" in page.inner_text(".pv-action"), "barra mostra tipo e rótulo")
    page.keyboard.press("Enter")
    page.wait_for_selector('[data-cell="total_liquido"]', timeout=10000)
    page.wait_for_timeout(800)
    check(page.inner_text('[data-cell="total_liquido"]').replace("\xa0", " ").strip() == "R$ 834.086,00", "campo nasce com o valor convertido")
    page.locator('[data-field="total_liquido"] .pe-check input').set_checked(True)
    page.wait_for_timeout(800)

    # CA-07: pelo teclado
    page.locator(f'.pv-w[data-i="{word(page, doc, "Competência:")}"]').click()
    page.keyboard.press("ArrowRight")
    settled(page)
    page.keyboard.press("Enter")
    page.wait_for_selector('[data-cell="competencia"]', timeout=10000)
    check("out/2026" in page.inner_text('[data-cell="competencia"]'), "campo criado pelo teclado")

    # CA-04/05: tabela por arraste, com a célula de duas linhas unida e a página 2 sem o cabeçalho repetido
    a = page.locator(f'.pv-w[data-i="{word(page, doc, "Filial")}"]').bounding_box()
    z = page.locator(f'.pv-w[data-i="{word(page, doc, "semanas", last=True)}"]').bounding_box()
    assert a and z
    page.mouse.move(a["x"] - 12, a["y"] - 6)
    page.mouse.down()
    page.mouse.move(z["x"] + 300, z["y"] + z["height"] + 4, steps=10)
    page.mouse.up()
    page.wait_for_timeout(600)
    page.keyboard.press("t")
    page.wait_for_selector(".pe-out[data-table] tbody tr", timeout=15000)
    page.wait_for_timeout(1500)
    rows = page.locator(".pe-out[data-table] tbody tr")
    check(rows.count() == 32, f"tabela com 32 linhas ({rows.count()})")
    check("e o ajuste da nota de crédito" in rows.nth(1).inner_text(), "célula de duas linhas unida")
    shot(page, "01_tabela")

    # CA-06: célula → origem na página 2
    rows.nth(25).locator("td").nth(3).locator("button").click()
    page.wait_for_selector(".pv-mark.pulse", timeout=5000)
    check(page.evaluate("() => document.querySelector('.pv-mark.pulse').closest('.pv-page').dataset.page") == "1", "célula leva à página 2")

    # guia com prévia ao vivo
    page.locator(".pv-scroll").evaluate("el => el.scrollTo(0, 0)")
    page.wait_for_timeout(800)
    g = page.locator(".pv-guide").first.bounding_box()
    assert g
    page.mouse.move(g["x"] + g["width"] / 2, g["y"] + 60)
    page.mouse.down()
    page.mouse.move(g["x"] + 140, g["y"] + 60, steps=8)
    page.wait_for_timeout(1000)
    live = rows.first.inner_text()
    page.mouse.move(g["x"] + g["width"] / 2, g["y"] + 60, steps=8)
    page.mouse.up()
    page.wait_for_timeout(1500)
    check("São Paulo R$" in live and "São Paulo R$" not in rows.first.inner_text(), "guia muda a prévia ao vivo e volta")

    # CA-03 e CA-16: o relatório com dois totais fica Ambíguo; corrigir só nele
    page.locator(".pe-doc-select").select_option("relatorio_2026-12.pdf")
    page.wait_for_timeout(1800)
    check("Ambíguo" in page.inner_text('[data-field="total_liquido"]'), "dois totais ficam Ambíguo")
    check(page.locator('.pv-mark.show[data-owner="total_liquido"]').count() == 2, "os dois candidatos aparecem na página")
    page.locator('[data-field="total_liquido"] .pe-fix summary').click()
    page.locator('[data-field="total_liquido"] .pe-fix input').fill("149.500,00")
    page.locator('[data-field="total_liquido"] .pe-fix').get_by_role("button", name="Corrigir").click()
    page.wait_for_timeout(1800)
    check("Corrigido só neste documento" in page.inner_text('[data-field="total_liquido"]'), "correção registrada")

    # CA-10: usar como rótulo, ver o impacto e desfazer
    page.locator('[data-field="competencia"] button[aria-pressed]').click()
    page.locator(f'.pv-w[data-i="{word(page, "relatorio_2026-12.pdf", "Emitido")}"]').dblclick()
    page.wait_for_timeout(600)
    page.keyboard.press("r")
    page.wait_for_timeout(2500)
    check("abaixo de “Emitido”" in page.inner_text('[data-field="competencia"]') or "Emitido" in page.inner_text('[data-field="competencia"]'), "rótulo trocado")
    banner = page.locator(".pe-change")
    check(banner.count() == 1 and "passa" in banner.inner_text(), "quadro mostra o impacto da mudança")
    page.keyboard.press("Control+z")
    page.wait_for_timeout(1500)
    check("Competência" in page.inner_text('[data-field="competencia"]'), "desfazer volta a regra")

    # CA-09: teste nos outros arquivos
    page.get_by_role("tab", name="Testar em outros arquivos").click()
    page.wait_for_timeout(1200)
    check("3 de 3 documentos avaliados" in page.inner_text(".pe-result"), "N de M avaliados")

    # CA-12: política parar no Designer, sem o documento corrigido a correção some
    page.evaluate("""async () => { const id = (await (await fetch('/api/pdfs')).json()).find((p) => p.name.startsWith('Relatórios de exemplo')).id;
        for (const c of await (await fetch(`/api/pdfs/${id}/corrections`)).json()) await fetch(`/api/pdfs/${id}/corrections/${c.id}`, {method: 'DELETE'}); }""")
    page.get_by_role("tab", name="Visão geral").click()
    page.wait_for_selector(".pdf-doc-row", timeout=30000)
    page.get_by_role("button", name="Adicionar ao fluxo").first.click()
    page.wait_for_timeout(1200)
    page.get_by_role("button", name="Executar até aqui").first.click()
    page.wait_for_timeout(6000)
    left = page.inner_text("#leftPanel")
    check("parar a execução" in left and "relatorio_2026-12.pdf" in left, "política parar com mensagem clara")
    shot(page, "02_parar")

    # RF-3705: extrações salvas
    page.locator('#viewSwitch .segment[data-view="data"]').click()
    page.wait_for_timeout(600)
    page.get_by_role("tab", name="Extração").click()
    page.wait_for_selector(".pv-w", timeout=20000)
    page.locator(".pe-recipe-btn").click()
    page.get_by_role("menuitem", name="Copiar como extração nova").click()
    page.wait_for_timeout(2000)
    page.locator(".pe-recipe-btn").click()
    check("(cópia)" in page.inner_text(".menu"), "a fonte usa a cópia")
    page.get_by_role("menuitem", name="Extrações salvas…").click()
    page.wait_for_selector(".pdf-recipe", timeout=5000)
    page.wait_for_timeout(500)
    check(page.locator(".pdf-recipe").count() == 3, "três extrações salvas (com a do exemplo da Receita)")
    shot(page, "03_extracoes")
    original = page.locator(".pdf-recipe:not(.current)").filter(has_text="Relatórios de exemplo (PDF)")
    original.get_by_role("button", name="Excluir").click()
    page.locator("dialog[open]").last.get_by_role("button", name="Excluir").click()
    page.wait_for_timeout(1500)
    check(page.locator(".pdf-recipe").count() == 2, "extração sem uso excluída")
    page.locator("dialog[open]").get_by_role("button", name="Fechar").last.click()
    # fonte nova, já com a extração salva
    page.get_by_role("button", name="Adicionar").first.click()
    page.get_by_text("PDF (extrair campos e tabelas)").click()
    page.locator('[data-way="link"]').click()
    page.locator(".fd-editor input.mono").first.fill(str(ROOT / "src/prodata/samples/pdf/relatorio_2026-11.pdf"))
    page.locator(".fd-editor input.mono").first.press("Tab")
    page.locator('select[aria-label="Extração"]').select_option(label=page.locator('select[aria-label="Extração"] option', has_text="(cópia)").first.inner_text())
    page.get_by_role("button", name="Preparar extração").click()
    page.wait_for_selector('[data-cell="total_liquido"]', timeout=20000)
    page.wait_for_timeout(1000)
    check("195.880,75" in page.inner_text('[data-cell="total_liquido"]'), "fonte nova já nasce com os campos da extração salva")
    shot(page, "04_reaproveitada")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="desata-pdf-") as folder:
        env = {**os.environ, "PRODATA_PORT": str(PORT), "PRODATA_STORAGE_DIR": str(Path(folder) / "dados"), "PRODATA_SECRETS_BACKEND": "memory",
               "PRODATA_CORS_ORIGINS": f'["http://127.0.0.1:{PORT}"]'}
        uv = shutil.which("uv") or "uv"
        server = subprocess.Popen([uv, "run", "prodata"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # noqa: S603
        try:
            for _ in range(90):
                try:
                    urllib.request.urlopen(URL + "api/health")  # noqa: S310
                    break
                except OSError:
                    time.sleep(1)
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1.5)
                page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
                page.on("pageerror", lambda e: errors.append(str(e)))
                try:
                    run(page)
                except Exception:
                    shot(page, "erro")
                    raise
                finally:
                    browser.close()
        finally:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(server.pid)], capture_output=True, check=False)  # noqa: S603, S607
            else:
                server.terminate()
    check(not errors, f"sem erro de console ({errors[:3]})")
    print(f"\n{len(failures)} falha(s)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
