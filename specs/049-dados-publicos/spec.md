# Spec 049: dados públicos do Brasil — catálogo nativo, situação de cada órgão e downloads grandes

Status: Aprovada · Versão 0.9.6 · Criada: 2026-11-22 · Constituição 1.8.0 (princípio IV)

## Contexto

Quem analisa dados no Brasil volta sempre às mesmas fontes públicas: a Selic e o IPCA do Banco Central, a população
e os municípios do IBGE, o dólar do dia, o cadastro de CNPJ da Receita. Hoje, para usar qualquer uma delas no
programa, a pessoa precisa:

- descobrir o endereço da API (que muda, e cada órgão tem o seu jeito);
- montar a fonte de API à mão, com parâmetros, datas e paginação;
- saber regras escondidas (o SGS do Banco Central, desde 2025, exige período e aceita no máximo 10 anos por
  consulta; o CNPJ vem em dezenas de ZIPs sem cabeçalho, em Latin-1);
- descobrir sozinha se o problema é dela ou se o site do órgão caiu.

O dados.gov.br reúne os conjuntos, mas a API nova pede token de conta gov.br, e o portal é um índice de links, não
um lugar para usar os dados. Esta spec traz um **catálogo de dados públicos dentro do programa**, focado em UX:
navegar por categorias, ver tudo o que importa sobre a fonte antes de usar, saber se o órgão está no ar e colocar
os dados no fluxo com um clique, sem configurar API.

**Primeira camada apenas**: fontes abertas que não pedem conta, token ou chave. A camada com token (API do
dados.gov.br, Portal da Transparência) fica para depois.

Premissas:

- **Direto na fonte, sem intermediário.** O programa lê os catálogos e os dados dos próprios órgãos. Nada passa por
  servidor nosso, pelo GitHub ou por atualização do programa. Se um órgão sai do ar, só as fontes dele ficam
  indisponíveis.
- **Rede só quando faz sentido** (constituição 1.8.0): com o catálogo aberto, ao atualizar o catálogo e quando um
  fluxo executa uma fonte do catálogo. Fora disso, nenhum acesso.
- **Honestidade sobre a situação.** "No ar", "Lenta" e "Fora do ar" refletem o que este computador conferiu, com a
  hora da conferência. Nunca um selo verde sem conferir.

## Histórias de usuário

- Como analista financeiro, quero colocar a Selic diária dos últimos 15 anos no fluxo sem saber o que é SGS nem
  que a consulta precisa ser dividida em janelas de 10 anos.
- Como analista comercial, quero corrigir os valores de vendas pelo IPCA com um clique.
- Como quem cruza dados por município, quero juntar a minha planilha com a tabela de municípios do IBGE mesmo
  quando o nome vem sem acento ou o código vem com 6 dígitos.
- Como quem precisa do cadastro de empresas, quero saber o tamanho antes de baixar, escolher onde salvar,
  acompanhar o progresso, pausar e continuar depois, e no fim ter uma fonte pronta, com os nomes das colunas.
- Como qualquer pessoa, quero saber se o site do IBGE caiu antes de achar que o erro é meu.
- Como quem apresenta um dashboard, quero que a fonte dos dados apareça citada sem eu lembrar de escrever.

## Requisitos

### Entrada e navegação

| ID | Requisito |
|----|-----------|
| RF-4901 | **Onde fica.** A vista Dados ganha **Adicionar › Dados públicos do Brasil**, e a paleta de ferramentas ganha a ferramenta de entrada **Dados públicos** (que abre o mesmo catálogo). O catálogo abre num painel grande, sobre a vista atual, e fecha com Esc. |
| RF-4902 | **Menu de categorias com ícones**, à esquerda: Destaques, Favoritos, Recentes, e as categorias **Economia e juros**, **Preços e inflação**, **Câmbio**, **Território**, **População e trabalho**, **Empresas (CNPJ)**, **Calendário**, **Contas públicas** e **Comércio exterior**. Cada categoria mostra a quantidade de fontes e, ao lado, o ponto de situação pior entre os órgãos dela. |
| RF-4903 | **Cartões das fontes.** Cada fonte aparece como cartão: ícone da categoria, nome em português simples ("Taxa Selic diária"), órgão ("Banco Central do Brasil"), resumo de uma linha, periodicidade, **última atualização na fonte** ("atualizada em 21/11/2026") e o selo de situação do órgão. Fontes indisponíveis continuam visíveis, esmaecidas, com o motivo. |
| RF-4904 | **Busca no topo**, sempre visível, em todas as categorias: procura no nome, no órgão, no resumo, nas palavras-chave e no código ("432", "1705"), sem diferenciar acento nem maiúsculas. Os resultados mostram primeiro os destaques (RF-4931) e depois o catálogo completo dos órgãos (RF-4932), com o filtro por órgão e por periodicidade. A busca funciona sem internet, sobre o último catálogo lido (RF-4934). |
| RF-4905 | **Favoritos e recentes.** A estrela no cartão marca a fonte como favorita. Recentes guarda as 20 últimas fontes adicionadas. Os dois ficam neste computador, na pasta de dados, e não vão para o fluxo nem para o espaço da equipe. |

### Detalhe da fonte: o máximo de informação antes de usar

| ID | Requisito |
|----|-----------|
| RF-4911 | **Página da fonte.** Clicar no cartão abre o detalhe ao lado da lista, com: nome e descrição; órgão com o link da página oficial; **período coberto** (primeiro e último dado); **periodicidade** (diária, mensal, trimestral, anual) e **granularidade** (Brasil, estados, municípios); **última atualização na fonte** e próxima prevista quando o órgão informa; **unidade** ("% ao ano", "R$ por US$", "pessoas"); tamanho aproximado do resultado para o período escolhido; licença e citação. |
| RF-4912 | **Colunas, em português.** O detalhe lista as colunas que a fonte entrega, com nome, tipo e uma frase do que significa ("**valor** — taxa Selic em % ao ano, definida pelo Copom"). Esse **dicionário de colunas** acompanha a fonte: aparece também no Perfil da caixa e na dica da coluna no resultado. |
| RF-4913 | **Prévia de verdade.** O detalhe mostra as últimas 10 linhas lidas na hora, com o mesmo visual da prévia da vista Dados. Sem internet, mostra a última leitura guardada com a data ("prévia de 20/11/2026 14:02"); sem nenhuma leitura, diz "sem prévia: o órgão está fora do ar". |
| RF-4914 | **Escolhas antes de adicionar**, só as que a fonte precisa e com valores prontos: período (padrão: os últimos 5 anos; atalhos "último ano", "desde 2000", "tudo"), localidade (Brasil, estados ou municípios, quando a fonte tem), variável e moeda quando houver. O detalhe mostra a URL de cada consulta em **Avançado**, sem nada escondido. |
| RF-4915 | **Adicionar.** **Adicionar ao fluxo** coloca a caixa Dados públicos no canvas, já configurada. **Adicionar à vista Dados** guarda a fonte na pasta **Dados públicos**, como as outras fontes (situação, prévia, onde é usada). Com o órgão fora do ar, os dois botões ficam desabilitados com o motivo, exceto quando existe leitura guardada (RF-4925). |

