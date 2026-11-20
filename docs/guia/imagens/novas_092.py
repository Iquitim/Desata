"""Capturas da 0.9.2 (spec 044): Rank, média móvel, Append Fields, agendador e aviso de fim de execução.

A lista de agendamentos usa dados de exemplo servidos pelo próprio teste (rota interceptada): gerar os prints nunca
cria tarefas no Agendador do Windows.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from novas_091 import _clean, _explainer, _run_to


def _add(pg: Any, code: str) -> Any:
    return pg.evaluate(f"() => {{ const S = window.__S, A = window.__A; {code} }}")


def _link(pg: Any, source: str, target: str, port: str = "in") -> None:
    pg.evaluate(
        """([s, t, p]) => window.__S.mutate((wf) => { wf.edges.push({ id: 'x92' + Math.random().toString(36).slice(2, 7),
          source: s, sourceHandle: 'out', target: t, targetHandle: p }); }, { structural: true, affects: [t] })""",
        [source, target, port],
    )


def _panel_part(pg: Any, name: str, selector: str, shot: Callable[..., None], pad: int = 8) -> None:
    """Um pedaço do Configurar, com uma folga em volta."""
    pg.locator(selector).first.scroll_into_view_if_needed()
    pg.wait_for_timeout(200)
    box = pg.locator(selector).first.bounding_box()
    panel = pg.locator("#leftPanel").bounding_box()
    shot(pg, name, clip={"x": panel["x"], "y": box["y"] - pad - 22, "width": panel["width"], "height": box["height"] + 2 * pad + 22})


def _schedules_fixture() -> dict[str, Any]:
    now = datetime.now().replace(second=0, microsecond=0)
    ontem = (now - timedelta(days=1)).replace(hour=6, minute=0)
    base = {"file_path": "", "options": {"catch_up": True, "wake": False, "on_battery": True}, "created_at": now.isoformat()}
    items = [
        {**base, "id": "1a2b3c4d", "workflow_id": "fechamento", "name": "Fechamento do mês", "frequency": "monthly", "time": "06:00",
         "weekdays": [], "month_day": 2, "every_hours": 4, "paused": False, "task": "active", "task_name": "",
         "sentence": "Todo dia 2 do mês às 06:00", "next_text": "02/12, 06:00", "next_run": "",
         "last": {"schedule_id": "1a2b3c4d", "workflow": "Fechamento do mês", "started_at": (ontem - timedelta(seconds=42)).isoformat(),
                  "finished_at": ontem.isoformat(), "status": "ok", "errors": 0, "files": 3, "message": ""}},
        {**base, "id": "2b3c4d5e", "workflow_id": "vendas_diarias", "name": "Vendas do dia", "frequency": "weekly", "time": "07:30",
         "weekdays": [0, 1, 2, 3, 4], "month_day": 1, "every_hours": 4, "paused": False, "task": "active", "task_name": "",
         "sentence": "De segunda a sexta às 07:30", "next_text": "amanhã, 07:30", "next_run": "",
         "last": {"schedule_id": "2b3c4d5e", "workflow": "Vendas do dia", "started_at": (ontem + timedelta(hours=1, minutes=30)).isoformat(),
                  "finished_at": (ontem + timedelta(hours=1, minutes=30, seconds=8)).isoformat(), "status": "failed", "errors": 1, "files": 0,
                  "message": "Conexão com o banco recusada: confira se a VPN está ligada."}},
        {**base, "id": "3c4d5e6f", "workflow_id": "estoque", "name": "Estoque por loja", "frequency": "hourly", "time": "08:00",
         "weekdays": [], "month_day": 1, "every_hours": 4, "paused": True, "task": "paused", "task_name": "",
         "sentence": "A cada 4 horas, a partir das 08:00", "next_text": None, "next_run": None, "last": None},
    ]
    return {"supported": True, "items": items}


def part_092(pg: Any, shot: Callable[..., None]) -> None:
    _clean(pg)
    # ---------------------------------------------------------------- Rank: top 3 de MRR por UF
    rid = _add(pg, "return A.addNode('prep.rank', 1400, 3900, { order_by: [{ column: 'mrr_mensal', descending: true }], group_by: ['uf'], keep_top: true, top: 3, column: 'posicao' }).id;")
    _link(pg, "n_clientes", rid)
    _run_to(pg, rid)
    pg.evaluate("id => window.__S.select(id)", rid)
    pg.locator("#leftPanel .tab[data-tab=config]").click()
    pg.wait_for_selector("#leftPanel .rk-cards")
    pg.wait_for_timeout(500)
    _clean(pg)
    _panel_part(pg, "rank-empates", "#leftPanel .rk-cards", shot)
    _explainer(pg, rid, "rank-explicacao", shot)
    # ---------------------------------------------------------------- Média móvel de 3 meses
    cols = pg.evaluate("() => (window.__S.store.execution.node_results.n_pdf_vendas_mes?.anchors?.out?.columns || []).map((c) => [c.name, c.type])")
    order = next((c for c, t in cols if "mes" in c.lower() or "Date" in t), cols[0][0])
    value = next(c for c, t in cols if ("Float" in t or "Int" in t) and c != order)
    mid = _add(pg, "return A.addNode('prep.multirow', 1700, 3900, {}).id;")
    _link(pg, "n_pdf_vendas_mes", mid)
    pg.evaluate(
        """([m, o, v]) => import('/static/js/multirow_recipes.js').then((R) => { const A = window.__A;
          A.updateConfig(m, ['recipe'], 'mavg'); A.updateConfig(m, ['base'], v); A.updateConfig(m, ['order_by'], [{ column: o, descending: false }]);
          const now = window.__S.store.workflow.nodes.find((n) => n.id === m).config;
          for (const f of ['recipe', 'base']) { const cur = window.__S.store.workflow.nodes.find((n) => n.id === m).config;
            for (const [k, x] of Object.entries(R.recipePatch(cur, f))) A.updateConfig(m, [k], x); } })""",
        [mid, order, value],
    )
    _run_to(pg, mid)
    _explainer(pg, mid, "explain-media-movel", shot)
    # ---------------------------------------------------------------- Append Fields: cenários para cada UF
    tid = _add(pg, """return A.addNode('io.text_input', 1400, 4200, { table: { columns: ['cenario', 'fator'], rows: [['Base', '1'], ['Otimista', '1,1'], ['Pessimista', '0,9']] } }).id;""")
    aid = _add(pg, "return A.addNode('transform.append_fields', 1700, 4200, {}).id;")
    _link(pg, "n_sum_uf", aid, "T")
    _link(pg, tid, aid, "S")
    _run_to(pg, tid)
    pg.evaluate("id => window.__S.select(id)", aid)
    pg.locator("#leftPanel .tab[data-tab=config]").click()
    pg.wait_for_selector("#leftPanel details.explainer[open] .x-table", timeout=20000)
    pg.wait_for_timeout(800)
    _clean(pg)
    banner = pg.locator("#leftPanel .banner", has_text="Vai sair").first
    if banner.count():
        _panel_part(pg, "append-conta", "#leftPanel .banner >> text=Vai sair", shot, pad=4)
    _explainer(pg, aid, "append-explicacao", shot)
    # ---------------------------------------------------------------- Agendar (o diálogo, sem criar a tarefa)
    pg.get_by_role("button", name="Arquivo").first.click()
    pg.wait_for_timeout(200)
    pg.get_by_text("Agendar este fluxo…", exact=True).click()
    dlg = pg.locator("dialog[open]")
    dlg.wait_for()
    pg.wait_for_timeout(800)
    _clean(pg)
    shot(dlg, "agendar")
    dlg.locator(".sch-freq .segment[data-freq='hourly']").click()
    pg.wait_for_timeout(500)
    shot(dlg.locator(".sch-layout"), "agendar-horas")
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(300)
    # ---------------------------------------------------------------- Agendamentos (lista de exemplo)
    fixture = json.dumps(_schedules_fixture())
    pg.route("**/api/schedules", lambda route: route.fulfill(status=200, content_type="application/json", body=fixture))
    pg.get_by_role("button", name="Arquivo").first.click()
    pg.wait_for_timeout(200)
    pg.get_by_text("Agendamentos…", exact=True).click()
    dlg = pg.locator("dialog[open]")
    dlg.locator(".sch-item").first.wait_for()
    pg.wait_for_timeout(400)
    _clean(pg)
    shot(dlg, "agendamentos")
    pg.keyboard.press("Escape")
    pg.unroute("**/api/schedules")
    # ---------------------------------------------------------------- aviso de falha agendada e aviso de fim
    pg.evaluate("""() => import('/static/js/run_notice.js').then((N) => N.brandNotice({ tone: 'error', title: 'Um agendamento falhou',
        flow: 'Vendas do dia · hoje, 07:30', detail: 'Conexão com o banco recusada: confira se a VPN está ligada.',
        action: { icon: 'clock', label: 'Ver agendamentos', onClick: () => {} }, sticky: true }))""")
    pg.wait_for_timeout(400)
    shot(pg.locator(".run-notice").last, "agendamento-falhou")
    pg.evaluate("() => document.querySelectorAll('.run-notice').forEach((e) => e.remove())")
    report = {"total_elapsed_ms": 5400, "node_results": {
        **{f"a{i}": {"status": "executed", "extra": {}} for i in range(12)},
        **{f"c{i}": {"status": "cached", "extra": {}} for i in range(29)},
        "o1": {"status": "executed", "extra": {"exported_path": "x"}}, "o2": {"status": "executed", "extra": {"exported_path": "y"}}}}
    pg.evaluate("r => import('/static/js/run_notice.js').then((N) => N.showRunNotice(r, window.__S.store.workflow.name, { onLog: () => {} }))", report)
    pg.wait_for_timeout(400)
    shot(pg.locator(".run-notice").last, "aviso-fim")
    pg.evaluate("() => document.querySelectorAll('.run-notice').forEach((e) => e.remove())")
    # o menu Exibir inteiro (spec 044: submenus), com o aviso ligado
    pg.get_by_role("button", name="Exibir").first.click()
    pg.wait_for_selector(".menu")
    pg.wait_for_timeout(300)
    shot(pg.locator(".menu"), "aviso-fim-menu")
    pg.keyboard.press("Escape")
