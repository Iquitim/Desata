"""Spec 037: leitor de PDF como fonte da vista Dados, lido pelo Input Data (saídas, política, cache e correções)."""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from prodata.documents import reader
from prodata.documents.recipe import Recipe
from prodata.documents.sources import PdfSource, source_pdf_ref
from prodata.documents.suggest import suggest_field, suggest_table
from prodata.domain.workflow import Workflow
from prodata.engine.runner import WorkflowRunner
from prodata.errors import ConflictError, InvalidInputError, NotFoundError
from prodata.ingestion import DatasetStore

FIX = Path(__file__).parent / "fixtures" / "pdf"


@pytest.fixture(autouse=True)
def close_reader(store: DatasetStore) -> Iterator[None]:
    yield
    store.pdfs.close()  # o processo do leitor não fica sobrando depois do teste


@pytest.fixture
def month(tmp_path: Path) -> Path:
    folder = tmp_path / "relatorios"
    folder.mkdir()
    for name in ("outubro", "novembro", "dois_totais"):
        shutil.copy(FIX / f"relatorio_{name}.pdf", folder / f"relatorio_{name}.pdf")
    (folder / "anotacoes.txt").write_text("não é PDF", encoding="utf-8")
    return folder


def recipe() -> Recipe:
    """A extração que a pessoa faria marcando o PDF de outubro: total obrigatório, competência e a tabela."""
    info = reader.inspect(str(FIX / "relatorio_outubro.pdf"))
    total = suggest_field(info, [w for w in info["words"] if w["t"] == "834.086,00" and w["p"] == 0])
    comp = suggest_field(info, [w for w in info["words"] if w["t"] == "10/2026"])
    table = suggest_table(info, 0, (0.05, 0.18, 0.95, 0.97), "vendas")
    return Recipe(
        id="x",
        nome="Relatório de vendas",
        campos=[{**total["campo"], "obrigatorio": True}, comp["campo"]],
        tabelas=[table["tabela"]],
    )


def make(store: DatasetStore, month: Path, **extra: object) -> PdfSource:
    saved = store.pdfs.save(
        PdfSource.model_validate(
            {"name": "Relatórios", "mode": "pasta", "path": str(month), "pattern": "relatorio_*.pdf", **extra}
        )
    )
    store.pdfs.save_recipe(saved.id, recipe())
    return store.pdfs.get(saved.id)


def flow(dataset: str) -> Workflow:
    return Workflow.model_validate(
        {
            "id": "pdf",
            "name": "PDF",
            "nodes": [{"id": "i", "type": "io.input_data", "config": {"dataset": dataset}}],
            "edges": [],
        }
    )


def test_reference_names_the_output() -> None:
    assert source_pdf_ref("pdf:relatorios/itens_vendas") == ("relatorios", "itens_vendas")
    assert source_pdf_ref("pdf:relatorios") == ("relatorios", "campos")
    assert source_pdf_ref("folder:x") is None


def test_cadastro_rascunho_revisao_e_duplicar(store: DatasetStore, month: Path) -> None:
    draft = store.pdfs.save(PdfSource(name="Relatórios", mode="pasta", path=str(month)))
    st = store.pdfs.status(draft)
    assert st.draft and st.files == 3 and st.outputs == ["campos", "falhas", "origem"]
    with pytest.raises(ConflictError):
        store.pdfs.save(PdfSource(name="relatórios", mode="pasta", path=str(month)))
    with pytest.raises(InvalidInputError):
        store.pdfs.read(draft.id, "campos")  # rascunho não vira dado
    first = store.pdfs.save_recipe(draft.id, recipe())
    assert first.revisao == 1
    assert store.pdfs.save_recipe(draft.id, first.model_copy(update={"nome": "Outro nome"})).revisao == 1
    changed = first.model_copy(update={"campos": first.campos[:1]})
    assert store.pdfs.save_recipe(draft.id, changed).revisao == 2  # o que muda o resultado sobe a revisão
    st = store.pdfs.status(store.pdfs.get(draft.id))
    assert not st.draft and st.outputs == ["campos", "itens_vendas", "falhas", "origem"]
    copy = store.pdfs.duplicate(draft.id)
    assert copy.name == "Relatórios (cópia)" and copy.recipe == store.pdfs.get(draft.id).recipe
    store.pdfs.delete(draft.id)
    assert store.pdfs.recipe_of(copy) is not None  # a extração continua: a cópia usa


