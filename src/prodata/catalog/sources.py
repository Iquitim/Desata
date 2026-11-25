"""Uma fonte do catálogo, de ponta a ponta: o detalhe para a tela e a leitura (spec 049, RF-4911..4915, RF-4937..4940).

O mesmo despacho serve a prévia do detalhe e a execução da caixa Dados públicos: a prévia lê exatamente como o fluxo
vai ler. As escolhas (``choices``) são as da caixa: período, variável, nível, moeda, consulta e parâmetros do OData,
arquivo de um portal com o formato aceito, local do calendário.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any, cast

import polars as pl

from prodata.catalog import curated, holidays, hosts, portals
from prodata.catalog.http import CatalogClient, CatalogError
from prodata.catalog.model import PeriodChoice, ReadResult, SourceNotFoundError
from prodata.catalog.readers import (
    anbima,
    bcb_olinda,
    bcb_sgs,
    ckan,
    comex,
    files,
    ibge,
    ipea,
    odata,
    siconfi,
    tesouro,
)

PREVIEW_ROWS = 10
_ID = re.compile(r"^[A-Za-z0-9_.\-]+(/[A-Za-z0-9_.\-]+){1,3}$")


KNOWN = frozenset({"bcb.sgs", "bcb.ptax", "bcb.focus", "ibge.agregado", "ibge.localidades", "ipea", "tesouro.direto",
                   "siconfi", "comex", "calendario", "ckan", "receita.cnpj"})  # fmt: skip


def check_id(source_id: str) -> list[str]:
    """O identificador tem um prefixo conhecido e nenhum segmento só de pontos (nada de "../x")."""
    parts = (source_id or "").split("/")
    if (
        not _ID.match(source_id or "")
        or parts[0] not in KNOWN
        or any(set(p) <= {"."} for p in parts)
        or (parts[0] == "ckan" and (len(parts) != 3 or parts[1] not in portals.BY_ID))
    ):
        raise SourceNotFoundError(f"{source_id!r} não é uma fonte do catálogo.")
    return parts


_SERVICE_OF_PREFIX = {
    "bcb.sgs": "bcb_sgs", "bcb.ptax": "bcb_olinda", "bcb.focus": "bcb_olinda", "ibge.agregado": "ibge",
    "ibge.localidades": "ibge", "ipea": "ipea", "tesouro.direto": "tesouro", "siconfi": "siconfi", "comex": "comex",
    "calendario": "anbima", "receita.cnpj": "receita",
}  # fmt: skip


def service_of(source_id: str) -> str:
    """O serviço de onde vêm os dados da fonte (para a situação e o aviso "fora do ar")."""
    parts = check_id(source_id)
    if parts[0] == "ckan":
        return "bcb_olinda" if parts[1] == "bcb_portal" else hosts.PORTAL_SERVICE[parts[1]]
    return _SERVICE_OF_PREFIX[parts[0]]


def _period(choices: dict[str, Any], today: date, first: date | None = None) -> tuple[date, date]:
    return PeriodChoice.model_validate(choices.get("periodo") or {}).resolve(today, first)


def _column(name: str, kind: str, description: str = "") -> dict[str, str]:
    return {"nome": name, "tipo": kind, "descricao": description}


_GENERIC_COLUMNS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "bcb.sgs": (("data", "data", "Dia do valor."), ("valor", "numero", "Valor da série.")),
    "ipea": (("data", "data", "Dia do valor."), ("valor", "numero", "Valor da série.")),
    "ibge.agregado": (("codigo", "texto", "Código da localidade no IBGE."), ("localidade", "texto", "Nome."),
                      ("periodo", "texto", "Período no formato do IBGE."), ("data", "data", "Primeiro dia do período."),
                      ("valor", "numero", "Valor da variável escolhida.")),
}  # fmt: skip


def dictionary(source_id: str, columns: list[str]) -> list[dict[str, str]]:
    """O dicionário das colunas que a leitura entregou (RF-4912), sem rede: o dos destaques ou o genérico do tipo."""
    try:
        parts = check_id(source_id)
    except SourceNotFoundError:
        return []
    source = curated.get(source_id)
    known = (
        {c.name: (c.type, c.description) for c in source.colunas}
        if source is not None
        else {n: (t, d) for n, t, d in _GENERIC_COLUMNS.get(parts[0], ())}
    )
    return [_column(name, *known[name]) for name in columns if name in known and known[name][1]]


def _service(service_id: str) -> dict[str, Any]:
    s = hosts.SERVICES[service_id]
    return {"servico": service_id, "orgao": s.agency, "pagina": s.page}


# ------------------------------------------------------------------ detalhe


def describe(client: CatalogClient, source_id: str, today: date | None = None) -> dict[str, Any]:
    """O máximo que se sabe da fonte (RF-4911): o que não muda vem do programa; o que muda vem do órgão, na hora.

    Uma falha ao conferir com o órgão não impede o detalhe: ele sai com o que o programa sabe e o aviso do motivo.
    """
    parts = check_id(source_id)
    day = today or date.today()
    source = curated.get(source_id)
    out: dict[str, Any] = _static(source_id, source)
    try:
        _live(client, parts, source, out, day)
    except (CatalogError, SourceNotFoundError) as exc:
        if isinstance(exc, SourceNotFoundError) and not source:
            raise
        message = exc.message if isinstance(exc, CatalogError) else str(exc)
        out["avisos"].append(f"Não foi possível conferir com o órgão agora: {message}")
    return out


def _static(source_id: str, source: curated.Source | None) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": source_id,
        "destaque": source is not None,
        "leitura": "pronta" if source else "automatica",
        "avisos": [],
        "escolhas": [],
        "colunas": [],
        "periodo": None,
        "atualizado": None,
        "atualizado_rotulo": "atualizada em",
        "urls_exemplo": [],
    }
    if source is None:
        return base
    base.update(
        nome=source.nome,
        resumo=source.resumo,
        descricao="",
        categoria=source.categoria,
        periodicidade=source.periodicidade,
        granularidade=source.granularidade,
        unidade=source.unidade,
        licenca=source.licenca,
        citacao=source.citacao,
        colunas=[_column(c.name, c.type, c.description) for c in source.colunas],
        **_service(source.servico),
    )
    base["escolhas"] = _choices_for(source)
    return base


def _choices_for(source: curated.Source) -> list[dict[str, Any]]:
    """Os campos que a caixa oferece (RF-4914), já com os valores prontos."""
    out: list[dict[str, Any]] = []
    e = source.escolhas
    if "periodo" in e:
        out.append({"id": "periodo", "rotulo": "Período", "tipo": "periodo", "padrao": e["periodo"]})
    if isinstance(e.get("variavel"), dict):
        options = [{"valor": v, "rotulo": k} for k, v in e["variavel"].items()]
        out.append(
            {
                "id": "variavel",
                "rotulo": "Variável",
                "tipo": "opcoes",
                "opcoes": options,
                "padrao": options[0]["valor"],
            }
        )
    if "nivel" in e:
        names = {"N1": "Brasil", "N2": "Grandes regiões", "N3": "Estados", "N6": "Municípios"}
        options = [{"valor": n, "rotulo": names[n]} for n in e["nivel"]]
        out.append(
            {
                "id": "nivel",
                "rotulo": "Localidade",
                "tipo": "opcoes",
                "opcoes": options,
                "padrao": source.params.get("nivel", "N1"),
            }
        )
    if "moeda" in e:
        out.append(
            {"id": "moeda", "rotulo": "Moeda", "tipo": "texto", "padrao": e["moeda"], "lista": "moedas"}
        )
    for key, label in (("indicador", "Indicador"), ("periodicidade", "Periodicidade da previsão"), ("relatorio", "Relatório"),
                       ("calendario", "Calendário")):  # fmt: skip
        if isinstance(e.get(key), list):
            options = [{"valor": v, "rotulo": v} for v in e[key]]
            out.append({"id": key, "rotulo": label, "tipo": "opcoes", "opcoes": options, "padrao": e[key][0]})
    if "detalhes" in e:
        names = {"country": "País", "state": "UF", "ncm": "Produto (NCM)", "chapter": "Capítulo do produto"}
        options = [{"valor": v, "rotulo": names.get(v, v)} for v in e["detalhes"]]
        out.append(
            {
                "id": "detalhes",
                "rotulo": "Detalhar por",
                "tipo": "varios",
                "opcoes": options,
                "padrao": ["country"],
            }
        )
    if "local" in e:
        out.append({"id": "local", "rotulo": "Local", "tipo": "local", "padrao": "BR"})
    if source.kind == "siconfi":
        out += [
            {"id": "exercicio", "rotulo": "Ano", "tipo": "numero", "padrao": date.today().year - 1},
            {
                "id": "ente",
                "rotulo": "Código do IBGE do estado ou município",
                "tipo": "texto",
                "padrao": "3550308",
            },
        ]
    return out


def _live(
    client: CatalogClient, parts: list[str], source: curated.Source | None, out: dict[str, Any], day: date
) -> None:
    head = parts[0]
    if head == "bcb.sgs":
        _live_sgs(client, int(parts[1]), out, source)
    elif head == "ibge.agregado":
        _live_ibge(client, int(parts[1]), out, source)
    elif head == "ipea":
        _live_ipea(client, parts[1], out)
    elif head == "tesouro.direto":
        info = tesouro.meta(client)
        out["atualizado"], out["descricao"] = info["atualizado"], info["descricao"]
    elif head == "comex":
        info = comex.updated(client)
        out["atualizado"], out["periodo"] = (
            info["atualizado"],
            {"inicio": "1997-01", "fim": info["ultimo_mes"]},
        )
    elif head == "bcb.focus":
        out["atualizado_rotulo"] = "última pesquisa em"
    elif head == "calendario":
        out["atualizado"] = holidays.program_revision()
        out["atualizado_rotulo"] = "tabela de estados e capitais revisada em"
        out["periodo"] = {"inicio": "2001-01-01", "fim": "2099-12-31"}
    elif head == "ckan":
        _live_ckan(client, parts[1], parts[2], out)
    elif head == "ibge.localidades":
        out["atualizado_rotulo"] = ""


def _live_sgs(client: CatalogClient, code: int, out: dict[str, Any], source: curated.Source | None) -> None:
    last, _value = bcb_sgs.last_value(client, code)
    out["atualizado"], out["atualizado_rotulo"] = last.isoformat(), "último dado em"
    out["urls_exemplo"] = [f"{bcb_sgs.DATA_URL.format(code=code)}?formato=json&dataInicial=...&dataFinal=..."]
    if source is not None:
        return
    out.update(
        nome=f"Série {code} do SGS", resumo="", leitura="automatica", **_service("bcb_sgs"),
        licenca=curated.LICENSES["bcb"], citacao=f"Banco Central do Brasil, SGS {code}",
        colunas=[_column("data", "data", "Dia do valor."), _column("valor", "numero", "Valor da série.")],
        escolhas=[{"id": "periodo", "rotulo": "Período", "tipo": "periodo", "padrao": {"kind": "ultimos_anos", "anos": 5}}],
    )  # fmt: skip
    try:
        info = bcb_sgs.meta(client, code)
    except SourceNotFoundError:
        out["avisos"].append(
            "Esta série não está no catálogo do portal do Banco Central: lida direto pelo código."
        )
        return
    out.update(nome=info["nome"], descricao=info["descricao"], periodicidade=info["periodicidade"].lower(),
               unidade=info["unidade"], periodo={"inicio": info["inicio"], "fim": info["fim"] or None})  # fmt: skip


def _live_ibge(client: CatalogClient, table: int, out: dict[str, Any], source: curated.Source | None) -> None:
    meta = ibge.meta(client, table)
    per = meta.get("periodicidade", {})
    out["periodo"] = {"inicio": str(per.get("inicio", "")), "fim": str(per.get("fim", ""))}
    periods = ibge.periods(client, table)
    if periods:
        out["atualizado"] = _br_date(periods[-1].get("modificacao", ""))
        out["atualizado_rotulo"] = f"último período ({periods[-1].get('literals', [''])[0]}) publicado em"
    out["urls_exemplo"] = [
        f"{ibge.AGREGADOS}/{table}/periodos/-12/variaveis/{{variável}}?localidades=N1[all]"
    ]
    if source is not None:
        return
    levels = [n for n in meta.get("nivelTerritorial", {}).get("Administrativo", []) if n in ibge.LEVELS]
    variables = [
        {"valor": v["id"], "rotulo": f"{v['nome']} ({v.get('unidade', '')})"}
        for v in meta.get("variaveis", [])
    ]
    out.update(
        nome=meta.get("nome", f"Tabela {table}"), resumo=meta.get("pesquisa", ""), leitura="automatica",
        periodicidade=per.get("frequencia", ""), **_service("ibge"), licenca=curated.LICENSES["ibge"],
        citacao=f"IBGE, tabela {table} — {meta.get('nome', '')[:80]}",
        colunas=[_column("codigo", "texto", "Código da localidade no IBGE."), _column("localidade", "texto", "Nome."),
                 _column("periodo", "texto", "Período no formato do IBGE."), _column("data", "data", "Primeiro dia do período."),
                 _column("valor", "numero", "Valor da variável escolhida.")],
        escolhas=[
            {"id": "periodo", "rotulo": "Período", "tipo": "periodo", "padrao": {"kind": "ultimos_anos", "anos": 5}},
            {"id": "variavel", "rotulo": "Variável", "tipo": "opcoes", "opcoes": variables,
             "padrao": variables[0]["valor"] if variables else None},
            {"id": "nivel", "rotulo": "Localidade", "tipo": "opcoes",
             "opcoes": [{"valor": n, "rotulo": ibge.LEVELS[n]} for n in levels], "padrao": levels[0] if levels else "N1"},
        ],
    )  # fmt: skip


def _br_date(text: str) -> str | None:
    match = re.match(r"(\d{2})/(\d{2})/(\d{4})", text or "")
    return f"{match.group(3)}-{match.group(2)}-{match.group(1)}" if match else None


def _live_ipea(client: CatalogClient, code: str, out: dict[str, Any]) -> None:
    info = ipea.meta(client, code)
    out.update(
        nome=info["nome"], resumo=info["fonte"], descricao=info["descricao"], periodicidade=info["periodicidade"].lower(),
        unidade=" ".join(p for p in (info["multiplicador"], info["unidade"]) if p), atualizado=info["atualizado"],
        leitura="automatica", **_service("ipea"), licenca=curated.LICENSES["ipea"],
        citacao=f"Ipeadata ({info['fonte_sigla'] or info['fonte']}), série {code}",
        colunas=[_column("data", "data", "Dia do valor."), _column("valor", "numero", f"Valor ({info['unidade']}).")],
        escolhas=[{"id": "periodo", "rotulo": "Período", "tipo": "periodo", "padrao": {"kind": "tudo"}}],
    )  # fmt: skip
    if not info["ativa"]:
        out["avisos"].append("O Ipeadata marca esta série como inativa: ela não recebe dados novos.")


def _live_ckan(client: CatalogClient, portal_id: str, name: str, out: dict[str, Any]) -> None:
    detail = ckan.dataset(client, portal_id, name)
    site = portals.BY_ID[portal_id]
    out.update(
        nome=detail["nome"], resumo=detail["resumo"], descricao=detail["descricao"], atualizado=detail["atualizado"],
        licenca=detail["licenca"] or "Conforme o portal", citacao=f"{site.orgao}, {detail['nome']}",
        orgao=site.orgao, servico=hosts.PORTAL_SERVICE[portal_id], pagina=detail["pagina"], arquivos=detail["arquivos"],
        grupo=detail["grupo"], temas=detail["temas"],
    )  # fmt: skip
    out["escolhas"] = [{"id": "arquivo", "rotulo": "Arquivo", "tipo": "arquivo"}]
    if not any(a["situacao"] != "so_link" for a in detail["arquivos"]):
        out["avisos"].append("Nenhum arquivo deste conjunto é lido pelo programa: abra no navegador.")


def odata_entries(client: CatalogClient, resource_url: str) -> dict[str, Any]:
    """As consultas do serviço OData de um recurso do portal do Banco Central, com os parâmetros conferidos."""
    parsed = odata.parse_resource_url(resource_url)
    if parsed is None:
        raise SourceNotFoundError("Este arquivo não é um serviço OData do Banco Central.")
    servico, versao, consulta, extra = parsed
    service = odata.describe(client, servico, versao)
    entries = [
        {
            "nome": e.nome, "titulo": e.titulo, "descricao": e.descricao, "conferida": e.conferida,
            "colunas": [{"nome": n, "tipo": t.removeprefix("Edm.")} for n, t in e.colunas],
            "parametros": [{"nome": p.nome, "tipo": p.tipo, "descricao": p.descricao, "conferido": p.conferido,
                            "papel": p.papel, "opcoes": p.opcoes, "exemplo": p.exemplo} for p in e.parametros],
        }
        for e in service.entradas
    ]  # fmt: skip
    return {"servico": servico, "versao": versao, "consulta": consulta, "filtro": extra, "titulo": service.titulo,
            "descricao": service.descricao, "consultas": entries,
            "documentacao": f"{service.url}/aplicacao#!/recursos"}  # fmt: skip


# ------------------------------------------------------------------ leitura


def read(
    client: CatalogClient,
    source_id: str,
    choices: dict[str, Any],
    root: Path,
    today: date | None = None,
    *,
    team_holidays: holidays.Edits | None = None,
) -> ReadResult:
    """Lê a fonte com as escolhas da caixa. A prévia usa a mesma função (com período curto)."""
    parts = check_id(source_id)
    day = today or date.today()
    source = curated.get(source_id)
    params = {
        **(source.params if source else {}),
        **{k: v for k, v in choices.items() if v not in (None, "")},
    }
    head = parts[0]
    if head == "bcb.sgs":
        start, end = _period(choices, day)
        result = bcb_sgs.read_series(client, int(parts[1]), start, end)
        if int(parts[1]) == 432 and not choices.get("incluir_futuro"):
            result.frame = result.frame.filter(
                pl.col("data") <= day
            )  # a meta vale até a próxima reunião do Copom
        return result
    if head == "bcb.ptax":
        start, end = _period(choices, day)
        return bcb_olinda.read_ptax(client, str(params.get("moeda", "USD")), start, end)
    if head == "bcb.focus":
        start, _end = _period(choices, day)
        return bcb_olinda.read_focus(client, str(params.get("indicador", "IPCA")), start,
                                     periodicidade=str(params.get("periodicidade", "mensal")))  # fmt: skip
    if head == "ibge.agregado":
        return _read_ibge(client, int(parts[1]), params, choices, day)
    if head == "ibge.localidades":
        return {"regioes": ibge.regions, "estados": ibge.states, "municipios": ibge.municipalities}[parts[1]](
            client
        )
    if head == "ipea":
        start, end = _period(choices, day, date(1900, 1, 1))
        return ipea.read_series(client, parts[1], start if choices.get("periodo") else None, end)
    if head == "tesouro.direto":
        start, end = _period(choices, day)
        return tesouro.read_direto(client, start, end)
    if head == "siconfi":
        report = str(params.get("relatorio", "dca"))
        if report not in ("dca", "rreo", "rgf"):
            raise SourceNotFoundError(f"Relatório {report!r} não existe no Siconfi.")
        year = int(params.get("exercicio") or day.year - 1)
        return siconfi.read_report(client, cast(siconfi.Report, report), year, str(params.get("ente", "")))
    if head == "comex":
        start, end = _period(choices, day)
        details = choices.get("detalhes") or ["country"]
        metrics = ["metricFOB", "metricKG"] + (["metricCIF"] if params.get("fluxo") == "import" else [])
        return comex.read_general(client, params.get("fluxo", "export"), f"{start:%Y-%m}", f"{end:%Y-%m}",
                                  details=list(details), metrics=metrics)  # fmt: skip
    if head == "calendario":
        return _read_calendar(client, parts[1], params, choices, day, root, team_holidays)
    if head == "ckan":
        return _read_portal(client, parts[1], parts[2], choices, root, day)
    if head == "receita.cnpj":
        raise SourceNotFoundError("O CNPJ vem em arquivos grandes: use Baixar… para escolher a pasta.")
    raise SourceNotFoundError(f"{source_id} não é uma fonte do catálogo.")


def _read_ibge(
    client: CatalogClient, table: int, params: dict[str, Any], choices: dict[str, Any], day: date
) -> ReadResult:
    meta = ibge.meta(client, table)
    freq = meta.get("periodicidade", {}).get("frequencia", "")
    start, end = _period(choices, day)
    span = f"{start:%Y%m}-{end:%Y%m}" if freq != "anual" else f"{start:%Y}-{end:%Y}"
    if freq.startswith("trimestral") and "móvel" not in freq:
        span = f"{start.year}0{(start.month - 1) // 3 + 1}-{end.year}0{(end.month - 1) // 3 + 1}"
    if choices.get("ultimos_periodos"):  # a prévia: os últimos períodos publicados, seja qual for a data
        span = f"-{int(choices['ultimos_periodos'])}"
    variable = int(params.get("variavel") or meta["variaveis"][0]["id"])
    return ibge.read_table(
        client, table, variable, period=span, level=str(params.get("nivel", "N1")), frequency=freq
    )


def _read_calendar(
    client: CatalogClient,
    kind: str,
    params: dict[str, Any],
    choices: dict[str, Any],
    day: date,
    root: Path,
    team_holidays: holidays.Edits | None = None,
) -> ReadResult:
    period = PeriodChoice.model_validate(choices.get("periodo") or {"kind": "intervalo", "inicio": date(day.year, 1, 1),
                                                                     "fim": date(day.year, 12, 31)})  # fmt: skip
    start, end = period.resolve(day)
    calendar: holidays.Calendar = "bancario" if params.get("calendario") == "bancario" else "civil"
    place = str(params.get("local") or "BR")
    # As edições da pessoa valem nos feriados e nos dias úteis; num fluxo do espaço, as da equipe (RF-4948).
    edits = team_holidays if team_holidays is not None else holidays.load_edits(root)
    bank: tuple[holidays.Holiday, ...] = ()
    warnings: list[str] = []
    if calendar == "bancario":
        try:
            bank = holidays.anbima_holidays(anbima.read(client).frame)
        except CatalogError as exc:
            warnings.append(
                f"ANBIMA indisponível ({exc.message}): feriados bancários calculados pelo programa."
            )
    if kind == "feriados":
        frame = holidays.table(start.year, end.year, place, calendar=calendar, anbima=bank, edits=edits)
        frame = frame.filter((pl.col("data") >= start) & (pl.col("data") <= end))
    else:
        frame = holidays.business_days(start, end, place, calendar=calendar, anbima=bank, edits=edits)
    return ReadResult(frame, [], warnings)


def _read_portal(client: CatalogClient, portal_id: str, name: str, choices: dict[str, Any], root: Path,
                 day: date) -> ReadResult:  # fmt: skip
    detail = ckan.dataset(client, portal_id, name)
    wanted = str(choices.get("arquivo") or "")
    resource = next((a for a in detail["arquivos"] if a["id"] == wanted), None)
    if resource is None:
        raise SourceNotFoundError("Escolha um arquivo do conjunto (o portal pode ter trocado o arquivo).")
    if resource["situacao"] == "so_link":
        raise SourceNotFoundError(f"Este arquivo só abre no navegador: {resource['motivo']}.")
    if resource["situacao"] == "grande":
        raise SourceNotFoundError("Arquivo acima de 200 MB: use Baixar… para escolher a pasta.")
    if resource["situacao"] == "odata":
        parsed = odata.parse_resource_url(resource["url"])
        assert parsed is not None
        servico, versao, consulta, extra = parsed
        service = odata.describe(client, servico, versao)
        entry_name = str(choices.get("consulta") or consulta)
        entry = service.entry(entry_name)
        start, end = _period(choices, day)
        values = odata.param_values(entry, start, end, dict(choices.get("parametros") or {}))
        return odata.read(
            client, service, entry_name, values, extra=extra if entry_name == consulta else None
        )
    accepted = files.AcceptedFormat.model_validate(choices.get("formato_aceito") or {})
    return files.read(client, resource["url"], root, resource["formato"], accepted)


def preview(client: CatalogClient, source_id: str, choices: dict[str, Any], root: Path,
            today: date | None = None) -> dict[str, Any]:  # fmt: skip
    """As últimas linhas, lidas na hora com as escolhas (RF-4913). Série temporal: período curto, para ser rápido."""
    day = today or date.today()
    quick = dict(choices)
    head = check_id(source_id)[0]
    # A janela da prévia termina no último dado que a fonte tem (série encerrada, tabela anual com atraso).
    end = day
    if head == "bcb.sgs":
        end = bcb_sgs.last_value(client, int(source_id.split("/")[1]))[0]
    if head == "ibge.agregado":
        quick["ultimos_periodos"] = 6
    elif (
        head in ("bcb.sgs", "bcb.ptax", "bcb.focus", "tesouro.direto", "comex", "ckan")
        or "periodo" not in quick
    ):
        quick["periodo"] = {
            "kind": "intervalo",
            "inicio": (end - timedelta(days=400)).isoformat(),
            "fim": end.isoformat(),
        }
    result = read(client, source_id, quick, root, day)
    frame = result.frame
    tail = frame.tail(PREVIEW_ROWS) if "data" in frame.columns else frame.head(PREVIEW_ROWS)
    from prodata.engine.profiling import schema_of
    from prodata.engine.serialize import json_rows

    return {"colunas": schema_of(tail), "linhas": json_rows(tail), "linhas_lidas": frame.height,
            "avisos": result.warnings, "urls": result.urls[:5]}  # fmt: skip
