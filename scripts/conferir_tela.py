"""Conferências da tela no navegador, como uma pessoa usando o programa (antes de cada versão).

    uv run --with playwright python scripts/conferir_tela.py            # todas
    uv run --with playwright python scripts/conferir_tela.py fio versoes  # só algumas

Sobe o próprio servidor, com uma pasta de dados temporária (nada vai para a biblioteca de ninguém), abre o Chrome sem
janela e confere o comportamento de ponta a ponta: o que os testes do motor não enxergam (cliques, arrastos, diálogos,
animações). Sai com 1 se alguma conferência falhar ou se a página tiver erro de JavaScript.

Conferências: salvar (spec 045), versoes, fio, fonte, erros e pilula (spec 046), equipe, equipe2 a equipe6 (specs 047 e 048,
duas pessoas: sobe um segundo servidor).
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PORT = 8795
URL = f"http://127.0.0.1:{PORT}/"
PORT_BRUNO = 8794  # segunda pessoa, para as conferências com duas pessoas (spec 047)
URL_BRUNO = f"http://127.0.0.1:{PORT_BRUNO}/"
DATA = (
    Path(tempfile.gettempdir()) / "conferir-tela-dados"
)  # trocada em main(): a pasta de dados do servidor da Ana
UPLOAD = """async ([name, text]) => { const fd = new FormData(); fd.append('file', new File([text], name, { type: 'text/csv' }));
  fd.append('overwrite', 'true'); const r = await fetch('/api/datasets', { method: 'POST', body: fd }); return (await r.json()).name; }"""


class Checks:
    def __init__(self) -> None:
        self.failed = 0
        self.total = 0

    def __call__(self, name: str, ok: object, detail: object = "") -> None:
        self.total += 1
        self.failed += not ok
        print(("OK    " if ok else "FALHA ") + name + ("" if ok else f"  {detail}"))


check = Checks()

# ---------------------------------------------------------------- ajudantes


def ready(pg: Page, url: str = URL) -> None:
    pg.goto(url)
    pg.wait_for_function("() => document.querySelectorAll('.node').length > 15", timeout=90000)
    pg.evaluate("""async () => { window.__S = await import('/static/js/store.js'); window.__A = await import('/static/js/actions.js');
      window.__CV = await import('/static/js/canvas.js'); }""")
    pg.wait_for_function("() => window.__S.store.execution && !window.__S.store.running", timeout=180000)


def new_flow(pg: Page) -> str:
    pg.locator(".top-menu", has_text="Arquivo").click()
    pg.locator(".menu .menu-item", has_text="Novo fluxo").click()
    pg.wait_for_timeout(600)
    return str(pg.evaluate("() => window.__S.store.workflow.id"))


def run(pg: Page) -> None:
    pg.evaluate("() => { window.__old = window.__S.store.execution; }")
    pg.evaluate("() => import('/static/js/canvas_state.js').then((CS) => CS.state.handlers.run())")
    pg.wait_for_function(
        "() => window.__S.store.execution !== window.__old && !window.__S.store.running", timeout=120000
    )
    pg.wait_for_timeout(400)


def save_named(pg: Page, name: str) -> None:
    pg.locator("#topActions .save-main").click()
    dlg = pg.locator("dialog[open]")
    dlg.wait_for()
    dlg.locator("input").fill(name)
    dlg.locator("input").press("Enter")
    pg.wait_for_function("() => !window.__S.isDirty()", timeout=10000)


def configure(pg: Page, node_id: str) -> None:
    pg.evaluate("id => window.__S.select(id)", node_id)
    pg.locator("#leftPanel .tab[data-tab=config]").click()
    pg.wait_for_timeout(300)


# ---------------------------------------------------------------- spec 045: primeiro Salvar e salvar automático


def salvar(pg: Page) -> None:
    library = "() => fetch('/api/workflows').then((r) => r.json()).then((l) => l.map((w) => w.id).sort())"
    new_flow(pg)
    before = pg.evaluate(library)
    pg.locator("#topActions .save-arrow").click()
    item = pg.locator(".menu .menu-item", has_text="Salvar automaticamente")
    check("fluxo novo: salvar automático indisponível", item.is_disabled())
    pg.keyboard.press("Escape")
    pg.keyboard.press("Control+s")
    dlg = pg.locator("dialog[open]")
    dlg.wait_for(timeout=5000)
    check("primeiro Salvar pergunta o nome", dlg.locator("input").input_value() == "Novo fluxo")
    dlg.locator("button", has_text="Cancelar").click()
    pg.wait_for_timeout(300)
    check("Cancelar não grava nada na biblioteca", pg.evaluate(library) == before)
    save_named(pg, "Conferência do nome")
    check("grava com o nome escolhido", pg.locator("#wfName").input_value() == "Conferência do nome")
    pg.locator("#topActions .save-arrow").click()
    check(
        "depois de salvo, o automático fica disponível",
        not pg.locator(".menu .menu-item", has_text="Salvar automaticamente").is_disabled(),
    )
    pg.keyboard.press("Escape")
    pg.keyboard.press("Control+s")
    pg.wait_for_timeout(500)
    check("o segundo Salvar não pergunta de novo", pg.locator("dialog[open]").count() == 0)


# ---------------------------------------------------------------- spec 046, C: versões anteriores


def versoes(pg: Page) -> None:
    pg.locator(".top-menu", has_text="Arquivo").click()
    check(
        "no exemplo, Versões anteriores fica indisponível",
        pg.locator(".menu .menu-item", has_text="Versões anteriores").is_disabled(),
    )
    pg.keyboard.press("Escape")
    new_flow(pg)
    pg.evaluate("""() => { const A = window.__A; for (let i = 0; i < 3; i++) A.addNode('prep.select', 100 + i * 260, 200);
      A.addNode('io.input_data', 100, 420); }""")
    save_named(pg, "Conferência das versões")
    pg.evaluate("""() => { const S = window.__S; const ids = S.store.workflow.nodes.slice(1, 3).map((n) => n.id);
      S.mutate((wf) => { wf.nodes = wf.nodes.filter((n) => !ids.includes(n.id)); wf.nodes[0].label = 'Mudou'; }, { structural: true }); }""")
    pg.keyboard.press("Control+s")
    pg.wait_for_function("() => !window.__S.isDirty()", timeout=10000)
    pg.locator(".top-menu", has_text="Arquivo").click()
    pg.locator(".menu .menu-item", has_text="Versões anteriores").click()
    dlg = pg.locator("dialog[open]")
    dlg.locator(".ver-item").first.wait_for()
    check("duas versões guardadas", dlg.locator(".ver-item").count() == 2, dlg.locator(".ver-item").count())
    dlg.locator(".ver-item").nth(1).click()
    dlg.locator(".ver-preview .ver-node").first.wait_for()
    pg.wait_for_timeout(300)
    back, changed = dlg.locator(".ver-node.back").count(), dlg.locator(".ver-node.changed").count()
    check("prévia marca 2 que voltam e 1 diferente", (back, changed) == (2, 1), (back, changed))
    pg.evaluate("() => window.__S.mutate((wf) => { wf.description = 'rascunho'; })")
    dlg.locator("button", has_text="Restaurar esta versão").click()
    pg.wait_for_timeout(500)
    check("restaurar traz as 4 caixas, como mudança não salva",
          pg.evaluate("() => window.__S.store.workflow.nodes.length === 4 && window.__S.isDirty()"))  # fmt: skip
    pg.keyboard.press("Control+z")
    pg.wait_for_timeout(300)
    check(
        "Ctrl+Z volta ao de antes", pg.evaluate("() => window.__S.store.workflow.description === 'rascunho'")
    )
    wid = pg.evaluate("() => window.__S.store.workflow.id")
    listed = pg.evaluate("id => fetch('/api/workflows/' + id + '/versions').then((r) => r.json())", wid)
    check(
        "o que estava aberto virou 'Antes de restaurar'",
        listed and listed[0]["origin"] == "restore",
        [v["origin"] for v in listed],
    )


# ---------------------------------------------------------------- spec 046, D: fio inteligente


def fio(pg: Page) -> None:
    pg.evaluate("() => localStorage.removeItem('prodata.nextTools')")
    new_flow(pg)
    ids = pg.evaluate("""() => { const A = window.__A;
      return { i: A.addNode('io.text_input', 0, 0).id, s: A.addNode('prep.select', 400, -150).id, j: A.addNode('transform.join', 400, 150).id }; }""")
    pg.evaluate("() => window.__CV.fitView()")
    pg.wait_for_timeout(400)

    def center(selector: str) -> tuple[float, float]:
        b = pg.locator(selector).first.bounding_box()
        assert b is not None
        return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2

    def drag(x: float, y: float, release: bool = True) -> str:
        ox, oy = center(f".port.out[data-node='{ids['i']}']")
        pg.mouse.move(ox, oy)
        pg.mouse.down()
        pg.mouse.move(ox + 30, oy + 5, steps=3)
        pg.mouse.move(x, y, steps=8)
        pg.wait_for_timeout(120)
        tip = str(pg.evaluate("() => document.querySelector('.wire-tip')?.innerText || ''"))
        if release:
            pg.mouse.up()
            pg.wait_for_timeout(250)
        return tip

    def edges() -> list[list[str]]:
        return pg.evaluate(
            "() => window.__S.store.workflow.edges.map((e) => [e.source, e.target, e.targetHandle])"
        )

    sx, sy = center(f".port.in[data-node='{ids['s']}']")
    tip = drag(sx - 18, sy + 8, release=False)
    check(f"ímã: a etiqueta diz o que vai acontecer ({tip!r})", tip.startswith("Ligar em"))
    check("entradas compatíveis acesas durante o arrasto", pg.locator(".port.in.wire-ok").count() >= 3)
    pg.mouse.up()
    pg.wait_for_timeout(250)
    check("soltar perto da entrada liga", [ids["i"], ids["s"], "in"] in edges(), edges())
    jx, jy = center(f".node[data-id='{ids['j']}'] .node-card")
    tip = drag(jx, jy)
    check(
        f"em cima do Join: escolher a entrada ({tip!r})",
        "escolher a entrada" in tip and pg.locator(".port-chooser").count() == 1,
    )
    if pg.locator(".port-chooser").count():
        pg.locator(".port-chooser .port-choice").nth(1).click()
        pg.wait_for_timeout(250)
        check("o seletor liga na entrada escolhida", any(e[1] == ids["j"] for e in edges()), edges())
    before = len(edges())
    sb = pg.locator(f".node[data-id='{ids['s']}'] .node-card").bounding_box()
    assert sb is not None
    tip = drag(sb["x"] + sb["width"] / 2, sb["y"] + sb["height"] + 40)
    check(
        "faixa neutra: nada acontece",
        tip == "" and pg.locator(".quick-add").count() == 0 and len(edges()) == before,
    )
    tb = pg.locator(f".node[data-id='{ids['i']}']").bounding_box()
    assert tb is not None
    tip = drag(tb["x"] + 20, tb["y"] + tb["height"] + 150)
    groups = [g.upper() for g in pg.locator(".quick-add .quick-group").all_inner_texts()]
    check(
        f"longe de tudo: lista com as sugeridas ({tip!r})",
        "adicionar" in tip and "SUGERIDAS" in groups,
        groups,
    )
    pg.keyboard.press("Escape")


# ---------------------------------------------------------------- spec 046, A e B: fonte que muda e erros


def fonte(pg: Page) -> None:
    ds = pg.evaluate(UPLOAD, ["conferencia_formato.csv", "uf;valor\nSP;120,50\nRJ;89,90\nMG;15,00\n"])
    new_flow(pg)
    ids = pg.evaluate(
        """(ds) => { const A = window.__A;
      const i = A.addNode('io.input_data', 0, 0, { dataset: ds }).id;
      const f = A.addNode('prep.formula', 300, -120, { formulas: [{ name: 'dobro', expression: '[valor] * 2', type: 'Float64' }] }).id;
      const s = A.addNode('transform.summarize', 300, 120, { group_by: ['uf'], aggregations: [{ column: 'valor', agg: 'sum' }] }).id;
      A.connect(i, 'out', f, 'in'); A.connect(i, 'out', s, 'in'); return { i, f, s }; }""",
        ds,
    )
    pg.evaluate("() => window.__CV.fitView()")
    run(pg)
    names = pg.evaluate(
        "(id) => window.__S.store.workflow.schemas?.[id]?.ports?.out?.map((c) => c.name)", ids["i"]
    )
    check(
        "primeira leitura só lembra o formato",
        names == ["uf", "valor"] and pg.locator(".node-drift").count() == 0,
        names,
    )
    pg.evaluate(
        UPLOAD, ["conferencia_formato.csv", "uf;valor_total;desconto\nSP;120,50;1\nRJ;89,90;2\nMG;15,00;0\n"]
    )
    run(pg)
    check(
        "selo 'formato mudou' na entrada", pg.locator(f".node[data-id='{ids['i']}'] .node-drift").count() == 1
    )
    configure(pg, ids["i"])
    notice = pg.locator("#leftPanel .drift-notice")
    notice.wait_for(timeout=5000)
    text = notice.inner_text()
    check(
        "aviso lista a nova, a que sumiu e as caixas",
        "desconto" in text and "usada em 2 caixas" in text,
        text,
    )
    notice.locator("button", has_text="Mostrar").click()
    pg.wait_for_timeout(400)
    check(
        "acende as 2 caixas atingidas",
        pg.locator(".node.drift-hit").count() == 2,
        pg.locator(".node.drift-hit").count(),
    )
    notice.locator("button", has_text="Trocar por").click()
    dlg = pg.locator("dialog[open]")
    dlg.wait_for()
    check(
        "sugere a coluna do mesmo tipo",
        dlg.locator("input[type=radio]:checked").get_attribute("value") == "valor_total",
    )
    dlg.locator("button", has_text="Trocar em 2 caixas").click()
    pg.wait_for_timeout(500)
    cfg = pg.evaluate(
        "(ids) => [window.__S.node(ids.f).config.formulas[0].expression, window.__S.node(ids.s).config.aggregations[0].column]",
        ids,
    )
    check("troca na fórmula e no Summarize", cfg == ["[valor_total] * 2", "valor_total"], cfg)
    pg.keyboard.press("Control+z")
    pg.wait_for_timeout(300)
    check(
        "um Desfazer volta tudo",
        pg.evaluate("(id) => window.__S.node(id).config.formulas[0].expression", ids["f"]) == "[valor] * 2",
    )
    pg.keyboard.press("Control+y")
    pg.wait_for_timeout(300)
    run(pg)
    status = pg.evaluate(
        "(ids) => [ids.f, ids.s].map((id) => window.__S.store.execution.node_results[id].status)", ids
    )
    check("executa sem erro depois da troca", status == ["executed", "executed"], status)
    configure(pg, ids["i"])
    pg.locator("#leftPanel .drift-notice button", has_text="Entendi").click()
    pg.wait_for_timeout(300)
    check(
        "Entendi apaga o aviso e o selo",
        pg.locator("#leftPanel .drift-notice").count() == 0 and pg.locator(".node-drift").count() == 0,
    )


def erros(pg: Page) -> None:
    new_flow(pg)
    ids = pg.evaluate("""() => { const A = window.__A;
      const t = A.addNode('io.text_input', 0, 0, { table: { columns: ['uf', 'valor'], rows: [['SP', '10'], ['RJ', '20']] } }).id;
      const f = A.addNode('prep.formula', 300, -100, { formulas: [{ name: 'dobro', expression: '[valr] * 2', type: 'Float64' }] }).id;
      const q = A.addNode('transform.sql_query', 300, 120, { sql: 'SELEC * FROM input_1' }).id;
      A.connect(t, 'out', f, 'in'); A.connect(t, 'out', q, 'in'); return { t, f, q }; }""")
    run(pg)
    configure(pg, ids["f"])
    err = pg.locator("#leftPanel .banner-error").first
    err.wait_for()
    check(
        "erro de coluna mostra a parecida",
        "Parecidas com" in err.inner_text() and "valor" in err.inner_text(),
        err.inner_text(),
    )
    check("tem Escolher outra coluna", err.locator("button", has_text="Escolher outra coluna").count() == 1)
    err.locator("button", has_text="valor").first.click()
    pg.wait_for_timeout(400)
    check(
        "um clique troca na fórmula",
        pg.evaluate("(id) => window.__S.node(id).config.formulas[0].expression", ids["f"]) == "[valor] * 2",
    )
    configure(pg, ids["q"])
    err = pg.locator("#leftPanel .banner-error").first
    check("erro do SQL em português", "Erro de sintaxe" in err.inner_text(), err.inner_text())
    err.locator(".err-tech summary").click()
    check(
        "Detalhes técnicos com o texto original", "Parser Error" in err.locator(".err-tech pre").inner_text()
    )


# ---------------------------------------------------------------- spec 047: espaço da equipe (marco 1)


def equipe(pg: Page) -> None:
    # Sem espaço, nada de equipe aparece além do item de menu (RF-4702)
    pg.locator(".top-menu", has_text="Arquivo").click()
    check(
        "sem espaço: Arquivo tem Espaços da equipe…",
        pg.locator(".menu .menu-item", has_text="Espaços da equipe").count() == 1,
    )
    pg.locator(".menu .menu-item", has_text="Abrir da biblioteca").click()
    pg.locator("dialog[open]").wait_for()
    check(
        "sem espaço: a biblioteca não tem abas de equipe", pg.locator("dialog[open] .team-tabs").count() == 0
    )
    pg.keyboard.press("Escape")
    pg.locator("#topActions .save-arrow").click()
    check(
        "sem espaço: Salvar não oferece o espaço",
        pg.locator(".menu .menu-item", has_text="Salvar no espaço").count() == 0,
    )
    pg.keyboard.press("Escape")

    folder = Path(tempfile.mkdtemp(prefix="conferir-espaco-"))
    try:
        pg.locator(".top-menu", has_text="Arquivo").click()
        pg.locator(".menu .menu-item", has_text="Espaços da equipe").click()
        dlg = pg.locator("dialog[open][aria-label='Espaços da equipe']")
        dlg.wait_for()
        dlg.locator("input[aria-label='Seu nome no espaço']").fill("Ana Souza")
        dlg.locator("button", has_text="Criar espaço").click()
        ask = pg.locator("dialog[open][aria-label='Pasta do espaço da equipe']")
        ask.locator("input").fill(str(folder))
        ask.locator("input").press("Enter")
        name = pg.locator("dialog[open][aria-label='Nome do espaço']")
        name.locator("input[aria-label='Nome do espaço']").fill("Equipe de teste")
        name.locator("input[aria-label='Nome do espaço']").press("Enter")
        pg.wait_for_selector("dialog[open] .team-space", timeout=10000)
        check("cria o espaço na pasta", (folder / "_equipe" / "espaco.json").is_file())
        check(
            "o espaço aparece com o papel de quem criou",
            "Administrador" in pg.locator("dialog[open] .team-space").first.inner_text(),
        )
        pg.keyboard.press("Escape")

        new_flow(pg)
        pg.evaluate("() => window.__A.addNode('prep.select', 200, 200)")
        save_named(pg, "Fluxo da equipe")
        pg.locator("#topActions .save-arrow").click()
        pg.locator(".menu .menu-item", has_text="Salvar no espaço").click()
        pg.wait_for_timeout(600)
        wid = pg.evaluate("() => window.__S.store.workflow.id")
        badge = pg.locator("#fileBadge").inner_text()
        check(
            f"salvo no espaço, com o selo ({badge!r})",
            (folder / f"{wid}.prodata.json").is_file() and "Equipe de teste" in badge,
        )
        pg.evaluate("() => window.__S.mutate((wf) => { wf.description = 'mudou no espaço'; })")
        pg.keyboard.press("Control+s")
        pg.wait_for_function("() => !window.__S.isDirty()", timeout=10000)
        check(
            "Salvar de novo grava no espaço",
            "mudou no espaço" in (folder / f"{wid}.prodata.json").read_text(encoding="utf-8"),
        )
        check(
            "na pasta, só o fluxo e a assinatura (nada de amostra ou resultado)",
            {p.name for p in folder.iterdir()}
            == {"_equipe", f"{wid}.prodata.json", f"{wid}.prodata.json.sig"},
        )

        pg.locator(".top-menu", has_text="Arquivo").click()
        pg.locator(".menu .menu-item", has_text="Abrir da biblioteca").click()
        lib = pg.locator("dialog[open]")
        lib.locator(".team-tabs").wait_for()
        lib.locator(".team-tabs .segment", has_text="Equipe de teste").click()
        lib.locator(".wf-item", has_text="Fluxo da equipe").wait_for(timeout=10000)
        check(
            "a biblioteca ganha a aba do espaço, com o fluxo",
            lib.locator(".wf-item", has_text="Fluxo da equipe").count() == 1,
        )
        pg.keyboard.press("Escape")

        pg.reload()
        ready(pg)
        check(
            "a aba do espaço volta ao reabrir",
            pg.locator(".wf-tab[title*='espaço Equipe de teste']").count() >= 1,
        )

        # Marco 2: membros e assinaturas (RF-4711..4718)
        pg.locator(".top-menu", has_text="Arquivo").click()
        pg.locator(".menu .menu-item", has_text="Espaços da equipe").click()
        spaces = pg.locator("dialog[open][aria-label='Espaços da equipe']")
        spaces.locator(".team-space .team-chip", has_text="Administrador").wait_for(timeout=10000)
        check(
            "quem cria o espaço é administrador",
            spaces.locator(".team-chip", has_text="Administrador").count() == 1,
        )
        spaces.locator("button", has_text="Membros").click()
        members = pg.locator("dialog[open][aria-label='Membros · Equipe de teste']")
        members.locator(".team-member").first.wait_for(timeout=10000)
        text = members.inner_text()
        check(
            "Membros mostra a Ana e avisa que só há um administrador",
            "Ana Souza" in text and "Só há um administrador" in text,
            text,
        )
        check("Membros explica como o espaço fica seguro", members.locator(".team-help").count() == 1)
        pg.keyboard.press("Escape")
        pg.keyboard.press("Escape")

        path = folder / f"{wid}.prodata.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["name"] = "Adulterado por fora"
        path.write_text(json.dumps(data), encoding="utf-8")
        pg.reload()
        pg.wait_for_function("() => document.querySelectorAll('.wf-tab').length > 0", timeout=90000)
        pg.locator(".wf-tab[title*='espaço Equipe de teste']").first.click()
        banner = pg.locator(".trust-banner")
        banner.wait_for(timeout=10000)
        check(
            "fluxo mudado fora do programa abre protegido, com o motivo",
            "alterado fora do programa" in banner.inner_text(),
            banner.inner_text(),
        )
    finally:
        shutil.rmtree(folder, ignore_errors=True)


# ---------------------------------------------------------------- spec 047: duas pessoas (marco 3)

POST = """async ([url, body]) => { const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body) }); const j = await r.json(); if (!r.ok) throw new Error(JSON.stringify(j)); return j; }"""
PUT = """async ([url, body]) => { const r = await fetch(url, { method: 'PUT', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body) }); if (!r.ok) throw new Error(await r.text()); return r.json(); }"""
TEAM_FLOW = {"id": "fluxo_time", "name": "Fluxo do time", "edges": [],
             "nodes": [{"id": "n1", "type": "prep.select", "x": 200, "y": 160, "config": {}}]}  # fmt: skip


def open_space_flow(pg: Page, space_name: str, flow_name: str) -> None:
    pg.locator(".top-menu", has_text="Arquivo").click()
    pg.locator(".menu .menu-item", has_text="Abrir da biblioteca").click()
    lib = pg.locator("dialog[open]")
    lib.locator(".team-tabs .segment", has_text=space_name).click()
    lib.locator(".wf-item", has_text=flow_name).locator(".wf-main").click()


def node_x(pg: Page) -> float:
    return float(pg.evaluate("() => window.__S.store.workflow.nodes[0].x"))


def equipe2(pg: Page) -> None:
    folder = Path(tempfile.mkdtemp(prefix="conferir-espaco2-"))
    ctx2 = pg.context.browser.new_context(viewport={"width": 1500, "height": 950})  # type: ignore[union-attr]
    bruno = ctx2.new_page()
    try:
        pg.evaluate(POST, ["/api/equipe/identidade", {"nome": "Ana Souza"}])
        sid = pg.evaluate(
            POST, ["/api/equipe/espacos", {"acao": "criar", "caminho": str(folder), "nome": "Time"}]
        )["id"]
        pg.evaluate(PUT, [f"/api/equipe/espacos/{sid}/fluxos/fluxo_time", TEAM_FLOW])
        ready(bruno, URL_BRUNO)
        bruno.evaluate(POST, ["/api/equipe/identidade", {"nome": "Bruno Lima"}])
        joined = bruno.evaluate(POST, ["/api/equipe/espacos", {"acao": "entrar", "caminho": str(folder)}])
        check("Bruno entra como pedido", joined["papel"] is None and joined["pedido"])
        pg.evaluate(
            POST,
            [
                f"/api/equipe/espacos/{sid}/membros",
                {"acao": "aceitar", "usuario": "bruno", "papel": "editor"},
            ],
        )

        open_space_flow(pg, "Time", "Fluxo do time")
        pg.wait_for_function("() => window.__S.store.workflow?.id === 'fluxo_time'", timeout=10000)
        check("Ana abre para editar (sem faixa)", pg.locator(".readonly-bar").count() == 0)

        bruno.locator(".top-menu", has_text="Arquivo").click()
        bruno.locator(".menu .menu-item", has_text="Abrir da biblioteca").click()
        lib = bruno.locator("dialog[open]")
        lib.locator(".team-tabs .segment", has_text="Time").click()
        item = lib.locator(".wf-item", has_text="Fluxo do time")
        item.wait_for(timeout=10000)
        check(
            "a biblioteca do Bruno mostra que a Ana está editando",
            "Ana Souza" in item.inner_text(),
            item.inner_text(),
        )
        item.locator(".wf-main").click()
        conflict = bruno.locator("dialog[open][aria-label='Este fluxo está sendo editado']")
        conflict.wait_for(timeout=10000)
        check("Bruno é avisado: Ana está editando", "Ana Souza está editando" in conflict.inner_text())
        conflict.locator("button", has_text="Abrir só para ver").click()
        bar = bruno.locator(".readonly-bar")
        bar.wait_for(timeout=10000)
        check("abre só para ver, com a faixa", "Aberto só para ver" in bar.inner_text())
        before = node_x(bruno)
        box = bruno.locator(".node[data-id='n1'] .node-card").bounding_box()
        assert box is not None
        bruno.mouse.move(box["x"] + 40, box["y"] + 20)
        bruno.mouse.down()
        bruno.mouse.move(box["x"] + 240, box["y"] + 120, steps=8)
        bruno.mouse.up()
        check("só para ver: arrastar não move a caixa", node_x(bruno) == before)
        bruno.keyboard.press("Control+s")
        bruno.wait_for_timeout(400)
        check(
            "só para ver: Salvar não grava", "nada para salvar" in bruno.locator(".toast").last.inner_text()
        )

        pg.locator(".wf-tab.active .wf-tab-close").click()  # Ana fecha o fluxo: a marca é solta
        pg.wait_for_timeout(800)
        bar.locator("button", has_text="Editar").click()
        bruno.wait_for_selector(".readonly-bar", state="detached", timeout=10000)
        check("Bruno passa a editar quando fica livre", bruno.locator(".readonly-bar").count() == 0)
        box = bruno.locator(".node[data-id='n1'] .node-card").bounding_box()
        assert box is not None
        bruno.mouse.move(box["x"] + 40, box["y"] + 20)
        bruno.mouse.down()
        bruno.mouse.move(box["x"] + 240, box["y"] + 120, steps=8)
        bruno.mouse.up()
        bruno.keyboard.press("Control+s")
        bruno.wait_for_function("() => !window.__S.isDirty()", timeout=10000)
        saved = json.loads((folder / "fluxo_time.prodata.json").read_text(encoding="utf-8"))
        check(
            "editando, a mudança do Bruno vai para o espaço",
            saved["nodes"][0]["x"] != TEAM_FLOW["nodes"][0]["x"],
        )

        pg.evaluate(
            POST,
            [f"/api/equipe/espacos/{sid}/membros", {"acao": "papel", "usuario": "bruno", "papel": "leitor"}],
        )
        bruno.locator(".wf-tab.active .wf-tab-close").click()
        bruno.wait_for_timeout(500)
        open_space_flow(bruno, "Time", "Fluxo do time")
        bar = bruno.locator(".readonly-bar")
        bar.wait_for(timeout=10000)
        check(
            "Leitor abre só para ver, sem botão Editar",
            "Leitor" in bar.inner_text() and bar.locator("button").count() == 0,
            bar.inner_text(),
        )
    finally:
        ctx2.close()
        shutil.rmtree(folder, ignore_errors=True)


# ---------------------------------------------------------------- spec 047: duas pessoas (marco 4)

SQL_FLOW = {"id": "fluxo_sql", "name": "Fluxo com SQL", "edges": [],
            "nodes": [{"id": "n1", "type": "prep.select", "x": 200, "y": 160, "config": {}},
                      {"id": "q1", "type": "transform.sql_query", "x": 520, "y": 160,
                       "config": {"sql": "SELECT 1"}}]}  # fmt: skip


def bruno_saves(bruno: Page, sid: str, x: int = 200, sql: str = "SELECT 1") -> None:
    body = json.loads(json.dumps(SQL_FLOW))
    body["nodes"][0]["x"] = x
    body["nodes"][1]["config"]["sql"] = sql
    bruno.evaluate(PUT, [f"/api/equipe/espacos/{sid}/fluxos/fluxo_sql", body])


def equipe3(pg: Page) -> None:
    folder = Path(tempfile.mkdtemp(prefix="conferir-espaco3-"))
    ctx2 = pg.context.browser.new_context(viewport={"width": 1500, "height": 950})  # type: ignore[union-attr]
    bruno = ctx2.new_page()
    try:
        pg.evaluate(POST, ["/api/equipe/identidade", {"nome": "Ana Souza"}])
        sid = pg.evaluate(
            POST, ["/api/equipe/espacos", {"acao": "criar", "caminho": str(folder), "nome": "Time 4"}]
        )["id"]
        pg.evaluate(PUT, [f"/api/equipe/espacos/{sid}/fluxos/fluxo_sql", SQL_FLOW])
        ready(bruno, URL_BRUNO)
        bruno.evaluate(POST, ["/api/equipe/identidade", {"nome": "Bruno Lima"}])
        bruno.evaluate(POST, ["/api/equipe/espacos", {"acao": "entrar", "caminho": str(folder)}])
        pg.evaluate(
            POST,
            [
                f"/api/equipe/espacos/{sid}/membros",
                {"acao": "aceitar", "usuario": "bruno", "papel": "editor"},
            ],
        )

        # Conflito: Bruno salva enquanto a Ana edita (RF-4761)
        open_space_flow(pg, "Time 4", "Fluxo com SQL")
        pg.wait_for_function("() => window.__S.store.workflow?.id === 'fluxo_sql'", timeout=10000)
        bruno_saves(bruno, sid, x=420)
        pg.evaluate("() => window.__S.mutate((wf) => { wf.description = 'da Ana'; })")
        pg.keyboard.press("Control+s")
        dlg = pg.locator("dialog[open][aria-label='Outra pessoa salvou este fluxo']")
        dlg.wait_for(timeout=10000)
        check(
            "salvar por cima do colega avisa e não sobrescreve",
            "Bruno Lima salvou enquanto você editava" in dlg.inner_text()
            and "da Ana" not in (folder / "fluxo_sql.prodata.json").read_text(encoding="utf-8"),
            dlg.inner_text(),
        )
        dlg.locator("button", has_text="Ver as duas").click()
        versions = pg.locator("dialog[open] .ver-list")
        versions.locator(".ver-item").first.wait_for(timeout=10000)
        text = versions.inner_text()
        check(
            "Versões anteriores mostra as duas, com o autor",
            "Bruno Lima" in text and "Ana Souza" in text and "outra pessoa editava" in text,
            text,
        )
        pg.keyboard.press("Escape")
        pg.keyboard.press("Control+s")
        dlg.wait_for(timeout=10000)
        dlg.locator("button", has_text="Abrir a do colega").click()
        pg.wait_for_function("() => window.__S.store.workflow.nodes[0].x === 420", timeout=10000)
        check("Abrir a do colega troca pela versão dele", not pg.evaluate("() => window.__S.isDirty()"))

        # Recarregar: Bruno salva de novo com o fluxo aberto na Ana (RF-4733)
        bruno_saves(bruno, sid, x=640)
        news = pg.locator(".news-bar")
        news.wait_for(timeout=40000)  # a tela confere a cada 30 s
        check(
            "a faixa avisa a versão nova do colega", "Bruno Lima salvou uma versão nova" in news.inner_text()
        )
        news.locator("button", has_text="Recarregar").click()
        pg.wait_for_function("() => window.__S.store.workflow.nodes[0].x === 640", timeout=10000)
        check("Recarregar traz a versão nova", pg.locator(".news-bar").count() == 0)

        # Atualizado por e confiança por diferença (RF-4732, RF-4741, CA-06)
        pg.locator(".wf-tab.active .wf-tab-close").click()
        pg.wait_for_timeout(500)
        bruno_saves(bruno, sid, x=640, sql="SELECT * FROM clientes")
        open_space_flow(pg, "Time 4", "Fluxo com SQL")
        news.wait_for(timeout=10000)
        check(
            "ao abrir: Atualizado por Bruno",
            "Atualizado por Bruno Lima" in news.inner_text(),
            news.inner_text(),
        )
        banner = pg.locator(".trust-banner")
        banner.wait_for(timeout=10000)
        check(
            "mudança sensível: conferir só o que mudou",
            banner.locator(".trust-item").count() == 1
            and "SQL" in banner.inner_text()
            and banner.locator("button", has_text="Conferir e confiar").count() == 1,
            banner.inner_text(),
        )
        banner.locator("button", has_text="Conferir e confiar").click()
        pg.wait_for_selector(".trust-banner", state="detached", timeout=10000)
        check("depois de conferir, o fluxo fica liberado", pg.locator(".trust-banner").count() == 0)
    finally:
        ctx2.close()
        shutil.rmtree(folder, ignore_errors=True)


# ---------------------------------------------------------------- spec 047: versão oficial e agendamentos (marco 5)


def equipe4(pg: Page) -> None:
    """Publicar como oficial, selo na biblioteca, agendar um fluxo do espaço (sem criar tarefa no Windows) e a lista
    de agendamentos do time."""
    folder = Path(tempfile.mkdtemp(prefix="conferir-espaco4-"))
    try:
        pg.evaluate(POST, ["/api/equipe/identidade", {"nome": "Ana Souza"}])
        sid = pg.evaluate(
            POST, ["/api/equipe/espacos", {"acao": "criar", "caminho": str(folder), "nome": "Time 5"}]
        )["id"]
        pg.evaluate(PUT, [f"/api/equipe/espacos/{sid}/fluxos/fluxo_time", TEAM_FLOW])
        pg.reload()  # a tela conhece o espaço novo e o papel
        ready(pg)
        open_space_flow(pg, "Time 5", "Fluxo do time")
        pg.wait_for_function("() => window.__S.store.workflow?.id === 'fluxo_time'", timeout=10000)
        pg.locator("#topActions .save-arrow").click()
        pg.locator(".menu .menu-item", has_text="Publicar como oficial").click()
        pg.locator(".toast", has_text="versão oficial").first.wait_for(timeout=10000)
        check(
            "Publicar como oficial grava a versão assinada",
            (folder / "_equipe" / "oficiais" / "fluxo_time.prodata.json.sig").is_file(),
        )
        pg.locator(".top-menu", has_text="Arquivo").click()
        pg.locator(".menu .menu-item", has_text="Abrir da biblioteca").click()
        lib = pg.locator("dialog[open]")
        lib.locator(".team-tabs .segment", has_text="Time 5").click()
        item = lib.locator(".wf-item", has_text="Fluxo do time")
        item.locator(".team-chip", has_text="Oficial").wait_for(timeout=10000)
        check("a biblioteca mostra o selo de oficial", "Oficial" in item.inner_text(), item.inner_text())
        pg.keyboard.press("Escape")

        pg.locator(".top-menu", has_text="Arquivo").click()
        pg.locator(".menu .menu-item", has_text="Agendar este fluxo").click()
        dlg = pg.locator("dialog[open]", has_text="Agendar")
        dlg.locator(".sch-sentence").wait_for(timeout=10000)
        pg.wait_for_function(
            "() => !document.querySelector('dialog[open] .sch-sentence').textContent.includes('…')",
            timeout=10000,
        )
        text = dlg.inner_text()
        check(
            "agendar fluxo do espaço explica que roda a versão oficial",
            "versão oficial do espaço" in text,
            text[:300],
        )
        dlg.locator("button", has_text="Cancelar").click()  # nada é criado no Agendador do Windows

        pg.locator(".top-menu", has_text="Arquivo").click()
        pg.locator(".menu .menu-item", has_text="Espaços da equipe").click()
        spaces = pg.locator("dialog[open][aria-label='Espaços da equipe']")
        spaces.locator(".team-space", has_text="Time 5").locator("button", has_text="Agendamentos").click()
        team = pg.locator("dialog[open][aria-label='Agendamentos · Time 5']")
        team.locator(".ver-empty").wait_for(timeout=10000)
        check(
            "Agendamentos do time abre, com a explicação",
            "Nenhum fluxo do espaço está agendado" in team.inner_text() and "assumir" in team.inner_text(),
            team.inner_text(),
        )
        pg.keyboard.press("Escape")
        pg.keyboard.press("Escape")
    finally:
        shutil.rmtree(folder, ignore_errors=True)


# ---------------------------------------------------------------- spec 048: definições da equipe (marco 2)

FETCH = "async (url) => (await fetch(url)).json()"
META_FLOW = {"id": "fluxo_meta", "name": "Fluxo da meta", "edges": [{"id": "e", "source": "t", "target": "f"}],
             "nodes": [{"id": "t", "type": "io.text_input", "x": 160, "y": 160,
                        "config": {"table": {"columns": ["v"], "rows": [[2]]}}},
                       {"id": "f", "type": "prep.formula", "x": 460, "y": 160, "config": {"formulas": [
                           {"target": "new", "column": "x", "type": "Auto", "expression": "[v] * [#meta]"}]}}]}  # fmt: skip


def equipe5(pg: Page) -> None:
    folder = Path(tempfile.mkdtemp(prefix="conferir-espaco5-"))
    ctx2 = pg.context.browser.new_context(viewport={"width": 1500, "height": 950})  # type: ignore[union-attr]
    bruno = ctx2.new_page()
    try:
        pg.evaluate(POST, ["/api/equipe/identidade", {"nome": "Ana Souza"}])
        sid = pg.evaluate(
            POST, ["/api/equipe/espacos", {"acao": "criar", "caminho": str(folder), "nome": "Time 6"}]
        )["id"]
        pg.evaluate(POST, ["/api/constants", {"constant": {"name": "meta", "type": "number", "value": "50"}}])
        conn = {
            "id": "erp",
            "name": "ERP",
            "kind": "postgres",
            "host": "srv-erp",
            "database": "erp",
            "user": "ana",
        }
        pg.evaluate(PUT, ["/api/connections/erp", {"connection": conn, "password": "senha-da-ana"}])
        pg.reload()
        ready(pg)
        pg.locator("#viewSwitch .segment[data-view=data]").click()
        pg.locator(".dv-list").get_by_text("meta", exact=True).first.click()
        pg.locator(".dv-head-actions button", has_text="Compartilhar com a equipe").click()
        pick = pg.locator("dialog[open]", has_text="Compartilhar com a equipe")
        if pick.count():
            pick.locator(".wf-item", has_text="Time 6").locator(".wf-main").click()
        pg.locator(".toast", has_text="Compartilhada com a equipe").first.wait_for(timeout=10000)
        check(
            "Compartilhar com a equipe leva a constante para o espaço",
            (folder / "_equipe" / "definicoes" / "constantes" / "meta.json").is_file(),
        )
        pg.evaluate(
            POST, [f"/api/equipe/espacos/{sid}/definicoes/compartilhar", {"tipo": "conexoes", "id": "erp"}]
        )
        text = "".join(p.read_text(encoding="utf-8") for p in (folder / "_equipe").rglob("*") if p.is_file())
        check("a senha não vai para a pasta da equipe", "senha-da-ana" not in text)
        pg.evaluate(PUT, [f"/api/equipe/espacos/{sid}/fluxos/fluxo_meta", META_FLOW])

        ready(bruno, URL_BRUNO)
        bruno.evaluate(POST, ["/api/equipe/identidade", {"nome": "Bruno Lima"}])
        bruno.evaluate(POST, ["/api/equipe/espacos", {"acao": "entrar", "caminho": str(folder)}])
        pg.evaluate(
            POST,
            [
                f"/api/equipe/espacos/{sid}/membros",
                {"acao": "aceitar", "usuario": "bruno", "papel": "editor"},
            ],
        )
        bruno.reload()
        ready(bruno, URL_BRUNO)
        bruno.locator("#viewSwitch .segment[data-view=data]").click()
        section = bruno.locator(".team-defs-space", has_text="Da equipe · Time 6")
        section.wait_for(timeout=15000)
        check(
            "a vista Dados do Bruno mostra o que é da equipe",
            "meta" in section.inner_text() and "ERP" in section.inner_text(),
            section.inner_text(),
        )
        check(
            "a conexão pede a senha do Bruno",
            section.locator(".team-def-item", has_text="ERP")
            .locator(".team-chip", has_text="Sua senha")
            .count()
            == 1,
        )
        section.locator(".team-def-item", has_text="ERP").click()
        bruno.locator(".dv-head-actions button", has_text="Digitar a minha senha").click()
        dialog = bruno.locator("dialog[open]", has_text="Sua senha")
        dialog.locator("input[type=password]").fill("senha-do-bruno")
        dialog.locator("button", has_text="Guardar").click()
        bruno.locator(".dv-head-actions button", has_text="Trocar a minha senha").wait_for(timeout=10000)
        check(
            "a senha do Bruno fica no computador dele",
            "senha-do-bruno"
            not in "".join(
                p.read_text(encoding="utf-8") for p in (folder / "_equipe").rglob("*") if p.is_file()
            ),
        )

        open_space_flow(bruno, "Time 6", "Fluxo da meta")
        bruno.wait_for_function(
            "() => window.__S.store.workflow?.id === 'fluxo_meta' && !window.__S.store.running", timeout=20000
        )
        bruno.wait_for_timeout(800)
        rows = bruno.evaluate(FETCH, "/api/results/fluxo_meta/f/out").get("rows", [])
        check(
            "o fluxo do espaço usa a constante da equipe (sem cadastro no Bruno)",
            bool(rows) and rows[0].get("x") == 100,
            rows[:1],
        )

        # Comentários nas caixas (spec 048, marco 3)
        versions_before = len(list((folder / "_equipe" / "versoes").glob("fluxo_meta/*.json")))
        bruno.locator("#viewSwitch .segment[data-view=designer]").click()
        bruno.locator(".node[data-id='f'] .node-card").click(button="right")
        bruno.locator(".menu .menu-item", has_text="Comentar").click()
        panel = bruno.locator(".cm-panel")
        panel.wait_for(timeout=10000)
        panel.locator("textarea").fill("Por que multiplica pela meta?")
        panel.locator("button", has_text="Enviar").click()
        bruno.wait_for_timeout(1500)
        toasts = bruno.locator(".toast").all_inner_texts()
        check("enviar o comentário não dá erro", not any("Não foi possível" in t for t in toasts), toasts)
        bruno.locator(".node[data-id='f'] .node-comments").wait_for(timeout=10000)
        check(
            "comentar põe o selo na caixa",
            bruno.locator(".node[data-id='f'] .node-comments").inner_text().strip() == "1",
        )
        check(
            "comentar não cria versão do fluxo",
            len(list((folder / "_equipe" / "versoes").glob("fluxo_meta/*.json"))) == versions_before,
        )
        pg.locator("#viewSwitch .segment[data-view=designer]").click()
        open_space_flow(pg, "Time 6", "Fluxo da meta")
        conflict = pg.locator("dialog[open][aria-label='Este fluxo está sendo editado']")
        conflict.wait_for(timeout=10000)
        conflict.locator("button", has_text="Abrir só para ver").click()
        chip = pg.locator(".cm-chip")
        chip.wait_for(timeout=15000)
        check("a Ana vê o comentário novo", "1 novo" in chip.inner_text(), chip.inner_text())
        chip.click()
        thread = pg.locator(".cm-panel .cm-thread").first
        thread.wait_for(timeout=10000)
        check(
            "a conversa mostra quem comentou",
            "Bruno Lima" in thread.inner_text() and "meta" in thread.inner_text(),
        )
        thread.locator("button", has_text="Responder").click()
        thread.locator("textarea").fill("É a meta do trimestre, da equipe.")
        thread.locator("button", has_text="Enviar").click()
        pg.locator(".cm-panel .cm-msg.reply").wait_for(timeout=10000)
        pg.locator(".cm-panel .cm-thread").first.locator("button", has_text="Resolver").click()
        pg.locator(".cm-panel .cm-done").wait_for(timeout=10000)
        check("resolvido sai do selo da caixa", pg.locator(".node[data-id='f'] .node-comments").count() == 0)
    except Exception:
        bruno.screenshot(
            path=str(Path(tempfile.gettempdir()) / "conferir-equipe5-bruno.png")
        )  # a outra pessoa
        raise
    finally:
        ctx2.close()
        shutil.rmtree(folder, ignore_errors=True)


# ---------------------------------------------------------------- spec 048: juntar caixa por caixa (marco 4)


def equipe6(pg: Page) -> None:
    folder = Path(tempfile.mkdtemp(prefix="conferir-espaco6-"))
    ctx2 = pg.context.browser.new_context(viewport={"width": 1500, "height": 950})  # type: ignore[union-attr]
    bruno = ctx2.new_page()
    try:
        pg.evaluate(POST, ["/api/equipe/identidade", {"nome": "Ana Souza"}])
        sid = pg.evaluate(
            POST, ["/api/equipe/espacos", {"acao": "criar", "caminho": str(folder), "nome": "Time 7"}]
        )["id"]
        pg.evaluate(PUT, [f"/api/equipe/espacos/{sid}/fluxos/fluxo_sql", SQL_FLOW])
        ready(bruno, URL_BRUNO)
        bruno.evaluate(POST, ["/api/equipe/identidade", {"nome": "Bruno Lima"}])
        bruno.evaluate(POST, ["/api/equipe/espacos", {"acao": "entrar", "caminho": str(folder)}])
        pg.evaluate(
            POST,
            [
                f"/api/equipe/espacos/{sid}/membros",
                {"acao": "aceitar", "usuario": "bruno", "papel": "editor"},
            ],
        )

        # Caixas diferentes: entra tudo sozinho
        open_space_flow(pg, "Time 7", "Fluxo com SQL")
        pg.wait_for_function(
            "() => window.__S.store.workflow?.id === 'fluxo_sql' && !window.__S.store.running", timeout=20000
        )
        bruno_saves(bruno, sid, sql="SELECT 2")  # Bruno muda a caixa SQL
        pg.evaluate("() => window.__S.mutate((wf) => { wf.nodes[0].label = 'Colunas da Ana'; })")
        pg.keyboard.press("Control+s")
        dlg = pg.locator("dialog[open][aria-label='Outra pessoa salvou este fluxo']")
        dlg.wait_for(timeout=10000)
        dlg.locator("button", has_text="Juntar as duas").click()
        merge = pg.locator("dialog[open]", has=pg.locator(".mg-layout"))
        merge.locator(".mg-summary").wait_for(timeout=10000)
        check(
            "juntar: caixas diferentes entram sozinhas, sem perguntar",
            "2 mudanças juntadas" in merge.inner_text() and merge.locator(".mg-conflict").count() == 0,
            merge.inner_text()[:300],
        )
        merge.locator("button", has_text="Aplicar").click()
        merge.wait_for(
            state="detached", timeout=10000
        )  # o Aplicar terminou (o fluxo já estava com mudanças não salvas)
        pg.wait_for_function(
            "() => window.__S.store.workflow.nodes[1].config.sql === 'SELECT 2'", timeout=10000
        )
        joined = pg.evaluate(
            "() => window.__S.store.workflow.nodes.map((n) => [n.label || '', n.config.sql || ''])"
        )
        check(
            "o resultado tem as duas mudanças",
            ["Colunas da Ana", ""] in joined and ["", "SELECT 2"] in joined,
            joined,
        )
        pg.keyboard.press("Control+s")
        pg.wait_for_function("() => !window.__S.isDirty()", timeout=10000)
        check(
            "depois de juntar, Salvar grava sem novo conflito",
            pg.locator("dialog[open][aria-label='Outra pessoa salvou este fluxo']").count() == 0,
        )

        # A mesma caixa: escolher
        bruno_saves(bruno, sid, sql="SELECT 3")
        pg.evaluate("() => window.__S.mutate((wf) => { wf.nodes[1].config.sql = 'SELECT 4'; })")
        pg.keyboard.press("Control+s")
        dlg.wait_for(timeout=10000)
        dlg.locator("button", has_text="Juntar as duas").click()
        merge.locator(".mg-conflict").first.wait_for(timeout=10000)
        check("a mesma caixa nos dois: a janela pergunta só essa", merge.locator(".mg-conflict").count() == 1)
        merge.locator(".mg-option", has_text="A de Bruno Lima").click()
        merge.locator("button", has_text="Aplicar").click()
        pg.wait_for_function(
            "() => window.__S.store.workflow.nodes[1].config.sql === 'SELECT 3'", timeout=10000
        )
        check("a escolha vale: ficou a do Bruno", True)
        pg.keyboard.press("Control+z")
        check(
            "Desfazer volta ao de antes de juntar",
            pg.evaluate("() => window.__S.store.workflow.nodes[1].config.sql") == "SELECT 4",
        )
    except Exception:
        bruno.screenshot(path=str(Path(tempfile.gettempdir()) / "conferir-equipe6-bruno.png"))
        raise
    finally:
        ctx2.close()
        shutil.rmtree(folder, ignore_errors=True)


# ---------------------------------------------------------------- spec 048: recomendações de limpeza (marco 5)


def limpeza(pg: Page) -> None:
    new_flow(pg)
    node_id = pg.evaluate("""() => window.__A.addNode('io.text_input', 200, 200, { table: { columns: ['uf', 'valor'],
      rows: [['SP', '10'], ['sp', 'N/D'], ['RJ', '30'], ['MG', '40'], ['RJ', '50']] } }).id""")
    run(pg)
    dot = pg.locator(f".node[data-id='{node_id}'] .node-cleaning")
    dot.wait_for(timeout=15000)
    check("a caixa de entrada ganha o ponto de limpeza", dot.count() == 1)
    dot.click()
    card = pg.locator(".cl-card")
    card.wait_for(timeout=15000)
    text = card.inner_text()
    check(
        "o Perfil mostra as recomendações",
        "parece número" in text and "N/D" in text and "maiúsculas" in text,
        text[:300],
    )
    before = pg.evaluate("() => window.__S.store.workflow.nodes.length")
    card.locator(".cl-item", has_text="parece número").locator("button", has_text="Corrigir").click()
    confirm = pg.locator("dialog[open]", has_text="Inserir")
    confirm.wait_for(timeout=10000)
    check(
        "Corrigir mostra antes o que muda",
        "N/D" in confirm.inner_text() and "→" in confirm.inner_text(),
        confirm.inner_text()[:200],
    )
    confirm.locator("button", has_text="Inserir").click()
    pg.wait_for_function(f"() => window.__S.store.workflow.nodes.length === {before + 1}", timeout=10000)
    added = pg.evaluate("() => window.__S.store.workflow.nodes.at(-1)")
    check(
        "insere o Select com a troca de tipo, ligado depois da caixa",
        added["type"] == "prep.select"
        and added["config"]["fields"][0]["cast"] in ("Int64", "Float64")
        and pg.evaluate(
            f"() => window.__S.store.workflow.edges.some((e) => e.source === '{node_id}' && e.target === '{added['id']}')"
        ),
        added,
    )
    pg.keyboard.press("Control+z")
    check(
        "Desfazer tira a caixa inserida",
        pg.evaluate("() => window.__S.store.workflow.nodes.length") == before,
    )
    dot.click()
    card.wait_for(timeout=15000)
    card.locator(".cl-item", has_text="maiúsculas").locator("button", has_text="Ignorar").click()
    ignored = pg.evaluate(f"() => window.__S.store.workflow.ignored_cleaning?.['{node_id}'] || []")
    check("Ignorar fica gravado no fluxo", ignored == ["caixa:uf"], ignored)


# ---------------------------------------------------------------- spec 049: dados públicos do Brasil


def _print(pg: Page, name: str) -> None:
    shot = Path(tempfile.gettempdir()) / f"conferir-catalogo-{name}.png"
    pg.screenshot(path=str(shot))
    print(f"      print: {shot}")


def catalogo(pg: Page) -> None:
    pg.locator("#viewSwitch .segment", has_text="Dados").click()
    pg.locator(".dv-list-head button", has_text="Adicionar").click()
    pg.locator(".menu .menu-item", has_text="Dados públicos do Brasil").click()
    dlg = pg.locator("dialog.pd-dialog[open]")
    dlg.wait_for(timeout=15000)
    dlg.locator(".pd-card").first.wait_for(timeout=20000)
    menu = dlg.locator(".pd-menu").inner_text()
    check(
        "o menu tem destaques, categorias e portais",
        all(
            t in menu
            for t in ("Destaques", "Economia e juros", "Território", "Empresas (CNPJ)", "ANEEL", "Recife")
        ),
        menu[:300],
    )
    check(
        "os destaques aparecem como cartões com o selo Pronto",
        "Pronto" in dlg.locator(".pd-card").first.inner_text(),
    )
    _print(pg, "abertura")
    dlg.locator(".pd-search input").fill("municipios")
    pg.wait_for_timeout(900)
    first = dlg.locator(".pd-card h3").first.inner_text()
    check("a busca sem acento acha Municípios do Brasil primeiro", first == "Municípios do Brasil", first)
    dlg.locator(".pd-search input").fill("")
    dlg.locator(".pd-menu-item", has_text="Território").click()
    pg.wait_for_timeout(700)
    check(
        "a categoria Território mostra 3 fontes",
        dlg.locator(".pd-card").count() == 3,
        dlg.locator(".pd-card").count(),
    )
    dlg.locator(".pd-card").first.click()
    check("o detalhe abre ao lado", dlg.locator(".pd-detail h2").inner_text() != "")
    star = dlg.locator(".pd-card").first.locator(".pd-star")
    star.click()
    pg.wait_for_timeout(400)
    dlg.locator(".pd-menu-item", has_text="Favoritos").click()
    pg.wait_for_timeout(700)
    check("a estrela leva a fonte para Favoritos", dlg.locator(".pd-card").count() == 1)
    # O catálogo dos órgãos é lido direto da fonte, em segundo plano, ao abrir pela primeira vez (RF-4933).
    for _ in range(240):  # evaluate espera a promessa; wait_for_function trataria a promessa como "pronto"
        if not pg.evaluate(
            "() => fetch('/api/catalogo/atualizar').then((r) => r.json()).then((s) => s.rodando)"
        ):
            break
        pg.wait_for_timeout(1000)
    pg.wait_for_timeout(1500)
    dlg.locator(".pd-menu-item", has_text="ANEEL").click()
    dlg.locator(".pd-card").first.wait_for(timeout=20000)
    check(
        "o portal da ANEEL lista conjuntos com Leitura automática",
        "Leitura automática" in dlg.locator(".pd-card").first.inner_text(),
    )
    _print(pg, "portal")
    # T08: o detalhe de um destaque, com a prévia lida na hora e as colunas explicadas.
    dlg.locator(".pd-menu-item", has_text="Economia e juros").click()
    dlg.locator(".pd-card", has_text="Taxa Selic meta").click()
    detail = dlg.locator(".pd-detail")
    detail.locator(".pd-table tbody tr").first.wait_for(timeout=30000)
    text = detail.inner_text()
    check("o detalhe diz o último dado e a licença", "Último dado" in text and "Licença" in text, text[-400:])
    check("nada de null escrito no detalhe", "null" not in text, text[:200])
    detail.locator(".pd-table").scroll_into_view_if_needed()
    check("a prévia de um destaque já vem lida", detail.locator(".pd-table tbody tr").count() >= 5)
    check(
        "Adicionar não pede prévia num destaque Pronto",
        not detail.locator(".pd-actions .pd-why").count()
        or "Chega" in detail.locator(".pd-actions button").first.get_attribute("title"),
    )
    # T11: a situação do órgão, conferida ao abrir, com Conferir de novo e a barra de 30 dias.
    detail.locator(".pd-health").wait_for(timeout=15000)
    pg.wait_for_function(
        "() => !document.querySelector('.pd-health.is-nao_conferido') || document.querySelector('.pd-offline')",
        timeout=30000,
    )
    health_text = detail.locator(".pd-health").inner_text()
    check(
        "o detalhe diz se o Banco Central está no ar",
        any(t in health_text for t in ("No ar", "Lenta", "Fora do ar")),
        health_text,
    )
    check("a barra tem os 30 dias", detail.locator(".pd-day").count() == 30)
    check("os pontos de situação aparecem no menu", dlg.locator(".pd-menu .pd-dot").count() >= 5)
    detail.locator(".pd-health button", has_text="Conferir de novo").click()
    pg.wait_for_timeout(500)
    detail.locator(".pd-health button", has_text="Conferir de novo").wait_for(timeout=20000)
    check("Conferir de novo atualiza a hora", "conferido agora" in detail.locator(".pd-health").inner_text())
    _print(pg, "detalhe")
    # Um conjunto de portal: escolher o arquivo abre a prévia obrigatória.
    dlg.locator(".pd-menu-item", has_text="CVM").click()
    dlg.locator(".pd-card").first.wait_for(timeout=20000)
    dlg.locator(".pd-card").first.click()
    detail.locator(".pd-files").wait_for(timeout=30000)
    check(
        "Adicionar fica travado até escolher o arquivo",
        "Escolha um arquivo" in detail.locator(".pd-actions").inner_text(),
    )
    detail.locator(".pd-file button", has_text="Usar este").first.click()
    detail.locator(".pd-must .pd-table, .pd-must .pd-note-err").first.wait_for(timeout=120000)
    check(
        "a prévia obrigatória mostra a tabela lida do portal",
        detail.locator(".pd-must .pd-table tbody tr").count() > 0,
        detail.locator(".pd-must").inner_text()[:300],
    )
    _print(pg, "arquivo")
    # T09a: Editar feriados, com um município que não é capital (CA-10).
    dlg.locator(".pd-menu-item", has_text="Calendário").click()
    dlg.locator(".pd-card", has_text="Feriados").first.click()
    detail.locator("button", has_text="Editar feriados").click()
    editor = pg.locator("dialog.hol-dialog[open]")
    editor.locator(".hol-row").first.wait_for(timeout=15000)
    local = editor.locator(".hol-top input").first
    local.fill("3509502")
    local.press("Tab")
    editor.locator(".hol-row", has_text="Revolução Constitucionalista").wait_for(timeout=15000)
    check(
        "Campinas mostra o 9 de julho de São Paulo", editor.locator(".hol-row", has_text="09/07").count() >= 1
    )
    editor.locator("button", has_text="Incluir feriado").click()
    editor.locator(".hol-form input").first.fill("Nossa Senhora da Conceição")
    editor.locator(".hol-rule input.input").fill("08/12")
    editor.locator(".hol-form button", has_text="Incluir").click()
    mine = editor.locator(".hol-row", has_text="Nossa Senhora da Conceição")
    mine.wait_for(timeout=15000)
    check("o feriado incluído aparece como Seu", "Seu" in mine.inner_text(), mine.inner_text())
    check("nada de null escrito no editor", "null" not in editor.inner_text())
    _print(pg, "feriados")
    editor.locator("header button").click()


def caixa_publica(pg: Page) -> None:
    """T12: do catálogo para o fluxo, executar, o cartão do Configurar e Trocar."""
    new_flow(pg)
    pg.locator("#viewSwitch .segment", has_text="Dados").click()
    pg.locator(".dv-list-head button", has_text="Adicionar").click()
    pg.locator(".menu .menu-item", has_text="Dados públicos do Brasil").click()
    dlg = pg.locator("dialog.pd-dialog[open]")
    dlg.locator(".pd-card").first.wait_for(timeout=20000)
    dlg.locator(".pd-card", has_text="Taxa Selic diária").click()
    detail = dlg.locator(".pd-detail")
    add = detail.locator(".pd-actions button", has_text="Adicionar ao fluxo")
    add.wait_for(timeout=20000)
    pg.wait_for_function(
        "() => { const b = [...document.querySelectorAll('.pd-actions button')].find((x) => x.textContent.includes('Adicionar ao fluxo')); return b && !b.disabled; }",
        timeout=30000,
    )
    add.click()
    pg.wait_for_function(
        "() => window.__S.store.workflow.nodes.some((n) => n.type === 'io.public_data')", timeout=10000
    )
    node = pg.evaluate("() => window.__S.store.workflow.nodes.find((n) => n.type === 'io.public_data')")
    check(
        "a caixa entra no fluxo com a fonte e as escolhas",
        node["config"]["fonte"]["id"] == "bcb.sgs/11"
        and node["config"]["fonte"]["escolhas"]["periodo"]["kind"] == "ultimos_anos",
        node["config"],
    )
    check("o fluxo não guarda endereço nem dados", "http" not in json.dumps(node["config"]))
    run(pg)
    status = pg.evaluate(f"() => window.__S.store.execution?.node_results?.['{node['id']}']?.status")
    check("a caixa executa lendo do Banco Central", status in ("executed", "cached"), status)
    configure(pg, node["id"])
    card = pg.locator(".pd-box")
    card.wait_for(timeout=10000)
    check(
        "o Configurar mostra a fonte em palavras",
        "Taxa Selic diária" in card.inner_text() and "últimos 5 anos" in card.inner_text(),
        card.inner_text(),
    )
    _print(pg, "caixa")
    card.locator("button", has_text="Trocar").click()
    dlg.wait_for(timeout=10000)
    dlg.locator(".pd-detail h2").wait_for(timeout=20000)
    check(
        "Trocar abre o catálogo na mesma fonte",
        "Taxa Selic diária" in dlg.locator(".pd-detail h2").inner_text(),
    )
    check(
        "o botão diz Usar nesta caixa",
        dlg.locator(".pd-actions button", has_text="Usar nesta caixa").count() == 1,
    )
    dlg.locator("header button").first.click()


def pasta_publica(pg: Page) -> None:
    """T13: À vista Dados, a pasta Dados públicos, Usar no fluxo e o aviso Dados novos (na vista e na caixa)."""
    new_flow(pg)
    pg.locator("#viewSwitch .segment", has_text="Dados").click()
    pg.locator(".dv-list-head button", has_text="Adicionar").click()
    pg.locator(".menu .menu-item", has_text="Dados públicos do Brasil").click()
    dlg = pg.locator("dialog.pd-dialog[open]")
    dlg.locator(".pd-card").first.wait_for(timeout=20000)
    dlg.locator(".pd-card", has_text="Taxa Selic diária").click()
    pg.wait_for_function(
        "() => { const b = [...document.querySelectorAll('.pd-actions button')].find((x) => x.textContent.includes('À vista Dados')); return b && !b.disabled; }",
        timeout=30000,
    )
    dlg.locator(".pd-actions button", has_text="À vista Dados").click()
    folder = pg.locator(".pd-saved")
    folder.wait_for(timeout=10000)
    check(
        "a pasta Dados públicos aparece na vista Dados",
        "Taxa Selic diária" in folder.inner_text(),
        folder.inner_text(),
    )
    head = pg.locator(".dv-detail .dv-head")
    head.wait_for(timeout=10000)
    check("o detalhe abre na fonte guardada", "Taxa Selic diária" in head.inner_text() and "Ainda não usada" in head.inner_text(),
          head.inner_text())  # fmt: skip
    facts = pg.locator(".pd-saved-facts").inner_text()
    # Ainda não lida, ou a data da leitura quando outra conferência já leu a mesma consulta neste servidor.
    read = "ainda não lida" in facts or bool(
        re.search(r"Última leitura neste computador\s+\d{2}/\d{2}/\d{4}", facts)
    )
    check("o detalhe diz as escolhas e a última leitura", "últimos 5 anos" in facts and read, facts)
    _print(pg, "pasta")
    head.locator("button", has_text="Usar no fluxo").click()
    pg.wait_for_function(
        "() => window.__S.store.view === 'designer' && window.__S.store.workflow.nodes.some((n) => n.type === 'io.public_data')",
        timeout=10000,
    )
    node_id = pg.evaluate("() => window.__S.store.workflow.nodes.find((n) => n.type === 'io.public_data').id")
    run(pg)
    check(
        "sem novidade, a caixa não tem o aviso",
        pg.locator(f".node[data-id='{node_id}'] .node-news").count() == 0,
    )
    # O órgão "publica" dados mais novos que a leitura (o que a conferência do catálogo gravaria).
    tomorrow = time.strftime("%Y-%m-%d", time.localtime(time.time() + 86400))
    (DATA / "catalogo" / "novidades.json").write_text(json.dumps({"bcb.sgs/11": {
        "atualizado": tomorrow, "rotulo": "último dado em", "conferido_em": time.strftime("%Y-%m-%dT%H:%M:%S")}}), encoding="utf-8")  # fmt: skip
    pg.evaluate("() => import('/static/js/public_news.js').then((m) => m.refreshNodeNews())")
    badge = pg.locator(f".node[data-id='{node_id}'] .node-news")
    badge.wait_for(timeout=10000)
    check("a caixa ganha o aviso Dados novos", "Dados novos" in badge.inner_text() and "a última leitura vai até" in (badge.get_attribute("title") or ""),
          badge.get_attribute("title"))  # fmt: skip
    _print(pg, "dados-novos-caixa")
    save_named(pg, "Selic com aviso")
    pg.locator("#viewSwitch .segment", has_text="Dados").click()
    item = pg.locator(".pd-saved .team-def-item", has_text="Taxa Selic diária")
    item.locator(".pd-news-chip").wait_for(timeout=10000)
    item.click()
    note = pg.locator(".pd-news-note")
    note.wait_for(timeout=10000)
    check(
        "a vista Dados mostra o aviso e o que muda",
        "próxima execução" in note.inner_text(),
        note.inner_text(),
    )
    pg.wait_for_function(
        "() => document.querySelector('.dv-detail .dv-head')?.textContent.includes('Usada em 1 fluxo')",
        timeout=10000,
    )
    check("o detalhe mostra onde é usada", pg.locator(".dv-detail .dv-lanes").count() == 1)
    # A conferência que começou ao abrir o catálogo leva alguns segundos; a pasta se atualiza quando ela termina.
    with contextlib.suppress(Exception):  # se não chegar, a conferência abaixo diz o que apareceu
        pg.wait_for_function(
            "() => /No ar|Lenta/.test(document.querySelector('.dv-detail .pd-saved-health')?.textContent || '')",
            timeout=30000,
        )
    health = pg.locator(".dv-detail .pd-saved-health").inner_text()
    check(
        "o detalhe mostra a situação do órgão, conferida ao abrir o catálogo",
        health in ("No ar", "Lenta"),
        health,
    )
    _print(pg, "dados-novos-vista")
    pg.locator(".dv-detail .dv-head button", has_text="Tirar da vista Dados").click()
    confirm = pg.locator("dialog[open]")
    check(
        "tirar avisa que o fluxo continua funcionando",
        "continuam funcionando" in confirm.inner_text(),
        confirm.inner_text(),
    )
    confirm.locator("button", has_text="Tirar da vista Dados").click()
    pg.wait_for_function("() => !document.querySelector('.pd-saved')", timeout=10000)
    check("a pasta some quando fica vazia", pg.locator(".pd-saved").count() == 0)


# ---------------------------------------------------------------- spec 046, E: pílula deslizante

PILL = """() => { const p = document.querySelector('#viewSwitch .seg-pill').getBoundingClientRect();
  const b = document.querySelector('#viewSwitch .segment[aria-selected=true]').getBoundingClientRect();
  return Math.abs(p.left - b.left) + Math.abs(p.width - b.width); }"""


def pilula(pg: Page, reduced: bool = False) -> None:
    label = "com reduzir movimento" if reduced else "normal"
    pg.wait_for_timeout(500)
    check(f"[{label}] pílula parada na vista atual", pg.evaluate(PILL) < 1.5)
    pg.locator("#viewSwitch .segment[data-view=dashboard]").click()
    pg.wait_for_timeout(70)
    moving = pg.evaluate(PILL) > 3
    check(f"[{label}] {'troca instantânea' if reduced else 'desliza no meio do caminho'}", moving != reduced)
    pg.wait_for_timeout(350)
    check(f"[{label}] chega ao Dashboard", pg.evaluate(PILL) < 1.5)


CHECKS: dict[str, Callable[[Page], None]] = {
    "salvar": salvar, "versoes": versoes, "fio": fio, "fonte": fonte, "erros": erros, "pilula": pilula,
    "equipe": equipe,
    "equipe2": equipe2,
    "equipe3": equipe3,
    "equipe4": equipe4,
    "equipe5": equipe5,
    "equipe6": equipe6,
    "limpeza": limpeza,
    "catalogo": catalogo,
    "caixa_publica": caixa_publica,
    "pasta_publica": pasta_publica,
}  # fmt: skip

# ---------------------------------------------------------------- servidor e navegador


def start_server(data: Path, port: int = PORT, user: str = "ana") -> subprocess.Popen[bytes]:
    env = {
        **os.environ,
        "PRODATA_USUARIO": user,  # identidade de teste (spec 047): cada servidor é uma pessoa
        "PRODATA_PORT": str(port),
        "PRODATA_STORAGE_DIR": str(data),
        "PRODATA_SECRETS_BACKEND": "memory",
    }
    uv = shutil.which("uv") or "uv"
    quiet = subprocess.DEVNULL
    server = subprocess.Popen([uv, "run", "prodata"], cwd=ROOT, env=env, stdout=quiet, stderr=quiet)  # noqa: S603
    for _ in range(120):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health")
            return server
        except OSError:
            time.sleep(1)
    raise SystemExit("O servidor não subiu em 2 minutos.")


def stop_server(server: subprocess.Popen[bytes]) -> None:
    if sys.platform == "win32":  # o uv abre um processo filho: derruba a árvore inteira
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(server.pid)], capture_output=True, check=False)  # noqa: S603, S607
    else:
        server.terminate()


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # acentos certos no console do Windows
        getattr(stream, "reconfigure", lambda **_: None)(encoding="utf-8", errors="replace")
    chosen = sys.argv[1:] or list(CHECKS)
    unknown = [c for c in chosen if c not in CHECKS]
    if unknown:
        print(f"Conferência desconhecida: {', '.join(unknown)}. Use: {', '.join(CHECKS)}.")
        return 2
    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="conferir-tela-") as folder:
        global DATA
        DATA = Path(folder) / "dados"
        server = start_server(DATA)
        # Duas pessoas (spec 047): o Bruno tem o próprio servidor, pasta de dados e usuário.
        second = (
            start_server(Path(folder) / "dados-bruno", PORT_BRUNO, "bruno")
            if {"equipe2", "equipe3", "equipe5", "equipe6"} & set(chosen)
            else None
        )
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome", headless=True)
                runs: list[tuple[str, Callable[[Page], None], dict[str, Any]]] = [
                    (c, CHECKS[c], {}) for c in chosen
                ]
                if "pilula" in chosen:
                    runs.append(("pilula", lambda pg: pilula(pg, reduced=True), {"reduced_motion": "reduce"}))
                for name, fn, options in runs:
                    print(f"== {name}")
                    ctx = browser.new_context(viewport={"width": 1500, "height": 950}, **options)
                    pg = ctx.new_page()
                    pg.on("pageerror", lambda e, n=name: errors.append(f"{n}: {e}"))
                    try:
                        ready(pg)
                        fn(pg)
                    except Exception as exc:  # uma conferência quebrada não impede as outras
                        shot = Path(tempfile.gettempdir()) / f"conferir-{name}.png"
                        pg.screenshot(path=str(shot))  # a tela no momento da falha, para entender o que houve
                        detail = f"{type(exc).__name__}: {str(exc).splitlines()[0]} (tela em {shot})"
                        check(f"{name} rodou até o fim", False, detail)
                    ctx.close()
                browser.close()
        finally:
            stop_server(server)
            if second is not None:
                stop_server(second)
    check("nenhum erro de JavaScript na página", not errors, errors[:3])
    print(
        f"{check.total - check.failed}/{check.total} conferências"
        + (f", {check.failed} falha(s)" if check.failed else "")
    )
    return 1 if check.failed else 0


if __name__ == "__main__":
    sys.exit(main())
