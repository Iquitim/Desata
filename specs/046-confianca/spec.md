# Spec 046: confiança — fonte que muda, erros em português, versões anteriores, fio inteligente e pílula deslizante

Status: Implementada · Versão 0.9.3 · Criada: 2026-11-20

## Contexto

Diagnóstico de experiência feito depois da 0.9.2, com pesquisa de mercado (avaliações do Alteryx, KNIME, Tableau Prep,
Power Query e n8n; diretrizes de mensagens de erro da Nielsen Norman). O que mais se repete nas queixas é **perder a
confiança no fluxo**: não entender o erro, perder trabalho, descobrir tarde que a fonte mudou. Conferido no programa:

- **A fonte muda e ninguém avisa.** O programa percebe que o arquivo foi atualizado (data e tamanho) e recalcula, mas
  não guarda como era o formato (colunas e tipos). Quando a planilha passa de `valor` para `valor_total`:
  - a regra do Select para `valor` deixa de valer em silêncio;
  - uma caixa adiante quebra com um erro do motor, em inglês, longe da causa;
  - uma coluna nova passa calada até o Output, e a planilha gravada muda de formato sem ninguém perceber;
  - um tipo que mudou (`valor` virou texto por causa de uma linha "N/D") quebra uma soma lá na frente.
  Hoje só os campos de uma coluna mostram "(não existe)", e só se a pessoa abrir a caixa. Com o agendador da 0.9.2,
  isso pode acontecer às 6h da manhã, sem ninguém olhando.
- **Erros do motor chegam crus.** Os erros escritos pelo programa são claros, mas os do motor de dados (Polars) chegam
  ao usuário em inglês técnico (`unable to find column "x"; valid columns: [...]`).
- **O desfazer acaba quando o fluxo fecha.** Com o salvar automático (0.9.1), um engano é gravado na hora; depois de
  fechar o programa, não há como voltar a uma versão de ontem.
- **Ligar caixas pede pontaria.** O fio só liga se for solto exatamente sobre a entrada (14 px, que encolhem com o
  zoom). Soltar em cima da caixa não faz nada, em silêncio; soltar no vazio abre a lista de ferramentas, inclusive
  quando a pessoa só errou a caixa por pouco. A lista não sugere o que costuma vir depois.
- **A troca de vista é seca.** O destaque da vista (Dados, Designer, Dashboard, SQL) pula de um botão para outro, e o
  mesmo vale para os demais controles segmentados.

## Histórias de usuário

- Como analista, quando o arquivo de vendas muda de formato, quero saber **na entrada** o que mudou e quais caixas
  isso atinge, e consertar tudo de uma vez, em vez de caçar o erro caixa por caixa.
- Como quem agenda fluxos, quero que uma mudança perigosa na fonte **pare** a execução com uma frase clara, em vez de
  gravar uma planilha errada para o relatório de alguém.
- Como iniciante, quero que o erro diga em português o que aconteceu e me ofereça o conserto.
- Como quem usa o salvar automático, quero **voltar a uma versão anterior** do fluxo, mesmo depois de fechar o programa.
- Como quem monta fluxos o dia todo, quero ligar caixas **sem pontaria**, e saber antes de soltar o que vai acontecer.

## Requisitos

### A. Mudanças na fonte

