# Spec 038: separador decimal escolhido pela pessoa

Status: Implementada na 0.8.5 · Criada: 2026-11-15

## Contexto

O programa mostra números sempre no formato brasileiro, com vírgula decimal (1.234,56), porque o `pt-BR` está fixo na
formatação da tela. Quem trabalha com relatórios, planilhas ou sistemas em ponto decimal (1,234.56) não tem como trocar.
Há também incoerências:

- As faixas do histograma no Perfil da coluna saem do Python em estilo americano, com ponto decimal, mesmo com o resto
  da tela em vírgula.
- O CSV gravado pelo Output Data sai com ponto decimal e `;` entre as colunas. O Excel em português espera vírgula
  decimal nesse formato, e não há como escolher.

## Objetivo

Uma escolha só, no topo do programa, decide como **todo número mostrado** aparece. Nada do que um fluxo guarda muda, e
um fluxo enviado a um colega abre com os números no formato dele.

## Requisitos

| ID | Requisito |
|----|-----------|
| RF-3801 | Em **Exibir → Números**, a pessoa escolhe entre **1.234,56** (vírgula decimal, o padrão) e **1,234.56** (ponto decimal). A escolha vale para este computador e fica guardada entre as aberturas do programa. |
| RF-3802 | A escolha vale em toda a tela: tabela de resultados, perfil e histograma das colunas, gráficos, cartões de KPI, destaques e filtros do dashboard, vista Dados, leitor de PDF e mensagens de tamanho e tempo. Muda na hora, sem reabrir o programa. Palavras como "mil", "mi" e "R$" continuam em português. |
| RF-3803 | O HTML exportado do dashboard leva a escolha de quem exportou: abre do mesmo jeito em qualquer computador. |
| RF-3804 | O filtro rápido da tabela aceita o número digitado no formato escolhido (com ou sem separador de milhar). |
| RF-3805 | O **Output Data** em CSV ganha o campo **Separador decimal**: ponto (padrão, como sempre foi) ou vírgula (Excel em português). As exportações que já existem não mudam. O SQL gerado avisa como gravar com vírgula, já que o DuckDB não grava vírgula decimal sozinho. |
| RF-3806 | Não mudam com a escolha: a linguagem das fórmulas (número com ponto, porque a vírgula separa argumentos), o SQL, a leitura de CSV (cada arquivo tem a própria opção de separador decimal), Parquet, JSON e os dados gravados. |
| RF-3807 | Guia e Manual explicam onde trocar e o que muda, com print do menu. |

## Fora do escopo

- Formato de datas (continua dd/mm/aaaa na tela).
- Idioma da interface.
- Textos que viram dado numa coluna, como os valores do Reconcile, que continuam no formato brasileiro.

## Critérios de aceite

| ID | Critério | Requisitos |
|----|----------|------------|
| CA-01 | Trocar para ponto decimal: a tabela mostra 1,234.56, o KPI "R$ 21.9 mi" e o histograma também em ponto, sem reabrir. | RF-3801, RF-3802 |
| CA-02 | Fechar e abrir o programa mantém a escolha. | RF-3801 |
| CA-03 | HTML exportado com ponto decimal abre com ponto num navegador comum. | RF-3803 |
| CA-04 | Output Data com vírgula grava `1234,56` no CSV; sem mexer, continua `1234.56`. | RF-3805 |
| CA-05 | Uma fórmula com `0.5` continua valendo nas duas escolhas. | RF-3806 |
