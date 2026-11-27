# Plano da spec 050 (0.9.6 substituída)

## Modelo

`Workflow.column_formats: dict[str, dict[str, DisplayFormat]]`, por id da caixa e nome da coluna, fora do arquivo
quando vazio (`exclude_if`, como `ignored_cleaning`). `DisplayFormat` (pydantic, `domain/display_formats.py`):

| Campo | Valores |
|---|---|
| `kind` | `none`, `number`, `currency`, `percent`, `document`, `date` |
| `decimals` | 0..6 (número, moeda, porcentagem) |
| `thousands` | separador de milhar (número) |
| `symbol` | até 6 caracteres, sem `<>"'` (moeda) |
| `base` | `fraction` ou `hundred` (porcentagem) |
| `mask` | `cpf`, `cnpj`, `cep`, `phone` ou máscara livre com `#`, até 40 caracteres, sem `<>"'` (documento) |
| `pattern` | `dmy`, `my`, `dmy_hm`, `long`, `iso` (data) |

`kind = none` existe para tirar um formato herdado (RF-5012). O `Workflow` apaga os formatos de caixas que não
existem mais (RF-5014), no mesmo validador que poda o dashboard.

## Herança (RF-5011, RF-5012)

`effective_formats(workflow, node_id) -> dict[coluna, DisplayFormat]`: o que a caixa definiu e, por coluna que ela
não definiu, o que vem das entradas, na ordem das portas de entrada (primeira entrada ganha). `none` some do
resultado, mas bloqueia o que viria de antes. A mesma regra existe em JavaScript (`col_format.js`, `effectiveFormats`),
para a tela responder sem executar; os dois lados têm os mesmos casos de teste (tabela em
`tests/fixtures/formatos_heranca.json`, lida pelo pytest e pela conferência de tela).

A herança é por nome: a caixa não precisa saber se a coluna passou por ela. Quem consulta só pergunta por colunas
que a caixa tem (RF-5014).

## Formatar (front)

`web/js/col_format.js`, puro e no pacote do HTML exportado (`dashboard/viewer.py`):

- `formatValue(spec, value, { compact })` → `{ text, bad }` (`bad`: motivo, quando não cabe, RF-5031);
- `badge(spec)` e `describe(spec)` para o selo e a dica (RF-5013);
- `effectiveFormats(workflow, nodeId)`;
- `valueFormatFor(widget, formats)` e `labelFormatFor(widget, formats)` para os visuais (RF-5023).

Números usam `fmt.number`/`fmt.compact`, que já seguem a escolha de separador (spec 038). Datas: o motor entrega
ISO (`2026-11-26`, `2026-11-26T14:30:00`); o formato lê os números da data sem passar por `Date` (sem fuso).

## Onde liga

- `datasets.js` `cell(value, type, spec)`: texto formatado, classe `fmt-bad` com a dica (RF-5031).
- `results.js`: selo no cabeçalho, item **Formato de exibição…** no menu, foco da célula com o valor guardado,
  Perfil formatado. O diálogo fica em `col_format_ui.js` (prévia, esquema, receita).
- Dashboard: `dash_model.widgetsByNode` passa a anexar `w.formats = { value, label, columns }`, resolvido pela caixa
  do visual; o HTML exportado leva junto porque serializa os widgets. `chart_kit.options` usa `w.formats.value` em
  `short`, `full` e no eixo quando o visual não tem prefixo, sufixo nem formato próprio (RF-5025); `chartCard`
  monta os nomes das categorias pelo formato do rótulo pelo mesmo caminho de `relabel` (`_keyOf` devolve o valor
  original, então cores e filtros continuam); `kpiTile` e `tableCard` usam o formato da coluna.
- Excel (`nodes/excel_output.py`): `excel_formats(df, formats)` → formato de número do Excel por coluna;
  `write_excel` do polars recebe `column_formats`; `openpyxl` (adicionar planilha e modelo) grava `number_format`
  por célula. `NodeContext.column_formats` vem de `effective_formats` no `runner` (o Output Data é caixa com efeito
  colateral: grava a cada execução, então trocar o formato vale na próxima execução).

## Formato do Excel

| Formato | Excel |
|---|---|
| Número | `#,##0` / `#,##0.00`; sem milhar `0.00` |
| Moeda | `"R$" #,##0.00;-"R$" #,##0.00` (símbolo entre aspas) |
| Porcentagem fração | `0.0%` |
| Porcentagem em pontos | `0.0"%"` |
| Data | `dd/mm/yyyy`, `mm/yyyy`, `dd/mm/yyyy hh:mm`, `[$-pt-BR]d" de "mmm". de "yyyy`, `yyyy-mm-dd` |
| CPF / CNPJ / CEP | `000"."000"."000"-"00` / `00"."000"."000"/"0000"-"00` / `00000"-"000` |
| Telefone | `[<=9999999999]"("00") "0000"-"0000;"("00") "00000"-"0000` |
| Máscara livre | `#` vira `0`, o resto entre aspas |

O Excel usa os separadores do Windows de quem abre; o código grava no padrão do Excel (vírgula de milhar, ponto
decimal), como manda o formato.

## Receita (RF-5041)

`col_format_ui.js` monta a expressão (`textFormula(spec, coluna, tipo)`) e insere uma Formula ligada depois da caixa
com o mesmo caminho das receitas da spec 049 (`recipes_ui.insertAfter`). Expressões:

- número/moeda: `"R$ " + FormatNumber([c], 2)`; porcentagem: `FormatNumber([c] * 100, 1) + "%"`;
- documento: `RegexReplace(PadLeft(DigitsOnly(ToString(ToInteger([c]))), 11, "0"), "^(\d{3})(\d{3})(\d{3})(\d{2})$", "\1.\2.\3-\4")`
  (texto sem `ToInteger`);
- data: `DateFormat([c], '%d/%m/%Y')`; por extenso com `Day`, `Month` e a lista dos meses abreviados.

A conferência de tela executa a Formula e compara a coluna nova com o texto da tela (CA-07).

## Testes

- `tests/test_display_formats.py`: modelo (símbolo e máscara inválidos, `none`), herança (cadeia, troca adiante,
  `none`, Join com dois formatos, coluna renomeada), poda de caixa apagada, impressão de confiança sem formatos,
  Excel (formato de número lido de volta com openpyxl nos três caminhos).
- `scripts/conferir_tela.py` `formato_coluna`: diálogo e prévia, Resultado da caixa e da seguinte, foco da célula,
  Perfil, gráfico e KPI, HTML exportado, Excel baixado, receita.