def test_politica_parar_falha_com_mensagem_clara(
    runner: WorkflowRunner, store: DatasetStore, month: Path
) -> None:
    """CA-12: o relatório com dois totais deixa o total obrigatório Ambíguo, e a política manda parar."""
    src = make(store, month)
    result = runner.run(flow(f"pdf:{src.id}/campos")).node_results["i"]
    assert result.status == "error"
    assert "relatorio_dois_totais.pdf" in result.error and "parar a execução" in result.error
    failures = runner.run(flow(f"pdf:{src.id}/falhas")).node_results["i"]
    assert (
        failures.status == "executed" and failures.anchors["out"].row_count == 1
    )  # o relatório sai mesmo assim


def test_politicas_aprovados_e_todos(runner: WorkflowRunner, store: DatasetStore, month: Path) -> None:
    src = make(store, month, policy="aprovados")
    frame, extra = store.pdfs.read(src.id, "campos")
    assert frame["documento"].to_list() == ["relatorio_novembro.pdf", "relatorio_outubro.pdf"]
    assert frame["total_liquido"].to_list() == [Decimal("195880.75"), Decimal("834086.00")]
    assert frame["revisao"].unique().to_list() == [1] and "ficaram de fora" in extra["warnings"][0]
    items, _ = store.pdfs.read(src.id, "itens_vendas")
    assert items.height == 32 + 7 and set(items["documento"]) == {
        "relatorio_outubro.pdf",
        "relatorio_novembro.pdf",
    }
    store.pdfs.save(src.model_copy(update={"policy": "todos"}), previous=src.id)
    everything, _ = store.pdfs.read(src.id, "campos")
    assert everything.height == 3 and everything["situacao"].to_list() == ["Falhou", "Aprovado", "Aprovado"]
    origin, _ = store.pdfs.read(src.id, "origem")
    row = origin.filter(origin["coluna"] == "total_liquido").row(0, named=True)
    assert (
        row["pagina"] == 1
        and 0 < row["x0"] < row["x1"] <= 1
        and row["regra"] == "à direita de “Total líquido”"
    )


def test_cache_acompanha_os_pdfs(runner: WorkflowRunner, store: DatasetStore, month: Path) -> None:
    """CA-11: sem mudança aproveita; PDF novo na pasta ou PDF alterado refaz."""
    src = make(store, month, policy="todos")
    wf = flow(f"pdf:{src.id}/campos")
    assert runner.run(wf).node_results["i"].anchors["out"].row_count == 3
    assert runner.run(wf).node_results["i"].status == "cached"
    shutil.copy(FIX / "relatorio_invalido.pdf", month / "relatorio_invalido.pdf")
    again = runner.run(wf).node_results["i"]
    assert again.status == "executed" and again.anchors["out"].row_count == 4
    assert runner.run(wf).node_results["i"].status == "cached"
    target = month / "relatorio_outubro.pdf"
    shutil.copy(FIX / "relatorio_novembro.pdf", target)
    os.utime(target, ns=(target.stat().st_atime_ns, target.stat().st_mtime_ns + 10**9))
    assert runner.run(wf).node_results["i"].status == "executed"
    store.pdfs.save_recipe(src.id, recipe().model_copy(update={"tabelas": []}))
    assert runner.run(wf).node_results["i"].status == "executed"  # a extração mudou


