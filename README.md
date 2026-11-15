# Desata

*Desate a complexidade. Conecte possibilidades.*

Plataforma visual de pipelines de dados: monte fluxos arrastando ferramentas
em um canvas, conecte entradas e saídas, execute e inspecione o resultado de
cada etapa. O motor é colunar (Polars + DuckDB + Apache Arrow) e roda
localmente.

- **Ingestão** de CSV, Excel (inclusive `.xlsb`), Parquet, JSON/JSON Lines e Arrow, com detecção
  automática de formato, encoding (UTF-8, Windows-1252…), delimitador e
  separador decimal — CSVs brasileiros (`;` e vírgula decimal) funcionam sem
  configuração. Em planilhas, a prévia mostra as **abas** como guias e permite
  **pular linhas e colunas** quando a tabela não começa em A1.
- **Manual dentro do programa** (`?` ou `F1`): o guia ao lado do trabalho, com busca, imagens no tema da tela,
  "Mostrar onde fica" e exemplos para experimentar. **Ctrl+K** acha ferramenta, ação, caixa, fonte ou capítulo.
- **Modo foco** (`F11`), painéis recolhidos em faixa e editor de fórmula em janela larga (**Abrir grande**).
- **Vista Dados**: a primeira tela reúne arquivos, pastas de arquivos, leitores de PDF, consultas, APIs, conexões e
  constantes, com situação, prévia, qualidade das colunas e o **mapa de onde cada fonte é usada** nos
  fluxos da biblioteca. Antes de excluir uma fonte em uso, a tela lista o que deixa de funcionar.
- **Organização das fontes**: pastas por assunto (arrastar, Ctrl+clique), nome de exibição sem quebrar
  os fluxos, descrição e responsável, fixadas no topo e filtros "Com problema" e "Sem uso".
- **Pasta de arquivos**: todos os arquivos de um padrão (`vendas_*.xlsx`) numa tabela só, que inclui
  sozinha os arquivos novos, ou cada arquivo como uma fonte separada. A pasta é lida onde está.
