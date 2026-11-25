"""Editar feriados pela tela (spec 049, T09a, RF-4945..4948, CA-10)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

CAMPINAS = "3509502"


def _view(client: TestClient, local: str = "SP", ano: int = 2027) -> dict[str, Any]:
    data: dict[str, Any] = client.get(
        "/api/catalogo/feriados/editar", params={"local": local, "ano": ano}
    ).json()
    return data


def _row(data: dict[str, Any], holiday_id: str) -> dict[str, Any]:
    return next(r for r in data["linhas"] if r["id"] == holiday_id)


def _act(
    client: TestClient, action: str, body: dict[str, Any], local: str = "SP", ano: int = 2027
) -> dict[str, Any]:
    res = client.post(f"/api/catalogo/feriados/{action}", params={"local": local, "ano": ano}, json=body)
    assert res.status_code == 200, res.text
    data: dict[str, Any] = res.json()
    return data


def test_base_do_lugar_com_origem_e_regra(client: TestClient) -> None:
    data = _view(client)
    sp = _row(data, "SP/revolucao-constitucionalista")
    assert sp["data"] == "2027-07-09"
    assert sp["dia_semana"] == "sexta"
    assert sp["regra"] == "todo ano em 09/07 (desde 1997)"
    assert sp["origem"] == "programa"
    assert sp["revisado_em"] == "2026-11-22"
    corpus = _row(data, "BR/corpus-christi")
    assert corpus["regra"] == "60 dias depois da Páscoa"
    assert corpus["tipo"] == "ponto_facultativo"
    assert all(r["abrangencia"] in ("BR", "SP") for r in data["linhas"])


def test_incluir_feriado_municipal_e_usar_nos_dias_uteis(client: TestClient) -> None:
    """CA-10: Campinas não é capital; o feriado municipal entra pela edição e conta nos dias úteis."""
    data = _act(client, "incluir", {"nome": "Nossa Senhora da Conceição", "abrangencia": CAMPINAS, "tipo": "municipal",
                                     "fixo": "12-08"}, local=CAMPINAS)  # fmt: skip
    mine = next(r for r in data["linhas"] if r["nome"] == "Nossa Senhora da Conceição")
    assert mine["origem"] == "meu" and mine["editado"] is True
    assert mine["data"] == "2027-12-08"
    preview = client.post("/api/catalogo/previa", json={"id": "calendario/dias-uteis", "escolhas": {
        "local": CAMPINAS, "periodo": {"kind": "intervalo", "inicio": "2027-12-08", "fim": "2027-12-08"}}}).json()  # fmt: skip
    assert preview["linhas"] == [
        {"data": "2027-12-08", "dia_util": False, "feriado": "Nossa Senhora da Conceição"}
    ]


def test_recesso_de_data_unica(client: TestClient) -> None:
    data = _act(client, "incluir", {"nome": "Recesso", "abrangencia": "SP", "unico": "2027-12-24"})
    assert any(r["nome"] == "Recesso" and r["regra"] == "só em 24/12/2027" for r in data["linhas"])
    assert not any(r["nome"] == "Recesso" and r["data"] for r in _view(client, ano=2028)["linhas"])


def test_corrigir_e_restaurar(client: TestClient) -> None:
    data = _act(
        client, "corrigir", {"id": "SP/revolucao-constitucionalista", "campos": {"nome": "Revolução de 32"}}
    )
    row = _row(data, "SP/revolucao-constitucionalista")
    assert row["nome"] == "Revolução de 32" and row["editado"] is True
    assert row["original"]["nome"] == "Revolução Constitucionalista de 1932"
    data = _act(client, "restaurar", {"id": "SP/revolucao-constitucionalista"})
    row = _row(data, "SP/revolucao-constitucionalista")
    assert row["nome"] == "Revolução Constitucionalista de 1932" and row["editado"] is False


def test_trocar_a_regra_para_a_pascoa(client: TestClient) -> None:
    data = _act(client, "corrigir", {"id": "SP/revolucao-constitucionalista",
                                      "campos": {"fixo": None, "pascoa": 10, "unico": None}})  # fmt: skip
    assert _row(data, "SP/revolucao-constitucionalista")["regra"].startswith("10 dias depois da Páscoa")


def test_nao_vale_mais(client: TestClient) -> None:
    data = _act(client, "nao-vale-mais", {"id": "SP/revolucao-constitucionalista", "desde": 2027})
    row = _row(data, "SP/revolucao-constitucionalista")
    assert row["deixou_de_valer"] == 2027 and row["data"] is None
    assert _row(_view(client, ano=2026), "SP/revolucao-constitucionalista")["data"] == "2026-07-09"


def test_manter_o_meu_quando_o_programa_tambem_mudou(client: TestClient, settings: Any) -> None:
    import json

    _act(client, "corrigir", {"id": "SP/revolucao-constitucionalista", "campos": {"nome": "Revolução de 32"}})
    path = Path(settings.storage_dir) / "catalogo" / "feriados_meus.json"
    saved = json.loads(path.read_text(encoding="utf-8"))
    saved["corrigidos"]["SP/revolucao-constitucionalista"]["impressao"] = (
        "versao-antiga"  # simula a revisão do programa
    )
    path.write_text(json.dumps(saved), encoding="utf-8")
    row = _row(_view(client), "SP/revolucao-constitucionalista")
    assert row["programa_mudou"] is True and row["nome"] == "Revolução de 32"
    row = _row(
        _act(client, "manter-o-meu", {"id": "SP/revolucao-constitucionalista"}),
        "SP/revolucao-constitucionalista",
    )
    assert row["programa_mudou"] is False and row["nome"] == "Revolução de 32"


def test_entradas_invalidas(client: TestClient) -> None:
    bad = client.post("/api/catalogo/feriados/incluir", params={"local": "SP", "ano": 2027},
                      json={"nome": "X", "abrangencia": "SP", "fixo": "13-40"})  # fmt: skip
    assert bad.status_code == 422
    none = client.post("/api/catalogo/feriados/incluir", params={"local": "SP", "ano": 2027},
                       json={"nome": "X", "abrangencia": "SP"})  # fmt: skip
    assert none.status_code == 422
    assert (
        client.get("/api/catalogo/feriados/editar", params={"local": "XX1", "ano": 2027}).status_code == 422
    )
    gone = client.post("/api/catalogo/feriados/corrigir", params={"local": "SP", "ano": 2027},
                       json={"id": "SP/nao-existe", "campos": {"nome": "Y"}})  # fmt: skip
    assert gone.status_code == 404


def test_compartilhar_os_feriados_com_a_equipe(client: TestClient, tmp_path: Path) -> None:
    folder = tmp_path / "Compartilhada"
    folder.mkdir()
    sid = client.post(
        "/api/equipe/espacos", json={"acao": "criar", "caminho": str(folder), "nome": "Time"}
    ).json()["id"]
    _act(
        client,
        "incluir",
        {"nome": "Padroeira", "abrangencia": CAMPINAS, "tipo": "municipal", "fixo": "12-08"},
    )
    shared = client.post(
        f"/api/equipe/espacos/{sid}/definicoes/compartilhar", json={"tipo": "feriados", "id": "calendario"}
    )
    assert shared.status_code == 200, shared.text
    team = shared.json()["feriados"]
    assert team[0]["confere"] is True
    assert team[0]["conteudo"]["edicoes"]["incluidos"][0]["nome"] == "Padroeira"
    # Outra pessoa traz para o computador dela: as edições passam a valer aqui.
    _act(client, "restaurar", {"id": team[0]["conteudo"]["edicoes"]["incluidos"][0]["id"]})
    assert client.post(f"/api/equipe/espacos/{sid}/definicoes/feriados/calendario/trazer").status_code == 200
    assert any(r["nome"] == "Padroeira" for r in _view(client, local=CAMPINAS)["linhas"])
