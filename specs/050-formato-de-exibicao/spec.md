# Spec 050: formato de exibição da coluna (moeda, documento, data)

Status: Em andamento · Versão 0.9.6 (substituição) · Criada: 2026-11-26

## Contexto

Pedido feito depois da publicação da 0.9.6, para entrar na própria 0.9.6 substituída:

> Queria poder visualizar uma coluna como quero visualizar ela em alguns casos: uma coluna numérica como valor
> monetário colocando a moeda dela (R$, $, etc.), uma de CPF como xxx.xxx.xxx-xx ou uma de data como xx/xx/xxxx.

Situação conferida no programa:

- O **Resultado** mostra o número só com os separadores (`12345678901` vira `12.345.678.901`, e um CPF com zero à
  esquerda perde o zero); a data aparece como o motor entrega (`2026-11-26`, `2026-11-26T14:30:00`).
- Só o **KPI** do Dashboard tem prefixo, sufixo e casas; os gráficos têm prefixo e sufixo por visual. Nada disso
  conversa com a coluna: quem quer ver "R$" precisa repetir em cada visual.
- O **Excel** gravado leva os valores sem formato de número: quem abre vê `1234.5` e precisa formatar à mão.
- Para ver um CPF com pontos hoje, a pessoa cria uma coluna de texto com fórmula, e com isso perde o número.

## Princípio

O formato muda **só a aparência**. O dado continua o mesmo, com o mesmo tipo: contas, filtros, ordenação, junções e
o arquivo CSV não mudam. Mudar o formato nunca pede executar o fluxo de novo.

## Histórias de usuário

- Como analista, quero ver a coluna `valor` como **R$ 1.234,56** em toda parte (Resultado, Perfil, Dashboard,
  Excel) definindo isso **uma vez**, e não em cada visual.
- Como quem trabalha com cadastros, quero ver `cpf` como **123.456.789-01**, com o zero à esquerda de volta, sem
  transformar a coluna em texto.
- Como quem lê datas, quero ver **26/11/2026** em vez de `2026-11-26`.
- Como quem precisa gravar o texto formatado num CSV, quero um jeito de criar essa coluna de texto, sabendo o que
  foi feito.

## Requisitos

### A. Definir o formato

| ID | Requisito |
|----|-----------|
| RF-5001 | **Onde:** no **Resultado**, o botão direito no cabeçalho da coluna oferece **Formato de exibição…** (junto de ordenar, filtrar e das receitas). A busca de comandos (Ctrl+K) não abre o diálogo, porque ele depende da coluna. Fluxo só de leitura (espaço da equipe sem permissão, lição, exemplo protegido) mostra o formato mas não oferece a opção. |
| RF-5002 | **Tipos de formato**, oferecidos conforme o tipo da coluna: **Número** (casas decimais, separador de milhar), **Moeda** (símbolo e casas), **Porcentagem** (casas; o valor guardado como fração, 0,15 → 15%, ou já em pontos, 15 → 15%), **Documento** (CPF, CNPJ, CEP, telefone ou máscara livre) e **Data** (dd/mm/aaaa, mm/aaaa, dd/mm/aaaa hh:mm, "26 de nov. de 2026", aaaa-mm-dd). Número, Moeda e Porcentagem: colunas numéricas. Documento: números inteiros e texto. Data: data e data e hora. **Sem formato** volta ao normal. |
| RF-5003 | **Moeda:** símbolos prontos R$, US$, €, £, ¥ e "Outro" (até 6 caracteres, sem `<`, `>`, `"` ou aspas simples). O símbolo vem antes, com espaço (R$ 1.234,56); negativo fica -R$ 10,00. Os separadores seguem a escolha de número do programa (spec 038). |
| RF-5004 | **Documento:** CPF `000.000.000-00` (11 dígitos), CNPJ `00.000.000/0000-00` (14), CEP `00000-000` (8), telefone `(00) 00000-0000` (10 ou 11 dígitos: com 10, `(00) 0000-0000`) e **máscara livre**, em que `#` é um dígito e o resto é escrito como está (`###.###-#`, até 40 caracteres). Número guardado sem os zeros à esquerda recebe os zeros de volta. Do texto, só os dígitos contam (`123.456.789-01` e `12345678901` saem iguais). |
| RF-5005 | **Prévia ao vivo:** o diálogo mostra, ao lado das escolhas, uma tabela **Como está → Como fica** com até 6 valores reais e diferentes da coluna (da página aberta do Resultado), atualizada a cada escolha. Valor que não cabe no formato aparece marcado já na prévia, com o motivo. |
| RF-5006 | **Como funciona:** o diálogo traz um esquema curto: o dado guardado (`12345678901`) passa pelo formato e aparece na tela (`123.456.789-01`), com a frase "o dado não muda: contas, filtros e o CSV usam o valor guardado". |
| RF-5007 | **Desfazer:** aplicar, trocar e remover um formato é uma mudança do fluxo como outra qualquer: marca o fluxo como não salvo e sai com um Ctrl+Z. |