- **Leitor de PDF**: marque no próprio documento o valor ou a tabela e veja a coluna nascer na hora,
  com o valor convertido e o original ao lado. O Desata aprende onde achar o dado ("à direita de
  'Total líquido'"), testa nos outros PDFs da pasta e mostra o impacto de cada mudança com desfazer.
  Tabelas que vão até onde você marcou, com bordas e guias arrastáveis, em várias páginas, linhas quebradas,
  campos ambíguos (nenhum valor escolhido em silêncio),
  correção só num documento e "de onde veio" em um clique. Extrações salvas: reaproveitar, copiar, exportar,
  importar e excluir. Documentos um a um: tirar um PDF da fonte sem apagar o arquivo, trazer de volta e
  adicionar outros. O PDF é lido num processo separado, com tempo e memória limitados, sem executar
  conteúdo ativo. O exemplo traz três relatórios reais da Receita Federal com a extração pronta.
- **Vírgula ou ponto**: em Exibir → Números, os números aparecem como 1.234,56 ou 1,234.56 em toda
  a tela, no dashboard e no HTML exportado. O Output Data em CSV escolhe o próprio separador decimal.
- **Regex sem expressão regular**: marque o trecho num valor de verdade ("10/2026" em "NF 10/2026") e a caixa
  monta as peças ("2 dígitos, uma barra, 4 dígitos"), mostra onde achou em cada linha e deixa cada peça virar coluna.
  Peças prontas para data, CPF, CNPJ, CEP, e-mail, telefone e valor; a expressão fica no Avançado.
- **Datas do seu jeito**: escreva `07/08/2026`, `'2026-08-07'` ou `jul/26` numa fórmula e aparece "Você quis
  dizer 7 de agosto de 2026?", com a forma certa (`ToDate('2026-08-07')`) a um clique, sem trocar nada sozinho. Com
  hora também (`ToDateTime`), e ano com dois dígitos. O Filter básico ganha calendário (com hora opcional em data e
  hora) e compara data com data, nunca texto com texto.
- **Fluxo em outro computador**: o que falta aparece de cara (selo vermelho na aba Dados, seção "Faltam neste
  computador" e a caixa em vermelho), com a ação para resolver cada fonte. "Salvar com amostra dos dados" leva uma
  amostra de 100, 500 ou 1.000 linhas por fonte (5 MB no total), com as colunas pessoais já marcadas para mascarar e
  prévia mascarada. Onde a fonte não existe, o fluxo roda com a amostra, marcada em laranja na caixa e na vista Dados.
  Fonte que é arquivo vinculado ganha aviso para quem compartilha e para quem recebe (o caminho nunca vai no arquivo).
  Caminhos, senhas e conexões nunca vão no arquivo.
- **Constantes**: um valor com nome, escrito `[#nome]`, nas fórmulas, no Filter básico, no
  nome do arquivo do Output Data e nos parâmetros fixos de API. Do fluxo (vão no arquivo) ou
  compartilhadas (vista Dados). Mudar o valor refaz só as caixas que usam a constante.
- **Data Quality**: regras prontas (não vazio, sem duplicados, CPF, CNPJ alfanumérico, e-mail,
  faixa de número, data, lista de valores e fórmula livre), escolhidas por cartões. Saídas
  P (passou) e F (falhou, com `regra` e `motivo`), e selo no canvas com as falhas.
- **Abertura protegida**: um fluxo que veio de fora não executa nada até a pessoa conferir o
  que ele lê, calcula e grava e confiar.
- **Bancos de dados**: conexões com PostgreSQL, SQL Server e, por ODBC, Oracle, MySQL e ERPs
  (somente leitura).
  Na vista Dados, **consultas de banco** (uma tabela ou SQL livre, com prévia)
  ficam ao lado dos arquivos, e o mesmo **Input Data** lê qualquer uma dessas
  fontes. A senha fica no Gerenciador de Credenciais do Windows, nunca em
  arquivos do projeto.
- **APIs**: cadastre uma API na vista Dados (GET ou POST, JSON, CSV ou XML, com
  paginação e novas tentativas) e leia no Input Data. Token, chave, senha e OAuth 2
  ficam no cofre do sistema. API de endereço fixo vira tabela direto no Input Data; com
  variável (`{sigla}`), entra como **API Loop**: você escolhe a coluna que preenche
  cada variável, e ele chama uma vez por valor, juntando as respostas. O cadastro guarda
  o link da documentação da API e uma anotação do que faz cada parâmetro. A tabela pode
  ser a saída de outra API. O cadastro tem
  exemplos prontos e mostra a resposta ao lado da tabela, e o fluxo de demonstração
  consome a API pública do IBGE, só depois do clique em Executar.
- **Destinos à sua escolha**: o Output Data grava em qualquer pasta, e o fluxo
  pode ser salvo e aberto de qualquer pasta (*Salvar como…* / *Abrir arquivo…*).
- **Jira Cloud, só leitura**: conexão guiada com token de leitura, consulta sem escrever
  JQL, demandas, histórico e comentários como tabelas, atualização só do que mudou e retomada.
- **Replay analítico**: linha do tempo no dashboard, corrida de barras, bolhas, Sankey,
  destaques com critério, história em cenas, GIF por gráfico e HTML com tudo isso.
- **Lições guiadas** no Manual, cada uma num fluxo próprio.
- **43 ferramentas** na paleta, em 6 famílias: entrada/saída, preparação (com
  Text To Columns, Record ID, Running Total, Multi-Row Formula e Data Quality), combinação e transformação (Join
  com saídas L/J/R, Cross Tab, Transpose, Append Fields, Summarize, Union, SQL via
  DuckDB, Fuzzy Match), conferência e reúso (Reconcile, Compare Runs, Subflow), BI (Chart, KPI Card, Venn e Table)
  e Machine Learning (scikit-learn). Entradas sem fonte cadastrada: Text Input e Generate Rows.
- **Conferência**: Data Quality, Reconcile (linhas, somas e distintos entre duas tabelas) e
  Compare Runs (o que mudou desde a execução anterior) podem interromper o fluxo em vez de
  gravar um número errado; o Join avisa quando a chave repetida multiplica linhas.
- **Modelos de ML guardados**: o Model Trainer guarda cada versão do modelo em disco, e a
  biblioteca de modelos leva um modelo a qualquer fluxo (Model Input). O arquivo `.modelo`
  exporta e importa entre computadores sem pickle: nada dele é executado ao abrir.
- **Execução sem abrir o programa**: `prodata-cli.exe run <fluxo>` executa um fluxo salvo e
  termina com código 0 ou 1, para o Agendador do Windows; o programa mostra o comando pronto.
- **Ponto de cache** (como o "Cache and Run" do Alteryx): congela o resultado de
  uma caixa — inclusive em disco — e dispensa tudo o que vem antes dela até alguma
  caixa anterior mudar. Ideal para consultas a banco e arquivos grandes.
- **Seleção múltipla**: `Shift`/`Ctrl` + clique, `Shift` + arrastar (retângulo) e
  `Ctrl+A`; mover, alinhar, distribuir, agrupar numa etapa ou tirar
  dela, copiar e excluir várias caixas de uma vez.
- **Dados de cada porta**: clicar numa saída mostra o que sai; clicar numa
  entrada mostra o que chega por ela.
- **Execução incremental**: só recalcula as caixas cuja configuração, entradas ou
  arquivo de origem mudaram.
- **Perfil de dados** em toda saída: barra de qualidade (preenchido/vazio/nulo),
  histogramas e estatísticas por coluna.
- **Dashboard em canvas**: página de tamanho fixo (16:9, A4 ou altura livre) onde
  os visuais se arrastam e redimensionam com encaixe e guias; **Organizar** com
  layout automático e 5 layouts prontos; painel **Formato** (cores, rótulos,
  eixos, cartão); textos, imagens, logo e formas; **filtros na página**, sem executar
  o fluxo de novo; **imagem PNG** da página ou de um visual e **HTML** num arquivo só,
  que abre sem o programa e sem internet, com os filtros funcionando. O layout fica
  gravado no arquivo do fluxo.
- **Visuais**: colunas, barras, linhas, rosca, empilhado, agrupado, 100%, área,
  Pareto, funil, dispersão, Venn (2 conjuntos proporcionais ou 3), medidor, tabela
  com cores por faixa e big number com variação contra meta ou período anterior e
  minigráfico de tendência. Um painel de **gráficos e resumos** abaixo do canvas
  mostra os mesmos visuais e um gráfico automático de cada Summarize.
- **Exploração sem mexer no fluxo**: filtros por coluna na tabela de resultados
  (texto, número, data, nulos), com perfil recalculado e opção de virar uma caixa Filter.
- **Organização**: caixas de etapa com nome, descrição, cor e interruptor
  liga/desliga (desligada, as caixas de dentro não executam).
- **Edição rápida**: lixeira em cada caixa, copiar/recortar/colar caixas ou
  etapas inteiras (inclusive entre fluxos) e menu de botão direito com as ações
  mais comuns.
- **Abas**: vários fluxos abertos ao mesmo tempo, cada um com seu resultado e
  seu desfazer; as abas voltam ao reabrir o programa. Fechar uma aba ou a janela
  com alterações pergunta *Salvar / Não salvar / Cancelar*.
- **Editor de fórmulas**: cores por tipo (coluna, função, controle, operador
  lógico, comparação, texto, número), autocompletar de funções e colunas
  (`Ctrl+Espaço`), dica da assinatura da função e assistente com 82 funções
  documentadas (inclusive números e datas no padrão brasileiro, CPF/CNPJ,
  expressões regulares) e botões de operadores. Diferente é `!=` (`<>` também
  vale). A Formula cria colunas novas ou altera colunas existentes, e calcula
  entre colunas da mesma linha com `Average`, `Sum`, `Median`, `Mode`, `StdDev`, `Max` e `Min`.
- **Esquemas visuais** ("Como funciona") no Configurar das ferramentas: o antes e o depois
  com uma amostra dos seus dados, depois de executar.
- **Aba SQL**: o fluxo escrito em SQL do DuckDB, com um código por saída (só o
  que existe entre as entradas e ela) ou um código unificado de várias saídas,
  sem repetir etapas. Cada etapa é rodada e comparada com o resultado do fluxo:
  o estado da saída diz se o código deu o mesmo resultado, e caixas sem tradução
  ficam em vermelho. Copie ou baixe `.sql` ou `.zip` para o time de dados. O código também
  sai em Spark SQL e T-SQL (Microsoft Fabric), marcado como não conferido. Fontes de banco, API,
  Jira, pasta e PDF viram uma tabela de origem, com a ressalva de criá-la no destino. Regex e Generate
  Rows também têm tradução; Machine Learning, API Loop, Subflow, Fuzzy Match, Mask, Multi-Field Formula,
  Compare Runs, Reconcile e Estado por período ficam como "sem SQL".
- **Join como no Alteryx**: escolha se o J mantém as chaves dos dois lados, só
  da esquerda ou só da direita, e selecione, renomeie, converta e reordene as
  colunas do J sem precisar de um Select depois.
- **Summarize** com moda e desvio padrão, além de soma, média, mediana,
  contagens, mínimo, máximo e concatenação.
- **Excel por padrão** no Output Data: ligue várias tabelas na mesma caixa e cada
  uma vira uma planilha do arquivo, ou junte planilhas de caixas diferentes. Se o arquivo de saída já existe, o
  Desata pergunta ao executar: substituir, criar um novo (data e hora no nome)
  ou adicionar a planilha. Também grava num **modelo de Excel** já formatado, numa cópia.
- **Fontes que se atualizam**: *Vincular arquivo* lê a planilha original (pasta
  da rede, OneDrive) sem copiar, e a pasta de arquivos percebe arquivo novo, removido ou
  alterado; as mudanças são percebidas a cada execução e também invalidam o ponto de
  cache, que pode ainda renovar todo dia ou a cada hora (para bancos de dados).
- **Dashboard que responde ao clique**: faixa de filtros com valores à mostra e controle
  deslizante; clicar numa barra ou fatia filtra a página, também no HTML.
- **Multi-Row com receitas**: preencher para baixo, diferença, variação %, valor anterior,
  próximo valor e "mudou?", com esquema visual do antes e depois.
- **Fluxos recebidos sob controle**: fórmulas e a caixa SQL não acessam arquivos nem a
  internet, e a interface e o HTML exportado têm política de conteúdo.
- **Segurança**: rótulos de confidencialidade na exportação e no dashboard, com dica do que
  cada um faz, HTML com senha, registro local das exportações e destinos de API controlados: públicas livres,
  rede interna só com a lista da TI (`%ProgramData%\Desata\politica.json`).
- **Conectores e animações**: os fios levam a cor de uma família de ferramentas à
  outra, com seta na chegada. Ao executar, o dado corre pelo fio até a caixa da vez;
  com o programa parado, nada se move, e as animações respeitam a opção do Windows.
- **Interface ajustável**: painéis de ferramentas/configuração, resultados e
  gráficos podem ser arrastados para esquerda, direita ou embaixo, ou ocultados.
- **Aplicativo de desktop** para Windows: instalador `.exe` ou `.zip` portátil,
  sem exigir Python na máquina do usuário.
- **Marca configurável**: nome, cores, fontes e logo vêm de um pacote de marca (veja o fim deste
  arquivo).

## Início rápido

Requer [uv](https://docs.astral.sh/uv/) (instala o Python 3.14 se preciso).

```powershell
uv sync
uv run prodata
```

Abra http://127.0.0.1:8765. Na primeira execução são gerados datasets de
exemplo e o fluxo de demonstração *Pipeline 360° de clientes*.

Para executar um fluxo salvo sem abrir a interface: `uv run prodata run "Pipeline 360° de clientes"`
(`uv run prodata list` lista a biblioteca).

| Atalho | Ação |
|--------|------|
| `Ctrl+Enter` | Executar (com `Shift`: até a caixa selecionada) |
| `Ctrl+S` / `Ctrl+Shift+S` / `Ctrl+O` | Salvar / salvar como / abrir fluxo |
| `Ctrl+Z` / `Ctrl+Shift+Z` | Desfazer / refazer |
| `Ctrl+C` / `Ctrl+X` / `Ctrl+V` | Copiar / recortar / colar caixa ou etapa |
| `Ctrl+D` / `Delete` | Duplicar / excluir seleção |
| `F` | Ajustar à tela |
| `G` | Nova etapa |
| `?` | Todos os atalhos |

## Aplicativo de desktop (Windows)

O Desata também roda como programa instalável, em janela própria e offline:

```powershell
uv sync --extra desktop --group build
uv run prodata-desktop                 # testar a janela a partir do código
uv run python packaging/build.py       # gera dist/: instalador .exe, .zip portátil e a pasta do app
uv run python packaging/build.py --marca protege   # a mesma versão com a marca PRO.DATA
```

Cada versão sai nas duas marcas, Desata e PRO.DATA, com o guia de cada uma (`docs/guia/gerar_pdf.py --marca protege`).

Os dados do usuário ficam em `%LOCALAPPDATA%\Desata`. Detalhes, requisitos e
diagnóstico em [docs/distribuicao.md](docs/distribuicao.md).

## Desenvolvimento

```powershell
uv run pytest            # testes
uv run ruff check src tests && uv run ruff format src tests
uv run mypy              # tipos
$env:PRODATA_RELOAD="true"; uv run prodata   # servidor com reload
```

A CI (`.github/workflows/ci.yml`) roda lint, tipos e testes em todo push e PR.
Para hooks locais: `uvx pre-commit install`.

### Spec-Driven Development

O projeto segue SDD no formato do [GitHub Spec Kit](https://github.com/github/spec-kit):

- `.specify/memory/constitution.md` — princípios não negociáveis (motor
  desacoplado da UI, ferramentas declarativas, segurança por padrão, falhas
  explícitas, testes).
- `specs/NNN-nome/` — `spec.md` (o quê e por quê, requisitos `RF-xxx`),
  `plan.md` (como) e `tasks.md` (passos ligados aos requisitos).

| Spec | Escopo |
|------|--------|
| [001](specs/001-arquitetura-modular/spec.md) | Arquitetura modular do motor e da API |
| [002](specs/002-motor-ingestao/spec.md) | Motor de ingestão de dados |
| [003](specs/003-workbench-ui/spec.md) | Interface de trabalho |
| [004](specs/004-layout-insights/spec.md) | Layout revisado: configuração à esquerda, dados à direita, gráficos e resumos abaixo do canvas |
| [005](specs/005-conexoes-banco/spec.md) | Conexões com PostgreSQL e SQL Server (somente leitura, senha no cofre do SO) |
| [006](specs/006-paineis-conteineres/spec.md) | Painéis reposicionáveis/ocultáveis e contêineres de etapa editáveis |
| [007](specs/007-organizacao-filtros/spec.md) | Caixa de organização na paleta e no Configurar; filtros exploratórios nos resultados |
| [008](specs/008-app-desktop/spec.md) | Aplicativo de desktop instalável (janela própria, instalador e portátil) |
| [009](specs/009-edicao-fontes-destinos/spec.md) | Lixeira, copiar/colar e menus no canvas; consultas na aba Dados lidas pelo Input Data; pasta do Output Data e do fluxo |
| [010](specs/010-abas-formulas-fechamento/spec.md) | Abas de fluxos, editor de fórmulas com cores e autocompletar, fechamento seguro; corrige o Salvar como no executável |
| [011](specs/011-planilhas-identidade/spec.md) | Abas e recorte de planilhas (pular linhas/colunas); identidade visual Grupo Protege |
| [012](specs/012-selecao-cache-portas/spec.md) | Seleção múltipla, ponto de cache e dados de entrada por porta; remove o assistente de fluxo |
| [013](specs/013-ferramentas-desempenho/spec.md) | Select com Todas/Nenhuma/Inverter, 6 ferramentas novas (Cross Tab, Transpose, Text To Columns, Record ID, Running Total, Append Fields), remove a IA generativa, canvas mais responsivo |
| [014](specs/014-dashboard-canvas/spec.md) | Dashboard em canvas (arrastar, redimensionar, guias, Organizar com layouts prontos), painel Formato, textos/imagens/formas, PNG, big number com variação e tendência, empilhados, Pareto, Venn, funil, dispersão, medidor e Table |
| [015](specs/015-ajustes-035/spec.md) | Subtítulo e nomes de legenda no dashboard, grupos do Venn escolhidos na lista, esquemas visuais (Cross Tab, Transpose, Join), Excel com várias planilhas, Formula alterando colunas, 42 funções novas, preferências lembradas no programa instalado |
| [016](specs/016-telas-menores-cache/spec.md) | Painéis proporcionais e densidade compacta em telas menores; caixas puladas pelo ponto de cache em destaque, com contagem e "mostrar as puladas" |
| [017](specs/017-fontes-vivas-exportacao/spec.md) | Arquivos vinculados (fonte sempre atualizada), cache que percebe a fonte e renova por prazo, exportação que pergunta antes de sobrescrever, Venn seguro com colunas grandes |
| [018](specs/018-versao-04/spec.md) | Tela de abertura, `.xlsb`, Select que reordena colunas e converte tipos com tolerância e aviso, Formula em coluna existente corrigida, média/soma entre colunas, Join que mantém as duas chaves, aviso de espaços em branco, caixa em execução brilhando |
| [019](specs/019-join-select-summarize/spec.md) | Join com lado das chaves e Select embutido, esquema visual do Summarize, moda e desvio padrão (Summarize e Formula), compatibilidade com fluxos da 0.3.8 |
| [020](specs/020-aba-sql/spec.md) | Aba SQL: código por saída e unificado, caminho por porta, trilha do fluxo, conferência com o motor por etapa e de ponta a ponta, entrega em `.sql` e `.zip` |
| [021](specs/021-versao-055/spec.md) | APIs, filtros e HTML no dashboard, Multi-Row e tema Dracula |
| [022](specs/022-api-didatica/spec.md) | API didática, com exemplos visuais |
| [023](specs/023-parametros-api/spec.md) | API com e sem parâmetro; variáveis e parâmetros fixos |
| [024](specs/024-documentacao-api/spec.md) | Documentação e anotações de cada API |
| [025](specs/025-conectores-e-guia/spec.md) | Conectores, animações e guia reorganizado |
| [026](specs/026-seguranca-e-rotulos/spec.md) | Ordenação, Summarize por tipo, rótulos, segurança de API e HTML; Multi-Row com receitas e clique no gráfico |
| [027](specs/027-qualidade-do-codigo/spec.md) | Código dividido, limites verificados por teste e fórmulas sem acesso externo |
| [028](specs/028-dados-e-confianca/spec.md) | Vista Dados com mapa de uso, abertura protegida, Data Quality e constantes |
| [029](specs/029-experiencia-e-idioma/spec.md) | Espaço para o fluxo, um nome para cada coisa, letra e contraste, busca Ctrl+K, `[#hoje]` e Manual dentro do programa |
| [030](specs/030-jira-e-replay/spec.md) | Conector do Jira (só leitura), Estado por período, linha do tempo, corrida de barras, bolhas, Sankey, destaques, história, GIF por gráfico e lições guiadas |
| [031](specs/031-ajustes-pos-0-7/spec.md) | Ajustes depois da 0.7 |
| [032](specs/032-polimento-dash-e-design/spec.md) | Polimento do dashboard, do designer e das fórmulas |
| [033](specs/033-fechamento-sem-clique/spec.md) | Execução sem abrir o programa, pasta inteira, conferência (Reconcile, Compare Runs), Fuzzy Match, Regex, Mask, Subflow, Excel com modelo, ODBC, SQL para o Fabric e biblioteca de modelos |
| [034](specs/034-organizar-dados/spec.md) | Vista Dados organizada: pastas, nome de exibição, descrição, filtros, ordem e fixadas |
| [035](specs/035-pasta-na-aba-dados/spec.md) | Pasta de arquivos como fonte da vista Dados: uma tabela só ou um por arquivo |
| [036](specs/036-marca-configuravel/spec.md) | Marca 100% configurável e marca Desata |
| [037](specs/037-leitor-visual-pdf/spec.md) | Leitor visual de PDF: marcar no documento, ver o dado nascer e rastrear a origem |
| [038](specs/038-separador-decimal/spec.md) | Separador decimal escolhido pela pessoa: vírgula ou ponto |
| [039](specs/039-regex-didatico/spec.md) | Regex sem escrever expressão regular: marcar o trecho no exemplo e ajustar as peças |
| [040](specs/040-datas-e-fluxo-portatil/spec.md) | Datas sem formato certo ("Você quis dizer…", calendário) e fluxo que viaja entre computadores (o que falta e amostra) |

Para adicionar uma ferramenta, veja [docs/nova-ferramenta.md](docs/nova-ferramenta.md).

Para pedir ajuda a um assistente de IA sobre um fluxo, envie junto o [docs/contexto-ia.md](docs/contexto-ia.md): ele
explica o formato do arquivo e todas as ferramentas. É gerado do código por `docs/gerar_contexto_ia.py`.

## Arquitetura

```text
src/prodata/
├── config.py          configurações (variáveis PRODATA_*)
├── brand.py           marca ativa: leitura, paleta, conferência e CSS (spec 036)
├── marcas/            um pacote por marca: marca.toml, logos, ícone e fontes
├── main.py            create_app(): FastAPI + serviços + arquivos estáticos
├── cli.py             linha de comando: prodata run / list (Agendador do Windows)
├── api/               rotas HTTP finas e tradução de erros
├── domain/            modelos Pydantic do workflow e do relatório de execução
├── engine/            grafo, executor incremental, cache Arrow, perfil, fórmulas
├── nodes/             ferramentas (uma família por módulo) + registro declarativo
├── ingestion/         detecção e leitura de arquivos, arquivos vinculados e pastas de arquivos
├── documents/         leitor de PDF: leitura isolada, palavras com posição, extração, saídas e correções
├── connectors/        bancos (connectorx e ODBC), APIs, Jira e senhas no cofre do SO
├── services/          workflows, uso das fontes, constantes, organização e abertura protegida
├── samples/           datasets e fluxo de demonstração
├── desktop.py         app de desktop (servidor local + janela WebView2)
└── web/               frontend (ES modules nativos, sem build)
tests/                 pytest: grafo, fórmulas, ingestão, ferramentas, executor, API, conectores, exploração
specs/                 especificações (SDD)
storage/               datasets, workflows, cache e exportações (configurável)
```

O motor (`engine`, `nodes`, `ingestion`) não depende de FastAPI e pode ser
usado em scripts:

```python
from prodata.engine.cache import ResultCache
from prodata.engine.runner import WorkflowRunner
from prodata.ingestion import DatasetStore
from prodata.domain.workflow import Workflow

runner = WorkflowRunner(ResultCache(cache_dir), DatasetStore(data_dir, 200 * 2**20), exports_dir)
report = runner.run(Workflow.model_validate_json(path.read_text()))
```

Cada ferramenta declara um modelo de configuração Pydantic; o catálogo
(`GET /api/catalog`) descreve os campos e o Inspector gera o formulário a
partir dele. O frontend não tem código específico por ferramenta.

## API

Documentação interativa em http://127.0.0.1:8765/docs.

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/api/catalog` | Ferramentas, portas e campos de configuração |
| GET · POST | `/api/datasets` | Listar · enviar arquivo (`multipart`, `overwrite`) |
| POST | `/api/datasets/{nome}/preview` | Pré-visualizar com opções de leitura (`auto` é resolvido) |
| DELETE | `/api/datasets/{nome}` | Excluir arquivo |
| GET | `/api/workflows` · `/api/workflows/{id}` | Listar · obter fluxo |
| PUT · DELETE | `/api/workflows/{id}` | Salvar · excluir fluxo |
| POST | `/api/execute` | Executar (opcional `target_node_id`) |
| GET | `/api/results/{wf}/{nó}/{porta}` | Página de resultados com perfil (`offset`, `limit`, `search`, `sort_col`, `filters` em JSON) |
| GET | `/api/exports/{arquivo}` | Baixar arquivo gerado pelo Output Data |
| POST | `/api/formula/validate` | Validar expressão contra um esquema |
| GET · PUT · DELETE | `/api/connections[/{id}]` | Conexões com bancos (a senha só entra no PUT, nunca sai) |
| POST · GET · POST | `/api/connections/{id}/test` · `/tables` · `/preview` | Testar, listar tabelas, pré-visualizar |
| GET · PUT · DELETE | `/api/queries[/{id}]` | Consultas de banco da vista Dados (sem senha) |
| POST | `/api/queries/preview` | Prévia de uma consulta ainda não salva |
| GET · PUT · DELETE | `/api/apis[/{id}]` | Fontes de API da vista Dados (segredos entram no PUT, nunca saem) |
| POST | `/api/apis/preview` | Chamada de teste de uma API, só a primeira página, com amostra da resposta |
| GET | `/api/apis/examples` | APIs públicas de exemplo para começar um cadastro (nada é chamado) |
| POST | `/api/dashboard/filter-options` · `/filtered` | Valores dos filtros · visuais recalculados, sem executar o fluxo |
| POST · GET | `/api/dashboard/export-data` · `/viewer.js` | Dados e script do dashboard em HTML |
| POST | `/api/dashboard/export-log` | Registra uma exportação feita na tela (sem os dados) |
| POST | `/api/files/workflow/save` · `/open` | Salvar / abrir fluxo num caminho escolhido (`.prodata.json`) |
| GET | `/api/usage` | Onde cada fonte e cada constante é usada nos fluxos da biblioteca |
| GET · POST · DELETE | `/api/constants[/{nome}]` | Constantes compartilhadas (`previous` no POST renomeia) |
| POST | `/api/trust/state` · `/confirm` | Abertura protegida: situação do fluxo e confirmação de confiança |
| POST | `/api/portable/sources` | Fontes do fluxo neste computador: ok, faltando ou com amostra |
| POST | `/api/portable/share/preview` · `/mask-preview` · `/save` | Salvar com amostra: fontes e tamanhos, prévia mascarada e gravação |
| GET · POST · PUT · DELETE | `/api/folders[/{id}]` · `/preview` · `/link-each` | Pastas de arquivos: cadastro, prévia empilhada e "um por arquivo" |
| GET · POST · PUT · DELETE | `/api/pdfs[/{id}]` · `/upload` · `/example` · `/duplicate` | Leitores de PDF: cadastro, cópia enviada, exemplo e duplicar |
| GET · POST · PUT | `/api/pdfs/{id}/docs` · `/recipe` · `/suggest/*` · `/evaluate` · `/outputs/{saida}` · `/corrections` | Editor do PDF: palavras, páginas, extração, sugestões, impacto, saídas e correções |
| POST | `/api/pdfs/{id}/docs/add` · `/docs/leave` · `/docs/back` | Documentos um a um: adicionar PDFs (cópia guardada), tirar da fonte e trazer de volta |
| GET · POST · DELETE | `/api/pdfs/recipes[/{id}]` · `/export` · `/import` · `/{id}/recipe/use` · `/fork` | Extrações salvas: listar, exportar, importar, excluir, usar e copiar |
| GET · POST · PUT · DELETE | `/api/organization[...]` | Pastas, nomes de exibição, descrições e fixadas da vista Dados |
| GET · PUT · DELETE | `/api/jira/connections` · `/queries` | Conexões e consultas do Jira (o token entra no PUT, nunca sai) |
| GET · POST · DELETE | `/api/models[...]` | Biblioteca de modelos: listar, importar e exportar `.modelo`, versões |
| POST · GET | `/api/sql/generate` · `/verify` · `/download` | Aba SQL: gerar, conferir e baixar o código |
| GET | `/api/marca` · `/marca/cores.css` · `/marca/{logo}` | Marca ativa: nome, cores e logos |

Fluxos são salvos na biblioteca `storage/workflows/<id>.prodata.json` ou, com
*Salvar como…*, em qualquer pasta (JSON legível, versionável em Git). O Input
Data aponta para um arquivo da vista Dados pelo nome, para uma pasta de arquivos como `folder:<id>`,
para uma saída de um leitor de PDF como `pdf:<id>/campos` (ou `itens_<tabela>`, `falhas`, `origem`),
para uma consulta como `sql:<id>`, para uma API como `api:<id>` ou para o Jira como `jira:<id>`. As
consultas ficam em `storage/queries.json`, as APIs, sem segredos, em `storage/apis.json`, os arquivos
vinculados e as pastas de arquivos em `storage/datasets_vinculos.json` e `storage/datasets_pastas.json`,
os leitores de PDF, as extrações e as correções em `storage/datasets_pdfs.json`, `storage/datasets_extracoes.json`
e `storage/datasets_pdf_correcoes.json`,
a organização da vista Dados em `storage/organizacao.json`, as constantes compartilhadas em
`storage/constantes.json` e os fluxos confirmados na abertura protegida em `storage/confianca.json`.

## Desempenho

Decisões medidas (detalhes nos comentários do código):

- Bibliotecas pesadas carregam sob demanda: scikit-learn só ao treinar e
  connectorx só ao consultar um banco; o scikit-learn é pré-carregado em segundo
  plano logo após o servidor subir. Inicialização: 1,6 s → 0,8 s.
- O motor de fórmulas reaproveita uma base DuckDB com as macros já criadas e usa
  um cursor isolado por execução: 30–60 ms → 6 ms por nó Formula/Filter.
- Random Forest só usa vários núcleos acima de 20 mil linhas; abaixo disso o
  paralelismo deixava o treino mais lento (270 ms contra 203 ms).
- Conexões com banco fazem uma checagem TCP de 5 s antes do driver: servidor
  inacessível falha em ~2 s em vez de ~30 s.
- Execução incremental: reexecutar um fluxo sem mudanças leva ~9 ms.
- Os resultados de cada caixa ficam na memória até um quarto da RAM (ajustável com
  `PRODATA_CACHE_MEMORY_MB`); acima disso, os usados há mais tempo ficam só no disco, em
  Arrow, e voltam quando pedidos.

## Configuração

Variáveis de ambiente (ou `.env`, ver `.env.example`): `PRODATA_HOST`,
`PRODATA_PORT`, `PRODATA_STORAGE_DIR`, `PRODATA_MAX_UPLOAD_MB`,
`PRODATA_CORS_ORIGINS`, `PRODATA_LOG_LEVEL`, `PRODATA_SEED_SAMPLES`,
`PRODATA_RELOAD`, `PRODATA_SECRETS_BACKEND` (`keyring` ou `memory`), `PRODATA_CACHE_MEMORY_MB`
(limite de resultados na memória; 0 = um quarto da RAM) e `PRODATA_MARCA` (marca em desenvolvimento).
Os nomes `PRODATA_*` são identificadores técnicos e valem para qualquer marca.

## Limitações conhecidas

- Aplicação local e de usuário único: não há autenticação.
- Cada arquivo de entrada é lido inteiro pelo Polars, e a pasta de arquivos aceita até 500 arquivos.
  Os resultados intermediários grandes vão para o disco, mas o arquivo lido precisa caber na memória.
- O leitor de PDF lê a camada de texto: PDF escaneado (só imagem) aparece como Não suportado, porque
  ainda não há OCR. Uma extração vale para um layout; layouts diferentes pedem fontes diferentes.
- ODBC, SQL para o Fabric e o Jira Cloud foram conferidos com drivers e serviços de teste: no
  primeiro uso num sistema real, confira a primeira leitura com um resultado que você conhece.

## Identidade visual e marcas

O nome, a organização, as cores, as fontes e o logo vêm de uma **marca**, em `src/prodata/marcas/<id>/` (spec 036).
O mesmo código gera o programa com qualquer marca, e um fluxo feito numa abre em todas:

```powershell
uv run python packaging/build.py --marca neutra   # instalador, portátil e executável com a marca neutra
$env:PRODATA_MARCA = "neutra"; uv run prodata     # em desenvolvimento
```

- `desata`: a marca padrão desde a 0.8.0 (Petróleo `#003F46`, Teal `#007E7D`, Verde fluxo `#21C7A4`, Manrope e Inter).
- `protege`: Grupo Protege, o PRO.DATA (marinho `#043154`, dourado `#95793c`, Open Sans e o escudo). Reproduz a 0.7.7.
- `neutra`: sem empresa, para testar a troca de ponta a ponta.

Cada marca tem a sua pasta de dados, o seu serviço no cofre do Windows e o seu identificador de instalador, então
duas marcas convivem no mesmo computador. Como criar uma marca: [src/prodata/marcas/LEIA-ME.md](src/prodata/marcas/LEIA-ME.md).