def test_correcao_so_neste_documento(store: DatasetStore, month: Path) -> None:
    """CA-16: corrigido, o documento passa; o conteúdo do PDF mudou, a correção deixa de valer."""
    src = make(store, month, policy="todos")
    with pytest.raises(InvalidInputError):
        store.pdfs.add_correction(src.id, "relatorio_dois_totais.pdf", "total_liquido", "a definir")
    fix = store.pdfs.add_correction(src.id, "relatorio_dois_totais.pdf", "total_liquido", "149.500,00")
    assert fix.quem and fix.estado_original == "ambiguo"
    frame, _ = store.pdfs.read(src.id, "campos")
    row = frame.filter(frame["documento"] == "relatorio_dois_totais.pdf").row(0, named=True)
    assert row["situacao"] == "Aprovado" and row["total_liquido"] == Decimal("149500.00")
    assert row["corrigidos"] == "total_liquido"
    origin, _ = store.pdfs.read(src.id, "origem")
    assert "corrigido só neste documento" in origin["regra"].to_list()
    target = month / "relatorio_dois_totais.pdf"
    shutil.copy(FIX / "relatorio_invalido.pdf", target)
    os.utime(target, ns=(target.stat().st_atime_ns, target.stat().st_mtime_ns + 10**9))
    frame, _ = store.pdfs.read(src.id, "campos")
    row = frame.filter(frame["documento"] == "relatorio_dois_totais.pdf").row(0, named=True)
    assert row["corrigidos"] == "" and row["situacao"] == "Falhou"
    store.pdfs.remove_correction(src.id, fix.id)
    with pytest.raises(NotFoundError):
        store.pdfs.remove_correction(src.id, fix.id)


def test_pdf_ilegivel_vira_falha_com_motivo(store: DatasetStore, tmp_path: Path) -> None:
    folder = tmp_path / "ruins"
    folder.mkdir()
    for name in ("escaneado", "protegido", "quebrado"):
        shutil.copy(FIX / f"relatorio_{name}.pdf", folder / f"{name}.pdf")
    src = make(store, folder, pattern="*.pdf", policy="todos")
    failures, _ = store.pdfs.read(src.id, "falhas")
    reasons = dict(zip(failures["documento"], failures["motivo"], strict=True))
    assert reasons == {
        "escaneado.pdf": "página sem texto legível (escaneada?)",
        "protegido.pdf": "protegido por senha",
        "quebrado.pdf": "arquivo danificado ou incompleto",
    }


# ------------------------------------------------------------------ API


def test_api_do_editor(client: TestClient, month: Path) -> None:
    created = client.post(
        "/api/pdfs", json={"name": "Relatórios", "mode": "pasta", "path": str(month)}
    ).json()
    sid = created["id"]
    assert created["status"]["draft"] and created["status"]["files"] == 3
    docs = client.get(f"/api/pdfs/{sid}/docs").json()["docs"]
    assert [d["key"] for d in docs] == [
        "relatorio_dois_totais.pdf",
        "relatorio_novembro.pdf",
        "relatorio_outubro.pdf",
    ]
    info = client.get(f"/api/pdfs/{sid}/docs/words", params={"doc": "relatorio_outubro.pdf"}).json()
    assert info["pages"][0]["t"] == 0 and info["assinatura"]
    png = client.get(
        f"/api/pdfs/{sid}/docs/page.png", params={"doc": "relatorio_outubro.pdf", "page": 1, "escala": 1}
    )
    assert png.status_code == 200 and png.content.startswith(b"\x89PNG")
    picked = [w for w in info["words"] if w["t"] == "834.086,00" and w["p"] == 0]
    sug = client.post(
        f"/api/pdfs/{sid}/suggest/field", json={"doc": "relatorio_outubro.pdf", "words": picked}
    ).json()
    assert sug["campo"]["nome"] == "total_liquido" and sug["resultado"]["valor"] == "834086.00"
    body = {
        "recipe": {"id": "nova", "nome": "x", "campos": [{**sug["campo"], "obrigatorio": True}]},
        "limit": 2,
    }
    impact = client.post(f"/api/pdfs/{sid}/evaluate", json=body).json()
    assert impact["evaluated"] == 2 and impact["total"] == 3  # "2 de 3 avaliados"
    assert impact["fields"]["total_liquido"] == {"ambiguo": 1, "encontrado": 1}
    saved = client.put(f"/api/pdfs/{sid}/recipe", json=body["recipe"]).json()
    assert saved["recipe"]["revisao"] == 1 and saved["outputs"] == ["campos", "falhas", "origem"]
    preview = client.get(f"/api/pdfs/{sid}/outputs/campos").json()
    assert preview["row_count"] == 3 and preview["stops"] is True and preview["failed"] == 1
    fix = client.post(
        f"/api/pdfs/{sid}/corrections",
        json={"doc": "relatorio_dois_totais.pdf", "field": "total_liquido", "value": "150.000,00"},
    ).json()
    assert client.get(f"/api/pdfs/{sid}/outputs/campos").json()["stops"] is False
    assert client.delete(f"/api/pdfs/{sid}/corrections/{fix['id']}").status_code == 204
    entry = next(p for p in client.get("/api/pdfs").json() if p["id"] == sid)
    assert entry["status"]["revision"] == 1 and entry["status"]["fields"] == 1


