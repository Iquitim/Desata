# Spec 040: datas sem formato certo e fluxo que viaja entre computadores

Status: Em andamento · Versão 0.8.6 · Criada: 2026-11-15

## Contexto

Duas fricções aparecem assim que o programa sai das mãos de quem o conhece.

**Datas.** Cada pessoa escreve data de um jeito: `2026-07-08`, `07/08/2026`, `jul/26`, com ou sem aspas. Hoje:

- O Filter no modo básico compara uma coluna de data como **texto**: `07/08/2026` contra datas guardadas como
  `2026-07-08` dá um resultado errado, sem aviso.
- Nas fórmulas e no Filter por expressão, só `'2026-07-08'` (ou `ToDate('2026-07-08')`) funciona. Os outros formatos
  falham ou viram nulo em silêncio, e a pessoa não sabe por quê.

**Fluxo em outro computador.** O fluxo guarda só o nome de cada fonte (um arquivo, `sql:`, `api:`, `pdf:`...). Quem
recebe o arquivo e não tem aquela fonte:

- não vê nenhum aviso até executar, e aí a caixa dá erro. Num fluxo já confiado, nada avisa; o diálogo de abertura
  protegida aponta só parte das fontes (arquivos e PDFs nem são conferidos);
- não tem como rodar o fluxo para entender o que ele faz, a não ser recriar todas as fontes.

## Objetivo

1. Digitar uma data de qualquer jeito comum nunca dá resultado errado em silêncio: o filtro básico oferece um
   calendário, e onde se escreve fórmula o programa reconhece a data e **sugere** a forma certa, sem trocar o que a
   pessoa digitou.
2. Um fluxo aberto noutro computador mostra, de cara e em vermelho, o que falta, e leva a pessoa a apontar cada fonte.
   Opcionalmente, o fluxo viaja com uma **amostra pequena** dos dados, para rodar mesmo sem as fontes, sempre marcada
   como amostra.

## Requisitos

### Datas

| ID | Requisito |
|----|-----------|
| RF-4001 | **Calendário no filtro básico:** com uma coluna de data (ou data e hora), o campo Valor do Filter básico vira um seletor de data. O valor fica guardado como `AAAA-MM-DD`. Fluxos antigos com outro formato abrem com o valor convertido, se for uma data reconhecível. |
| RF-4002 | O Filter básico compara coluna de data **como data**, nunca como texto. Aceita o valor em `AAAA-MM-DD` e `DD/MM/AAAA`; valor que não é data dá uma mensagem clara, em vez de um resultado errado. |
| RF-4003 | **"Você quis dizer…"** em todo campo de fórmula que usa colunas (Formula, Filter por expressão, Multi-Row Formula, Multi-Field Formula, regra livre do Data Quality e os demais com o editor de fórmulas): ao reconhecer uma data escrita de outro jeito, aparece logo abaixo uma sugestão, por exemplo *"Você quis dizer 7 de agosto de 2026? → ToDate('2026-08-07')"*. Clicar troca só aquele trecho. Ignorar não muda nada. |
| RF-4004 | Formatos reconhecidos, com ou sem aspas simples ou duplas: `2026-07-08`, `07/08/2026` e `7/8/2026` (dia/mês/ano, como no Brasil), `08-07-2026`, `jul/26`, `jul/2026`, `julho/2026` e `07/2026` (mês e ano, que viram o primeiro dia do mês, com a dica de comparar o mês inteiro). O texto da sugestão escreve a data por extenso, para não haver dúvida entre dia e mês. |
| RF-4005 | A sugestão nunca aparece dentro de um texto que claramente não é data (`'NF 07/08'`, nomes de colunas, números) nem quando a data já está na forma certa. Uma data impossível (`31/02/2026`) mostra o aviso, sem sugestão. |
| RF-4007 | **Data e hora, completo:** no Filter básico, coluna de data e hora ganha calendário com hora opcional; sem hora compara o dia inteiro, com hora compara o instante. Nas fórmulas, `08/07/2026 14:30`, `2026-07-08 14:30`, `2026-07-08T14:30:00` (com ou sem aspas, com ou sem segundos) sugerem `ToDateTime('2026-07-08 14:30:00')`, função nova que vale no motor e no SQL. O filtro rápido da tabela segue a mesma regra. |
| RF-4008 | Ano com dois dígitos (`8/7/26`, `08/07/26`) também é reconhecido, como 2026. |
| RF-4006 | O mesmo reconhecimento vale nos outros lugares em que se digita uma data para comparar com uma coluna de data: filtro rápido da tabela de resultados e regra de faixa de data do Data Quality. |

### Fluxo em outro computador

