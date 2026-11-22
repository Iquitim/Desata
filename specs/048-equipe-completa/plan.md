# Plano da spec 048 (0.9.5)

## Marcos

1. **Definições da equipe, motor** (RF-4801..4808): guardar, assinar e resolver constantes, conexões, consultas e
   APIs do espaço; segredo por pessoa; execução de fluxo do espaço usando a definição da equipe.
2. **Definições da equipe, tela**: pasta "Da equipe" na vista Dados, Compartilhar com a equipe, pedido de senha,
   conferência por diferença das definições.
3. **Comentários nas caixas** (RF-4811..4816).
4. **Juntar caixa por caixa** (RF-4821..4826).
5. **Recomendações de limpeza** (RF-4831..4835).
6. **Benchmark** (RF-4841..4843).
7. **Documentação e publicação** (RF-4851).

Ao fim de cada marco: testes, conferência na tela, commit e push (como na 0.9.4).

## Formato na pasta do espaço

```
_equipe/
  definicoes/<tipo>/<id>.json        tipo: constantes, conexoes, consultas, apis (sem senha, token ou chave)
  definicoes/<tipo>/<id>.json.sig    assinatura de quem salvou (tipo "definicao")
  comentarios/<fluxo>/<AAAAMMDD-HHMMSS-ffffff>-<usuário>-<acaso>.json   um evento por arquivo, assinado
```

- **Definições**: o JSON é o mesmo modelo de hoje (`Connection`, `SavedQuery`, `ApiSource`, `Constant`), validado ao
  ler. Campos de segredo nunca são gravados: o modelo de conexão já não tem senha; o da API passa por uma lista
  explícita dos campos que podem ir (os de autenticação ficam de fora), conferida por teste. Identificadores pelo
  `ID_PATTERN`; constante pelo nome saneado.
- **Assinatura** (`team/signing.py`): `sign_document(kind, espaco, chave, conteúdo)` e `check_document(...)`, no mesmo
  formato da assinatura dos fluxos (`Signature`, com `tipo="definicao"` e `fluxo` = `<tipo>/<id>`), com papel mínimo
  Editor. Uma definição sem assinatura válida é listada como "Não confere" e não é resolvida.
- **Comentários como eventos**: `comentario`, `resposta`, `resolver`, `reabrir`, `apagar`. A conversa é a dobra dos
  eventos em ordem; um evento sem assinatura válida, ou de quem não pode (apagar comentário alheio sem ser
  Administrador), é ignorado. Arquivos pequenos e só acrescentados: duas pessoas comentando nunca escrevem no mesmo
  arquivo, e a sincronização não cria cópia de conflito.

## Resolução (qual definição vale)

- `team/definitions.py`: `TeamDefinitions(space_root, space_id)` com `list(tipo)`, `get(tipo, id)`, `save`, `delete`,
  `check`; e `Overlay`, que embrulha as lojas locais (`ConnectionStore`, `QueryStore`, `ApiStore`, `ConstantStore`):
  `get(id)` procura primeiro a definição da equipe que confere e depois a local.
- A execução ganha um **contexto de espaço**: `POST /api/execute` aceita `espaco` (a tela manda `store.space.id`), e o
  `run --agendamento` de um fluxo do espaço já sabe o espaço pelo alvo `espaco:<id>/<fluxo>`. Com contexto, o runner
  recebe as lojas embrulhadas; sem contexto, as de sempre (nada muda fora do espaço).
- **Segredo por pessoa**: chave no cofre `equipe:<espaço>:<tipo>:<id>` (a mesma `SecretStore` de hoje). Sem o
  segredo, a leitura falha com o código `needs_secret` e a mensagem com o nome da conexão, o servidor e o usuário; a
  tela abre o pedido de senha e tenta de novo.
- **Conferência por diferença** (`team/trust_diff.py`): `sensitive_parts` passa a incluir, para cada caixa que lê uma
  fonte da equipe, a impressão das partes sensíveis da definição (servidor, banco e tipo da conexão; endereço e
  parâmetros da API; SQL da consulta). Uma mudança do colega muda a parte e pede conferência, com o resumo legível
  ("Consulta Vendas: servidor srv-bi → srv-bi2, por Bruno").

## Juntar (`team/merge.py`)

- Função pura `merge(base, mine, theirs) -> MergeResult` sobre os modelos `Workflow`: caixas e etapas por id
  (configuração, rótulo, desativada), fios como conjunto de ligações, nome e descrição do fluxo. Cada diferença é
  classificada: só minha, só dele, igual nos dois (entra uma vez) ou conflito. Posição: sempre a minha.