### B. Até onde o formato vale

| ID | Requisito |
|----|-----------|
| RF-5011 | **Na caixa e nas seguintes:** o formato definido na saída de uma caixa vale nela e em todas as caixas seguintes em que a coluna continua com **o mesmo nome**. Renomear a coluna (Select) ou criar outra com outro nome deixa a nova sem formato. O diálogo diz isso em palavras ("Vale nesta caixa e nas seguintes enquanto a coluna se chamar `cpf`"). |
| RF-5012 | **Trocar ou tirar adiante:** numa caixa adiante, a pessoa pode trocar o formato herdado ou escolher **Sem formato**; a escolha vale dali em diante. Quando duas entradas trazem a mesma coluna com formatos diferentes (Join, Union), vale o da primeira entrada. |
| RF-5013 | **De onde veio:** o cabeçalho da coluna mostra um selo curto do formato (`R$`, `CPF`, `dd/mm`, `%`, `1,2`); a dica diz o formato por extenso e, quando herdado, de qual caixa ("Moeda R$, 2 casas · definido em Vendas do mês"). |
| RF-5014 | **Coluna que some:** formato de uma coluna que não existe mais na caixa não aparece em lugar nenhum e não atrapalha; volta a valer se a coluna voltar. Apagar a caixa apaga os formatos dela. |

### C. Onde aparece

| ID | Requisito |
|----|-----------|
| RF-5021 | **Resultado:** as células mostram o valor formatado. A barra da célula em foco (spec 041) mostra também o **valor guardado**. Filtrar pelo valor da célula usa o valor guardado. |
| RF-5022 | **Perfil:** mínimo, máximo, média, mediana e soma de colunas numéricas, e o valor mais comum, saem no formato da coluna. |
| RF-5023 | **Dashboard, gráficos:** quando o visual soma, faz média, mínimo ou máximo de uma coluna com formato numérico (Número, Moeda, Porcentagem), os valores do eixo, os rótulos, a dica e o modo tabela saem nesse formato (no eixo e nos rótulos, compacto: R$ 1,2 mi). Contagem e valores distintos não usam o formato. As categorias do eixo (coluna de data ou documento) saem no formato da coluna; as cores, os filtros por clique e os nomes trocados no painel Formato continuam valendo. |
| RF-5024 | **Dashboard, KPI e tabela:** o KPI de soma, média, mínimo ou máximo usa o formato da coluna; a Tabela formatada mostra cada coluna no seu formato, inclusive os totais. |
| RF-5025 | **O visual manda:** prefixo, sufixo, casas ou formato do número escritos no próprio visual (painel Formato ou na caixa) valem mais que o formato da coluna. |
| RF-5026 | **Exportações do Dashboard:** a imagem PNG, o GIF e o HTML exportado mostram os mesmos formatos da tela; o HTML leva os formatos dentro do arquivo. |
| RF-5027 | **Excel:** o Output Data em Excel grava cada coluna com o **formato de número do Excel** equivalente (moeda, número, porcentagem, data, e documento em coluna de número inteiro, como `000"."000"."000"-"00`). A célula continua com o número ou a data: quem abre pode somar e filtrar. Coluna de texto fica como está (o Excel não formata texto). Vale para arquivo novo, para adicionar planilha e para o modelo de Excel. |
| RF-5028 | **CSV, JSON e Arrow** gravam o valor guardado, sem formato. O diálogo avisa: "No CSV vai o valor guardado; para gravar o texto formatado, use Criar coluna de texto". |

