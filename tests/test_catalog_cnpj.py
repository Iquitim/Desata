"""CNPJ: conferência e descompactação segura, leiaute e a fonte de pasta pronta (spec 049, T16, RF-4954, RF-4955, CA-05)."""

from __future__ import annotations

import io
import time
import zipfile
from collections.abc import Callable
from datetime import date
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from prodata.catalog import cnpj, download
from prodata.catalog.cnpj import ZipRefusedError
from test_catalog_download import MONTH, Receita

Server = Callable[[Callable[[httpx.Request], httpx.Response]], list[httpx.Request]]

EMPRESAS = ('"00000000";"BANCO DO BRASIL SA";"2038";"10";"120000000000,00";"05";""\n'
            '"01234567";"AÇÚCAR & CIA LTDA";"2062";"49";"1000,50";"01";""\n')  # fmt: skip
ESTAB = ('"01234567";"0001";"89";"1";"DOCE";"02";"20050101";"00";"";"";"19990315";"1091101";"4721102,4729699";'
         '"RUA";"DAS FLORES";"S/N";"";"CENTRO";"01001000";"SP";"7107";"11";"55550000";"";"";"";"";"a@b.com";"";"0"\n')  # fmt: skip
CNAES = '"1091101";"Fabricação de produtos de panificação industrial"\n'


def _zip(member: str, text: str, *, stored: bool = False) -> bytes:
    buffer = io.BytesIO()
    method = zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED
    with zipfile.ZipFile(buffer, "w", method) as archive:
        archive.writestr(member, text.encode("latin-1"))
    return buffer.getvalue()


def test_descompacta_com_nome_fixo_utf8_e_cabecalho(tmp_path: Path) -> None:
    path = tmp_path / "Empresas0.zip"
    path.write_bytes(_zip("K3241.K03200Y0.D41109.EMPRECSV", EMPRESAS))
    csv, warning = cnpj.extract(path, "empresas", 0)
    assert csv.name == "empresas_0.csv" and warning == ""
    lines = csv.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("cnpj_basico;razao_social;")
    assert "AÇÚCAR & CIA LTDA" in lines[2]


def test_leitura_com_os_tipos_do_leiaute(tmp_path: Path) -> None:
    (tmp_path / "Empresas0.zip").write_bytes(_zip("x.EMPRECSV", EMPRESAS))
    (tmp_path / "Estabelecimentos0.zip").write_bytes(_zip("x.ESTABELE", ESTAB))
    emp, _ = cnpj.extract(tmp_path / "Empresas0.zip", "empresas", 0)
    est, _ = cnpj.extract(tmp_path / "Estabelecimentos0.zip", "estabelecimentos", 0)
    frame, notes = cnpj.read_file(emp, "receita.cnpj/empresas")
    assert notes == []
    assert frame["cnpj_basico"].to_list() == ["00000000", "01234567"]  # zeros à esquerda preservados
    assert frame["capital_social"].to_list() == [120000000000.0, 1000.5]
    assert frame["natureza_juridica"].dtype.is_(frame["razao_social"].dtype)  # código fica texto
    frame, _ = cnpj.read_file(est, "receita.cnpj/estabelecimentos")
    row = frame.row(0, named=True)
    assert row["data_situacao_cadastral"] == date(2005, 1, 1)
    assert row["data_inicio_atividade"] == date(1999, 3, 15)
    assert row["data_situacao_especial"] is None  # "0" da Receita é "sem data"
    assert row["cep"] == "01001000" and row["numero"] == "S/N"


def test_leiaute_mudado_avisa_e_usa_nomes_genericos(tmp_path: Path) -> None:
    """RF-4955: uma coluna a mais em Empresas."""
    path = tmp_path / "Empresas0.zip"
    path.write_bytes(_zip("x.EMPRECSV", EMPRESAS.replace('""\n', '"";"novo"\n')))
    csv, warning = cnpj.extract(path, "empresas", 0)
    assert warning.startswith("A Receita mudou o leiaute de Empresas: 8 colunas, esperadas 7.")
    frame, notes = cnpj.read_file(csv, "receita.cnpj/empresas")
    assert frame.columns[0] == "coluna_1" and frame.width == 8
    assert notes and "não batem com o leiaute" in notes[0]
    assert frame["coluna_5"].to_list()[1] == "1000,50"  # sem adivinhar: fica como veio


@pytest.mark.parametrize(
    ("member", "message"),
    [
        ("../../fora.csv", "para fora da pasta"),
        ("/abs.csv", "para fora da pasta"),
        ("C:/x.csv", "para fora da pasta"),
    ],
)
def test_zip_com_caminho_para_fora_e_recusado(tmp_path: Path, member: str, message: str) -> None:
    folder = tmp_path / "CNPJ-2026-11"
    folder.mkdir()
    path = folder / "Empresas0.zip"
    path.write_bytes(_zip(member, EMPRESAS))
    with pytest.raises(ZipRefusedError, match=message):
        cnpj.extract(path, "empresas", 0)
    assert sorted(p.name for p in tmp_path.rglob("*") if p.is_file()) == ["Empresas0.zip"]


def test_bomba_de_zip_e_varios_arquivos_sao_recusados(tmp_path: Path) -> None:
    bomb = tmp_path / "Empresas0.zip"
    bomb.write_bytes(_zip("x.EMPRECSV", "0" * 5_000_000))
    with pytest.raises(ZipRefusedError, match="bomba"):
        cnpj.extract(bomb, "empresas", 0)
    two = tmp_path / "Cnaes.zip"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("a.csv", CNAES)
        archive.writestr("b.csv", CNAES)
    two.write_bytes(buffer.getvalue())
    with pytest.raises(ZipRefusedError, match="2 arquivos dentro"):
        cnpj.extract(two, "cnaes", None)


