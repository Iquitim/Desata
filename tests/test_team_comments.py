"""Espaço da equipe, spec 048 marco 3 (RF-4811..4816): comentários nas caixas como eventos assinados."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from prodata.domain.workflow import Workflow
from prodata.errors import InvalidInputError, NotFoundError
from prodata.team.comments import COMMENTS_DIR
from prodata.team.workspaces import CONTROL
from test_team_roles import Person

Team = tuple[Person, Person, Path, str]


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
        t.change_members(sid, "aceitar", "bruno", "leitor")  # Leitor também comenta
        t.save(
            sid,
            Workflow.model_validate(
                {"id": "fechamento", "name": "F", "nodes": [{"id": "filtro", "type": "prep.select"}]}
            ),
        )
    return ana, bruno, folder, sid


def test_reader_comments_and_author_sees_new(team: Team) -> None:
    ana, bruno, folder, sid = team
    with bruno.acting() as t:
        view = t.comment(
            sid,
            "fechamento",
            "comentario",
            texto="Por que tira as devoluções?",
            caixa="filtro",
            rotulo="Filtro",
        )
    thread = view["conversas"][0]
    assert thread["nome"] == "Bruno Lima" and thread["minha"] and view["por_caixa"] == {"filtro": 1}
    with ana.acting() as t:
        seen = t.comments(sid, "fechamento")
        assert seen["novos"] == 1 and seen["conversas"][0]["minha"] is False
        t.comment(sid, "fechamento", "resposta", texto="Elas entram no outro fluxo.", alvo=thread["id"])
        after = t.comment(sid, "fechamento", "resolver", alvo=thread["id"])
        assert (
            after["novos"] == 0
            and after["por_caixa"] == {}
            and after["conversas"][0]["resolvido_por"] == "Ana Souza"
        )
    with bruno.acting() as t:
        mine = t.comments(sid, "fechamento")
        assert (
            mine["novos"] == 1
            and mine["conversas"][0]["respostas"][0]["texto"] == "Elas entram no outro fluxo."
        )
    files = list((folder / CONTROL / COMMENTS_DIR / "fechamento").glob("*.json"))
    assert len(files) == 3  # um arquivo por evento: ninguém reescreve o arquivo de outro
    assert (
        not (folder / "fechamento.prodata.json").read_text(encoding="utf-8").count("devoluções")
    )  # não vai no fluxo


def test_forged_or_foreign_deletion_is_ignored(team: Team) -> None:
    ana, bruno, folder, sid = team
    with ana.acting() as t:
        thread = t.comment(sid, "fechamento", "comentario", texto="Conferir a meta", caixa="filtro")[
            "conversas"
        ][0]
    with bruno.acting() as t:
        t.comment(sid, "fechamento", "apagar", alvo=thread["id"])  # Bruno não é o autor nem administrador
        assert [c["texto"] for c in t.comments(sid, "fechamento")["conversas"]] == ["Conferir a meta"]
    path = next((folder / CONTROL / COMMENTS_DIR / "fechamento").glob("*-ana-*.json"))
    data = json.loads(path.read_text(encoding="utf-8"))
    data["texto"] = "Texto trocado por fora"
    path.write_text(json.dumps(data), encoding="utf-8")
    with ana.acting() as t:
        assert t.comments(sid, "fechamento")["conversas"] == []  # sem assinatura válida, não aparece


def test_author_edits_and_admin_deletes(team: Team) -> None:
    ana, bruno, _, sid = team
    with bruno.acting() as t:
        thread = t.comment(sid, "fechamento", "comentario", texto="Primeira versão", caixa="filtro")[
            "conversas"
        ][0]
        edited = t.comment(sid, "fechamento", "editar", texto="Versão corrigida", alvo=thread["id"])[
            "conversas"
        ][0]
        assert edited["texto"] == "Versão corrigida" and edited["editado"]
    with ana.acting() as t:
        t.comment(
            sid, "fechamento", "editar", texto="Ana mexendo", alvo=thread["id"]
        )  # não é a autora: não vale
        assert t.comments(sid, "fechamento")["conversas"][0]["texto"] == "Versão corrigida"
        assert (
            t.comment(sid, "fechamento", "apagar", alvo=thread["id"])["conversas"] == []
        )  # administradora apaga


def test_comment_needs_text_box_and_existing_target(team: Team) -> None:
    ana, _, _, sid = team
    with ana.acting() as t:
        with pytest.raises(InvalidInputError, match="Escreva"):
            t.comment(sid, "fechamento", "comentario", texto="  ", caixa="filtro")
        with pytest.raises(NotFoundError):
            t.comment(sid, "fechamento", "resposta", texto="oi", alvo="20260101-000000-000000-ana-deadbeef")


def test_api_comment_round_trip(client: object, tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    assert isinstance(client, TestClient)
    folder = tmp_path / "Compartilhada"
    folder.mkdir()
    sid = client.post(
        "/api/equipe/espacos", json={"acao": "criar", "caminho": str(folder), "nome": "Time"}
    ).json()["id"]
    flow = {"id": "fx", "name": "F", "edges": [], "nodes": [{"id": "f", "type": "prep.select", "config": {}}]}
    client.put(f"/api/equipe/espacos/{sid}/fluxos/fx", json=flow)
    res = client.post(f"/api/equipe/espacos/{sid}/fluxos/fx/comentarios",
                      json={"tipo": "comentario", "caixa": "f", "rotulo": "Formula", "texto": "Por quê?"})  # fmt: skip
    assert res.status_code == 200, res.text
    assert res.json()["por_caixa"] == {"f": 1}
    listed = client.get(f"/api/equipe/espacos/{sid}/fluxos/fx/comentarios?visto=true").json()
    assert listed["conversas"][0]["texto"] == "Por quê?"
