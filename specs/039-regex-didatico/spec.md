# Spec 039: Regex sem escrever expressão regular

Status: Implementada na 0.8.5 · Criada: 2026-11-15

## Contexto

O Regex é a única caixa que exige aprender uma linguagem nova: para tirar o mês e o ano de "NF 10/2026", a pessoa
precisa escrever `(\d{2})/(\d{4})`. Todas as outras pedem escolher e clicar, e até tarefas difíceis, como ler uma tabela
de PDF ou montar regras de qualidade, viraram marcar no exemplo ou escolher cartões. O Regex fura essa regra.

## Objetivo

Quem nunca ouviu falar de expressão regular consegue pegar, trocar ou marcar um trecho de texto **mostrando o que quer
num valor de verdade**. Quem já sabe continua escrevendo a expressão. Motor, SQL e fluxos salvos não mudam: no fim,
continua sendo uma expressão regular.

## Requisitos

| ID | Requisito |
|----|-----------|
| RF-3901 | Os modos têm nomes do dia a dia: **Pegar um trecho** (vira coluna), **Trocar um trecho** e **Marcar as linhas que têm**. |
| RF-3902 | **Marcar no exemplo:** a caixa mostra valores reais da coluna escolhida. A pessoa seleciona com o mouse o trecho que quer ("10/2026" em "NF 10/2026"), e a caixa monta as peças que descrevem esse trecho: números com a quantidade de dígitos, letras, espaços e o texto fixo. |
| RF-3903 | **Peças**, em linguagem simples: número (com N dígitos ou com quantos houver), palavra, letras e números, espaço, texto fixo, qualquer coisa até a próxima peça, início e fim do texto, e peças prontas de data dd/mm/aaaa, CPF, CNPJ, CEP, e-mail, telefone e valor com vírgula. As peças prontas entram por cartões; cada peça pode ser trocada, ajustada ou tirada. |
| RF-3904 | No modo Pegar, cada peça pode **virar coluna**, com nome. Sem nenhuma marcada, o trecho inteiro vira uma coluna. |
| RF-3905 | A caixa lê o padrão em português ("Procura: 2 dígitos, uma barra, 4 dígitos"), destaca nos exemplos onde casou (com a cor de cada coluna) e diz em quantas linhas casou, com exemplos das que não casaram. Tudo ao vivo, antes de executar. |
| RF-3906 | **Avançado:** a expressão regular fica visível e editável, sempre a mesma que as peças geram. Se a pessoa editar à mão, a caixa avisa e oferece voltar às peças. Ignorar maiúsculas fica junto. |
| RF-3907 | No modo Trocar, botões inserem as colunas marcadas no texto novo, sem precisar saber de `$1`. |
| RF-3908 | Fluxos salvos com uma expressão escrita à mão abrem no Avançado, sem mudança no resultado. |
| RF-3909 | Guia e Manual mostram marcar no exemplo e as peças, com print. |

## Fora do escopo

- Deduzir o padrão a partir de vários exemplos ao mesmo tempo (um exemplo marcado, ajustável pelas peças).
- Grupos opcionais, alternativas ("isto ou aquilo") e repetições complexas: ficam no Avançado.

## Critérios de aceite

| ID | Critério | Requisitos |
|----|----------|------------|
| CA-01 | Selecionar "10/2026" em "NF 10/2026" gera "2 dígitos, /, 4 dígitos" e destaca o trecho nos outros valores. | RF-3902, RF-3905 |
| CA-02 | Marcar as duas peças de número como colunas "mes" e "ano" gera duas colunas novas na execução. | RF-3904 |
| CA-03 | Escolher o cartão CPF acha os CPFs com e sem pontuação. | RF-3903 |
| CA-04 | Um fluxo com `(\d{2})/(\d{4})` escrito à mão abre no Avançado e dá o mesmo resultado. | RF-3908 |
| CA-05 | O padrão gerado pelas peças dá o mesmo resultado no motor, no esquema e no SQL. | RF-3905 |
