"""Pasta Dados públicos na vista Dados e o aviso Dados novos (spec 049, T13, RF-4915, RF-4935)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx
import polars as pl
from fastapi.testclient import TestClient

from prodata.catalog import cache
from prodata.catalog.saved import News, SavedSources
from prodata.catalog.service import CatalogService

Server = Callable[[Callable[[httpx.Request], httpx.Response]], list[httpx.Request]]

SELIC = {"id": "bcb.sgs/11", "nome": "Selic diária", "orgao": "Banco Central", "citacao": "BCB, SGS 11",
         "escolhas": {"periodo": {"kind": "ultimos_anos", "anos": 1}}}  # fmt: skip


def _saved_frame(root: Path, last: date, read_at: datetime) -> None:
    frame = pl.DataFrame({"data": [last - timedelta(days=1), last], "valor": [0.05, 0.05]})
    cache.save(root, "bcb.sgs/11", SELIC["escolhas"], frame, read_at)


def test_guardar_trocar_e_excluir(tmp_path: Path) -> None:
    saved = SavedSources(tmp_path)
    item = saved.add(dict(SELIC))
    assert [r["fonte"]["nome"] for r in saved.list()] == ["Selic diária"]
    saved.update(item["key"], {**SELIC, "escolhas": {"periodo": {"kind": "ultimos_anos", "anos": 3}}})
    assert saved.list()[0]["fonte"]["escolhas"]["periodo"]["anos"] == 3
    saved.delete(item["key"])
    assert saved.list() == []


def test_arquivo_estragado_vira_lista_vazia(tmp_path: Path) -> None:
    (tmp_path / "fontes_publicas.json").write_text("{não é json", encoding="utf-8")
    assert SavedSources(tmp_path).list() == []
    assert News(tmp_path).load() == {}


def test_ultimo_dado_mais_novo_que_a_leitura(tmp_path: Path) -> None:
    """Série com 'último dado em': compara com a última data lida, não com o dia da leitura."""
    news = News(tmp_path)
    _saved_frame(tmp_path, date(2026, 11, 20), datetime(2026, 11, 24, 9, 0))
    news.record("bcb.sgs/11", "2026-11-21", "último dado em", datetime(2026, 11, 25, 8, 0))
    state = news.state("bcb.sgs/11", SELIC["escolhas"])
    assert state["novo"] is True
    assert "21/11/2026" in state["texto"] and "20/11/2026" in state["texto"]
    news.record("bcb.sgs/11", "2026-11-20", "último dado em", datetime(2026, 11, 25, 9, 0))
    assert news.state("bcb.sgs/11", SELIC["escolhas"])["novo"] is False


def test_publicado_depois_da_leitura(tmp_path: Path) -> None:
    news = News(tmp_path)
    _saved_frame(tmp_path, date(2026, 10, 1), datetime(2026, 11, 1, 9, 0))
    news.record("bcb.sgs/11", "2026-11-10", "atualizada em", datetime(2026, 11, 25))
    state = news.state("bcb.sgs/11", SELIC["escolhas"])
    assert state["novo"] is True and "10/11/2026" in state["texto"]


def test_sem_leitura_ou_sem_informacao_nao_avisa(tmp_path: Path) -> None:
    news = News(tmp_path)
    assert news.state("bcb.sgs/11", SELIC["escolhas"])["novo"] is False
    _saved_frame(tmp_path, date(2026, 11, 20), datetime(2026, 11, 24))
    assert news.state("bcb.sgs/11", SELIC["escolhas"])["novo"] is False


def test_conferir_pergunta_ao_orgao_no_maximo_a_cada_6_horas(tmp_path: Path, catalog_server: Server) -> None:
    seen = catalog_server(lambda r: httpx.Response(200, json=[{"data": "21/11/2026", "valor": "0.05"}]))
    service = CatalogService(tmp_path)
    service.news_check(["bcb.sgs/11", "bcb.sgs/11"])
    asked = len(seen)
    assert asked >= 1
    assert News(tmp_path).load()["bcb.sgs/11"]["atualizado"] == "2026-11-21"
    service.news_check(["bcb.sgs/11"])
    assert len(seen) == asked


def test_orgao_fora_nao_grava_e_confere_de_novo(tmp_path: Path, catalog_server: Server) -> None:
    catalog_server(lambda r: httpx.Response(503))
    service = CatalogService(tmp_path)
    service.news_check(["bcb.sgs/11"])
    assert "bcb.sgs/11" not in News(tmp_path).load()


def test_rotas_da_pasta_e_das_novidades(client: TestClient) -> None:
    assert client.get("/api/catalogo/salvas").json() == {"fontes": []}
    item = client.post("/api/catalogo/salvas", json={"fonte": SELIC}).json()
    rows = client.get("/api/catalogo/salvas").json()["fontes"]
    assert rows[0]["fonte"]["id"] == "bcb.sgs/11"
    assert rows[0]["servico"] == "bcb_sgs"
    assert rows[0]["novidade"]["novo"] is False
    changed = {**SELIC, "nome": "Selic (3 anos)"}
    assert client.put(f"/api/catalogo/salvas/{item['key']}", json={"fonte": changed}).status_code == 200
    assert client.put("/api/catalogo/salvas/naoexiste", json={"fonte": changed}).status_code == 404
    assert client.put("/api/catalogo/salvas/..%2Fx", json={"fonte": changed}).status_code in (400, 404)
    assert client.post("/api/catalogo/salvas", json={"fonte": {**SELIC, "id": "../x"}}).status_code == 404
    news = client.post(
        "/api/catalogo/novidades", json={"fontes": [{"id": "bcb.sgs/11", "escolhas": {}}]}
    ).json()
    assert news["novidades"][0]["novo"] is False
    assert client.delete(f"/api/catalogo/salvas/{item['key']}").json() == {"ok": True}
    assert client.get("/api/catalogo/salvas").json() == {"fontes": []}


def test_a_fonte_guardada_mostra_a_situacao_do_orgao(tmp_path: Path, catalog_server: Server) -> None:
    catalog_server(lambda r: httpx.Response(200, content=b"[]"))
    service = CatalogService(tmp_path)
    service.saved_add(dict(SELIC))
    service.check_health(force=True)
    assert service.saved_list()[0]["situacao"]["situacao"] == "no_ar"


def test_onde_e_usada_conta_a_fonte_com_quaisquer_escolhas() -> None:
    from prodata.services.usage import source_keys

    config = {
        "fonte": {"id": "bcb.sgs/11", "escolhas": {"periodo": {"kind": "desde", "inicio": "2020-01-01"}}}
    }
    assert source_keys("io.public_data", config) == ["publica:bcb.sgs/11"]
    assert source_keys("io.public_data", {"fonte": {}}) == []