def test_api_envio_e_pdf_ilegivel(client: TestClient) -> None:
    files = {
        "file": ("relatorio escaneado.pdf", (FIX / "relatorio_escaneado.pdf").read_bytes(), "application/pdf")
    }
    created = client.post("/api/pdfs/upload", files=files).json()
    assert created["stored"] and created["name"] == "relatorio escaneado"
    info = client.get(
        f"/api/pdfs/{created['id']}/docs/words", params={"doc": Path(created["path"]).name}
    ).json()
    assert info["erro"] == "sem_texto" and "escaneada" in info["mensagem"]
    bad = client.post("/api/pdfs/upload", files={"file": ("x.pdf", b"isto nao e pdf", "application/pdf")})
    assert bad.status_code == 400
    assert client.delete(f"/api/pdfs/{created['id']}").status_code == 204
    assert not Path(created["path"]).exists()  # a cópia enviada sai junto


def test_documento_fora_da_fonte_e_recusado(client: TestClient, month: Path) -> None:
    sid = client.post("/api/pdfs", json={"name": "R", "mode": "pasta", "path": str(month)}).json()["id"]
    outside = client.get(f"/api/pdfs/{sid}/docs/words", params={"doc": "..\\..\\segredo.pdf"})
    assert outside.status_code == 404


# ------------------------------------------------------------------ extrações salvas (RF-3705)


def test_extracoes_salvas_usar_copiar_e_excluir(store: DatasetStore, month: Path, tmp_path: Path) -> None:
    src = make(store, month, policy="todos")
    rid = src.recipe
    other_dir = tmp_path / "outra"
    other_dir.mkdir()
    shutil.copy(FIX / "relatorio_novembro.pdf", other_dir / "relatorio_x.pdf")
    other = store.pdfs.save(PdfSource(name="Outra filial", mode="pasta", path=str(other_dir)))
    store.pdfs.use_recipe(other.id, rid)  # a mesma extração, compartilhada
    lib = {r["id"]: r for r in store.pdfs.recipe_library()}
    assert {f["name"] for f in lib[rid]["fontes"]} == {"Relatórios", "Outra filial"}
    assert store.pdfs.read(other.id, "campos")[0]["total_liquido"].to_list() == [Decimal("195880.75")]
    copy = store.pdfs.fork_recipe(other.id)  # independente: mudar a cópia não mexe na original
    assert copy.id != rid and copy.nome == "Relatório de vendas (cópia)" and copy.revisao == 1
    store.pdfs.save_recipe(other.id, copy.model_copy(update={"tabelas": []}))
    assert store.pdfs.get_recipe(rid).tabelas and not store.pdfs.get_recipe(copy.id).tabelas
    with pytest.raises(ConflictError):
        store.pdfs.delete_recipe(rid)  # em uso: pede confirmação
    assert store.pdfs.delete_recipe(rid, force=True) == ["Relatórios"]
    assert store.pdfs.status(store.pdfs.get(src.id)).draft  # a fonte volta a rascunho
    store.pdfs.delete(other.id)
    assert any(r["id"] == copy.id for r in store.pdfs.recipe_library())  # excluir a fonte guarda a extração