def test_zip_com_defeito_nao_fica_com_nome_final(tmp_path: Path) -> None:
    data = bytearray(_zip("x.CNAECSV", CNAES * 50, stored=True))
    spot = data.index(b"panifica")
    data[spot] ^= 0xFF  # um byte trocado: o CRC não confere
    path = tmp_path / "Cnaes.zip"
    path.write_bytes(bytes(data))
    with pytest.raises(ZipRefusedError, match="defeito"):
        cnpj.extract(path, "cnaes", None)
    assert not (tmp_path / "cnaes.csv").exists() and not (tmp_path / "cnaes.csv.parte").exists()
    (tmp_path / "Lixo.zip").write_bytes(b"isto nao e zip")
    with pytest.raises(ZipRefusedError, match="não é um ZIP válido"):
        cnpj.extract(tmp_path / "Lixo.zip", "cnaes", None)


def _wait(client: TestClient, job_id: str, states: set[str]) -> dict[str, object]:
    end = time.monotonic() + 15
    while True:
        job = client.get(f"/api/catalogo/downloads/{job_id}").json()
        if job["estado"] in states:
            return job
        assert time.monotonic() < end, job
        time.sleep(0.02)


@pytest.fixture
def receita_zips(catalog_server: Server, monkeypatch: pytest.MonkeyPatch) -> Receita:
    monkeypatch.setattr(download, "CHUNK", 4096)
    fake = Receita({"Empresas0.zip": _zip("x.EMPRECSV", EMPRESAS), "Estabelecimentos0.zip": _zip("x.ESTABELE", ESTAB),
                    "Cnaes.zip": _zip("x.CNAECSV", CNAES)})  # fmt: skip
    catalog_server(fake)
    return fake


def test_do_download_a_fonte_pronta_com_colunas_com_nome(
    client: TestClient, tmp_path: Path, receita_zips: Receita
) -> None:
    """CA-05, até o fim: baixa, confere, descompacta, apaga os ZIPs e a vista Dados ganha as fontes de pasta."""
    folder = tmp_path / "escolhida"
    folder.mkdir()
    body = {
        "mes": MONTH,
        "arquivos": ["Empresas0.zip", "Estabelecimentos0.zip", "Cnaes.zip"],
        "pasta": str(folder),
    }
    job = _wait(client, client.post("/api/catalogo/downloads", json=body).json()["id"], {"concluido", "erro"})
    assert job["estado"] == "concluido", job
    dest = folder / f"CNPJ-{MONTH}"
    assert sorted(p.name for p in dest.iterdir()) == ["cnaes.csv", "empresas_0.csv", "estabelecimentos_0.csv"]
    sources = {s["name"]: s for s in client.get("/api/folders").json()}
    assert set(sources) >= {
        f"CNPJ {MONTH} · Empresas",
        f"CNPJ {MONTH} · Estabelecimentos",
        f"CNPJ {MONTH} · CNAE",
    }
    emp = sources[f"CNPJ {MONTH} · Empresas"]
    assert emp["layout"] == "receita.cnpj/empresas" and emp["pattern"] == "empresas_*.csv"
    org = client.get("/api/organization").json()
    folder_id = next(f["id"] for f in org["folders"] if f["name"] == f"CNPJ {MONTH}")
    assert org["sources"][f"folder:{emp['id']}"]["folder"] == folder_id
    flow = {"id": "wf-cnpj", "name": "CNPJ", "edges": [],
            "nodes": [{"id": "e", "type": "io.input_data", "label": "Empresas", "config": {"dataset": f"folder:{emp['id']}"}}]}  # fmt: skip
    report = client.post("/api/execute", json={"workflow": flow}).json()["node_results"]["e"]
    assert report["status"] == "executed", report
    rows = client.get("/api/results/wf-cnpj/e/out").json()["rows"]
    assert rows[1]["razao_social"] == "AÇÚCAR & CIA LTDA" and rows[0]["cnpj_basico"] == "00000000"
    info = report["extra"]["fonte_publica"]
    assert (
        info["citacao"].startswith("Receita Federal do Brasil")
        and info["colunas"][0]["nome"] == "cnpj_basico"
    )


def test_manter_os_zips(client: TestClient, tmp_path: Path, receita_zips: Receita) -> None:
    folder = tmp_path / "escolhida"
    folder.mkdir()
    body = {"mes": MONTH, "arquivos": ["Cnaes.zip"], "pasta": str(folder), "manter_zips": True}
    _wait(client, client.post("/api/catalogo/downloads", json=body).json()["id"], {"concluido"})
    assert sorted(p.name for p in (folder / f"CNPJ-{MONTH}").iterdir()) == ["Cnaes.zip", "cnaes.csv"]


def test_zip_recusado_no_download_para_com_o_motivo(
    client: TestClient, tmp_path: Path, receita_zips: Receita
) -> None:
    receita_zips.files["Cnaes.zip"] = _zip("../../fora.csv", CNAES)
    folder = tmp_path / "escolhida"
    folder.mkdir()
    body = {"mes": MONTH, "arquivos": ["Cnaes.zip"], "pasta": str(folder)}
    job = _wait(client, client.post("/api/catalogo/downloads", json=body).json()["id"], {"concluido", "erro"})
    assert job["estado"] == "erro" and "para fora da pasta" in job["motivo"]
    assert list((folder / f"CNPJ-{MONTH}").iterdir()) == []
    assert not (tmp_path / "fora.csv").exists()
