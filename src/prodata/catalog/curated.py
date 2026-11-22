"""Os destaques do catálogo (spec 049, RF-4931, RF-4941) e o dicionário de colunas (RF-4912).

A lista diz **como ler** cada fonte (o leitor e os parâmetros) e traz o que não muda: nome simples, resumo,
categoria, palavras-chave, colunas explicadas, licença e citação. O que muda (período, último dado, atualização)
vem sempre da fonte, na hora.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from prodata.catalog.model import Column

Kind = Literal[
    "sgs", "ptax", "focus", "ibge_tabela", "ibge_localidades", "ipea", "tesouro_direto", "siconfi", "comex",
    "cnpj", "feriados", "dias_uteis",
]  # fmt: skip


@dataclass(frozen=True)
class Category:
    id: str
    nome: str
    # Nome do ícone na interface (icons.js).
    icone: str


CATEGORIES: tuple[Category, ...] = (
    Category("economia", "Economia e juros", "percent"),
    Category("precos", "Preços e inflação", "trending-up"),
    Category("cambio", "Câmbio", "currency"),
    Category("territorio", "Território", "map"),
    Category("populacao", "População e trabalho", "users"),
    Category("empresas", "Empresas (CNPJ)", "building"),
    Category("calendario", "Calendário", "calendar"),
    Category("contas", "Contas públicas", "landmark"),
    Category("comercio", "Comércio exterior", "ship"),
    Category("series", "Séries do Ipeadata", "chart"),
)
CATEGORY_IDS = frozenset(c.id for c in CATEGORIES)

LICENSES = {
    "bcb": "Open Data Commons Open Database License (ODbL): uso livre com atribuição ao Banco Central do Brasil.",
    "ibge": "Dados abertos do IBGE: uso livre com citação da fonte.",
    "ipea": "Dados do Ipeadata: uso livre com citação da fonte (Ipea e a fonte original da série).",
    "tesouro": "Open Data Commons Open Database License (ODbL): uso livre com atribuição ao Tesouro Nacional.",
    "receita": "Dados abertos da Receita Federal: uso livre com citação da fonte.",
    "comex": "Dados abertos do Comex Stat (MDIC): uso livre com citação da fonte.",
    "calendario": "Calculado pelo programa a partir das leis citadas; feriados bancários da ANBIMA.",
}

_DATA = Column("data", "data", "Dia do valor; para série mensal, o primeiro dia do mês.")
_VALOR_PCT_AA = Column("valor", "numero", "Taxa em % ao ano.")


@dataclass(frozen=True)
class Source:
    id: str
    nome: str
    resumo: str
    categoria: str
    # Serviço de hosts.SERVICES de que a fonte depende (situação e citação).
    servico: str
    kind: Kind
    params: dict[str, Any] = field(default_factory=dict)
    periodicidade: str = ""
    granularidade: str = "Brasil"
    unidade: str = ""
    palavras: tuple[str, ...] = ()
    colunas: tuple[Column, ...] = ()
    licenca: str = ""
    citacao: str = ""
    # Escolhas que a caixa oferece (RF-4914), com os valores prontos.
    escolhas: dict[str, Any] = field(default_factory=dict)
    destaque: bool = True

    @property
    def codigo(self) -> str:
        return self.id.rsplit("/", 1)[-1]


def _sgs(code: int, nome: str, resumo: str, categoria: str, periodicidade: str, unidade: str,
         valor: str, palavras: tuple[str, ...], **kw: Any) -> Source:  # fmt: skip
    return Source(
        id=f"bcb.sgs/{code}",
        nome=nome,
        resumo=resumo,
        categoria=categoria,
        servico="bcb_sgs",
        kind="sgs",
        params={"codigo": code},
        periodicidade=periodicidade,
        unidade=unidade,
        palavras=(*palavras, "banco central", "bcb", "sgs", str(code)),
        colunas=(_DATA, Column("valor", "numero", valor)),
        licenca=LICENSES["bcb"],
        citacao=f"Banco Central do Brasil, SGS {code} — {nome}",
        escolhas={"periodo": {"kind": "ultimos_anos", "anos": 5}},
        **kw,
    )


def _ibge_index(
    table: int, nome: str, resumo: str, palavras: tuple[str, ...], variables: dict[str, int]
) -> Source:
    return Source(
        id=f"ibge.agregado/{table}",
        nome=nome,
        resumo=resumo,
        categoria="precos",
        servico="ibge",
        kind="ibge_tabela",
        params={"tabela": table, "variavel": next(iter(variables.values())), "nivel": "N1"},
        periodicidade="mensal",
        unidade="número-índice ou %",
        palavras=(*palavras, "ibge", "inflação", str(table)),
        colunas=(
            Column("codigo", "texto", "Código da localidade no IBGE (1 = Brasil)."),
            Column("localidade", "texto", "Nome da localidade."),
            Column("periodo", "texto", "Mês no formato do IBGE (AAAAMM)."),
            _DATA,
            Column("valor", "numero", "Valor da variável escolhida (número-índice ou variação em %)."),
        ),
        licenca=LICENSES["ibge"],
        citacao=f"IBGE, tabela {table} — {nome}",
        escolhas={"periodo": {"kind": "ultimos_anos", "anos": 5}, "variavel": variables},
    )


_LOCALIDADE = (
    Column("codigo", "texto", "Código do município no IBGE, com 7 dígitos."),
    Column("localidade", "texto", "Nome do lugar, sem a UF."),
    Column("nivel", "texto", "N1 Brasil, N2 região, N3 UF, N6 município."),
    Column("periodo", "texto", "Ano (AAAA) ou trimestre (AAAA0T) no formato do IBGE."),
    _DATA,
)

SOURCES: tuple[Source, ...] = (
    _sgs(432, "Taxa Selic meta", "A meta da Selic definida pelo Copom, dia a dia.", "economia", "diária",
         "% ao ano", "Meta da taxa Selic em % ao ano, definida pelo Copom.", ("selic", "copom", "juros", "meta")),
    _sgs(11, "Taxa Selic diária", "A taxa Selic efetiva de cada dia útil.", "economia", "diária", "% ao dia",
         "Taxa Selic do dia, em % ao dia.", ("selic", "over", "juros")),
    _sgs(12, "CDI", "A taxa dos depósitos interbancários de cada dia útil.", "economia", "diária", "% ao dia",
         "Taxa DI (CDI) do dia, em % ao dia.", ("cdi", "di", "interbancário", "juros")),
    Source(
        id="bcb.focus/mensal", nome="Expectativas do mercado (Focus)",
        resumo="O que os economistas esperam para IPCA, Selic, câmbio e PIB, pesquisa a pesquisa.",
        categoria="economia", servico="bcb_olinda", kind="focus", params={"indicador": "IPCA", "periodicidade": "mensal"},
        periodicidade="semanal", unidade="conforme o indicador",
        palavras=("focus", "expectativa", "mercado", "boletim", "previsão", "banco central"),
        colunas=(
            Column("data", "data", "Dia em que a pesquisa foi feita."),
            Column("indicador", "texto", "O que está sendo previsto (IPCA, Selic, PIB Total...)."),
            Column("referencia", "texto", "Para quando é a previsão (mês, trimestre ou ano)."),
            Column("mediana", "numero", "Mediana das respostas: o valor do meio."),
            Column("media", "numero", "Média das respostas."),
            Column("desvio_padrao", "numero", "Quanto as respostas variam entre si."),
            Column("minimo", "numero", "Menor resposta."),
            Column("maximo", "numero", "Maior resposta."),
            Column("respondentes", "inteiro", "Quantas instituições responderam."),
            Column("base_calculo", "inteiro", "0: respostas dos últimos 30 dias; 1: dos últimos 5 dias úteis."),
        ),
        licenca=LICENSES["bcb"], citacao="Banco Central do Brasil, Sistema de Expectativas de Mercado (Focus)",
        escolhas={"periodo": {"kind": "ultimos_anos", "anos": 1},
                  "indicador": ["IPCA", "IGP-M", "Selic", "Câmbio", "PIB Total"],
                  "periodicidade": ["mensal", "trimestral", "anual"]},
    ),
    _ibge_index(1737, "IPCA", "A inflação oficial do Brasil: número-índice e variações.", ("ipca", "inflação oficial"),
                {"Número-índice": 2266, "Variação mensal (%)": 63, "Acumulada em 12 meses (%)": 2265,
                 "Acumulada no ano (%)": 69}),
    _ibge_index(1736, "INPC", "A inflação das famílias de menor renda: número-índice e variações.", ("inpc",),
                {"Número-índice": 2289, "Variação mensal (%)": 44, "Acumulada em 12 meses (%)": 2292,
                 "Acumulada no ano (%)": 68}),
    _sgs(189, "IGP-M", "O índice geral de preços do mercado (FGV), usado em aluguéis.", "precos", "mensal",
         "% ao mês", "Variação do IGP-M no mês, em %.", ("igp-m", "igpm", "aluguel", "fgv", "inflação")),
    Source(
        id="bcb.ptax/moeda", nome="Dólar e outras moedas (PTAX)",
        resumo="A cotação oficial de compra e venda de cada dia útil, para o dólar e as principais moedas.",
        categoria="cambio", servico="bcb_olinda", kind="ptax", params={"moeda": "USD"},
        periodicidade="diária", unidade="R$ por unidade da moeda",
        palavras=("dólar", "dolar", "ptax", "câmbio", "euro", "moeda", "cotação", "usd", "eur"),
        colunas=(
            Column("data", "data", "Dia útil da cotação."),
            Column("moeda", "texto", "Código da moeda (USD, EUR...)."),
            Column("cotacao_compra", "numero", "Quantos reais o Banco Central paga por uma unidade da moeda."),
            Column("cotacao_venda", "numero", "Quantos reais custa uma unidade da moeda: é a PTAX usada em contratos."),
            Column("paridade_compra", "numero", "Quantas unidades da moeda valem um dólar (compra)."),
            Column("paridade_venda", "numero", "Quantas unidades da moeda valem um dólar (venda)."),
            Column("boletim", "texto", "Fechamento é a PTAX do dia."),
            Column("data_hora", "data", "Hora em que o boletim foi publicado."),
        ),
        licenca=LICENSES["bcb"], citacao="Banco Central do Brasil, PTAX",
        escolhas={"periodo": {"kind": "ultimos_anos", "anos": 2}, "moeda": "USD"},
    ),
    Source(
        id="ibge.localidades/regioes", nome="Regiões do Brasil", resumo="As 5 grandes regiões, com código e sigla.",
        categoria="territorio", servico="ibge", kind="ibge_localidades", params={"lista": "regioes"},
        periodicidade="quando muda", granularidade="Região", palavras=("região", "regiões", "ibge"),
        colunas=(Column("codigo", "texto", "Código da região no IBGE."), Column("sigla", "texto", "N, NE, SE, S, CO."),
                 Column("nome", "texto", "Nome da região.")),
        licenca=LICENSES["ibge"], citacao="IBGE, API de localidades",
    ),
    Source(
        id="ibge.localidades/estados", nome="Estados do Brasil",
        resumo="As 27 unidades da federação, com código do IBGE, sigla e região.",
        categoria="territorio", servico="ibge", kind="ibge_localidades", params={"lista": "estados"},
        periodicidade="quando muda", granularidade="UF", palavras=("estado", "estados", "uf", "ibge"),
        colunas=(Column("codigo", "texto", "Código da UF no IBGE, com 2 dígitos."),
                 Column("sigla", "texto", "Sigla da UF."), Column("nome", "texto", "Nome do estado."),
                 Column("regiao", "texto", "Região do estado."), Column("regiao_sigla", "texto", "Sigla da região.")),
        licenca=LICENSES["ibge"], citacao="IBGE, API de localidades",
    ),
    Source(
        id="ibge.localidades/municipios", nome="Municípios do Brasil",
        resumo="Os 5.571 municípios, com códigos de 7 e 6 dígitos, UF, região e regiões imediatas.",
        categoria="territorio", servico="ibge", kind="ibge_localidades", params={"lista": "municipios"},
        periodicidade="quando muda", granularidade="Município",
        palavras=("município", "municipios", "cidade", "cidades", "ibge", "código do município"),
        colunas=(
            Column("codigo", "texto", "Código do município no IBGE, com 7 dígitos (o último é o verificador)."),
            Column("codigo6", "texto", "Os 6 primeiros dígitos: o código que muitos sistemas usam, sem o verificador."),
            Column("nome", "texto", "Nome oficial do município."),
            Column("uf", "texto", "Sigla da UF."),
            Column("uf_codigo", "texto", "Código da UF no IBGE."),
            Column("uf_nome", "texto", "Nome do estado."),
            Column("regiao", "texto", "Região do Brasil."),
            Column("microrregiao", "texto", "Microrregião (divisão antiga do IBGE)."),
            Column("mesorregiao", "texto", "Mesorregião (divisão antiga do IBGE)."),
            Column("regiao_imediata", "texto", "Região geográfica imediata (divisão atual do IBGE)."),
            Column("regiao_intermediaria", "texto", "Região geográfica intermediária (divisão atual do IBGE)."),
        ),
        licenca=LICENSES["ibge"], citacao="IBGE, API de localidades",
    ),
    Source(
        id="ibge.agregado/6579", nome="População estimada", resumo="A população de cada município, estado e do Brasil, ano a ano.",
        categoria="populacao", servico="ibge", kind="ibge_tabela",
        params={"tabela": 6579, "variavel": 9324, "nivel": "N6"}, periodicidade="anual",
        granularidade="Brasil, UF e município", unidade="pessoas",
        palavras=("população", "habitantes", "estimativa", "ibge", "6579"),
        colunas=(*_LOCALIDADE, Column("valor", "numero", "População residente estimada, em pessoas.")),
        licenca=LICENSES["ibge"], citacao="IBGE, Estimativas da População, tabela 6579",
        escolhas={"periodo": {"kind": "ultimos_anos", "anos": 5}, "nivel": ["N1", "N3", "N6"]},
    ),
    Source(
        id="ibge.agregado/4099", nome="Taxa de desocupação (PNAD Contínua)",
        resumo="O desemprego no Brasil, por trimestre, das pessoas de 14 anos ou mais.",
        categoria="populacao", servico="ibge", kind="ibge_tabela",
        params={"tabela": 4099, "variavel": 4099, "nivel": "N1"}, periodicidade="trimestral",
        granularidade="Brasil, região, UF e capitais", unidade="%",
        palavras=("desemprego", "desocupação", "pnad", "trabalho", "ibge", "4099"),
        colunas=(*_LOCALIDADE, Column("valor", "numero", "Taxa de desocupação na semana de referência, em %.")),
        licenca=LICENSES["ibge"], citacao="IBGE, PNAD Contínua trimestral, tabela 4099",
        escolhas={"periodo": {"kind": "ultimos_anos", "anos": 5}, "nivel": ["N1", "N2", "N3"]},
    ),
    Source(
        id="ibge.agregado/5938", nome="PIB dos municípios",
        resumo="O produto interno bruto de cada município, a preços correntes.",
        categoria="populacao", servico="ibge", kind="ibge_tabela",
        params={"tabela": 5938, "variavel": 37, "nivel": "N6"}, periodicidade="anual",
        granularidade="Brasil, UF e município", unidade="mil reais",
        palavras=("pib", "produto interno bruto", "economia", "município", "ibge", "5938"),
        colunas=(*_LOCALIDADE, Column("valor", "numero", "PIB a preços correntes, em mil reais.")),
        licenca=LICENSES["ibge"], citacao="IBGE, Produto Interno Bruto dos Municípios, tabela 5938",
        escolhas={"periodo": {"kind": "ultimos_anos", "anos": 5}, "nivel": ["N1", "N3", "N6"]},
    ),
    Source(
        id="receita.cnpj/dados-abertos", nome="Cadastro de empresas (CNPJ)",
        resumo="Empresas, estabelecimentos e sócios de todo o Brasil, da Receita Federal. Arquivos grandes: baixa para uma pasta.",
        categoria="empresas", servico="receita", kind="cnpj", periodicidade="mensal", granularidade="Estabelecimento",
        palavras=("cnpj", "empresa", "empresas", "estabelecimento", "sócio", "socios", "receita", "cnae", "simples"),
        licenca=LICENSES["receita"], citacao="Receita Federal do Brasil, Dados Abertos do CNPJ",
    ),
    Source(
        id="calendario/feriados", nome="Feriados", resumo="Nacionais, estaduais, das capitais e bancários, com a lei de cada um; você pode editar.",
        categoria="calendario", servico="anbima", kind="feriados", periodicidade="anual", granularidade="Brasil, UF e município",
        palavras=("feriado", "feriados", "calendário", "anbima", "ponto facultativo"),
        colunas=(
            Column("data", "data", "Dia do feriado."), Column("nome", "texto", "Nome do feriado."),
            Column("tipo", "texto", "nacional, estadual, municipal, bancário, ponto facultativo ou seu."),
            Column("abrangencia", "texto", "BR, a sigla da UF ou o código do município."),
            Column("lei", "texto", "A lei que cria o feriado, quando conhecida."),
            Column("origem", "texto", "calculado, ANBIMA, do programa ou seu."),
            Column("confirmar", "texto", "Verdadeiro quando as fontes divergem: confira com a lei local."),
        ),
        licenca=LICENSES["calendario"], citacao="Feriados: leis federais, estaduais e municipais; ANBIMA",
        escolhas={"periodo": {"kind": "intervalo"}, "local": "BR", "calendario": ["civil", "bancario"]},
    ),
    Source(
        id="calendario/dias-uteis", nome="Dias úteis", resumo="Um dia por linha, dizendo se é útil no lugar escolhido.",
        categoria="calendario", servico="anbima", kind="dias_uteis", periodicidade="diária", granularidade="Brasil, UF e município",
        palavras=("dia útil", "dias úteis", "calendário", "útil", "anbima"),
        colunas=(Column("data", "data", "O dia."), Column("dia_util", "texto", "Verdadeiro quando é dia útil."),
                 Column("feriado", "texto", "Nome do feriado, quando é feriado.")),
        licenca=LICENSES["calendario"], citacao="Feriados: leis federais, estaduais e municipais; ANBIMA",
        escolhas={"periodo": {"kind": "intervalo"}, "local": "BR", "calendario": ["civil", "bancario"]},
    ),
    Source(
        id="tesouro.direto/precos-taxas", nome="Tesouro Direto: preços e taxas",
        resumo="O preço e a taxa de cada título do Tesouro Direto, dia a dia.",
        categoria="contas", servico="tesouro", kind="tesouro_direto", periodicidade="diária",
        palavras=("tesouro direto", "título", "títulos", "renda fixa", "tesouro selic", "ipca+", "prefixado"),
        colunas=(
            Column("data", "data", "Dia da cotação (data base)."),
            Column("titulo", "texto", "Tipo do título (Tesouro Selic, Tesouro IPCA+...)."),
            Column("vencimento", "data", "Quando o título vence."),
            Column("taxa_compra", "numero", "Taxa ao ano para quem compra, em %."),
            Column("taxa_venda", "numero", "Taxa ao ano para quem vende, em %."),
            Column("pu_compra", "numero", "Preço unitário de compra, em R$."),
            Column("pu_venda", "numero", "Preço unitário de venda, em R$."),
            Column("pu_base", "numero", "Preço unitário de referência, em R$."),
        ),
        licenca=LICENSES["tesouro"], citacao="Tesouro Nacional, Tesouro Transparente — Taxas dos Títulos Ofertados pelo Tesouro Direto",
        escolhas={"periodo": {"kind": "ultimos_anos", "anos": 1}},
    ),
    Source(
        id="siconfi/relatorios", nome="Receitas e despesas de estados e municípios (Siconfi)",
        resumo="Os relatórios fiscais (DCA, RREO, RGF) que cada ente entrega ao Tesouro.",
        categoria="contas", servico="siconfi", kind="siconfi", params={"relatorio": "dca"},
        periodicidade="anual e bimestral", granularidade="UF e município",
        palavras=("siconfi", "receita", "despesa", "orçamento", "dca", "rreo", "rgf", "prefeitura", "fiscal"),
        colunas=(
            Column("exercicio", "inteiro", "Ano do relatório."),
            Column("instituicao", "texto", "Quem entregou (prefeitura, governo, câmara)."),
            Column("codigo", "texto", "Código do ente no IBGE."),
            Column("anexo", "texto", "Anexo do relatório."),
            Column("coluna", "texto", "Coluna do anexo (previsão, realizado...)."),
            Column("cod_conta", "texto", "Código da conta contábil."),
            Column("conta", "texto", "Nome da conta."),
            Column("valor", "numero", "Valor em R$."),
        ),
        licenca=LICENSES["tesouro"], citacao="Tesouro Nacional, Siconfi",
        escolhas={"relatorio": ["dca", "rreo", "rgf"], "exercicio": None, "ente": None},
    ),
    Source(
        id="comex/exportacao", nome="Exportações (Comex Stat)", resumo="O que o Brasil vende ao exterior, por país, produto e UF.",
        categoria="comercio", servico="comex", kind="comex", params={"fluxo": "export"}, periodicidade="mensal",
        granularidade="Brasil e UF", unidade="US$ e kg",
        palavras=("exportação", "exportações", "comex", "comércio exterior", "ncm", "balança comercial"),
        colunas=(
            Column("ano", "inteiro", "Ano."), Column("mes", "inteiro", "Mês, quando o detalhe é mensal."), _DATA,
            Column("valor_fob_usd", "numero", "Valor FOB em dólares (sem frete e seguro)."),
            Column("peso_kg", "numero", "Peso líquido em quilos."),
        ),
        licenca=LICENSES["comex"], citacao="Ministério do Desenvolvimento, Indústria, Comércio e Serviços — Comex Stat",
        escolhas={"periodo": {"kind": "ultimos_anos", "anos": 1}, "detalhes": ["country", "state", "ncm", "chapter"]},
    ),
    Source(
        id="comex/importacao", nome="Importações (Comex Stat)", resumo="O que o Brasil compra do exterior, por país, produto e UF.",
        categoria="comercio", servico="comex", kind="comex", params={"fluxo": "import"}, periodicidade="mensal",
        granularidade="Brasil e UF", unidade="US$ e kg",
        palavras=("importação", "importações", "comex", "comércio exterior", "ncm", "balança comercial"),
        colunas=(
            Column("ano", "inteiro", "Ano."), Column("mes", "inteiro", "Mês, quando o detalhe é mensal."), _DATA,
            Column("valor_fob_usd", "numero", "Valor FOB em dólares (sem frete e seguro)."),
            Column("valor_cif_usd", "numero", "Valor CIF em dólares (com frete e seguro)."),
            Column("peso_kg", "numero", "Peso líquido em quilos."),
        ),
        licenca=LICENSES["comex"], citacao="Ministério do Desenvolvimento, Indústria, Comércio e Serviços — Comex Stat",
        escolhas={"periodo": {"kind": "ultimos_anos", "anos": 1}, "detalhes": ["country", "state", "ncm", "chapter"]},
    ),
)  # fmt: skip

BY_ID: dict[str, Source] = {s.id: s for s in SOURCES}


def get(source_id: str) -> Source | None:
    return BY_ID.get(source_id)
