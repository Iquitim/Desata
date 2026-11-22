"""Arquivos dos portais: prévia, conteúdo conferido, ZIP seguro e formato aceito (spec 049, T04d, CA-12)."""

from __future__ import annotations

import gzip
import io
import zipfile
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import polars as pl
import pytest

from prodata.catalog.http import CatalogClient, CatalogError
from prodata.catalog.readers import files
from prodata.errors import InvalidInputError

Server = Callable[[Callable[[httpx.Request], httpx.Response]], list[httpx.Request]]
URL = "https://dados.cvm.gov.br/dados/arquivo.csv"
CSV_LATIN1 = "município;valor_pago;data\nSão Paulo;1.234,56;01/02/2026\nCampinas;10,50;02/02/2026\n".encode(
    "latin-1"
)


def _serve(server: Server, body: bytes, **headers: str) -> list[httpx.Request]:
    return server(lambda r: httpx.Response(200, content=body, headers=headers))


def _zip(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buf.getvalue()


# ------------------------------------------------------------------ prévia


def test_csv_latin1_com_ponto_e_virgula_e_virgula_decimal(catalog_server: Server, tmp_path: Path) -> None:
    """CA-12: Latin-1, ";" e vírgula decimal aparecem certos na prévia."""
    _serve(catalog_server, CSV_LATIN1)
    with CatalogClient() as client:
        prev = files.preview(client, URL, tmp_path, "csv")
    assert prev["opcoes"]["delimiter"] == ";"
    assert prev["opcoes"]["decimal"] == ","
    assert prev["opcoes"]["encoding"] in ("cp1252", "latin-1")
    assert prev["linhas"][0]["município"] == "São Paulo"
    assert prev["linhas_total"] == 2
    assert [c for c, _ in prev["formato_aceito"]["colunas"]] == ["município", "valor_pago", "data"]


def test_prévia_aceita_opcoes_da_pessoa(catalog_server: Server, tmp_path: Path) -> None:
    body = "Relatório de 2026\n\na;b\n1;2\n".encode()
    _serve(catalog_server, body)
    with CatalogClient() as client:
        prev = files.preview(client, URL, tmp_path, "csv", options={"skip_rows": 2, "delimiter": ";"})
    assert [c["name"] for c in prev["colunas"]] == ["a", "b"]


def test_arquivo_vai_para_o_cache_com_nome_fixo(catalog_server: Server, tmp_path: Path) -> None:
    _serve(catalog_server, CSV_LATIN1)
    with CatalogClient() as client:
        files.preview(client, URL, tmp_path, "csv")
    saved = list((tmp_path / "arquivos").iterdir())
    assert [p.name for p in saved] == [files.cache_file(tmp_path, URL, "csv").name]
    assert not any(p.name.endswith(".parte") for p in saved)


# ------------------------------------------------------------------ conteúdo de verdade


def test_zip_rotulado_como_csv_e_aberto_como_zip(catalog_server: Server, tmp_path: Path) -> None:
    _serve(catalog_server, _zip({"leia-me.txt": b"ola", "dados.csv": b"a;b\n1;2\n"}))
    with CatalogClient() as client:
        prev = files.preview(client, URL, tmp_path, "csv")
    assert prev["formato"] == "zip"
    assert prev["membro"] == "dados.csv"  # tabela antes do leia-me
    assert prev["membros"] == ["dados.csv", "leia-me.txt"]


def test_gzip_e_descompactado(catalog_server: Server, tmp_path: Path) -> None:
    _serve(catalog_server, gzip.compress(b"a;b\n1;2\n3;4\n"))
    with CatalogClient() as client:
        prev = files.preview(client, URL, tmp_path, "csv")
    assert prev["linhas_total"] == 2


def test_xlsx_nao_e_confundido_com_zip(catalog_server: Server, tmp_path: Path) -> None:
    buf = io.BytesIO()
    pl.DataFrame({"uf": ["SP", "RJ"], "valor": [1.5, 2.5]}).write_excel(buf)
    _serve(catalog_server, buf.getvalue())
    with CatalogClient() as client:
        prev = files.preview(client, "https://dados.es.gov.br/a.xlsx", tmp_path, "xlsx")
    assert prev["formato"] == "xlsx"
    assert [c["name"] for c in prev["colunas"]] == ["uf", "valor"]


def test_parquet(catalog_server: Server, tmp_path: Path) -> None:
    buf = io.BytesIO()
    pl.DataFrame({"x": [1, 2, 3]}).write_parquet(buf)
    _serve(catalog_server, buf.getvalue())
    with CatalogClient() as client:
        prev = files.preview(client, "https://dadosabertos.aneel.gov.br/a.parquet", tmp_path, "parquet")
    assert prev["linhas_total"] == 3


@pytest.mark.parametrize(
    ("body", "match"),
    [
        (b"%PDF-1.7 ...", "PDF"),
        (b"<!DOCTYPE html><html><body>Manutencao</body></html>", "página da web"),
        (b"\xef\xbb\xbf  <html>erro</html>", "página da web"),
    ],
)
def test_pdf_e_pagina_disfarcados(body: bytes, match: str, catalog_server: Server, tmp_path: Path) -> None:
    _serve(catalog_server, body)
    with CatalogClient() as client, pytest.raises(InvalidInputError, match=match):
        files.preview(client, URL, tmp_path, "csv")


# ------------------------------------------------------------------ ZIP seguro


@pytest.mark.parametrize("name", ["../fora.csv", "/abs.csv", "C:/win.csv", "a/../../b.csv", "..\\x.csv"])
def test_zip_com_caminho_perigoso(name: str, catalog_server: Server, tmp_path: Path) -> None:
    _serve(catalog_server, _zip({name: b"a\n1\n"}))
    with CatalogClient() as client, pytest.raises(InvalidInputError, match="perigoso"):
        files.preview(client, URL, tmp_path, "zip")
    assert not (tmp_path.parent / "fora.csv").exists()


def test_bomba_de_zip(catalog_server: Server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(files, "MAX_ZIP_RATIO", 10)
    _serve(catalog_server, _zip({"a.csv": b"0" * 200_000}))
    with CatalogClient() as client, pytest.raises(InvalidInputError, match="grande demais"):
        files.preview(client, URL, tmp_path, "zip")


def test_zip_sem_tabela(catalog_server: Server, tmp_path: Path) -> None:
    _serve(catalog_server, _zip({"manual.pdf": b"%PDF"}))
    with CatalogClient() as client, pytest.raises(InvalidInputError, match="nenhum arquivo"):
        files.preview(client, URL, tmp_path, "zip")


# ------------------------------------------------------------------ tamanho e endereço


def test_acima_do_limite_para_e_nao_deixa_arquivo(
    catalog_server: Server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(files, "MAX_DIRECT_BYTES", 1000)
    _serve(catalog_server, b"a;b\n" + b"1;2\n" * 1000)
    with CatalogClient() as client, pytest.raises(CatalogError) as err:
        files.preview(client, URL, tmp_path, "csv")
    assert err.value.kind == "limite"
    assert not any((tmp_path / "arquivos").glob("*"))


def test_tamanho_declarado_acima_do_limite_nem_baixa(
    catalog_server: Server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(files, "MAX_DIRECT_BYTES", 10)
    chunks: list[int] = []

    def body() -> Iterator[bytes]:
        chunks.append(1)
        yield b"x" * 50

    catalog_server(lambda r: httpx.Response(200, content=body(), headers={"content-length": "50"}))
    with CatalogClient() as client, pytest.raises(CatalogError) as err:
        files.preview(client, URL, tmp_path, "csv")
    assert err.value.kind == "limite"
    assert chunks == []  # o tamanho declarado bastou: nada foi lido do corpo


def test_redirecionamento_para_fora_da_lista(catalog_server: Server, tmp_path: Path) -> None:
    seen = catalog_server(
        lambda r: httpx.Response(302, headers={"location": "https://armazenamento.exemplo.com/a.csv"})
    )
    with CatalogClient() as client, pytest.raises(CatalogError) as err:
        files.preview(client, URL, tmp_path, "csv")
    assert err.value.kind == "recusado"
    assert len(seen) == 1  # nenhum pedido ao site fora da lista


def test_redirecionamento_para_o_armazenamento_do_portal(catalog_server: Server, tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "dados.recife.pe.gov.br":
            return httpx.Response(
                302, headers={"location": "https://ckan-storage-download.app.emprel.gov.br/a.csv"}
            )
        return httpx.Response(200, content=b"a;b\n1;2\n")

    catalog_server(handler)
    with CatalogClient() as client:
        prev = files.preview(
            client, "https://dados.recife.pe.gov.br/dataset/x/resource/y/download/a.csv", tmp_path, "csv"
        )
    assert prev["linhas_total"] == 1


# ------------------------------------------------------------------ formato aceito


def test_leitura_com_o_formato_aceito(catalog_server: Server, tmp_path: Path) -> None:
    _serve(catalog_server, CSV_LATIN1)
    with CatalogClient() as client:
        prev = files.preview(client, URL, tmp_path, "csv")
        accepted = files.AcceptedFormat.model_validate(prev["formato_aceito"])
        result = files.read(client, URL, tmp_path, "csv", accepted)
    assert result.frame.height == 2
    assert result.frame.schema["valor_pago"].is_numeric()


def test_coluna_trocada_para_e_diz_o_que_mudou(catalog_server: Server, tmp_path: Path) -> None:
    """CA-12: o órgão troca uma coluna; a execução para com o que mudou e oferece o novo formato."""
    _serve(catalog_server, CSV_LATIN1)
    with CatalogClient() as client:
        accepted = files.AcceptedFormat.model_validate(
            files.preview(client, URL, tmp_path, "csv")["formato_aceito"]
        )
    changed = "município;valor_liquidado;data\nSão Paulo;1,00;01/02/2026\n".encode("latin-1")
    _serve(catalog_server, changed)
    with CatalogClient() as client, pytest.raises(files.FormatChangedError) as err:
        files.read(client, URL, tmp_path, "csv", accepted)
    assert err.value.changes == ["saiu a coluna valor_pago", "entrou a coluna valor_liquidado"]
    assert "valor_liquidado" in str(err.value)
    # Aceitar o novo formato: a mesma leitura volta a executar.
    with CatalogClient() as client:
        again = files.read(client, URL, tmp_path, "csv", err.value.new_format)
    assert again.frame.columns == ["município", "valor_liquidado", "data"]


def test_numero_com_milhar_vira_numero_e_a_previa_diz(catalog_server: Server, tmp_path: Path) -> None:
    body = b"codigo;valor;nome\n0012;1.234,56;A\n0034;10,50;B\n"
    _serve(catalog_server, body)
    with CatalogClient() as client:
        prev = files.preview(client, URL, tmp_path, "csv")
    assert prev["numeros_convertidos"] == ["valor"]
    assert prev["linhas"][0]["valor"] == 1234.56
    assert prev["linhas"][0]["codigo"] == "0012"  # código com zero à esquerda continua texto


def test_valor_que_nao_e_numero_depois_da_previa_vira_vazio_com_aviso(
    catalog_server: Server, tmp_path: Path
) -> None:
    accepted = files.AcceptedFormat(opcoes={"delimiter": ";", "encoding": "utf-8", "decimal": ","},
                                    colunas=[("uf", "texto"), ("valor", "numero")])  # fmt: skip
    _serve(catalog_server, b"uf;valor\nSP;1.234,56\nRJ;N/D\nMG;10,5\n")
    with CatalogClient() as client:
        result = files.read(client, URL, tmp_path, "csv", accepted)
    assert result.frame["valor"].to_list() == [1234.56, None, 10.5]
    assert result.warnings == ["1 valor(es) de valor não são número e ficaram vazios."]


def test_coluna_vazia_na_previa_aceita_o_tipo_que_vier() -> None:
    assert files.changes_between([("a", "vazio")], [("a", "numero")]) == []
    frame = pl.DataFrame({"a": [None, None], "b": ["x", "y"]}, schema={"a": pl.String, "b": pl.String})
    assert files.signature(frame) == [("a", "vazio"), ("b", "texto")]


def test_data_com_valor_estranho_depois_da_previa(catalog_server: Server, tmp_path: Path) -> None:
    accepted = files.AcceptedFormat(opcoes={"delimiter": ";", "encoding": "utf-8"},
                                    colunas=[("uf", "texto"), ("dia", "data")])  # fmt: skip
    _serve(catalog_server, b"uf;dia\nSP;01/02/2026\nRJ;00/00/0000\n")
    with CatalogClient() as client:
        result = files.read(client, URL, tmp_path, "csv", accepted)
    assert result.frame["dia"].null_count() == 1
    assert result.warnings == ["1 valor(es) de dia não são data e ficaram vazios."]


def test_identificador_longo_fica_texto() -> None:
    frame = pl.DataFrame({"cnpj": ["33000167000101", "60746948000112"], "qtd": ["10", "20"]})
    typed, _ = files.type_text_columns(frame)
    assert typed.schema["cnpj"] == pl.String
    assert typed.schema["qtd"] == pl.Int64


def test_mudancas_em_palavras() -> None:
    old = [("a", "inteiro"), ("b", "texto"), ("c", "data")]
    new = [("a", "numero"), ("b", "numero"), ("d", "texto")]
    assert files.changes_between(old, new) == [
        "saiu a coluna c",
        "entrou a coluna d",
        "a coluna b mudou de texto para número",
    ]  # inteiro → decimal não conta


def test_arquivo_do_zip_que_sumiu(catalog_server: Server, tmp_path: Path) -> None:
    _serve(catalog_server, _zip({"novo.csv": b"a\n1\n"}))
    accepted = files.AcceptedFormat(opcoes={}, membro="antigo.csv", colunas=[("a", "inteiro")])
    with CatalogClient() as client, pytest.raises(InvalidInputError, match=r"antigo\.csv"):
        files.read(client, URL, tmp_path, "zip", accepted)
