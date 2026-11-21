"""Espaço da equipe, marco 2 (spec 047, RF-4711..4715): papéis e assinaturas, inclusive as tentativas de burlar."""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from prodata.connectors.secrets import MemorySecretStore
from prodata.domain.workflow import Workflow
from prodata.errors import InvalidInputError
from prodata.services.workflows import WorkflowRepository
from prodata.team.identity import IdentityStore
from prodata.team.service import TeamService
from prodata.team.signing import Member, sign_members
from prodata.team.workspaces import CONTROL, Workspaces


class Person:
    """Uma pessoa com o próprio computador: cofre, pasta de dados e usuário do Windows."""

    def __init__(self, root: Path, user: str, name: str, monkeypatch: pytest.MonkeyPatch) -> None:
        self.user, self.monkeypatch = user, monkeypatch
        home = root / user
        self.identity = IdentityStore(MemorySecretStore(), home / "equipe.json")
        with self.acting():
            self.identity.set_name(name)
        self.team = TeamService(Workspaces(home / "espacos.json", "desata", "Desata"), self.identity,
                                WorkflowRepository(home / "biblioteca"), home / "estado")  # fmt: skip

    @contextmanager
    def acting(self) -> Iterator[TeamService]:
        self.monkeypatch.setenv("PRODATA_USUARIO", self.user)
        yield getattr(self, "team", None)  # type: ignore[misc]


def flow(name: str = "Fechamento") -> Workflow:
    return Workflow.model_validate(
        {"id": "fechamento", "name": name, "nodes": [{"id": "n1", "type": "prep.select"}]}
    )


@pytest.fixture
def team(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Person, Person, Path, str]:
    folder = tmp_path / "pasta_da_equipe"
    folder.mkdir()
    ana = Person(tmp_path, "ana", "Ana Souza", monkeypatch)
    bruno = Person(tmp_path, "bruno", "Bruno Lima", monkeypatch)
    with ana.acting() as t:
        space_id = t.create(str(folder), "Controladoria")["id"]
    with bruno.acting() as t:
        joined = t.join(str(folder))
    assert joined["papel"] is None and joined["pedido"]  # entrou como pedido
    return ana, bruno, folder, space_id


def test_creator_is_admin_and_requests_wait(team: tuple[Person, Person, Path, str]) -> None:
    ana, bruno, _, sid = team
    with ana.acting() as t:
        view = t.members_view(sid)
    assert [(m["usuario"], m["papel"]) for m in view["membros"]] == [("ana", "administrador")]
    assert [p["nome"] for p in view["pedidos"]] == ["Bruno Lima"] and view["um_administrador"]
    with bruno.acting() as t, pytest.raises(InvalidInputError, match="ainda não é membro"):
        t.save(sid, flow())


def test_editor_saves_signed_and_others_trust_it(team: tuple[Person, Person, Path, str]) -> None:
    ana, bruno, _, sid = team
    with ana.acting() as t:
        t.change_members(sid, "aceitar", "bruno", "editor")
    with bruno.acting() as t:
        t.save(sid, flow("do Bruno"))
    with ana.acting() as t:
        workflow, reason = t.get(sid, "fechamento")
    assert workflow.name == "do Bruno" and reason is None


def test_reader_cannot_save(team: tuple[Person, Person, Path, str]) -> None:
    ana, bruno, _, sid = team
    with ana.acting() as t:
        t.change_members(sid, "aceitar", "bruno", "leitor")
    with bruno.acting() as t:
        assert t.flows(sid) == []  # lê
        with pytest.raises(InvalidInputError, match="Leitor"):
            t.save(sid, flow())


def test_flow_changed_outside_the_program_is_refused(team: tuple[Person, Person, Path, str]) -> None:
    """CA-04: alguém troca o arquivo do fluxo por fora."""
    ana, _, folder, sid = team
    with ana.acting() as t:
        t.save(sid, flow())
    path = folder / "fechamento.prodata.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["name"] = "Adulterado"
    path.write_text(json.dumps(data), encoding="utf-8")
    with ana.acting() as t:
        _, reason = t.get(sid, "fechamento")
    assert reason and "alterado fora do programa" in reason
    (folder / "fechamento.prodata.json.sig").unlink()
    with ana.acting() as t:
        assert "não tem assinatura" in (t.get(sid, "fechamento")[1] or "")


