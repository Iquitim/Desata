"""Caixa Dados públicos (spec 049, T12, CA-01, CA-02, CA-08, CA-12, RF-4948)."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient

from prodata.catalog import holidays
from prodata.catalog.holidays import Edits, Holiday
from prodata.nodes.base import NodeContext
from prodata.nodes.public_data import PublicDataConfig, public_data

Server = Callable[[Callable[[httpx.Request], httpx.Response]], list[httpx.Request]]


def _ctx(root: Path, team: Edits | None = None) -> NodeContext:
    return NodeContext({}, {}, None, root, catalog_root=root, team_holidays=team)  # type: ignore[arg-type]


def _cfg(source_id: str, choices: dict[str, Any] | None = None, **kw: Any) -> PublicDataConfig:
    return PublicDataConfig.model_validate({"fonte": {"id": source_id, "nome": "Teste", "orgao": "Órgão",
                                                      "citacao": "Banco Central do Brasil, SGS 11",
                                                      "escolhas": choices or {}}, **kw})  # fmt: skip


def _sgs(request: httpx.Request) -> httpx.Response:
    q = {k: v[0] for k, v in parse_qs(urlsplit(unquote(str(request.url))).query).items()}
    return httpx.Response(200, json=[{"data": q.get("dataInicial", "01/01/2026"), "valor": "0.05"}])


def test_selic_de_quinze_anos_em_janelas(tmp_path: Path, catalog_server: Server) -> None:
    """CA-01: 15 anos de Selic diária viram duas consultas de até 10 anos, sem repetir data."""
    seen = catalog_server(_sgs)
    out = public_data(_ctx(tmp_path), _cfg("bcb.sgs/11", {"periodo": {"kind": "ultimos_anos", "anos": 15}}))
    frame = out.tables["out"]
    assert len(seen) == 2
    assert frame["data"].n_unique() == frame.height == 2
    assert out.extra["fonte_publica"]["citacao"] == "Banco Central do Brasil, SGS 11"
    assert "warnings" not in out.extra


def test_orgao_fora_usa_a_leitura_guardada(tmp_path: Path, catalog_server: Server) -> None:
    """CA-02: com o Banco Central fora, a caixa usa a última leitura, com o aviso e a data."""
    catalog_server(_sgs)
    cfg = _cfg("bcb.sgs/11")
    first = public_data(_ctx(tmp_path), cfg).tables["out"]
    catalog_server(lambda r: httpx.Response(503))
    out = public_data(_ctx(tmp_path), cfg)
    assert out.tables["out"].equals(first)
    warning = out.extra["warnings"][0]
    assert warning.startswith("Banco Central fora do ar: usando os dados lidos em ")
    assert "503" in warning


def test_exigir_dados_atuais(tmp_path: Path, catalog_server: Server) -> None:
    catalog_server(_sgs)
    public_data(_ctx(tmp_path), _cfg("bcb.sgs/11"))
    catalog_server(lambda r: httpx.Response(503))
    with pytest.raises(ValueError, match="503"):
        public_data(_ctx(tmp_path), _cfg("bcb.sgs/11", exigir_atual=True))


def test_sem_leitura_guardada_falha_com_o_motivo(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Ainda não há leitura guardada"):
        public_data(_ctx(tmp_path), _cfg("bcb.sgs/11"))


def test_escolha_diferente_e_outra_consulta(tmp_path: Path, catalog_server: Server) -> None:
    catalog_server(_sgs)
    public_data(_ctx(tmp_path), _cfg("bcb.sgs/11", {"periodo": {"kind": "ultimos_anos", "anos": 1}}))
    catalog_server(lambda r: httpx.Response(503))
    with pytest.raises(ValueError, match="Ainda não há leitura guardada"):
        public_data(_ctx(tmp_path), _cfg("bcb.sgs/11", {"periodo": {"kind": "ultimos_anos", "anos": 2}}))


def test_feriados_da_equipe_valem_no_fluxo_do_espaco(tmp_path: Path) -> None:
    team = Edits()
    team.include(
        Holiday(
            id="meu/padroeira",
            nome="Padroeira da equipe",
            tipo="municipal",
            abrangencia="3509502",
            fixo="12-08",
        )
    )
    year = date.today().year
    choices = {
        "local": "3509502",
        "periodo": {"kind": "intervalo", "inicio": f"{year}-12-08", "fim": f"{year}-12-08"},
    }
    here = public_data(_ctx(tmp_path), _cfg("calendario/feriados", choices)).tables["out"]
    assert "Padroeira da equipe" not in here["nome"].to_list()
    in_space = public_data(_ctx(tmp_path, team), _cfg("calendario/feriados", choices)).tables["out"]
    assert "Padroeira da equipe" in in_space["nome"].to_list()
    # As edições deste computador não entram no fluxo do espaço: vale a lista da equipe.
    mine = Edits()
    mine.include(
        Holiday(id="meu/x", nome="Só daqui", tipo="meu", abrangencia="3509502", unico=date(year, 12, 8))
    )
    holidays.save_edits(tmp_path, mine)
    in_space = public_data(_ctx(tmp_path, team), _cfg("calendario/feriados", choices)).tables["out"]
    assert "Só daqui" not in in_space["nome"].to_list()


def test_sem_fonte(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Escolher no catálogo"):
        public_data(_ctx(tmp_path), PublicDataConfig())


def test_formato_mudado_pede_aceitar(tmp_path: Path, catalog_server: Server) -> None:
    detail = {"success": True, "result": {"name": "x", "title": "X", "resources": [
        {"id": "r1", "name": "dados.csv", "format": "CSV", "url": "https://dados.cvm.gov.br/x.csv"}]}}  # fmt: skip

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("package_show"):
            return httpx.Response(200, json=detail)
        return httpx.Response(200, content=b"cnpj;valor_liquidado\n1;2\n")

    catalog_server(handler)
    accepted = {
        "opcoes": {"delimiter": ";", "encoding": "utf-8"},
        "membro": "",
        "colunas": [["cnpj", "inteiro"], ["valor_pago", "inteiro"]],
    }
    cfg = _cfg("ckan/cvm/x", {"arquivo": "r1", "formato_aceito": accepted})
    with pytest.raises(ValueError, match="O órgão mudou o arquivo: saiu a coluna valor_pago") as err:
        public_data(_ctx(tmp_path), cfg)
    assert "Aceitar o novo formato" in str(err.value)


def test_fluxo_executa_e_nao_guarda_endereco_nem_dados(client: TestClient) -> None:
    """CA-08: a caixa guarda só a referência e as escolhas."""
    year = date.today().year
    flow = {
        "id": "wf-publico", "name": "Público", "edges": [],
        "nodes": [{"id": "p", "type": "io.public_data", "label": "Feriados", "config": {"fonte": {
            "id": "calendario/feriados", "nome": "Feriados", "escolhas": {"local": "SP", "periodo": {
                "kind": "intervalo", "inicio": f"{year}-07-09", "fim": f"{year}-07-09"}}}}}],
    }  # fmt: skip
    report = client.post("/api/execute", json={"workflow": flow}).json()["node_results"]["p"]
    assert report["status"] == "executed", report
    rows = client.get("/api/results/wf-publico/p/out").json()["rows"]
    assert [r["nome"] for r in rows] == ["Revolução Constitucionalista de 1932"]
    saved = json.dumps(flow["nodes"][0]["config"])
    assert "http" not in saved and "Revolução" not in saved


def test_a_ferramenta_aparece_no_catalogo_de_ferramentas(client: TestClient) -> None:
    tools = {t["type"]: t for t in client.get("/api/catalog").json()["tools"]}
    assert tools["io.public_data"]["name"] == "Dados públicos"
    assert tools["io.public_data"]["category"] == "inout"


def test_mesmo_dia_reaproveita_dia_seguinte_le_de_novo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from prodata.nodes import public_data as module

    cfg = _cfg("bcb.sgs/11")
    today = module._signature(_ctx(tmp_path), cfg)
    assert module._signature(_ctx(tmp_path), cfg) == today

    class Tomorrow(date):
        @classmethod
        def today(cls) -> date:  # type: ignore[override]
            return date.today() + timedelta(days=1)

    monkeypatch.setattr(module, "date", Tomorrow)
    assert module._signature(_ctx(tmp_path), cfg) != today


def test_dicionario_das_colunas_vai_no_resultado(tmp_path: Path, catalog_server: Server) -> None:
    """RF-4912: o significado de cada coluna acompanha a fonte, sem rede."""
    catalog_server(_sgs)
    out = public_data(_ctx(tmp_path), _cfg("bcb.sgs/11"))
    names = {c["nome"]: c["descricao"] for c in out.extra["fonte_publica"]["colunas"]}
    assert set(names) == {"data", "valor"}
    assert all(names.values())


def test_dicionario_generico_e_sem_dicionario() -> None:
    from prodata.catalog import sources

    assert [c["nome"] for c in sources.dictionary("bcb.sgs/99999", ["data", "valor", "extra"])] == [
        "data",
        "valor",
    ]
    assert sources.dictionary("ckan/cvm/x", ["cnpj"]) == []
    assert sources.dictionary("../x", ["a"]) == []
