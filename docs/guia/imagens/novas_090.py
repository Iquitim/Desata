"""Capturas da 0.9 (spec 041): recolher, fios, seletor de fontes, tabela, dica no Dashboard, tempo nas caixas e laço."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def _frame(pg: Any, node: str, zoom: float = 0.9) -> None:
    """Põe a caixa no meio do canvas, no zoom pedido."""
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
    pg.evaluate("() => document.querySelectorAll('.trust-host, .toast, .canvas-hint').forEach((e) => e.remove())")


def part_090(pg: Any, shot: Callable[..., None]) -> None:
    _clean(pg)
    canvas = pg.locator("#canvas")
    # Blocos de fórmula recolhidos, com nome
    pg.evaluate(
        """() => { const n = window.__S.store.workflow.nodes.find((x) => x.id === 'n_formula');
          const f = n.config.formulas.map((x, i) => ({ ...x, _ui: { collapsed: true, name: ['Receita anual', 'Faixa do cliente'][i] } }));
          window.__A.updateConfig('n_formula', ['formulas'], f); window.__S.select('n_formula'); }"""
    )
    pg.locator("#leftPanel .tab[data-tab=config], #leftPanel [role=tab]:has-text('Configurar')").first.click()
    pg.wait_for_selector("#leftPanel .list-item.collapsed")
    pg.wait_for_timeout(400)
    shot(pg.locator("#leftPanel .list-field").first, "lista-formulas")
    # Etapas recolhidas: o fluxo em blocos
    pg.evaluate("() => import('/static/js/canvas_collapse.js').then((C) => C.setContainersCollapsed(['c_prep', 'c_vendas', 'c_ml', 'c_api'], true))")
    pg.evaluate("() => { window.__S.select(null); return import('/static/js/canvas.js').then((V) => V.fitView()); }")
    pg.wait_for_timeout(700)
    shot(canvas, "recolher-etapas")
    pg.evaluate("() => import('/static/js/canvas_collapse.js').then((C) => C.setContainersCollapsed(C.allContainers(), false))")
    # Fios organizados
    _frame(pg, "n_join", 0.8)
    shot(canvas, "fios-organizados")
    # Tempo nas caixas: a mais lenta em destaque
    pg.evaluate("() => import('/static/js/node_timing.js').then((T) => T.setTiming(true))")
    _frame(pg, "n_pdf_campos", 0.8)
    shot(canvas, "tempo-caixas")
    pg.evaluate("() => import('/static/js/node_timing.js').then((T) => T.setTiming(false))")
    # Seletor de fontes
    pg.evaluate("() => window.__S.select('n_clientes')")
    pg.wait_for_selector("#leftPanel .src-card")
    pg.wait_for_timeout(300)
    shot(pg.locator("#leftPanel .src-card").first, "fonte-cartao")
    pg.locator("#leftPanel .src-card button", has_text="Trocar").click()
    pg.wait_for_selector("dialog[open] .sp-preview .data-table", timeout=30000)
    pg.wait_for_timeout(400)
    shot(pg.locator("dialog[open]"), "seletor-fontes")
    pg.keyboard.press("Escape")
    # Tabela: célula em destaque, sem o resumo das colunas
    pg.evaluate("() => { window.__S.select('n_clientes'); window.__S.inspect('n_clientes'); }")
    pg.wait_for_selector("#results td[data-ci]")
    pg.evaluate("() => import('/static/js/table_tools.js').then((T) => T.setSummary(false))")
    pg.locator("#results tbody tr").nth(3).locator("td[data-ci]").nth(1).click()
    pg.wait_for_timeout(500)
    box = pg.locator("#results").bounding_box()
    shot(pg, "celula-destaque", clip={"x": box["x"], "y": box["y"], "width": box["width"], "height": min(box["height"], 330)})
    pg.keyboard.press("Escape")
    pg.evaluate("() => import('/static/js/table_tools.js').then((T) => T.setSummary(true))")
    # Laço do exemplo: a moldura, o Início e uma volta escolhida
    _frame(pg, "n_laco_top", 0.72)
    shot(canvas, "laco")
    pg.evaluate("() => window.__S.select('n_laco_ini')")
    pg.wait_for_timeout(400)
    shot(pg.locator("#leftPanel .form").first, "laco-inicio")
    pg.evaluate("() => { window.__S.select('n_laco_top'); window.__S.inspect('n_laco_top'); }")
    pg.wait_for_selector("#results .results-turn input", timeout=15000)
    pg.locator("#results .results-turn input").fill("2")
    pg.locator("#results .results-turn input").press("Enter")
    pg.wait_for_timeout(900)
    box = pg.locator("#results").bounding_box()
    shot(pg, "laco-volta", clip={"x": box["x"], "y": box["y"], "width": box["width"], "height": min(box["height"], 230)})
    # Dica editável no Dashboard: colunas extras e texto com campos
    pg.evaluate("() => window.__A.updateConfig('n_chart_uf', ['tip_columns'], ['total_mrr', 'clientes'])")
    _run_to(pg, "n_chart_uf")
    pg.locator('#viewSwitch .segment[data-view="dashboard"]').click()
    pg.wait_for_timeout(1200)
    pg.locator("button", has_text="Editar layout").first.click()
    pg.wait_for_timeout(700)
    pg.locator(".dash-item[data-id='d_n_chart_uf']").click(position={"x": 40, "y": 14})
    pg.wait_for_timeout(600)
    pg.locator(".dash-panel .format-tab", has_text="Dica").click()  # o painel Formato é em abas (spec 042)
    pg.wait_for_timeout(300)
    dica = pg.locator(".dash-panel .format-tab-body")
    dica.locator("textarea").fill("{uf}: {valor}% da meta · {clientes} clientes")
    dica.locator("textarea").blur()
    pg.wait_for_timeout(700)
    pg.locator(".dash-panel .format-tabs").scroll_into_view_if_needed()
    pg.wait_for_timeout(300)
    tabs = pg.locator(".dash-panel .format-tabs").bounding_box()
    body = dica.bounding_box()
    panel = pg.locator(".dash-panel").bounding_box()
    bottom = min(body["y"] + body["height"], panel["y"] + panel["height"])
    shot(pg, "dica-painel", clip={"x": panel["x"], "y": tabs["y"] - 10, "width": panel["width"], "height": bottom - tabs["y"] + 18})
    pg.locator("button", has_text="Concluir").first.click()
    pg.wait_for_timeout(700)
    card = pg.locator(".dash-item[data-id='d_n_chart_uf'] .chart-card").first
    card.scroll_into_view_if_needed()
    card.locator("[data-tip]").nth(1).hover()
    pg.wait_for_timeout(400)
    shot(card, "dica-grafico")
    pg.locator('#viewSwitch .segment[data-view="designer"]').click()
    pg.wait_for_timeout(500)
    # Aviso de desenho do laço: uma caixa de dentro ligada para fora, antes de executar
    pg.evaluate(
        "() => window.__S.mutate((wf) => { wf.edges.push({ id: 'x90_vaza', source: 'n_laco_ordem', sourceHandle: 'out', "
        "target: 'n_chart_seg', targetHandle: 'in' }); }, { structural: true })"
    )
    _frame(pg, "n_laco_ordem", 1.0)
    _clean(pg)
    node = pg.locator(".node[data-id='n_laco_ordem']")
    node.locator(".node-loop-problem").hover()
    pg.wait_for_timeout(300)
    box = node.bounding_box()
    shot(pg, "laco-aviso", clip={"x": box["x"] - 40, "y": box["y"] - 30, "width": box["width"] + 80, "height": box["height"] + 56})
    pg.evaluate("() => window.__S.mutate((wf) => { wf.edges = wf.edges.filter((e) => e.id !== 'x90_vaza'); }, { structural: true })")
    # Parar: enquanto o fluxo roda, o Executar do topo vira Parar
    pg.evaluate(
        """() => { const S = window.__S, A = window.__A;
          const n = A.addNode('flow.loop_start', 200, 3600); const end = S.store.workflow.nodes.find((x) => x.config?.start === n.id);
          const f = A.addNode('prep.formula', 480, 3600, { formulas: [{ target: 'new', column: 'x', type: 'Auto', expression: '[#volta]' }] });
          S.mutate((wf) => { const st = wf.nodes.find((x) => x.id === n.id); st.config = { ...st.config, mode: 'range', start: '1', end: '4000', max_iterations: 5000 };
            wf.edges = wf.edges.filter((e) => !(e.source === n.id && e.target === end.id));
            wf.edges.push({ id: 'x90p1', source: 'n_clientes', sourceHandle: 'out', target: n.id, targetHandle: 'in' },
              { id: 'x90p2', source: n.id, sourceHandle: 'out', target: f.id, targetHandle: 'in' },
              { id: 'x90p3', source: f.id, sourceHandle: 'out', target: end.id, targetHandle: 'in' }); }, { structural: true });
          window.__X90 = [n.id, end.id, f.id]; }"""
    )
    pg.evaluate("() => { import('/static/js/canvas_state.js').then((CS) => { CS.state.handlers.runTo(window.__X90[1]); }); }")
    pg.wait_for_selector("#topActions .btn.stop", timeout=60000)
    pg.wait_for_timeout(1200)
    bar = pg.locator("header").first.bounding_box()
    acts = pg.locator("#topActions").bounding_box()
    shot(pg, "parar-topo", clip={"x": acts["x"] - 16, "y": bar["y"], "width": acts["width"] + 32, "height": bar["height"]})
    pg.locator("#topActions .btn.stop").click()
    pg.wait_for_function("() => !window.__S.store.running", timeout=60000)
    pg.evaluate("() => window.__S.mutate((wf) => { const ids = new Set(window.__X90); wf.nodes = wf.nodes.filter((n) => !ids.has(n.id)); wf.edges = wf.edges.filter((e) => !ids.has(e.source) && !ids.has(e.target)); }, { structural: true })")
    pg.wait_for_timeout(500)
