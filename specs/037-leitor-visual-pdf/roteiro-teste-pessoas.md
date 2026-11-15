# Roteiro de teste com pessoas: leitor de PDF (spec 037)

Objetivo: confirmar que alguém que nunca viu o editor consegue **marcar no PDF, ver o dado nascer e rastrear a
origem** sem ajuda, e achar os pontos em que a tela confunde. São cinco pessoas, 30 minutos cada, de preferência de
controladoria ou operações, que hoje copiam dados de PDF para planilhas.

## Preparação

- Desata 0.8.5 instalado, com o fluxo de demonstração aberto. Sem nenhum leitor de PDF cadastrado.
- Quem conduz só observa e anota. Não explica a tela. Se a pessoa travar por mais de 2 minutos, dá a dica da tarefa
  e anota como "precisou de ajuda".
- Pedir que a pessoa pense em voz alta.

## Tarefas

Cada tarefa tem o que se espera ver e o que anotar.

1. **"Você recebeu relatórios de vendas em PDF. Traga o total líquido para uma tabela."**
   - Espera-se: Dados > Adicionar > PDF > Usar os PDFs de exemplo; clique no valor; Enter (ou Criar campo).
   - Anotar: achou o caminho sozinha? Leu a prévia em cima da seleção? Entendeu "à direita de 'Total líquido'"?
2. **"Traga também a competência, sem usar o mouse."**
   - Espera-se: setas, Shift, Enter. Anotar se percebeu que dá pelo teclado (dica do estado vazio).
3. **"Traga a tabela de filiais, com uma linha por filial."**
   - Espera-se: arrastar sobre a tabela e T. Anotar se notou que a observação de duas linhas virou uma linha só e se
     entendeu "nova linha quando 'filial' tem valor".
4. **"De onde veio o valor do Rio de Janeiro na página 2?"**
   - Espera-se: clicar na célula e ver a página rolar e destacar. Anotar o tempo até achar.
5. **"Um dos relatórios tem um problema. Qual é, e o que você faria?"**
   - Espera-se: Testar em outros arquivos; o de dezembro está Ambíguo; Corrigir só neste documento ou usar outro
     rótulo. Anotar se entendeu que nada foi escolhido sozinho.
6. **"Use esse resultado num fluxo. O que acontece com o relatório problemático?"**
   - Espera-se: Adicionar ao fluxo; Executar; ler a mensagem da política Parar. Anotar se a mensagem foi entendida e
     se a pessoa achou onde trocar a política.

## Perguntas ao final

- De 1 a 5, quão fácil foi marcar um dado? E conferir de onde veio?
- Em algum momento achou que o Desata escolheu um valor sem avisar?
- O que você esperava que acontecesse e não aconteceu?

## Critério de sucesso

- 4 de 5 pessoas concluem as tarefas 1, 3 e 4 sem ajuda.
- Todas entendem, na tarefa 5, que o documento com dois totais não teve valor escolhido.
- Nenhuma confunde "Corrigir só neste documento" com mudar a regra.

## Registro

Uma linha por pessoa e tarefa: concluiu (sim, com ajuda, não), tempo, o que confundiu, citação marcante. Os achados
viram tarefas numa spec de ajuste, com print do momento em que a pessoa travou.
