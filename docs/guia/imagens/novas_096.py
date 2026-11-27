"""Capturas da 0.9.6 (spec 049): Comece por aqui, o catálogo de dados públicos, a caixa, a pasta Dados públicos, a
citação, as receitas (IPCA, PTAX, municípios), o Join pela data anterior, o curinga no PDF e o CNPJ.

Como as conferências de tela (scripts/conferir_tela.py), lê o Banco Central, o IBGE e a Receita de verdade: os prints
mostram dados reais. Do CNPJ, só as tabelas pequenas são baixadas; os Estabelecimentos do filtro são de mentira.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

Shot = Callable[..., None]


def part_096(pg: Any, tmp: Path, shot: Shot) -> None:
    pg.evaluate("async () => { window.__CV = await import('/static/js/canvas.js'); }")
    steps: list[tuple[str, Callable[[], None]]] = [
        ("health", lambda: _seed_health(tmp / "dados")),
        ("welcome", lambda: _welcome(pg, shot)),
        ("catalog", lambda: _catalog(pg, shot)),
        ("places", lambda: _places(pg, shot)),
        ("public_box", lambda: _public_box(pg, shot)),
        ("saved", lambda: _saved(pg, tmp / "dados", shot)),
        ("citation", lambda: _citation(pg, shot)),
        ("recipes", lambda: _recipes(pg, shot)),
        ("municipios", lambda: _municipios(pg, shot)),
        ("join", lambda: _join_previous(pg, shot)),
        ("pdf", lambda: _pdf_wildcard(pg, shot)),
        ("cnpj", lambda: _cnpj(pg, tmp, shot)),
        ("formato", lambda: _formato(pg, shot)),
    ]
    only = os.environ.get("IMAGENS_096")  # para refazer só algumas etapas: IMAGENS_096=pdf,cnpj
    for name, step in steps:
        if not only or name in only.split(","):
            step()


# ---------------------------------------------------------------- auxiliares


# A situação dos órgãos nos prints: a checagem de verdade muda a cada geração (uma queda de minutos fica congelada no
# guia). Ficam fora do ar só o Comex Stat e o portal de Minas Gerais, com as mensagens reais de 26/11/2026 (503 e
# 502): o guia mostra como um erro aparece. O programa não confere de novo antes de 5 minutos.
DOWN = {
    "comex": "O site do Comex Stat respondeu erro 503: serviço indisponível.",
    "mg": "O portal de Minas Gerais respondeu erro 502: erro no servidor intermediário.",
}


def _seed_health(data: Path) -> None:
    from datetime import datetime

    from prodata.catalog import hosts

    now = datetime.now()
    moment, today = now.isoformat(), now.date().isoformat()
    services = {}
    for sid in hosts.SERVICES:
        down = sid in DOWN
        services[sid] = {"situacao": "fora" if down else "no_ar", "motivo": DOWN.get(sid, ""),
                         "segundos": 0.1 if down else 0.2, "conferido_em": moment, "desde": moment if down else None,
                         "historico": {today: "fora" if down else "no_ar"}}  # fmt: skip
    folder = data / "catalogo"
    folder.mkdir(parents=True, exist_ok=True)
    body = {"servicos": services, "sem_conexao": False, "conferido_em": moment}
    (folder / "situacao.json").write_text(json.dumps(body, ensure_ascii=False, indent=1), encoding="utf-8")


def _quiet(pg: Any) -> None:
    pg.evaluate(
        "() => document.querySelectorAll('.toast, .canvas-hint, .bi-hover, .run-notice').forEach((e) => e.remove())"
    )


def _new_flow(pg: Any) -> None:
    # Fecha o fluxo novo anterior (sem salvar), para os prints não acumularem abas "Novo fluxo"
    active = pg.locator(".wf-tab.active", has_text="Novo fluxo")
    if active.count():
        active.locator(".wf-tab-close").dispatch_event("click")  # o X só aparece com o mouse em cima
        pg.wait_for_timeout(400)
        ask = pg.locator("dialog[open] button", has_text="Não salvar")
        if ask.count():
            ask.click()
        pg.wait_for_timeout(500)
    pg.locator(".top-menu", has_text="Arquivo").click()
    pg.locator(".menu .menu-item", has_text="Novo fluxo").click()
    pg.wait_for_timeout(600)


def _run(pg: Any) -> None:
    pg.evaluate("() => { window.__old = window.__S.store.execution; }")
    pg.evaluate("() => import('/static/js/canvas_state.js').then((CS) => CS.state.handlers.run())")
    pg.wait_for_function(
        "() => window.__S.store.execution !== window.__old && !window.__S.store.running", timeout=180000
    )
    pg.wait_for_timeout(500)


def _configure(pg: Any, node_id: str) -> None:
    pg.evaluate("id => window.__S.select(id)", node_id)
    pg.locator("#leftPanel .tab[data-tab=config]").click()
    pg.wait_for_timeout(400)


def _inspect(pg: Any, node_id: str, tab: str = "data") -> None:
    pg.evaluate("id => { window.__S.select(id); window.__S.inspect(id); }", node_id)
    pg.locator(f"#results .tab[data-tab={tab}]").click()
    pg.wait_for_timeout(600)


def _fit(pg: Any) -> None:
    pg.evaluate("() => window.__CV.fitView?.()")
    pg.wait_for_timeout(600)


def _data_view(pg: Any) -> None:
    pg.locator("#viewSwitch .segment[data-view=data]").click()
    pg.wait_for_timeout(700)  # a troca de vista desliza: o print sai com a tela parada


def _open_catalog(pg: Any) -> Any:
    _data_view(pg)
    pg.locator(".dv-list-head button", has_text="Adicionar").click()
    pg.locator(".menu .menu-item", has_text="Dados públicos do Brasil").click()
    dlg = pg.locator("dialog.pd-dialog[open]")
    dlg.locator(".pd-card").first.wait_for(timeout=30000)
    pg.wait_for_timeout(600)
    return dlg


def _choose(dlg: Any, pg: Any, name: str, button: str) -> None:
    """Abre o detalhe da fonte e espera o botão (Adicionar ao fluxo, À vista Dados) ficar pronto."""
    dlg.locator(".pd-menu-item", has_text="Destaques").click()  # o catálogo reabre no último portal visto
    pg.wait_for_timeout(600)
    dlg.locator(".pd-search input").fill(name)
    pg.wait_for_timeout(900)
    dlg.locator(".pd-card", has_text=name).first.click()
    pg.wait_for_function(
        f"""() => {{ const b = [...document.querySelectorAll('.pd-actions button')].find((x) => x.textContent.includes({json.dumps(button)}));
        return b && !b.disabled; }}""",
        timeout=60000,
    )


def _source(source_id: str) -> dict[str, Any]:
    from prodata.catalog import curated, hosts

    s = curated.get(source_id)
    assert s is not None
    return {"fonte": {"id": s.id, "nome": s.nome, "orgao": hosts.SERVICES[s.servico].agency, "citacao": s.citacao,
                      "licenca": s.licenca, "escolhas": {"periodo": {"kind": "ultimos_anos", "anos": 1}}}}  # fmt: skip


# ---------------------------------------------------------------- vista Dados e catálogo


def _welcome(pg: Any, shot: Shot) -> None:
    _data_view(pg)
    pg.evaluate(
        "() => import('/static/js/data_view.js').then((m) => { m.openInData(null); m.renderDataView(); })"
    )
    welcome = pg.locator(".dv-welcome")
    welcome.wait_for(timeout=10000)
    pg.wait_for_timeout(500)
    _quiet(pg)
    shot(welcome, "dados-comece")


def _catalog(pg: Any, shot: Shot) -> None:
    dlg = _open_catalog(pg)
    _quiet(pg)
    shot(dlg, "catalogo-abertura")
    # A Selic diária: o último dado, a situação do Banco Central, a prévia lida agora e como citar
    dlg.locator(".pd-menu-item", has_text="Economia e juros").click()
    dlg.locator(".pd-card", has_text="Taxa Selic diária").first.click()
    detail = dlg.locator(".pd-detail")
    detail.locator(".pd-table tbody tr").first.wait_for(timeout=60000)
    detail.locator(".pd-health").wait_for(timeout=20000)
    pg.wait_for_function(
        "() => !document.querySelector('.pd-health.is-nao_conferido') || document.querySelector('.pd-offline')",
        timeout=40000,
    )
    pg.wait_for_timeout(600)
    _quiet(pg)
    shot(dlg, "catalogo-detalhe")
    # Editar feriados: um município que não é capital, com um feriado próprio
    dlg.locator(".pd-menu-item", has_text="Calendário").click()
    dlg.locator(".pd-card", has_text="Feriados").first.click()
    detail.locator("button", has_text="Editar feriados").click()
    editor = pg.locator("dialog.hol-dialog[open]")
    editor.locator(".hol-row").first.wait_for(timeout=20000)
    local = editor.locator(".hol-top input").first
    local.fill("3509502")
    local.press("Tab")
    editor.locator(".hol-row", has_text="Revolução Constitucionalista").wait_for(timeout=20000)
    editor.locator("button", has_text="Incluir feriado").click()
    editor.locator(".hol-form input").first.fill("Nossa Senhora da Conceição")
    editor.locator(".hol-rule input.input").fill("08/12")
    editor.locator(".hol-form button", has_text="Incluir").click()
    editor.locator(".hol-row", has_text="Nossa Senhora da Conceição").wait_for(timeout=20000)
    pg.wait_for_timeout(500)
    _quiet(pg)
    shot(editor, "feriados-editor")
    editor.locator("header button").click()
    # Um portal: o catálogo dos órgãos é lido em segundo plano na primeira abertura
    for _ in range(300):  # evaluate espera a promessa; wait_for_function trataria a promessa como "pronto"
        if not pg.evaluate(
            "() => fetch('/api/catalogo/atualizar').then((r) => r.json()).then((s) => s.rodando)"
        ):
            break
        pg.wait_for_timeout(1000)
    pg.wait_for_timeout(1500)
    dlg.locator(".pd-menu-item", has_text="ANEEL").click()
    dlg.locator(".pd-card").first.wait_for(timeout=30000)
    dlg.locator(".pd-card").first.click()
    pg.wait_for_timeout(2500)
    _quiet(pg)
    shot(dlg, "catalogo-portal")
    dlg.locator("header button").first.click()


def _places(pg: Any, shot: Shot) -> None:
    """Revisão de 2026-11-26: o mapa do Brasil, o painel de um estado, os lugares na busca e a barra de progresso."""
    dlg = _open_catalog(pg)
    dlg.locator(".pd-menu-item", has_text="Mapa do Brasil").click()
    dlg.locator(".pd-uf").first.wait_for(timeout=15000)
    pg.wait_for_timeout(600)
    _quiet(pg)
    shot(dlg, "catalogo-mapa")
    dlg.locator('.pd-uf[data-uf="MG"]').click()
    pg.wait_for_function(
        "() => (document.querySelector('.pd-place')?.textContent || '').includes('Belo Horizonte')",
        timeout=15000,
    )
    dlg.locator(".pd-place-finder input").fill("juiz")
    pg.wait_for_timeout(800)
    _quiet(pg)
    shot(dlg, "catalogo-estado")
    dlg.locator(".pd-search input").fill("campinas")
    dlg.locator(".pd-place-card").first.wait_for(timeout=15000)
    pg.wait_for_timeout(800)
    _quiet(pg)
    shot(dlg, "catalogo-lugares")
    dlg.locator(".pd-search input").fill("")
    dlg.locator(".pd-menu-item", has_text="Destaques").click()
    refresh = dlg.locator(".pd-top button", has_text="Atualizar o catálogo")
    if (
        refresh.is_enabled()
    ):  # num servidor novo, o catálogo nunca lido já começa a atualizar sozinho ao abrir
        refresh.click()
    dlg.locator(".pd-refreshing").wait_for(timeout=15000)
    pg.wait_for_function(
        r"() => /[1-9]\d* de \d+ catálogos lidos/.test(document.querySelector('.pd-refreshing')?.textContent || '')",
        timeout=300000,  # o primeiro catálogo (Banco Central) pode levar mais de um minuto
    )
    _quiet(pg)
    top = dlg.locator(".pd-top").bounding_box()
    shot(
        pg,
        "catalogo-progresso",
        clip={"x": top["x"], "y": top["y"], "width": top["width"], "height": top["height"] + 6},
    )
    for _ in range(
        300
    ):  # a leitura segue; espera terminar para as etapas seguintes acharem o catálogo pronto
        if not pg.evaluate(
            "() => fetch('/api/catalogo/atualizar').then((r) => r.json()).then((s) => s.rodando)"
        ):
            break
        pg.wait_for_timeout(1000)
    dlg.locator("header button").first.click()


def _public_box(pg: Any, shot: Shot) -> None:
    _new_flow(pg)
    dlg = _open_catalog(pg)
    _choose(dlg, pg, "Taxa Selic diária", "Adicionar ao fluxo")
    dlg.locator(".pd-actions button", has_text="Adicionar ao fluxo").click()
    pg.wait_for_function(
        "() => window.__S.store.workflow.nodes.some((n) => n.type === 'io.public_data')", timeout=15000
    )
    node_id = pg.evaluate("() => window.__S.store.workflow.nodes.find((n) => n.type === 'io.public_data').id")
    _run(pg)
    _inspect(pg, node_id)
    _configure(pg, node_id)
    pg.locator(".pd-box").wait_for(timeout=15000)
    _fit(pg)
    _quiet(pg)
    shot(pg, "caixa-publica")


def _saved(pg: Any, data: Path, shot: Shot) -> None:
    _new_flow(pg)
    dlg = _open_catalog(pg)
    _choose(dlg, pg, "Taxa Selic diária", "À vista Dados")
    dlg.locator(".pd-actions button", has_text="À vista Dados").click()
    pg.locator(".pd-saved").wait_for(timeout=15000)
    head = pg.locator(".dv-detail .dv-head")
    head.wait_for(timeout=15000)
    pg.wait_for_timeout(800)
    _quiet(pg)
    shot(pg, "pasta-publica")
    head.locator("button", has_text="Usar no fluxo").click()
    pg.wait_for_function(
        "() => window.__S.store.view === 'designer' && window.__S.store.workflow.nodes.some((n) => n.type === 'io.public_data')",
        timeout=15000,
    )
    node_id = pg.evaluate("() => window.__S.store.workflow.nodes.find((n) => n.type === 'io.public_data').id")
    kpi = pg.evaluate(
        """(src) => { const k = window.__A.addNode('bi.kpi_card', 0, 0, { title: 'Dias de Selic', metric: 'count' }).id;
        const n = window.__S.store.workflow.nodes.find((x) => x.id === src); const kn = window.__S.store.workflow.nodes.find((x) => x.id === k);
        kn.x = n.x + 300; kn.y = n.y; window.__A.connect(src, 'out', k, 'in'); return k; }""",
        node_id,
    )
    _run(pg)
    # O órgão "publica" dados mais novos que a leitura (o que a conferência do catálogo gravaria)
    tomorrow = time.strftime("%Y-%m-%d", time.localtime(time.time() + 86400))
    (data / "catalogo").mkdir(parents=True, exist_ok=True)
    (data / "catalogo" / "novidades.json").write_text(json.dumps({"bcb.sgs/11": {
        "atualizado": tomorrow, "rotulo": "último dado em", "conferido_em": time.strftime("%Y-%m-%dT%H:%M:%S")}}), encoding="utf-8")  # fmt: skip
    pg.evaluate("() => import('/static/js/public_news.js').then((m) => m.refreshNodeNews())")
    badge = pg.locator(f".node[data-id='{node_id}'] .node-news")
    badge.wait_for(timeout=15000)
    _fit(pg)
    badge.hover()
    pg.wait_for_timeout(900)
    box = pg.locator(f".node[data-id='{node_id}']").bounding_box()
    end = pg.locator(f".node[data-id='{kpi}']").bounding_box()
    _quiet(pg)
    left, top = box["x"] - 60, box["y"] - 110
    shot(pg, "dados-novos-caixa", clip={"x": left, "y": top, "width": end["x"] + end["width"] + 60 - left,
                                        "height": max(box["height"], end["height"]) + 240})  # fmt: skip


def _citation(pg: Any, shot: Shot) -> None:
    _new_flow(pg)
    ids = pg.evaluate(
        """([selic, ipca]) => {
          const a = window.__A.addNode('io.public_data', 100, 100, { ...selic, __label: selic.fonte.nome }).id;
          const b = window.__A.addNode('io.public_data', 100, 280, { ...ipca, __label: ipca.fonte.nome }).id;
          const line = (title) => ({ title, chart_type: 'line', x_column: 'data', y_column: 'valor', agg: 'mean', sort: 'label' });
          const ka = window.__A.addNode('bi.chart', 420, 100, line('Selic diária (% ao dia)')).id;
          const kb = window.__A.addNode('bi.chart', 420, 280, line('IPCA (número-índice)')).id;
          window.__A.connect(a, 'out', ka, 'in'); window.__A.connect(b, 'out', kb, 'in'); return [a, b]; }""",
        [_source("bcb.sgs/11"), _source("ibge.agregado/1737")],
    )
    _run(pg)
    _inspect(pg, ids[0], "profile")
    pg.locator(".profile-source").wait_for(timeout=15000)
    pg.wait_for_timeout(500)
    _quiet(pg)
    shot(pg.locator("#results"), "perfil-fonte")
    pg.locator("#viewSwitch .segment[data-view=dashboard]").click()
    cite = pg.locator(".dash-citation")
    cite.wait_for(timeout=30000)
    pg.wait_for_timeout(900)
    cite.scroll_into_view_if_needed()
    pg.wait_for_timeout(300)
    _quiet(pg)
    shot(pg, "dash-citacao")
    pg.locator("#viewSwitch .segment[data-view=designer]").click()
    pg.wait_for_timeout(600)


# ---------------------------------------------------------------- receitas e Join


def _sales(pg: Any, columns: list[str], rows: list[list[str]]) -> str:
    node_id: str = pg.evaluate(
        "([columns, rows]) => window.__A.addNode('io.text_input', 100, 200, { table: { columns, rows } }).id",
        [columns, rows],
    )
    _run(pg)
    _inspect(pg, node_id)
    return node_id


def _column_menu(pg: Any, column: str, label: str) -> Any:
    pg.locator("th.sortable", has_text=column).first.click(button="right")
    pg.locator(".menu .menu-item", has_text=label).click()
    dlg = pg.locator("dialog[open]", has=pg.locator(".rc-dialog"))
    dlg.wait_for(timeout=10000)
    return dlg


def _recipes(pg: Any, shot: Shot) -> None:
    _new_flow(pg)
    node_id = _sales(
        pg, ["data", "valor"], [["2025-01-15", "100"], ["2025-06-14", "250"], ["2025-09-20", "80"]]
    )
    dlg = _column_menu(pg, "valor", "Corrigir valores pelo IPCA")
    pg.wait_for_timeout(500)
    _quiet(pg)
    shot(dlg, "receita-ipca")
    dlg.locator("button", has_text="Inserir no fluxo").click()
    pg.wait_for_function(
        "() => window.__S.store.workflow.containers.some((c) => c.title.includes('IPCA'))", timeout=10000
    )
    _inspect(pg, node_id)
    dlg = _column_menu(pg, "valor", "Converter para dólar pela PTAX")
    dlg.locator("button", has_text="Inserir no fluxo").click()
    pg.wait_for_function("() => window.__S.store.workflow.containers.length >= 2", timeout=10000)
    _run(pg)
    last = pg.evaluate("""() => { const wf = window.__S.store.workflow; const used = new Set(wf.edges.map((e) => e.source));
      return wf.nodes.find((n) => n.type === 'prep.formula' && !used.has(n.id)).id; }""")
    _inspect(pg, last)
    pg.evaluate("() => window.__S.select(null)")
    pg.keyboard.press("F11")  # modo foco: o canvas inteiro para as duas etapas
    pg.wait_for_timeout(900)
    _fit(pg)
    _quiet(pg)
    shot(pg, "receitas-canvas")
    pg.keyboard.press("F11")
    pg.wait_for_timeout(600)


def _municipios(pg: Any, shot: Shot) -> None:
    _new_flow(pg)
    _sales(pg, ["cidade", "vendas"], [["Sao Paulo/SP", "10"], ["355030", "5"], ["3509502", "7"],
                                      ["SANTA BARBARA D'OESTE - SP", "3"], ["Bom Jesus", "2"], ["Cidade Inventada", "1"]])  # fmt: skip
    dlg = _column_menu(pg, "cidade", "Juntar com municípios do IBGE")
    dlg.locator(".rc-match").wait_for(timeout=90000)
    pg.wait_for_timeout(500)
    _quiet(pg)
    shot(dlg, "municipios-conferencia")
    pg.keyboard.press("Escape")


def _join_previous(pg: Any, shot: Shot) -> None:
    """Venda no sábado com a cotação de sexta: Join pela data anterior mais próxima."""
    _new_flow(pg)
    join = pg.evaluate("""() => {
      const A = window.__A;
      const date = (col) => ({ formulas: [{ target: 'existing', existing: col, type: 'Date', expression: `ToDate([${col}])` }] });
      const sales = A.addNode('io.text_input', 80, 120, { table: { columns: ['venda', 'data'], rows: [['V-101', '2026-03-02'],
        ['V-102', '2026-03-04'], ['V-103', '2026-03-07'], ['V-104', '2026-03-08'], ['V-105', '2026-03-09']] }, __label: 'Vendas' }).id;
      const rates = A.addNode('io.text_input', 80, 330, { table: { columns: ['cotacao_data', 'dolar'], rows: [['2026-03-02', '5,71'],
        ['2026-03-03', '5,69'], ['2026-03-04', '5,74'], ['2026-03-05', '5,72'], ['2026-03-06', '5,68'], ['2026-03-09', '5,70']] },
        __label: 'Cotações (dias úteis)' }).id;
      const fs = A.addNode('prep.formula', 330, 120, { ...date('data'), __label: 'Data da venda' }).id;
      const fr = A.addNode('prep.formula', 330, 330, { ...date('cotacao_data'), __label: 'Data da cotação' }).id;
      const j = A.addNode('transform.join', 600, 220, { keys: [{ left: 'data', right: 'cotacao_data' }], match: 'previous',
        keys_mode: 'both', stack: 'LJ', stack_column: '', __label: 'Cotação do dia ou da véspera útil' }).id;
      A.connect(sales, 'out', fs, 'in'); A.connect(rates, 'out', fr, 'in'); A.connect(fs, 'out', j, 'L'); A.connect(fr, 'out', j, 'R');
      return j; }""")
    _run(pg)
    pg.evaluate("id => { window.__S.select(id); window.__S.inspect(id, 'U'); }", join)
    pg.locator("#results .tab[data-tab=data]").click()
    _configure(pg, join)
    _fit(pg)
    _quiet(pg)
    shot(pg, "join-anterior")


# ---------------------------------------------------------------- PDF: curinga e limite de palavras


def _pdf_wildcard(pg: Any, shot: Shot) -> None:
    """No relatório de julho, "a julho de 2026, a arrecadação alcançou R$ 1.791.203 milhões": o rótulo proposto já
    vem com [mês] e [ano], e a regra pega só as palavras marcadas."""
    _data_view(pg)
    pg.locator(".dv-list").get_by_text("Arrecadação federal (Receita Federal)").first.click()
    pg.locator(".dv-detail .dv-tab", has_text="Extração").first.click()
    pg.wait_for_selector(".pv-w", timeout=60000)
    doc = "arrecadacao_2026-07.pdf"
    pg.locator(".pe-doc-select").select_option(doc)
    pg.wait_for_timeout(2000)
    index = pg.evaluate(
        """async (doc) => {
          const sid = (await (await fetch('/api/pdfs')).json()).find((p) => p.name.startsWith('Arrecadação federal')).id;
          const info = await (await fetch(`/api/pdfs/${sid}/docs/words?doc=${encodeURIComponent(doc)}`)).json();
          const w = info.words;
          return w.findIndex((x, i) => x.t === 'R$' && w[i + 1]?.t === '1.791.203' && w[i - 1]?.t === 'alcançou');
        }""",
        doc,
    )
    pg.locator(
        '.pv-page[data-page="3"]'
    ).scroll_into_view_if_needed()  # as páginas são desenhadas ao aparecer
    word = pg.locator(f'.pv-w[data-i="{index}"]')
    word.wait_for(timeout=30000)
    word.scroll_into_view_if_needed()
    word.click()
    pg.locator(f'.pv-w[data-i="{index + 1}"]').click(modifiers=["Shift"])
    pg.wait_for_function(
        "() => !document.querySelector('.pv-action small')?.textContent.includes('lendo')", timeout=15000
    )
    pg.wait_for_timeout(500)
    marked = pg.locator(".pv-action").inner_text()
    assert "1.791.203" in marked and "7,71" not in marked, marked
    pg.keyboard.press("Enter")
    pg.wait_for_function(
        "() => [...document.querySelectorAll('.pe-fields [data-field]')].some((e) => e.textContent.includes('[mês]'))",
        timeout=20000,
    )
    card = pg.locator(".pe-fields [data-field]", has_text="[mês]").last
    card.click()
    more = card.locator("details.pe-more", has_text="Rótulos aceitos")
    if more.count():
        more.locator("summary").click()
    card.scroll_into_view_if_needed()  # o cartão novo inteiro, com o rótulo e "só as 2 primeiras palavras"
    pg.wait_for_timeout(1200)
    _quiet(pg)
    shot(pg.locator(".pe"), "pdf-curinga")


# ---------------------------------------------------------------- CNPJ


ESTAB_COLUMNS = ("cnpj_basico;cnpj_ordem;cnpj_dv;identificador_matriz_filial;nome_fantasia;situacao_cadastral;"
                 "data_situacao_cadastral;motivo_situacao_cadastral;nome_cidade_exterior;pais;data_inicio_atividade;"
                 "cnae_fiscal_principal;cnae_fiscal_secundaria;tipo_logradouro;logradouro;numero;complemento;bairro;"
                 "cep;uf;municipio;ddd_1;telefone_1;ddd_2;telefone_2;ddd_fax;fax;correio_eletronico;"
                 "situacao_especial;data_situacao_especial")  # fmt: skip


def _estab_row(basic: str, order: str, dv: str, uf: str, cnae: str) -> str:
    fields = [basic, order, dv, "1", "LOJA", "02", "20050101", "00", "", "", "19990315", cnae, "", "RUA", "A", "1", "",
              "C", "01001000", uf, "7107"] + [""] * 9  # fmt: skip
    return ";".join(f'"{f}"' for f in fields)


def _cnpj(pg: Any, tmp: Path, shot: Shot) -> None:
    target = tmp / "Receita"  # no print, D:\Dados\Receita (o caminho de verdade não aparece)
    target.mkdir()
    dlg = _open_catalog(pg)
    dlg.locator(".pd-menu-item", has_text="Destaques").click()  # o catálogo reabre no último portal visto
    pg.wait_for_timeout(600)
    dlg.locator(".pd-search input").fill("cnpj")
    dlg.locator(".pd-card", has_text="Cadastro de empresas").first.click()
    dlg.locator(".pd-actions button", has_text="Baixar").click()
    box = pg.locator("dialog[open]", has=pg.locator(".cnpj-dialog"))
    box.locator(".cnpj-group").first.wait_for(timeout=60000)
    for name in ("Empresas", "Estabelecimentos"):  # só as tabelas pequenas, para o print não baixar 6 GB
        item = box.locator(".cnpj-group", has_text=name).first
        if item.locator("input").is_checked():
            item.locator("input").uncheck()
    box.locator("button", has_text="Escolher pasta").click()
    ask = pg.locator("dialog[open]", has_text="Onde salvar o CNPJ")
    ask.locator("input").fill(str(target))
    ask.locator("button", has_text="OK").click()
    box.locator(".cnpj-disk").wait_for(timeout=30000)
    pg.wait_for_timeout(500)
    _quiet(pg)
    shot(box, "cnpj-baixar")
    box.get_by_role("button", name="Baixar", exact=True).click()
    dlg.locator("header button").first.click()
    pg.locator(".cnpj-job").first.wait_for(timeout=30000)
    pg.wait_for_function(
        "() => document.querySelector('.cnpj-job')?.classList.contains('is-concluido')", timeout=300000
    )
    pg.wait_for_function(
        "() => (document.querySelector('.dv-list')?.textContent || '').includes('CNAE')", timeout=30000
    )
    pg.locator(".dv-list").get_by_text("· CNAE").first.click()
    pg.wait_for_timeout(1200)
    _quiet(pg)
    shot(pg, "cnpj-faixa")
    # O filtro na leitura, com Estabelecimentos de mentira (o de verdade tem 5 GB)
    dest = next(target.iterdir())
    lines = [ESTAB_COLUMNS, _estab_row("00000000", "0001", "91", "DF", "6422100"),
             _estab_row("12345678", "0001", "95", "SP", "1091101"), _estab_row("12345678", "0002", "76", "RJ", "1091101")]  # fmt: skip
    (dest / "estabelecimentos_0.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    pg.evaluate(
        """(folder) => fetch('/api/folders', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: 'CNPJ · Estabelecimentos', folder, pattern: 'estabelecimentos_*.csv',
            file_column: '', format: 'csv', delimiter: ';', encoding: 'utf-8', has_header: true,
            layout: 'receita.cnpj/estabelecimentos' }) }).then((r) => r.json())""",
        str(dest),
    )
    pg.evaluate("() => import('/static/js/folder_sources.js').then((m) => m.refreshFolderSources())")
    pg.locator(".dv-list").get_by_text("CNPJ · Estabelecimentos").first.click()
    pg.locator(".dv-detail .dv-tab", has_text="Cadastro").first.click()
    section = pg.locator(".cf-section")
    section.wait_for(timeout=15000)
    section.locator(".cf-uf", has_text="SP").click()
    section.locator("textarea").fill("00.000.000/0001-91\n12.345.678\n11.222.333/0001-00")
    section.locator("button", has_text="Conferir e incluir").click()
    pg.wait_for_function("() => document.querySelectorAll('.cf-chip').length >= 2", timeout=15000)
    pg.wait_for_timeout(1500)
    section.scroll_into_view_if_needed()
    _quiet(pg)
    shot(pg, "cnpj-filtro")
    # A pergunta de memória (o freio de verdade é testado no motor; aqui, a tela com uma estimativa)
    pg.evaluate(
        # sem devolver a promessa: ela só termina com a resposta, e o print é da pergunta aberta
        """() => { import('/static/js/memory_ask.js').then((m) => m.askMemory({ node_results: { 'CNPJ · Estabelecimentos': {
          status: 'error', error: 'Esta leitura deve ocupar cerca de 6,0 GB, mais de 1/4 da memória deste computador (16,0 GB).',
          extra: { pergunta_memoria: { estimado: 6 * 1024 ** 3, memoria: 16 * 1024 ** 3 } } } } })); }"""
    )
    mem = pg.locator("dialog[open]", has=pg.locator(".mem-bar"))
    mem.wait_for(timeout=10000)
    pg.wait_for_timeout(500)
    _quiet(pg)
    shot(mem, "memoria-pergunta")
    mem.locator("button", has_text="Parar").click()


# ---------------------------------------------------------------- formato de exibição (spec 050)

_CHART = {"title": "Valor por cliente", "series_column": "", "sort": "value_desc", "max_items": 12, "tip_columns": [],
          "pareto_threshold": 80, "x_value_column": "", "size_column": "", "chart_type": "bar", "x_column": "cliente",
          "y_column": "valor", "agg": "sum"}  # fmt: skip


def _format_dialog(pg: Any, column: str) -> Any:
    name = pg.locator(".th-name", has_text=re.compile(f"^{column}$"))
    pg.locator("#results th.sortable", has=name).first.click(button="right")
    pg.locator(".menu .menu-item", has_text="Formato de exibição").click()
    dlg = pg.locator("dialog[open]", has=pg.locator(".cf-dialog"))
    dlg.wait_for(timeout=10000)
    return dlg


def _formato(pg: Any, shot: Shot) -> None:
    # a etapa anterior (CNPJ) termina na vista Dados: o Resultado só aparece no Designer
    pg.keyboard.press("Escape")
    pg.locator("#viewSwitch .segment[data-view=designer]").click()
    pg.wait_for_timeout(600)
    _new_flow(pg)
    ids = pg.evaluate(
        """(chart) => { const A = window.__A;
          const t = A.addNode('io.text_input', 100, 200, { table: { columns: ['cliente', 'valor', 'cpf', 'data'], rows: [
            ['Ana Souza', '1234,5', '1234567890', '2026-11-26'], ['Bruno Lima', '-10', '12345678901', '2026-01-02'],
            ['Carla Dias', '9876,25', '123456789012', '2026-03-05'], ['Davi Rocha', '4500', '9876543210', '2026-07-19']] } }).id;
          const f = A.addNode('prep.formula', 380, 200, { formulas: [{ target: 'existing', existing: 'data', type: 'Date', expression: 'ToDate([data])' }] }).id;
          const c = A.addNode('bi.chart', 660, 120, chart).id;
          const k = A.addNode('bi.kpi_card', 660, 300, { title: 'Valor total', column: 'valor', metric: 'sum' }).id;
          A.connect(t, 'out', f, 'in'); A.connect(f, 'out', c, 'in'); A.connect(f, 'out', k, 'in');
          return { t, f }; }""",
        _CHART,
    )
    _run(pg)
    _inspect(pg, ids["t"])
    dlg = _format_dialog(pg, "cpf")
    pg.wait_for_timeout(400)
    _quiet(pg)
    shot(dlg, "formato-dialogo")
    dlg.locator(".dialog-footer button", has_text="Aplicar").click()
    dlg = _format_dialog(pg, "valor")
    dlg.locator(".cf-kind[data-kind=currency]").click()
    dlg.locator(".dialog-footer button", has_text="Aplicar").click()
    _inspect(pg, ids["f"])
    dlg = _format_dialog(pg, "data")
    dlg.locator(".dialog-footer button", has_text="Aplicar").click()
    # a tabela em modo foco: as quatro colunas cabem no print
    pg.evaluate("() => import('/static/js/results.js').then((m) => m.toggleTableFocus(true))")
    pg.wait_for_timeout(900)
    _quiet(pg)
    panel = pg.locator("#results").bounding_box()
    table = pg.locator("#results .data-table").bounding_box()
    width = min(panel["width"], table["x"] + table["width"] + 12 - panel["x"])
    shot(pg, "formato-resultado", clip={"x": panel["x"], "y": panel["y"], "width": width,
                                        "height": table["y"] + table["height"] + 12 - panel["y"]})  # fmt: skip
    pg.evaluate("() => import('/static/js/results.js').then((m) => m.toggleTableFocus(false))")
    pg.wait_for_timeout(500)
    pg.locator("#viewSwitch .segment[data-view=dashboard]").click()
    pg.locator(".dash-item").first.wait_for(timeout=20000)
    chart = pg.locator(".dash-item", has=pg.locator(".chart-card", has_text="Valor por cliente")).first
    kpi = pg.locator(".dash-item", has=pg.locator(".kpi", has_text="Valor total")).first
    chart.scroll_into_view_if_needed()
    pg.wait_for_timeout(2500)  # as barras crescem ao aparecer: o print sai com o gráfico parado
    _quiet(pg)
    a, b = chart.bounding_box(), kpi.bounding_box()
    left, top = min(a["x"], b["x"]) - 8, min(a["y"], b["y"]) - 8
    right, bottom = (
        max(a["x"] + a["width"], b["x"] + b["width"]) + 8,
        max(a["y"] + a["height"], b["y"] + b["height"]) + 8,
    )
    shot(pg, "formato-dashboard", clip={"x": left, "y": top, "width": right - left, "height": bottom - top})
    pg.locator("#viewSwitch .segment[data-view=designer]").click()
    pg.wait_for_timeout(600)