- `apply(result, choices) -> Workflow` monta o fluxo final; fio que liga caixa que saiu é descartado, com aviso.
- Base: a versão com a impressão `store.space.base` (`SpaceVersions.find`); sem ela, base vazia e tudo o que difere
  vira escolha (RF-4825).
- API: `POST /api/equipe/espacos/{id}/fluxos/{wid}/juntar` `{atual, outra: "trabalho" | <versão>, base}` devolve o
  resumo e os conflitos com a descrição em palavras; `POST …/juntar/aplicar` com as escolhas devolve o fluxo.

## Recomendações de limpeza (`engine/cleaning.py`)

- `recommend(df, ignored) -> list[Recommendation]` sobre o resultado da caixa (amostra limitada, como o Perfil):
  espaços nas pontas, número como texto (com os valores que impedem), data como texto, caixa diferente no mesmo valor,
  texto vazio e linhas repetidas. Cada recomendação traz contagem, até 5 exemplos, a prévia "antes → depois" e a
  correção: tipo de ferramenta e configuração já pronta (`prep.data_cleansing`, `prep.select` com troca de tipo,
  `prep.formula`, `prep.unique`).
- Reaproveita o que a spec 046 criou para o "tipo mudou" (`schema_drift`: exemplos dos valores que mudam o tipo) e a
  inserção de caixa depois de outra com religação dos fios (`actions.js`).
- "Ignorar nesta coluna": `Workflow.ignored_cleaning: dict[node_id, list[str]]` (vazio fica fora do arquivo), coberto
  pelo `contexto-ia.md`.
- API: as recomendações vêm junto do Perfil da caixa (`/api/profile/...`), calculadas sob demanda.

## Benchmark (`scripts/benchmark.py`)

- Dados gerados com semente fixa (Polars), numa pasta temporária; os fluxos montados por código e executados pelo
  `Runner` (como o CLI). Tempo por `perf_counter`, pico de memória pelo processo (`psutil` só no script, via
  `uv run --with psutil`). Três repetições, mediana.
- Saída: `benchmark-<versão>-<data>.md` e `.json` na pasta escolhida (`--saida`, padrão: a temporária). `--comparar`
  lê um JSON anterior. `--rapido` só com 100 mil linhas (para conferir que roda).

## Tela

- Vista Dados: pasta "Da equipe · <espaço>" por espaço, com selo "Da equipe" nos itens; ação Compartilhar com a
  equipe…; aviso de definição local e da equipe diferentes; Trocar a minha senha.
- Pedido de senha: diálogo único, reaproveitado por conexões e APIs, chamado quando a execução devolve `needs_secret`.
- Comentários: selo na caixa (`canvas_nodes.js`), conversa ao lado do Configurar, painel Comentários (aba no painel
  direito), "N novos".
- Juntar: `merge_dialog.js` com o resumo, a lista de escolhas (lado a lado, em palavras), a prévia do canvas
  (reaproveitando a prévia das Versões anteriores) e Aplicar.
- Perfil: cartão de recomendações (no máximo três, Ver todas), Corrigir com antes e depois, Ignorar; ponto discreto
  na caixa.

## Testes

- Unidade: assinatura e resolução das definições (a da equipe vence só no espaço; a que não confere não é usada;
  nenhum segredo na pasta, inclusive campos de autenticação da API); segredo por pessoa; conferência por diferença com
  definição mudada; dobra dos comentários (eventos forjados e apagar alheio ignorados); `merge` (só meu, só dele,
  igual, conflito, excluído por um e mudado pelo outro, sem base); `recommend` em cada tipo de problema e na correção
  já feita depois.
- API: compartilhar, executar com contexto de espaço, `needs_secret`, comentários, juntar e aplicar.
- Garantia do opcional (CA-01) estendida à vista Dados e ao menu da caixa.
- Tela: `conferir_tela.py` ganha `equipe5` (definições com duas pessoas, comentários, juntar) e `limpeza`.
- Sincronização: `scripts/sincronizacao/simular.py` ganha comentários das duas pessoas ao mesmo tempo (nenhuma cópia
  de conflito) e uma definição compartilhada chegando ao outro computador.

## Riscos

- **Campos de segredo da API**: a API tem vários jeitos de autenticar. A lista do que pode ir para a pasta é
  explícita (o resto fica), e um teste falha se um campo novo do modelo não estiver classificado.
- **Execução com contexto**: esquecer o contexto num caminho de execução usaria a definição local. Todos os caminhos
  (Executar, executar até aqui, prévia, agendamento) passam pela mesma função que monta as lojas, com teste por caminho.
- **Desempenho na pasta de rede**: a vista Dados lê só a lista das definições (arquivos pequenos), e os comentários de
  um fluxo só quando ele abre.