| ID | Requisito |
|----|-----------|
| RF-4601 | **Formato lembrado:** cada Input Data (arquivo, pasta de arquivos, consulta de banco, API e Jira) lembra as colunas e os tipos que leu na última execução bem-sucedida. O formato lembrado viaja dentro do fluxo e só é regravado quando muda. Guarda apenas nomes e tipos de coluna: nunca valores, caminhos ou credenciais. |
| RF-4602 | **Aviso na entrada:** quando a fonte vem com formato diferente do lembrado, o Input mostra um selo no canvas e, no Configurar, um resumo: colunas novas, colunas que sumiram e colunas que mudaram de tipo, cada uma pelo nome. A primeira leitura de uma fonte só lembra o formato, sem avisar. |
| RF-4603 | **Caixas atingidas:** o aviso diz quantas caixas usam as colunas que sumiram ou mudaram de tipo, e um clique acende essas caixas no canvas (brilho âmbar suave, com o nome da coluna). Vale para os campos de coluna das ferramentas e para as colunas citadas em fórmulas (`[coluna]`). Uma caixa SQL que cite a coluna conta como "talvez atingida", porque o texto livre não é interpretado. |
| RF-4604 | **Trocar a coluna em todas as caixas:** para uma coluna que sumiu, o aviso oferece **Trocar por…** com a lista das colunas novas e das existentes. Quando há um candidato forte (sumiu uma coluna e apareceu uma com o mesmo tipo), ele vem sugerido, mostrando o tipo da coluna que sumiu ao lado do tipo e dos primeiros valores da candidata (`valor`, número → `valor_total`, número: 120,50 · 89,90 · 15,00). Os valores antigos não aparecem porque o formato lembrado nunca guarda valores (RF-4601). A troca vale em todas as caixas que usam a coluna, de uma vez, como **um único Desfazer**. O programa nunca troca sozinho. |
| RF-4605 | **Aceitar o formato novo:** **Entendi, usar o formato novo** passa a lembrar o formato atual e apaga o aviso. Enquanto o aviso estiver aberto, o fluxo executa normalmente (com os erros que a mudança causar). |
| RF-4606 | **Tipo que mudou:** o aviso mostra até 3 valores que impediram o tipo antigo (ex.: `valor` agora é texto por causa de "N/D", "—"), para a pessoa decidir entre corrigir a fonte ou converter. |
| RF-4607 | **Execução sem ninguém olhando** (agendada ou pela linha de comando): cada Input tem, em Avançado, **Se aparecer coluna nova: Seguir (padrão) / Parar**. Uma coluna **usada** que sumiu **para sempre** a execução antes de gravar qualquer saída, com a frase "A coluna `valor` sumiu de vendas.xlsx (usada em 3 caixas)", que aparece no histórico do agendamento e no aviso de falha agendada. |
| RF-4608 | **Formato da saída:** o Output Data lembra o formato que gravou. Quando a próxima gravação vai sair diferente (coluna a mais, a menos ou com outro tipo), o resultado da caixa avisa, pelo nome das colunas, que quem consome a planilha pode ser afetado. Opção em Avançado: **Parar se o formato da saída mudar** (desligada por padrão), que vale para execuções com e sem alguém olhando. |
| RF-4609 | **Pasta de arquivos:** a comparação é com o conjunto de colunas da pasta, não com o último arquivo. Arquivos que não têm uma coluna que os outros têm aparecem na própria tabela de arquivos da pasta ("3 arquivos sem a coluna `desconto`"). |
| RF-4610 | **Como funciona** do aviso: um esquema com o formato lembrado e o atual lado a lado, as colunas novas, as que sumiram e as que mudaram de tipo marcadas, e as caixas atingidas. |

### B. Erros em português

| ID | Requisito |
|----|-----------|
| RF-4621 | Os erros mais comuns do motor de dados chegam em português simples, dizendo o que aconteceu e como resolver: coluna que não existe, coluna repetida, tipo incompatível numa conta ou comparação, conversão de número ou data que falhou, divisão inválida, memória insuficiente e arquivo em uso por outro programa. |
| RF-4622 | **Coluna que não existe** traz, junto ao erro, as colunas parecidas e a ação **Escolher outra coluna**, que leva ao campo certo da caixa; se a coluna sumiu da fonte, leva ao aviso da entrada (RF-4602). |
| RF-4623 | O texto original do motor continua disponível, recolhido, em **Detalhes técnicos**, e vai inteiro para o log. Um erro que não se encaixa em nenhum caso conhecido aparece como hoje, sem tradução inventada. |

