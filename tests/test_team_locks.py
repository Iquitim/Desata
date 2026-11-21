"""Quem está editando (spec 047, RF-4721..4724): marcas de edição que avisam, renovam e expiram."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from prodata.team.identity import Identity
from prodata.team.locks import EXPIRES_AFTER, LockStore
from sync_sim import SyncSim
from test_team_roles import Person, flow


class Clock:
    now_value = datetime(2026, 11, 21, 10, 32, tzinfo=UTC)

    @classmethod
    def now(cls, tz: object = None) -> datetime:
        return cls.now_value


def who(user: str, name: str) -> Identity:
    return Identity(usuario=user, nome=name, chave_publica="A" * 44)


ANA, BRUNO = who("ana", "Ana Souza"), who("bruno", "Bruno Lima")


@pytest.fixture(autouse=True)
def reset_clock() -> None:
    Clock.now_value = datetime(2026, 11, 21, 10, 32, tzinfo=UTC)


def test_second_person_is_told_who_is_editing(tmp_path: Path) -> None:
    locks = LockStore(tmp_path, Clock)  # type: ignore[arg-type]
    assert locks.acquire("fechamento", ANA) is None
    theirs = locks.acquire("fechamento", BRUNO)
    assert theirs is not None and theirs.nome == "Ana Souza" and theirs.desde == Clock.now_value
    assert locks.acquire("fechamento", BRUNO, force=True) is None  # Editar mesmo assim
    assert locks.current("fechamento").usuario == "bruno"  # type: ignore[union-attr]


def test_renew_keeps_and_release_frees(tmp_path: Path) -> None:
    locks = LockStore(tmp_path, Clock)  # type: ignore[arg-type]
    locks.acquire("f", ANA)
    Clock.now_value += timedelta(minutes=2)
    assert locks.renew("f", ANA)
    Clock.now_value += timedelta(minutes=2)
    assert locks.other("f", BRUNO) is not None  # renovou: ainda vale
    locks.release("f", BRUNO)  # soltar a de outra pessoa não faz nada
    assert locks.current("f") is not None
    locks.release("f", ANA)
    assert locks.current("f") is None


def test_lock_expires_when_the_program_closes_without_releasing(tmp_path: Path) -> None:
    """CA-05: Ana fecha o programa sem fechar o fluxo; depois do prazo, a marca não vale mais."""
    locks = LockStore(tmp_path, Clock)  # type: ignore[arg-type]
    locks.acquire("f", ANA)
    Clock.now_value += EXPIRES_AFTER + timedelta(seconds=1)
    assert locks.other("f", BRUNO) is None and locks.acquire("f", BRUNO) is None


def test_clock_ahead_on_another_computer_does_not_freeze_the_lock(tmp_path: Path) -> None:
    locks = LockStore(tmp_path, Clock)  # type: ignore[arg-type]
    Clock.now_value += timedelta(days=1)  # o computador da Ana está um dia adiantado
    locks.acquire("f", ANA)
    Clock.now_value -= timedelta(days=1)
    assert locks.current("f") is not None
    Clock.now_value += EXPIRES_AFTER + timedelta(seconds=1)
    assert locks.current("f") is None


def test_renew_reports_when_someone_took_over(tmp_path: Path) -> None:
    locks = LockStore(tmp_path, Clock)  # type: ignore[arg-type]
    locks.acquire("f", ANA)
    locks.acquire("f", BRUNO, force=True)
    assert not locks.renew("f", ANA)


def test_lock_travels_through_sync(tmp_path: Path) -> None:
    sim = SyncSim(tmp_path)
    ana, bruno = LockStore(sim.path("NOTEANA"), Clock), LockStore(sim.path("NOTEBRUNO"), Clock)  # type: ignore[arg-type]
    ana.acquire("f", ANA)
    assert bruno.other("f", BRUNO) is None  # a marca ainda não chegou: o aviso é aviso, não trava
    sim.sync_all()
    assert bruno.other("f", BRUNO) is not None and set(bruno.all()) == {"f"}


def test_service_modes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = tmp_path / "pasta"
    folder.mkdir()
    ana, bruno = (
        Person(tmp_path, "ana", "Ana Souza", monkeypatch),
        Person(tmp_path, "bruno", "Bruno Lima", monkeypatch),
    )
    with ana.acting() as t:
        sid = t.create(str(folder), "Equipe")["id"]
        t.save(sid, flow())
    with bruno.acting() as t:
        t.join(str(folder))
    with ana.acting() as t:
        t.change_members(sid, "aceitar", "bruno", "leitor")
        assert t.editing(sid, "fechamento", "abrir") == {"modo": "editar"}
    with bruno.acting() as t:
        opened = t.editing(sid, "fechamento", "abrir")
        assert opened["modo"] == "ver" and "Leitor" in opened["motivo"]
        assert t.flows(sid)[0].editando == "Ana Souza"  # a biblioteca mostra quem está editando
    with ana.acting() as t:
        t.change_members(sid, "papel", "bruno", "editor")
    with bruno.acting() as t:
        conflict = t.editing(sid, "fechamento", "abrir")
        assert conflict["modo"] == "conflito" and conflict["editando"]["nome"] == "Ana Souza"
        assert t.editing(sid, "fechamento", "abrir", force=True) == {"modo": "editar"}
