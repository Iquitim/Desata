# Spec 044: ranking e médias móveis, Append Fields mais seguro, agendador visual e aviso de fim de execução

Status: Implementada · Versão 0.9.2 · Criada: 2026-11-19

## Contexto

- **Funções de janela:** a Multi-Row Formula já traz valor anterior (LAG), próximo (LEAD), diferença, variação % e
  preencher para baixo; o Running Total acumula por grupo; o Record ID numera a tabela inteira. Faltam as perguntas mais
  comuns do analista: **"quem é o 1º, 2º, 3º de cada região?"** (ranking, com empates) e **"qual a média dos últimos
  3 meses?"** (média móvel).
- **Append Fields** já combina todas as linhas de [T] com todas as de [S] (CROSS JOIN), mas só avisa quando passa do
  limite de 10 milhões de linhas, com erro. Não diz antes quantas linhas vão sair, nem explica com desenho o que faz.
- **Agendar:** hoje o Arquivo › Executar sem abrir o programa mostra um comando `schtasks` para colar no Prompt de
  Comando, e outro horário exige editar o comando (/ST, /SC). Para quem não é de TI, o recurso fica escondido atrás de
  uma tela preta. Além disso, o `prodata-cli.exe` abre uma janela de console na hora agendada.
- **Fim da execução:** num fluxo demorado, a pessoa vai fazer outra coisa e não fica sabendo quando terminou, a não
  ser olhando a tela. Só erro e Parar avisam.
- **Seletor de fontes (correção):** na vista em ícones, nomes longos se sobrepunham aos cartões vizinhos. Corrigido
  (correção de bug, sem requisito novo): o cartão respeita a largura, e o nome usa até três linhas.

## Requisitos

### Ranking (caixa Rank)

| ID | Requisito |
|----|-----------|
| RF-4401 | **Caixa Rank** (Preparação): numera as linhas pela ordem de uma ou mais colunas (ex.: vendas, da maior para a menor), com **"Recomeçar a cada grupo"** opcional (ex.: por região). A coluna nova tem nome editável (padrão `posicao`). |
| RF-4402 | **Como tratar empates**, em três cartões, cada um com um mini-exemplo visível sem precisar ler: **Posição única** `1 2 3 4` (empate desempata pela ordem de chegada; ROW_NUMBER), **Empate divide e pula** `1 1 3 4` (RANK) e **Empate divide sem pular** `1 1 2 3` (DENSE_RANK). O nome técnico aparece pequeno, para quem vem do SQL. |
| RF-4403 | **Manter só os primeiros:** opção para ficar só com as N primeiras posições de cada grupo ("top 3 por região"). Com empates em "divide", o painel avisa que podem vir mais de N linhas. |
| RF-4404 | A saída sai na ordem do ranking (grupo, depois posição). Vazios na coluna de ordem ficam por último, nas duas direções. |
| RF-4405 | **Como funciona** da caixa: uma tabela pequena (com a amostra dos dados, depois de executar; com um exemplo, antes) mostra as linhas em ordem, a posição calculada e os empates destacados com a mesma cor; com grupos, as posições recomeçam visivelmente a cada grupo. |
| RF-4406 | Igual no motor e no SQL (aba SQL e equivalência testada), inclusive empates, vazios e top N. Pesquisar "rank", "ranking", "top", "posição", "row_number", "dense_rank" na paleta encontra a caixa. |

### Média e soma móvel (Multi-Row Formula)

| ID | Requisito |
|----|-----------|
| RF-4411 | Duas receitas novas na Multi-Row: **Média móvel** e **Soma móvel**, com "Quantas linhas na janela" (2 a 24; padrão 3). A janela é a linha atual e as anteriores, respeitando Ordenar por e Agrupar por. |
| RF-4412 | Enquanto ainda não há linhas suficientes para a janela (as primeiras de cada grupo), o resultado fica vazio, e o Como funciona diz isso. Uma janela com valor vazio no meio dá vazio. |
| RF-4413 | Como nas outras receitas, a fórmula sai pronta e visível (sem caixa-preta), o SQL é gerado, e o **Como funciona** acende a janela inteira de cada linha (as N linhas que entram na conta), não só a vizinha. |