| ID | Requisito |
|----|-----------|
| RF-4010 | **Fontes que faltam:** ao abrir um fluxo, o programa confere cada fonte que ele usa (arquivo, pasta, consulta, API, Jira, PDF, conexão de banco, subfluxo e modelo; as constantes compartilhadas já viajam com o fluxo, spec 028). As que não existem neste computador aparecem: com um selo vermelho na aba **Dados** (com a quantidade), numa seção **Faltam neste computador** no topo da vista Dados, e na própria caixa do Designer, em vermelho, com "fonte ausente". |
| RF-4011 | Cada fonte que falta tem a ação certa: arquivo → **Escolher o arquivo** (entra com o mesmo nome, e o fluxo funciona sem mudar); pasta e PDF → escolher a pasta ou o arquivo; consulta, API e Jira → **Cadastrar**, com o identificador já preenchido; subfluxo e modelo → importar. Resolvida, sai da lista na hora. |
| RF-4012 | Executar um fluxo com fonte ausente diz qual é e onde resolver ("A fonte 'vendas.csv' não está neste computador: veja Dados → Faltam neste computador"), em vez de um erro técnico. |
| RF-4013 | **Salvar com amostra dos dados** (Arquivo → Salvar com amostra dos dados…): item próprio, nunca automático, que sempre leva junto com o arquivo uma amostra das fontes que o fluxo lê (sem amostra, vale o Salvar como de sempre). A tela mostra antes, fonte a fonte, quantas linhas e o tamanho, e deixa tirar fontes. Limites: até 1.000 linhas por fonte e 5 MB no total. |
| RF-4019 | **Linhas e anonimização no próprio salvamento:** cada fonte escolhe 100, 500 ou 1.000 linhas. Colunas que parecem dados pessoais (CPF, CNPJ, e-mail, telefone, nome) já vêm marcadas para mascarar, com os métodos da caixa Mask (máscara de CPF, CNPJ e e-mail, só o início, código estável); a pessoa ajusta coluna a coluna e vê uma prévia mascarada antes de salvar. Só a amostra é mascarada: a fonte e o fluxo não mudam. |
| RF-4020 | **Arquivo vinculado** (lido de uma pasta só deste computador): no salvar com amostra, a fonte aparece marcada como vinculada e um aviso explica que quem receber não tem a pasta; sem amostra dela, avisa que essa parte do fluxo não roda do outro lado. A amostra leva só o sinal de que era vinculado, nunca o caminho, e quem recebe vê no cartão da fonte que era um arquivo vinculado de quem enviou. |
| RF-4014 | A amostra vem das primeiras linhas lidas de cada fonte e guarda colunas, tipos, quantas linhas, de quando é e de onde veio (o nome da fonte, nunca o caminho, a senha ou a conexão). O aviso de dados pessoais lembra que a amostra leva dados de verdade, e o salvamento entra no registro de exportações com o rótulo de confidencialidade. |
| RF-4015 | Ao abrir um fluxo com amostra num computador **sem** a fonte, o Input Data lê a amostra. A fonte aparece na vista Dados com o rótulo laranja **Amostra** ("200 linhas, de 15/11/2026"), a caixa mostra "lendo a amostra" e os resultados avisam que vêm de uma amostra. Com a fonte de verdade presente, ela sempre vence. |
| RF-4016 | Da amostra para a fonte de verdade: **Apontar para a fonte** troca a amostra pela fonte real sem mudar o fluxo. A amostra pode ser apagada do fluxo. |
| RF-4017 | A abertura protegida (spec 029) passa a usar a mesma conferência: lista todas as fontes que faltam, de todos os tipos, e diz quando o fluxo traz amostra. |
| RF-4018 | Guia e Manual com as duas partes, prints nos dois temas, e o exemplo de abrir um fluxo de fora: o calendário também onde o guia explica o Filter, e a caixa e a vista Dados lendo a amostra. |

## Fora do escopo

- Levar no arquivo a definição das consultas, APIs e extrações de PDF (sem segredo). Fica para uma versão seguinte;
  nesta, a extração de PDF já pode ser exportada à parte (spec 037).
- Mascarar colunas da amostra automaticamente. O aviso lembra da caixa Mask antes de salvar.
- Datas em inglês por extenso (`July 8`), datas com hora no "Você quis dizer" e formatos mês/dia/ano.

## Critérios de aceite

| ID | Critério | Requisitos |
|----|----------|------------|
| CA-01 | Filter básico numa coluna de data mostra o calendário; escolher 08/07/2026 filtra as linhas de 8 de julho, igual a `[data] == ToDate('2026-07-08')`. | RF-4001, RF-4002 |
| CA-02 | Filter básico com `07/08/2026` gravado num fluxo antigo compara como data (7 de agosto), não como texto. | RF-4002 |
| CA-03 | Digitar `[data] >= 07/08/2026` numa Formula mostra "Você quis dizer 7 de agosto de 2026?"; clicar deixa `[data] >= ToDate('2026-08-07')`. | RF-4003, RF-4004 |
| CA-04 | `jul/26` sugere `ToDate('2026-07-01')`, com a dica de comparar o mês inteiro. `'NF 07/08'` e `31/02/2026` não geram sugestão (o segundo mostra o aviso). | RF-4004, RF-4005 |
| CA-05 | Um fluxo que lê `clientes.csv`, aberto num computador sem esse arquivo, mostra a aba Dados com selo vermelho, a seção Faltam neste computador e a caixa em vermelho; escolher o arquivo resolve tudo sem mexer no fluxo. | RF-4010, RF-4011 |
| CA-06 | Salvar para compartilhar com amostra de 2 fontes; abrir noutro computador sem elas: o fluxo executa com a amostra, e Dados mostra as duas com o rótulo Amostra. Com a fonte real presente, a amostra é ignorada. | RF-4013..4016 |
| CA-08 | Filter básico em data e hora: 08/07/2026 sem hora pega o dia inteiro; com 14:30, só aquele instante. `[quando] >= 08/07/2026 14:30` sugere `ToDateTime('2026-07-08 14:30:00')`, que roda no motor e no SQL. | RF-4007 |
| CA-09 | Salvar com amostra com 100 linhas de uma fonte e o CPF mascarado: o arquivo leva 100 linhas e nenhum CPF legível; a fonte de origem continua igual. | RF-4019 |
| CA-10 | Salvar com amostra um fluxo que lê um arquivo vinculado: o diálogo avisa; o arquivo leva o sinal, não o caminho; quem abre vê no cartão que era um arquivo vinculado. | RF-4020 |
| CA-07 | A amostra respeita 1.000 linhas por fonte e 5 MB; nenhum caminho local, senha ou dado de conexão vai no arquivo. | RF-4013, RF-4014 |
