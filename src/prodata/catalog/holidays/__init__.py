"""Base de feriados e dias úteis (spec 049, RF-4944..4948).

Quatro origens numa base só:
- **calculado**: nacionais fixos e móveis (pela Páscoa) e os pontos facultativos federais, sem internet;
- **ANBIMA**: feriados bancários, lidos da planilha da ANBIMA (``read_anbima``);
- **programa**: estados e capitais, em ``base_estados_capitais.json``, com a lei e a fonte de cada um;
- **meus**: as edições da pessoa (``Edits``), que ficam por cima, sem alterar nada do programa.

A edição da pessoa vence a revisão do programa (RF-4947): uma correção guarda a impressão do feriado do programa no
momento da edição; se a impressão atual for outra, a linha ganha a marca "o programa também mudou".
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from functools import cache
from pathlib import Path
from typing import Any, Literal

import polars as pl

HolidayType = Literal["nacional", "estadual", "municipal", "bancario", "ponto_facultativo", "meu"]
Origin = Literal["calculado", "anbima", "programa", "meu"]
Adjust = Literal["domingo_seguinte"]
Calendar = Literal["civil", "bancario"]

BASE_FILE = Path(__file__).with_name("base_estados_capitais.json")
UF_BY_CODE = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO", "21": "MA", "22": "PI",
    "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL", "28": "SE", "29": "BA", "31": "MG", "32": "ES",
    "33": "RJ", "35": "SP", "41": "PR", "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF",
}  # fmt: skip
UFS = frozenset(UF_BY_CODE.values())
_MMDD = re.compile(r"^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")


def easter(year: int) -> date:
    """Domingo de Páscoa no calendário gregoriano (algoritmo de Meeus/Jones/Butcher)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month = (h + l_ - 7 * m + 114) // 31
    day = ((h + l_ - 7 * m + 114) % 31) + 1
    return date(year, month, day)


@dataclass(frozen=True)
class Holiday:
    """Uma definição de feriado: a regra que dá a data em cada ano."""

    id: str
    nome: str
    tipo: HolidayType
    # "BR", a sigla da UF ou o código do município com 7 dígitos.
    abrangencia: str
    fixo: str | None = None  # "MM-DD"
    pascoa: int | None = None  # dias depois (ou antes) do domingo de Páscoa
    unico: date | None = None  # um dia só (recesso, ponte)
    ajuste: Adjust | None = None
    desde: int | None = None
    ate: int | None = None
    lei: str = ""
    fonte: str = ""
    confirmar: bool = False
    nota: str = ""
    origem: Origin = "programa"

    def on(self, year: int) -> date | None:
        if (self.desde and year < self.desde) or (self.ate and year > self.ate):
            return None
        if self.unico is not None:
            return self.unico if self.unico.year == year else None
        if self.pascoa is not None:
            day = easter(year) + timedelta(days=self.pascoa)
        elif self.fixo:
            month, dd = (int(p) for p in self.fixo.split("-"))
            try:
                day = date(year, month, dd)
            except ValueError:  # 29 de fevereiro fora do ano bissexto
                return None
        else:
            return None
        if self.ajuste == "domingo_seguinte":
            day += timedelta(days=(6 - day.weekday()) % 7)
        return day

    def fingerprint(self) -> str:
        """O que decide a data e o nome: muda quando o programa revisa o feriado."""
        keys = ("nome", "tipo", "abrangencia", "fixo", "pascoa", "unico", "ajuste", "desde", "ate")
        data = {k: _plain(getattr(self, k)) for k in keys}
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]

    def to_json(self) -> dict[str, Any]:
        out = {k: _plain(v) for k, v in self.__dict__.items() if v not in (None, "", False)}
        out["id"], out["nome"], out["tipo"], out["abrangencia"] = (
            self.id,
            self.nome,
            self.tipo,
            self.abrangencia,
        )
        return out

    @classmethod
    def from_json(cls, data: dict[str, Any], origem: Origin = "programa") -> Holiday:
        rule = data.get("regra") or {}
        fixo = rule.get("fixo", data.get("fixo"))
        pascoa = rule.get("pascoa", data.get("pascoa"))
        unico = rule.get("unico", data.get("unico"))
        holiday = cls(
            id=str(data["id"]),
            nome=str(data["nome"]),
            tipo=data["tipo"],
            abrangencia=str(data["abrangencia"]),
            fixo=fixo,
            pascoa=int(pascoa) if pascoa is not None else None,
            unico=date.fromisoformat(unico) if isinstance(unico, str) else unico,
            ajuste=data.get("ajuste"),
            desde=data.get("desde"),
            ate=data.get("ate"),
            lei=data.get("lei", ""),
            fonte=data.get("fonte", ""),
            confirmar=bool(data.get("confirmar", False)),
            nota=data.get("nota", ""),
            origem=data.get("origem", origem),
        )
        holiday.validate()
        return holiday

    def validate(self) -> None:
        rules = [self.fixo is not None, self.pascoa is not None, self.unico is not None]
        if sum(rules) != 1:
            raise ValueError(
                f"O feriado {self.nome!r} precisa de uma regra: data fixa, dias da Páscoa ou data única."
            )
        if self.fixo is not None and not _MMDD.match(self.fixo):
            raise ValueError(f"Data fixa {self.fixo!r} inválida (use MM-DD).")
        if self.pascoa is not None and not -100 <= self.pascoa <= 100:
            raise ValueError("Deslocamento da Páscoa fora do intervalo de 100 dias.")
        if not valid_place(self.abrangencia):
            raise ValueError(
                f"Abrangência {self.abrangencia!r} inválida: BR, sigla da UF ou código do município."
            )