### Append Fields

| ID | Requisito |
|----|-----------|
| RF-4421 | **Estimativa antes de executar:** com as entradas já executadas, o painel mostra "[T] 1.200 linhas × [S] 3 linhas = 3.600 linhas" e o número de colunas que sai. Sem execução, explica que a conta aparece depois de executar as caixas anteriores. |
| RF-4422 | **Aviso em três níveis:** até 100 mil linhas, nada; de 100 mil a 1 milhão, aviso amarelo ("vai ficar pesado"); acima de 1 milhão, aviso forte, sugerindo que [S] costuma ser uma tabela pequena de parâmetros e que, para juntar por uma coluna em comum, a caixa certa é o Join. O limite de 10 milhões continua, com o erro de hoje. Executado com mais de 100 mil linhas, a caixa também mostra o aviso depois de executar. |
| RF-4423 | **Como funciona** do Append Fields: um desenho de [T] e [S] pequenos (amostra ou exemplo) e o resultado, em que cada linha de [T] se repete para cada linha de [S], com as cores de origem; colunas repetidas aparecem com o prefixo. |
| RF-4424 | A descrição e a busca da paleta dizem "combinar tudo com tudo (CROSS JOIN)". |

### Agendador visual (Windows)

| ID | Requisito |
|----|-----------|
| RF-4431 | **Agendar o fluxo aberto** (Arquivo › Agendar…), num diálogo visual, sem comando para colar: frequência em botões (**Todo dia**, **Dias da semana**, **Todo mês**, **A cada X horas**), horário, dias da semana em fichas clicáveis, dia do mês. Uma frase de resumo acompanha cada escolha: "Roda de segunda a sexta às 06:00 · próxima: amanhã, 06:00". |
| RF-4432 | **Opções em linguagem simples:** "Se o computador estiver desligado na hora, rodar assim que ligar" (ligado por padrão), "Acordar o computador para rodar" (desligado por padrão) e "Rodar também na bateria" (ligado por padrão). |
| RF-4433 | **Antes de agendar:** fluxo novo ou com mudanças não salvas oferece **Salvar e agendar** (o agendamento roda a versão salva). Fluxo de fora ainda não confiado não agenda, e o diálogo diz por quê. |
| RF-4434 | **Agendamentos** (Arquivo › Agendamentos…): a lista dos fluxos agendados neste computador, com frequência em frase, próxima execução, última execução (quando, quanto tempo, deu certo, falhou ou foi recusada, com a mensagem) e as ações **Executar agora**, **Pausar/Retomar**, **Editar** e **Excluir** (com confirmação). |
| RF-4435 | **Falha visível:** se uma execução agendada falhou desde a última vez que a pessoa olhou, o app avisa ao abrir (e enquanto aberto), com o nome do fluxo, o horário e o erro, e um botão para ver os detalhes. |
| RF-4436 | **Sem janela na hora agendada:** a execução agendada roda em silêncio, sem console e sem tela de abertura. O histórico fica na pasta de dados. |
| RF-4437 | **Coerência com o Windows:** a tarefa aparece no Agendador de Tarefas com o nome da marca e do fluxo. Se a pessoa apagou a tarefa por lá, a lista mostra "Removido no Agendador do Windows" com **Recriar**. Fluxo da biblioteca excluído pergunta se exclui o agendamento junto. Se a política da empresa bloquear a criação de tarefas, o diálogo explica e oferece a linha de comando (o caminho de hoje). |
| RF-4438 | **Segurança:** o agendamento roda só com a pessoa conectada ao Windows, nunca pede nem guarda a senha do Windows, e o diálogo explica isso numa frase. Fluxo de fora continua recusado na hora de rodar enquanto não for confiado (spec 028). A linha de comando continua disponível em "Avançado" no diálogo. Fora do Windows, o diálogo mostra só a linha de comando. |
| RF-4439 | **Desativar e excluir à vista:** cada agendamento da lista tem um interruptor **Ativo** (desativado, a tarefa continua no Windows mas não roda) e os botões **Editar** e **Excluir** com nome; o Editar também tem o interruptor e **Excluir agendamento**, com confirmação. |

