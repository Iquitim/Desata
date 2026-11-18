# Spec 041: canvas organizado, seletor de fontes e laço

Status: Concluída · Versão 0.9.0 · Criada: 2026-11-17

## Contexto

Os fluxos cresceram: o exemplo tem seis etapas, e fluxos reais passam de 40 caixas. Hoje:

- **Canvas.** Toda caixa tem o mesmo tamanho e a etapa só desenha uma moldura; um fluxo grande fica poluído. O fio é
  uma curva direta entre as portas e atravessa as caixas que estiverem no caminho.
- **Fontes.** O Input Data escolhe a fonte numa lista suspensa com grupos por tipo. Com dezenas de fontes, achar a
  certa é difícil, e as pastas da vista Dados (spec 026) não aparecem ali.
- **Tabela do Designer.** O cabeçalho com perfil (minigráfico, qualidade e total) ocupa metade do painel em telas
  pequenas, e a largura das colunas não se ajusta.
- **Dashboard.** A dica dos gráficos é fixa: rótulo e valor.
- **Tempo.** O motor mede o tempo de cada caixa, mas ele só aparece no Inspector e no Log; o gargalo não salta aos
  olhos.
- **Repetição.** Não há um laço: o que mais se parece é o API Loop (uma chamada por linha) e o subfluxo. Quem precisa
  de "para cada filial, faça…" ou de um cálculo que se repete até convergir não tem como.

## Objetivo

1. Um fluxo grande se lê em blocos: caixas e etapas recolhem, e os fios desviam das caixas sozinhos.
2. Escolher uma fonte entre muitas é tão fácil quanto abrir um arquivo no Windows.
3. A tabela e a dica dos gráficos se ajustam a quem usa; o tempo de cada caixa aparece no canvas.
4. Um laço visual, com começo e fim claros, para repetir um trecho do fluxo por valor, por faixa ou até uma condição.

## Requisitos

### Configurar: blocos de lista que recolhem

Toda lista repetida da aba Configurar usa o mesmo componente; o que vale para um vale para todos: fórmulas da
Formula, ordenação do Sort, ordem do Multi-Row, chaves do Join, agregações do Summarize, controles do Reconcile e
regras do Data Quality.

| ID | Requisito |
|----|-----------|
| RF-4105 | **Bloco recolhido:** cada item da lista pode recolher num cartão pequeno de uma linha com o número, o nome (se tiver) e um resumo do conteúdo, por exemplo `receita_anual = Round([mrr_mensal] * 12, 2)` ou `Soma de valor`, e o estado (válido ou com erro). Um clique no cartão expande; a seta no cabeçalho recolhe e expande. Subir, descer e excluir continuam no cabeçalho. |
| RF-4106 | **Nomear o item:** dois cliques no título (ou o lápis que aparece ao passar o mouse) dão um nome ao bloco, como "Receita anual" ou "Faixa do cliente". O nome aparece no cartão recolhido e no expandido; sem nome, aparece o número. O nome é só para quem lê: não muda o resultado nem o cache. |
| RF-4107 | **Recolher todos / Expandir todos** no topo de cada lista com dois itens ou mais. Item recém-adicionado nasce expandido; item com erro de validação mostra o erro também recolhido e abre ao clicar. |
| RF-4108 | Os nomes e o que está recolhido ficam guardados no fluxo, por caixa, fora da configuração que o motor lê; fluxos antigos abrem com tudo expandido. |

### Canvas: recolher (extra)