### Situação dos órgãos

| ID | Requisito |
|----|-----------|
| RF-4921 | **Conferir ao abrir.** Ao abrir o catálogo, o programa confere, em paralelo e com tempo curto (até 5 s), cada serviço de que as fontes dependem (SGS, Olinda e dados abertos do Banco Central; API de serviço de dados do IBGE; Ipeadata; Tesouro; Receita; Comex Stat). O painel abre na hora e os selos chegam conforme as respostas. |
| RF-4922 | **Três situações e o porquê.** **No ar** (respondeu certo em até 2 s), **Lenta** (respondeu certo depois de 2 s) e **Fora do ar** (não respondeu, ou respondeu erro). O selo diz há quanto foi a conferência ("conferido há 3 min") e, fora do ar, **desde quando** este computador vê o problema ("fora do ar desde 14:20") e o motivo em palavras ("o site do IBGE não respondeu em 5 segundos"; "o site respondeu erro 503: serviço indisponível"). **Conferir de novo** refaz na hora. |
| RF-4923 | **Sem internet não é órgão fora do ar.** Quando nenhum serviço responde e o computador está sem rede, o painel mostra uma faixa única "Sem conexão com a internet agora" e marca os órgãos como "não conferido", sem acusar nenhum. |
| RF-4924 | **Histórico de disponibilidade.** O detalhe da fonte mostra uma barra com os últimos 30 dias de conferências feitas **neste computador** (verde, amarelo, vermelho, cinza para dias sem conferência), com a dica "o que este computador viu, não um dado oficial do órgão". |
| RF-4925 | **Fluxo com órgão fora do ar.** Ao executar, se o órgão não responde, a caixa usa a **última leitura guardada** da mesma consulta, avisa na caixa e no resultado ("Banco Central fora do ar: usando os dados lidos em 20/11/2026 14:02") e o fluxo segue. Sem leitura guardada, a caixa falha com a mensagem do motivo (princípio V). A opção **Exigir dados atuais** na caixa troca o aviso por falha. |

### Catálogo atualizado direto dos órgãos

| ID | Requisito |
|----|-----------|
| RF-4931 | **Destaques escolhidos.** O programa traz uma lista de fontes curadas (RF-4941), com nome simples, resumo, ícone, dicionário de colunas e escolhas prontas. A lista diz **como ler** cada fonte; os metadados que mudam (período, última atualização, colunas novas) vêm sempre da fonte. |
| RF-4932 | **Catálogo completo dos órgãos.** Além dos destaques, a busca alcança os catálogos inteiros que os órgãos publicam: as séries do SGS listadas no portal de dados abertos do Banco Central (3.579), as tabelas da API de agregados do IBGE (9.348), as séries do Ipeadata (4.141) e os conjuntos dos portais de dados abertos (RF-4936). Uma fonte do catálogo completo tem o mesmo detalhe (com o que o órgão informa) e entra no fluxo do mesmo jeito. O portal do Banco Central não lista todas as séries do SGS (faltam o IPCA 433, o INPC 188, o IGP-M 189 e o CDI 12, conferido em 2026-11-22): um código que não está em catálogo nenhum aparece como **Série N do SGS (ler direto)**, conferida ao abrir. |
| RF-4933 | **Atualizar o catálogo**, sem depender de nós. O botão lê de novo os catálogos de cada órgão, direto da fonte, e mostra o progresso por órgão ("IBGE: 3.412 tabelas · Ipeadata: lendo…"). O programa também atualiza sozinho, em segundo plano, ao abrir o catálogo quando a última leitura tem mais de 7 dias. O jeito de ler cada órgão fica no programa, com endereços alternativos quando o órgão tem; um órgão que falha mantém o catálogo anterior dele, marcado com a data, e os outros seguem atualizados. |
| RF-4934 | **Catálogo guardado.** O último catálogo lido fica na pasta de dados deste computador. O catálogo abre e a busca funciona sem internet, com a faixa "catálogo lido em 15/11/2026; sem conexão para conferir agora". |
| RF-4935 | **Dados novos disponíveis.** Quando a última atualização informada pelo órgão é mais nova que a última leitura de uma fonte usada num fluxo, a fonte na vista Dados e a caixa no canvas ganham o aviso discreto **Dados novos** ("o IBGE publicou o IPCA de outubro em 10/11"). A informação vem da conferência do catálogo (RF-4921), sem acesso extra. |

### Portais de dados abertos

Os portais oficiais que usam o mesmo sistema (CKAN) e respondem sem conta nem token entram no catálogo. Conferidos
em 2026-11-22: Banco Central (682 conjuntos além das séries do SGS, quase todos serviços OData do Olinda), Tesouro
Transparente (91), ANEEL (72), CVM (54), IBAMA (79), TSE (190), governos do RS (416), PE (47), MG (105), GO (451),
ES (512) e SC (111), e prefeituras de São Paulo (564), Recife (223), Fortaleza (640) e Porto Alegre (62).

