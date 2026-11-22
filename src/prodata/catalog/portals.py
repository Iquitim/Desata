"""Portais de dados abertos verificados (spec 049, RF-4936).

Cada portal usa o CKAN e respondeu sem conta nem token na verificação de 2026-11-22. Os hosts dos arquivos entram
na lista fixa de endereços (``hosts.ALLOWED_HOSTS``) junto com o do portal; um recurso que aponta para qualquer outro
endereço vira só link (RF-4940). Nada vindo de um portal acrescenta endereço.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Sphere = Literal["federal", "estadual", "municipal"]


@dataclass(frozen=True)
class Portal:
    id: str
    nome: str
    orgao: str
    esfera: Sphere
    # Endereço base do CKAN: a API fica em ``{ckan}/api/3/action/...``.
    ckan: str
    # Como o portal aparece nas mensagens ("o portal da ANEEL não respondeu").
    site: str
    # Hosts onde o portal publica os arquivos (além do próprio).
    arquivos: tuple[str, ...] = ()
    nota: str = ""
    # Conjuntos por página na lista do portal. Santa Catarina corta respostas acima de ~130 KB: lote pequeno.
    lote: int = 500

    @property
    def api(self) -> str:
        return f"{self.ckan}/api/3/action"

    @property
    def host(self) -> str:
        return self.ckan.split("/")[2]

    @property
    def pagina(self) -> str:
        return self.ckan


PORTALS: tuple[Portal, ...] = (
    Portal(
        id="bcb_portal", nome="Banco Central do Brasil", orgao="Banco Central do Brasil", esfera="federal",
        ckan="https://dadosabertos.bcb.gov.br", site="o portal do Banco Central", arquivos=("olinda.bcb.gov.br",),
        nota="Os conjuntos são serviços OData do Olinda; as séries do SGS ficam no catálogo do SGS.",
    ),
    Portal(
        id="tesouro_portal", nome="Tesouro Transparente", orgao="Tesouro Nacional", esfera="federal",
        ckan="https://www.tesourotransparente.gov.br/ckan", site="o portal Tesouro Transparente",
    ),
    Portal(
        id="aneel", nome="Dados abertos da ANEEL", orgao="Agência Nacional de Energia Elétrica (ANEEL)",
        esfera="federal", ckan="https://dadosabertos.aneel.gov.br", site="o portal da ANEEL",
        nota="Portal lento: a lista completa pode levar meio minuto.",
    ),
    Portal(
        id="cvm", nome="Dados abertos da CVM", orgao="Comissão de Valores Mobiliários (CVM)", esfera="federal",
        ckan="https://dados.cvm.gov.br", site="o portal da CVM",
    ),
    Portal(
        id="ibama", nome="Dados abertos do IBAMA", orgao="Instituto Brasileiro do Meio Ambiente (IBAMA)",
        esfera="federal", ckan="https://dadosabertos.ibama.gov.br", site="o portal do IBAMA",
        arquivos=("stibamadadosabertosprd.blob.core.windows.net",),
        nota="Parte dos arquivos fica no armazenamento oficial do IBAMA na nuvem, para onde o próprio portal aponta.",
    ),
    Portal(
        id="tse", nome="Dados abertos do TSE", orgao="Tribunal Superior Eleitoral (TSE)", esfera="federal",
        ckan="https://dadosabertos.tse.jus.br", site="o portal do TSE", arquivos=("cdn.tse.jus.br",),
        nota="Muitos arquivos grandes: vão pelo download com pasta escolhida.",
    ),
    Portal(
        id="rs", nome="Dados abertos do Rio Grande do Sul", orgao="Governo do Estado do Rio Grande do Sul",
        esfera="estadual", ckan="https://dados.rs.gov.br", site="o portal do Rio Grande do Sul",
        arquivos=("data.rs.gov.br",), nota="Portal lento: a lista completa pode levar meio minuto.",
    ),
    Portal(
        id="pe", nome="Dados abertos de Pernambuco", orgao="Governo do Estado de Pernambuco", esfera="estadual",
        ckan="https://dados.pe.gov.br", site="o portal de Pernambuco",
    ),
    Portal(
        id="mg", nome="Dados abertos de Minas Gerais", orgao="Governo do Estado de Minas Gerais", esfera="estadual",
        ckan="https://dados.mg.gov.br", site="o portal de Minas Gerais",
    ),
    Portal(
        id="go", nome="Dados abertos de Goiás", orgao="Governo do Estado de Goiás", esfera="estadual",
        ckan="https://dadosabertos.go.gov.br", site="o portal de Goiás",
    ),
    Portal(
        id="es", nome="Dados abertos do Espírito Santo", orgao="Governo do Estado do Espírito Santo",
        esfera="estadual", ckan="https://dados.es.gov.br", site="o portal do Espírito Santo",
    ),
    Portal(
        id="sc", nome="Dados abertos de Santa Catarina", orgao="Governo do Estado de Santa Catarina",
        esfera="estadual", ckan="https://dados.sc.gov.br", site="o portal de Santa Catarina", lote=5,
        nota="O portal corta respostas grandes: alguns conjuntos podem não abrir.",
    ),
    Portal(
        id="sp_capital", nome="Dados abertos da Prefeitura de São Paulo", orgao="Prefeitura de São Paulo",
        esfera="municipal", ckan="https://dados.prefeitura.sp.gov.br", site="o portal da Prefeitura de São Paulo",
    ),
    Portal(
        id="recife", nome="Dados abertos do Recife", orgao="Prefeitura do Recife", esfera="municipal",
        ckan="https://dados.recife.pe.gov.br", site="o portal da Prefeitura do Recife",
    ),
    Portal(
        id="fortaleza", nome="Dados abertos de Fortaleza", orgao="Prefeitura de Fortaleza", esfera="municipal",
        ckan="https://dados.fortaleza.ce.gov.br", site="o portal da Prefeitura de Fortaleza",
    ),
    Portal(
        id="poa", nome="Dados abertos de Porto Alegre", orgao="Prefeitura de Porto Alegre", esfera="municipal",
        ckan="https://dadosabertos.poa.br", site="o portal da Prefeitura de Porto Alegre",
    ),
)  # fmt: skip

BY_ID: dict[str, Portal] = {p.id: p for p in PORTALS}

# Verificados e não disponíveis em 2026-11-22: o script de conferência volta a testar (RF-4936).
UNAVAILABLE: dict[str, str] = {
    "https://dados.antt.gov.br": "ANTT: não respondeu em 45 s",
    "https://dados.ba.gov.br": "Bahia: sem conexão",
    "https://www.data.rj.gov.br": "Rio de Janeiro: sem conexão",
    "https://dados.natal.br": "Natal: sem conexão",
    "https://www.dados.pr.gov.br": "Paraná: sem a API do CKAN aberta",
    "https://dadosabertos.curitiba.pr.gov.br": "Curitiba: sem a API do CKAN aberta",
    "https://dadosabertos.saude.gov.br": "Ministério da Saúde: sem a API do CKAN aberta",
}
