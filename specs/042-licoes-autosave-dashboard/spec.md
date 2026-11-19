# Spec 042: lições em dia, salvar sozinho, prévia dos gráficos e Dashboard mais fácil de formatar

Status: Rascunho · Versão 0.9.1 · Criada: 2026-11-19

## Contexto

- **Lições guiadas** (spec 030): são quatro (primeiro fluxo, juntar tabelas, qualidade, dashboard) e envelheceram. A
  primeira manda "escolher o arquivo no painel à direita", mas o Configurar fica à esquerda e a fonte agora é
  escolhida no seletor (spec 041). Nenhuma lição mostra o que veio depois: constantes, datas, laço, recolher e organizar.
- **Salvar:** só com Ctrl+S. Quem esquece perde o trabalho se o programa fechar.
- **Designer:** para ver como ficou um gráfico, é preciso ir ao Dashboard ou ao painel de gráficos.
- **Dashboard:**
  - o fundo da página aceita só uma cor;
  - o painel Formato é uma lista longa de seções (Cartão, Cores, Rótulos e legenda, Eixos, Dica, Cores por faixa), e é
    preciso rolar muito;
  - as paletas são poucas (marca, alternativa, uma cor) e nenhuma é pensada para daltonismo;
  - os rótulos de dados vão até "maior e menor": não há "todos";
  - os valores dos eixos não podem ser escondidos.

## Requisitos

### Lições guiadas

| ID | Requisito |
|----|-----------|
| RF-4201 | As quatro lições existentes conferidas e atualizadas para a tela de hoje: Configurar à esquerda, fonte pelo seletor (Trocar), nomes dos botões e das abas atuais. Cada passo continua dizendo onde agir, com o destaque no lugar certo, e avança sozinho. |
| RF-4202 | Lições novas, no mesmo formato: **Repetir com um laço** (Loop por uma coluna, Formula com `[#valor]`, executar e escolher a volta), **Um arquivo por valor** (Output Data com `{coluna}` no nome), **Valores com nome: constantes** (criar uma constante e usar numa fórmula) e **Organizar um fluxo grande** (agrupar numa etapa, recolher a etapa e Organizar o fluxo). |
| RF-4203 | Um teste no navegador percorre cada lição do começo ao fim fazendo o que o passo pede e confirma que todos os passos avançam: uma lição nunca mais fica para trás de uma mudança na tela. |

### Salvar sozinho

| ID | Requisito |
|----|-----------|
| RF-4211 | **Botão Salvar na barra superior:** o Salvar sai do menu Arquivo e vira um botão com ícone próprio no topo, ao lado do Executar (Ctrl+S continua valendo). Uma seta ao lado do botão abre **Salvar automaticamente** (liga e desliga). Com ele ligado, um fluxo que **já foi salvo uma vez** (na biblioteca ou num arquivo escolhido) é salvo sozinho alguns segundos depois de cada mudança. Fluxo novo, nunca salvo, continua pedindo o primeiro Salvar. |
| RF-4212 | **Sinal discreto:** com o salvamento automático ligado, o botão Salvar ganha um pequeno selo (setas circulares) e a dica "Salvamento automático ligado · salvo às 14:32". O salvamento é silencioso: sem aviso a cada vez, e o selo "não salvo" some. Um erro ao salvar avisa e desliga o automático daquele fluxo até o próximo Salvar manual. |
| RF-4213 | Fluxo aberto em modo protegido (de fora, ainda não confiado), lição e exemplo aberto pelo Manual nunca salvam sozinhos. A escolha fica guardada neste computador. |

### Prévia do gráfico no Designer

| ID | Requisito |
|----|-----------|
| RF-4221 | Passar o mouse numa caixa de BI (Chart, KPI Card, Venn, Table) mostra, depois de meio segundo, um cartão flutuante com a prévia do visual, do mesmo jeito que no Dashboard. Sem execução, o cartão diz "Execute para ver a prévia". O cartão some ao tirar o mouse, ao arrastar ou ao clicar. |

