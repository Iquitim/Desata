# Spec 048: equipe completa e dados mais limpos — definições da equipe, comentários, juntar caixa por caixa, recomendações de limpeza e benchmark

Status: Em revisão · Versão 0.9.5 · Criada: 2026-11-22 · Constituição 1.7.0 (princípios IV e VIII)

## Contexto

A 0.9.4 (spec 047) trouxe o espaço da equipe: a pasta compartilhada com papéis, assinaturas, quem está editando,
versões com autor, conflito sem perda e versão oficial. Três coisas ainda fazem o time tropeçar:

- **Cada um cadastra as próprias fontes.** O fluxo do espaço usa a consulta "Vendas" e a constante "Meta", mas
  elas vivem no computador de quem criou. O colega abre o fluxo e vê "Faltam neste computador".
- **A conversa acontece fora do fluxo.** "Por que esse filtro tira as devoluções?" vai por e-mail ou Teams e se
  perde; quem abre o fluxo depois não sabe.
- **No conflito, é uma versão ou a outra.** Quando duas pessoas mudam partes diferentes do mesmo fluxo, hoje alguém
  refaz à mão o que o outro fez.

Duas melhorias valem para todos, com ou sem equipe:

- **Recomendações de limpeza.** O perfil de dados já encontra espaços sobrando, número guardado como texto e datas
  em texto, mas só mostra. A 0.9.3 criou a peça que faltava (o aviso de "tipo mudou", com exemplos dos valores e a
  caixa inserida no lugar certo); agora o perfil passa a oferecer **Corrigir**.
- **Benchmark no repositório.** Os números de desempenho do README vêm de medições pontuais que ninguém reproduz.

As premissas da spec 047 continuam: **opcional** (sem espaço, nada muda), **sincronização não é confiável** e
**detectar e recusar, não fingir bloquear**. E uma nova, da constituição 1.7.0: **segredo não viaja**. Uma conexão
ou API da equipe vai para a pasta sem senha, token ou chave; cada pessoa digita o seu uma vez, no próprio cofre.

## Histórias de usuário

- Como analista de uma equipe, quero abrir o fluxo do colega e ele rodar, porque a consulta, a conexão e as
  constantes que ele usa já estão no espaço; só a minha senha do banco eu digito, uma vez.
- Como coordenador, quero que ninguém troque o servidor de uma conexão da equipe sem que os outros percebam.
- Como revisor, quero deixar uma pergunta na caixa do filtro e que o autor veja ao abrir o fluxo.
- Como quem salvou ao mesmo tempo que um colega, quero juntar o que cada um fez sem refazer nada à mão, e escolher
  só onde os dois mexeram na mesma caixa.
- Como quem recebe uma planilha suja, quero ver "12 valores com espaço no fim · Corrigir" e não precisar saber qual
  ferramenta resolve.
- Como quem mantém o programa, quero medir o desempenho com um comando e comparar com a versão anterior.

## Requisitos

### Definições da equipe: constantes, conexões, consultas e APIs

