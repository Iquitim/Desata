"""Capturas da 0.9.5 (spec 048): recomendações de limpeza, definições da equipe, comentários e Juntar as duas.

Como na 0.9.4, a Ana usa o servidor de prints e o Bruno ganha um segundo servidor, com a mesma pasta do espaço dentro
da pasta temporária dos prints. Nenhuma senha de verdade: a do exemplo existe só nesta geração.
"""

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from novas_094 import POST, PUT, URL_BRUNO, _open_space_flow, _quiet, _ready, _start_bruno, _wait_flow

SQL_FLOW = {"id": "carteira", "name": "Carteira por estado", "edges": [{"id": "e1", "source": "clientes", "target": "total"}],
            "nodes": [{"id": "clientes", "type": "io.text_input", "label": "Clientes", "x": 140, "y": 200,
                       "config": {"table": {"columns": ["uf", "valor"], "rows": [["SP", "120"], ["RJ", "80"], ["MG", "60"]]}}},
                      {"id": "total", "type": "transform.sql_query", "label": "Total por estado", "x": 480, "y": 200,
                       "config": {"sql": "SELECT uf, SUM(CAST(valor AS DOUBLE)) AS total FROM input_1 GROUP BY uf"}}]}  # fmt: skip


def part_095(pg: Any, tmp: Path, shot: Callable[..., None]) -> None:
    _cleaning(pg, shot)
    folder = tmp / f"Equipe-{int(time.time() * 1000)}"
    folder.mkdir()
    server = _start_bruno(tmp / f"dados-bruno-{folder.name}")
    scheme = pg.evaluate("() => matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'")
    ctx = pg.context.browser.new_context(
        viewport={"width": 1600, "height": 1000}, device_scale_factor=2, color_scheme=scheme
    )
    bruno = ctx.new_page()
    try:
        _team(pg, bruno, folder, shot)
    finally:
        ctx.close()
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(server.pid)], capture_output=True, check=False)  # noqa: S603, S607


def _cleaning(pg: Any, shot: Callable[..., None]) -> None:
    pg.get_by_role("button", name="Arquivo").first.click()
    pg.get_by_role("menuitem", name="Novo fluxo").click()
    pg.wait_for_timeout(600)
    node_id = pg.evaluate("""() => window.__A.addNode('io.text_input', 200, 220, { table: { columns: ['uf', 'valor'],
      rows: [['SP', '1200'], ['sp', 'N/D'], ['RJ', '830'], ['MG', '610'], ['RJ', '450'], ['PR', '320']] } }).id""")
    pg.evaluate("() => import('/static/js/canvas_state.js').then((CS) => CS.state.handlers.run())")
    pg.wait_for_selector(f".node[data-id='{node_id}'] .node-cleaning", timeout=30000)
    pg.locator(f".node[data-id='{node_id}'] .node-cleaning").click()
    card = pg.locator(".cl-card")
    card.wait_for(timeout=20000)
    pg.wait_for_timeout(500)
    _quiet(pg)
    shot(card, "limpeza-perfil")