def _plain(value: Any) -> Any:
    return value.isoformat() if isinstance(value, date) else value


def valid_place(place: str) -> bool:
    return place == "BR" or place in UFS or (len(place) == 7 and place.isdigit() and place[:2] in UF_BY_CODE)


# ------------------------------------------------------------------ origens


def _national(id_: str, nome: str, lei: str, **kw: Any) -> Holiday:
    tipo = kw.pop("tipo", "nacional")
    return Holiday(id=f"BR/{id_}", nome=nome, tipo=tipo, abrangencia="BR", lei=lei, origem="calculado", **kw)


NATIONAL: tuple[Holiday, ...] = (
    _national("confraternizacao", "Confraternização Universal", "Lei 662/1949", fixo="01-01"),
    _national("sexta-feira-santa", "Sexta-feira Santa (Paixão de Cristo)", "Lei 9.093/1995", pascoa=-2),
    _national("tiradentes", "Tiradentes", "Lei 662/1949", fixo="04-21"),
    _national("trabalho", "Dia do Trabalho", "Lei 662/1949", fixo="05-01"),
    _national("independencia", "Independência do Brasil", "Lei 662/1949", fixo="09-07"),
    _national("aparecida", "Nossa Senhora Aparecida", "Lei 6.802/1980", fixo="10-12", desde=1980),
    _national("finados", "Finados", "Lei 662/1949", fixo="11-02"),
    _national("republica", "Proclamação da República", "Lei 662/1949", fixo="11-15"),
    _national("consciencia-negra", "Dia Nacional de Zumbi e da Consciência Negra", "Lei 14.759/2023",
              fixo="11-20", desde=2024),
    _national("natal", "Natal", "Lei 662/1949", fixo="12-25"),
    _national("carnaval-segunda", "Carnaval (segunda-feira)", "Portaria anual do Ministério da Gestão",
              pascoa=-48, tipo="ponto_facultativo"),
    _national("carnaval-terca", "Carnaval (terça-feira)", "Portaria anual do Ministério da Gestão",
              pascoa=-47, tipo="ponto_facultativo"),
    _national("cinzas", "Quarta-feira de Cinzas (até as 14h)", "Portaria anual do Ministério da Gestão",
              pascoa=-46, tipo="ponto_facultativo"),
    _national("corpus-christi", "Corpus Christi", "Portaria anual do Ministério da Gestão",
              pascoa=60, tipo="ponto_facultativo"),
)  # fmt: skip

# Sem a planilha da ANBIMA (sem internet, sem leitura guardada), o calendário bancário é calculado: os nacionais,
# Carnaval e Corpus Christi, que é a regra que a ANBIMA segue.
BANK_EXTRA = ("BR/carnaval-segunda", "BR/carnaval-terca", "BR/corpus-christi")


@cache
def _program_file() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(BASE_FILE.read_text(encoding="utf-8"))
    return data


def program_revision() -> str:
    return str(_program_file()["revisado_em"])


def program_holidays() -> tuple[Holiday, ...]:
    return tuple(Holiday.from_json(item) for item in _program_file()["feriados"])


