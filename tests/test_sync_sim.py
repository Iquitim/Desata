"""O próprio simulador de sincronização (spec 047, T01): os outros testes da equipe dependem dele estar certo."""

from __future__ import annotations

from pathlib import Path

from sync_sim import SyncSim, conflict_name


def test_change_reaches_the_other_machine_only_after_both_sync(tmp_path: Path) -> None:
    sim = SyncSim(tmp_path)
    (sim.path("NOTEANA") / "f.prodata.json").write_text("v1", encoding="utf-8")
    assert not (sim.path("NOTEBRUNO") / "f.prodata.json").exists()  # ainda não sincronizou: o atraso
    sim.sync("NOTEANA")
    assert not (sim.path("NOTEBRUNO") / "f.prodata.json").exists()
    sim.sync("NOTEBRUNO")
    assert (sim.path("NOTEBRUNO") / "f.prodata.json").read_text(encoding="utf-8") == "v1"


def test_both_change_before_syncing_makes_a_onedrive_style_conflict(tmp_path: Path) -> None:
    sim = SyncSim(tmp_path)
    (sim.path("NOTEANA") / "f.prodata.json").write_text("v1", encoding="utf-8")
    sim.sync_all()
    (sim.path("NOTEANA") / "f.prodata.json").write_text("da Ana", encoding="utf-8")
    (sim.path("NOTEBRUNO") / "f.prodata.json").write_text("do Bruno", encoding="utf-8")
    sim.sync("NOTEANA")  # a Ana chega primeiro na nuvem
    sim.sync("NOTEBRUNO")
    sim.sync_all()
    bruno = sim.path("NOTEBRUNO")
    assert (bruno / "f.prodata.json").read_text(encoding="utf-8") == "da Ana"
    assert (bruno / "f-NOTEBRUNO.prodata.json").read_text(encoding="utf-8") == "do Bruno"
    assert (sim.path("NOTEANA") / "f-NOTEBRUNO.prodata.json").is_file()  # a cópia de conflito também chega
    assert sim.conflicts == ["f-NOTEBRUNO.prodata.json"]


def test_deletion_propagates(tmp_path: Path) -> None:
    sim = SyncSim(tmp_path)
    (sim.path("NOTEANA") / "f.prodata.json").write_text("v1", encoding="utf-8")
    sim.sync_all()
    (sim.path("NOTEANA") / "f.prodata.json").unlink()
    sim.sync_all()
    assert not (sim.path("NOTEBRUNO") / "f.prodata.json").exists()


def test_conflict_name_keeps_every_extension() -> None:
    assert conflict_name("_equipe/membros.json", "NOTEANA") == "_equipe/membros-NOTEANA.json"
    assert conflict_name("vendas.prodata.json", "PC1") == "vendas-PC1.prodata.json"
