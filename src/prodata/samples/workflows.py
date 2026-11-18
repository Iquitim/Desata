"""Fluxo de demonstração usado na primeira execução e pelos testes."""

from __future__ import annotations

from typing import Any

from prodata.dashboard.layouts import LayoutItem, Rect, VisualHint, arrange
from prodata.domain.dashboard import DashPage
from prodata.samples.apis import ESTADOS_ID, MUNICIPIOS_ID
from prodata.samples.demo_logo import LOGO, logo_uri
from prodata.samples.pdfs import SOURCE_ID as PDF_SOURCE

DEMO_WORKFLOW_ID = "demo_pipeline_360"
# Caixas criadas na v0.3 (spec 014): sem elas, a demonstração salva é de uma versão anterior.
DEMO_V3_NODES = ("n_pareto", "n_venn")
# Etapa da API pública (spec 022): quem já tem a demonstração salva a recebe sem perder o que alterou.
API_FIRST_NODE = "n_api_estados"
# Corrida de barras e linha do tempo (spec 030): a demonstração mostra o Replay com dados que já tem.
RACE_NODE = "n_race"
# Leitor de PDF (spec 037): relatórios reais da Receita Federal, lidos pelo Input Data.
PDF_FIRST_NODE = "n_pdf_campos"
DEMO_TIMELINE = {"column": "competencia", "step": "month", "mode": "cumulative", "speed": 1.0}
# Colunas do canvas para cartões de 188 px com 60 px de folga (spec 004, RF-403).
COL = [40 + 248 * i for i in range(9)]


def _node(node_id: str, type_: str, label: str, col: int, y: int, **config: Any) -> dict[str, Any]:
    return {"id": node_id, "type": type_, "label": label, "x": COL[col], "y": y, "config": config}


def _edge(
    eid: str, source: str, source_handle: str, target: str, target_handle: str = "in"
) -> dict[str, str]:
    return {
        "id": eid,
        "source": source,
        "sourceHandle": source_handle,
        "target": target,
        "targetHandle": target_handle,
    }


def _container(cid: str, title: str, color: str, x: int, y: int, width: int, height: int) -> dict[str, Any]:
    return {"id": cid, "title": title, "color": color, "x": x, "y": y, "width": width, "height": height}


def api_section() -> dict[str, list[dict[str, Any]]]:
    """Etapa que consome uma API pública: não chama nada até o clique em Executar (RF-2213)."""
    return {
        "containers": [
            {
                **_container("c_api", "5 · API pública do IBGE", "#10b981", 20, 620, 2212, 170),
                "description": "Chama a internet só ao clicar em Executar. Abra cada caixa para ver como funciona.",
            }
        ],
        "nodes": [
            _node("n_api_estados", "io.input_data", "Estados (IBGE)", 0, 690, dataset=f"api:{ESTADOS_ID}"),
            _node(
                "n_api_municipios",
                "io.api_loop",
                "Municípios por estado",
                1,
                690,
                source=MUNICIPIOS_ID,
                columns={"sigla": "sigla"},
                reuse=True,
            ),
            _node(
                "n_api_contagem",
                "transform.summarize",
                "Conta municípios",
                2,
                690,
                group_by=["sigla", "nome", "regiao.nome"],
                aggregations=[{"column": "municipio-id", "agg": "count", "alias": "municipios"}],
            ),
            _node(
                "n_api_join",
                "transform.join",
                "Clientes × IBGE",
                5,
                690,
                keys=[{"left": "uf", "right": "sigla"}],
            ),
            _node(
                "n_api_chart",
                "bi.chart",
                "MRR por região",
                6,
                690,
                title="MRR por região do Brasil",
                chart_type="bar",
                x_column="regiao.nome",
                y_column="mrr_mensal",
                agg="sum",
            ),
        ],
        "edges": [
            _edge("e_api1", "n_api_estados", "out", "n_api_municipios"),
            _edge("e_api2", "n_api_municipios", "out", "n_api_contagem"),
            _edge("e_api3", "n_join", "J", "n_api_join", "L"),
            _edge("e_api4", "n_api_contagem", "out", "n_api_join", "R"),
            _edge("e_api5", "n_api_join", "J", "n_api_chart"),
        ],
    }


