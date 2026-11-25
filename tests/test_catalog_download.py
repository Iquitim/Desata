"""Download do CNPJ (spec 049, T15, RF-4951..4953, CA-05): Receita simulada, Range, pausa, retomada e pastas."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from conftest import catalog_fixture
from prodata.catalog import download, hosts
from prodata.catalog.download import DownloadError, DownloadManager
from prodata.catalog.http import CatalogClient
from prodata.catalog.readers import receita

Server = Callable[[Callable[[httpx.Request], httpx.Response]], list[httpx.Request]]
MONTH = "2026-11"
ROOT = f"/public.php/webdav{hosts.CNPJ_LINKS[0][1]}"


def _listing(files: dict[str, bytes], months: tuple[str, ...] = (MONTH,)) -> bytes:
    items = [f"<d:response><d:href>{ROOT}/{m}/</d:href><d:propstat><d:prop><d:resourcetype><d:collection/>"
             "</d:resourcetype></d:prop></d:propstat></d:response>" for m in months]  # fmt: skip
    items += [f"<d:response><d:href>{ROOT}/{MONTH}/{name}</d:href><d:propstat><d:prop><d:getcontentlength>{len(body)}"
              "</d:getcontentlength><d:resourcetype/></d:prop></d:propstat></d:response>" for name, body in files.items()]  # fmt: skip
    return f'<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">{"".join(items)}</d:multistatus>'.encode()


class Receita:
    """Uma Receita simulada: listagem WebDAV, GET com Range e falhas programadas."""

    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files
        self.ranges: list[str | None] = []
        self.drop_after: dict[str, int] = {}  # arquivo → corta a conexão depois de N bytes (uma vez)
        self.fail: dict[str, int] = {}  # arquivo → quantas respostas 503 antes de funcionar
        self.ignore_range = False
        self.slow = 0.0
        self.auth: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.auth.append(request.headers.get("authorization", ""))
        path = request.url.path
        if request.method == "PROPFIND":
            if path.rstrip("/").endswith("CNPJ"):
                return httpx.Response(207, content=_listing({}, (MONTH, "2026-10")))
            return httpx.Response(207, content=_listing(self.files))
        name = path.rsplit("/", 1)[-1]
        body = self.files[name]
        if self.fail.get(name):
            self.fail[name] -= 1
            return httpx.Response(503)
        header = request.headers.get("range")
        self.ranges.append(header)
        start = int(header.removeprefix("bytes=").rstrip("-")) if header and not self.ignore_range else 0
        rest = body[start:]
        cut = self.drop_after.pop(name, None)

        def stream() -> Iterator[bytes]:
            sent = 0
            for i in range(0, len(rest), 10):
                if self.slow:
                    time.sleep(self.slow)
                if cut is not None and sent >= cut:
                    raise httpx.ReadError("conexão caiu")
                sent += len(rest[i : i + 10])
                yield rest[i : i + 10]

        if start:
            return httpx.Response(206, content=stream(),
                                  headers={"content-range": f"bytes {start}-{len(body) - 1}/{len(body)}"})  # fmt: skip
        return httpx.Response(200, content=stream())


FILES = {"Empresas0.zip": bytes(range(256)) * 4, "Cnaes.zip": b"c" * 300, "Socios0.zip": b"s" * 50}


@pytest.fixture
def receita_server(catalog_server: Server, monkeypatch: pytest.MonkeyPatch) -> Receita:
    monkeypatch.setattr(download, "CHUNK", 10)
    fake = Receita(dict(FILES))
    catalog_server(fake)
    return fake


def _manager(root: Path, **kw: Any) -> DownloadManager:
    return DownloadManager(root / "catalogo", lambda: [root / "dados"], retry_wait=0.0, **kw)


def _wait(manager: DownloadManager, job_id: str, states: set[str], timeout: float = 10) -> dict[str, Any]:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        job = manager.get(job_id)
        if job["estado"] in states:
            return job
        time.sleep(0.01)
    raise AssertionError(f"ficou em {manager.get(job_id)['estado']}")


@pytest.fixture
def target(tmp_path: Path) -> Path:
    folder = tmp_path / "escolhida"
    folder.mkdir()
    return folder


def test_lista_os_meses_e_as_partes_da_receita_de_verdade(catalog_server: Server) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        name = "cnpj_meses.xml" if request.url.path.rstrip("/").endswith("CNPJ") else "cnpj_mes.xml"
        return httpx.Response(207, content=catalog_fixture(name))

    seen = catalog_server(handler)
    with CatalogClient() as client:
        info = receita.summary(client)
    assert info["mes"] == "2026-11"
    groups = {g["id"]: g for g in info["grupos"]}
    assert groups["empresas"]["arquivos"][0]["arquivo"] == "Empresas0.zip"
    assert groups["empresas"]["arquivos"][0]["tamanho"] == 580989288
    assert groups["cnaes"]["padrao"] is True and groups["socios"]["padrao"] is False
    assert all(r.method == "PROPFIND" for r in seen)


def test_baixa_so_na_pasta_escolhida_com_nomes_fixos(
    tmp_path: Path, target: Path, receita_server: Receita
) -> None:
    manager = _manager(tmp_path)
    job = manager.start(MONTH, ["Empresas0.zip", "Cnaes.zip"], str(target))
    job = _wait(manager, job["id"], {"concluido"})
    dest = target / f"CNPJ-{MONTH}"
    assert sorted(p.name for p in dest.iterdir()) == ["Cnaes.zip", "Empresas0.zip"]
    assert (dest / "Empresas0.zip").read_bytes() == FILES["Empresas0.zip"]
    assert sorted(p.name for p in target.iterdir()) == [f"CNPJ-{MONTH}"]  # nada fora da subpasta
    assert job["baixado"] == job["total"] == 1024 + 300
    assert all(
        a.startswith("Basic ") for a in receita_server.auth
    )  # o link público da Receita, não um segredo nosso


def test_conexao_que_cai_continua_do_ponto_com_range(
    tmp_path: Path, target: Path, receita_server: Receita
) -> None:
    receita_server.drop_after["Empresas0.zip"] = 400
    manager = _manager(tmp_path)
    job = _wait(manager, manager.start(MONTH, ["Empresas0.zip"], str(target))["id"], {"concluido"})
    assert receita_server.ranges[0] is None
    assert receita_server.ranges[1] == "bytes=400-"
    assert (Path(job["destino"]) / "Empresas0.zip").read_bytes() == FILES["Empresas0.zip"]


def test_fechar_o_programa_pausa_e_ao_abrir_continua(
    tmp_path: Path, target: Path, receita_server: Receita
) -> None:
    """CA-05: fecha no meio, abre de novo (outro gerenciador, mesma pasta) e retoma do ponto, com Range."""
    receita_server.slow = 0.005
    first = _manager(tmp_path)
    job_id = first.start(MONTH, ["Empresas0.zip"], str(target))["id"]
    end = time.monotonic() + 10
    while first.get(job_id)["baixado"] < 200 and time.monotonic() < end:
        time.sleep(0.01)
    first.shutdown()
    paused = first.get(job_id)
    assert paused["estado"] == "pausado"
    assert "fechado" in paused["motivo"]
    have = (Path(paused["destino"]) / "Empresas0.zip.parte").stat().st_size
    assert 0 < have < 1024
    receita_server.slow = 0.0
    second = _manager(tmp_path)
    assert [j["id"] for j in second.pending()] == [job_id]
    second.resume(job_id)
    job = _wait(second, job_id, {"concluido"})
    assert receita_server.ranges[-1] == f"bytes={have}-"
    assert (Path(job["destino"]) / "Empresas0.zip").read_bytes() == FILES["Empresas0.zip"]


def test_programa_que_caiu_no_meio_volta_pausado(
    tmp_path: Path, target: Path, receita_server: Receita
) -> None:
    manager = _manager(tmp_path)
    job = _wait(manager, manager.start(MONTH, ["Cnaes.zip"], str(target))["id"], {"concluido"})
    state = manager._path(job["id"])
    state.write_text(state.read_text(encoding="utf-8").replace('"concluido"', '"baixando"'), encoding="utf-8")
    assert _manager(tmp_path).get(job["id"])["estado"] == "pausado"


def test_pausar_e_continuar(tmp_path: Path, target: Path, receita_server: Receita) -> None:
    receita_server.slow = 0.005
    manager = _manager(tmp_path)
    job_id = manager.start(MONTH, ["Empresas0.zip"], str(target))["id"]
    time.sleep(0.1)
    assert manager.pause(job_id)["estado"] == "pausado"
    receita_server.slow = 0.0
    manager.resume(job_id)
    job = _wait(manager, job_id, {"concluido"})
    assert (Path(job["destino"]) / "Empresas0.zip").read_bytes() == FILES["Empresas0.zip"]


def test_servidor_que_ignora_range_recomeca_do_zero(
    tmp_path: Path, target: Path, receita_server: Receita
) -> None:
    receita_server.drop_after["Empresas0.zip"] = 300
    receita_server.ignore_range = True
    manager = _manager(tmp_path)
    job = _wait(manager, manager.start(MONTH, ["Empresas0.zip"], str(target))["id"], {"concluido"})
    assert (Path(job["destino"]) / "Empresas0.zip").read_bytes() == FILES["Empresas0.zip"]


def test_tres_falhas_pedem_acao_e_continuar_tenta_de_novo(
    tmp_path: Path, target: Path, receita_server: Receita
) -> None:
    receita_server.fail["Cnaes.zip"] = 3
    manager = _manager(tmp_path)
    job = _wait(manager, manager.start(MONTH, ["Cnaes.zip"], str(target))["id"], {"erro"})
    assert job["partes"][0]["tentativas"] == 3
    assert "Tentou 3 vezes" in job["motivo"] and "503" in job["motivo"]
    manager.resume(job["id"])
    assert _wait(manager, job["id"], {"concluido"})["estado"] == "concluido"


def test_cancelar_apaga_so_o_que_baixou(tmp_path: Path, target: Path, receita_server: Receita) -> None:
    receita_server.slow = 0.005
    manager = _manager(tmp_path)
    job = manager.start(MONTH, ["Empresas0.zip"], str(target))
    dest = Path(job["destino"])
    (dest / "minha-anotacao.txt").write_text("da pessoa", encoding="utf-8")
    time.sleep(0.05)
    assert manager.cancel(job["id"])["estado"] == "cancelado"
    assert [p.name for p in dest.iterdir()] == ["minha-anotacao.txt"]


def test_pasta_proibida_relativa_ou_inexistente(tmp_path: Path, receita_server: Receita) -> None:
    data = tmp_path / "dados"
    (data / "sub").mkdir(parents=True)
    manager = _manager(tmp_path)
    for folder, message in ((str(data / "sub"), "do programa ou de um espaço"), ("relativa\\x", "caminho precisa"),
                            (str(tmp_path / "nao-existe"), "não existe")):  # fmt: skip
        with pytest.raises(DownloadError, match=message):
            manager.start(MONTH, ["Cnaes.zip"], folder)
    assert not any(p.name.startswith("CNPJ-") for p in tmp_path.rglob("*"))


def test_falta_espaco_avisa_antes(
    tmp_path: Path, target: Path, receita_server: Receita, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(download, "free_space", lambda _folder: 100)
    manager = _manager(tmp_path)
    plan = manager.plan(MONTH, ["Empresas0.zip"], str(target))
    assert plan["cabe"] is False and plan["livre"] == 100 and plan["necessario"] > 1024
    with pytest.raises(DownloadError, match="Falta espaço"):
        manager.start(MONTH, ["Empresas0.zip"], str(target))
    assert not (target / f"CNPJ-{MONTH}").exists()


def test_arquivo_fora_da_listagem_e_recusado(tmp_path: Path, target: Path, receita_server: Receita) -> None:
    manager = _manager(tmp_path)
    with pytest.raises(DownloadError, match="não estão na pasta"):
        manager.start(MONTH, ["../../segredo.zip"], str(target))


def test_um_download_por_vez(tmp_path: Path, target: Path, receita_server: Receita) -> None:
    receita_server.slow = 0.005
    manager = _manager(tmp_path)
    job = manager.start(MONTH, ["Empresas0.zip"], str(target))
    with pytest.raises(DownloadError, match="Já há um download"):
        manager.start(MONTH, ["Cnaes.zip"], str(target))
    manager.cancel(job["id"])


def test_rotas(client: TestClient, tmp_path: Path, receita_server: Receita) -> None:
    folder = tmp_path / "rota"
    folder.mkdir()
    info = client.get("/api/catalogo/cnpj").json()
    assert info["mes"] == MONTH and info["downloads"] == []
    body = {"mes": MONTH, "arquivos": ["Cnaes.zip"], "pasta": str(folder)}
    assert client.post("/api/catalogo/downloads/plano", json=body).json()["cabe"] is True
    job = client.post("/api/catalogo/downloads", json=body).json()
    end = time.monotonic() + 10
    while client.get(f"/api/catalogo/downloads/{job['id']}").json()["estado"] != "concluido":
        assert time.monotonic() < end
        time.sleep(0.02)
    assert client.get("/api/catalogo/downloads").json()["pendentes"] == []
    assert client.get("/api/catalogo/downloads/..%2Fx").status_code in (400, 404, 405)
    assert client.post(f"/api/catalogo/downloads/{job['id']}/apagar").status_code == 422
    storage = client.app.state.services.settings.storage_dir  # type: ignore[attr-defined]
    refused = client.post("/api/catalogo/downloads", json={**body, "pasta": str(storage)})
    assert refused.status_code == 422 and "programa" in refused.json()["detail"]


def test_baixar_nao_bloqueia_quem_consulta(tmp_path: Path, target: Path, receita_server: Receita) -> None:
    receita_server.slow = 0.005
    manager = _manager(tmp_path)
    job = manager.start(MONTH, ["Empresas0.zip"], str(target))
    started = time.monotonic()
    for _ in range(20):
        manager.get(job["id"])
    assert time.monotonic() - started < 1
    assert threading.active_count() >= 2
    manager.cancel(job["id"])