| ID | Requisito |
|----|-----------|
| RF-4101 | **Caixa compacta:** no menu da caixa (e com várias selecionadas), *Recolher* deixa a caixa num bloco pequeno só com o ícone e as portas; o nome aparece ao passar o mouse. Os selos de erro, aviso, fonte ausente e amostra continuam visíveis. Dois cliques ou *Expandir* voltam ao tamanho normal. |
| RF-4102 | **Etapa recolhida:** no menu da etapa, *Recolher* troca a moldura e suas caixas por um cartão com o nome, a cor, quantas caixas tem, uma fileira com os ícones das caixas e o estado do conjunto (ok, com erro, com amostra). Os fios que entram e saem da etapa passam a ligar no cartão, agrupados quando vão para a mesma caixa. *Expandir* devolve tudo na mesma posição. |
| RF-4103 | **Exibir → Recolher todas as etapas / Expandir todas** e **Recolher as caixas desativadas**. *Ajustar à tela* considera a etapa recolhida pelo tamanho do cartão. |
| RF-4104 | Recolher é só desenho: não muda a execução, o resultado, o SQL nem a assinatura de cache. O estado fica guardado no fluxo (`collapsed`) e fluxos antigos abrem expandidos. Selecionar uma caixa por busca, erro ou "Faltam neste computador" expande o que for preciso para mostrá-la. |

### Canvas: fios organizados

| ID | Requisito |
|----|-----------|
| RF-4110 | **Rota organizada:** o fio sai da porta na horizontal e segue em segmentos retos com cantos arredondados, desviando das caixas, dos cartões de etapa recolhida e dos títulos de etapa. Quando não houver caminho livre (caixas encostadas), usa a menor rota que cruza menos caixas. |
| RF-4111 | Fios que correm juntos ganham pistas separadas, para não ficarem um sobre o outro; fios que saem da mesma porta compartilham o tronco e se separam perto do destino. |
| RF-4112 | A rota é calculada ao ligar, mover, colar, alinhar ou recolher. Durante o arrasto, os fios da caixa movida ficam provisórios (curva simples) e se acomodam ao soltar, para o arrasto continuar fluido em fluxos de 200 caixas. |
| RF-4113 | **Exibir → Fios:** *Organizados* (padrão) ou *Curvos* (o desenho atual). A escolha fica guardada neste computador; o arquivo do fluxo não muda. |
| RF-4114 | **Organizar o fluxo** (menu Exibir e botão direito no canvas vazio): dispõe as caixas em colunas da esquerda para a direita, seguindo os fios, mantendo cada etapa junta. Sempre com desfazer. |

### Seletor de fontes

| ID | Requisito |
|----|-----------|
| RF-4120 | No Input Data, o campo Fonte vira um cartão com a fonte escolhida (ícone do tipo, nome de exibição, linhas, atualização) e o botão **Trocar**, que abre o seletor. Sem fonte, o cartão convida a escolher. |
| RF-4121 | **Seletor grande**, como a janela de abrir arquivo do Windows: à esquerda, as pastas da vista Dados, *Fixadas*, *Recentes* e os tipos (arquivo, pasta de arquivos, PDF, consulta, API, Jira); no centro, a lista com nome, tipo, linhas, atualização e em quantos fluxos é usada, com busca, ordenação e modo lista ou ícones; à direita, a prévia das primeiras linhas e das colunas da fonte selecionada. |
| RF-4122 | Dois cliques ou Enter escolhem; Esc fecha. O teclado navega em tudo (setas, Tab entre as áreas, digitar para buscar). Fontes em rascunho (PDF não concluído) ou que não servem aqui (API que pede variável) aparecem esmaecidas, com o motivo. |
| RF-4123 | Do seletor dá para **Enviar arquivo** e **Cadastrar** (consulta, API, Jira, PDF) sem perder o lugar; ao concluir, a fonte nova vem selecionada. |
| RF-4124 | O mesmo seletor serve para *Usar uma fonte daqui* em "Faltam neste computador" (spec 040). |

### Tabela do Designer

| ID | Requisito |
|----|-----------|
| RF-4130 | **Resumo das colunas** liga e desliga, na barra da aba Resultado e em Exibir, o minigráfico, a barra de qualidade e o total do cabeçalho. O nome, o tipo, o filtro e a ordenação ficam sempre. A escolha fica guardada neste computador. |
| RF-4131 | Com o painel de resultados baixo (menos de 260 px de altura), o resumo se recolhe sozinho, e volta quando houver espaço, a menos que a pessoa tenha escolhido. |
| RF-4132 | **Largura das colunas:** arrastar a borda direita do cabeçalho muda a largura; dois cliques ajustam ao conteúdo visível. A largura fica guardada neste computador, por caixa e coluna, e um item *Larguras automáticas* no menu da coluna volta ao padrão. |
| RF-4133 | **Célula em destaque:** clicar numa célula a destaca com um brilho na cor de destaque, e a linha e a coluna dela ficam levemente marcadas, para a leitura em cruz. Um rodapé mostra a coluna, a linha e o valor inteiro (útil para textos cortados). As setas movem o destaque, Ctrl+C copia o valor, e Esc ou um novo clique na mesma célula tiram o destaque. O destaque some ao ordenar, filtrar ou executar de novo. Vale também no visual Tabela do Dashboard, na tela e no modo apresentação. O botão direito continua com o menu de filtrar. |

