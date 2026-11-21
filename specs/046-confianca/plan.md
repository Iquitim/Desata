# Plano da spec 046

Ordem de implementação: **C → D → A → B**, com **E** quando couber (é independente). C vem primeiro porque é a rede de
segurança da troca de colunas em massa do A.

## C. Versões anteriores

- `services/versions.py` (`VersionStore`), sem FastAPI: um arquivo `<AAAAMMDD-HHMMSS-ffffff>-<origem>.json` por versão
  (o fluxo inteiro, **sem** `samples`), em `storage_dir/versoes/biblioteca/<workflow_id>/` para fluxos da biblioteca e
  em `storage_dir/versoes/arquivos/<sha256 do caminho normalizado, 32 hex>/` para fluxos salvos numa pasta (o Salvar
  como mantém o id: a chave pelo arquivo impede misturar históricos). O caminho do cliente só entra no hash; nunca é
  aberto nem gravado. O id do fluxo é validado por `ID_PATTERN`.
- Origens: `manual`, `auto`, `restore`, `columns`. Regra do automático: só grava se a última versão tiver mais de
  10 minutos; versão idêntica à última (hash do JSON sem `samples`) não é gravada. Limite de 30 por fluxo, apagando as
  mais antigas.
- Resumo do que mudou: função pura `diff_summary(old, new)` (caixas adicionadas, removidas e alteradas por id e config;
  fios; nome) em `services/versions.py`, testada.
- API `api/routes/versions.py`:
  - `GET /api/workflows/{id}/versions`: lista com data, origem e resumo em relação ao fluxo enviado (ou ao salvo);
  - `GET /api/workflows/{id}/versions/{version}`: o fluxo daquela versão;
  - `POST /api/workflows/{id}/versions`: grava uma versão (corpo: fluxo + origem), usado pelo Salvar, pelo restaurar e
    pela troca de colunas.
- Gravação: a tela chama o `POST` depois de um Salvar bem-sucedido (biblioteca ou pasta), com a origem certa. Exemplo,
  lição e modo protegido não chamam (a mesma regra de `autoBlockedReason`, que já existe).
- Tela: `versions_dialog.js`. Lista à esquerda, prévia à direita (miniatura do canvas desenhada a partir das posições das
  caixas, com os ícones das ferramentas, sem executar). Restaurar: grava a versão atual com origem `restore` e aplica a
  escolhida com `mutate` (estrutural, um passo de Desfazer). Item em Arquivo.

## D. Fio inteligente

Só tela (`canvas.js`, novo `canvas_snap.js`, `canvas_quickadd.js`, CSS em `canvas.css`):

- `canvas_snap.js`: `snapTarget(gesture, clientX, clientY)` devolve `{ kind: 'port'|'node'|'neutral'|'empty', nodeId,
  port, candidates }`. Distâncias medidas em pixels de tela (posições das entradas × zoom). Raio do ímã 28 px; faixa
  neutra 60 px em volta do retângulo de cada caixa. Usa `connectionError` (já existe) para compatibilidade e ciclos.
- Durante o gesto `connect`: classe no canvas (`.wiring`) acende as entradas compatíveis e esmaece as demais; a ponta
  do fio vai para a entrada-alvo quando há ímã; etiqueta flutuante junto ao cursor; entrada ocupada mostra o fio antigo
  tracejado (classe no `g.edge`).
- Ao soltar: `port` liga (substituindo a ligação se a entrada aceita uma só, numa única mutação); `node` com uma
  candidata liga, com várias abre o seletor (`port_chooser`, com letra e rótulo da porta, vindo de `toolOf(...).inputs`);
  `neutral` não faz nada; `empty` abre a lista.
- Próxima caixa: contagem `{ferramentaOrigem: {ferramentaDestino: n}}` em `localStorage` (try/catch), somada a cada
  ligação criada pela pessoa; padrão fixo por família quando não há contagem. `canvas_quickadd.js` ordena: sugeridas
  (até 5, com um rótulo "Sugeridas") e depois as demais como hoje.

## A. Mudanças na fonte

Motor (puro, testado) em `engine/schema_drift.py`:

- `Schema = list[ColumnSpec(name, dtype)]`; `diff(old, new) -> SchemaDiff(added, removed, retyped, rename_hints)`.
  Dica de renome: exatamente um par sumiu/apareceu com o mesmo tipo, ou o par sumiu/apareceu na mesma posição e com o
  mesmo tipo; nunca só pelo nome.
- `column_refs(workflow, node) -> set[str]`: percorre a config pela descrição declarativa da ferramenta
  (`describe_fields`): widgets `column`, `columns`, `select_columns`, itens de `list` com campos de coluna, regras de
  qualidade; expressões (`expression`, `filter_value`) pelo analisador de fórmulas que já existe (`[coluna]`,
  `[Row-1:coluna]`). Campos `sql` só contam como "talvez" (busca do nome entre aspas ou como palavra).
