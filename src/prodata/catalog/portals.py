"""Portais de dados abertos verificados (spec 049, RF-4936, RF-4949, RF-4950).

Cada portal usa o CKAN e respondeu sem conta nem token nas verificações de 2026-11-22 e 2026-11-26. Os hosts dos arquivos entram
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
        id="sp", nome="Dados abertos do Estado de São Paulo", orgao="Governo do Estado de São Paulo",
        esfera="estadual", ckan="https://dadosabertos.sp.gov.br", site="o portal do Estado de São Paulo",
        arquivos=("infosiga.detran.sp.gov.br", "0010068detrandadoabprdsa.blob.core.windows.net",
                  "repositorio.seade.gov.br", "dersp.der.sp.gov.br", "portal.fazenda.sp.gov.br"),
        nota="Parte dos arquivos fica nos sites do Detran (Infosiga e o armazenamento oficial dele), da Seade, do DER "
             "e da Fazenda, para onde o próprio portal aponta.",
    ),
    Portal(
        id="rj", nome="Dados abertos do Rio de Janeiro", orgao="Governo do Estado do Rio de Janeiro",
        esfera="estadual", ckan="https://dadosabertos.rj.gov.br", site="o portal do Rio de Janeiro",
        arquivos=("www.ispdados.rj.gov.br",),
    ),
    Portal(
        id="al", nome="Alagoas em Dados", orgao="Governo do Estado de Alagoas", esfera="estadual",
        ckan="https://dados.al.gov.br/catalogo", site="o portal de Alagoas", arquivos=("portal.dados.al.gov.br",),
        nota="Muitos arquivos em PDF e em formatos de mapa: aparecem só como link.",
    ),
    Portal(
        id="ba", nome="Dados abertos da Bahia", orgao="Governo do Estado da Bahia", esfera="estadual",
        ckan="https://dados.ba.gov.br", site="o portal da Bahia",
        nota="O site da Bahia envia o certificado de segurança incompleto: num computador que ainda não tem o "
             "certificado intermediário, a leitura falha com o motivo.",
    ),
    Portal(
        id="mt", nome="Dados abertos de Mato Grosso", orgao="Governo do Estado de Mato Grosso", esfera="estadual",
        ckan="https://dadosabertos.mt.gov.br", site="o portal de Mato Grosso",
    ),
    Portal(
        id="ac", nome="Dados abertos do Acre", orgao="Governo do Estado do Acre", esfera="estadual",
        ckan="https://dados.ac.gov.br", site="o portal do Acre",
    ),
    Portal(
        id="sp_capital", nome="Dados abertos da Prefeitura de São Paulo", orgao="Prefeitura de São Paulo",
        esfera="municipal", ckan="https://dados.prefeitura.sp.gov.br", site="o portal da Prefeitura de São Paulo",
    ),
    Portal(
        id="recife", nome="Dados abertos do Recife", orgao="Prefeitura do Recife", esfera="municipal",
        ckan="https://dados.recife.pe.gov.br", site="o portal da Prefeitura do Recife",
        arquivos=("ckan-storage-download.app.emprel.gov.br",),
        nota="Os arquivos ficam no armazenamento da Emprel, a empresa de TI da prefeitura, para onde o portal aponta.",
    ),
    Portal(
        id="fortaleza", nome="Dados abertos de Fortaleza", orgao="Prefeitura de Fortaleza", esfera="municipal",
        ckan="https://dados.fortaleza.ce.gov.br", site="o portal da Prefeitura de Fortaleza",
    ),
    Portal(
        id="poa", nome="Dados abertos de Porto Alegre", orgao="Prefeitura de Porto Alegre", esfera="municipal",
        ckan="https://dadosabertos.poa.br", site="o portal da Prefeitura de Porto Alegre",
    ),
    Portal(
        id="bh", nome="Dados abertos de Belo Horizonte", orgao="Prefeitura de Belo Horizonte", esfera="municipal",
        ckan="https://dados.pbh.gov.br", site="o portal da Prefeitura de Belo Horizonte", arquivos=("ckan.pbh.gov.br",),
    ),
    Portal(
        id="goiania", nome="Dados abertos de Goiânia", orgao="Prefeitura de Goiânia", esfera="municipal",
        ckan="https://dadosabertos.goiania.go.gov.br", site="o portal da Prefeitura de Goiânia",
        arquivos=("www4.goiania.go.gov.br",),
    ),
    Portal(
        id="mogi", nome="Dados abertos de Mogi das Cruzes", orgao="Prefeitura de Mogi das Cruzes", esfera="municipal",
        ckan="https://dados.mogidascruzes.sp.gov.br", site="o portal da Prefeitura de Mogi das Cruzes",
    ),
)  # fmt: skip

BY_ID: dict[str, Portal] = {p.id: p for p in PORTALS}

# ------------------------------------------------------------------ estados e capitais (RF-4949, RF-4950)

Situation = Literal["le_direto", "bloqueia", "outra_plataforma", "fora_do_ar", "sem_dados", "sem_portal"]
CHECKED = "2026-11-26"


@dataclass(frozen=True)
class Place:
    """Um estado ou uma capital, sempre listado, com a situação conferida do portal de dados abertos."""

    uf: str
    nome: str
    ibge: str  # código do IBGE: 2 dígitos (UF) ou 7 (município)
    esfera: Literal["estadual", "municipal"]
    situacao: Situation
    portal: str = ""  # id do Portal quando lê direto
    pagina: str = ""  # para Abrir no navegador
    motivo: str = ""  # em palavras, quando não lê direto
    capital: bool = False

    @property
    def id(self) -> str:
        return f"{self.esfera[:3]}:{self.ibge}"


_NONE = "Nenhum portal de dados abertos do governo foi encontrado na conferência."
_STATE_NONE = "Nenhum portal de dados abertos do governo do estado foi encontrado na conferência."


def _state(
    uf: str, nome: str, ibge: str, situacao: Situation, portal: str = "", pagina: str = "", motivo: str = ""
) -> Place:
    if situacao == "sem_portal" and not motivo:
        motivo = _STATE_NONE
    return Place(uf, nome, ibge, "estadual", situacao, portal, pagina, motivo)


def _capital(
    uf: str, nome: str, ibge: str, situacao: Situation, portal: str = "", pagina: str = "", motivo: str = ""
) -> Place:
    if situacao == "sem_portal" and not motivo:
        motivo = _NONE
    return Place(uf, nome, ibge, "municipal", situacao, portal, pagina, motivo, capital=True)


_OTHER = "O portal existe, mas usa {0}, que o programa ainda não lê."
_BLOCK = "O portal recusa programas (bloqueio de leitura automática); o programa não se passa por navegador."

PLACES: tuple[Place, ...] = (
    _state("AC", "Acre", "12", "le_direto", "ac"),
    _state("AL", "Alagoas", "27", "le_direto", "al"),
    _state("AP", "Amapá", "16", "sem_portal"),
    _state("AM", "Amazonas", "13", "sem_portal"),
    _state("BA", "Bahia", "29", "le_direto", "ba"),
    _state("CE", "Ceará", "23", "bloqueia", pagina="https://dados.ce.gov.br", motivo=_BLOCK),
    _state("DF", "Distrito Federal", "53", "outra_plataforma", pagina="https://dados.df.gov.br",
           motivo=_OTHER.format("a plataforma Liferay")),
    _state("ES", "Espírito Santo", "32", "le_direto", "es"),
    _state("GO", "Goiás", "52", "le_direto", "go"),
    _state("MA", "Maranhão", "21", "sem_portal"),
    _state("MT", "Mato Grosso", "51", "le_direto", "mt"),
    _state("MS", "Mato Grosso do Sul", "50", "sem_portal"),
    _state("MG", "Minas Gerais", "31", "le_direto", "mg"),
    _state("PA", "Pará", "15", "fora_do_ar", pagina="https://dados.pa.gov.br",
           motivo="O portal não respondeu em 20 segundos na conferência."),
    _state("PB", "Paraíba", "25", "sem_dados", pagina="https://dados.pb.gov.br",
           motivo="O portal lista 7 conjuntos, mas nenhum tem endereço de arquivo para ler."),
    _state("PR", "Paraná", "41", "outra_plataforma", pagina="https://www.dados.pr.gov.br",
           motivo=_OTHER.format("a plataforma Drupal")),
    _state("PE", "Pernambuco", "26", "le_direto", "pe"),
    _state("PI", "Piauí", "22", "outra_plataforma", pagina="https://dados.pi.gov.br",
           motivo=_OTHER.format("um site WordPress (Observatório de Dados do Piauí)")),
    _state("RJ", "Rio de Janeiro", "33", "le_direto", "rj"),
    _state("RN", "Rio Grande do Norte", "24", "sem_dados", pagina="https://dados.rn.gov.br",
           motivo="O portal existe, mas está vazio (nenhum conjunto)."),
    _state("RS", "Rio Grande do Sul", "43", "le_direto", "rs"),
    _state("RO", "Rondônia", "11", "fora_do_ar", pagina="https://dados.ro.gov.br",
           motivo="O portal respondeu erro 500 (falha no servidor) na conferência."),
    _state("RR", "Roraima", "14", "sem_portal"),
    _state("SC", "Santa Catarina", "42", "le_direto", "sc"),
    _state("SP", "São Paulo", "35", "le_direto", "sp"),
    _state("SE", "Sergipe", "28", "sem_portal"),
    _state("TO", "Tocantins", "17", "sem_portal"),
    _capital("AC", "Rio Branco", "1200401", "sem_portal"),
    _capital("AL", "Maceió", "2704302", "sem_portal"),
    _capital("AP", "Macapá", "1600303", "sem_portal"),
    _capital("AM", "Manaus", "1302603", "sem_portal"),
    _capital("BA", "Salvador", "2927408", "outra_plataforma", pagina="https://dados.salvador.ba.gov.br",
             motivo=_OTHER.format("a plataforma ArcGIS")),
    _capital("CE", "Fortaleza", "2304400", "le_direto", "fortaleza"),
    _capital("DF", "Brasília", "5300108", "outra_plataforma", pagina="https://dados.df.gov.br",
             motivo="Brasília usa o portal do Distrito Federal, que usa a plataforma Liferay; o programa ainda não o lê."),
    _capital("ES", "Vitória", "3205309", "bloqueia", pagina="https://dadosabertos.vitoria.es.gov.br", motivo=_BLOCK),
    _capital("GO", "Goiânia", "5208707", "le_direto", "goiania"),
    _capital("MA", "São Luís", "2111300", "sem_portal"),
    _capital("MT", "Cuiabá", "5103403", "sem_portal"),
    _capital("MS", "Campo Grande", "5002704", "sem_portal"),
    _capital("MG", "Belo Horizonte", "3106200", "le_direto", "bh"),
    _capital("PA", "Belém", "1501402", "sem_portal"),
    _capital("PB", "João Pessoa", "2507507", "sem_portal"),
    _capital("PR", "Curitiba", "4106902", "outra_plataforma", pagina="https://dadosabertos.curitiba.pr.gov.br",
             motivo=_OTHER.format("um sistema próprio da prefeitura")),
    _capital("PE", "Recife", "2611606", "le_direto", "recife"),
    _capital("PI", "Teresina", "2211001", "outra_plataforma", pagina="https://dados.teresina.pi.gov.br",
             motivo=_OTHER.format("a plataforma OpenMetadata")),
    _capital("RJ", "Rio de Janeiro", "3304557", "outra_plataforma", pagina="https://www.data.rio",
             motivo=_OTHER.format("a plataforma ArcGIS Hub (DATA.RIO)")),
    _capital("RN", "Natal", "2408102", "fora_do_ar", pagina="https://dados.natal.br",
             motivo="O portal não respondeu em 20 segundos na conferência."),
    _capital("RS", "Porto Alegre", "4314902", "le_direto", "poa"),
    _capital("RO", "Porto Velho", "1100205", "fora_do_ar", pagina="https://dados.portovelho.ro.gov.br",
             motivo="O portal respondeu erro 502 (servidor intermediário) na conferência."),
    _capital("RR", "Boa Vista", "1400100", "sem_portal"),
    _capital("SC", "Florianópolis", "4205407", "sem_portal"),
    _capital("SP", "São Paulo", "3550308", "le_direto", "sp_capital"),
    _capital("SE", "Aracaju", "2800308", "sem_portal"),
    _capital("TO", "Palmas", "1721000", "sem_portal"),
)  # fmt: skip

# Prefeituras que não são capitais e leem direto: ficam no mapa, dentro do estado (RF-4950, RF-4958).
MAP_CITIES: tuple[Place, ...] = (Place("SP", "Mogi das Cruzes", "3530607", "municipal", "le_direto", "mogi"),)

# Para o script de conferência testar de novo o que não lê direto (RF-4964).
UNAVAILABLE: dict[str, str] = {
    pl.pagina: f"{pl.nome}: {pl.motivo}" for pl in PLACES if pl.situacao != "le_direto" and pl.pagina
}
