"""Espaço da equipe, spec 048 marco 1 (RF-4801..4808): definições da equipe sem segredo, assinadas, resolvidas só no
espaço, com o segredo de cada pessoa no próprio cofre e a conferência quando um colega muda o que é sensível."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from prodata.connectors.api_model import ApiAuth, ApiParam, SavedApi
from prodata.connectors.api_store import ApiStore
from prodata.connectors.models import Connection
from prodata.connectors.queries import QueryStore, SavedQuery
from prodata.connectors.secrets import MemorySecretStore
from prodata.connectors.store import ConnectionStore
from prodata.domain.constants import Constant
from prodata.domain.workflow import Workflow
from prodata.errors import InvalidInputError
from prodata.services.constants import ConstantStore
from prodata.team.overlay import (
    NeedsSecretError,
    OverlayApis,
    OverlayConnections,
    OverlayConstants,
    OverlayQueries,
)
from prodata.team.workspaces import CONTROL
from test_team_roles import Person

Team = tuple[Person, Person, Path, str]
CONN = Connection(id="vendas_db", name="Vendas", kind="postgres", host="srv-bi", database="bi", user="ana")
QUERY = SavedQuery(
    id="vendas", name="Vendas do mês", connection="vendas_db", mode="query", query="SELECT 1 AS x"
)


@pytest.fixture
def team(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Team:
    folder = tmp_path / "pasta_da_equipe"
    folder.mkdir()
    ana = Person(tmp_path, "ana", "Ana Souza", monkeypatch)
    bruno = Person(tmp_path, "bruno", "Bruno Lima", monkeypatch)
    with ana.acting() as t:
        sid = t.create(str(folder), "Controladoria")["id"]
    with bruno.acting() as t:
        t.join(str(folder))
    with ana.acting() as t:
        t.change_members(sid, "aceitar", "bruno", "editor")
    return ana, bruno, folder, sid


def files_text(folder: Path) -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in (folder / CONTROL).rglob("*") if p.is_file())


def test_definitions_go_without_secrets_and_signed(team: Team) -> None:
    ana, _, folder, sid = team
    api = SavedApi(id="cotacao", name="Cotação", url="https://api.exemplo.com/v1",
                   params=[ApiParam(name="moeda", value="USD"), ApiParam(name="chave", value="segredo-123", secret=True)],
                   auth=ApiAuth(type="bearer"))  # fmt: skip
    with ana.acting() as t:
        t.save_definition(sid, "conexoes", CONN)
        t.save_definition(sid, "consultas", QUERY)
        t.save_definition(sid, "apis", api)
        t.save_definition(sid, "constantes", Constant(name="meta", value="100"))
        view = t.definitions(sid)
    text = files_text(folder)
    assert (
        "segredo-123" not in text
        and "password" not in text
        and "senha" not in text.lower().replace("assinatura", "")
    )
    assert [(d["id"], d["confere"], d["autor_nome"]) for d in view["consultas"]] == [
        ("vendas", True, "Ana Souza")
    ]
    assert view["apis"][0]["conteudo"]["params"][1]["value"] == ""
    assert view["conexoes"][0]["tem_segredo"] is False


def test_hand_edited_definition_does_not_count(team: Team) -> None:
    ana, _, folder, sid = team
    with ana.acting() as t:
        t.save_definition(sid, "conexoes", CONN)
    path = folder / CONTROL / "definicoes" / "conexoes" / "vendas_db.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["host"] = "servidor-do-atacante"
    path.write_text(json.dumps(data), encoding="utf-8")
    with ana.acting() as t:
        row = t.definitions(sid)["conexoes"][0]
        assert row["confere"] is False and "alterada fora do programa" in row["motivo"]
        assert t.space_definitions(sid).get("conexoes", "vendas_db") is None  # type: ignore[union-attr]


def test_reader_cannot_save_definitions(team: Team) -> None:
    ana, bruno, _, sid = team
    with ana.acting() as t:
        t.change_members(sid, "papel", "bruno", "leitor")
    with bruno.acting() as t, pytest.raises(InvalidInputError, match="Leitor"):
        t.save_definition(sid, "constantes", Constant(name="meta", value="1"))


def test_team_definition_wins_only_in_the_space(team: Team, tmp_path: Path) -> None:
    ana, _, _, sid = team
    secrets = MemorySecretStore()
    local_conn = ConnectionStore(tmp_path / "c.json", secrets)
    local_conn.save(CONN.model_copy(update={"host": "servidor-local"}), password="minha")
    local_q = QueryStore(tmp_path / "q.json")
    local_q.save(QUERY.model_copy(update={"query": "SELECT 2 AS x"}))
    local_k = ConstantStore(tmp_path / "k.json")
    local_k.save(Constant(name="meta", value="1"))
    local_k.save(Constant(name="so_aqui", value="7"))
    with ana.acting() as t:
        t.save_definition(sid, "conexoes", CONN)
        t.save_definition(sid, "consultas", QUERY)
        t.save_definition(sid, "constantes", Constant(name="meta", value="100"))
        defs = t.space_definitions(sid)
    assert defs is not None
    assert OverlayQueries(local_q, defs).get("vendas").query == "SELECT 1 AS x"
    assert OverlayConnections(local_conn, defs, secrets).get("vendas_db").host == "srv-bi"
    merged = OverlayConstants(local_k, defs).all()
    assert merged["meta"].value == "100" and merged["so_aqui"].value == "7"
    assert local_q.get("vendas").query == "SELECT 2 AS x"  # fora do espaço, a deste computador


def test_each_person_types_the_own_password(team: Team, tmp_path: Path) -> None:
    ana, bruno, folder, sid = team
    with ana.acting() as t:
        t.save_definition(sid, "conexoes", CONN)
    with bruno.acting() as t:
        defs = t.space_definitions(sid)
        assert defs is not None
        conns = OverlayConnections(
            ConnectionStore(tmp_path / "c.json", bruno.identity.secrets), defs, bruno.identity.secrets
        )
        with pytest.raises(NeedsSecretError, match="Falta a sua senha para a conexão Vendas"):
            conns.password("vendas_db")
        assert t.missing_secrets(sid, ["vendas_db"], [])[0]["nome"] == "Vendas"
        t.set_secret(sid, "conexoes", "vendas_db", {"senha": "do-bruno"})
        assert conns.password("vendas_db") == "do-bruno"
        assert t.missing_secrets(sid, ["vendas_db"], []) == []
    assert "do-bruno" not in files_text(folder)


def test_api_secret_is_per_person(team: Team, tmp_path: Path) -> None:
    ana, bruno, _, sid = team
    api = SavedApi(
        id="cotacao", name="Cotação", url="https://api.exemplo.com/v1", auth=ApiAuth(type="bearer")
    )
    with ana.acting() as t:
        t.save_definition(sid, "apis", api)
    with bruno.acting() as t:
        defs = t.space_definitions(sid)
        assert defs is not None
        apis = OverlayApis(
            ApiStore(tmp_path / "a.json", bruno.identity.secrets), defs, bruno.identity.secrets
        )
        with pytest.raises(NeedsSecretError, match="API Cotação"):
            apis.secret_reader("cotacao")("token")
        t.set_secret(sid, "apis", "cotacao", {"token": "tk"})
        assert apis.secret_reader("cotacao")("token") == "tk"
        with pytest.raises(InvalidInputError, match="não tem o segredo"):
            t.set_secret(sid, "apis", "cotacao", {"outro": "x"})


def flow_with_query() -> Workflow:
    return Workflow.model_validate({"id": "fechamento", "name": "Fechamento", "edges": [],
                                    "nodes": [{"id": "q", "type": "io.input_data", "config": {"dataset": "sql:vendas"}}]})  # fmt: skip


def opened(person: Person, sid: str) -> dict[str, Any]:
    with person.acting() as t:
        workflow, reason = t.get(sid, "fechamento")
        return t.opened(sid, workflow, reason)


def test_colleague_changing_a_connection_asks_to_check(team: Team) -> None:
    ana, bruno, _, sid = team
    with ana.acting() as t:
        t.save_definition(sid, "conexoes", CONN)
        t.save_definition(sid, "consultas", QUERY)
        t.save(sid, flow_with_query())
    assert opened(ana, sid)["conferir"] == []
    with bruno.acting() as t:
        t.save_definition(sid, "conexoes", CONN.model_copy(update={"name": "Vendas (BI)"}))  # só o nome
    assert opened(ana, sid)["conferir"] == []
    with bruno.acting() as t:
        t.save_definition(sid, "conexoes", CONN.model_copy(update={"host": "srv-bi2"}))
    seen = opened(ana, sid)
    assert seen["conferir"] == ["q"] and "definição da equipe" in seen["motivo"]
    with ana.acting() as t:
        t.accept_sensitive(sid, "fechamento")
    assert opened(ana, sid)["conferir"] == []


def test_api_execute_uses_team_constant(client: TestClient, tmp_path: Path) -> None:
    folder = tmp_path / "Compartilhada"
    folder.mkdir()
    sid = client.post(
        "/api/equipe/espacos", json={"acao": "criar", "caminho": str(folder), "nome": "Time"}
    ).json()["id"]
    client.post("/api/constants", json={"constant": {"name": "fator", "type": "number", "value": "2"}})
    assert client.put(f"/api/equipe/espacos/{sid}/definicoes/constantes/fator",
                      json={"name": "fator", "type": "number", "value": "10"}).status_code == 200  # fmt: skip
    wf = Workflow.model_validate({"id": "k", "name": "K", "edges": [{"id": "e", "source": "t", "target": "f"}], "nodes": [
        {"id": "t", "type": "io.text_input", "config": {"table": {"columns": ["v"], "rows": [[1]]}}},
        {"id": "f", "type": "prep.formula", "config": {"formulas": [
            {"target": "new", "column": "x", "type": "Auto", "expression": "[v] * [#fator]"}]}}]}).model_dump(mode="json")  # fmt: skip

    def x_after(body: dict[str, Any]) -> Any:
        report = client.post("/api/execute", json=body).json()
        assert report["node_results"]["f"]["status"] in ("executed", "cached"), report["node_results"]["f"]
        return client.get("/api/results/k/f/out").json()["rows"][0]["x"]

    assert x_after({"workflow": wf}) == 2  # fora do espaço: a constante deste computador
    assert x_after({"workflow": wf, "espaco": sid}) == 10  # no espaço: a da equipe
    shared = client.post(
        f"/api/equipe/espacos/{sid}/definicoes/compartilhar", json={"tipo": "constantes", "id": "fator"}
    )
    assert shared.status_code == 200 and shared.json()["constantes"][0]["conteudo"]["value"] == "2"