### Aviso de fim de execução

| ID | Requisito |
|----|-----------|
| RF-4441 | Ao terminar uma execução pedida pela pessoa (Executar ou Executar até aqui), uma caixinha no canto, **com as cores da marca**, avisa: nome do fluxo, quanto tempo levou, quantas caixas executaram e, quando houver, quantos arquivos foram gravados. Com erro, a mesma caixa em tom de erro diz quantas caixas falharam e leva ao Log. Parada pelo Parar, diz que foi interrompida. Execuções automáticas (ao abrir o fluxo) não avisam. |
| RF-4442 | Com a janela do programa em segundo plano, o aviso fica até a pessoa voltar e fechar; com a janela em primeiro plano, some sozinho em alguns segundos. Um botão leva ao resultado (Log ou a caixa de saída). |
| RF-4443 | **Exibir › Aviso ao terminar a execução** liga e desliga (ligado por padrão), lembrado neste computador. |

### Menu Exibir

| ID | Requisito |
|----|-----------|
| RF-4444 | **Exibir enxuto, com submenus:** o que é escolha entre opções (Painéis com Restaurar layout padrão, Densidade, Fios, Etapas e caixas, Números) abre ao lado, ao passar o mouse, com o valor atual à direita; o que liga e desliga (Tempo nas caixas, Resumo das colunas, Aviso ao terminar) fica à vista, com a marca de ligado. Teclado: setas andam, → abre e ← volta. Os menus de botão direito ganham o mesmo suporte. |

### Documentação

| ID | Requisito |
|----|-----------|
| RF-4451 | Guia e Manual com as novidades: Rank, médias móveis, Append Fields, agendador e aviso de fim; prints nos dois temas e nas duas marcas; uma lição guiada curta de Rank (top 3 por grupo). Versão 0.9.2, guias e instaladores nas duas marcas. |

## Fora do escopo

- Agendador visual no Mac e no Linux (cron/launchd): a tela é feita de forma que dê para acrescentar depois.
- Rodar agendado com ninguém conectado ao Windows (exigiria guardar a senha do Windows).
- Notificação do sistema (central de notificações do Windows) para execuções agendadas bem-sucedidas.
- Parâmetros visuais na consulta SQL e diagnóstico de desempenho (versões futuras).
- Percentil, NTILE e janelas centradas.

## Critérios de aceite

| ID | Critério | Requisitos |
|----|----------|------------|
| CA-01 | Um Rank por vendas, decrescente, por região, com "Empate divide e pula" e top 2 dá as mesmas linhas no motor e no SQL; dois vendedores empatados na 1ª posição saem os dois com 1, e o seguinte com 3. | RF-4401..4406 |
| CA-02 | A receita Média móvel de 3 linhas, ordenada por mês e agrupada por UF, dá vazio nas duas primeiras linhas de cada UF e a média das três a partir da terceira, igual no SQL; o Como funciona acende três linhas. | RF-4411..4413 |
| CA-03 | Com [T] de 2.000 linhas e [S] de 100 executadas, o Append Fields mostra "200.000 linhas" e o aviso amarelo antes de executar; o Como funciona mostra cada linha de [T] repetida para cada linha de [S]. | RF-4421..4424 |
| CA-04 | Agendar um fluxo salvo para "Dias da semana, seg a sex, 06:00" cria a tarefa no Agendador do Windows sem console; a lista mostra a próxima execução certa; Executar agora roda o fluxo e a lista mostra a última execução com sucesso; Pausar desativa a tarefa no Windows; Excluir a remove. | RF-4431..4434, RF-4436, RF-4437 |
| CA-05 | Uma execução agendada que falhou aparece como aviso ao abrir o app, uma vez; fluxo não confiado não agenda. | RF-4433, RF-4435, RF-4438 |
| CA-06 | Executar o fluxo de exemplo mostra a caixinha com as cores da marca, com o tempo e as caixas executadas; com a opção desligada em Exibir, nada aparece; abrir o fluxo (execução automática) não mostra. | RF-4441..4443 |