# Os principais tributos (o primeiro nível da tabela da Receita), para o gráfico do dashboard.
_TRIBUTOS = " OR ".join(
    [
        "[receita] = 'IMPOSTO SOBRE IMPORTAÇÃO'",
        "[receita] = 'I.P.I-TOTAL'",
        "[receita] = 'IMPOSTO SOBRE A RENDA-TOTAL'",
        "StartsWith([receita], 'IOF')",
        "StartsWith([receita], 'COFINS')",
        "StartsWith([receita], 'CONTRIBUIÇÃO PARA O PIS')",
        "StartsWith([receita], 'CSLL')",
        "StartsWith([receita], 'RECEITA PREVIDENCIÁRIA')",
    ]
)
# Caixas do PDF que aparecem no dashboard do exemplo.
PDF_VISUALS = (
    ("n_pdf_chart", "bar"),
    ("n_pdf_tributos", "hbar"),
    ("n_pdf_indice_chart", "bar"),
)
# Onde as caixas da primeira versão da etapa ficavam (0.8.5 de antes): se continuam lá, vão para o lugar novo.
_PDF_V1 = {"n_pdf_chart": (1, 70), "n_pdf_itens": (3, 70)}


def pdf_section(y: int = 810) -> dict[str, list[dict[str, Any]]]:
    """Etapa com PDFs de verdade: a Análise da Arrecadação da Receita Federal, três meses, com a extração pronta.

    Os dados do PDF entram no resto do fluxo: o faturamento das Transações é cruzado com a arrecadação federal do
    mesmo mês, e a tabela por tributo vira o gráfico dos principais tributos.
    """
    row1, row2 = y + 70, y + 190
    return {
        "containers": [
            {
                **_container("c_pdf", "6 · PDFs da Receita Federal", "#ef4444", 20, y, 2212, 290),
                "description": "Três relatórios mensais em PDF, lidos por uma extração ensinada na vista Dados, cruzados "
                "com o faturamento das Transações. Abra a fonte em Dados para ver de onde veio cada número.",
            }
        ],
        "nodes": [
            _node(
                "n_pdf_campos",
                "io.input_data",
                "Resumo de cada PDF",
                0,
                row1,
                dataset=f"pdf:{PDF_SOURCE}/campos",
            ),
            _node(
                "n_pdf_mes",
                "prep.formula",
                "Mês do relatório",
                1,
                row1,
                formulas=[
                    {"column": "mes", "expression": "DateFormat([competencia], '%Y-%m')", "type": "String"},
                    {
                        "column": "receita_bi",
                        "expression": "Round([receita_administrada_rfb] / 1000, 1)",
                        "type": "Float64",
                    },
                ],
            ),
            _node(
                "n_pdf_vendas_mes",
                "transform.summarize",
                "Faturamento por mês",
                2,
                row1,
                group_by=["competencia"],
                aggregations=[{"column": "valor_bruto", "agg": "sum", "alias": "faturamento"}],
            ),
            _node(
                "n_pdf_join",
                "transform.join",
                "Faturamento × arrecadação",
                3,
                row1,
                keys=[{"left": "mes", "right": "competencia"}],
            ),
            _node(
                "n_pdf_indice",
                "prep.formula",
                "Por R$ 1 bi arrecadado",
                4,
                row1,
                formulas=[
                    {
                        "column": "faturamento_por_bi",
                        "expression": "Round([faturamento] / ([receita_administrada_rfb] / 1000), 2)",
                        "type": "Float64",
                    }
                ],
            ),
            _node(
                "n_pdf_indice_chart",
                "bi.chart",
                "Faturamento × União",
                5,
                row1,
                title="Faturamento para cada R$ 1 bi arrecadado pela União",
                chart_type="bar",
                x_column="mes",
                y_column="faturamento_por_bi",
                agg="sum",
                sort="label",
            ),
            _node(
                "n_pdf_itens",
                "io.input_data",
                "Arrecadação por tributo",
                0,
                row2,
                dataset=f"pdf:{PDF_SOURCE}/itens_acumulado_no_ano",
            ),
            _node(
                "n_pdf_bi",
                "prep.formula",
                "Em R$ bilhões",
                1,
                row2,
                formulas=[
                    {
                        "column": "arrecadado_bi",
                        "expression": "Round([arrecadado_ano_atual] / 1000, 1)",
                        "type": "Float64",
                    }
                ],
            ),
            _node(
                "n_pdf_principais",
                "prep.filter",
                "Principais tributos",
                2,
                row2,
                mode="expression",
                expression=_TRIBUTOS,
            ),
            _node(
                "n_pdf_tributos",
                "bi.chart",
                "Tributos no ano",
                3,
                row2,
                title="Principais tributos no ano (R$ bilhões)",
                chart_type="hbar",
                x_column="receita",
                y_column="arrecadado_bi",
                agg="max",  # o acumulado só cresce: o maior é o do último relatório
            ),
            _node(
                "n_pdf_chart",
                "bi.chart",
                "Arrecadação por mês",
                4,
                row2,
                title="Receita administrada pela RFB (R$ bilhões)",
                chart_type="bar",
                x_column="mes",
                y_column="receita_bi",
                agg="sum",
                sort="label",
            ),
        ],
        "edges": [
            _edge("e_pdf2", "n_pdf_campos", "out", "n_pdf_mes"),
            _edge("e_pdf3", "n_vendas", "out", "n_pdf_vendas_mes"),
            _edge("e_pdf4", "n_pdf_mes", "out", "n_pdf_join", "L"),
            _edge("e_pdf5", "n_pdf_vendas_mes", "out", "n_pdf_join", "R"),
            _edge("e_pdf6", "n_pdf_join", "J", "n_pdf_indice"),
            _edge("e_pdf7", "n_pdf_indice", "out", "n_pdf_indice_chart"),
            _edge("e_pdf8", "n_pdf_itens", "out", "n_pdf_bi"),
            _edge("e_pdf9", "n_pdf_principais", "T", "n_pdf_tributos"),
            _edge("e_pdf10", "n_pdf_mes", "out", "n_pdf_chart"),
            _edge("e_pdf11", "n_pdf_bi", "out", "n_pdf_principais"),
        ],
    }


