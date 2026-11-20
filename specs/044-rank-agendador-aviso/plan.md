# Plano da spec 044

## Rank

- `prep.rank` em `nodes/window.py` (arquivo novo; `prep.py` e `reshape.py` já são grandes). Config declarativa:
  `order_by: list[SortItem]`, `method: row|rank|dense` (widget de cartões com mini-exemplo), `group_by`, `column`,
  `keep_top: bool`, `top: int`.
- Motor (Polars): ordena por grupo e ordem (`nulls_last`, `maintain_order`), numera com `int_range().over(grupo)`; o
  empate vem de "alguma coluna de ordem mudou em relação à linha anterior do grupo"; DENSE = soma acumulada das
  mudanças; RANK = menor número de linha do bloco empatado.
- SQL: `ROW_NUMBER/RANK/DENSE_RANK() OVER (PARTITION BY … ORDER BY … NULLS LAST, posição de chegada)`; top N com
  `QUALIFY`; saída com `ORDER BY` igual ao motor. Testado em `test_sql_equivalence`.
- Como funciona em `explainers_extra.js` (padrão das caixas novas).

## Média e soma móvel

- Só receitas novas em `multirow_recipes.js`: a fórmula é escrita com `[Row-k:col]` (o motor e o SQL de hoje já
  executam). Média: `IF IsNull([Row-(N-1):c]) THEN Null ELSE ([c] + [Row-1:c] + …) / N ENDIF`.
- A receita força "Linha que não existe vale: vazio" (com 0 a média sairia errada) e esconde esse campo.
- `distance` passa a valer até 24 nessas receitas (o campo continua com o limite geral); o rótulo muda para
  "Quantas linhas na janela".
- O Como funciona passa a receber a janela (`window`) além da vizinha, e acende todas as linhas dela.

## Append Fields

- Estimativa e avisos calculados na tela a partir das contagens de linhas das entradas já executadas
  (`anchors.row_count` das caixas anteriores): nada novo na API.
- Depois de executar, o motor põe o aviso em `extra.warnings` acima de 100 mil linhas.
- Como funciona em `explainers_extra.js`.

## Agendador

- `prodata/scheduling/` (motor puro, sem FastAPI):
  - `model.py`: `Schedule` (id, workflow_id ou caminho do arquivo, nome, frequência, horário, dias, dia do mês,
    intervalo, opções, pausado) e o cálculo da próxima execução.
  - `task_xml.py`: monta o XML da tarefa do Agendador (Task Scheduler 1.2, `InteractiveToken`, `LeastPrivilege`,
    `StartWhenAvailable`, `WakeToRun`, `DisallowStartIfOnBatteries`, `ExecutionTimeLimit` de 4 h,
    `MultipleInstancesPolicy=IgnoreNew`) com `xml.etree`, nunca por concatenação.
  - `windows.py`: chama `%SystemRoot%\System32\schtasks.exe` por `subprocess.run([...])`, sem shell: `/Create /XML`,
    `/Query /XML` (existe? está ativo?), `/Change /ENABLE|/DISABLE`, `/Run`, `/Delete /F`. O executor é injetável,
    para os testes.
  - `store.py`: agendamentos em `schedules.json` na pasta de dados; histórico em `logs/agendamentos.jsonl`.
- Nome da tarefa: `<marca> - <nome do fluxo> (<id curto>)`, só com letras, dígitos, espaço, `-` e `_`, na raiz do
  Agendador (pasta própria pode exigir administrador).
- Comando da tarefa, montado só no servidor: executável instalado `<nome>-tarefa.exe` (novo EXE do PyInstaller,
  `console=False`, sem splash, o mesmo `launcher_cli`) com `run <id> --agendamento <id>`; em desenvolvimento,
  `sys.executable -m prodata run …`. O id do fluxo é validado por `ID_PATTERN`; o arquivo, por existir e terminar
  em `.prodata.json`.
- `cli run --agendamento <id>`: grava uma linha no histórico (início, fim, status ok/falhou/recusado, erros, arquivos
  gravados, mensagem), inclusive quando recusa por confiança.
- API `api/routes/schedules.py`: listar (com estado no Windows e última execução), criar, editar, pausar, retomar,
  executar agora, excluir, falhas não vistas e marcar como vistas.
- Tela: `schedule_dialog.js` (agendar/editar) e `schedules_list.js` (lista); aviso de falha no início.

### Riscos

- `schtasks` localizado: só se usam códigos de saída e o XML (não o texto).
- Política da empresa bloqueando tarefas: erro do `schtasks` vira mensagem com a linha de comando como saída.
- Segurança: nenhum valor do cliente entra no comando além de id validado e caminho conferido; sem senha; sem shell.

## Aviso de fim

- `run_notice.js`: depois de `run()` (não automática), monta a caixinha com `--accent`/cores da marca; usa
  `document.hasFocus()` para decidir se some sozinha; a opção fica em `localStorage` e no menu Exibir.