def anbima_holidays(frame: pl.DataFrame) -> tuple[Holiday, ...]:
    """A planilha da ANBIMA (colunas Data, Dia da Semana, Feriado) vira feriados bancários de data única."""
    out: list[Holiday] = []
    first, name = frame.columns[0], frame.columns[-1]
    for row in frame.drop_nulls(first).iter_rows(named=True):
        when = row[first]
        day = when.date() if hasattr(when, "date") else when
        if not isinstance(day, date):
            continue
        out.append(
            Holiday(
                id=f"ANBIMA/{day.isoformat()}",
                nome=str(row[name] or "Feriado bancário"),
                tipo="bancario",
                abrangencia="BR",
                unico=day,
                fonte="ANBIMA",
                origem="anbima",
            )
        )
    return tuple(out)


# ------------------------------------------------------------------ edições da pessoa


@dataclass
class Edits:
    """As edições da pessoa sobre a base (RF-4945): incluir, corrigir e "não vale mais". Nada do programa muda."""

    incluidos: list[Holiday] = field(default_factory=list)
    # id do feriado do programa → (campos corrigidos, impressão do original quando a pessoa corrigiu)
    corrigidos: dict[str, tuple[dict[str, Any], str]] = field(default_factory=dict)
    # id → primeiro ano em que deixou de valer
    nao_vale_mais: dict[str, int] = field(default_factory=dict)

    def include(self, holiday: Holiday) -> None:
        holiday.validate()
        self.incluidos = [h for h in self.incluidos if h.id != holiday.id] + [replace(holiday, origem="meu")]

    def correct(self, original: Holiday, **fields: Any) -> None:
        allowed = {"nome", "tipo", "fixo", "pascoa", "unico", "ajuste", "desde", "ate", "lei", "nota"}
        bad = set(fields) - allowed
        if bad:
            raise ValueError(f"Não dá para corrigir {', '.join(sorted(bad))}.")
        replace(original, **fields).validate()
        self.corrigidos[original.id] = (fields, original.fingerprint())

    def stop(self, holiday_id: str, from_year: int) -> None:
        self.nao_vale_mais[holiday_id] = from_year

    def restore(self, holiday_id: str) -> None:
        """Restaurar o do programa: desfaz correção e "não vale mais"; uma inclusão da pessoa é apagada."""
        self.corrigidos.pop(holiday_id, None)
        self.nao_vale_mais.pop(holiday_id, None)
        self.incluidos = [h for h in self.incluidos if h.id != holiday_id]

    def to_json(self) -> dict[str, Any]:
        return {
            "incluidos": [h.to_json() for h in self.incluidos],
            "corrigidos": {
                k: {"campos": {f: _plain(v) for f, v in c.items()}, "impressao": fp}
                for k, (c, fp) in self.corrigidos.items()
            },
            "nao_vale_mais": dict(self.nao_vale_mais),
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Edits:
        fixed: dict[str, tuple[dict[str, Any], str]] = {}
        for key, item in (data.get("corrigidos") or {}).items():
            fields = dict(item.get("campos") or {})
            if isinstance(fields.get("unico"), str):
                fields["unico"] = date.fromisoformat(fields["unico"])
            fixed[key] = (fields, str(item.get("impressao", "")))
        return cls(
            incluidos=[Holiday.from_json(h, "meu") for h in data.get("incluidos") or []],
            corrigidos=fixed,
            nao_vale_mais={k: int(v) for k, v in (data.get("nao_vale_mais") or {}).items()},
        )


@dataclass(frozen=True)
class Merged:
    holiday: Holiday
    editado: bool = False
    # O programa revisou este feriado depois que a pessoa o corrigiu (RF-4947).
    programa_mudou: bool = False
    original: Holiday | None = None
    deixou_de_valer: int | None = None


def merge(base: Iterable[Holiday], edits: Edits | None) -> list[Merged]:
    edits = edits or Edits()
    out: list[Merged] = []
    for holiday in base:
        current = holiday
        changed = False
        edited = False
        if holiday.id in edits.corrigidos:
            fields, fingerprint = edits.corrigidos[holiday.id]
            current = replace(holiday, **fields)
            edited = True
            changed = fingerprint != holiday.fingerprint()
        stop = edits.nao_vale_mais.get(holiday.id)
        if stop is not None:
            edited = True
            current = replace(current, ate=min(current.ate or stop - 1, stop - 1))
        out.append(Merged(current, edited, changed, holiday if edited else None, stop))
    for mine in edits.incluidos:
        out.append(Merged(mine, editado=True))
    return out


def merge_program_update(old: Iterable[Holiday], new: Iterable[Holiday], edits: Edits) -> list[Holiday]:
    """Feriado novo do programa entra sozinho, salvo se a pessoa já tem um igual (mesma data e abrangência)."""
    old_ids = {h.id for h in old}
    mine = {(h.abrangencia, h.fixo, h.pascoa) for h in edits.incluidos}
    return [h for h in new if h.id in old_ids or (h.abrangencia, h.fixo, h.pascoa) not in mine]


# ------------------------------------------------------------------ tabela e dias úteis


def places_for(place: str) -> set[str]:
    """O que vale num lugar: Brasil, a UF e o município (a UF sai dos dois primeiros dígitos do código)."""
    if not valid_place(place):
        raise ValueError(f"Lugar {place!r} inválido: BR, sigla da UF ou código do município com 7 dígitos.")
    if place == "BR":
        return {"BR"}
    if place in UFS:
        return {"BR", place}
    return {"BR", UF_BY_CODE[place[:2]], place}


def base_for(calendar: Calendar, anbima: Iterable[Holiday] | None = None) -> list[Holiday]:
    if calendar == "bancario":
        bank = list(anbima or ())
        if bank:
            return bank
        return [h for h in NATIONAL if h.tipo == "nacional" or h.id in BANK_EXTRA]
    return [*NATIONAL, *program_holidays()]


def table(
    start: int,
    end: int,
    place: str = "BR",
    *,
    calendar: Calendar = "civil",
    edits: Edits | None = None,
    anbima: Iterable[Holiday] | None = None,
    include_optional: bool = True,
) -> pl.DataFrame:
    """Os feriados de ``start`` a ``end`` (anos) que valem no lugar, já com as edições da pessoa."""
    wanted = places_for(place)
    rows: list[dict[str, Any]] = []
    for item in merge(base_for(calendar, anbima), edits):
        h = item.holiday
        if h.abrangencia not in wanted:
            continue
        if h.tipo == "ponto_facultativo" and not include_optional:
            continue
        for year in range(start, end + 1):
            day = h.on(year)
            if day is None:
                continue
            rows.append(
                {
                    "data": day,
                    "nome": h.nome,
                    "tipo": h.tipo,
                    "abrangencia": h.abrangencia,
                    "lei": h.lei,
                    "origem": "meu" if item.editado else h.origem,
                    "confirmar": h.confirmar,
                    "programa_mudou": item.programa_mudou,
                    "id": h.id,
                }
            )
    schema = {
        "data": pl.Date, "nome": pl.String, "tipo": pl.String, "abrangencia": pl.String, "lei": pl.String,
        "origem": pl.String, "confirmar": pl.Boolean, "programa_mudou": pl.Boolean, "id": pl.String,
    }  # fmt: skip
    return pl.DataFrame(rows, schema=schema).sort(["data", "abrangencia", "nome"])


def business_days(
    start: date,
    end: date,
    place: str = "BR",
    *,
    calendar: Calendar = "civil",
    edits: Edits | None = None,
    anbima: Iterable[Holiday] | None = None,
    optional_is_holiday: bool = True,
) -> pl.DataFrame:
    """Um dia por linha, com ``dia_util`` e o nome do feriado (sábado e domingo não são úteis)."""
    holidays = table(start.year, end.year, place, calendar=calendar, edits=edits, anbima=anbima,
                     include_optional=optional_is_holiday)  # fmt: skip
    names: dict[date, list[str]] = {}
    for day, name in holidays.select("data", "nome").iter_rows():
        names.setdefault(day, []).append(name)
    days = pl.date_range(start, end, "1d", eager=True)
    feriado = [" · ".join(dict.fromkeys(names.get(d, []))) or None for d in days]
    util = [d.weekday() < 5 and not names.get(d) for d in days]
    return pl.DataFrame({"data": days, "dia_util": util, "feriado": feriado},
                        schema={"data": pl.Date, "dia_util": pl.Boolean, "feriado": pl.String})  # fmt: skip


def previous_business_day(day: date, frame: pl.DataFrame) -> date | None:
    """O último dia útil até ``day`` (inclusive), numa tabela de ``business_days`` (usado pela receita da PTAX)."""
    rows = frame.filter((pl.col("data") <= day) & pl.col("dia_util"))
    return rows["data"].max() if rows.height else None  # type: ignore[return-value]