def add_pdf_section(workflow: dict[str, Any]) -> bool:
    """Leva a etapa do PDF (ou a versão nova dela) a uma demonstração salva, sem cobrir o que foi movido.

    Caixas que faltam entram; as da primeira versão que continuam no lugar de antes vão para o lugar novo; os
    gráficos entram no dashboard. Devolve se mudou algo.
    """
    nodes = {n["id"]: n for n in workflow["nodes"]}
    if "n_vendas" not in nodes:
        return False
    box = next((c for c in workflow.get("containers", []) if c["id"] == "c_pdf"), None)
    if box is None:
        bottom = max(
            [n["y"] + 56 for n in workflow["nodes"]]
            + [c["y"] + c["height"] for c in workflow.get("containers", [])]
        )
        y = bottom + 20
    else:
        y = box["y"]
    section = pdf_section(y)
    changed = False
    if box is None:
        workflow.setdefault("containers", []).extend(section["containers"])
        changed = True
    elif box["height"] < section["containers"][0]["height"]:
        box.update(
            height=section["containers"][0]["height"], description=section["containers"][0]["description"]
        )
        changed = True
    for node in section["nodes"]:
        current = nodes.get(node["id"])
        if current is None:
            workflow["nodes"].append(node)
            changed = True
        elif node["id"] in _PDF_V1:
            col, dy = _PDF_V1[node["id"]]
            if (current["x"], current["y"]) == (COL[col], y + dy) and (current["x"], current["y"]) != (
                node["x"],
                node["y"],
            ):
                current.update(x=node["x"], y=node["y"])
                changed = True
    edges = workflow.setdefault("edges", [])
    old_chart = next((n for n in workflow["nodes"] if n["id"] == "n_pdf_chart"), None)
    if old_chart and old_chart["config"].get("x_column") == "competencia":  # o gráfico da primeira versão
        fresh = next(n for n in section["nodes"] if n["id"] == "n_pdf_chart")
        old_chart["config"] = dict(fresh["config"])
        changed = True
    # ligações da primeira versão que mudaram: o gráfico agora vem do mês, e os tributos passam pela fórmula
    stale = [
        e
        for e in edges
        if e["id"] == "e_pdf1" or (e["id"] == "e_pdf8" and e.get("target") == "n_pdf_principais")
    ]
    if stale:
        edges[:] = [e for e in edges if e not in stale]
        changed = True
    known = {e["id"] for e in edges}
    for edge in section["edges"]:
        if edge["id"] not in known:
            edges.append(edge)
            changed = True
    return _show_pdf_visuals(workflow) or changed