def test_hand_edited_member_list_is_refused(team: tuple[Person, Person, Path, str]) -> None:
    """CA-03: Bruno edita membros.json à mão para virar administrador."""
    ana, bruno, folder, sid = team
    with ana.acting() as t:
        t.change_members(sid, "aceitar", "bruno", "editor")
        t.save(sid, flow())
    path = folder / CONTROL / "membros.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for m in data["membros"]:
        if m["usuario"] == "bruno":
            m["papel"] = "administrador"
    path.write_text(json.dumps(data), encoding="utf-8")
    for person in (ana, bruno):
        with person.acting() as t:
            assert "alterada fora do programa" in (t.members(sid)[1] or "")
            assert t.describe(t.workspaces.get(sid))["protegido"]
            assert "lista de membros" in (t.get(sid, "fechamento")[1] or "")  # nada do espaço executa


def test_non_admin_cannot_sign_a_new_member_list(team: tuple[Person, Person, Path, str]) -> None:
    ana, bruno, folder, sid = team
    with ana.acting() as t:
        t.change_members(sid, "aceitar", "bruno", "editor")
        current = t.members(sid)[0]
    assert current is not None
    promoted = [m.model_copy(update={"papel": "administrador"}) for m in current.membros]
    with bruno.acting():  # Bruno assina, com a própria chave, uma lista em que ele é administrador
        forged = sign_members(bruno.identity, sid, current.versao + 1, promoted)
    (folder / CONTROL / "membros.json").write_text(forged.model_dump_json(), encoding="utf-8")
    with ana.acting() as t:
        assert "não era administrador" in (t.members(sid)[1] or "")


def test_old_member_list_cannot_be_restored(team: tuple[Person, Person, Path, str]) -> None:
    ana, _bruno, folder, sid = team
    path = folder / CONTROL / "membros.json"
    with ana.acting() as t:
        t.change_members(sid, "aceitar", "bruno", "administrador")
        when_admin = path.read_text(encoding="utf-8")
        t.change_members(sid, "papel", "bruno", "leitor")
    path.write_text(when_admin, encoding="utf-8")  # Bruno restaura a lista de quando era administrador
    with ana.acting() as t:
        assert "mais antiga" in (t.members(sid)[1] or "")


def test_signature_does_not_travel_to_another_space(
    team: tuple[Person, Person, Path, str], tmp_path: Path
) -> None:
    ana, _, folder, sid = team
    other_folder = tmp_path / "outro"
    other_folder.mkdir()
    with ana.acting() as t:
        t.save(sid, flow())
        other = t.create(str(other_folder), "Outro")["id"]
    for name in ("fechamento.prodata.json", "fechamento.prodata.json.sig"):
        shutil.copy2(folder / name, other_folder / name)
    with ana.acting() as t:
        assert "alterado fora do programa" in (t.get(other, "fechamento")[1] or "")


def test_space_needs_one_admin(team: tuple[Person, Person, Path, str]) -> None:
    ana, _, _, sid = team
    with ana.acting() as t, pytest.raises(InvalidInputError, match="pelo menos um administrador"):
        t.change_members(sid, "papel", "ana", "editor")


def test_removed_member_flow_no_longer_trusted(team: tuple[Person, Person, Path, str]) -> None:
    ana, bruno, _, sid = team
    with ana.acting() as t:
        t.change_members(sid, "aceitar", "bruno", "editor")
    with bruno.acting() as t:
        t.save(sid, flow("do Bruno"))
    with ana.acting() as t:
        t.change_members(sid, "remover", "bruno")
        assert "não é membro" in (t.get(sid, "fechamento")[1] or "")


def test_member_list_never_holds_private_keys(team: tuple[Person, Person, Path, str]) -> None:
    ana, _, folder, _ = team
    secret = ana.identity._secrets.get("equipe:identidade")  # type: ignore[attr-defined]
    assert secret
    for path in folder.rglob("*"):
        if path.is_file():
            assert secret not in path.read_text(encoding="utf-8", errors="ignore")


def test_sign_members_payload_is_stable() -> None:
    people = [Member(usuario="b", nome="B", chave_publica="x" * 44, papel="editor"),
              Member(usuario="a", nome="A", chave_publica="y" * 44, papel="administrador")]  # fmt: skip
    from prodata.team.signing import members_payload

    assert members_payload("s", 1, people) == members_payload("s", 1, list(reversed(people)))