def test_exportar_e_importar_extracao(client: TestClient, month: Path) -> None:
    sid = client.post("/api/pdfs", json={"name": "R", "mode": "pasta", "path": str(month)}).json()["id"]
    client.put(f"/api/pdfs/{sid}/recipe", json=recipe().model_dump(mode="json"))
    rid = next(r["id"] for r in client.get("/api/pdfs/recipes").json() if r["nome"] == "Relatório de vendas")
    out = client.get(f"/api/pdfs/recipes/{rid}/export")
    assert 'filename="Relatorio_de_vendas.extracao.json"' in out.headers["content-disposition"]
    body = out.json()
    assert body["tipo"] == "extracao-pdf" and "id" not in body["extracao"]
    assert str(month) not in out.text  # sem caminho no arquivo
    other = client.post("/api/pdfs", json={"name": "Nova", "mode": "pasta", "path": str(month)}).json()["id"]
    imported = client.post(
        "/api/pdfs/recipes/import",
        files={"file": ("x.extracao.json", out.content, "application/json")},
        data={"source": other},
    ).json()
    assert imported["recipe"]["id"] != rid and imported["recipe"]["nome"] == "Relatório de vendas (2)"
    entry = next(p for p in client.get("/api/pdfs").json() if p["id"] == other)
    assert entry["recipe"] == imported["recipe"]["id"] and not entry["status"]["draft"]
    bad = client.post(
        "/api/pdfs/recipes/import", files={"file": ("x.json", b'{"campos": 3}', "application/json")}
    )
    assert bad.status_code == 400
    assert client.delete(f"/api/pdfs/recipes/{rid}").status_code == 409
    assert client.delete(f"/api/pdfs/recipes/{rid}?force=true").json()["detached"] == ["R"]
    created = client.post(
        "/api/pdfs",
        json={
            "name": "Com extração",
            "mode": "pasta",
            "path": str(month),
            "recipe": imported["recipe"]["id"],
        },
    ).json()
    assert created["recipe"] == imported["recipe"]["id"]


# ------------------------------------------------------------------ exemplo com PDFs reais da Receita Federal


def test_exemplo_da_receita_le_os_tres_meses(runner: WorkflowRunner, store: DatasetStore) -> None:
    """Os relatórios reais do pacote, com a extração pronta: os três meses aprovados, inclusive setembro, que mudou o
    cabeçalho da tabela."""
    from prodata.samples.pdfs import SOURCE_ID

    campos, _ = store.pdfs.read(SOURCE_ID, "campos")
    assert campos["situacao"].to_list() == ["Aprovado", "Aprovado", "Aprovado"]
    assert [d.isoformat() for d in campos["competencia"].to_list()] == [
        "2026-07-01",
        "2026-08-01",
        "2026-09-01",
    ]
    assert campos["receita_administrada_rfb"].to_list() == [268859, 227865, 231426]
    itens, _ = store.pdfs.read(SOURCE_ID, "itens_acumulado_no_ano")
    assert itens.height == 35 * 3
    first = itens.filter(itens["documento"] == "arrecadacao_2026-08.pdf").row(0, named=True)
    assert first["receita"] == "IMPOSTO SOBRE IMPORTAÇÃO" and first["arrecadado_ano_atual"] == 70182


def test_demonstracao_salva_ganha_a_secao_do_pdf() -> None:
    from prodata.samples.workflows import PDF_VISUALS, add_pdf_section, demo_workflow

    saved = demo_workflow()
    saved["nodes"] = [n for n in saved["nodes"] if not n["id"].startswith("n_pdf")]
    saved["containers"] = [c for c in saved["containers"] if c["id"] != "c_pdf"]
    saved["edges"] = [e for e in saved["edges"] if not e["id"].startswith("e_pdf")]
    saved["dashboard"]["items"] = [
        i for i in saved["dashboard"]["items"] if not str(i.get("node_id", "")).startswith("n_pdf")
    ]
    moved = next(n for n in saved["nodes"] if n["id"] == "n_clientes")
    moved["y"] = 2000  # a pessoa mudou uma caixa de lugar: a seção nova entra abaixo dela
    assert add_pdf_section(saved) is True
    box = next(c for c in saved["containers"] if c["id"] == "c_pdf")
    assert box["y"] > 2000
    shown = {i.get("node_id") for i in saved["dashboard"]["items"]}
    assert {n for n, _ in PDF_VISUALS} <= shown and not set(
        saved["dashboard"]["hidden"]
    ) & shown  # no dashboard
    joined = {(e["source"], e["target"]) for e in saved["edges"]}
    assert ("n_vendas", "n_pdf_vendas_mes") in joined  # ligada ao resto do fluxo
    assert add_pdf_section(saved) is False  # uma vez só