- `affected(workflow, input_node_id, columns) -> {node_id: [colunas]}`: descendentes do Input cujas referências cruzam
  as colunas. Atenção a renomes no caminho (Select): a referência só conta se a coluna chega com o mesmo nome; o
  primeiro Select que renomeia ou descarta corta a propagação.
- `rename_column(workflow, nodes, old, new) -> Workflow`: troca nos mesmos campos de `column_refs` (inclusive dentro de
  fórmulas, preservando o resto do texto). Testada caixa por caixa nas ferramentas com colunas.

Modelo e execução:

- `Workflow.schemas: dict[str, RememberedSchema]` (id da caixa → colunas, tipos e data). Campo opcional, com padrão
  vazio: fluxos antigos abrem iguais.
- O runner, ao executar um Input ou um Output, põe no `extra` do resultado o formato atual e, se houver formato
  lembrado, o `schema_diff` e, para Inputs, as caixas atingidas e até 3 valores de exemplo das colunas com tipo novo
  (os que não convertem para o tipo antigo).
- Quem regrava `schemas` é a tela (mutação não estrutural, que o salvar automático leva): na primeira leitura, ou ao
  clicar **Entendi, usar o formato novo**. Na linha de comando, o formato lembrado é só lido.
- `run(..., unattended=True)` (CLI e agendador): antes de executar qualquer Output, se algum Input tiver coluna usada
  que sumiu, ou coluna nova com política `parar`, a execução inteira para com erro de domínio em português (frase do
  RF-4607), sem gravar saídas. O Output com `stop_on_schema_change` também para (interativo ou não).
- Campos novos nas configs: Input `on_new_columns: Literal["seguir", "parar"]` (grupo Avançado) e Output
  `stop_on_schema_change: bool` (grupo Avançado). Ferramentas continuam declarativas.
- Pasta de arquivos: o Input Folder já monta a tabela por arquivo; ganha "colunas que faltam" por arquivo, e o formato
  lembrado é a união.

Tela:

- Selo no Input (`canvas_nodes.js`), aviso no Configurar (`schema_notice.js`), acender as caixas (classe
  `.drift-hit`, âmbar, com etiqueta da coluna), diálogo **Trocar por…** com valores lado a lado (primeiras linhas das
  duas colunas, vindas do resultado já executado), gravação de uma versão `columns` antes da troca (C) e troca numa única
  mutação.
- Como funciona do aviso em `explainers_extra.js`.

### Riscos

- Ferramentas com widgets próprios (`quality_rules`, `pdf`, `sheet_ports`, `dashboard`): `column_refs` precisa cobrir
  cada uma; o que não cobrir fica documentado e testado como "não atingida" em vez de troca errada.
- O dashboard também cita colunas: entra em `column_refs` e na troca (os visuais de um BI apontam para colunas da saída).
- Desempenho: a análise é por fluxo e barata (centenas de caixas); roda só quando há diferença de formato.

## B. Erros em português

- `engine/errors_pt.py`: `translate(exc, columns) -> FriendlyError(message, kind, column, similar, technical)` para
  `ColumnNotFoundError`, `DuplicateError`, `SchemaError`/`InvalidOperationError` (tipos), `ComputeError` de conversão,
  `ZeroDivisionError`, `MemoryError`/`OutOfMemory`, `PermissionError` em arquivo. Colunas parecidas por `difflib`.
  Sem correspondência: devolve a mensagem original (nada inventado).
- Runner (`_run_node_inner`): usa `translate` no `except` de erros conhecidos; `NodeResult` ganha `error_detail` (o
  texto técnico) e `error_hint` (`kind`, `column`, `similar`). O log recebe o texto técnico inteiro.
- Tela: o painel de erro mostra a frase, as parecidas como botões, **Escolher outra coluna** (foca o campo que cita a
  coluna, via `column_refs` do lado da tela ou do `field` já devolvido em `SkippedError`) e **Detalhes técnicos**
  recolhido.

## E. Pílula deslizante

- `segmented_pill.js`: `enhanceSegmented(root)` acrescenta um `span.seg-pill` atrás dos botões e o move por
  `left/width` com transição CSS de 200 ms (`cubic-bezier(.2,.8,.2,1)`); observa `aria-selected`/`aria-checked` e a
  classe `active` por `MutationObserver`, e o redimensionamento por `ResizeObserver`. Com `prefers-reduced-motion`, sem
  transição. Aplicado à troca de vista e aos `.segmented` do programa; o fundo do selecionado passa à pílula.

## Testes

- `tests/test_versions.py`: gravar, limite, regra dos 10 minutos, idêntica não grava, sem `samples`, resumo.
- `tests/test_schema_drift.py`: diff, dicas de renome, `column_refs` por ferramenta, `affected` com Select no caminho,
  `rename_column` (Select, fórmula, Summarize, Join, Sort, Filter, dashboard), parada `unattended`, Output.
- `tests/test_errors_pt.py`: cada caso traduzido, parecidas, fallback sem tradução.
- Tela: conferência no navegador (Playwright) de D, A e E; prints do guia.