def _show_pdf_visuals(workflow: dict[str, Any]) -> bool:
    """Os gráficos do PDF entram no dashboard (abaixo do que já existe) e saem da lista de ocultos."""
    dashboard = workflow.get("dashboard")
    if not dashboard:
        return False
    items = dashboard.setdefault("items", [])
    hidden = dashboard.setdefault("hidden", [])
    shown = {i.get("node_id") for i in items if i.get("kind") == "visual"}
    missing = [n for n, _ in PDF_VISUALS if n not in shown]
    changed = any(n in hidden for n, _ in PDF_VISUALS)
    dashboard["hidden"] = [h for h in hidden if h not in {n for n, _ in PDF_VISUALS}]
    if not missing:
        return changed
    top = max([i["y"] + i["h"] for i in items] or [0]) + 24
    width = (1520 - 24 * (len(missing) - 1)) // len(missing)
    for k, node_id in enumerate(missing):
        items.append(
            {
                "id": f"d_{node_id}",
                "kind": "visual",
                "node_id": node_id,
                "x": 40 + k * (width + 24),
                "y": top,
                "w": width,
                "h": 300,
                "format": {},
            }
        )
    page = dashboard.setdefault("page", {})
    if top + 300 + 24 > _page_height(page):
        page.update(size="free", height=min(20000, top + 300 + 40))
    return True


def _page_height(page: dict[str, Any]) -> int:
    return DashPage.model_validate(page or {}).pixel_height


def _race_node(y: int = 480) -> dict[str, Any]:
    return _node(
        RACE_NODE,
        "bi.chart",
        "Corrida por produto",
        2,
        y,
        title="Faturamento por produto",
        chart_type="race",
        x_column="produto",
        y_column="valor_bruto",
        agg="sum",
    )


def add_replay_section(workflow: dict[str, Any]) -> bool:
    """Leva a corrida de barras e a linha do tempo a uma demonstração salva, sem cobrir o que foi movido."""
    dashboard = workflow.get("dashboard")
    ids = {n["id"] for n in workflow["nodes"]}
    if (
        RACE_NODE in ids
        or "n_vendas" not in ids
        or not dashboard
        or (dashboard.get("timeline") or {}).get("column")
    ):
        return False
    node = _race_node()
    taken = any(abs(n["x"] - node["x"]) < 200 and abs(n["y"] - node["y"]) < 110 for n in workflow["nodes"])
    if taken:
        node["y"] = max(n["y"] for n in workflow["nodes"]) + 140
    workflow["nodes"].append(node)
    workflow["edges"].append(_edge("e_race", "n_vendas", "out", RACE_NODE))
    dashboard["timeline"] = DEMO_TIMELINE
    return True