| ID | Requisito |
|----|-----------|
| RF-4936 | **Navegar por portal.** O menu ganha **Portais**, com cada portal, o órgão, a quantidade de conjuntos e o selo de situação. Dentro do portal, os grupos e temas que o próprio portal publica viram filtros, e a busca do topo vale ali também. Um portal só entra no programa depois de verificado (resposta sem token, endereços dos arquivos conhecidos); cada um tem os seus endereços na lista fixa (RF-4981). |
| RF-4937 | **OData do Banco Central.** Os conjuntos do Banco Central servidos pelo Olinda (52 serviços) são lidos por um leitor de OData que usa a descrição do próprio serviço: colunas e tipos vêm do `$metadata`, e o título de cada consulta e a descrição dos parâmetros vêm do `/swagger`. Consultas **sem parâmetro** (a maioria) entram direto. Nas consultas **com parâmetro**, o serviço declara quase tudo como texto e cada um usa um formato de data (PTAX `MM-DD-AAAA`, Pix `AAAAMM` "a partir do mês", Saldos com fim de mês); testar formatos até um trazer dados não é confiável (o Pix aceita `09/2026` e devolve 2023). Por isso os parâmetros **conferidos um a um** (19 consultas na 0.9.6, com a checagem refeita por `scripts/conferir_catalogo.py`) viram seletor de período e lista de opções; os demais aparecem como **parâmetros não conferidos**, com o texto que o Banco Central publica, o link da documentação e a prévia obrigatória. A primeira página vai sem `$skip` (alguns serviços o recusam) e, se o serviço não paginar e passar de 50 mil linhas, a caixa pede um período menor em vez de entregar dados pela metade. O XML do serviço é lido sem DTD nem entidades. |
| RF-4938 | **Arquivos dos portais, com prévia e conferência.** CSV, XLSX, Parquet, JSON em forma de tabela e ZIP com CSV são lidos com a detecção da vista Dados (separador, codificação, cabeçalho). O **conteúdo** é conferido pelos primeiros bytes, porque o rótulo do portal pode mentir (o IBAMA publica ZIP rotulado como CSV e JSON): ZIP é aberto como ZIP, GZIP é descompactado, XLSX não é confundido com ZIP, e PDF ou página da web disfarçados dão erro claro. O CSV é lido como texto e tipado pela coluna inteira: **identificador fica texto com os zeros** (código com zero à esquerda ou com 12 dígitos ou mais: CNPJ, CEP, código do IBGE), número com milhar ou vírgula vira número pela regra do programa (spec 048), data só se todos os valores forem datas; a prévia diz quais colunas foram convertidas. Coluna toda vazia na prévia aceita o tipo que vier; valor fora do padrão depois das linhas da prévia ("N/D", "00/00/0000") fica vazio com aviso e contagem, como no Select, sem ser tratado como mudança do órgão. Antes de adicionar, a **prévia é obrigatória**: a pessoa vê as colunas e as primeiras linhas como ficaram e pode trocar separador, codificação e linha do cabeçalho. O formato aceito fica gravado na caixa; a cada execução, se o órgão mudar as colunas do arquivo, a caixa **não lê errado em silêncio**: para, mostra o que mudou ("saiu a coluna valor_pago; entrou valor_liquidado") e oferece **Aceitar o novo formato**. |
| RF-4939 | **Pronto ou Leitura automática.** O cartão e o detalhe dizem de que tipo é a fonte: **Pronto** (destaque conferido um a um, com dicionário de colunas) ou **Leitura automática: confira a prévia** (conjunto de portal ou OData). A leitura automática traz a descrição e as colunas que o portal informa, quando informa. |
| RF-4940 | **Tamanho, formato e endereço.** O tamanho vem do portal ou de um HEAD antes de ler. Até 200 MB, o arquivo é lido direto (com a leitura guardada de RF-4925). Acima disso, ou sem tamanho conhecido e passando do limite durante a leitura, vai pelo download com pasta escolhida (RF-4952..4954), com a fonte de pasta pronta no fim. ZIP é conferido antes de abrir (caminhos dentro da pasta, tamanho descompactado máximo). PDF, página HTML, formato que o programa não lê ou arquivo num endereço fora da lista aparecem com **Abrir no navegador** e o motivo ("arquivo PDF: o programa não lê tabelas de PDF de portais"; "arquivo em outro site, fora da lista oficial"). |

### O Brasil inteiro: estados, capitais e mapa (revisão de 2026-11-26)

Na primeira versão, a lista de portais ficou com 6 estados: o portal do Rio de Janeiro foi testado num endereço antigo
e o do estado de São Paulo nem foi testado. A revisão lista **todos** os estados e capitais, cada um com a situação
conferida e o motivo em palavras, e acrescenta a navegação pelo mapa do Brasil.

| ID | Requisito |
|----|-----------|
| RF-4949 | **Todos os estados.** Em Portais, **Estaduais** lista as 27 UFs, sempre, em ordem alfabética. Cada uma mostra uma situação, com a data da conferência: **Lê direto** (CKAN aberto: quantidade de conjuntos e o selo do RF-4922); **Bloqueia leitura automática** (o portal recusa programas; o programa se identifica com o próprio nome e não se passa por navegador, então oferece **Abrir no navegador**); **Outra plataforma** (o portal existe, mas não usa o CKAN — Drupal, Liferay, ArcGIS, WordPress — e o programa ainda não o lê: **Abrir no navegador**); **Fora do ar** (respondeu erro ou não respondeu na conferência; o programa confere de novo ao abrir); **Sem dados para ler** (portal vazio, ou conjuntos sem endereço de arquivo); **Sem portal encontrado** (nenhum portal de dados abertos do governo foi encontrado na conferência). Um portal que lê direto e passa a recusar o programa (página de "Acesso negado", erro 403) mostra o motivo em palavras, não "fora do ar". Toda situação diferente de Lê direto leva ao mapa do estado (RF-4958), onde as fontes federais do estado funcionam. |
| RF-4950 | **Só as capitais em Municipais.** **Municipais** lista as 27 capitais, com as mesmas situações do RF-4949; Brasília aponta para o portal do Distrito Federal. Prefeituras que não são capitais (na conferência, Mogi das Cruzes) ficam no mapa, dentro do estado delas. |
| RF-4958 | **Mapa do Brasil.** O menu ganha **Mapa do Brasil**, acima de Portais: os 27 estados desenhados, coloridos pela situação do portal estadual (lê direto, lê com ressalva, não lê), com o nome e a situação ao passar o mouse e a mesma lista em botões para quem usa o teclado. O desenho vem da malha oficial do IBGE, simplificado uma vez por um script do repositório e guardado no programa: abrir o mapa não usa internet. Clicar num estado abre o painel do estado: o portal estadual e a capital, com a situação e **Ver conjuntos**; as outras prefeituras com portal; **Dados do estado** nas fontes federais (população e PIB do IBGE, receitas e despesas no Siconfi, feriados, empresas do CNPJ do estado), já filtrados pela UF; e **Buscar um município** do estado, sobre a lista de municípios do IBGE guardada. Escolher um município mostra as fontes federais filtradas por ele (população, PIB, Siconfi, feriados e dias úteis; empresas do CNPJ quando a pessoa já baixou o CNPJ). Nada é lido até a pessoa escolher a fonte, como no resto do catálogo. |
| RF-4959 | **Atualizar sem atrapalhar.** Enquanto o catálogo é lido de novo (RF-4933), a tela não é redesenhada inteira: a rolagem da lista e do menu, o foco e o texto da busca ficam onde estão. Uma barra fina no topo mostra o progresso ("12 de 41 catálogos lidos") e cada órgão ganha a contagem e o selo no lugar, assim que termina; quem falhou mostra o motivo. O catálogo anterior continua navegável e buscável durante a leitura. A atualização segue com o catálogo fechado, e reabrir mostra o progresso. No fim, a lista e as contagens se atualizam no lugar, sem pular a rolagem. |
| RF-4965 | **A busca acha lugares.** A busca do topo procura também os 27 estados e os 5.570 municípios do IBGE (sem diferenciar acento nem maiúsculas: "sao jose dos campos", "juiz de fora"). Cada lugar vem num cartão próprio, antes das fontes, com a UF e o que há nele ("Juiz de Fora (MG) · dados do município"; "Bahia · portal do estado e dados federais"), e clicar abre o mesmo painel do mapa (RF-4958). Nomes repetidos em estados diferentes ("Bom Jesus") aparecem um por estado. A lista de municípios é a guardada do IBGE: a busca funciona sem internet. |
| RF-4966 | **Demais municípios no menu.** Em **Municipais**, depois das 27 capitais, o item **Demais municípios** abre uma lista com busca, agrupada por estado, com as prefeituras que têm portal próprio no topo (na conferência, Mogi das Cruzes). Clicar num município abre o mesmo painel do mapa. Os três caminhos — mapa, busca e menu — levam ao mesmo painel, e nada é lido da internet até a pessoa escolher uma fonte. |
| RF-4964 | **Conferência dos portais de novo.** `scripts/conferir_catalogo.py` testa, de verdade, os 27 estados, as 27 capitais e as prefeituras do mapa, com o mesmo cliente e a mesma identificação do programa, e diz o que mudou em relação à situação gravada no programa (um portal que voltou, mudou de endereço ou passou a bloquear). |

