# Spec 045: correções na 0.9.2 (etapa recolhida com laço e salvar automático)

Status: Implementada · Versão 0.9.2 (republicada) · Criada: 2026-11-20

## Contexto

Problemas apontados logo depois de publicar a 0.9.2, corrigidos na própria 0.9.2:

- **Etapa recolhida com laço:** ao recolher uma etapa que tem um laço dentro, a etapa vira o cartão, mas a moldura
  tracejada do laço continua desenhada no tamanho original, vazia, embaixo do cartão.
- **Salvar automaticamente:** a opção pode ficar ligada com um fluxo que nunca foi salvo. Nada é gravado (o
  automático só vale para fluxos já salvos), mas o menu mostra a marca de ligado e o botão ganha o selo, como se
  estivesse salvando.

## Requisitos

| ID | Requisito |
|----|-----------|
| RF-4501 | **Laço em etapa recolhida:** com a etapa recolhida, o laço que está inteiro dentro dela não desenha moldura (o cartão o representa). Laço que fica só em parte na etapa recolhida usa o cartão no lugar das caixas escondidas: a moldura envolve o cartão e as caixas à vista. Expandir a etapa traz a moldura de volta como era. |
| RF-4502 | **Salvar automaticamente só em fluxo já salvo:** em fluxo nunca salvo (e no protegido, no exemplo e na lição), a opção aparece desmarcada e indisponível, com o motivo logo abaixo ("Indisponível: este fluxo ainda não foi salvo: use Salvar uma vez"). A marca de ligado e o selo no botão só aparecem quando o fluxo aberto está de fato salvando sozinho. Depois do primeiro Salvar, a opção fica disponível. A busca (Ctrl+K) segue a mesma regra. |
| RF-4505 | **Primeiro Salvar pede o nome:** num fluxo nunca salvo, Salvar (Ctrl+S, botão do topo, Salvar e agendar) abre um diálogo curto com o nome atual selecionado, avisa se já existe um fluxo com o mesmo nome na biblioteca e oferece **Salvar numa pasta…** (o Salvar como). Cancelar não salva. Assim a biblioteca não junta fluxos chamados "Novo fluxo" que ninguém reconhece depois. |
| RF-4504 | Guia e README atualizados; a 0.9.2 é republicada com as correções, com guias e instaladores nas duas marcas. |

## Encontrado na revisão

- O fluxo de teste que confundiu o mapa de uso era um "Novo fluxo" salvo sem nome em 29/10: o primeiro Salvar não pedia nome (RF-4505).

## Fora do escopo

- Mapa de uso: o fluxo de exemplo continua aparecendo (é um fluxo da biblioteca). O fluxo estranho que apareceu era um fluxo de teste salvo na biblioteca, não um fluxo não salvo.

## Critérios de aceite

| ID | Critério | Requisitos |
|----|----------|------------|
| CA-01 | No exemplo, recolher a etapa "7 · Laço" deixa só o cartão, sem moldura tracejada; expandir traz a moldura. | RF-4501 |
| CA-02 | Num fluxo novo, a seta do Salvar mostra "Salvar automaticamente" desmarcado e indisponível, com o motivo; o botão não tem selo. Depois de salvar, a opção liga e o selo aparece. | RF-4502 |
| CA-03 | Num fluxo novo, Ctrl+S abre o diálogo com o nome; Cancelar não grava nada; Salvar com outro nome grava na biblioteca com esse nome. | RF-4505 |