def add_api_section(workflow: dict[str, Any]) -> bool:
    """Acrescenta a etapa a uma demonstração salva, sem tocar no resto. Precisa da junção de clientes."""
    ids = {n["id"] for n in workflow["nodes"]}
    if API_FIRST_NODE in ids or "n_join" not in ids:
        return False
    section = api_section()
    # Abaixo do que já existir, para não cobrir o que o usuário mudou de lugar.
    bottom = max(
        [n["y"] + 56 for n in workflow["nodes"]]
        + [c["y"] + c["height"] for c in workflow.get("containers", [])]
    )
    shift = max(0, bottom + 20 - 620)
    for box in section["containers"]:
        box["y"] += shift
    for node in section["nodes"]:
        node["y"] += shift
    workflow.setdefault("containers", []).extend(section["containers"])
    workflow["nodes"].extend(section["nodes"])
    workflow.setdefault("edges", []).extend(section["edges"])
    if workflow.get("dashboard"):
        workflow["dashboard"].setdefault("hidden", []).append("n_api_chart")
    return True


def demo_workflow() -> dict[str, Any]:
    from prodata.samples.workflow_loop import loop_section  # o laço importa as peças daqui

    section = api_section()
    pdf = pdf_section()
    loop = loop_section()
    return {
        "id": DEMO_WORKFLOW_ID,
        "name": "Pipeline 360° de clientes",
        "description": "Limpeza, filtro, junção L/J/R, metas regionais (CSV ';' em CP1252), BI e modelo de inadimplência.",
        "containers": [
            _container("c_prep", "1 · Ingestão e preparação", "#3b82f6", 20, 20, 972, 260),
            _container("c_bi", "2 · Junção, metas e indicadores", "#8b5cf6", 1010, 20, 1222, 420),
            _container("c_ml", "3 · Modelo de inadimplência", "#06b6d4", 1010, 460, 1222, 140),
            _container("c_vendas", "4 · Vendas no dashboard", "#f59e0b", 20, 300, 972, 300),
            *section["containers"],
            *pdf["containers"],
            *loop["containers"],
        ],
        "nodes": [
            _node("n_clientes", "io.input_data", "Clientes", 0, 70, dataset="clientes_enterprise.csv"),
            _node("n_vendas", "io.input_data", "Transações", 0, 190, dataset="transacoes_vendas.csv"),
            _node(
                "n_cleanse",
                "prep.cleanse",
                "Limpeza",
                1,
                70,
                columns=["setor"],
                replace_null_string=True,
                string_default="Não informado",
            ),
            _node(
                "n_formula",
                "prep.formula",
                "ARR e tier",
                2,
                70,
                formulas=[
                    {
                        "column": "receita_anual",
                        "type": "Float64",
                        "expression": "Round([mrr_mensal] * 12, 2)",
                    },
                    {
                        "column": "tier",
                        "type": "String",
                        "expression": "IF [mrr_mensal] >= 6000 THEN 'Diamond' ELSEIF [mrr_mensal] >= 3000 "
                        "THEN 'Gold' ELSE 'Silver' ENDIF",
                    },
                ],
            ),
            _node(
                "n_filter",
                "prep.filter",
                "Ativos",
                3,
                70,
                mode="expression",
                expression="[status] != 'INATIVO' AND [mrr_mensal] >= 1000",
            ),
            _node(
                "n_sum_vendas",
                "transform.summarize",
                "Vendas por cliente",
                2,
                190,
                group_by=["id_cliente"],
                aggregations=[
                    {"column": "valor_bruto", "agg": "sum", "alias": "total_compras"},
                    {"column": "quantidade_licencas", "agg": "sum", "alias": "total_licencas"},
                    {"column": "id_transacao", "agg": "count", "alias": "qtd_pedidos"},
                ],
            ),
            _node(
                "n_join",
                "transform.join",
                "Clientes × vendas",
                4,
                125,
                right_prefix="v_",
                keys=[{"left": "id_cliente", "right": "id_cliente"}],
            ),
            _node(
                "n_sum_uf",
                "transform.summarize",
                "MRR por UF",
                5,
                65,
                group_by=["uf"],
                aggregations=[
                    {"column": "mrr_mensal", "agg": "sum", "alias": "total_mrr"},
                    {"column": "id_cliente", "agg": "count", "alias": "clientes"},
                ],
            ),
            _node("n_metas", "io.input_data", "Metas regionais", 5, 165, dataset="metas_regionais_br.csv"),
            _node(
                "n_join_metas", "transform.join", "UF × metas", 6, 100, keys=[{"left": "uf", "right": "uf"}]
            ),
            _node(
                "n_atingimento",
                "prep.formula",
                "Atingimento",
                7,
                108,
                formulas=[
                    {
                        "column": "atingimento_pct",
                        "type": "Float64",
                        "expression": "Round([total_mrr] / [meta_mrr] * 100, 1)",
                    },
                ],
            ),
            _node(
                "n_chart_uf",
                "bi.chart",
                "Gráfico por UF",
                8,
                108,
                title="Atingimento da meta de MRR por UF (%)",
                chart_type="bar",
                x_column="uf",
                y_column="atingimento_pct",
                agg="max",
                sort="value_desc",
            ),
            _node(
                "n_kpi",
                "bi.kpi_card",
                "ARR ativo",
                5,
                270,
                title="ARR dos clientes ativos",
                column="receita_anual",
                metric="sum",
                prefix="R$ ",
            ),
            _node(
                "n_chart_seg",
                "bi.chart",
                "MRR por segmento",
                5,
                360,
                title="MRR por segmento",
                chart_type="donut",
                x_column="segmento",
                y_column="mrr_mensal",
                agg="sum",
            ),
            _node(
                "n_pareto",
                "bi.chart",
                "Pareto por UF",
                6,
                300,
                title="Pareto do MRR por UF",
                chart_type="pareto",
                x_column="uf",
                y_column="mrr_mensal",
                agg="sum",
            ),
            _node(
                "n_kpi_mes",
                "bi.kpi_card",
                "Faturamento do mês",
                1,
                350,
                title="Faturamento do mês",
                column="valor_bruto",
                metric="sum",
                prefix="R$ ",
                compare="previous",
                date_column="competencia",
                period="month",
                sparkline=True,
            ),
            _node(
                "n_stacked",
                "bi.chart",
                "Vendas por mês",
                2,
                350,
                title="Faturamento mensal por produto",
                chart_type="stacked",
                x_column="competencia",
                y_column="valor_bruto",
                series_column="produto",
                agg="sum",
                sort="label",
            ),
            _race_node(),
            _node(
                "n_venn",
                "bi.venn",
                "Produtos por cliente",
                1,
                480,
                title="Clientes por produto contratado",
                key_column="id_cliente",
                group_column="produto",
                groups=["Cloud", "AutoML", "BI Pro"],
            ),
            _node(
                "n_trainer",
                "ml.automl_trainer",
                "Treino",
                5,
                510,
                target_column="inadimplente",
                feature_columns=[
                    "mrr_mensal",
                    "meses_contrato",
                    "nps",
                    "total_compras",
                    "total_licencas",
                    "segmento",
                    "uf",
                ],
            ),
            _node(
                "n_predictor",
                "ml.predictor",
                "Score de risco",
                6,
                510,
                prediction_column="risco_inadimplencia",
                probability_column="confianca_pct",
            ),
            _node(
                "n_output",
                "io.output_data",
                "Exportar",
                7,
                510,
                filename="clientes_pontuados",
                format="parquet",
            ),
            *section["nodes"],
            *pdf["nodes"],
            *loop["nodes"],
        ],
        "edges": [
            _edge("e1", "n_clientes", "out", "n_cleanse"),
            _edge("e2", "n_cleanse", "out", "n_formula"),
            _edge("e3", "n_formula", "out", "n_filter"),
            _edge("e4", "n_vendas", "out", "n_sum_vendas"),
            _edge("e5", "n_filter", "T", "n_join", "L"),
            _edge("e6", "n_sum_vendas", "out", "n_join", "R"),
            _edge("e7", "n_join", "J", "n_sum_uf"),
            _edge("e8", "n_sum_uf", "out", "n_join_metas", "L"),
            _edge("e9", "n_metas", "out", "n_join_metas", "R"),
            _edge("e10", "n_join_metas", "J", "n_atingimento"),
            _edge("e11", "n_atingimento", "out", "n_chart_uf"),
            _edge("e12", "n_join", "J", "n_kpi"),
            _edge("e13", "n_join", "J", "n_chart_seg"),
            _edge("e14", "n_join", "J", "n_trainer"),
            _edge("e15", "n_trainer", "M", "n_predictor", "M"),
            _edge("e16", "n_join", "J", "n_predictor", "D"),
            _edge("e17", "n_predictor", "out", "n_output"),
            _edge("e18", "n_join", "J", "n_pareto"),
            _edge("e19", "n_vendas", "out", "n_kpi_mes"),
            _edge("e20", "n_vendas", "out", "n_stacked"),
            _edge("e21", "n_vendas", "out", "n_venn"),
            _edge("e_race", "n_vendas", "out", RACE_NODE),
            *section["edges"],
            *pdf["edges"],
            *loop["edges"],
        ],
        "dashboard": demo_dashboard(),
    }