### Fontes de partida

| ID | Requisito |
|----|-----------|
| RF-4941 | **Destaques da 0.9.6**, por categoria (a lista final é a que passar na verificação de endereços, T01): **Economia e juros**: Selic meta e Selic diária, CDI, expectativas do mercado (Focus). **Preços e inflação**: IPCA, INPC, IGP-M (com a variação mensal e o índice acumulado). **Câmbio**: PTAX de compra e venda do dólar e das principais moedas, por dia. **Território**: regiões, estados e municípios do IBGE (com códigos, nomes, UF e região). **População e trabalho**: população estimada por município, taxa de desocupação (PNAD Contínua), PIB dos municípios. **Empresas (CNPJ)**: cadastro de empresas, estabelecimentos e sócios da Receita (RF-4951). **Calendário**: feriados (nacionais, estaduais, das capitais e bancários) e dias úteis por local (RF-4944..4948). **Contas públicas**: preços e taxas do Tesouro Direto; receitas e despesas de estados e municípios (Siconfi). **Comércio exterior**: exportações e importações por produto, país e UF (Comex Stat). E **Ipeadata**: qualquer série, pela busca. |
| RF-4942 | **Formato pronto para usar.** Toda fonte entrega uma tabela larga e tipada: data como data (o primeiro dia do mês para série mensal, com a coluna `periodo` em texto "2026-10" junto), valores como número, códigos do IBGE como texto de 7 dígitos (municípios) ou 2 dígitos (UF). Sem colunas aninhadas nem JSON. |
| RF-4943 | **As regras escondidas ficam por conta do programa.** O período longo do SGS é dividido em consultas de até 10 anos e juntado; consultas grandes do IBGE são divididas por localidade; a paginação de cada órgão é seguida; valores marcados pelo órgão como sem dado ("..", "-", "X") viram vazio, com a contagem no aviso da caixa. |

### Feriados e dias úteis

Não existe base oficial consultável de feriados estaduais e municipais: cada um está numa lei estadual ou municipal
(até 4 feriados religiosos por município, Lei 9.093/1995). Por isso a base de feriados combina o que se calcula, o
que se lê da fonte, o que vem no programa e o que a pessoa mantém, e **a pessoa sempre pode corrigir**, sem esperar
uma versão nova do programa.

| ID | Requisito |
|----|-----------|
| RF-4944 | **Uma base, quatro origens.** A fonte **Feriados** entrega `data`, `nome`, `tipo` (nacional, estadual, municipal, bancário, ponto facultativo), `abrangencia` (Brasil, UF ou código do município), `lei` e `origem`. Origens: **calculado** (nacionais fixos e móveis pela Páscoa, sem internet); **ANBIMA** (feriados bancários, lidos da fonte como as outras fontes do catálogo); **do programa** (tabela embutida com os feriados dos 27 estados e das capitais, cada um com a lei e o início da vigência, e a data da última revisão); **meus** (RF-4945). |
| RF-4945 | **Editar a base.** **Editar feriados…**, no detalhe da fonte e na caixa, abre a tabela do local escolhido. A pessoa **inclui** um feriado (municipal, recesso da empresa, ponte), **corrige** um do programa (data, nome, tipo) ou marca **Não vale mais** (com a data a partir da qual deixou de valer). Feriado fixo vale todo ano; móvel é dado como "N dias depois da Páscoa"; também aceita data única. Nada do programa é apagado: a edição fica por cima e **Restaurar o do programa** desfaz. |
| RF-4946 | **De onde veio cada linha.** A tabela e a caixa mostram a origem de cada feriado ("do programa, revisado em 11/2026"; "editado por você em 03/02/2027"; "ANBIMA, lido hoje") e o cartão diz o que a base cobre: "nacionais, bancários, estaduais e capitais completos; outros municípios: os que você cadastrar". A tabela do programa foi montada cruzando duas fontes (os calendários de 2026 dos 27 tribunais de justiça, com a norma que cada um cita, e a biblioteca `holidays`, que cita a legislação estadual); o feriado que só uma delas traz, ou em que elas divergem, aparece como **a confirmar**, com a fonte e a nota. |
| RF-4947 | **A sua edição vence a atualização.** Quando uma versão nova do programa traz a tabela revisada, as edições da pessoa continuam valendo. Se o programa mudou um feriado que a pessoa também editou, a tabela marca **O programa também mudou este feriado** com as duas versões lado a lado e **Manter o meu** / **Usar o do programa**. Feriado novo do programa entra sozinho, a menos que a pessoa já tenha um igual (mesma data e abrangência). |
| RF-4948 | **Dias úteis por local e na equipe.** A caixa Feriados e a fonte **Dias úteis** escolhem o local (Brasil, UF ou município) e o calendário (civil ou bancário) e juntam tudo o que vale ali, já com as edições. As edições ficam neste computador; num espaço da equipe, **Compartilhar com a equipe** leva a lista de edições como as definições da spec 048 (assinada, sem segredo), e os fluxos do espaço usam o calendário da equipe. |

### Arquivos grandes: CNPJ

