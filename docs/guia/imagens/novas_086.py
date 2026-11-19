"""Capturas da 0.8.6 (spec 040): datas ("Você quis dizer…" e o calendário do Filter) e o fluxo em outro computador."""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

NODES = """
wf.nodes.push(
  { id: 'x86_f', type: 'prep.formula', label: 'Depois de agosto', x: 360, y: 2900,
    config: { formulas: [{ column: 'depois', expression: '', type: 'Auto' }] } },
  { id: 'x86_dt', type: 'prep.formula', label: 'Quando chegou', x: 360, y: 3020,
    config: { formulas: [{ column: 'chegada', expression: "ToDateTime('2026-07-08 14:30:00')", type: 'Auto' }] } },
  { id: 'x86_flt', type: 'prep.filter', label: 'Desde 8 de julho', x: 660, y: 3020,
    config: { mode: 'simple', column: 'chegada', operator: '>=', value: '2026-07-08' } },
);
wf.edges.push({ id: 'x86e1', source: 'n_pdf_campos', sourceHandle: 'out', target: 'x86_f', targetHandle: 'in' });
wf.edges.push({ id: 'x86e2', source: 'n_pdf_mes', sourceHandle: 'out', target: 'x86_dt', targetHandle: 'in' });
wf.edges.push({ id: 'x86e3', source: 'x86_dt', sourceHandle: 'out', target: 'x86_flt', targetHandle: 'in' });
"""


def _run_to(pg: Any, node: str) -> None:
    pg.evaluate("id => { window.__S.select(id); window.__S.inspect(id); }", node)
    pg.wait_for_timeout(400)
    pg.keyboard.press("Control+Shift+Enter")
    pg.wait_for_function(
        "id => ['executed', 'cached', 'error'].includes(window.__S.store.execution?.node_results?.[id]?.status) && !window.__S.store.running",
        arg=node,
        timeout=120000,
    )
    pg.wait_for_timeout(900)


def _answer_path(pg: Any, path: Path) -> None:
    box = pg.locator("dialog[open] input.input.mono")
    box.wait_for()
    box.fill(str(path))
    box.press("Enter")


def part_086(pg: Any, shot: Callable[..., None]) -> None:
    pg.evaluate("code => window.__S.mutate((wf) => { new Function('wf', code)(wf); })", NODES)
    pg.wait_for_timeout(500)
    # "Você quis dizer…": a data escrita de outro jeito, e a forma certa logo abaixo
    _run_to(pg, "x86_f")
    pg.wait_for_timeout(1500)  # as colunas da entrada chegam depois da execução
    area = pg.locator("#leftPanel .fx-input").first
    area.click()
    area.type("[competencia] >= 07/08/2026", delay=4)
    area.type(" ")
    area.press("Backspace")
    pg.wait_for_selector("#leftPanel .fx-date", timeout=5000)
    pg.wait_for_timeout(300)
    shot(pg.locator("#leftPanel .fx").first, "data-sugestao")
    # o calendário do Filter básico numa coluna de data e hora: hora opcional
    _run_to(pg, "x86_dt")
    _run_to(pg, "x86_flt")
    field = pg.locator("#leftPanel .field", has=pg.locator("input[type=date]"))
    field.wait_for(timeout=10000)
    shot(field, "filtro-calendario")
    pg.evaluate(
        "() => window.__S.mutate((wf) => { wf.nodes = wf.nodes.filter((n) => !n.id.startsWith('x86_')); "
        "wf.edges = wf.edges.filter((e) => !e.id.startsWith('x86e')); })"
    )
    # "Salvar com amostra dos dados": linhas e máscara por fonte, com a prévia mascarada
    pg.locator("#topActions .save-arrow").click()  # desde a 0.9.1, na seta do Salvar
    pg.locator("[role=menuitem]", has_text="Salvar com amostra dos dados").click()
    pg.wait_for_selector("dialog[open] .pt-src", timeout=120000)
    boxes = pg.locator("dialog[open] .pt-src input[type=checkbox]:not([disabled])")
    for i in range(2, boxes.count()):
        boxes.nth(i).uncheck()
    pg.locator("dialog[open] .pt-src").first.locator(".btn[aria-expanded]").click()
    pg.wait_for_selector("dialog[open] .pt-preview", timeout=30000)
    pg.wait_for_timeout(400)
    shot(pg.locator("dialog[open]"), "compartilhar")
    # grava só os clientes e reabre como se fosse noutro computador (a fonte com outro nome não existe aqui)
    pg.locator("dialog[open] .pt-src input[type=checkbox]").nth(1).uncheck()
    tmp = Path(tempfile.mkdtemp())
    saved = tmp / "pipeline_com_amostra.prodata.json"
    pg.locator("dialog[open] button", has_text="Escolher onde salvar").click()
    _answer_path(pg, saved)
    pg.wait_for_timeout(2500)
    data = json.loads(saved.read_text(encoding="utf-8"))
    for node in data["nodes"]:
        if node["config"].get("dataset") == "clientes_enterprise.csv":
            node["config"]["dataset"] = "clientes_2025.csv"
    data["samples"] = {"clientes_2025.csv": data["samples"]["clientes_enterprise.csv"]}
    data["id"] = "pipeline_de_fora"
    other = tmp / "pipeline_de_fora.prodata.json"
    other.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    pg.locator(".top-menu", has_text="Arquivo").click()
    pg.locator("[role=menuitem]", has_text="Abrir arquivo").click()
    _answer_path(pg, other)
    pg.wait_for_selector(".node.source-sample", timeout=30000)
    pg.wait_for_timeout(1200)
    pg.evaluate("() => document.querySelectorAll('.trust-host, .toast').forEach((e) => e.remove())")
    pg.evaluate("() => window.__S.select('n_clientes')")
    pg.keyboard.press("f")  # enquadra a caixa selecionada
    pg.wait_for_timeout(900)
    node = pg.locator(".node.source-sample").first
    box = node.bounding_box()
    shot(
        pg,
        "amostra-caixa",
        clip={
            "x": box["x"] - 30,
            "y": box["y"] - 26,
            "width": box["width"] + 60,
            "height": box["height"] + 44,
        },
    )
    pg.locator('#viewSwitch .segment[data-view="data"]').click()
    pg.wait_for_selector(".pt-item.sample", timeout=10000)
    pg.wait_for_timeout(600)
    shot(pg.locator(".pt-box"), "amostra-dados")
    pg.locator('#viewSwitch .segment[data-view="designer"]').click()
    # o que falta neste computador: uma fonte que não existe aqui, sem amostra
    pg.evaluate(
        """() => window.__S.mutate((wf) => { wf.nodes.push({ id: 'x86_fora', type: 'io.input_data', label: 'Vendas 2025', x: 60, y: 3200,
           config: { dataset: 'vendas_2025.csv' } }); wf.samples = {}; }, { structural: true })"""
    )
    pg.wait_for_timeout(1200)
    pg.locator('#viewSwitch .segment[data-view="data"]').click()
    pg.wait_for_selector(".pt-item.missing", timeout=10000)
    pg.wait_for_timeout(600)
    shot(pg.locator(".pt-box"), "faltam-aqui")
    pg.locator('#viewSwitch .segment[data-view="designer"]').click()
    pg.wait_for_timeout(500)