### Dashboard: dica editável

| ID | Requisito |
|----|-----------|
| RF-4140 | No painel Formato de cada visual com dica (barras, linhas, área, pizza, dispersão, mapa de calor e os demais com `data-tip`), uma seção **Dica**: mostrar ou não o rótulo e o valor, o percentual do total (pizza, barras e colunas empilhadas) e a cor da série. |
| RF-4141 | **Colunas extras na dica:** escolher outras colunas da mesma saída para aparecer na dica, cada uma com a agregação do visual (por exemplo, quantidade de pedidos e ticket médio junto da receita). Como precisam ser agregadas com os dados, ficam guardadas na caixa do gráfico (também editáveis no Configurar dela) e aparecem depois de executar; vale para gráficos de uma série. |
| RF-4142 | **Texto da dica** livre com campos entre chaves (`Receita de {mês}: {valor}`), com autocompletar dos campos e prévia ao vivo. Campo que não existe aparece sublinhado, e a dica cai no padrão. |
| RF-4143 | A dica editada vale igual no Designer, no Dashboard, na linha do tempo e no HTML exportado; os nomes trocados no Formato (spec 015) continuam valendo. Texto da dica é escapado (nada de HTML vindo do dado). |

### Tempo nas caixas

| ID | Requisito |
|----|-----------|
| RF-4150 | **Exibir → Tempo nas caixas:** cada caixa executada ganha um selo com o tempo da última execução ("120 ms", "4,8 s") ou "cache". A escolha fica guardada neste computador. |
| RF-4151 | O selo tem cor pelo peso no total; as três caixas mais lentas (acima de 5% do total) ganham destaque. Etapa recolhida mostra a soma das caixas dela. |
| RF-4152 | A barra de status mostra "mais lenta: Join (4,8 s)"; o clique seleciona e mostra a caixa. |

### Laço (Loop)

