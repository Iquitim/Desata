"""Os únicos endereços que o catálogo acessa (spec 049, RF-4981; constituição 1.8.1, princípio IV).

A lista é fixa, no código: nada vindo da tela, de um fluxo ou de uma resposta acrescenta endereço. Cada serviço
diz de que órgão é (para as mensagens e o selo de situação), os hosts que usa e a sonda da conferência (RF-4921).
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Service:
    id: str
    # Quem publica, como aparece para a pessoa ("o site do IBGE").
    agency: str
    short: str
    hosts: tuple[str, ...]
    # Página oficial do órgão para os dados abertos: só um link que a pessoa abre no navegador; o programa não acessa.
    page: str
    # A menor consulta que mostra se o serviço responde (RF-4921). Montada pelo leitor quando precisa de data.
    probe: str
    # HEAD quando a sonda é um arquivo: confere sem baixar.
    probe_method: str = "GET"


# Link público de compartilhamento da pasta do CNPJ no Nextcloud oficial da Receita: igual para todos e publicado
# pelo órgão, não é credencial (constituição 1.8.1). O segundo é o alternativo, para a mesma pasta.
CNPJ_DAV = "https://arquivos.receitafederal.gov.br/public.php/webdav"
CNPJ_LINKS = (("gn672Ad4CF8N6TK", "/Dados/Cadastros/CNPJ"), ("YggdBLfdninEJX9", ""))

SERVICES: dict[str, Service] = {
    s.id: s
    for s in (
        Service(
            "bcb_sgs",
            "Banco Central do Brasil",
            "Banco Central",
            ("api.bcb.gov.br",),
            "https://dadosabertos.bcb.gov.br",
            "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/1?formato=json",
        ),
        Service(
            "bcb_dados",
            "Banco Central do Brasil",
            "Banco Central",
            ("dadosabertos.bcb.gov.br",),
            "https://dadosabertos.bcb.gov.br",
            "https://dadosabertos.bcb.gov.br/api/3/action/package_search?rows=0",
        ),
        Service(
            "bcb_olinda",
            "Banco Central do Brasil",
            "Banco Central",
            ("olinda.bcb.gov.br",),
            "https://dadosabertos.bcb.gov.br",
            "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/Moedas?$format=json&$top=1",
        ),
        Service(
            "ibge",
            "Instituto Brasileiro de Geografia e Estatística (IBGE)",
            "IBGE",
            ("servicodados.ibge.gov.br",),
            "https://servicodados.ibge.gov.br/api/docs",
            "https://servicodados.ibge.gov.br/api/v1/localidades/regioes",
        ),
        Service(
            "ipea",
            "Instituto de Pesquisa Econômica Aplicada (Ipea), Ipeadata",
            "Ipeadata",
            ("www.ipeadata.gov.br",),
            "https://www.ipeadata.gov.br",
            "https://www.ipeadata.gov.br/api/odata4/Temas",
        ),
        Service(
            "tesouro",
            "Tesouro Nacional, Tesouro Transparente",
            "Tesouro",
            ("www.tesourotransparente.gov.br",),
            "https://www.tesourotransparente.gov.br",
            "https://www.tesourotransparente.gov.br/ckan/api/3/action/site_read",
        ),
        Service(
            "siconfi",
            "Tesouro Nacional, Siconfi",
            "Siconfi",
            ("apidatalake.tesouro.gov.br",),
            "https://siconfi.tesouro.gov.br",
            "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/entes?limit=1",
        ),
        Service(
            "comex",
            "Ministério do Desenvolvimento, Indústria, Comércio e Serviços, Comex Stat",
            "Comex Stat",
            ("api-comexstat.mdic.gov.br",),
            "https://comexstat.mdic.gov.br",
            "https://api-comexstat.mdic.gov.br/general/dates/updated",
        ),
        Service(
            "receita",
            "Receita Federal do Brasil",
            "Receita Federal",
            ("arquivos.receitafederal.gov.br",),
            "https://dados.gov.br/dados/conjuntos-dados/cadastro-nacional-da-pessoa-juridica---cnpj",
            f"{CNPJ_DAV}{CNPJ_LINKS[0][1]}/",
        ),
        Service(
            "anbima",
            "ANBIMA",
            "ANBIMA",
            ("www.anbima.com.br",),
            "https://www.anbima.com.br/feriados/feriados.asp",
            "https://www.anbima.com.br/feriados/arqs/feriados_nacionais.xls",
            probe_method="HEAD",
        ),
    )
}

ALLOWED_HOSTS: frozenset[str] = frozenset(h for s in SERVICES.values() for h in s.hosts)


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def service_of(url: str) -> Service | None:
    host = host_of(url)
    return next((s for s in SERVICES.values() if host in s.hosts), None)


def allowed(url: str) -> bool:
    """Só HTTPS, só os hosts da lista, sem usuário e senha nem porta fora do padrão no endereço."""
    parts = urlsplit(url)
    return (
        parts.scheme == "https"
        and (parts.hostname or "").lower() in ALLOWED_HOSTS
        and parts.username is None
        and parts.password is None
        and parts.port in (None, 443)
    )