| ID | Requisito |
|----|-----------|
| RF-4951 | **Antes de baixar, o tamanho.** A fonte CNPJ mostra o mês mais recente publicado pela Receita, a lista de partes (Empresas, Estabelecimentos, Sócios, Simples e as tabelas auxiliares: CNAE, municípios, naturezas jurídicas, países, qualificações e motivos) com o tamanho de cada uma e o total, e o espaço livre no disco escolhido. A pessoa marca as partes que quer (padrão: Empresas, Estabelecimentos e as auxiliares). |
| RF-4952 | **Onde salvar, perguntando.** **Baixar…** abre a escolha de pasta do sistema. O programa cria ali a subpasta `CNPJ-AAAA-MM` e avisa antes quando o espaço livre não basta. Nunca baixa para a pasta de um espaço da equipe nem para a pasta de dados do programa. |
| RF-4953 | **Download que não prende o programa.** O download roda em segundo plano, com uma barra na vista Dados (parte atual, total baixado, velocidade e tempo estimado), **Pausar**, **Continuar** e **Cancelar**. Fechar o programa pausa; ao abrir, a vista Dados oferece **Continuar o download do CNPJ**, retomando do ponto em que parou. Uma parte que falha tenta de novo sozinha três vezes antes de pedir ação. |
| RF-4954 | **Conferido e pronto.** Cada ZIP é conferido (tamanho anunciado e integridade do ZIP) e descompactado na mesma pasta com nomes fixos (`empresas_0.csv`, `estabelecimentos_3.csv`…); o ZIP é apagado depois, salvo se a pessoa marcar **Manter os ZIPs**. No fim, a vista Dados ganha a fonte de pasta **CNPJ AAAA-MM** já configurada: separador, Latin-1, sem cabeçalho, nomes das colunas do leiaute da Receita, tipos (datas `AAAAMMDD` como data, capital social como número) e o dicionário de colunas. |
| RF-4955 | **Leiaute conferido.** O programa conhece o leiaute publicado pela Receita. Se a quantidade de colunas de um arquivo não bate com o leiaute, a fonte avisa ("a Receita mudou o leiaute de Estabelecimentos: 31 colunas, esperadas 30") e entrega as colunas com nomes genéricos, sem adivinhar. |
| RF-4957 | **Filtro na leitura.** Estabelecimentos inteiro passa de 20 GB de texto e não cabe na memória da maioria dos computadores. A fonte de pasta do CNPJ tem **Filtro na leitura**: UF, município, CNAE principal e situação cadastral (Estabelecimentos), e **Só as empresas destes estabelecimentos** (Empresas, Sócios e Simples, pela fonte de Estabelecimentos do mesmo mês). Também **CNPJ**, vários de uma vez (Estabelecimentos, Empresas, Sócios e Simples): a pessoa cola a lista em qualquer formato (com ou sem pontuação, com os zeros à esquerda perdidos no Excel) e o programa converte para o formato da Receita, mostrando como entendeu cada linha: 14 dígitos (conferidos pelos dígitos verificadores) é um estabelecimento; 8 dígitos, a empresa inteira (matriz e filiais); o que não é CNPJ válido aparece marcado e não entra no filtro. Em Empresas, Sócios e Simples vale a raiz (8 dígitos). O programa lê os arquivos aos poucos e guarda só as linhas que passam; a prévia e o Perfil mostram o filtro em palavras. **Memória:** antes de ler, o programa estima o tamanho do resultado (sem filtro, pelo tamanho dos arquivos; com filtro, por um trecho lido e projetado) e, durante a leitura, arquivo por arquivo, mede o que já leu. Passando de **1/4 da memória** do computador (acima disso o Windows usa o arquivo de paginação no disco e tudo fica lento), a leitura para e pergunta **Parar** ou **Continuar assim mesmo**, com a estimativa e a sugestão de filtrar mais. A resposta vale só para aquela execução. |
| RF-4956 | **Mês novo.** Quando a Receita publica um mês mais novo que o baixado, a fonte CNPJ mostra **Dados novos: AAAA-MM disponível** e oferece baixar, na mesma pasta-mãe. |

### Usar os dados com um clique

| ID | Requisito |
|----|-----------|
| RF-4961 | **Receitas prontas.** No resultado de uma caixa, o menu da coluna oferece, quando cabe: **Corrigir valores pelo IPCA** (escolhe a coluna de valor, a coluna de data e o mês de referência; insere a fonte IPCA, a junção por mês e a fórmula, num grupo nomeado) e **Converter para dólar pela PTAX** (valor e data; usa a PTAX de venda do dia ou do último dia útil anterior, dito no aviso). As caixas inseridas são caixas comuns, que a pessoa pode abrir e mudar. |
| RF-4962 | **Juntar com municípios do IBGE.** O menu de uma coluna de texto que parece município ou UF oferece **Juntar com municípios do IBGE**. A junção aceita código de 7 dígitos, código de 6 dígitos (sem o dígito verificador) e nome com UF, sem diferenciar acento, maiúsculas e "d'"/"D'"; mostra antes quantas linhas casam e lista as que não casam, para a pessoa corrigir. |
| RF-4963 | **Citação automática.** Um fluxo com fonte pública cita a origem: no rodapé do dashboard e do HTML exportado ("Fonte: Banco Central do Brasil, SGS 432 — Taxa Selic; IBGE, tabela 6579. Lidos em 21/11/2026."), e no Perfil da caixa. A citação segue a licença de cada fonte (inclusive a atribuição da ODbL do Banco Central) e pode ser desligada no dashboard. |

### Equipe, agendamento e linha de comando

| ID | Requisito |
|----|-----------|
| RF-4971 | **Funciona igual em todo lugar.** A caixa Dados públicos guarda no fluxo só a referência da fonte e as escolhas (sem endereço montado, sem dados). O fluxo roda no agendamento, na linha de comando e no espaço da equipe sem configurar nada, porque não há segredo. |
| RF-4972 | **CNPJ é deste computador.** Num fluxo compartilhado, a fonte CNPJ aponta para a pasta de quem baixou; para o colega, ela aparece em **Faltam neste computador** com **Baixar os dados do CNPJ aqui…**, que abre o mesmo download (RF-4951). |
| RF-4973 | **Leituras guardadas não vão para lugar nenhum.** As últimas leituras (RF-4925), o catálogo (RF-4934) e o histórico de situação (RF-4924) ficam na pasta de dados deste computador; nunca no fluxo nem na pasta do espaço. |

### Segurança

| ID | Requisito |
|----|-----------|
| RF-4981 | **Só endereços oficiais, só leitura.** O programa acessa apenas uma lista fixa de endereços dos órgãos, embutida no código, por HTTPS e só com métodos de leitura: GET, HEAD e, para listar a pasta do CNPJ, PROPFIND (WebDAV). Única exceção, decidida em 2026-11-22: a consulta geral do Comex Stat só existe por POST, então o POST é aceito **só nesse endereço exato**, com o corpo montado pelo programa apenas com a consulta (fluxo, período, filtros, detalhes e métricas de listas fechadas); um teste garante que nenhum outro endereço aceita POST e que a consulta não segue redirecionamento. Redirecionamento para fora da lista é recusado. Nada é enviado além da própria consulta (código da série, período, localidade). |
| RF-4982 | **Limites.** Respostas de metadados e de séries têm tamanho máximo; o ZIP é conferido antes de descompactar (caminhos dentro da pasta, tamanho descompactado máximo, nomes trocados pelos fixos); o download grava só na pasta escolhida. |
| RF-4983 | **Sem rede fora de hora.** Sem catálogo aberto e sem fluxo executando fonte do catálogo, nenhum acesso à rede. Um teste automatizado garante que abrir o programa, a vista Dados e um fluxo sem fonte pública não faz nenhuma requisição externa. |

### Correção: zeros à esquerda na leitura de CSV (vista Dados)

Achado durante a T04d e incluído na 0.9.6 a pedido do usuário ("é uma correção mega importante"): o leitor de CSV
decide os tipos pelas primeiras linhas e transformava "0012" em 12, sem aviso. Em dados de empresa e de governo isso
estraga justamente os identificadores (CNPJ, CEP, código de cliente, matrícula), e depois de lido não há como
recuperar o zero.

