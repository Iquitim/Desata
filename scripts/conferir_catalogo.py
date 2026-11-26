"""Conferência de verdade dos endereços do catálogo de dados públicos (spec 049, T01).

    uv run python scripts/conferir_catalogo.py              # confere todos e mostra o tempo de cada um
    uv run python scripts/conferir_catalogo.py --gravar     # também grava as respostas reduzidas dos testes
    uv run python scripts/conferir_catalogo.py ibge ipea    # só os serviços citados

Acessa a internet: é manual, fora do CI. Os testes usam as respostas gravadas em tests/fixtures/catalogo/, sem rede.
Cada resposta é reduzida antes de gravar (poucas linhas, os itens que os testes usam), para o repositório não
carregar megabytes de catálogo.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "catalogo"

CNPJ_DAV = "https://arquivos.receitafederal.gov.br/public.php/webdav"
CNPJ_LINK = "gn672Ad4CF8N6TK"  # link público de compartilhamento da Receita (não é credencial)
CNPJ_ROOT = "/Dados/Cadastros/CNPJ"
PROPFIND = (
    '<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:getcontentlength/><d:getlastmodified/>'
    "<d:resourcetype/></d:prop></d:propfind>"
)

Reducer = Callable[[httpx.Response], bytes]


@dataclass
class Check:
    service: str
    name: str
    url: str
    check: Callable[[httpx.Response], str]
    reduce: Reducer | None = None
    suffix: str = ".json"
    method: str = "GET"
    params: dict[str, Any] = field(default_factory=dict)
    auth: tuple[str, str] | None = None
    headers: dict[str, str] = field(default_factory=dict)
    content: str | None = None
    json: Any = None


def _json(data: Any) -> bytes:
    return json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8")


def _first(n: int) -> Reducer:
    def reduce(r: httpx.Response) -> bytes:
        data = r.json()
        if isinstance(data, list):
            return _json(data[:n])
        if isinstance(data, dict) and isinstance(data.get("value"), list):
            return _json({**data, "value": data["value"][:n]})
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            return _json({**data, "items": data["items"][:n]})
        return _json(data)

    return reduce


def _whole(r: httpx.Response) -> bytes:
    return r.content


def _ibge_catalog(r: httpx.Response) -> bytes:
    keep = {"1737", "6579", "4099", "5938"}
    out: list[dict[str, Any]] = []
    for survey in r.json():
        chosen = [a for a in survey["agregados"] if a["id"] in keep]
        if chosen or len(out) < 2:
            out.append({**survey, "agregados": chosen or survey["agregados"][:3]})
    return _json(out)


def _ipea_catalog(r: httpx.Response) -> bytes:
    data = r.json()
    keep = {"BM12_TJOVER12", "PRECOS12_IPCA12", "GAC12_SALMINRE12"}
    rows = [x for x in data["value"] if x["SERCODIGO"] in keep] + data["value"][:5]
    return _json({**data, "value": rows})


def _municipios(r: httpx.Response) -> bytes:
    keep = {
        "Campinas",
        "São Paulo",
        "Alta Floresta D'Oeste",
        "Rio de Janeiro",
        "Santa Bárbara d'Oeste",
        "Brasília",
    }
    return _json([m for m in r.json() if m["nome"] in keep])


def _bcb_search(r: httpx.Response) -> bytes:
    data = r.json()
    rows = [
        {
            k: p.get(k)
            for k in (
                "name",
                "title",
                "notes",
                "codigo_sgs",
                "periodicidade",
                "unidade_medida",
                "inicio_periodo",
                "fim_periodo",
                "metadata_modified",
                "license_title",
                "url",
            )
        }
        | {"organization": {"title": (p.get("organization") or {}).get("title")}}
        for p in data["result"]["results"]
    ]
    return _json({"success": data["success"], "result": {"count": data["result"]["count"], "results": rows}})


def _tesouro(r: httpx.Response) -> bytes:
    data = r.json()["result"]
    keep = ("name", "title", "notes", "metadata_modified", "license_title")
    res = [
        {k: x.get(k) for k in ("name", "url", "last_modified", "size", "format")} for x in data["resources"]
    ]
    return _json({"success": True, "result": {k: data.get(k) for k in keep} | {"resources": res}})


def _tesouro_csv(r: httpx.Response) -> bytes:
    lines = r.content.decode("latin-1").splitlines()
    return ("\n".join(lines[:40]) + "\n").encode("latin-1")


def _dav(r: httpx.Response) -> bytes:
    # Mantém o cabeçalho e as primeiras entradas da listagem WebDAV.
    text = r.text
    parts = re.split(r"(?=<d:response>)", text)
    head, items = parts[0], parts[1:]
    small = [*items[:12], *items[-3:]] if len(items) > 15 else items
    tail = "" if small and small[-1].rstrip().endswith("</d:multistatus>") else "</d:multistatus>"
    return (head + "".join(small) + tail).encode("utf-8")


def _ok_list(r: httpx.Response) -> str:
    data = r.json()
    rows = (
        data if isinstance(data, list) else data.get("value") or data.get("items") or data.get("data") or []
    )
    if not rows:
        raise ValueError("resposta sem linhas")
    return f"{len(rows)} linhas"


def _ok_ckan(r: httpx.Response) -> str:
    data = r.json()
    if not data.get("success"):
        raise ValueError("success=false")
    res = data["result"]
    return f"{res['count']} conjuntos" if "count" in res else str(res.get("title"))


def _ok_meta(r: httpx.Response) -> str:
    data = r.json()
    per = data.get("periodicidade", {})
    return f"{data['nome'][:50]}… {per.get('frequencia')} {per.get('inicio')}–{per.get('fim')}"


def _ok_sgs_sem_periodo(r: httpx.Response) -> str:
    if r.status_code != 406 or "10 anos" not in r.text:
        raise ValueError(f"esperado 406 com a regra dos 10 anos, veio {r.status_code}")
    return "406 com a regra dos 10 anos (como esperado)"


def _ok_dav(r: httpx.Response) -> str:
    if r.status_code != 207:
        raise ValueError(f"esperado 207, veio {r.status_code}")
    months = sorted(set(re.findall(r"/(\d{4}-\d{2})/</d:href>", r.text)))
    files = re.findall(r"/([^/<]+\.zip)</d:href>", r.text)
    sizes = [int(s) for s in re.findall(r"<d:getcontentlength>(\d+)", r.text)]
    if files:
        return f"{len(files)} ZIPs, {sum(sizes) / 1e9:.2f} GB"
    if not months:
        raise ValueError("listagem sem meses nem arquivos")
    return f"meses {months[0]} a {months[-1]}"


def _ok_range(r: httpx.Response) -> str:
    if r.status_code != 206 or not r.headers.get("content-range"):
        raise ValueError(f"sem Range: {r.status_code}")
    return f"206 {r.headers['content-range']}"


def _ok_xls(r: httpx.Response) -> str:
    import fastexcel

    frame = fastexcel.read_excel(r.content).load_sheet(0).to_polars().drop_nulls()
    return f"{frame.height} feriados, {frame[0, 0]:%Y} a {frame[-1, 0]:%Y}"


def _ok_csv(r: httpx.Response) -> str:
    lines = r.content.decode("latin-1").splitlines()
    return f"{len(lines)} linhas; cabeçalho: {lines[0][:80]}"


def _ok_comex(r: httpx.Response) -> str:
    data = r.json()["data"]
    return f"atualizado em {data['updated']} (mês {data['year']}-{data['monthNumber']})"


def _ok_comex_list(r: httpx.Response) -> str:
    rows = r.json()["data"]["list"]
    if not rows:
        raise ValueError("consulta sem linhas")
    return f"{len(rows)} linhas"


def _comex_small(r: httpx.Response) -> bytes:
    data = r.json()
    return _json({**data, "data": {"list": data["data"]["list"][:20]}})


def _ok_any_json(r: httpx.Response) -> str:
    r.json()
    return "JSON válido"


def checks(month: str) -> list[Check]:
    hoje = time.strftime("%d/%m/%Y")
    mes_atras = time.strftime("%d/%m/%Y", time.localtime(time.time() - 30 * 86400))
    sgs = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{}/dados"
    olinda = "https://olinda.bcb.gov.br/olinda/servico"
    ibge = "https://servicodados.ibge.gov.br/api"
    ipea = "https://www.ipeadata.gov.br/api/odata4"
    dav: dict[str, Any] = {
        "auth": (CNPJ_LINK, ""),
        "headers": {"Depth": "1"},
        "content": PROPFIND,
        "method": "PROPFIND",
    }
    bcb_q = "https://dadosabertos.bcb.gov.br/api/3/action/package_search"
    return [
        Check(
            "bcb",
            "sgs_432",
            sgs.format(432),
            _ok_list,
            _first(30),
            params={"formato": "json", "dataInicial": mes_atras, "dataFinal": hoje},
        ),
        Check(
            "bcb",
            "sgs_11",
            sgs.format(11),
            _ok_list,
            _first(30),
            params={"formato": "json", "dataInicial": mes_atras, "dataFinal": hoje},
        ),
        Check(
            "bcb",
            "sgs_433",
            sgs.format(433),
            _ok_list,
            _first(30),
            params={"formato": "json", "dataInicial": "01/01/2025", "dataFinal": hoje},
        ),
        Check(
            "bcb", "sgs_sem_periodo", sgs.format(11), _ok_sgs_sem_periodo, _whole, params={"formato": "json"}
        ),
        Check("bcb", "bcb_catalogo", bcb_q, _ok_ckan, _bcb_search, params={"q": "codigo_sgs:432", "rows": 1}),
        Check(
            "bcb",
            "bcb_catalogo_pagina",
            bcb_q,
            _ok_ckan,
            _bcb_search,
            params={"fq": "codigo_sgs:[* TO *]", "rows": 5, "start": 0},
        ),
        Check(
            "olinda",
            "ptax_moedas",
            f"{olinda}/PTAX/versao/v1/odata/Moedas",
            _ok_list,
            _first(20),
            params={"$format": "json"},
        ),
        Check(
            "olinda",
            "ptax_usd",
            f"{olinda}/PTAX/versao/v1/odata/CotacaoMoedaPeriodo(moeda=@moeda,dataInicial=@dataInicial,"
            "dataFinalCotacao=@dataFinalCotacao)",
            _ok_list,
            _first(30),
            params={
                "@moeda": "'USD'",
                "@dataInicial": "'11-01-2026'",
                "@dataFinalCotacao": "'11-21-2026'",
                "$format": "json",
            },
        ),
        # O Olinda recusa o espaço escrito como "+" (é o que o httpx manda nos params): vai %20 na própria URL.
        Check(
            "olinda",
            "focus_mensal",
            f"{olinda}/Expectativas/versao/v1/odata/ExpectativaMercadoMensais?$top=10&$format=json"
            "&$orderby=Data%20desc",
            _ok_list,
            _first(10),
        ),
        Check("ibge", "ibge_catalogo", f"{ibge}/v3/agregados", _ok_list, _ibge_catalog),
        Check("ibge", "ibge_1737_meta", f"{ibge}/v3/agregados/1737/metadados", _ok_meta, _whole),
        Check("ibge", "ibge_1737_periodos", f"{ibge}/v3/agregados/1737/periodos", _ok_list, _first(24)),
        Check(
            "ibge",
            "ibge_1737_dados",
            f"{ibge}/v3/agregados/1737/periodos/-12/variaveis/2266",
            _ok_list,
            _whole,
            params={"localidades": "N1[all]"},
        ),
        Check("ibge", "ibge_6579_meta", f"{ibge}/v3/agregados/6579/metadados", _ok_meta, _whole),
        Check(
            "ibge",
            "ibge_6579_uf",
            f"{ibge}/v3/agregados/6579/periodos/-1/variaveis/9324",
            _ok_list,
            _whole,
            params={"localidades": "N3[all]"},
        ),
        Check("ibge", "ibge_4099_meta", f"{ibge}/v3/agregados/4099/metadados", _ok_meta, _whole),
        Check("ibge", "ibge_5938_meta", f"{ibge}/v3/agregados/5938/metadados", _ok_meta, _whole),
        Check("ibge", "ibge_regioes", f"{ibge}/v1/localidades/regioes", _ok_list, _whole),
        Check("ibge", "ibge_estados", f"{ibge}/v1/localidades/estados", _ok_list, _whole),
        Check("ibge", "ibge_municipios", f"{ibge}/v1/localidades/municipios", _ok_list, _municipios),
        Check("ipea", "ipea_catalogo", f"{ipea}/Metadados", _ok_list, _ipea_catalog),
        Check(
            "ipea", "ipea_valores", f"{ipea}/ValoresSerie(SERCODIGO='BM12_TJOVER12')", _ok_list, _first(24)
        ),
        Check(
            "tesouro",
            "tesouro_direto",
            "https://www.tesourotransparente.gov.br/ckan/api/3/action/package_show",
            _ok_ckan,
            _tesouro,
            params={"id": "taxas-dos-titulos-ofertados-pelo-tesouro-direto"},
        ),
        Check(
            "tesouro",
            "tesouro_direto_csv",
            "https://www.tesourotransparente.gov.br/ckan/dataset/df56aa42-484a-4a59-8184-7676580c81e3/resource/"
            "796d2059-14e9-44e3-80c9-2d9e30b405c1/download/precotaxatesourodireto.csv",
            _ok_csv,
            _tesouro_csv,
            suffix=".csv",
        ),
        Check(
            "siconfi",
            "siconfi_entes",
            "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/entes",
            _ok_list,
            _first(10),
        ),
        Check(
            "comex",
            "comex_atualizado",
            "https://api-comexstat.mdic.gov.br/general/dates/updated",
            _ok_comex,
            _whole,
        ),
        Check("receita", "cnpj_meses", f"{CNPJ_DAV}{CNPJ_ROOT}/", _ok_dav, _dav, suffix=".xml", **dav),
        Check("receita", "cnpj_mes", f"{CNPJ_DAV}{CNPJ_ROOT}/{month}/", _ok_dav, _dav, suffix=".xml", **dav),
        Check(
            "receita",
            "cnpj_range",
            f"{CNPJ_DAV}{CNPJ_ROOT}/{month}/Cnaes.zip",
            _ok_range,
            auth=(CNPJ_LINK, ""),
            headers={"Range": "bytes=0-99", "Accept-Encoding": "identity"},
        ),
        Check(
            "anbima",
            "anbima_feriados",
            "https://www.anbima.com.br/feriados/arqs/feriados_nacionais.xls",
            _ok_xls,
            _whole,
            suffix=".xls",
        ),
        Check(
            "ipea",
            "ipea_meta",
            "https://www.ipeadata.gov.br/api/odata4/Metadados('BM12_TJOVER12')",
            _ok_list,
            _whole,
        ),
        Check(
            "siconfi",
            "siconfi_dca",
            "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/dca",
            _ok_list,
            _first(25),
            params={"an_exercicio": 2024, "id_ente": 3550308, "no_anexo": "DCA-Anexo I-C"},
        ),
        Check(
            "siconfi",
            "siconfi_rreo",
            "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/rreo",
            _ok_list,
            _first(25),
            params={
                "an_exercicio": 2025,
                "nr_periodo": 6,
                "co_tipo_demonstrativo": "RREO",
                "no_anexo": "RREO-Anexo 01",
                "id_ente": 3550308,
            },
        ),
        Check(
            "comex",
            "comex_uf",
            "https://api-comexstat.mdic.gov.br/tables/uf",
            _ok_list,
            _whole,
            params={"language": "pt"},
        ),
        Check(
            "comex",
            "comex_geral",
            "https://api-comexstat.mdic.gov.br/general?language=pt",
            _ok_comex_list,
            _comex_small,
            method="POST",
            json={
                "flow": "export",
                "monthDetail": True,
                "period": {"from": "2026-01", "to": "2026-03"},
                "filters": [{"filter": "state", "values": [41]}],
                "details": ["country"],
                "metrics": ["metricFOB", "metricKG"],
            },
        ),
        *probes(),
        Check(
            "odata",
            "odata_ptax_metadata",
            f"{OLINDA}/PTAX/versao/v1/odata/$metadata",
            _ok_xml,
            _whole,
            ".xml",
        ),
        Check("odata", "odata_ptax_swagger", f"{OLINDA}/PTAX/versao/v1/swagger", _ok_any_json, _whole),
        Check(
            "odata",
            "odata_saldos_metadata",
            f"{OLINDA}/Saldos_BCB/versao/v1/odata/$metadata",
            _ok_xml,
            _whole,
            ".xml",
        ),
        Check(
            "odata", "odata_saldos_swagger", f"{OLINDA}/Saldos_BCB/versao/v1/swagger", _ok_any_json, _whole
        ),
    ]


OLINDA = "https://olinda.bcb.gov.br/olinda/servico"


def _ok_xml(r: httpx.Response) -> str:
    from prodata.catalog.model import safe_xml

    safe_xml(r.content)
    return f"XML válido, {len(r.content)} bytes"


def conferir_parametros_odata() -> int:
    """Cada parâmetro conferido de odata_params.json continua trazendo as datas pedidas (RF-4937)."""
    from datetime import date

    from prodata.catalog.http import CatalogClient
    from prodata.catalog.readers import odata

    period = (date(2025, 1, 1), date(2025, 6, 30))
    examples = {"moeda": "USD"}
    failures = 0
    services: dict[str, odata.Service] = {}
    with CatalogClient(timeout=60) as client:
        for key in odata.verified_params():
            servico, consulta = key.split("/", 1)
            start = time.perf_counter()
            try:
                if servico not in services:
                    versao = "v2" if servico in ("BcBase", "taxaJuros") else "v1"
                    services[servico] = odata.describe(client, servico, versao)
                entry = services[servico].entry(consulta)
                values = odata.param_values(entry, *period, examples)
                result = odata.read(client, services[servico], consulta, values, limit=50_000)
                if not result.frame.height:
                    raise ValueError(f"nenhuma linha com {values}")
                print(
                    f"ok    odata    {key[:44]:44} {time.perf_counter() - start:5.1f}s  {result.frame.height} linhas"
                )
            except Exception as exc:
                failures += 1
                print(f"FALHA odata    {key[:44]:44} {type(exc).__name__}: {exc}")
    return failures


def conferir_portais(gravar: bool) -> int:
    """Os portais verificados respondem e os indisponíveis são testados de novo (RF-4936)."""
    from prodata.catalog.http import CatalogClient
    from prodata.catalog.portals import PORTALS
    from prodata.catalog.readers import ckan

    failures = 0
    with CatalogClient(timeout=120) as client:
        for p in PORTALS:
            start = time.perf_counter()
            try:
                rows = ckan.catalog(client, p.id)
                print(f"ok    portais  {p.id:22} {time.perf_counter() - start:5.1f}s  {len(rows)} conjuntos")
            except Exception as exc:
                failures += 1
                print(f"FALHA portais  {p.id:22} {type(exc).__name__}: {exc}")
    if gravar:
        with httpx.Client(timeout=60, headers={"User-Agent": "prodata-catalogo"}) as raw:
            search = raw.get(
                "https://dados.cvm.gov.br/api/3/action/package_search", params={"rows": 3}
            ).json()
            (FIXTURES / "ckan_cvm_busca.json").write_bytes(_json(search))
            name = search["result"]["results"][0]["name"]
            show = raw.get("https://dados.cvm.gov.br/api/3/action/package_show", params={"id": name}).json()
            (FIXTURES / "ckan_cvm_conjunto.json").write_bytes(_json(show))
            print(f"gravado: ckan_cvm_busca.json e ckan_cvm_conjunto.json ({name})")
    # Estados e capitais que não leem direto (RF-4964): o mesmo cliente e a mesma identificação do programa
    # (certificados do Windows, "Desata/<versão> (catalogo de dados publicos)"), sem se passar por navegador.
    # Diz só o que mudou em relação à situação gravada no programa.
    import ssl

    from prodata.catalog.http import blocked, user_agent
    from prodata.catalog.portals import PLACES

    def now_state(base: str) -> tuple[str, int]:
        """(situação vista agora, conjuntos com arquivo) com o mesmo critério da revisão de 2026-11-26."""
        try:
            r = raw.get(f"{base}/api/3/action/package_search", params={"rows": 100})
        except httpx.TimeoutException:
            return "fora_do_ar", 0
        except httpx.HTTPError:
            return "sem_resposta", 0
        if r.headers.get("content-type", "").startswith("application/json") and r.json().get("success"):
            res = r.json()["result"]
            with_files = sum(1 for d in res["results"] if any(x.get("url") for x in d.get("resources", [])))
            return ("le_direto" if with_files else "sem_dados"), res["count"]
        if blocked(r.content) or r.status_code == 403:
            return "bloqueia", 0
        return ("fora_do_ar" if r.status_code >= 500 else "outra_plataforma"), 0

    with httpx.Client(timeout=20, follow_redirects=True, verify=ssl.create_default_context(),
                      headers={"User-Agent": user_agent()}) as raw:  # fmt: skip
        seen: set[str] = set()
        for place in PLACES:
            if place.situacao == "le_direto" or not place.pagina or place.pagina in seen:
                continue
            seen.add(place.pagina)
            found, count = now_state(place.pagina)
            same = found == place.situacao or (found == "sem_resposta" and place.situacao == "fora_do_ar")
            note = "igual" if same else f"MUDOU: agora {found}" + (f" ({count} conjuntos)" if count else "")
            print(f"info  lugares  {place.pagina[8:44]:36} {note} — gravado: {place.situacao} ({place.nome})")
    return failures


def _ok_probe(r: httpx.Response) -> str:
    return f"HTTP {r.status_code}, {len(r.content)} bytes"


def probes() -> list[Check]:
    """As sondas da conferência de situação (RF-4921), tal como estão em prodata.catalog.hosts."""
    from prodata.catalog import hosts

    out = []
    for s in hosts.SERVICES.values():
        if s.id == "receita":
            dav: dict[str, Any] = {"auth": (hosts.CNPJ_LINKS[0][0], ""), "headers": {"Depth": "1"}}
            out.append(
                Check(
                    "sondas", f"sonda_{s.id}", s.probe, _ok_probe, method="PROPFIND", content=PROPFIND, **dav
                )
            )
        else:
            out.append(Check("sondas", f"sonda_{s.id}", s.probe, _ok_probe, method=s.probe_method))
        out.append(Check("sondas", f"pagina_{s.id}", s.page, _ok_probe))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "servicos", nargs="*", help="bcb, olinda, ibge, ipea, tesouro, siconfi, comex, receita, anbima"
    )
    parser.add_argument(
        "--gravar", action="store_true", help="grava as respostas reduzidas em tests/fixtures/catalogo"
    )
    parser.add_argument("--mes", default="2026-11", help="mês do CNPJ conferido (AAAA-MM)")
    args = parser.parse_args()
    if args.gravar:
        FIXTURES.mkdir(parents=True, exist_ok=True)
    failures = 0
    with httpx.Client(
        timeout=30, follow_redirects=False, headers={"User-Agent": "prodata-catalogo"}
    ) as client:
        for c in checks(args.mes):
            if args.servicos and c.service not in args.servicos:
                continue
            start = time.perf_counter()
            try:
                r = client.request(
                    c.method,
                    c.url,
                    params=c.params or None,
                    auth=c.auth,
                    headers=c.headers,
                    content=c.content,
                    json=c.json,
                )
                if r.status_code >= 400 and c.name != "sgs_sem_periodo":
                    raise ValueError(f"HTTP {r.status_code}")
                note = c.check(r)
                if args.gravar and c.reduce:
                    (FIXTURES / f"{c.name}{c.suffix}").write_bytes(c.reduce(r))
                print(f"ok    {c.service:8} {c.name:22} {time.perf_counter() - start:5.1f}s  {note}")
            except Exception as exc:
                failures += 1
                print(
                    f"FALHA {c.service:8} {c.name:22} {time.perf_counter() - start:5.1f}s  {type(exc).__name__}: {exc}"
                )
    if not args.servicos or "odata" in args.servicos:
        failures += conferir_parametros_odata()
    if not args.servicos or "portais" in args.servicos:
        failures += conferir_portais(args.gravar)
    print(f"\n{failures} falha(s)" if failures else "\ntudo no ar")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
