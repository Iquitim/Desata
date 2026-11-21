"""Capturas da 0.9.3 (spec 046): versões anteriores, fio inteligente, fonte que muda de formato e erro com conserto.

Tudo roda no servidor de prints, com a pasta de dados temporária: as fontes e os fluxos criados aqui somem no fim.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from novas_091 import _clean

UPLOAD = """async ([name, text]) => { const fd = new FormData(); fd.append('file', new File([text], name, { type: 'text/csv' }));
  fd.append('overwrite', 'true'); const r = await fetch('/api/datasets', { method: 'POST', body: fd }); return (await r.json()).name; }"""


def _new_flow(pg: Any) -> None:
    pg.get_by_role("button", name="Arquivo").first.click()
    pg.wait_for_timeout(200)
    pg.get_by_role("menuitem", name="Novo fluxo").click()
    pg.wait_for_timeout(700)
    pg.evaluate("async () => { window.__CV = await import('/static/js/canvas.js'); }")


def _run(pg: Any) -> None:
    pg.evaluate("() => { window.__old = window.__S.store.execution; }")
    pg.evaluate("() => import('/static/js/canvas_state.js').then((CS) => CS.state.handlers.run())")
    pg.wait_for_function("() => window.__S.store.execution !== window.__old && !window.__S.store.running", timeout=120000)
    pg.wait_for_timeout(700)


def _region(pg: Any, ids: list[str], pad: int = 40, extra_bottom: int = 0) -> dict[str, float]:
    boxes = [pg.locator(f".node[data-id='{i}']").bounding_box() for i in ids]
    x1 = min(b["x"] for b in boxes) - pad
    y1 = min(b["y"] for b in boxes) - pad
    x2 = max(b["x"] + b["width"] for b in boxes) + pad
    y2 = max(b["y"] + b["height"] for b in boxes) + pad + extra_bottom
    return {"x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1}


def _port(pg: Any, node_id: str, side: str) -> tuple[float, float]:
    b = pg.locator(f".port.{side}[data-node='{node_id}']").first.bounding_box()
    return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2


def part_093(pg: Any, shot: Callable[..., None]) -> None:
    _wire(pg, shot)
    _source_change(pg, shot)
    _versions(pg, shot)


# ---------------------------------------------------------------- fio inteligente (RF-4641..4646)


def _wire(pg: Any, shot: Callable[..., None]) -> None:
    _new_flow(pg)
    ids = pg.evaluate("""() => { const A = window.__A;
      const t = A.addNode('io.text_input', 0, 60, { table: { columns: ['uf', 'valor'], rows: [['SP', '10'], ['RJ', '20']] } }).id;
      const s = A.addNode('prep.select', 330, -60).id, j = A.addNode('transform.join', 330, 180).id;
      return { t, s, j }; }""")
    pg.evaluate("() => window.__CV.fitView()")
    pg.wait_for_timeout(500)
    _clean(pg)
    area = _region(pg, list(ids.values()), pad=50, extra_bottom=20)
    ox, oy = _port(pg, ids["t"], "out")
    sx, sy = _port(pg, ids["s"], "in")
    pg.mouse.move(ox, oy)
    pg.mouse.down()
    pg.mouse.move(ox + 30, oy, steps=3)
    pg.mouse.move(sx - 16, sy + 10, steps=8)
    pg.wait_for_timeout(200)
    shot(pg, "fio-ima", clip=area)
    pg.mouse.up()
    pg.wait_for_timeout(300)
    jb = pg.locator(f".node[data-id='{ids['j']}'] .node-card").bounding_box()
    pg.mouse.move(ox, oy)
    pg.mouse.down()
    pg.mouse.move(ox + 30, oy, steps=3)
    pg.mouse.move(jb["x"] + jb["width"] / 2, jb["y"] + jb["height"] / 2, steps=8)
    pg.mouse.up()
    pg.wait_for_selector(".port-chooser")
    pg.wait_for_timeout(250)
    chooser = pg.locator(".port-chooser").bounding_box()
    shot(pg, "fio-seletor", clip={"x": area["x"], "y": area["y"], "width": max(area["width"], chooser["x"] + chooser["width"] + 12 - area["x"]),
                                  "height": max(area["height"], chooser["y"] + chooser["height"] + 12 - area["y"])})
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(200)
    pg.mouse.move(ox, oy)
    pg.mouse.down()
    pg.mouse.move(ox + 30, oy, steps=3)
    tb = pg.locator(f".node[data-id='{ids['t']}']").bounding_box()
    pg.mouse.move(tb["x"] + 40, tb["y"] + tb["height"] + 170, steps=8)
    pg.mouse.up()
    pg.wait_for_selector(".quick-add .quick-group")
    pg.wait_for_timeout(250)
    shot(pg.locator(".quick-add"), "fio-sugeridas")
    pg.keyboard.press("Escape")


# ---------------------------------------------------------------- fonte que muda de formato (RF-4601..4610) e erro (RF-4622)


def _source_change(pg: Any, shot: Callable[..., None]) -> None:
    ds = pg.evaluate(UPLOAD, ["vendas_mes.csv", "uf;valor\nSP;120,50\nRJ;89,90\nMG;15,00\n"])
    _new_flow(pg)
    ids = pg.evaluate("""(ds) => { const A = window.__A;
      const i = A.addNode('io.input_data', 0, 60, { dataset: ds }).id;
      const f = A.addNode('prep.formula', 330, -60, { formulas: [{ name: 'com_imposto', expression: '[valor] * 1.1', type: 'Float64' }] }).id;
      const s = A.addNode('transform.summarize', 330, 180, { group_by: ['uf'], aggregations: [{ column: 'valor', agg: 'sum' }] }).id;
      A.connect(i, 'out', f, 'in'); A.connect(i, 'out', s, 'in'); return { i, f, s }; }""", ds)
    pg.evaluate("() => window.__CV.fitView()")
    _run(pg)
    pg.evaluate(UPLOAD, ["vendas_mes.csv", "uf;valor_total;desconto\nSP;120,50;1\nRJ;89,90;2\nMG;15,00;0\n"])
    _run(pg)
    # o erro da fórmula, com a parecida e o conserto (antes de mexer na entrada)
    pg.evaluate("id => window.__S.select(id)", ids["f"])
    pg.locator("#leftPanel .tab[data-tab=config]").click()
    pg.wait_for_selector("#leftPanel .banner-error")
    pg.wait_for_timeout(300)
    _clean(pg)
    shot(pg.locator("#leftPanel .banner-error").first, "erro-coluna")
    pg.evaluate("id => window.__S.select(id)", ids["i"])
    notice = pg.locator("#leftPanel .drift-notice")
    notice.wait_for()
    pg.wait_for_timeout(300)
    _clean(pg)
    shot(notice, "fonte-mudou")
    pg.locator("#leftPanel .drift-explainer summary").click()
    pg.wait_for_timeout(250)
    shot(pg.locator("#leftPanel .drift-explainer"), "fonte-explicacao")
    notice.locator("button", has_text="Mostrar").click()
    pg.wait_for_timeout(500)
    _clean(pg)
    shot(pg, "fonte-caixas", clip=_region(pg, list(ids.values()), pad=40, extra_bottom=16))
    notice.locator("button", has_text="Trocar por").click()
    dlg = pg.locator("dialog[open]")
    dlg.wait_for()
    pg.wait_for_timeout(300)
    shot(dlg, "trocar-coluna")
    dlg.locator("button", has_text="Cancelar").click()


# ---------------------------------------------------------------- versões anteriores (RF-4631..4634)


def _versions(pg: Any, shot: Callable[..., None]) -> None:
    _new_flow(pg)
    pg.evaluate("""() => { const A = window.__A;
      const t = A.addNode('io.text_input', 0, 60, { table: { columns: ['uf', 'valor'], rows: [['SP', '10']] } }).id;
      const f = A.addNode('prep.filter', 280, 60).id, s = A.addNode('prep.sort', 560, 60).id, o = A.addNode('io.output_data', 840, 60).id;
      A.connect(t, 'out', f, 'in'); A.connect(f, 'T', s, 'in'); A.connect(s, 'out', o, 'in'); }""")
    pg.locator("#topActions .save-main").click()
    dlg = pg.locator("dialog[open]")
    dlg.wait_for()
    dlg.locator("input").fill("Fechamento mensal")
    dlg.locator("input").press("Enter")
    pg.wait_for_function("() => !window.__S.isDirty()", timeout=10000)
    pg.evaluate("""() => { const S = window.__S; const ids = S.store.workflow.nodes.slice(1, 3).map((n) => n.id);
      S.mutate((wf) => { wf.nodes = wf.nodes.filter((n) => !ids.includes(n.id)); wf.edges = wf.edges.filter((e) => !ids.includes(e.source) && !ids.includes(e.target)); }, { structural: true }); }""")
    pg.keyboard.press("Control+s")
    pg.wait_for_function("() => !window.__S.isDirty()", timeout=10000)
    pg.get_by_role("button", name="Arquivo").first.click()
    pg.wait_for_timeout(200)
    pg.get_by_role("menuitem", name="Versões anteriores…").click()
    dlg = pg.locator("dialog[open]")
    dlg.locator(".ver-item").nth(1).wait_for()
    dlg.locator(".ver-item").nth(1).click()
    dlg.locator(".ver-preview .ver-node").first.wait_for()
    pg.wait_for_timeout(400)
    _clean(pg)
    shot(dlg, "versoes")
    pg.keyboard.press("Escape")