def test_etapa_antiga_do_pdf_e_atualizada() -> None:
    """Quem tem a primeira versão da etapa 6 recebe as caixas novas; as que continuam no lugar de antes se mudam."""
    from prodata.samples.workflows import COL, add_pdf_section, demo_workflow

    saved = demo_workflow()
    box = next(c for c in saved["containers"] if c["id"] == "c_pdf")
    keep = {"n_pdf_campos", "n_pdf_chart", "n_pdf_itens"}
    saved["nodes"] = [n for n in saved["nodes"] if not n["id"].startswith("n_pdf") or n["id"] in keep]
    old = {"n_pdf_chart": (COL[1], box["y"] + 70), "n_pdf_itens": (COL[3], box["y"] + 70)}
    for n in saved["nodes"]:
        if n["id"] in old:
            n["x"], n["y"] = old[n["id"]]
    # como era a primeira versão: o gráfico ligado direto ao resumo, por competência, em milhões
    v1_edge = {
        "id": "e_pdf1",
        "source": "n_pdf_campos",
        "sourceHandle": "out",
        "target": "n_pdf_chart",
        "targetHandle": "in",
    }
    saved["edges"] = [e for e in saved["edges"] if not e["id"].startswith("e_pdf")] + [v1_edge]
    chart_v1 = next(n for n in saved["nodes"] if n["id"] == "n_pdf_chart")
    chart_v1["config"] = {
        **chart_v1["config"],
        "x_column": "competencia",
        "y_column": "receita_administrada_rfb",
    }
    saved["dashboard"]["hidden"].append("n_pdf_chart")
    assert add_pdf_section(saved) is True
    ids = {n["id"] for n in saved["nodes"]}
    assert {"n_pdf_join", "n_pdf_tributos", "n_pdf_indice_chart"} <= ids
    chart = next(n for n in saved["nodes"] if n["id"] == "n_pdf_chart")
    assert (chart["x"], chart["y"]) == (COL[4], box["y"] + 190)  # saiu do caminho do "Mês do relatório"
    assert chart["config"]["x_column"] == "mes" and "e_pdf1" not in {e["id"] for e in saved["edges"]}
    assert "n_pdf_chart" not in saved["dashboard"]["hidden"]


def test_logo_do_exemplo_segue_a_marca() -> None:
    import base64

    from prodata.samples.demo_logo import LOGO, refresh_demo_logo
    from prodata.samples.workflows import demo_workflow

    saved = demo_workflow()
    logo = next(i for i in saved["dashboard"]["items"] if i["id"] == "d_logo")
    other = next(p for p in LOGO.parents[1].glob("*/logo-claro.svg") if p != LOGO)
    logo["content"] = "data:image/svg+xml;base64," + base64.b64encode(other.read_bytes()).decode()
    assert refresh_demo_logo(saved) is True
    assert logo["content"] == "data:image/svg+xml;base64," + base64.b64encode(LOGO.read_bytes()).decode()
    logo["content"] = "data:image/png;base64,AAAA"  # imagem da própria pessoa: fica
    assert refresh_demo_logo(saved) is False and logo["content"].endswith("AAAA")


