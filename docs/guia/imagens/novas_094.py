"""Capturas da 0.9.4 (spec 047): o espaço da equipe, com duas pessoas de exemplo.

A Ana usa o servidor de prints de sempre; o Bruno ganha um segundo servidor, com a própria pasta de dados e o próprio
usuário, apontando para a mesma pasta do espaço (dentro da pasta temporária dos prints). Nada aqui cria tarefa no
Agendador do Windows: a lista de agendamentos do time é preenchida pela própria página, com dados de exemplo.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
PORT_BRUNO = 8798
EXAMPLE_PATH = "\\\\servidor\\equipes\\Controladoria"  # mostrado no print no lugar da pasta temporária
URL_BRUNO = f"http://127.0.0.1:{PORT_BRUNO}/"

POST = """async ([url, body]) => { const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body) }); const j = await r.json(); if (!r.ok) throw new Error(JSON.stringify(j)); return j; }"""
PUT = """async ([url, body]) => { const r = await fetch(url, { method: 'PUT', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body) }); if (!r.ok) throw new Error(await r.text()); return r.json(); }"""

SALES = {
    "columns": ["uf", "valor"],
    "rows": [["SP", "1200"], ["RJ", "830"], ["MG", "610"], ["SP", "-40"], ["PR", "450"]],
}


def _closing(
    sql: str = "SELECT uf, SUM(valor) AS total FROM input_1 GROUP BY uf ORDER BY total DESC", x: int = 120
) -> dict[str, Any]:
    return {
        "id": "fechamento_mensal",
        "name": "Fechamento mensal",
        "nodes": [
            {"id": "vendas", "type": "io.text_input", "label": "Vendas do mês", "x": x, "y": 200, "config": {"table": SALES}},
            {"id": "validas", "type": "prep.filter", "label": "Só vendas válidas", "x": x + 300, "y": 200,
             "config": {"mode": "expression", "expression": "ToNumber([valor]) > 0"}},
            {"id": "por_uf", "type": "transform.sql_query", "label": "Total por estado", "x": x + 600, "y": 200,
             "config": {"sql": sql}},
        ],
        "edges": [{"id": "e1", "source": "vendas", "target": "validas"}, {"id": "e2", "source": "validas", "sourceHandle": "T", "target": "por_uf"}],
    }  # fmt: skip


CLIENTS = {
    "id": "carteira_clientes",
    "name": "Carteira de clientes",
    "nodes": [
        {"id": "c", "type": "io.text_input", "label": "Clientes", "x": 120, "y": 200,
         "config": {"table": {"columns": ["cliente", "uf"], "rows": [["Alfa", "SP"], ["Beta", "RJ"]]}}},
        {"id": "s", "type": "prep.select", "x": 420, "y": 200, "config": {}},
    ],
    "edges": [{"id": "e1", "source": "c", "target": "s"}],
}  # fmt: skip


def _schedules(space_id: str) -> dict[str, Any]:
    """Agendamentos de exemplo para a lista do time (a página não cria tarefa nenhuma)."""
    base = {"espaco": space_id, "pausado": False, "atualizado_em": "2026-11-23T09:00:00Z", "confere": True}
    return {"papel": "administrador", "agendamentos": [
        {**base, "id": "1a2b3c4d", "fluxo": "fechamento_mensal", "fluxo_nome": "Fechamento mensal",
         "frase": "De segunda a sexta às 06:00", "proxima": "2026-11-24T06:00:00", "usuario": "ana", "nome": "Ana Souza",
         "maquina": "NOTE-ANA", "meu": True, "substituido_por": None,
         "ultima": {"finished_at": "2026-11-23T06:00:41", "status": "ok", "message": ""}},
        {**base, "id": "5e6f7a8b", "fluxo": "carteira_clientes", "fluxo_nome": "Carteira de clientes",
         "frase": "Todo dia 1 do mês às 07:30", "proxima": "2026-12-01T07:30:00", "usuario": "bruno", "nome": "Bruno Lima",
         "maquina": "NOTE-BRUNO", "meu": False, "substituido_por": None,
         "ultima": {"finished_at": "2026-11-01T07:30:12", "status": "refused",
                    "message": "A versão oficial não confere: salve e publique de novo."}},
    ]}  # fmt: skip


def _start_bruno(data: Path) -> subprocess.Popen[bytes]:
    env = {**os.environ, "PRODATA_USUARIO": "bruno", "PRODATA_PORT": str(PORT_BRUNO), "PRODATA_STORAGE_DIR": str(data),
           "PRODATA_SECRETS_BACKEND": "memory"}  # fmt: skip
    server = subprocess.Popen([shutil.which("uv") or "uv", "run", "prodata"], cwd=ROOT, env=env,  # noqa: S603
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # fmt: skip
    for _ in range(120):
        try:
            urllib.request.urlopen(URL_BRUNO + "api/health")  # noqa: S310
            return server
        except OSError:
            time.sleep(1)
    raise SystemExit("O servidor do Bruno não subiu em 2 minutos.")


def _ready(pg: Any, url: str) -> None:
    pg.goto(url)
    pg.wait_for_function("() => document.querySelector('#canvas') && window.fetch", timeout=90000)
    pg.wait_for_timeout(1500)
    pg.evaluate("async () => { window.__S = await import('/static/js/store.js'); }")


def _quiet(pg: Any) -> None:
    pg.evaluate(
        "() => document.querySelectorAll('.toast, .canvas-hint, .bi-hover, .run-notice').forEach((e) => e.remove())"
    )


def _open_space_flow(pg: Any, space: str, flow: str) -> None:
    pg.locator(".top-menu", has_text="Arquivo").click()
    pg.locator(".menu .menu-item", has_text="Abrir da biblioteca").click()
    lib = pg.locator("dialog[open]")
    lib.locator(".team-tabs .segment", has_text=space).click()
    lib.locator(".wf-item", has_text=flow).locator(".wf-main").click()


def _wait_flow(pg: Any, wid: str) -> None:
    pg.wait_for_function(
        f"() => window.__S.store.workflow?.id === '{wid}' && !window.__S.store.running", timeout=60000
    )
    pg.wait_for_timeout(1200)


def part_094(pg: Any, tmp: Path, shot: Callable[..., None]) -> None:
    folder = tmp / f"Controladoria-{int(time.time() * 1000)}"
    folder.mkdir()
    server = _start_bruno(tmp / f"dados-bruno-{folder.name}")
    ctx = pg.context.browser.new_context(viewport={"width": 1600, "height": 1000}, device_scale_factor=2,
                                         color_scheme=pg.evaluate("() => matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'"))  # fmt: skip
    bruno = ctx.new_page()
    try:
        _scenario(pg, bruno, folder, shot)
    finally:
        ctx.close()
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(server.pid)], capture_output=True, check=False)  # noqa: S603, S607


def _scenario(pg: Any, bruno: Any, folder: Path, shot: Callable[..., None]) -> None:
    pg.evaluate(POST, ["/api/equipe/identidade", {"nome": "Ana Souza"}])
    sid = pg.evaluate(
        POST, ["/api/equipe/espacos", {"acao": "criar", "caminho": str(folder), "nome": "Controladoria"}]
    )["id"]
    for flow in (_closing(), CLIENTS):
        pg.evaluate(PUT, [f"/api/equipe/espacos/{sid}/fluxos/{flow['id']}", flow])
    pg.evaluate(POST, [f"/api/equipe/espacos/{sid}/fluxos/fechamento_mensal/oficial", {}])
    _ready(bruno, URL_BRUNO)
    bruno.evaluate(POST, ["/api/equipe/identidade", {"nome": "Bruno Lima"}])
    bruno.evaluate(POST, ["/api/equipe/espacos", {"acao": "entrar", "caminho": str(folder)}])

    # Espaços da equipe e o pedido de entrada do Bruno
    pg.reload()
    _ready(pg, pg.url)
    pg.locator(".top-menu", has_text="Arquivo").click()
    pg.locator(".menu .menu-item", has_text="Espaços da equipe").click()
    spaces = pg.locator("dialog[open][aria-label='Espaços da equipe']")
    spaces.locator(".team-space .team-chip", has_text="Administrador").wait_for(timeout=15000)
    pg.wait_for_timeout(400)
    _quiet(pg)
    # a pasta temporária dos prints traz o usuário do Windows: no print, um caminho de exemplo
    pg.evaluate(
        "(p) => document.querySelectorAll('.team-space .wf-desc').forEach((e) => { e.textContent = p; })",
        EXAMPLE_PATH,
    )
    shot(spaces, "equipe-espacos")
    spaces.locator(".team-space", has_text="Controladoria").locator("button", has_text="Membros").click()
    members = pg.locator("dialog[open][aria-label='Membros · Controladoria']")
    members.locator(".team-member.request").wait_for(timeout=15000)
    pg.wait_for_timeout(400)
    _quiet(pg)
    shot(members, "equipe-membros")
    pg.keyboard.press("Escape")
    pg.keyboard.press("Escape")
    pg.evaluate(
        POST,
        [f"/api/equipe/espacos/{sid}/membros", {"acao": "aceitar", "usuario": "bruno", "papel": "editor"}],
    )

    # Ana edita; Bruno é avisado e abre só para ver
    _open_space_flow(pg, "Controladoria", "Fechamento mensal")
    _wait_flow(pg, "fechamento_mensal")
    bruno.reload()
    _ready(bruno, URL_BRUNO)
    _open_space_flow(bruno, "Controladoria", "Fechamento mensal")
    conflict = bruno.locator("dialog[open][aria-label='Este fluxo está sendo editado']")
    conflict.wait_for(timeout=15000)
    bruno.wait_for_timeout(400)
    _quiet(bruno)
    shot(conflict, "equipe-editando")
    conflict.locator("button", has_text="Abrir só para ver").click()
    _wait_flow(bruno, "fechamento_mensal")
    bruno.locator(".readonly-bar").wait_for(timeout=15000)
    bruno.evaluate("() => window.__S.select('por_uf')")
    bruno.wait_for_timeout(600)
    _quiet(bruno)
    shot(bruno, "equipe-so-ver")

    # Bruno muda a consulta SQL (parte sensível); Ana abre de novo e confere só isso
    pg.locator(".wf-tab.active .wf-tab-close").click()
    pg.wait_for_timeout(800)
    bruno.locator(".wf-tab.active .wf-tab-close").click()
    bruno.wait_for_timeout(500)
    sql = "SELECT uf, SUM(valor) AS total, COUNT(*) AS vendas FROM input_1 GROUP BY uf ORDER BY total DESC"
    bruno.evaluate(PUT, [f"/api/equipe/espacos/{sid}/fluxos/fechamento_mensal", _closing(sql)])
    _open_space_flow(pg, "Controladoria", "Fechamento mensal")
    pg.wait_for_function("() => window.__S.store.workflow?.id === 'fechamento_mensal'", timeout=30000)
    pg.locator(".news-bar").wait_for(timeout=15000)
    pg.locator(".trust-banner").wait_for(timeout=15000)
    pg.wait_for_timeout(800)
    _quiet(pg)
    shot(pg, "equipe-atualizado")
    pg.locator(".trust-banner button", has_text="Conferir e confiar").click()
    pg.wait_for_selector(".trust-banner", state="detached", timeout=15000)
    pg.locator(".news-bar button[aria-label='Fechar o aviso']").click()

    # Conflito: Bruno salva enquanto a Ana edita
    bruno.evaluate(PUT, [f"/api/equipe/espacos/{sid}/fluxos/fechamento_mensal", _closing(sql, x=160)])
    pg.evaluate("() => window.__S.mutate((wf) => { wf.description = 'Fechamento com a meta do trimestre'; })")
    pg.keyboard.press("Control+s")
    dialog = pg.locator("dialog[open][aria-label='Outra pessoa salvou este fluxo']")
    dialog.wait_for(timeout=15000)
    pg.wait_for_timeout(400)
    _quiet(pg)
    shot(dialog, "equipe-conflito")
    dialog.locator("button", has_text="Ver as duas").click()
    versions = pg.locator("dialog[open]", has=pg.locator(".ver-list"))
    versions.locator(".ver-preview").wait_for(timeout=15000)
    versions.locator(".ver-item", has_text="Bruno Lima").first.click()  # a versão do colega, com o que muda
    pg.wait_for_timeout(600)
    pg.wait_for_timeout(800)
    _quiet(pg)
    shot(versions, "equipe-versoes")
    pg.keyboard.press("Escape")

    # Agendamentos do time (dados de exemplo: nenhuma tarefa é criada no Windows)
    pg.route(f"**/api/equipe/espacos/{sid}/agendamentos", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps(_schedules(sid))))  # fmt: skip
    pg.locator(".top-menu", has_text="Arquivo").click()
    pg.locator(".menu .menu-item", has_text="Espaços da equipe").click()
    spaces = pg.locator("dialog[open][aria-label='Espaços da equipe']")
    spaces.locator(".team-space", has_text="Controladoria").locator("button", has_text="Agendamentos").click()
    team = pg.locator("dialog[open][aria-label='Agendamentos · Controladoria']")
    team.locator(".team-member").first.wait_for(timeout=15000)
    pg.wait_for_timeout(400)
    _quiet(pg)
    shot(team, "equipe-agendamentos")
    pg.keyboard.press("Escape")
    pg.keyboard.press("Escape")
