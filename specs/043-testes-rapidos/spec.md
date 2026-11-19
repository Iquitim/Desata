# Spec 043: testes rápidos no dia a dia, completos antes da release

Status: Rascunho · Criada: 2026-11-19

## Contexto

A suíte completa leva cerca de 6 minutos. Uns 60 testes executam o fluxo de exemplo inteiro (~5,6 s cada) e um teste
do Jira leva 62 s. Rodar tudo a cada alteração atrasa o trabalho; rodar só "o que parece necessário" à mão deixa passar
erros (na 0.9.1, um tamanho de fonte fora da escala no CSS só apareceu na suíte completa).

## Requisitos

| ID | Requisito |
|----|-----------|
| RF-4301 | **Rodada rápida** (um comando): roda só os testes afetados pelo código Python alterado (pytest-testmon) e pula os marcados `lento`. |
| RF-4302 | Mudança em `src/prodata/web/` (JS, CSS, HTML) inclui sempre os testes que leem esses arquivos (tema, qualidade de código, HTML exportado, Manual), porque o testmon só enxerga Python. |
| RF-4303 | **Rodada completa** (um comando): toda a suíte, em paralelo (pytest-xdist), com os testes lentos. |
| RF-4304 | Testes que executam o fluxo de exemplo inteiro e os que passam de alguns segundos ganham a marca `lento`, registrada no pyproject. |
| RF-4305 | **CI**: roda a suíte completa em paralelo a cada push e pull request; push que só altera `docs/`, `specs/` ou arquivos `.md` não roda. |
| RF-4306 | A regra de trabalho passa a ser: rodada rápida durante o desenvolvimento e antes de cada commit; rodada completa antes de uma release (o CI confere de novo). |

## Critérios de aceite

| ID | Critério |
|----|----------|
| CA-01 | Sem alteração desde a última rodada, a rodada rápida termina em segundos sem rodar testes de novo. |
| CA-02 | Alterar um CSS faz a rodada rápida rodar o teste de tema. |
| CA-03 | A rodada completa passa em paralelo, com o mesmo resultado da serial, em bem menos que 6 minutos. |