| ID | Requisito |
|----|-----------|
| RF-4995 | **Identificador fica texto, com os zeros.** Toda coluna que a amostra diz ser inteira é lida como texto e conferida **no arquivo inteiro** (não só nas linhas da amostra): se algum valor tem zero à esquerda ou 12 dígitos ou mais, a coluna fica texto; senão, vira inteiro como sempre foi. Vale para o Input Data, a prévia da vista Dados e a pasta de arquivos (que junta texto e inteiro como texto, sem perder nada). Números com decimal, datas e o resto da leitura não mudam. |
| RF-4996 | **A caixa diz.** O Input Data mostra o aviso "Lida(s) como texto para manter os zeros à esquerda e os códigos longos: codigo (ex.: 0012)", com um exemplo real. Num fluxo que já existia, uma fórmula ou junção que contava com a coluna numérica passa a acusar o tipo, e o aviso na caixa de origem explica por quê. |
| RF-4997 | **O SQL acompanha.** O código SQL gerado (spec 020/041) lê os tipos da leitura do motor e força no DuckDB os que divergem: a coluna protegida sai como VARCHAR também no SQL (testes de paridade com CNPJ, CEP e zero só depois da amostra). |

### Documentação

| ID | Requisito |
|----|-----------|
| RF-4991 | Guia e Manual com o capítulo **Dados públicos do Brasil** (navegar, situação, detalhe, adicionar, receitas, junção com municípios, CNPJ passo a passo, citação, sem internet), prints das duas marcas, README e `contexto-ia.md` com a caixa Dados públicos. O capítulo Escopo e limitações diz o que fica de fora (abaixo). |

## Verificação dos endereços (T01, 2026-11-22)

Todos os endereços foram chamados de verdade por `scripts/conferir_catalogo.py`. Todos os destaques passaram; nenhum
pede conta, token ou chave.

| Serviço | Catálogo | Dados | Observações |
|---|---|---|---|
| BCB SGS | portal de dados abertos (CKAN): 4.261 conjuntos, 3.579 com `codigo_sgs`, com periodicidade, unidade, início e fim, licença ODbL | `api.bcb.gov.br/dados/serie/bcdata.sgs.{código}/dados` | Sem período: erro 406 com a regra dos 10 anos. A Selic meta (432) traz datas futuras (a meta vale até a próxima reunião do Copom): por padrão a caixa corta em hoje, com a opção de incluir. |
| BCB Olinda | `Moedas` (PTAX) | PTAX por moeda e período; Expectativas (Focus) | Focus levou 3,3 s na primeira chamada: a sonda usa uma consulta pequena da PTAX. O Olinda recusa (400) o espaço escrito como "+": a consulta OData vai com `%20`. |
| IBGE | `/api/v3/agregados`: 70 pesquisas, 9.348 tabelas (1,9 MB); `metadados` com periodicidade (início e fim), níveis territoriais e variáveis; `periodos` com a data de modificação | variáveis por período e localidade; localidades v1 | IPCA é a tabela 1737 (número-índice: variável 2266); população estimada 6579; desocupação 4099; PIB dos municípios 5938. |
| Ipeadata | `/api/odata4/Metadados` por HTTPS: 4.141 séries (7,9 MB), com fonte, periodicidade, unidade, última atualização (`SERATUALIZACAO`) e situação | `ValoresSerie(SERCODIGO='…')` | — |
| Tesouro | portal Tesouro Transparente (CKAN), com data de atualização e tamanho | CSV de preços e taxas do Tesouro Direto (14,7 MB) | ODbL. |
| Siconfi | `entes` (5.598 entes, com código do IBGE, esfera e população) | `dca`, `rreo`, `rgf` com `an_exercicio`, `id_ente`, `nr_periodo`, `co_tipo_demonstrativo`, `no_anexo`, `in_periodicidade`, `co_poder` | Paginação Oracle ORDS (`items`, `hasMore`, 5.000 por página, `offset`). A documentação oficial não abre; os parâmetros foram conferidos com São Paulo (DCA 2024: 3.240 linhas). `anexos-relatorios` não responde em 30 s: não é usado. |
| Comex Stat | `general/dates/updated` (último mês publicado), `general/details`, `general/metrics`, `tables/uf` | consulta geral **só por POST** (RF-4981) | A UF tem código próprio (SP = 41, não 35), lido de `tables/uf`. Valores vêm como texto. Frete, seguro e CIF só na importação. |
| Receita (CNPJ) | Nextcloud oficial `arquivos.receitafederal.gov.br`, link público de compartilhamento, listagem WebDAV (PROPFIND) com tamanho e data de cada arquivo; meses de 2023-05 a 2026-11 | ZIPs por parte; o mês 2026-11 tem 37 arquivos e 7,87 GB | Aceita Range (206): o download retoma. O endereço antigo `dadosabertos.rfb.gov.br` não responde mais. Existem dois links públicos para a mesma pasta: um é o principal, o outro o alternativo. |
| ANBIMA | — | planilha de feriados nacionais (`.xls`), de 2001 a 2099 | Lida pelo `fastexcel`, que o programa já usa; linhas vazias e notas no fim são descartadas. |

Portais CKAN, conferidos em 2026-11-22 (`package_search` sem token):

| Portal | Conjuntos | Onde ficam os arquivos | Observações |
|---|---|---|---|
| Banco Central | 682 (sem as séries SGS) | `olinda.bcb.gov.br` (OData) | Formato uniforme: leitor de OData (RF-4937). |
| Tesouro Transparente | 91 | `www.tesourotransparente.gov.br` | CSV e XLSX; mediana de 2 MB, 19 arquivos acima de 200 MB. |
| ANEEL | 72 | `dadosabertos.aneel.gov.br` | Lento (até 22 s para 200 conjuntos): a sonda usa `rows=0`. Tem Parquet. |
| CVM | 54 | `dados.cvm.gov.br` | Quase tudo em ZIP com CSV. |
| IBAMA | 79 | `dadosabertos.ibama.gov.br` e o armazenamento oficial do IBAMA em `stibamadadosabertosprd.blob.core.windows.net` | O endereço do armazenamento entra na lista exato, por ser onde o portal oficial publica ~65% dos arquivos. |
| TSE | 190 | `cdn.tse.jus.br` | Muitos ZIPs grandes (download com pasta). |
| Governo do RS | 416 | `dados.rs.gov.br`, `data.rs.gov.br` | Lento (20 s para 200 conjuntos). Alguns arquivos 7z: só link. |
| Governo de PE | 47 | `dados.pe.gov.br` | Poucos conjuntos com milhares de arquivos cada. |
| Governo de MG | 105 | `dados.mg.gov.br` | — |
| Governo de GO | 451 | `dadosabertos.go.gov.br` | — |
| Governo do ES | 512 | `dados.es.gov.br` | Alguns arquivos em outros sites do estado: só link. |
| Governo de SC | 111 | `dados.sc.gov.br` | Voltou a responder na segunda verificação, mas corta respostas acima de ~130 KB: lista em páginas de 5 conjuntos; página cortada é lida um conjunto por vez, e o que não vem é contado no aviso do portal (1 conjunto em 2026-11-22). Muitos arquivos em PDF ou por http: só link. |
| Prefeitura de São Paulo | 564 | `dados.prefeitura.sp.gov.br` | CSV, XLSX e ODS (ODS: só link). |
| Prefeitura do Recife | 223 | `dados.recife.pe.gov.br` | — |
| Prefeitura de Fortaleza | 640 | `dados.fortaleza.ce.gov.br` | Alguns recursos com endereço inválido: aparecem como indisponíveis. |
| Prefeitura de Porto Alegre | 62 | `dadosabertos.poa.br` | — |