def _team(pg: Any, bruno: Any, folder: Path, shot: Callable[..., None]) -> None:
    pg.evaluate(POST, ["/api/equipe/identidade", {"nome": "Ana Souza"}])
    sid = pg.evaluate(
        POST, ["/api/equipe/espacos", {"acao": "criar", "caminho": str(folder), "nome": "Comercial"}]
    )["id"]
    conn = {
        "id": "erp",
        "name": "ERP de vendas",
        "kind": "postgres",
        "host": "srv-erp",
        "database": "vendas",
        "user": "ana",
    }
    pg.evaluate(PUT, ["/api/connections/erp", {"connection": conn, "password": "exemplo"}])
    pg.evaluate(
        POST,
        ["/api/constants", {"constant": {"name": "meta_comercial", "type": "number", "value": "250000"}}],
    )
    for tipo, key in (("conexoes", "erp"), ("constantes", "meta_comercial")):
        pg.evaluate(POST, [f"/api/equipe/espacos/{sid}/definicoes/compartilhar", {"tipo": tipo, "id": key}])
    pg.evaluate(PUT, [f"/api/equipe/espacos/{sid}/fluxos/carteira", SQL_FLOW])
    _ready(bruno, URL_BRUNO)
    bruno.evaluate(POST, ["/api/equipe/identidade", {"nome": "Bruno Lima"}])
    bruno.evaluate(POST, ["/api/equipe/espacos", {"acao": "entrar", "caminho": str(folder)}])
    pg.evaluate(
        POST,
        [f"/api/equipe/espacos/{sid}/membros", {"acao": "aceitar", "usuario": "bruno", "papel": "editor"}],
    )

    # Definições da equipe, na vista Dados do Bruno, e o pedido da senha dele
    bruno.reload()
    _ready(bruno, URL_BRUNO)
    bruno.locator("#viewSwitch .segment[data-view=data]").click()
    item = bruno.locator(".team-defs-space .team-def-item", has_text="ERP de vendas")
    item.wait_for(timeout=20000)
    item.scroll_into_view_if_needed()
    item.click()
    bruno.locator(".dv-head-actions button", has_text="Digitar a minha senha").wait_for(timeout=10000)
    bruno.wait_for_timeout(500)
    item.scroll_into_view_if_needed()
    _quiet(bruno)
    shot(bruno, "equipe-definicoes")
    bruno.locator(".dv-head-actions button", has_text="Digitar a minha senha").click()
    dialog = bruno.locator("dialog[open]", has_text="Sua senha")
    dialog.wait_for(timeout=10000)
    bruno.wait_for_timeout(300)
    _quiet(bruno)
    shot(dialog, "equipe-senha")
    bruno.keyboard.press("Escape")

    # Comentário do Bruno; a Ana responde
    bruno.locator("#viewSwitch .segment[data-view=designer]").click()
    _open_space_flow(bruno, "Comercial", "Carteira por estado")
    _wait_flow(bruno, "carteira")
    bruno.evaluate(POST, [f"/api/equipe/espacos/{sid}/fluxos/carteira/comentarios",
                          {"tipo": "comentario", "caixa": "total", "rotulo": "Total por estado",
                           "texto": "Esse total já desconta as devoluções do mês?"}])  # fmt: skip
    bruno.locator(".wf-tab.active .wf-tab-close").click()
    bruno.wait_for_timeout(600)
    pg.reload()
    _ready(pg, pg.url)
    _open_space_flow(pg, "Comercial", "Carteira por estado")
    _wait_flow(pg, "carteira")
    pg.locator(".cm-chip").wait_for(timeout=20000)
    pg.locator(".node[data-id='total'] .node-comments").click()
    thread = pg.locator(".cm-panel .cm-thread").first
    thread.wait_for(timeout=10000)
    thread.locator("button", has_text="Responder").click()
    thread.locator("textarea").fill(
        "Ainda não: entra na versão de dezembro, junto com o filtro de devoluções."
    )
    thread.locator("button", has_text="Enviar").click()
    pg.locator(".cm-panel .cm-msg.reply").wait_for(timeout=10000)
    pg.wait_for_timeout(600)
    _quiet(pg)
    shot(pg, "equipe-comentarios")
    pg.locator(".cm-panel button[aria-label='Fechar os comentários']").click()

    # Juntar as duas: Bruno muda o SQL e o nome da entrada; a Ana também muda o SQL
    theirs = json.loads(json.dumps(SQL_FLOW))
    theirs["nodes"][0]["label"] = "Clientes ativos"
    theirs["nodes"][1]["config"]["sql"] = (
        "SELECT uf, SUM(CAST(valor AS DOUBLE)) AS total FROM input_1 WHERE valor <> '' GROUP BY uf"
    )
    bruno.evaluate(PUT, [f"/api/equipe/espacos/{sid}/fluxos/carteira", theirs])
    pg.evaluate(
        "() => window.__S.mutate((wf) => { wf.nodes[1].config.sql = 'SELECT uf, COUNT(*) AS clientes, SUM(CAST(valor AS DOUBLE)) AS total FROM input_1 GROUP BY uf'; })"
    )
    pg.keyboard.press("Control+s")
    pg.locator(
        "dialog[open][aria-label='Outra pessoa salvou este fluxo'] button", has_text="Juntar as duas"
    ).click()
    merge = pg.locator("dialog[open]", has=pg.locator(".mg-layout"))
    merge.locator(".mg-conflict").first.wait_for(timeout=15000)
    pg.wait_for_timeout(800)
    _quiet(pg)
    shot(merge, "equipe-juntar")
    pg.keyboard.press("Escape")