def test_logo_da_protege_sai_no_programa_instalado(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """O instalado só traz a pasta da marca ativa: o logo antigo é reconhecido pela impressão, não pelo arquivo."""
    import base64

    from prodata.samples import demo_logo, workflows

    root = Path(workflows.__file__).resolve().parents[1] / "marcas"
    only = tmp_path / "marcas" / "desata"
    only.mkdir(parents=True)
    (only / "logo-claro.svg").write_bytes((root / "desata" / "logo-claro.svg").read_bytes())
    monkeypatch.setattr(demo_logo, "LOGO", only / "logo-claro.svg")
    saved = workflows.demo_workflow()
    logo = next(i for i in saved["dashboard"]["items"] if i["id"] == "d_logo")
    protege = (root / "protege" / "logo-claro.svg").read_bytes().replace(b"\n", b"\r\n")  # salvo com CRLF
    logo["content"] = "data:image/svg+xml;base64," + base64.b64encode(protege).decode()
    assert demo_logo.refresh_demo_logo(saved) is True
    assert base64.b64decode(logo["content"].split(",", 1)[1]) == (only / "logo-claro.svg").read_bytes()


def test_impressoes_cobrem_os_logos_das_marcas() -> None:
    from prodata.samples import demo_logo

    root = Path(demo_logo.__file__).resolve().parents[1] / "marcas"
    for path in root.glob("*/logo-*.svg"):
        assert demo_logo._svg_digest(path.read_bytes()) in demo_logo.KNOWN_LOGOS, path


def test_exemplo_reaponta_os_pdfs_do_pacote(store: DatasetStore, tmp_path: Path) -> None:
    """Portátil descompactado em outra pasta: a fonte do exemplo volta a achar os PDFs."""
    from prodata.samples.pdfs import FOLDER, SOURCE_ID, refresh_example_pdfs

    old = tmp_path / "antigo" / "pdf_receita"
    old.mkdir(parents=True)
    source = store.pdfs.get(SOURCE_ID)
    store.pdfs.save(source.model_copy(update={"path": str(old)}), previous=SOURCE_ID)
    refresh_example_pdfs(store.pdfs)
    assert Path(store.pdfs.get(SOURCE_ID).path) == FOLDER


# ------------------------------------------------------------------ documentos um a um (RF-3706)


def test_tirar_e_trazer_de_volta_sem_apagar_o_arquivo(store: DatasetStore, month: Path) -> None:
    """CA-17: o PDF tirado sai das saídas e da contagem, continua no disco e volta com Trazer de volta."""
    pdfs = store.pdfs
    source = make(store, month, policy="todos")
    assert pdfs.status(source).files == 3
    assert pdfs.leave_out(source.id, "relatorio_dois_totais.pdf") is False  # arquivo da pessoa: não apaga
    source = pdfs.get(source.id)
    assert (month / "relatorio_dois_totais.pdf").is_file()
    assert [p.name for p in pdfs.files_of(source)] == ["relatorio_novembro.pdf", "relatorio_outubro.pdf"]
    assert [p.name for p in pdfs.left_out_files(source)] == ["relatorio_dois_totais.pdf"]
    st = pdfs.status(source)
    assert (st.files, st.left_out) == (2, 1)
    campos, _ = pdfs.read(source.id, "campos")
    assert sorted(campos["documento"].to_list()) == ["relatorio_novembro.pdf", "relatorio_outubro.pdf"]
    # o cadastro (formulário) não mexe nas listas de documentos
    pdfs.save(source.model_copy(update={"left_out": [], "name": "Relatórios do mês"}), previous=source.id)
    assert pdfs.get(source.id).left_out == ["relatorio_dois_totais.pdf"]
    pdfs.bring_back(source.id, "relatorio_dois_totais.pdf")
    assert pdfs.status(pdfs.get(source.id)).files == 3
    with pytest.raises(NotFoundError):
        pdfs.bring_back(source.id, "relatorio_dois_totais.pdf")


def test_fonte_nunca_fica_sem_documento(store: DatasetStore, month: Path) -> None:
    pdfs = store.pdfs
    source = make(store, month)
    pdfs.leave_out(source.id, "relatorio_dois_totais.pdf")
    pdfs.leave_out(source.id, "relatorio_novembro.pdf")
    with pytest.raises(InvalidInputError, match="pelo menos um PDF"):
        pdfs.leave_out(source.id, "relatorio_outubro.pdf")
    with pytest.raises(NotFoundError):
        pdfs.leave_out(source.id, "nao_existe.pdf")


def test_adicionar_pdfs_guarda_copia_e_nao_toca_a_pasta(store: DatasetStore, month: Path) -> None:
    """CA-17: dois PDFs somados a uma fonte de um PDF: três documentos, a pasta original intacta."""
    pdfs = store.pdfs
    single = pdfs.save(PdfSource(name="Outubro", mode="arquivo", path=str(month / "relatorio_outubro.pdf")))
    pdfs.save_recipe(single.id, recipe())
    before = sorted(p.name for p in month.iterdir())
    data = (FIX / "relatorio_novembro.pdf").read_bytes()
    names = pdfs.add_files(single.id, [("relatorio_novembro.pdf", data), ("relatorio_outubro.pdf", data)])
    assert names == [
        "relatorio_novembro.pdf",
        "relatorio_outubro_2.pdf",
    ]  # nome já usado na fonte ganha outro
    assert sorted(p.name for p in month.iterdir()) == before
    source = pdfs.get(single.id)
    assert pdfs.status(source).files == 3
    assert all(Path(p).parent == pdfs.uploads for p in source.added)
    # um arquivo ruim não deixa metade somada
    with pytest.raises(InvalidInputError):
        pdfs.add_files(single.id, [("bom.pdf", data), ("ruim.pdf", b"isto nao e pdf")])
    assert pdfs.get(single.id).added == source.added and not (pdfs.uploads / "bom.pdf").exists()
    # tirar uma cópia do programa apaga a cópia
    copy_path = Path(source.added[1])
    assert pdfs.leave_out(single.id, copy_path.name) is True
    assert not copy_path.exists() and pdfs.status(pdfs.get(single.id)).files == 2
    # duplicar leva cópias próprias; excluir a fonte apaga as dela e deixa as da outra
    twin = pdfs.duplicate(single.id)
    assert twin.added and set(twin.added).isdisjoint(pdfs.get(single.id).added)
    kept = pdfs.get(single.id).added
    pdfs.delete(twin.id)
    assert all(not Path(p).exists() for p in twin.added) and all(Path(p).exists() for p in kept)


def test_api_documentos_um_a_um(client: TestClient, month: Path) -> None:
    sid = client.post("/api/pdfs", json={"name": "R", "mode": "pasta", "path": str(month)}).json()["id"]
    left = client.post(f"/api/pdfs/{sid}/docs/leave", json={"name": "relatorio_outubro.pdf"}).json()
    assert left["deleted"] is False and left["source"]["status"]["left_out"] == 1
    docs = client.get(f"/api/pdfs/{sid}/docs").json()
    assert docs["left_out"] == [{"name": "relatorio_outubro.pdf", "added": False}]
    assert "relatorio_outubro.pdf" not in {d["name"] for d in docs["docs"]}
    data = (FIX / "relatorio_novembro.pdf").read_bytes()
    files = [
        ("files", ("extra um.pdf", data, "application/pdf")),
        ("files", ("extra dois.pdf", data, "application/pdf")),
    ]
    added = client.post(f"/api/pdfs/{sid}/docs/add", files=files).json()
    assert added["added"] == ["extra_um.pdf", "extra_dois.pdf"] and added["source"]["status"]["files"] == 4
    assert {d["name"]: d["added"] for d in client.get(f"/api/pdfs/{sid}/docs").json()["docs"]}["extra_um.pdf"]
    back = client.post(f"/api/pdfs/{sid}/docs/back", json={"name": "relatorio_outubro.pdf"}).json()
    assert back["status"]["files"] == 5 and back["status"]["left_out"] == 0
    bad = client.post(f"/api/pdfs/{sid}/docs/add", files=[("files", ("x.pdf", b"nada", "application/pdf"))])
    assert bad.status_code == 400


def test_api_borda_da_tabela(client: TestClient, month: Path) -> None:
    """RF-3735: a borda de baixo arrastada até o meio dos dados corta em N linhas; a de cima escolhe o cabeçalho."""
    sid = client.post("/api/pdfs", json={"name": "R", "mode": "pasta", "path": str(month)}).json()["id"]
    table = recipe().tabelas[0].model_dump(mode="json")
    doc = "relatorio_outubro.pdf"
    out = client.post(
        f"/api/pdfs/{sid}/suggest/table_edge",
        json={"doc": doc, "page": 0, "edge": "bottom", "pos": 0.30, "tabela": table},
    )
    assert (
        out.status_code == 200
        and out.json()["tabela"]["max_linhas"] >= 1
        and out.json()["tabela"]["fim"] == []
    )
    top = client.post(
        f"/api/pdfs/{sid}/suggest/table_edge",
        json={"doc": doc, "page": 0, "edge": "top", "pos": 0.0, "tabela": table},
    )
    assert top.status_code == 200 and top.json()["tabela"]["linhas_cabecalho"] == 1
    bad = client.post(
        f"/api/pdfs/{sid}/suggest/table_edge",
        json={"doc": doc, "page": 0, "edge": "meio", "pos": 0.5, "tabela": table},
    )
    assert bad.status_code == 422