| ID | Requisito |
|----|-----------|
| RF-4160 | **Duas caixas, Início do loop e Fim do loop**, criadas juntas (arrastar *Loop* da paleta cria o par numa moldura própria, com as duas ligadas). O **corpo** do laço são as caixas nos caminhos entre o Início e o Fim; a moldura do laço acompanha o corpo e mostra o modo e o número de voltas. |
| RF-4161 | **Para cada valor:** repete o corpo para cada valor distinto de uma coluna da entrada (ou de uma lista digitada), em ordem crescente ou na ordem em que aparecem. Em cada volta, a saída do Início traz só as linhas daquele valor (ou a tabela inteira, se a pessoa escolher). |
| RF-4162 | **Para cada número ou data:** de um início a um fim, com passo (número, ou dia, semana, mês, ano). Em cada volta, a saída do Início traz a tabela de entrada inteira. |
| RF-4163 | **Enquanto:** repete enquanto alguma linha do resultado da volta atender à condição escrita no Fim do loop (por exemplo, `[saldo] < [meta]`), sempre com limite de voltas. A primeira volta sempre roda. |
| RF-4164 | **Variáveis do laço** em qualquer fórmula ou campo de texto do corpo (Formula, Filter, nome de arquivo do Output Data...): `[#valor]` (o valor ou a data da volta), `[#volta]` (1, 2, 3…) e `[#total]` (quantas voltas, quando se sabe). O autocompletar mostra as variáveis só dentro do corpo; fora dele, usá-las é erro com mensagem clara. |
| RF-4165 | **O que sai no Fim:** *Empilhar* (o resultado de todas as voltas numa tabela, com a coluna `volta` e a coluna do valor; padrão), *Acumular* (o resultado de uma volta vira a entrada da próxima; o Fim entrega o da última) ou *Só a última volta*. Colunas diferentes entre voltas se juntam pelo nome, como no Union. |
| RF-4166 | **Segurança:** limite de voltas (padrão 1.000, máximo 100.000); progresso "volta 37 de 120" na barra de status e na caixa, com Cancelar; erro numa volta diz qual volta e qual valor, e para o laço. Laço dentro de laço é permitido até 3 níveis. |
| RF-4167 | **Validação do desenho:** o corpo não pode ter caixas que mandem dados para fora sem passar pelo Fim; caixas de fora podem alimentar o corpo (a tabela é a mesma em todas as voltas). Início sem Fim, Fim sem Início ou dois laços cruzados dão erro na caixa, com a explicação. |
| RF-4168 | **Resultados:** a aba Resultado de uma caixa do corpo tem um seletor de volta (primeira, última, ou escolher); o Inspector mostra o tempo por volta. O cache vale por volta: mudar uma caixa depois do laço não refaz o laço. |
| RF-4169 | **Dica antes do laço:** quando o corpo só agrupa e calcula por grupo (Summarize, Formula, Filter sobre o valor da volta) e o modo é Para cada valor, a caixa sugere o jeito sem laço (Summarize ou Multi-Row por grupo), que é mais rápido. A dica pode ser dispensada. |
| RF-4170 | **Aba SQL:** o laço é desenrolado volta a volta: cada volta vira uma cópia do corpo, com o Início trocado por um filtro do valor e as variáveis já trocadas, e o Fim empilha as cópias (`UNION ALL BY NAME`, com a coluna `volta`) ou fica com a última. Vale para Para cada valor e faixa, até 50 voltas, e é conferido com o resultado do motor; Para cada valor pede o fluxo executado (os valores vêm dos dados). Enquanto, Acumular e laço dentro de laço ficam sem tradução, com o motivo. |
| RF-4171 | **Output Data dentro do laço** grava uma vez por volta; com `[#valor]` ou uma `{coluna}` no nome do arquivo, um arquivo por valor ("vendas_[#valor].xlsx"). Sem nenhum dos dois, avisa que cada volta sobrescreve a anterior. |

### Parar e nome dinâmico

| ID | Requisito |
|----|-----------|
| RF-4190 | **Parar qualquer execução:** enquanto o fluxo executa, o botão **Executar** do topo vira **Parar** (e "Parando…" depois do clique). A caixa que está rodando termina; as seguintes ficam como "não executado: execução interrompida", e um aviso diz quantas ficaram de fora. Num laço, para na próxima volta. |
| RF-4191 | **Nome dinâmico no Output Data:** uma coluna entre chaves no nome (`vendas_{regiao}`) grava um arquivo por valor dela, com o valor limpo para nome de arquivo (caracteres proibidos viram `_`, vazio vira "vazio"), até 500 arquivos. Coluna que não existe é erro claro. Com "Perguntar", nunca sobrescreve: cria outro arquivo com data e hora. |
| RF-4192 | **Aviso de desenho do laço na hora:** as regras do RF-4167 valem também enquanto se monta o fluxo: a caixa errada ganha um selo vermelho "laço", com a explicação ao passar o mouse, antes de executar. |

### Texto e documentação

| ID | Requisito |
|----|-----------|
| RF-4180 | "Abrir grande" vira **Expandir** no editor de fórmulas; os botões de maximizar usam *Expandir / Recolher* em toda a interface. |
| RF-4181 | Guia e Manual: seção **Laços** no capítulo Automação (depois de subfluxos), recolher e fios em "Montando o fluxo", seletor de fontes em "Trazendo dados", dica editável no Dashboard e tempo nas caixas em "Organização"; prints nos dois temas e nas duas marcas. O exemplo ganha um laço (um relatório por região). |

## Fora do escopo

