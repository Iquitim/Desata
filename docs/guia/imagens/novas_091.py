"""Capturas da 0.9.1 (spec 042): Salvar automático, Join com a saída U, Union, prévia no Designer e Dashboard."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def _frame(pg: Any, node: str, zoom: float = 0.9) -> None:
    pg.evaluate(
        """([id, z]) => import('/static/js/canvas_state.js').then(async (CS) => {
          const V = await import('/static/js/canvas.js'); CS.view.zoom = z; V.revealNode(id); })""",
        [node, zoom],
    )
    pg.wait_for_timeout(500)


def _run_to(pg: Any, node: str) -> None:
    pg.evaluate("() => { window.__old = window.__S.store.execution; }")
    pg.evaluate("id => import('/static/js/canvas_state.js').then((CS) => CS.state.handlers.runTo(id))", node)
    pg.wait_for_function("() => window.__S.store.execution !== window.__old && !window.__S.store.running", timeout=180000)
    pg.wait_for_timeout(700)


def _clean(pg: Any) -> None:
    pg.evaluate("() => document.querySelectorAll('.trust-host, .toast, .canvas-hint, .bi-hover').forEach((e) => e.remove())")


def _explainer(pg: Any, node: str, name: str, shot: Callable[..., None]) -> None:
    pg.evaluate("id => window.__S.select(id)", node)
    pg.locator("#leftPanel .tab[data-tab=config]").click()
    pg.wait_for_selector("#leftPanel details.explainer[open] .x-table", timeout=20000)
    pg.wait_for_timeout(600)
    box = pg.locator("#leftPanel details.explainer").first
    box.scroll_into_view_if_needed()
    _clean(pg)
    # Até as tabelas: a legenda do esquema repete o que o guia já explica (e o print fica mais baixo na página).
    full = box.bounding_box()
    caption = box.locator(".x-caption").first.bounding_box()
    bottom = caption["y"] - 2 if caption else full["y"] + full["height"]
    shot(pg, name, clip={"x": full["x"], "y": full["y"], "width": full["width"], "height": bottom - full["y"]})


def _layout(pg: Any, code: str, arg: Any = None) -> None:
    pg.evaluate(f"a => import('/static/js/dash_state.js').then((D) => D.commitLayout((d) => {{ {code} }}))", arg)
    pg.wait_for_timeout(500)


def part_091(pg: Any, shot: Callable[..., None]) -> None:
    _clean(pg)
    # Salvar automático: a seta aberta, com o selo no botão. O exemplo nunca salva sozinho; para o print, o fluxo
    # passa por um já salvo da pessoa (só na memória da página).
    pg.evaluate("""async () => { const S = window.__S; window.__wid = S.store.workflow.id; S.store.workflow.id = 'pipeline_da_equipe';
      S.markSaved(); const F = await import('/static/js/save_flow.js'); F.setAutosave(true); }""")
    pg.locator("#topActions .save-arrow").click()
    pg.wait_for_selector(".menu")
    pg.wait_for_timeout(300)
    bar = pg.locator("header").first.bounding_box()
    menu = pg.locator(".menu").first.bounding_box()
    split = pg.locator("#topActions .save-split").bounding_box()
    left = min(menu["x"], split["x"]) - 16
    right = max(menu["x"] + menu["width"], split["x"] + split["width"]) + 16
    shot(pg, "salvar-auto", clip={"x": left, "y": bar["y"], "width": right - left, "height": menu["y"] + menu["height"] - bar["y"] + 12})
    pg.keyboard.press("Escape")
    pg.evaluate("""async () => { const F = await import('/static/js/save_flow.js'); F.setAutosave(false);
      window.__S.store.workflow.id = window.__wid; window.__S.markSaved(); }""")
    # Join com a saída U (L + J)
    pg.evaluate("() => window.__A.updateConfig('n_join', ['stack'], 'LJ')")
    _run_to(pg, "n_join")
    _explainer(pg, "n_join", "join-u", shot)
    pg.evaluate("() => window.__A.updateConfig('n_join', ['stack'], 'none')")
    # Union de duas tabelas com colunas diferentes, num canto vazio do canvas
    pg.evaluate(
        """() => { const S = window.__S, A = window.__A;
          const a = A.addNode('io.input_data', 200, 4200, { dataset: 'clientes_enterprise.csv' });
          const b = A.addNode('io.input_data', 200, 4400, { dataset: 'transacoes_vendas.csv' });
          const u = A.addNode('transform.union', 520, 4300, { source_column: 'origem' });
          S.mutate((wf) => { wf.edges.push({ id: 'x91u1', source: a.id, sourceHandle: 'out', target: u.id, targetHandle: 'in1' },
            { id: 'x91u2', source: b.id, sourceHandle: 'out', target: u.id, targetHandle: 'in2' }); }, { structural: true });
          window.__X91 = [a.id, b.id, u.id]; }"""
    )
    union = pg.evaluate("() => window.__X91[2]")
    _run_to(pg, union)
    _explainer(pg, union, "union-explicacao", shot)
    pg.evaluate(
        "() => window.__S.mutate((wf) => { const ids = new Set(window.__X91); wf.nodes = wf.nodes.filter((n) => !ids.has(n.id));"
        " wf.edges = wf.edges.filter((e) => !ids.has(e.source) && !ids.has(e.target)); }, { structural: true })"
    )
    # Prévia do gráfico ao passar o mouse na caixa de BI (executada de novo: o Join mudou e voltou)
    _run_to(pg, "n_chart_uf")
    pg.evaluate("() => window.__S.select(null)")
    _frame(pg, "n_chart_uf", 0.9)
    _clean(pg)
    node = pg.locator(".node[data-id='n_chart_uf']")
    node.hover()
    pg.wait_for_selector(".bi-hover .chart", timeout=5000)
    pg.wait_for_timeout(300)
    nb = node.bounding_box()
    cb = pg.locator(".bi-hover").bounding_box()
    top = min(nb["y"], cb["y"]) - 16
    shot(pg, "previa-designer", clip={"x": nb["x"] - 24, "y": top, "width": cb["x"] + cb["width"] - nb["x"] + 48,
                                       "height": max(nb["y"] + nb["height"], cb["y"] + cb["height"]) - top + 16})
    pg.mouse.move(5, 500)
    # Dashboard: aba Cores com as paletas, rótulos e eixos, imagem de fundo. O gráfico ganha a linha de referência pela média.
    pg.evaluate("() => window.__A.updateConfig('n_chart_uf', ['ref_line'], 'mean')")
    _run_to(pg, "n_chart_uf")
    pg.locator('#viewSwitch .segment[data-view="dashboard"]').click()
    pg.wait_for_timeout(1200)
    pg.locator("button", has_text="Editar layout").first.click()
    pg.wait_for_timeout(700)
    pg.locator(".dash-item[data-id='d_n_chart_uf']").click(position={"x": 40, "y": 14})
    pg.wait_for_timeout(500)
    pg.locator(".dash-panel .format-tab", has_text="Cores").click()
    pg.wait_for_timeout(300)
    pg.locator(".dash-panel .palette-opt", has_text="Okabe-Ito").click()
    pg.wait_for_timeout(600)
    panel = pg.locator(".dash-panel")
    pb = panel.bounding_box()
    grid = pg.locator(".dash-panel .palette-grid").bounding_box()
    shot(pg, "formato-cores", clip={"x": pb["x"], "y": pb["y"], "width": pb["width"], "height": grid["y"] + grid["height"] - pb["y"] + 14})
    pg.locator(".dash-panel .palette-status button").click()  # volta à do dashboard
    # Aba Texto, no jeito da faixa do Office: título em negrito e uma cor, com a prévia
    pg.locator(".dash-panel .format-tab", has_text="Texto").click()
    pg.wait_for_timeout(300)
    pg.locator(".dash-panel .rb [aria-label='Escolher a cor']").click()
    pg.locator(".dash-panel .rb .rb-swatch").nth(7).click()
    pg.wait_for_timeout(400)
    tabs = pg.locator(".dash-panel .format-tabs").bounding_box()
    help_ = pg.locator(".dash-panel .tx-tab .field-help").bounding_box()
    panel = pg.locator(".dash-panel").bounding_box()
    shot(pg, "aba-texto", clip={"x": panel["x"], "y": tabs["y"] - 8, "width": panel["width"], "height": help_["y"] - tabs["y"] + 4})
    pg.locator(".dash-panel .rb [aria-label='Escolher a cor']").click()
    pg.locator(".dash-panel .rb .rb-theme").click()
    pg.locator(".dash-panel .format-tab", has_text="Cores").click()
    pg.wait_for_timeout(300)
    _layout(pg, "const it = d.items.find((i) => i.id === 'd_n_chart_uf'); it.format = { ...it.format, data_labels: 'all', grid_style: 'dotted' };")
    pg.locator("button", has_text="Concluir").first.click()
    pg.wait_for_timeout(800)
    card = pg.locator(".dash-item[data-id='d_n_chart_uf'] .chart-card").first
    card.scroll_into_view_if_needed()
    _clean(pg)
    shot(card, "rotulos-eixos")
    _layout(pg, "const it = d.items.find((i) => i.id === 'd_n_chart_uf'); const f = { ...it.format }; delete f.data_labels; delete f.grid_style; it.format = f;")
    pg.evaluate("() => window.__A.updateConfig('n_chart_uf', ['ref_line'], 'none')")
    # Imagem de fundo: um degradê leve feito no próprio navegador, com 35% de opacidade
    uri = pg.evaluate(
        """() => { const c = document.createElement('canvas'); c.width = 1600; c.height = 900; const g = c.getContext('2d');
          const grad = g.createLinearGradient(0, 0, 1600, 900); grad.addColorStop(0, '#0e7490'); grad.addColorStop(0.55, '#a5f3fc'); grad.addColorStop(1, '#f0abfc');
          g.fillStyle = grad; g.fillRect(0, 0, 1600, 900);
          g.globalAlpha = 0.18; g.fillStyle = '#ffffff'; for (let i = 0; i < 9; i++) { g.beginPath(); g.arc(200 + i * 170, 700 - (i % 3) * 180, 120 + (i % 4) * 30, 0, Math.PI * 2); g.fill(); }
          return c.toDataURL('image/png'); }"""
    )
    _layout(pg, "d.page = { ...d.page, image: a, image_fit: 'cover', image_opacity: 70 };", uri)
    pg.locator("button", has_text="Editar layout").first.click()
    pg.wait_for_timeout(700)
    pg.evaluate("() => import('/static/js/dash_state.js').then((D) => { D.ui.selected.clear(); D.els.panelKey = null; })")
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(600)
    # O painel rola por dentro: leva a parte da imagem para a vista e recorta a página ao lado dela.
    pg.evaluate("() => { const p = document.querySelector('.dash-panel'); p.scrollTop = p.scrollHeight; }")
    pg.wait_for_timeout(400)
    _clean(pg)
    view = pg.viewport_size
    pb = pg.locator(".dash-panel").bounding_box()
    shot(pg, "fundo-pagina", clip={"x": view["width"] * 0.40, "y": pb["y"], "width": pb["x"] + pb["width"] - view["width"] * 0.40 + 8,
                                    "height": min(pb["height"], view["height"] - pb["y"] - 4)})
    pg.locator("button", has_text="Concluir").first.click()
    _layout(pg, "d.page = { ...d.page, image: '' };")
    pg.locator('#viewSwitch .segment[data-view="designer"]').click()
    pg.wait_for_timeout(500)