| ID | Requisito |
|----|-----------|
| RF-4801 | **Da equipe, na vista Dados.** Para cada espaço em que a pessoa é membro, a vista Dados ganha a pasta **Da equipe · Controladoria**, com as constantes, conexões, consultas e APIs do espaço, no mesmo formato das de hoje (situação, prévia, onde é usada). Editor ou acima cria, edita e exclui; Leitor usa. Sem espaço, a vista Dados fica igual à de hoje (RF-4808). |
| RF-4802 | **Levar para a equipe.** Uma constante, conexão, consulta ou API deste computador ganha **Compartilhar com a equipe…**: escolhe o espaço e vai uma cópia, **sem a senha ou o token**. A consulta leva junto a conexão que ela usa, e a API leva as variáveis que não são segredo. O identificador continua o mesmo, para os fluxos não mudarem. A cópia local continua onde estava, e a vista Dados mostra que existe uma da equipe com o mesmo nome. |
| RF-4803 | **Qual vale.** Num fluxo do espaço, a definição da equipe vale sobre a deste computador com o mesmo identificador (constante: o mesmo nome). Fora do espaço, nada muda. Quando as duas existem e são diferentes, a vista Dados avisa ("a da equipe aponta para outro servidor") e o fluxo do espaço usa a da equipe. |
| RF-4804 | **Segredo por pessoa.** A primeira vez que um fluxo usa uma conexão ou API da equipe que pede senha ou token, o programa pede **"Sua senha para a conexão Vendas (servidor srv-bi, usuário ana)"**, guarda no cofre deste computador e não pergunta de novo. **Trocar a minha senha** fica na própria definição. Nada disso vai para a pasta, para o fluxo ou para um log. |
| RF-4805 | **Assinadas.** Cada definição da equipe é assinada por quem salvou, como as versões dos fluxos (spec 047). Uma definição mexida fora do programa, ou salva por quem não é Editor, aparece como **Não confere**, com o motivo, e nenhum fluxo a usa: a caixa que depende dela não executa e diz por quê. |
| RF-4806 | **Mudança sensível pede conferência.** Quando um colega muda o que decide onde o fluxo lê (o servidor, o banco ou o tipo de uma conexão; o endereço ou os parâmetros de uma API; o SQL de uma consulta), quem usa vê a mudança na faixa de confiança dos fluxos que dependem dela, com quem mudou e quando, e confere antes de executar (mesma conferência por diferença da spec 047). Nome, descrição e pasta não pedem nada. |
| RF-4807 | **Faltam neste computador, resolvido.** Num fluxo do espaço, uma fonte que falta aqui mas existe na equipe é usada sem perguntar nada (aparece como "Da equipe"). Uma que não existe nem aqui nem na equipe continua em "Faltam neste computador", agora com **Compartilhar com a equipe** para quem tem a fonte. |
| RF-4808 | **Sem espaço, nada muda.** A garantia da spec 047 (RF-4702) inclui a vista Dados: sem espaço, nenhuma pasta, selo ou botão de equipe; o teste automatizado da 0.9.4 cobre a vista Dados. |

### Comentários nas caixas

| ID | Requisito |
|----|-----------|
| RF-4811 | **Comentar uma caixa.** Num fluxo do espaço, o menu da caixa (clique direito e o `…` do Configurar) ganha **Comentar**. O comentário tem texto (até 2.000 caracteres), autor e quando. Qualquer membro comenta, inclusive o Leitor (revisar é ler e perguntar). |
| RF-4812 | **Ver na caixa.** A caixa com comentários ganha um selo com a quantidade; passar o mouse mostra o último. Clicar abre a conversa da caixa, ao lado do Configurar, com **Responder** e **Resolver**. Comentário resolvido some do selo e fica em "Resolvidos". |
| RF-4813 | **Todos os comentários do fluxo.** Um painel **Comentários (3)** lista a conversa de todas as caixas, as abertas primeiro; clicar num comentário seleciona a caixa. Comentário de uma caixa que foi excluída fica como "em caixa removida", com o rótulo que ela tinha. |
| RF-4814 | **O que é novo.** Ao abrir o fluxo, os comentários que chegaram desde a última vez aparecem marcados ("2 novos"), como a faixa "Atualizado por" (spec 047). |
| RF-4815 | **Onde ficam.** Um arquivo por comentário na pasta do espaço, assinado por quem escreveu (constituição, princípio VIII): nunca no arquivo do fluxo, então comentar não cria versão nem conflito, e duas pessoas comentando ao mesmo tempo não brigam pela sincronização. Editar e apagar só o próprio comentário; um Administrador pode apagar qualquer um. Comentário sem assinatura válida não aparece. |
| RF-4816 | Comentários existem só em fluxos do espaço. Fora de um espaço, o item Comentar não aparece. |

### Juntar duas versões caixa por caixa