- Laço que roda voltas em paralelo. As voltas rodam uma depois da outra; o paralelismo fica para depois.
- Rota de fios com o arrasto em tempo real (o fio se acomoda ao soltar, RF-4112).
- Tradução para SQL do laço Enquanto, do Acumular e de laço dentro de laço (RF-4170).
- Parar uma caixa no meio do que ela está fazendo: o Parar vale entre uma caixa e outra e a cada volta de um laço (RF-4190).
- Dica com gráfico dentro (minigráfico na dica).
- Seletor de fontes para o Join "com outra fonte" e outros campos que escolhem fonte; nesta versão, o Input Data e
  "Faltam neste computador".

## Critérios de aceite

| ID | Critério | Requisitos |
|----|----------|------------|
| CA-14 | Numa Formula com 5 fórmulas, *Recolher todos* deixa 5 cartões de uma linha com nome e resumo; dar o nome "Receita anual" à primeira aparece no cartão; clicar no cartão expande só aquela. O mesmo vale nas regras do Data Quality. O resultado e o SQL não mudam. | RF-4105..4108 |
| CA-01 | Recolher uma etapa de 8 caixas deixa um cartão com 8 ícones e os fios ligados nele; executar dá o mesmo resultado e o mesmo SQL; expandir devolve as posições. | RF-4102, RF-4104 |
| CA-02 | Recolher uma caixa mantém as portas e o selo de erro; buscar a caixa pelo nome a expande. | RF-4101, RF-4104 |
| CA-03 | Ligar duas caixas com uma terceira no meio desenha um fio que contorna a do meio, sem cruzá-la; dois fios paralelos não se sobrepõem. | RF-4110, RF-4111 |
| CA-04 | Num fluxo de 200 caixas, arrastar uma caixa continua fluido e os fios se acomodam ao soltar em menos de 300 ms. | RF-4112 |
| CA-05 | Com 60 fontes em 6 pastas, o seletor acha "vendas_2026" pela busca, mostra a prévia, e Enter escolhe; o cartão do Input Data mostra a fonte. | RF-4120..4122 |
| CA-06 | Desligar o Resumo das colunas deixa só nome e tipo no cabeçalho; arrastar a borda de uma coluna muda a largura, que continua igual depois de executar de novo. | RF-4130, RF-4132 |
| CA-13 | Clicar numa célula de texto longo a destaca, marca a linha e a coluna e mostra o valor inteiro no rodapé; seta para baixo move o destaque, Ctrl+C copia, Esc tira. No visual Tabela do Dashboard, o clique também destaca. | RF-4133 |
| CA-07 | Um gráfico de barras com a dica "Receita de {mês}: {valor} · {pedidos} pedidos" mostra o texto no Dashboard e no HTML exportado. | RF-4140..4143 |
| CA-08 | Com Tempo nas caixas ligado, cada caixa mostra o tempo, a mais lenta fica destacada, e o clique na barra de status leva até ela. | RF-4150..4152 |
| CA-09 | Laço Para cada valor de `regiao` com Summarize no corpo e Empilhar dá a mesma tabela que o Summarize por região, com a coluna `volta`; na aba SQL, o laço vira um `UNION ALL` por região e a conferência bate com o resultado. | RF-4161, RF-4165, RF-4170 |
| CA-10 | Laço Enquanto com Acumular (juros até dobrar o valor) para na volta certa; com limite de 5 voltas, para na 5ª e avisa. | RF-4163, RF-4165, RF-4166 |
| CA-11 | Output Data com "relatorio_[#valor].xlsx" num laço por região grava 5 arquivos. Uma Formula fora do laço com `[#valor]` dá erro claro. | RF-4164, RF-4171 |
| CA-12 | Uma caixa do corpo que liga para fora do laço sem passar pelo Fim ganha o aviso na hora, antes de executar, e o laço não roda até corrigir. | RF-4167 |
| CA-15 | Parar um fluxo no meio de um laço longo deixa a caixa seguinte como não executada e mostra "Execução interrompida"; o botão aparece em qualquer execução. | RF-4190 |
| CA-16 | Output Data com `vendas_{regiao}` grava um arquivo por região, também dentro de um laço, sem o aviso de sobrescrever. | RF-4191 |