Verificados e **não disponíveis** agora (ficam no script de conferência, que volta a testar e avisa quando um volta):
ANTT (não respondeu em 45 s), Bahia, Rio de Janeiro e Natal (sem conexão), Paraná, Curitiba e Saúde
(sem a API do CKAN aberta), Paraíba (recursos sem endereço), dados.gov.br (pede token: segunda camada).

## Verificação dos estados e das capitais (revisão, 2026-11-26)

Testados com o cliente do programa (certificados do Windows, identificação "Desata/0.9.6 (catalogo de dados
publicos)"), com os endereços prováveis de cada governo e a busca na web pelos portais oficiais.

| UF | Portal | Situação |
|----|--------|----------|
| AC | `dados.ac.gov.br` | Lê direto (20 conjuntos) |
| AL | `dados.al.gov.br/catalogo` | Lê direto (398); arquivos também em `portal.dados.al.gov.br` |
| AP | — | Sem portal encontrado |
| AM | — | Sem portal encontrado |
| BA | `dados.ba.gov.br` | Lê direto (22). O servidor não envia o certificado intermediário: num computador que ainda não o tem, a leitura falha com o motivo (o programa não desliga a conferência do certificado) |
| CE | `dados.ce.gov.br` | Bloqueia leitura automática (403) |
| DF | `dados.df.gov.br` | Outra plataforma (Liferay) |
| ES | `dados.es.gov.br` | Lê direto (512) |
| GO | `dadosabertos.go.gov.br` | Lê direto (451) quando o portal aceita; na revisão, recusou a identificação do programa ("Acesso negado"), e o programa mostra esse motivo |
| MA | — | Sem portal encontrado |
| MT | `dadosabertos.mt.gov.br` | Lê direto (26) |
| MS | — | Sem portal encontrado |
| MG | `dados.mg.gov.br` | Lê direto (105) |
| PA | `dados.pa.gov.br` | Fora do ar (não respondeu em 20 s) |
| PB | `dados.pb.gov.br` | Sem dados para ler (7 conjuntos, nenhum com endereço de arquivo) |
| PR | `www.dados.pr.gov.br` | Outra plataforma (Drupal) |
| PE | `dados.pe.gov.br` | Lê direto (47) |
| PI | `dados.pi.gov.br` | Outra plataforma (WordPress, Observatório de Dados) |
| RJ | `dadosabertos.rj.gov.br` | Lê direto (1.155); arquivos também em `www.ispdados.rj.gov.br` |
| RN | `dados.rn.gov.br` | Sem dados para ler (portal vazio) |
| RS | `dados.rs.gov.br` | Lê direto (416) |
| RO | `dados.ro.gov.br` | Fora do ar (erro 500) |
| RR | — | Sem portal encontrado |
| SC | `dados.sc.gov.br` | Lê direto (111) |
| SP | `dadosabertos.sp.gov.br` | Lê direto (456); arquivos também no Infosiga e no armazenamento oficial do Detran, na Seade, no DER e na Fazenda |
| SE | — | Sem portal encontrado |
| TO | — | Sem portal encontrado |

| Capital | Portal | Situação |
|---------|--------|----------|
| Rio Branco, Maceió, Macapá, Manaus, São Luís, Cuiabá, Campo Grande, Belém, João Pessoa, Boa Vista, Florianópolis, Aracaju, Palmas | — | Sem portal encontrado |
| Salvador | `dados.salvador.ba.gov.br` | Outra plataforma (ArcGIS) |
| Fortaleza | `dados.fortaleza.ce.gov.br` | Lê direto (640) |
| Brasília | o portal do DF | Outra plataforma |
| Vitória | `dadosabertos.vitoria.es.gov.br` | Bloqueia leitura automática ("Request Rejected") |
| Goiânia | `dadosabertos.goiania.go.gov.br` | Lê direto (29); arquivos em `www4.goiania.go.gov.br` |
| Belo Horizonte | `dados.pbh.gov.br` | Lê direto (615); arquivos em `ckan.pbh.gov.br` |
| Curitiba | `dadosabertos.curitiba.pr.gov.br` | Outra plataforma |
| Recife | `dados.recife.pe.gov.br` | Lê direto (223) |
| Teresina | `dados.teresina.pi.gov.br` | Outra plataforma (OpenMetadata) |
| Rio de Janeiro | `www.data.rio` | Outra plataforma (ArcGIS Hub) |
| Natal | `dados.natal.br` | Fora do ar (não respondeu em 20 s) |
| Porto Alegre | `dadosabertos.poa.br` | Lê direto (62) |
| Porto Velho | `dados.portovelho.ro.gov.br` | Fora do ar (erro 502) |
| São Paulo | `dados.prefeitura.sp.gov.br` | Lê direto (584) |

Prefeituras que não são capitais: das 120 cidades grandes testadas, só **Mogi das Cruzes** (`dados.mogidascruzes.sp.gov.br`,
88 conjuntos) tem CKAN aberto. Por isso o mapa traz, para qualquer município, as fontes federais filtradas por ele.

## Como fica na tela