### D. Nada some sem aviso

| ID | Requisito |
|----|-----------|
| RF-5031 | **Valor que não cabe:** documento com outra quantidade de dígitos, texto numa coluna formatada como número ou data inválida aparecem **como estão**, com sublinhado pontilhado e a dica do motivo ("tem 10 dígitos; CPF tem 11"). Nunca são cortados nem completados além dos zeros à esquerda. |
| RF-5032 | **Contagem no diálogo:** a prévia diz quantos dos valores da página não cabem no formato ("2 de 50 valores não cabem: aparecem como estão"). |

### E. Criar coluna de texto

| ID | Requisito |
|----|-----------|
| RF-5041 | **Criar coluna de texto com este formato…** no diálogo insere, logo depois da caixa, uma **Formula** que cria `<coluna>_texto` com uma expressão legível, que a pessoa pode abrir e mudar (ex.: `"R$ " + FormatNumber([valor], 2)`, `DateFormat([data], '%d/%m/%Y')`). A coluna original fica como está. Desfazer tira a caixa. Antes de inserir, o diálogo mostra a expressão. |

### F. Arquivo do fluxo e segurança

| ID | Requisito |
|----|-----------|
| RF-5051 | Os formatos ficam no arquivo do fluxo, por caixa e por coluna. Fluxo sem formato não ganha nada no arquivo: a impressão de confiança, a assinatura e a base dos fluxos que já existem não mudam. Versões anteriores ao 0.9.6 substituído ignoram o campo ao abrir. |
| RF-5052 | Os formatos guardam só escolhas (tipo, casas, símbolo, máscara): nunca valores da coluna. Símbolo e máscara são conferidos ao abrir o fluxo (tamanho e caracteres), porque vão para a tela, para o HTML exportado e para o Excel. |

### G. Documentação

| ID | Requisito |
|----|-----------|
| RF-5061 | Guia (duas marcas) e manual do programa: seção **Formato de exibição** com o esquema, o diálogo, o Resultado formatado e um visual do Dashboard, e a regra "o dado não muda". Prints novos nas duas marcas e nos dois temas, como os demais. |

## Fora do escopo

- Formato condicional (cor por faixa): já existe nos visuais (spec 014) e na Tabela formatada.
- Formato no Designer (prévia das caixas no canvas) e na aba SQL.
- Converter a coluna de verdade (texto em número, número em data): continua com Select, Formula e as receitas.

## Critérios de aceite

- CA-01: definir Moeda R$ com 2 casas em `valor` mostra `R$ 1.234,56` no Resultado da caixa e da seguinte; o Perfil
  mostra a soma no mesmo formato; um gráfico de soma de `valor` mostra `R$` no eixo, nos rótulos e na dica.
- CA-02: CPF guardado como número `1234567890` aparece `012.345.678-90`; um valor com 12 dígitos aparece como está,
  marcado, com o motivo.
- CA-03: data `2026-11-26` aparece `26/11/2026` com dd/mm/aaaa e `26 de nov. de 2026` por extenso.
- CA-04: renomear a coluna num Select adiante tira o formato dali em diante; escolher Sem formato numa caixa adiante
  tira só dali em diante.
- CA-05: o Excel gravado tem `R$ #,##0.00` (ou equivalente) em `valor`, `dd/mm/yyyy` na data e a máscara do CPF na
  coluna inteira; as células continuam numéricas.
- CA-06: o HTML exportado e a imagem PNG mostram os mesmos formatos da tela.
- CA-07: Criar coluna de texto insere uma Formula com a expressão mostrada; o valor da coluna nova bate com a tela.
- CA-08: um fluxo antigo, aberto e salvo sem mexer em formato, continua com a mesma impressão de confiança.
