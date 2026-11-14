"""Leitor visual de PDF (spec 037): tipos, leitura, motor de extração, sugestões e leitura isolada."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from prodata.documents import reader
from prodata.documents.extract import AMBIGUO, AUSENTE, ENCONTRADO, FALHOU, INVALIDO, extract, unsupported
from prodata.documents.recipe import FieldSpec, LabelRule, PositionRule, Recipe, TableSpec
from prodata.documents.suggest import suggest_field, suggest_table
from prodata.documents.types import InvalidValueError, convert, guess_type
from prodata.documents.worker import PdfWorker

FIX = Path(__file__).parent / "fixtures" / "pdf"


@pytest.fixture(scope="module")
def docs() -> dict[str, dict]:
    return {
        n: reader.inspect(str(FIX / f"relatorio_{n}.pdf"))
        for n in ("outubro", "novembro", "dois_totais", "invalido")
    }


def _words(info: dict, text: str, page: int = 0) -> list[dict]:
    return [w for w in info["words"] if w["t"] == text and w["p"] == page]


# ------------------------------------------------------------------ tipos


@pytest.mark.parametrize(
    ("text", "kind", "value"),
    [
        ("R$ 125.430,00", "moeda", Decimal("125430.00")),
        ("-1.234,5", "moeda", Decimal("-1234.50")),
        ("(300,00)", "moeda", Decimal("-300.00")),
        ("1.234", "inteiro", 1234),
        ("12.5", "decimal", Decimal("12.5")),
        ("10/2026", "mes_ano", date(2026, 10, 1)),
        ("outubro/2026", "mes_ano", date(2026, 10, 1)),
        ("31/12/2026", "data", date(2026, 12, 31)),
        ("5 de março de 2026", "data", date(2026, 3, 5)),
        ("Não", "sim_nao", False),
    ],
)
def test_converte_no_padrao_brasileiro(text: str, kind: str, value: object) -> None:
    assert convert(text, kind) == value


@pytest.mark.parametrize(
    ("text", "kind"),
    [("a definir", "moeda"), ("1,234,5", "decimal"), ("12,5", "inteiro"), ("31/02/2026", "data")],
)
def test_nao_inventa_valor(text: str, kind: str) -> None:
    with pytest.raises(InvalidValueError) as exc:
        convert(text, kind)
    assert text not in str(exc.value)  # a mensagem não repete o conteúdo


def test_adivinha_o_tipo() -> None:
    assert guess_type("R$ 1.200,00") == "moeda"
    assert guess_type("10/2026") == "mes_ano"
    assert guess_type("15/10/2026") == "data"
    assert guess_type("42") == "inteiro"
    assert guess_type("Controladoria") == "texto"


# ------------------------------------------------------------------ leitura


def test_caixas_normalizadas_e_pagina_girada() -> None:
    info = reader.inspect(str(FIX / "relatorio_girado.pdf"))
    first = info["pages"][0]
    assert first["r"] == 90 and first["w"] > first["h"]  # deitada, como aparece
    assert all(0 <= v <= 1 for w in info["words"] for v in w["b"])


@pytest.mark.parametrize(
    ("name", "code"),
    [("escaneado", "sem_texto"), ("protegido", "protegido"), ("quebrado", "malformado")],
)
def test_pdf_ilegivel_vira_codigo(name: str, code: str) -> None:
    with pytest.raises(reader.PdfReadError) as exc:
        reader.inspect(str(FIX / f"relatorio_{name}.pdf"))
    assert exc.value.code == code


def test_protegido_abre_com_senha() -> None:
    assert reader.inspect(str(FIX / "relatorio_protegido.pdf"), password="segredo")["words"]


def test_imagem_respeita_limite_de_pixels(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reader, "MAX_PIXELS", 200_000)
    png = reader.render(str(FIX / "relatorio_outubro.pdf"), 0, 4.0)
    from io import BytesIO

    from PIL import Image

    w, h = Image.open(BytesIO(png)).size
    assert w * h <= 200_000 * 1.01


# ------------------------------------------------------------------ campos e tabela


def _recipe(docs: dict) -> Recipe:
    out = docs["outubro"]
    total = suggest_field(out, _words(out, "834.086,00"))
    comp = suggest_field(out, _words(out, "10/2026"))
    table = suggest_table(out, 0, (0.05, 0.18, 0.95, 0.40), "vendas")
    return Recipe(
        id="vendas",
        nome="Relatório de vendas",
        campos=[{**total["campo"], "obrigatorio": True}, comp["campo"]],
        tabelas=[table["tabela"]],
    )


def test_marcar_valor_propoe_campo_conferido(docs: dict) -> None:
    """CA-01: marcar o valor dá nome, tipo, como encontrar e o valor convertido com a origem."""
    s = suggest_field(docs["outubro"], _words(docs["outubro"], "834.086,00"))
    assert s["campo"]["nome"] == "total_liquido" and s["campo"]["tipo"] == "moeda"
    assert s["campo"]["regra"] == {
        "tipo": "rotulo",
        "rotulos": ["Total líquido"],
        "direcao": "direita",
        "distancia": 0.3,
    }
    assert s["fragil"] is False and s["resultado"]["estado"] == ENCONTRADO
    assert s["resultado"]["valor"] == "834086.00"
    assert s["resultado"]["candidatos"][0]["origem"][0]["p"] == 0


def test_sem_rotulo_cai_na_posicao_fragil(docs: dict) -> None:
    s = suggest_field(docs["outubro"], _words(docs["outubro"], "RELATÓRIO"))
    assert s["fragil"] is True and s["campo"]["regra"]["tipo"] == "posicao"


def test_mesma_regra_com_cabecalho_deslocado(docs: dict) -> None:
    """CA-02."""
    result = extract(_recipe(docs), docs["novembro"])
    assert result.estado == "aprovado"
    assert result.campos[0].valor == Decimal("195880.75")


def test_dois_totais_ficam_ambiguos(docs: dict) -> None:
    """CA-03: nenhum valor escolhido, os dois candidatos voltam com origem."""
    result = extract(_recipe(docs), docs["dois_totais"])
    total = result.campos[0]
    assert total.estado == AMBIGUO and total.valor is None
    assert sorted(c.texto for c in total.candidatos) == ["R$ 149.500,00", "R$ 150.000,00"]
    assert result.estado == FALHOU  # é obrigatório


def test_invalido_e_ausente(docs: dict) -> None:
    result = extract(_recipe(docs), docs["invalido"])
    assert [f.estado for f in result.campos] == [INVALIDO, AUSENTE]
    assert result.campos[1].motivo == "rótulo não encontrado"


def test_tabela_une_celula_de_varias_linhas(docs: dict) -> None:
    """CA-04: uma linha por filial; a observação quebrada vira uma célula só, com a origem das duas linhas."""
    table = extract(_recipe(docs), docs["novembro"]).tabelas[0]
    assert [r.cells[0].texto for r in table.linhas][:3] == ["São Paulo", "Rio de Janeiro", "Belo Horizonte"]
    rio = table.linhas[1]
    assert rio.linhas == 2
    assert rio.cells[2].texto.endswith("e o ajuste da nota de crédito")


def test_tabela_continua_na_pagina_seguinte(docs: dict) -> None:
    """CA-05: todas as linhas das duas páginas, sem o cabeçalho repetido, até 'Total geral'."""
    table = extract(_recipe(docs), docs["outubro"]).tabelas[0]
    assert len(table.linhas) == 32 and table.fim == "texto de fim"
    assert sum(r.cells[1].valor for r in table.linhas) == Decimal("834086.00")
    assert {i["motivo"] for i in table.ignoradas} == {"cabeçalho repetido", "fim da tabela"}
    assert {r.cells[0].words[0]["p"] for r in table.linhas} == {0, 1}


def test_tabela_sem_cabecalho_mostra_problema(docs: dict) -> None:
    spec = TableSpec(nome="t", cabecalho=["Produto", "Quantidade"], colunas=[{"nome": "a"}])
    result = extract(Recipe(id="x", nome="x", tabelas=[spec]), docs["outubro"])
    assert result.tabelas[0].problema == "não achei o cabeçalho da tabela" and not result.tabelas[0].linhas


def test_rotulo_ignora_acento_e_maiuscula(docs: dict) -> None:
    rule = LabelRule(rotulos=["Valor líquido", "TOTAL LIQUIDO"])
    result = extract(
        Recipe(id="x", nome="x", campos=[FieldSpec(nome="t", tipo="moeda", regra=rule)]), docs["novembro"]
    )
    assert result.campos[0].estado == ENCONTRADO


def test_documento_ilegivel_nao_suportado(docs: dict) -> None:
    result = unsupported(_recipe(docs), "sem texto")
    assert result.estado == FALHOU and {f.estado for f in result.campos} == {"nao_suportado"}


def test_digest_muda_so_com_o_que_muda_o_resultado(docs: dict) -> None:
    rec = _recipe(docs)
    assert rec.model_copy(update={"nome": "Outro", "revisao": 2}).digest() == rec.digest()
    changed = rec.model_copy(update={"campos": [*rec.campos[:1]]})
    assert changed.digest() != rec.digest()


def test_receita_valida_guias_e_area() -> None:
    with pytest.raises(ValueError):
        TableSpec(nome="t", cabecalho=["a"], colunas=[{"nome": "a"}, {"nome": "b"}], guias=[])
    with pytest.raises(ValueError):
        PositionRule(pagina=0, area=(0.5, 0.5, 0.2, 0.9))


# ------------------------------------------------------------------ leitura isolada


def test_leitura_isolada_aguenta_falhas() -> None:
    with PdfWorker(timeout=20, memory_mb=600, test_ops=True) as worker:
        assert worker.call("inspect", path=str(FIX / "relatorio_novembro.pdf"))["words"]
        with pytest.raises(reader.PdfReadError) as exc:
            worker.call("inspect", path=str(FIX / "relatorio_quebrado.pdf"))
        assert exc.value.code == "malformado"
        with pytest.raises(reader.PdfReadError) as exc:
            worker.call("_dormir", timeout=1.5, segundos=30)
        assert exc.value.code == "tempo_esgotado"
        with pytest.raises(reader.PdfReadError) as exc:
            worker.call("_consumir", mb=2000)
        assert exc.value.code in {"memoria", "leitor_caiu"}
        assert worker.call("inspect", path=str(FIX / "relatorio_novembro.pdf"))["words"]  # sobe de novo


# ------------------------------------------------------------------ cache


def test_cache_refaz_quando_o_pdf_muda(tmp_path: Path, docs: dict) -> None:
    """S09: o mesmo arquivo não é relido; trocar o conteúdo com o mesmo nome refaz palavras e extração."""
    import os
    import shutil

    from prodata.documents.cache import DocumentCache

    rec = _recipe(docs)
    target = tmp_path / "relatorio.pdf"
    shutil.copy(FIX / "relatorio_outubro.pdf", target)
    with PdfWorker(timeout=20) as worker:
        cache = DocumentCache(tmp_path / "cache", worker)
        first = cache.extract(target, rec)
        assert first["campos"][0]["valor"] == "834086.00"
        cache.extract(target, rec)
        cache.words(target)
        assert cache.reads == 1
        shutil.copy(FIX / "relatorio_novembro.pdf", target)
        os.utime(target, ns=(target.stat().st_atime_ns, target.stat().st_mtime_ns + 10**9))
        second = cache.extract(target, rec)
        assert second["campos"][0]["valor"] == "195880.75" and cache.reads == 2
        assert second["assinatura"] != first["assinatura"]
        # outro cache no mesmo diretório (programa reaberto) aproveita o disco
        again = DocumentCache(tmp_path / "cache", worker)
        assert again.extract(target, rec)["campos"][0]["valor"] == "195880.75" and again.reads == 0
        # PDF quebrado: falha guardada, documento Não suportado, sem reler
        shutil.copy(FIX / "relatorio_quebrado.pdf", tmp_path / "q.pdf")
        broken = again.extract(tmp_path / "q.pdf", rec)
        assert broken["estado"] == FALHOU and broken["erro"] == "malformado"
        again.extract(tmp_path / "q.pdf", rec.model_copy(update={"campos": rec.campos[:1]}))
        assert again.reads == 1


@pytest.mark.parametrize("name", ["girado", "rotacao_interna"])
def test_mesma_extracao_em_pagina_girada(docs: dict, name: str) -> None:
    """Página girada na tela e conteúdo girado dentro do PDF: o motor lê na direção do texto e acha tudo."""
    info = reader.inspect(str(FIX / f"relatorio_{name}.pdf"))
    plain = extract(_recipe(docs), docs["novembro"])
    result = extract(_recipe(docs), info)
    assert result.estado == "aprovado"
    assert [f.valor for f in result.campos] == [f.valor for f in plain.campos]
    table, ref = result.tabelas[0], plain.tabelas[0]
    assert [[c.texto for c in r.cells] for r in table.linhas] == [
        [c.texto for c in r.cells] for r in ref.linhas
    ]
    # a origem volta em coordenadas de tela: na girada, o valor fica à direita da página (primeira linha à direita)
    origin = result.campos[0].candidatos[0].origem[0]["b"]
    if name == "girado":
        assert origin[0] > 0.5 and origin[3] - origin[1] > origin[2] - origin[0]  # caixa em pé
    else:
        assert origin[2] - origin[0] > origin[3] - origin[1]  # texto normal na tela


def test_tabela_marcada_em_pagina_girada() -> None:
    """A área vem da tela; a sugestão converte para o espaço de leitura e acha as mesmas colunas."""
    info = reader.inspect(str(FIX / "relatorio_girado.pdf"))
    # a área que a pessoa arrastaria na tela: do cabeçalho "Filial" até a última linha ("Recife")
    boxes = [w["b"] for w in info["words"] if w["t"] in ("Filial", "Recife")]
    area = (min(b[0] for b in boxes) - 0.01, 0.02, max(b[2] for b in boxes) + 0.003, 0.98)
    table = suggest_table(info, 0, area, "vendas")
    assert [c["nome"] for c in table["tabela"]["colunas"]] == ["filial", "valor", "observacao"]
    assert len(table["resultado"]["linhas"]) == 7