### Dashboard

| ID | Requisito |
|----|-----------|
| RF-4231 | **Imagem de fundo da página:** no painel da página, enviar uma imagem (PNG, JPG ou SVG, até 5 MB) com ajuste (cobrir, caber, repetir, centralizar) e transparência. Vale no Dashboard, no modo apresentação, no PNG e no HTML exportados; o painel avisa que a imagem vai dentro do arquivo do fluxo e do HTML. Remover volta à cor de fundo. |
| RF-4232 | **Painel Formato em abas:** as seções viram abas com ícone no topo do painel (Cartão, Cores, Rótulos, Eixos, Dica, Faixas), e cada aba cabe sem rolar na maioria dos visuais. A aba aberta fica a mesma ao trocar de visual. |
| RF-4233 | **Mais visual:** a paleta é escolhida por amostras de cor (não por nome numa lista); opções de sim e não viram interruptores lado a lado; a posição da legenda e o alinhamento viram botões com ícone. |
| RF-4234 | **Paletas prontas:** além da marca e da alternativa, paletas conhecidas: **Okabe-Ito** (pensada para daltonismo, marcada como tal), **Tableau 10**, **ColorBrewer Set2**, **Viridis** (sequencial, legível em preto e branco), **Tons de azul** e **Tons de cinza**. Valem em todos os gráficos com várias cores, no Dashboard e no HTML. |
| RF-4238 | **Paleta geral do dashboard:** no painel da página, uma paleta para o dashboard inteiro muda as cores de todos os visuais de uma vez. O visual que tiver paleta própria continua com a dele, e o painel do visual mostra "Usa a paleta do dashboard" ou "Paleta própria", com um botão para voltar à geral. |
| RF-4235 | **Rótulos de dados: todos.** A opção "Todos" mostra o valor em cada barra, ponto ou fatia. Com muitos rótulos, os que não cabem são omitidos para não se sobrepor, e um aviso no painel diz isso. |
| RF-4236 | **Esconder os eixos:** "Valores do eixo Y" e "Rótulos do eixo X" ligam e desligam; sem os valores do eixo Y, as linhas de grade também podem sair, e os rótulos de dados são o jeito de ler os números. |
| RF-4237 | Guia e Manual com as novidades, prints nos dois temas e nas duas marcas, versão 0.9.1, guias e instaladores nas duas marcas. |

### Join e Union

| ID | Requisito |
|----|-----------|
| RF-4241 | **Como funciona no Union**, como no Join: as duas entradas e o resultado empilhado, com a amostra dos dados quando já executou. Pelo nome, mostra que a coluna que só existe numa entrada continua e fica vazia nas linhas da outra; pela posição, que vale a ordem e os nomes da entrada 1. A coluna de origem aparece quando escolhida. |
| RF-4242 | **Join com saídas empilhadas:** a opção "Empilhar saídas na U" cria a saída extra U com L + J + R, L + J, J + R ou L + R, empilhadas pelo nome (como um Union logo depois do Join), com a coluna opcional `saida` (L, J ou R). A saída U só aparece na caixa com a opção ligada (ou com fio). Vale também na aba SQL (UNION ALL BY NAME), conferida com o motor, e no Como funciona do Join. |

### Ajustes antes de publicar

