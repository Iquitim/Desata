"""Conferências da tela no navegador, como uma pessoa usando o programa (antes de cada versão).

    uv run --with playwright python scripts/conferir_tela.py            # todas
    uv run --with playwright python scripts/conferir_tela.py fio versoes  # só algumas

Sobe o próprio servidor, com uma pasta de dados temporária (nada vai para a biblioteca de ninguém), abre o Chrome sem
janela e confere o comportamento de ponta a ponta: o que os testes do motor não enxergam (cliques, arrastos, diálogos,
animações). Sai com 1 se alguma conferência falhar ou se a página tiver erro de JavaScript.

Conferências: salvar (spec 045), versoes, fio, fonte, erros e pilula (spec 046).
"""

from __future__ import annotations

import os
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


def ready(pg: Page) -> None:
    pg.goto(URL)
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
}  # fmt: skip

# ---------------------------------------------------------------- servidor e navegador


def start_server(data: Path) -> subprocess.Popen[bytes]:
    env = {
        **os.environ,
        "PRODATA_PORT": str(PORT),
        "PRODATA_STORAGE_DIR": str(data),
        "PRODATA_SECRETS_BACKEND": "memory",
    }
    uv = shutil.which("uv") or "uv"
    quiet = subprocess.DEVNULL
    server = subprocess.Popen([uv, "run", "prodata"], cwd=ROOT, env=env, stdout=quiet, stderr=quiet)  # noqa: S603
    for _ in range(120):
        try:
            urllib.request.urlopen(URL + "api/health")  # noqa: S310
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
        server = start_server(Path(folder) / "dados")
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
                        check(
                            f"{name} rodou até o fim",
                            False,
                            f"{type(exc).__name__}: {str(exc).splitlines()[0]}",
                        )
                    ctx.close()
                browser.close()
        finally:
            stop_server(server)
    check("nenhum erro de JavaScript na página", not errors, errors[:3])
    print(
        f"{check.total - check.failed}/{check.total} conferências"
        + (f", {check.failed} falha(s)" if check.failed else "")
    )
    return 1 if check.failed else 0


if __name__ == "__main__":
    sys.exit(main())