### C. Versões anteriores do fluxo

| ID | Requisito |
|----|-----------|
| RF-4631 | **Arquivo › Versões anteriores…** lista as versões guardadas do fluxo aberto, da mais nova para a mais antiga, com quando foi, de onde veio (Salvar, salvar automático, antes de restaurar, antes de trocar colunas) e um resumo do que mudou em relação à versão de agora (caixas adicionadas, removidas e alteradas). |
| RF-4632 | **Prévia e restaurar:** escolher uma versão mostra a prévia do canvas daquela versão; **Restaurar esta versão** a coloca no lugar do fluxo aberto como uma mudança ainda não salva (Desfazer volta), e a versão de antes vira, ela mesma, uma versão guardada. |
| RF-4633 | **Quando guardar:** a cada Salvar manual; no salvar automático, no máximo uma versão a cada 10 minutos de trabalho; e sempre antes de restaurar e antes de uma troca de colunas em massa (RF-4604). Cada fluxo guarda até 30 versões; as mais antigas saem primeiro. |
| RF-4634 | As versões ficam numa pasta interna da pasta de dados deste computador (não aparecem na biblioteca, no mapa de uso nem em nenhuma lista) e não guardam a amostra dos dados (spec 040). Valem para fluxos da biblioteca e fluxos salvos em pasta; o Salvar de um fluxo salvo em pasta continua gravando só no arquivo escolhido, nunca na biblioteca. **Cada arquivo tem o seu histórico**: duas cópias do mesmo fluxo em pastas diferentes (Salvar como) não misturam versões, e o caminho do arquivo não é guardado em texto. Excluir um fluxo da biblioteca exclui as versões dele. Fluxo de exemplo, de lição e em modo protegido não guarda versões. |

### D. Fio inteligente

| ID | Requisito |
|----|-----------|
| RF-4641 | **Ímã:** enquanto o fio é puxado, ele gruda na entrada livre e compatível mais próxima, num raio de cerca de 28 px **de tela** (não encolhe com o zoom); a entrada acende antes de soltar. |
| RF-4642 | **Soltar sobre a caixa liga:** com uma entrada livre e compatível, liga direto. Com várias (ex.: L e R do Join, T e S do Append Fields), abre ali um seletor pequeno com as letras e o que cada entrada recebe. Entrada que aceita várias ligações conta como livre. |
| RF-4643 | **Onde dá para ligar:** durante o arrasto, todas as entradas compatíveis do canvas acendem de leve e as incompatíveis esmaecem. |
| RF-4644 | **Entrada ocupada:** pairar sobre uma entrada que já tem fio (e aceita só um) mostra que vai substituir: o fio antigo fica tracejado. Soltar substitui; Desfazer volta. |
| RF-4645 | **Três zonas, com etiqueta:** perto de uma entrada ou sobre a caixa, a etiqueta junto ao cursor diz **"Ligar em Filter"**; numa faixa de cerca de 60 px em volta das caixas, soltar não faz nada e o fio volta (a etiqueta some); longe de tudo, a ponta do fio vira **+** e a etiqueta diz **"Soltar para adicionar uma caixa"**, e só aí a lista de ferramentas abre. Soltar fora do canvas cancela, como hoje. |
| RF-4646 | **Próxima caixa sugerida:** a lista que abre no vazio mostra no topo as ferramentas que mais vieram depois daquela ferramenta **neste computador**, com um padrão sensato para quem começa (ex.: depois do Input Data: Select, Filter, Data Cleansing). A contagem fica só neste computador e não sai dele. |

### E. Pílula deslizante

| ID | Requisito |
|----|-----------|
| RF-4651 | Nos controles segmentados (a troca de vista no topo e os demais do programa), o destaque desliza do botão antigo ao novo, ajustando a largura no caminho, em cerca de 200 ms, desacelerando no fim, sem quique, sem brilho e sem animar o conteúdo da tela. Clicar de novo no meio do movimento muda o destino na hora. Com "reduzir movimento" ligado no sistema, a troca é instantânea. |

