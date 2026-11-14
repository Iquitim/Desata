"""Spike 037, S07/S08: alinhamento da camada de palavras e fluxo de marcar → campo → origem, no Chrome.

    uv run --with playwright --with pillow python specs/037-leitor-visual-pdf/spike/teste_navegador.py <pasta-de-prints>

Precisa do protótipo rodando em http://127.0.0.1:8737 (prototipo.py).

Alinhamento: para cada palavra visível, mede a fração de pixels escuros dentro da caixa desenhada pela tela. Caixa fora
do texto ≈ 0. Roda em zoom 50/100/200% × escala de tela 1/1,5/2, na página normal e na girada.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

from PIL import Image
from playwright.sync_api import Page, sync_playwright

URL = "http://127.0.0.1:8737/"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("prints-spike")
OUT.mkdir(parents=True, exist_ok=True)


def wait_ready(page: Page, zoom: float) -> None:
    page.wait_for_function("() => window.__px && window.__px.info && document.querySelector('.px-w')")
    # imagem na escala certa para zoom × escala de tela, já carregada
    page.wait_for_function(
        """(z) => [...document.querySelectorAll('.px-page img')].slice(0, 1).every(img => {
            const pg = window.__px.info.pages[0];
            const want = Math.min(4, Math.ceil(((img.parentElement.clientWidth * devicePixelRatio) / pg.w) * 4) / 4);
            return img.complete && img.naturalWidth > 0 && img.dataset.src && img.dataset.src.endsWith('escala=' + want);
        })""",
        arg=zoom,
        timeout=15000,
    )


def alignment(page: Page) -> tuple[int, int, list[str]]:
    rects = page.evaluate(
        """() => {
            const vh = innerHeight, vw = document.querySelector('#viewer').getBoundingClientRect();
            return [...document.querySelectorAll('.px-page[data-page="0"] .px-w')].map(el => {
                const r = el.getBoundingClientRect();
                return {t: window.__px.info.words[+el.dataset.i].t, x: r.left, y: r.top, w: r.width, h: r.height};
            }).filter(r => r.x >= vw.left && r.y >= vw.top && r.x + r.w <= vw.right && r.y + r.h <= vh);
        }"""
    )
    shot = Image.open(io.BytesIO(page.screenshot())).convert("L")
    dpr = page.evaluate("devicePixelRatio")
    miss = []
    for r in rects:
        box = (int(r["x"] * dpr), int(r["y"] * dpr), int((r["x"] + r["w"]) * dpr), int((r["y"] + r["h"]) * dpr))
        crop = shot.crop((box[0], box[1], max(box[2], box[0] + 1), max(box[3], box[1] + 1)))
        data = crop.tobytes()  # fundo da página é branco (255): qualquer pixel de letra, mesmo cinza-claro, conta
        if sum(1 for v in data if v < 200) / max(1, len(data)) < 0.03:
            miss.append(r["t"])
    return len(rects), len(miss), miss[:5]


def test_alignment(p: object) -> list[dict]:
    rows = []
    browser = p.chromium.launch(channel="chrome", headless=True)  # type: ignore[attr-defined]
    for doc in ("outubro", "girado", "rotacao_interna"):
        for dpr in (1, 1.5, 2):
            ctx = browser.new_context(viewport={"width": 1500, "height": 950}, device_scale_factor=dpr)
            page = ctx.new_page()
            for zoom in (0.5, 1, 2):
                page.goto(f"{URL}?doc={doc}&zoom={zoom}")
                wait_ready(page, zoom)
                page.add_style_tag(content=".px-w{background:none!important}")
                total, miss, sample = alignment(page)
                rows.append({"doc": doc, "escala_tela": dpr, "zoom": zoom, "palavras": total, "fora": miss, "ex": sample})
                if zoom == 2 and dpr == 1.5:
                    page.add_style_tag(content=".px-w{outline:1px solid rgb(220 0 90 / .8)}")
                    page.screenshot(path=OUT / f"alinhamento_{doc}_z{zoom}_dpr{dpr}.png")
            ctx.close()
    browser.close()
    return rows


def word_index(page: Page, text: str, nth: int = 0) -> int:
    return page.evaluate(
        "([t, n]) => window.__px.info.words.map((w, i) => [w, i]).filter(([w]) => w.t === t)[n][1]", [text, nth]
    )


def click_word(page: Page, text: str, nth: int = 0, **kw: object) -> None:
    i = word_index(page, text, nth)
    page.locator(f'.px-w[data-i="{i}"]').click(**kw)  # type: ignore[arg-type]


def test_flow(p: object) -> dict:
    out: dict = {}
    browser = p.chromium.launch(channel="chrome", headless=True)  # type: ignore[attr-defined]
    ctx = browser.new_context(viewport={"width": 1600, "height": 1000}, device_scale_factor=2)
    page = ctx.new_page()
    page.goto(URL + "?doc=outubro")
    wait_ready(page, 1)
    page.screenshot(path=OUT / "01_inicio.png")

    # 1. clique no valor: a barra mostra o valor convertido e como encontrar
    click_word(page, "834.086,00")
    page.wait_for_selector(".px-action small:not(:empty)")
    page.wait_for_function("() => !document.querySelector('.px-action small').textContent.includes('lendo')")
    out["barra"] = page.inner_text(".px-action")
    page.screenshot(path=OUT / "02_selecao.png")

    # 2. Enter cria o campo; o valor aparece no painel
    page.keyboard.press("Enter")
    page.wait_for_selector('[data-field="total_liquido"] .px-value')
    page.wait_for_timeout(700)
    out["campo"] = page.inner_text('[data-field="total_liquido"]')
    page.screenshot(path=OUT / "03_campo_criado.png")

    # 3. teclado: setas até a competência, Enter
    click_word(page, "Competência:")
    page.keyboard.press("ArrowRight")
    page.wait_for_function("() => !document.querySelector('.px-action small').textContent.includes('lendo')")
    out["teclado_sel"] = page.evaluate("() => [...window.__px.sel].map(i => window.__px.info.words[i].t)")
    page.keyboard.press("Enter")
    page.wait_for_selector('[data-field="competencia"] .px-value')

    # 4. arrastar sobre a tabela e teclar T
    first = page.locator(f'.px-w[data-i="{word_index(page, "Filial")}"]').bounding_box()
    last = page.locator(f'.px-w[data-i="{word_index(page, "semanas")}"]').bounding_box()
    assert first and last
    page.mouse.move(first["x"] - 12, first["y"] - 6)
    page.mouse.down()
    page.mouse.move(first["x"] + 300, first["y"] + 120, steps=6)
    page.mouse.move(last["x"] + 260, last["y"] + last["height"] + 4, steps=10)
    page.screenshot(path=OUT / "04_arrastando.png")
    page.mouse.up()
    page.wait_for_function("() => !document.querySelector('.px-action small')?.textContent.includes('lendo')")
    page.screenshot(path=OUT / "05_area_marcada.png")
    page.keyboard.press("t")
    page.wait_for_selector("[data-table] tbody tr")
    page.wait_for_timeout(700)
    out["tabela_linhas"] = page.locator("[data-table] tbody tr").count()
    out["tabela_rodape"] = page.inner_text(".px-table-foot")
    page.screenshot(path=OUT / "06_tabela.png")

    # 5. clique numa célula: a página rola até a origem e pulsa
    page.locator("[data-table] tbody tr").nth(25).locator("td").nth(3).locator("button").click()
    page.wait_for_selector(".px-mark.pulse")
    page.wait_for_timeout(500)
    out["origem_pagina"] = page.evaluate(
        "() => document.querySelector('.px-mark.pulse').closest('.px-page').dataset.page"
    )
    page.screenshot(path=OUT / "07_origem_celula.png")

    # 6. do PDF para o dado: clicar no valor marcado destaca o campo
    page.locator("#viewer").evaluate("el => el.scrollTo(0, 0)")
    click_word(page, "834.086,00")
    page.wait_for_selector(".px-field.focus")
    out["pdf_para_dado"] = page.evaluate("() => document.querySelector('.px-field.focus').dataset.field")

    # 7. impacto e documento com dois totais
    page.keyboard.press("Escape")
    out["impacto"] = page.inner_text("#impacto")
    out["docs"] = page.inner_text("#docs")
    page.get_by_role("button", name="Relatório com dois totais").click()
    page.wait_for_function("() => window.__px.doc === 'dois_totais' && document.querySelector('.px-mark')")
    page.wait_for_timeout(600)
    out["ambiguo"] = page.inner_text('[data-field="total_liquido"]')
    page.screenshot(path=OUT / "08_ambiguo.png")

    # 8. guia arrastável: mover a 1ª guia para dentro da coluna Valor gera dúvida/valor inválido na prévia
    page.get_by_role("button", name="Relatório de novembro (cabeçalho mais abaixo)").click()
    page.wait_for_function("() => window.__px.doc === 'novembro' && document.querySelector('.px-guide')")
    page.wait_for_timeout(400)
    page.screenshot(path=OUT / "09_novembro_guias.png")
    g = page.locator(".px-guide").first
    gb = g.bounding_box()
    assert gb
    page.mouse.move(gb["x"] + gb["width"] / 2, gb["y"] + 40)
    page.mouse.down()
    page.mouse.move(gb["x"] + 160, gb["y"] + 40, steps=8)
    page.wait_for_timeout(900)
    out["guia_ainda_presa"] = page.evaluate("() => document.querySelectorAll('.px-guide').length")
    page.screenshot(path=OUT / "10_guia_arrastada.png")
    out["guia_movida_celula"] = page.inner_text("[data-table] tbody tr >> nth=0")
    page.mouse.move(gb["x"] + gb["width"] / 2, gb["y"] + 40, steps=8)
    page.mouse.up()
    page.wait_for_timeout(500)
    out["guia_volta_celula"] = page.inner_text("[data-table] tbody tr >> nth=0")

    # 9. a mesma extração na página girada e no conteúdo girado dentro do PDF
    for doc, label in (("girado", "Relatório com a página girada"), ("rotacao_interna", "Relatório girado dentro do PDF")):
        page.get_by_role("button", name=label).click()
        page.wait_for_function(f"() => window.__px.doc === '{doc}' && document.querySelector('.px-guide')")
        page.wait_for_timeout(700)
        out[f"{doc}_estado"] = page.inner_text("#doc-state")
        out[f"{doc}_guias_deitadas"] = page.locator(".px-guide.across").count()
        out[f"{doc}_linhas"] = page.locator("[data-table] tbody tr").count()
        page.screenshot(path=OUT / f"10b_{doc}.png")

    # 10. escaneado: estado vazio claro
    page.get_by_role("button", name="Relatório escaneado").click()
    page.wait_for_selector(".px-empty")
    page.screenshot(path=OUT / "11_escaneado.png")

    # 11. escuro
    ctx2 = browser.new_context(viewport={"width": 1600, "height": 1000}, device_scale_factor=1, color_scheme="dark")
    dark = ctx2.new_page()
    dark.goto(URL + "?doc=outubro")
    wait_ready(dark, 1)
    click_word(dark, "834.086,00")
    dark.wait_for_function("() => !document.querySelector('.px-action small').textContent.includes('lendo')")
    dark.screenshot(path=OUT / "12_escuro.png")
    browser.close()
    return out


if __name__ == "__main__":
    with sync_playwright() as pw:
        rows = test_alignment(pw)
        for r in rows:
            print(f"alinhamento {r['doc']:8} tela {r['escala_tela']:<3} zoom {r['zoom']:<3}: {r['palavras']:3} palavras, fora do texto {r['fora']} {r['ex']}")
        print(json.dumps(test_flow(pw), ensure_ascii=False, indent=1))