| ID | Requisito |
|----|-----------|
| RF-4821 | **Juntar as duas.** O aviso de conflito (spec 047, RF-4761) ganha **Juntar as duas**, e Versões anteriores ganha **Juntar com a que está aberta** numa versão de outra pessoa. |
| RF-4822 | **O que não conflita entra sozinho.** O programa compara as duas versões com a versão de onde as duas partiram (a base). O que só um dos dois mudou entra direto: caixa nova, caixa excluída, configuração mudada, fio novo ou removido. A janela mostra o resumo ("8 mudanças juntadas sozinhas: 3 do Bruno, 5 suas"). |
| RF-4823 | **Escolher onde os dois mexeram.** Cada caixa que os dois mudaram aparece com as duas configurações lado a lado, em palavras ("Filtro: `[valor] > 0` · `[valor] > 100`"), e a escolha **A minha** ou **A do Bruno**. Caixa que um mudou e o outro excluiu pergunta se fica ou sai. Posição das caixas não pergunta (fica a sua). |
| RF-4824 | **Prévia antes de aplicar.** A prévia do canvas mostra o resultado, com as caixas que vieram de cada um marcadas. **Aplicar** coloca o resultado no fluxo aberto como mudança não salva (um Desfazer volta); as duas versões de origem continuam em Versões anteriores. Salvar grava a versão juntada, assinada por quem juntou. |
| RF-4825 | **Sem base conhecida.** Quando não dá para achar a base (cópia de conflito sem histórico), o programa avisa e compara as duas direto: toda caixa diferente vira uma escolha. |
| RF-4826 | Um fluxo juntado que ganhou parte sensível do colega passa pela conferência por diferença ao executar (spec 047, RF-4741), como qualquer outra mudança. |

### Recomendações de limpeza (para todos)

| ID | Requisito |
|----|-----------|
| RF-4831 | **O perfil sugere.** No Perfil de uma caixa, cada coluna com problema comum ganha uma recomendação em uma linha, com a contagem e exemplos: espaço no começo ou no fim ("12 valores com espaço no fim"), número guardado como texto (com os valores que impedem, como "N/D"), data guardada como texto, mesmo valor escrito com maiúsculas diferentes ("SP", "sp"), texto vazio misturado com vazio de verdade, e linhas repetidas por inteiro. |
| RF-4832 | **Corrigir.** Cada recomendação tem **Corrigir**, que mostra antes o que muda ("12 valores; 'SP ' vira 'SP'") e, ao confirmar, insere logo depois da caixa a ferramenta que já existe, configurada (Data Cleansing, Select com troca de tipo, Formula, Unique). Um Desfazer volta. Nada é corrigido sozinho. |
| RF-4833 | **Mesma linguagem do "tipo mudou".** O número como texto por causa de "N/D" usa o mesmo cartão, os mesmos exemplos e a mesma inserção do aviso de mudança na fonte (spec 046), para a pessoa reconhecer o padrão. |
| RF-4834 | **Sem barulho.** Aparecem no máximo três recomendações por caixa, as que atingem mais linhas, com **Ver todas**. **Ignorar nesta coluna** guarda a escolha no fluxo (vale para quem abrir depois). No canvas, só um ponto discreto na caixa indica que há recomendação; nenhum aviso abre sozinho. Ajuste da 0.9.6: o ponto fica na caixa onde o problema surge (de entrada ou do meio do fluxo) e não se repete nas caixas seguintes que só herdam o mesmo problema; o Perfil de qualquer caixa mostra a lista completa. |
| RF-4835 | A recomendação vale para o que a caixa entrega, então uma correção já feita depois dela não é sugerida de novo (a caixa seguinte já resolve). |
| RF-4836 | **Número em texto: brasileiro por padrão, estrangeiro reconhecido.** Na conversão de texto em número (Select com troca de tipo, recomendações de limpeza, aviso de "tipo mudou" e a tradução para SQL), o formato é decidido **pela coluna inteira**: valores que só existem no padrão americano ("1,234.56", "3.75", "1,234,567") contam como americano; os que só existem no brasileiro ("1.234,56", "12,5", "1.234.567") contam como brasileiro; vence o que tiver mais. Coluna ambígua (só "1.200") ou empatada fica no **padrão brasileiro**: "1.200" é mil e duzentos. O Select ganha **Números no texto**: Automático (o padrão), Brasileiro ou Americano. Quando o automático lê uma coluna no formato americano, a caixa avisa. A tradução para SQL decide do mesmo jeito, pela coluna. |