```
┌ Dados públicos do Brasil ──────────────────────────────────────────── [Atualizar o catálogo] ✕ ┐
│ 🔍 Buscar: selic, ipca, municípios, 432…                    catálogo lido hoje 09:12           │
├────────────────────────┬────────────────────────────────┬──────────────────────────────────────┤
│ ★ Destaques         12 │ ┌────────────────────────────┐ │ Taxa Selic diária          ☆ Favorita│
│ ☆ Favoritos          3 │ │ % Taxa Selic diária        │ │ Banco Central do Brasil ↗  ● No ar   │
│ ⟲ Recentes           5 │ │ Banco Central · diária     │ │ conferido há 1 min · Conferir de novo│
│ ─────────────────────  │ │ atualizada em 21/11/2026 ● │ │ ▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮ 30 dias │
│ % Economia e juros ● 4 │ └────────────────────────────┘ │ Período: 04/06/1986 a 21/11/2026     │
│ ↗ Preços e inflação● 3 │ ┌────────────────────────────┐ │ Diária · Brasil · % ao dia           │
│ $ Câmbio           ● 1 │ │ % CDI                      │ │ Colunas                              │
│ ⌖ Território       ● 3 │ │ Banco Central · diária     │ │  data   data   dia da taxa           │
│ 👥 População       ◐ 3 │ └────────────────────────────┘ │  valor  número taxa em % ao dia      │
│ 🏢 Empresas (CNPJ) ● 1 │                                │ Prévia (últimas 10 linhas)  …        │
│ 📅 Calendário        2 │                                │ Período [Últimos 5 anos ▾]           │
│ 🏛 Contas públicas ○ 2 │                                │ Licença ODbL · Citação  · Avançado ▸ │
│ 🚢 Comércio exterior●1 │                                │ [Adicionar ao fluxo] [À vista Dados] │
└────────────────────────┴────────────────────────────────┴──────────────────────────────────────┘
  ● No ar   ◐ Lenta   ○ Fora do ar desde 14:20 (o site do Tesouro não respondeu em 5 segundos)
```

## Critérios de aceite

- CA-01: Da vista Dados, em até 3 cliques, a Selic diária dos últimos 15 anos está no fluxo e executa (três
  consultas de 10 anos ou menos, juntadas, sem linha repetida).
- CA-02: Com um serviço simulado fora do ar, o selo mostra "Fora do ar desde HH:MM" com o motivo, os outros órgãos
  seguem "No ar", e o fluxo que usa a fonte desse órgão executa com a última leitura e o aviso com a data.
- CA-03: Sem rede, o catálogo abre, a busca encontra "ipca" e "1705", e a faixa diz "sem conexão"; nenhum órgão é
  acusado de fora do ar.
- CA-04: Atualizar o catálogo com um órgão falhando mantém o catálogo anterior desse órgão, com a data, e atualiza
  os outros.
- CA-05: O download do CNPJ (servidor simulado) mostra tamanho e espaço livre, grava só na pasta escolhida, pausa,
  retoma do ponto (Range) depois de fechar o programa, recusa ZIP com caminho para fora da pasta e termina com a
  fonte de pasta pronta e as colunas com nome.
- CA-06: "Corrigir valores pelo IPCA" sobre uma tabela de vendas mensais dá o mesmo valor que o cálculo à mão com
  o índice do mês; "Juntar com municípios do IBGE" casa "Sao Paulo/SP", "355030" e "3550308" com o mesmo município.
- CA-10: Os dias úteis de um município que não é capital (por exemplo, Campinas), em 2027, descontam os nacionais,
  os estaduais da tabela do programa (o 9 de julho) e os municipais que a pessoa cadastrou; marcar
  um feriado do programa como "Não vale mais" e incluir um recesso muda o resultado na hora; com uma tabela do
  programa revisada que muda o mesmo feriado, a edição continua valendo e aparece "O programa também mudou este
  feriado".
- CA-11: Uma consulta OData conferida com parâmetros (cotação de moeda por período, saldos mensais) usa o período
  escolhido no formato certo e traz só datas do período; uma consulta sem parâmetros entra direto; uma consulta com
  parâmetros não conferidos aparece como tal, com a prévia obrigatória; um serviço que recusa a paginação dá
  "escolha um período menor", nunca dados pela metade.
- CA-12: Um CSV de portal em Latin-1 com `;` e vírgula decimal aparece certo na prévia; depois que o órgão troca uma
  coluna, a execução para com "saiu a coluna X; entrou a coluna Y" e **Aceitar o novo formato** volta a executar.
  Um arquivo acima de 200 MB vai pelo download com pasta; um PDF e um arquivo em site fora da lista aparecem só
  com **Abrir no navegador** e o motivo; nenhum pedido sai para o site fora da lista.
- CA-13: Um CSV da pessoa com "0012" na linha 20.001 (depois da amostra) e um CNPJ que começa com zero chega ao
  fluxo com "0012" e o CNPJ inteiro, como texto, com o aviso na caixa; uma coluna de inteiros comuns continua
  inteira; o SQL gerado lê as mesmas colunas como texto.
- CA-14: Estabelecimentos com Filtro na leitura (uma UF e um CNAE) lê só as linhas que passam, sem carregar o
  arquivo inteiro; Empresas com Só as empresas destes estabelecimentos traz só os CNPJs básicos dessa leitura; um
  filtro de CNPJ com "00.000.000/0001-91", "191" e "12.345.678" acha o estabelecimento do Banco do Brasil e a
  empresa inteira; uma leitura estimada acima de 1/4 da memória para e pergunta, e Continuar assim mesmo lê tudo.
- CA-07: O dashboard e o HTML exportado de um fluxo com IPCA e Selic trazem a citação das duas fontes com a data.
- CA-08: Abrir o programa, a vista Dados e executar um fluxo sem fonte pública não faz nenhuma requisição externa
  (teste automatizado); o fluxo salvo com a caixa Dados públicos não contém URL montada nem dados.
- CA-09: A verificação manual `scripts/conferir_catalogo.py` lê, de verdade, um dado de cada fonte destaque e o
  catálogo de cada órgão, e mostra o tempo de cada um.
- CA-15: Em Portais, Estaduais lista as 27 UFs e Municipais as 27 capitais, cada uma com a situação e o motivo;
  São Paulo e Rio de Janeiro leem direto, com a quantidade de conjuntos.
- CA-16: Durante Atualizar o catálogo, a rolagem do menu e da lista não se mexe sozinha e dá para rolar e buscar; a
  barra mostra "N de M catálogos lidos" e cada órgão ganha a contagem no lugar.
- CA-17: No Mapa do Brasil, clicar em Minas Gerais mostra o portal do estado e o de Belo Horizonte; buscar
  "Juiz de Fora" e escolher População estimada coloca no fluxo a caixa já filtrada pelo código 3136702.
- CA-18: Abrir o Mapa do Brasil não faz nenhuma requisição externa (teste automatizado).
- CA-19: Buscar "campinas" mostra o cartão Campinas (SP) antes das fontes, e clicar abre o painel com a população
  e o PIB de Campinas; em Municipais › Demais municípios, Mogi das Cruzes aparece no topo de São Paulo.

## Fora do escopo

- Fontes que pedem conta, token ou chave (API do dados.gov.br, Portal da Transparência): segunda camada.
- Microdados enormes além do CNPJ (Censo, RAIS, DATASUS, INEP, TSE): o mecanismo de download desta spec serve de
  base, mas cada um vem numa spec própria.
- Malhas do IBGE como fonte de dados (mapas com as divisas para os visuais). O desenho simplificado dos estados
  serve só à navegação do catálogo (RF-4958).
- Banco de dados local de CNPJ (importar para DuckDB, consultar por CNPJ): a fonte de pasta já permite filtrar;
  um índice próprio fica para depois.
- Avisar fora do programa (notificação do Windows) sobre dados novos.
