"""Espaço da equipe, marco 1 (spec 047, RF-4701..4705): identidade, espaços por marca, fluxos do espaço e a
garantia de que, sem espaço, nada muda (RF-4702)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from prodata.connectors.secrets import MemorySecretStore
from prodata.domain.workflow import Workflow
from prodata.errors import InvalidInputError, NotFoundError
from prodata.services.workflows import WorkflowRepository
from prodata.team import repository as repo_module
from prodata.team.identity import IDENTITY_KEY, IdentityStore, verify
from prodata.team.repository import SpaceRepository
from prodata.team.service import TeamService
from prodata.team.workspaces import CONTROL, Workspaces
from sync_sim import SyncSim


def flow(wid: str = "vendas", name: str = "Vendas") -> Workflow:
    return Workflow.model_validate({"id": wid, "name": name, "nodes": [{"id": "n1", "type": "prep.select"}]})


# ---------------------------------------------------------------- identidade (RF-4704)


def test_identity_key_lives_in_the_vault_and_signs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRODATA_USUARIO", "ana.souza")
    vault = MemorySecretStore()
    me = IdentityStore(vault, tmp_path / "equipe.json")
    who = me.current()
    assert who.usuario == "ana.souza" and who.nome == "ana.souza"  # sem nome escolhido, o usuário do Windows
    assert vault.get(IDENTITY_KEY)  # a chave privada está no cofre...
    assert (
        vault.get(IDENTITY_KEY) not in (tmp_path / "equipe.json").read_text(encoding="utf-8")
        if (tmp_path / "equipe.json").exists()
        else True
    )
    signature = me.sign(b"conteudo")
    assert verify(who.chave_publica, b"conteudo", signature)
    assert not verify(who.chave_publica, b"conteudo adulterado", signature)
    assert me.set_name("Ana Souza").nome == "Ana Souza"
    assert vault.get(IDENTITY_KEY) not in (tmp_path / "equipe.json").read_text(
        encoding="utf-8"
    )  # ...e nunca no arquivo


def test_each_brand_has_its_own_identity(tmp_path: Path) -> None:
    """Cofres de marcas diferentes = chaves diferentes, mesmo no mesmo computador e com o mesmo usuário."""
    desata = IdentityStore(MemorySecretStore(), tmp_path / "d.json").current()
    prodata = IdentityStore(MemorySecretStore(), tmp_path / "p.json").current()
    assert desata.chave_publica != prodata.chave_publica


def test_odd_windows_user_becomes_a_safe_name(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PRODATA_USUARIO", "EMPRESA\\joão silva")
    assert IdentityStore(MemorySecretStore(), tmp_path / "e.json").current().usuario == "EMPRESA_jo_o_silva"


# ---------------------------------------------------------------- espaços (RF-4701, RF-4716)


def test_create_join_leave_and_brand_ownership(tmp_path: Path) -> None:
    folder = tmp_path / "Equipe"
    folder.mkdir()
    desata = Workspaces(tmp_path / "d" / "espacos.json", "desata", "Desata")
    space = desata.create(str(folder), "Controladoria")
    assert space.estado == "ok" and (folder / CONTROL / "espaco.json").is_file()
    with pytest.raises(InvalidInputError, match="já é um espaço"):
        desata.create(str(folder), "De novo")
    colleague = Workspaces(tmp_path / "b" / "espacos.json", "desata", "Desata")
    assert colleague.join(str(folder)).id == space.id
    other_brand = Workspaces(tmp_path / "p" / "espacos.json", "protege", "PRO.DATA")
    with pytest.raises(InvalidInputError, match="Este espaço é do Desata"):
        other_brand.join(str(folder))
    colleague.leave(space.id)
    assert colleague.spaces() == [] and (folder / CONTROL / "espaco.json").is_file()  # sair não apaga nada


def test_missing_folder_and_relative_path(tmp_path: Path) -> None:
    spaces = Workspaces(tmp_path / "espacos.json", "desata", "Desata")
    with pytest.raises(InvalidInputError, match="caminho completo"):
        spaces.create("relativa", "X")
    folder = tmp_path / "Some"
    folder.mkdir()
    space = spaces.create(str(folder), "Some")
    folder.joinpath(CONTROL, "espaco.json").unlink()
    folder.joinpath(CONTROL).rmdir()
    folder.rmdir()
    assert spaces.get(space.id).estado == "pasta_ausente"
    with pytest.raises(NotFoundError):
        Workspaces(tmp_path / "x.json", "desata", "Desata").join(str(tmp_path))


def test_folder_without_write_permission_is_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "Equipe"
    folder.mkdir()
    spaces = Workspaces(tmp_path / "espacos.json", "desata", "Desata")
    space = spaces.create(str(folder), "Equipe")
    monkeypatch.setattr("prodata.team.workspaces.writable", lambda *_a, **_k: False)
    state = spaces.get(space.id)
    assert state.estado == "somente_leitura" and "só para leitura" in state.motivo


# ---------------------------------------------------------------- fluxos do espaço (RF-4703, RF-4705, RF-4762, RF-4763)


def test_flows_travel_through_a_synced_folder(tmp_path: Path) -> None:
    sim = SyncSim(tmp_path)
    ana, bruno = SpaceRepository(sim.path("NOTEANA")), SpaceRepository(sim.path("NOTEBRUNO"))
    ana.save(flow())
    assert bruno.flows() == []  # ainda não sincronizou
    sim.sync_all()
    assert [f.name for f in bruno.flows()] == ["Vendas"]


def test_sync_conflict_copies_do_not_become_loose_flows(tmp_path: Path) -> None:
    sim = SyncSim(tmp_path)
    ana, bruno = SpaceRepository(sim.path("NOTEANA")), SpaceRepository(sim.path("NOTEBRUNO"))
    ana.save(flow())
    sim.sync_all()
    ana.save(flow(name="Vendas da Ana"))
    bruno.save(flow(name="Vendas do Bruno"))
    sim.sync("NOTEANA")
    sim.sync_all()
    assert sim.conflicts  # a sincronização criou a cópia com o nome do computador
    assert [f.id for f in bruno.flows()] == ["vendas"]  # e ela não aparece como outro fluxo


def test_space_never_keeps_the_data_sample(tmp_path: Path) -> None:
    import polars as pl

    from prodata.domain.samples import SourceSample

    wf = flow()
    wf.samples["dataset:a"] = SourceSample.of(pl.DataFrame({"cpf": ["123"]}), "a.csv")
    SpaceRepository(tmp_path).save(wf)
    assert "cpf" not in (tmp_path / "vendas.prodata.json").read_text(encoding="utf-8")


def test_file_held_by_sync_is_retried(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real, calls = os.replace, {"n": 0}

    def flaky(src: str, dst: str) -> None:
        calls["n"] += 1
        if calls["n"] <= 2:
            raise PermissionError(32, "O arquivo já está sendo usado por outro processo")
        real(src, dst)

    monkeypatch.setattr(repo_module.os, "replace", flaky)
    monkeypatch.setattr(repo_module, "RETRY_WAIT", 0)
    SpaceRepository(tmp_path).save(flow())
    assert calls["n"] == 3 and (tmp_path / "vendas.prodata.json").is_file()
    assert not list(tmp_path.glob("*.tmp"))  # nenhum temporário sobrando


def test_move_to_space_and_copy_back(tmp_path: Path) -> None:
    folder = tmp_path / "Equipe"
    folder.mkdir()
    library = WorkflowRepository(tmp_path / "biblioteca")
    team = TeamService(Workspaces(tmp_path / "espacos.json", "desata", "Desata"),
                       IdentityStore(MemorySecretStore(), tmp_path / "equipe.json"), library)  # fmt: skip
    space = team.workspaces.create(str(folder), "Equipe")
    library.save(flow())
    team.move_from_library(space.id, "vendas")
    assert not library.exists("vendas") and [f.id for f in team.flows(space.id)] == ["vendas"]
    team.copy_to_library(space.id, "vendas", "wf_copia")
    assert library.get("wf_copia").name == "Vendas (cópia)" and team.get(space.id, "vendas").name == "Vendas"


# ---------------------------------------------------------------- sem espaço, nada muda (RF-4702, CA-01)


def test_without_a_space_nothing_is_created(client: TestClient, settings: object) -> None:
    storage = Path(settings.storage_dir)  # type: ignore[attr-defined]
    before = {p.name for p in storage.iterdir()}
    assert client.get("/api/equipe").json() == {"configurado": False, "espacos": []}
    after = {p.name for p in storage.iterdir()}
    assert after == before and "espacos.json" not in after and "equipe.json" not in after


def test_api_create_space_and_save_a_flow(client: TestClient, tmp_path: Path) -> None:
    folder = tmp_path / "Compartilhada"
    folder.mkdir()
    space = client.post(
        "/api/equipe/espacos", json={"acao": "criar", "caminho": str(folder), "nome": "Time"}
    ).json()
    overview = client.get("/api/equipe").json()
    assert overview["configurado"] and overview["espacos"][0]["nome"] == "Time"
    body = flow().model_dump(mode="json", by_alias=True)
    assert client.put(f"/api/equipe/espacos/{space['id']}/fluxos/vendas", json=body).status_code == 200
    listed = client.get(f"/api/equipe/espacos/{space['id']}/fluxos").json()
    assert [f["id"] for f in listed] == ["vendas"]
    assert client.get(f"/api/equipe/espacos/{space['id']}/fluxos/..%2F..%2Fx").status_code in (404, 422)
