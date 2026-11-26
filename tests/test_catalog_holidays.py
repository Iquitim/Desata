"""Base de feriados e dias úteis (spec 049, T04a, RF-4944..4948, CA-10)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path

import httpx
import polars as pl
import pytest

from conftest import catalog_fixture
from prodata.catalog import holidays as hol
from prodata.catalog.holidays import Edits, Holiday
from prodata.catalog.http import CatalogClient, CatalogError
from prodata.catalog.readers import anbima

Server = Callable[[Callable[[httpx.Request], httpx.Response]], list[httpx.Request]]
CAMPINAS = "3509502"
SAO_PAULO = "3550308"


@pytest.mark.parametrize(
    ("year", "expected"),
    [(2000, date(2000, 4, 23)), (2019, date(2019, 4, 21)), (2024, date(2024, 3, 31)), (2026, date(2026, 4, 5)),
     (2027, date(2027, 3, 28)), (2038, date(2038, 4, 25)), (2049, date(2049, 4, 18))],
)  # fmt: skip
def test_pascoa(year: int, expected: date) -> None:
    assert hol.easter(year) == expected


def test_nacionais_de_2026() -> None:
    frame = hol.table(2026, 2026, include_optional=False)
    assert frame["tipo"].unique().to_list() == ["nacional"]
    days = frame["data"].to_list()
    assert date(2026, 4, 3) in days  # Sexta-feira Santa
    assert date(2026, 11, 20) in days  # Consciência Negra, desde 2024
    assert len(days) == 10
    assert set(frame["origem"]) == {"calculado"}


def test_consciencia_negra_so_desde_2024() -> None:
    assert date(2023, 11, 20) not in hol.table(2023, 2023, include_optional=False)["data"].to_list()


def test_pontos_facultativos_marcados() -> None:
    frame = hol.table(2026, 2026).filter(pl.col("tipo") == "ponto_facultativo")
    assert frame["data"].to_list() == [
        date(2026, 2, 16),
        date(2026, 2, 17),
        date(2026, 2, 18),
        date(2026, 6, 4),
    ]


def test_tabela_do_programa_e_valida() -> None:
    base = hol.program_holidays()
    assert len({h.id for h in base}) == len(base)
    assert {h.abrangencia for h in base if h.tipo == "estadual"} >= hol.UFS - {"GO", "MT"}
    capitals = {h.abrangencia for h in base if h.tipo == "municipal"}
    # 27 capitais menos Brasília (entra pelo DF) e João Pessoa (sem feriado só da capital).
    assert len(capitals) == 25
    assert {"5300108", "2507507"}.isdisjoint(capitals)
    assert all(h.fonte for h in base)
    assert hol.program_revision() == "2026-11-22"


def test_estado_e_capital_de_sao_paulo() -> None:
    frame = hol.table(2026, 2026, SAO_PAULO, include_optional=False)
    names = dict(zip(frame["data"].to_list(), frame["nome"].to_list(), strict=True))
    assert names[date(2026, 7, 9)] == "Revolução Constitucionalista de 1932"
    assert names[date(2026, 1, 25)] == "Aniversário da Cidade de São Paulo"
    assert names[date(2026, 6, 4)] == "Corpus Christi"
    assert frame.filter(pl.col("data") == date(2026, 7, 9))["lei"].item() == "Lei estadual 9.497/1997"


def test_regras_especiais() -> None:
    sc = hol.table(2026, 2026, "SC").filter(pl.col("abrangencia") == "SC")["data"].to_list()
    assert sc == [date(2026, 8, 16), date(2026, 11, 29)]  # domingo seguinte
    es = hol.table(2026, 2026, "ES").filter(pl.col("abrangencia") == "ES")["data"].to_list()
    assert es == [date(2026, 4, 13)]  # Penha: 8 dias depois da Páscoa
    pe_2015 = hol.table(2015, 2015, "PE").filter(pl.col("abrangencia") == "PE")["data"].to_list()
    assert date(2015, 3, 1) in pe_2015  # primeiro domingo de março até 2017
    pr = hol.table(2013, 2014, "PR").filter(pl.col("abrangencia") == "PR")
    assert pr["data"].to_list() == [date(2013, 12, 19), date(2014, 11, 15)]


def test_ca10_dias_uteis_de_municipio_que_nao_e_capital() -> None:
    """CA-10: Campinas em 2027 desconta nacionais, o 9 de julho e os municipais que a pessoa cadastrou."""
    start, end = date(2027, 1, 1), date(2027, 12, 31)
    before = hol.business_days(start, end, CAMPINAS)
    july9 = before.filter(pl.col("data") == date(2027, 7, 9)).row(0, named=True)
    assert july9["dia_util"] is False
    assert july9["feriado"] == "Revolução Constitucionalista de 1932"
    # Campinas não é capital: o programa não traz feriado municipal dela.
    assert hol.table(2027, 2027, CAMPINAS).filter(pl.col("abrangencia") == CAMPINAS).is_empty()

    edits = Edits()
    edits.include(Holiday(id=f"{CAMPINAS}/nossa-senhora-da-conceicao", nome="Nossa Senhora da Conceição",
                          tipo="municipal", abrangencia=CAMPINAS, fixo="12-08"))  # fmt: skip
    edits.include(Holiday(id="meu/recesso-2027", nome="Recesso da empresa", tipo="meu", abrangencia=CAMPINAS,
                          unico=date(2027, 12, 24)))  # fmt: skip
    after = hol.business_days(start, end, CAMPINAS, edits=edits)
    lost = before.filter(pl.col("dia_util")).height - after.filter(pl.col("dia_util")).height
    assert lost == 2  # 08/12/2027 (quarta) e 24/12/2027 (sexta)
    mine = hol.table(2027, 2027, CAMPINAS, edits=edits).filter(pl.col("origem") == "meu")
    assert mine.height == 2


def test_ca10_nao_vale_mais_e_restaurar() -> None:
    sp = next(h for h in hol.program_holidays() if h.id == "SP/revolucao-constitucionalista")
    edits = Edits()
    edits.stop(sp.id, 2027)
    assert date(2026, 7, 9) in hol.table(2026, 2026, "SP", edits=edits)["data"].to_list()
    assert date(2027, 7, 9) not in hol.table(2027, 2027, "SP", edits=edits)["data"].to_list()
    edits.restore(sp.id)
    assert date(2027, 7, 9) in hol.table(2027, 2027, "SP", edits=edits)["data"].to_list()


def test_ca10_correcao_vence_e_avisa_quando_o_programa_tambem_muda() -> None:
    original = next(h for h in hol.program_holidays() if h.id == "SP/revolucao-constitucionalista")
    edits = Edits()
    edits.correct(original, nome="Revolução de 32")
    merged = {m.holiday.id: m for m in hol.merge([original], edits)}
    assert merged[original.id].holiday.nome == "Revolução de 32"
    assert merged[original.id].programa_mudou is False
    # Uma versão nova do programa revisa o mesmo feriado: a edição continua valendo, com a marca.
    revised = Holiday(**{**original.__dict__, "lei": "Lei estadual 9.497/1997 (revisada)", "desde": 1998})
    after = hol.merge([revised], edits)[0]
    assert after.holiday.nome == "Revolução de 32"
    assert after.programa_mudou is True
    assert after.original is revised


def test_feriado_novo_do_programa_nao_duplica_o_da_pessoa() -> None:
    edits = Edits()
    edits.include(Holiday(id="meu/x", nome="Padroeira", tipo="municipal", abrangencia=CAMPINAS, fixo="12-08"))
    old = list(hol.program_holidays())
    new_same = Holiday(id=f"{CAMPINAS}/padroeira", nome="N. Sra. da Conceição", tipo="municipal",
                       abrangencia=CAMPINAS, fixo="12-08")  # fmt: skip
    new_other = Holiday(id=f"{CAMPINAS}/aniversario", nome="Aniversário", tipo="municipal",
                        abrangencia=CAMPINAS, fixo="07-14")  # fmt: skip
    kept = hol.merge_program_update(old, [*old, new_same, new_other], edits)
    assert new_other in kept
    assert new_same not in kept
    assert len(kept) == len(old) + 1


def test_edicoes_vao_e_voltam_em_json() -> None:
    original = hol.program_holidays()[0]
    edits = Edits()
    edits.include(Holiday(id="meu/r", nome="Ponte", tipo="meu", abrangencia="SP", unico=date(2027, 11, 19)))
    edits.correct(original, nome="Outro nome")
    edits.stop("SP/revolucao-constitucionalista", 2030)
    again = Edits.from_json(edits.to_json())
    assert again == edits


@pytest.mark.parametrize(
    "kwargs",
    [
        {"fixo": "13-01"},
        {"fixo": "02-30x"},
        {"pascoa": 500},
        {"fixo": "01-01", "pascoa": 1},
        {},
        {"fixo": "01-01", "abrangencia": "XX"},
        {"fixo": "01-01", "abrangencia": "9999999"},
    ],
)
def test_regra_invalida(kwargs: dict[str, object]) -> None:
    args: dict[str, object] = {"id": "meu/x", "nome": "X", "tipo": "meu", "abrangencia": "SP"} | kwargs
    with pytest.raises(ValueError):
        Edits().include(Holiday(**args))  # type: ignore[arg-type]


def test_correcao_so_nos_campos_permitidos() -> None:
    original = hol.program_holidays()[0]
    with pytest.raises(ValueError, match="abrangencia"):
        Edits().correct(original, abrangencia="BR")


def test_lugar_invalido() -> None:
    with pytest.raises(ValueError):
        hol.places_for("SPX")
    assert hol.places_for(CAMPINAS) == {"BR", "SP", CAMPINAS}


# ------------------------------------------------------------------ ANBIMA


def test_planilha_da_anbima_real() -> None:
    frame = anbima.parse(catalog_fixture("anbima_feriados.xls"))
    assert frame.columns == ["data", "feriado"]
    assert frame["data"].min() == date(2001, 1, 1)
    assert frame["data"].max() == date(2099, 12, 25)
    assert frame["data"].n_unique() == frame.height


def test_calendario_bancario_calculado_bate_com_a_anbima() -> None:
    """Conferência cruzada: sem a planilha, o cálculo dá exatamente os mesmos dias, de 2001 a 2099."""
    real = set(anbima.parse(catalog_fixture("anbima_feriados.xls"))["data"].to_list())
    computed = set(hol.table(2001, 2099, calendar="bancario")["data"].to_list())
    assert computed == real


def test_bancario_usa_a_anbima_quando_lida() -> None:
    rows = hol.anbima_holidays(anbima.parse(catalog_fixture("anbima_feriados.xls")))
    frame = hol.table(2026, 2026, calendar="bancario", anbima=rows)
    assert set(frame["origem"]) == {"anbima"}
    assert date(2026, 2, 16) in frame["data"].to_list()


def test_planilha_que_nao_e_planilha(catalog_server: Server) -> None:
    catalog_server(lambda r: httpx.Response(200, content=b"<html>manutencao</html>"))
    with CatalogClient() as client, pytest.raises(CatalogError, match="ANBIMA"):
        anbima.read(client)


def test_dia_util_anterior() -> None:
    frame = hol.business_days(date(2026, 4, 1), date(2026, 4, 10))
    assert hol.previous_business_day(date(2026, 4, 5), frame) == date(
        2026, 4, 2
    )  # domingo de Páscoa → quinta
    assert hol.previous_business_day(date(2026, 4, 6), frame) == date(2026, 4, 6)


# ------------------------------------------------------------------ município fora da base (RF-4967, CA-20)


def test_ca20_municipio_fora_da_base_avisa(tmp_path: Path) -> None:
    from prodata.catalog import places, sources

    campinas = "3509502"
    assert hol.outside_base(campinas) and not hol.outside_base("3550308") and not hol.outside_base("SP")
    with CatalogClient() as client:
        choices = {
            "local": campinas,
            "periodo": {"kind": "intervalo", "inicio": "2027-01-01", "fim": "2027-12-31"},
        }
        result = sources.read(client, "calendario/feriados", choices, tmp_path)
        assert any("os de Campinas não estão incluídos" in w for w in result.warnings), result.warnings
        days = sources.read(client, "calendario/dias-uteis", choices, tmp_path)
        assert any("Editar feriados" in w for w in days.warnings)
        capital = sources.read(client, "calendario/feriados", {**choices, "local": "3550308"}, tmp_path)
        assert not any("capitais" in w for w in capital.warnings)
    edits = Edits()
    edits.include(
        Holiday(
            id=f"{campinas}/padroeira", nome="Padroeira", tipo="municipal", abrangencia=campinas, fixo="12-08"
        )
    )
    assert not hol.outside_base(campinas, edits)
    note = next(f for f in places.detail(f"mun:{campinas}")["fontes"] if f["id"] == "calendario/feriados")[
        "nota"
    ]
    assert "só das capitais" in note
    assert (
        next(f for f in places.detail("mun:3550308")["fontes"] if f["id"] == "calendario/feriados")["nota"]
        == ""
    )