| ID | Requisito |
|----|-----------|
| RF-4251 | **Salvar só com o ícone** no topo (o nome fica na dica e no leitor de tela). |
| RF-4252 | **Topo compacto:** com pouco espaço, Arquivo e Exibir viram só ícones bem antes de faltar lugar. |
| RF-4253 | **Menu do Salvar** reúne Salvar automaticamente, Salvar como… e Salvar com amostra dos dados… (que saem do Arquivo), num menu estreito, com a explicação do automático quebrando em linhas. |
| RF-4254 | **Prévia do Venn no Designer** legível: altura suficiente para os círculos e os números não se sobreporem, e a dica nativa da caixa não aparece por cima da prévia. |
| RF-4255 | **Paleta personalizada do dashboard:** no painel da página, até 8 cores escolhidas pela pessoa; aparece como "Personalizada" na paleta geral e na lista de cada visual; vai no fluxo e no HTML. |
| RF-4256 | **Linhas de grade editáveis** na aba Eixos: contínua, tracejada ou pontilhada, cor e transparência. |
| RF-4257 | **Escala logarítmica no eixo Y** (base 10) em colunas, barras, linhas e dispersão. Zero e negativos não cabem: ficam fora da escala, com aviso. Empilhados, 100% e rosca não oferecem. |
| RF-4258 | **Linha de referência** no Chart (Configurar): valor fixo, constante `[#nome]` ou calculado dos dados (média ou mediana), com rótulo. No gráfico aparece a linha, e barras e pontos acima e abaixo dela ganham cores próprias, escolhidas no painel Formato. Também no HTML. |
| RF-4259 | **Fontes dos visuais:** no painel Formato, título em negrito e itálico e com cor própria; subtítulo com tamanho, itálico e cor; fonte do cartão (do tema, sem serifa, com serifa, monoespaçada); nos gráficos, cor e negrito dos rótulos de dados e cor dos textos dos eixos; na caixa de texto, a mesma escolha de fonte e sublinhado. Vale no Dashboard, no PNG e no HTML. |
| RF-4260 | **Painel Formato mais compacto e uma aba Texto:** a aba Eixos se organiza em blocos com título (Eixo Y, Eixo X, Grade, Linha de referência), com campos lado a lado, cores compactas e transparência num controle deslizante. As opções de fonte ganham a aba **Texto**: famílias em cartões com "Aa", uma barra por texto (título, subtítulo, rótulos, eixos, número do KPI) com negrito, itálico, alinhamento, tamanho com − e + e cor, e uma prévia ao vivo. |

## Fora do escopo

- Paleta personalizada salva para reutilizar em outros fluxos.
- Vídeo ou GIF como fundo do Dashboard.
- Prévia de dados (tabela) ao passar o mouse em caixas que não são de BI.

## Critérios de aceite

| ID | Critério | Requisitos |
|----|----------|------------|
| CA-01 | O teste percorre as oito lições sem nenhum passo travado; a primeira manda escolher a fonte pelo Trocar. | RF-4201..4203 |
| CA-02 | O Salvar fica na barra superior; com o automático ligado, o botão mostra o selo, e mudar uma caixa num fluxo já salvo grava o arquivo em até 5 s sem aviso; num fluxo novo, nada é gravado. | RF-4211..4213 |
| CA-03 | Passar o mouse no Chart do exemplo mostra o gráfico numa caixa flutuante; tirar o mouse a esconde. | RF-4221 |
| CA-04 | Uma imagem de fundo aparece no Dashboard e no HTML exportado; remover volta à cor. | RF-4231 |
| CA-05 | O painel Formato de um gráfico abre em abas; a aba Cores mostra as paletas como amostras, incluindo Okabe-Ito marcada para daltonismo. Trocar a paleta geral do dashboard muda todos os gráficos sem paleta própria. | RF-4232..4234, RF-4238 |
| CA-06 | "Todos" nos rótulos mostra o valor de cada barra; sem os valores do eixo Y, o gráfico não desenha a escala. | RF-4235, RF-4236 |
| CA-07 | O Union mostra o Como funciona com a coluna que falta como vazia; o Join com L + J tem a saída U com L + J linhas e a coluna saida, igual no SQL. | RF-4241, RF-4242 |
| CA-08 | O Salvar do topo é só ícone, e o menu dele traz automático, Salvar como e amostra; em janela estreita, Arquivo e Exibir são ícones; a prévia do Venn não se sobrepõe. | RF-4251..4254 |
| CA-09 | Uma paleta personalizada pinta os gráficos; a grade pontilhada e o log no Y aparecem; a linha de referência com média pinta as barras acima e abaixo com cores diferentes, também no HTML. | RF-4255..4258 |