### Benchmark

| ID | Requisito |
|----|-----------|
| RF-4841 | **`scripts/benchmark.py`** gera dados de teste (100 mil, 1 milhão e 5 milhões de linhas, numa pasta temporária) e mede fluxos típicos: ler CSV e Excel, Filter, Formula, Join, Summarize, Union, Sort e um fluxo de fechamento inteiro, e também abrir o programa e reexecutar sem mudanças. Mede tempo e pico de memória, com três repetições (vale a mediana). |
| RF-4842 | **Resultado legível.** Grava uma tabela em Markdown e um JSON com a máquina (processador, núcleos, memória, Windows) e a versão. `--comparar <resultado anterior>` mostra o que ficou mais de 20% mais lento ou mais rápido. |
| RF-4843 | O README cita os números do benchmark, com a máquina e a data, no lugar de "ainda não há um script que os reproduza". |

### Documentação

| ID | Requisito |
|----|-----------|
| RF-4851 | Guia e Manual: o capítulo Trabalhar em equipe ganha definições da equipe, comentários e Juntar as duas; o capítulo Dados que dá para confiar ganha as recomendações de limpeza. Prints nos dois temas e nas duas marcas, README, versão 0.9.5, guias e instaladores nas duas marcas. |

## Fora do escopo

- Menções e notificações ("@Bruno") e avisos fora do programa (e-mail, Teams).
- Comentários em fluxos fora de um espaço.
- Fontes de arquivo, pasta de arquivos e PDF da equipe: os dados nunca vão para a pasta do espaço (princípio IV). O
  fluxo continua apontando cada arquivo em cada computador, com a ajuda de "Faltam neste computador".
- Conexões do Jira da equipe (a conexão do Jira fica por pessoa, como hoje).
- Juntar caixa por caixa dentro da configuração (escolher só uma fórmula de uma lista): a escolha é a caixa inteira.
- Edição simultânea em tempo real; servidor ou nuvem próprios; Mac e Linux.

## Critérios de aceite

| ID | Cenário | Requisitos |
|----|---------|------------|
| CA-01 | Sem espaço, a vista Dados, o menu da caixa e o Perfil (sem as recomendações, que valem para todos) ficam iguais aos de antes; o teste da garantia do opcional passa. | RF-4808, RF-4816 |
| CA-02 | Ana compartilha a consulta "Vendas" com a equipe; a pasta do espaço não tem senha nenhuma. Bruno abre o fluxo da Ana, digita a própria senha uma vez e o fluxo roda. | RF-4802, RF-4804, RF-4807 |
| CA-03 | Bruno troca o servidor da conexão da equipe; Ana abre o fluxo e confere só essa mudança antes de executar. A conexão editada à mão na pasta aparece como Não confere e nada a usa. | RF-4805, RF-4806 |
| CA-04 | Bruno, Leitor, comenta na caixa do filtro; Ana abre o fluxo, vê "1 novo", responde e resolve. Comentar não cria versão nem conflito. | RF-4811..4815 |
| CA-05 | Ana muda o Filter e Bruno muda o Summarize ao mesmo tempo; Juntar as duas junta sozinho, sem perguntar nada. Os dois mudam o mesmo Filter; a janela pergunta só essa caixa, e o resultado aplicado volta com um Desfazer. | RF-4821..4824 |
| CA-06 | Uma planilha com "SP " e "N/D" numa coluna de valores: o Perfil mostra as duas recomendações, Corrigir mostra o antes e depois e insere a caixa certa; Desfazer volta. | RF-4831..4834 |
| CA-07 | `uv run python scripts/benchmark.py` roda sem rede, grava a tabela e o JSON; `--comparar` aponta uma regressão de mais de 20% criada de propósito. | RF-4841, RF-4842 |