### Brilho com significado

| ID | Requisito |
|----|-----------|
| RF-4655 | O brilho no canvas fica reservado ao que pede atenção: caixa executando e caixa que terminou (como hoje), entrada que vai receber o fio (RF-4641) e caixas atingidas por mudança na fonte (RF-4603). Não há efeito de brilho decorativo. Tudo respeita "reduzir movimento". |

### Documentação

| ID | Requisito |
|----|-----------|
| RF-4661 | Guia e Manual com as novidades (aviso de mudança na fonte e troca de colunas, erros com conserto, versões anteriores, as três zonas do fio), com esquema visual e prints nos dois temas e nas duas marcas. README, versão 0.9.3, guias e instaladores nas duas marcas. **Todos os prints** (não só os novos) refeitos na versão, na mesma geração: o teste do Manual, o PDF e o build recusam prints de outra versão (encontrado depois da publicação: o guia misturava telas da 0.9.1, 0.9.2 e 0.9.3). |

## Fora do escopo

- Recomendações de limpeza a partir do perfil de dados (0.9.4; vão reaproveitar o aviso de tipo que mudou).
- Interpretar o texto livre da caixa SQL para trocar colunas dentro dele.
- Detectar renome por semelhança de nome sozinha (sem o mesmo tipo), ou trocar colunas sem confirmação.
- Comparar duas versões caixa a caixa, lado a lado, ou mesclar versões.
- Versões guardadas em outro computador ou na nuvem.
- Efeito neon geral nas caixas e animação de troca do conteúdo das vistas.

## Critérios de aceite

| ID | Critério | Requisitos |
|----|----------|------------|
| CA-01 | Num fluxo executado com `vendas.xlsx`, trocar o arquivo por um em que `valor` virou `valor_total` (mesmo tipo) e surgiu `desconto`: o Input mostra o selo; o aviso lista `desconto` como nova e `valor` como sumida, diz quantas caixas usam `valor` e acende essas caixas; **Trocar por…** já sugere `valor_total` com o tipo e os primeiros valores; confirmar troca em todas as caixas (Select, fórmula e Summarize), o fluxo executa sem erro, e um único Desfazer volta tudo. | RF-4601..4605 |
| CA-02 | Rodar o mesmo fluxo pela linha de comando com a coluna usada sumida para antes de gravar saídas, e o histórico do agendamento mostra a frase com a coluna, a fonte e o número de caixas; com só uma coluna nova e "Parar" escolhido, também para; com "Seguir", roda. | RF-4607 |
| CA-03 | Um Output que gravou 5 colunas e vai gravar 6 avisa no resultado; com "Parar se o formato da saída mudar", a execução para sem gravar. | RF-4608 |
| CA-04 | Uma fórmula com `[valr]` (coluna inexistente) mostra erro em português com `valor` entre as parecidas e **Escolher outra coluna**; o texto original do motor aparece em Detalhes técnicos. | RF-4621..4623 |
| CA-05 | Salvar um fluxo, apagar três caixas, salvar, fechar e reabrir o programa: Versões anteriores mostra a versão com as três caixas, a prévia as exibe, Restaurar as traz de volta como mudança não salva, e Desfazer volta ao estado sem elas. | RF-4631..4634 |
| CA-06 | Com o canvas em 50%, soltar o fio a 20 px de uma entrada liga; soltar sobre um Join livre abre o seletor L/R; soltar a 40 px de uma caixa não faz nada; soltar longe abre a lista com Select, Filter e Data Cleansing no topo (depois de um Input); a etiqueta diz o que vai acontecer em cada caso. | RF-4641..4646 |
| CA-07 | Trocar de Designer para Dashboard faz o destaque deslizar em ~200 ms; com reduzir movimento, a troca é instantânea. | RF-4651 |