def demo_dashboard() -> dict[str, Any]:
    """Dashboard já montado: título, logo, big numbers no topo e gráficos em três colunas."""
    visuals = [
        ("n_kpi", VisualHint(kind="kpi")),
        ("n_kpi_mes", VisualHint(kind="kpi")),
        ("n_stacked", VisualHint(chart_type="stacked")),
        ("n_pareto", VisualHint(chart_type="pareto")),
        ("n_chart_uf", VisualHint(chart_type="bar")),
        ("n_chart_seg", VisualHint(chart_type="donut")),
        ("n_venn", VisualHint(chart_type="venn")),
        (RACE_NODE, VisualHint(chart_type="hbar")),
        *((node, VisualHint(chart_type=kind)) for node, kind in PDF_VISUALS),
    ]
    title = Rect(x=40, y=32, w=1200, h=56)
    logo = Rect(x=1488, y=24, w=72, h=88)
    page = DashPage(size="free", height=1500)  # a4 não cabe os gráficos do PDF
    items = [LayoutItem(id=n, hint=hint, rect=Rect(y=i)) for i, (n, hint) in enumerate(visuals)]
    result = arrange(items, page, "kpis-top-3", [title, logo])
    content = logo_uri(LOGO)
    return {
        "page": result.page.model_dump(),
        "timeline": DEMO_TIMELINE,
        "items": [
            {
                "id": "d_title",
                "kind": "text",
                **title.model_dump(),
                "content": "Pipeline 360° de clientes",
                "format": {"size": 30, "bold": True, "vertical": "middle"},
            },
            {"id": "d_logo", "kind": "image", **logo.model_dump(), "content": content, "format": {}},
            *(
                {
                    "id": f"d_{n}",
                    "kind": "visual",
                    "node_id": n,
                    **result.positions[n].model_dump(),
                    "format": {},
                }
                for n, _ in visuals
            ),
        ],
        # O gráfico da API fica fora da página: o dashboard do exemplo não depende de rede (RF-2216).
        "hidden": ["n_api_chart"],
    }
