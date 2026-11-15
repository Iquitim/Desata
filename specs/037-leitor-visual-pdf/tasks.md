# Tarefas da spec 037

## Etapa 0: spike

- [x] S01 PDFs sintéticos de teste (campos, cabeçalho deslocado, dois totais, tabela multilinha, tabela em duas páginas, página girada, conteúdo girado dentro do PDF, escaneado, protegido, malformado)
- [x] S02 Leitura isolada: processo filho, tempo limite, limite de memória (Job Object no Windows), códigos de erro sem conteúdo
- [x] S03 Palavras e linhas com caixa normalizada, rotação aplicada; imagem da página com limite de pixels
- [x] S04 Confirmar licença, ausência de JavaScript e XFA no PDFium distribuído e o tamanho no pacote
- [x] S05 Regra por rótulo (direita e abaixo) com estados Encontrado, Ausente, Ambíguo e Inválido; conversão de tipos
- [x] S06 Tabela: guias por espaço em branco, linha nova por coluna, célula multilinha, cabeçalho repetido, continuação de página
- [x] S07 Protótipo de tela: página, camada de palavras, seleção (clique, arraste, teclado), criar campo, prévia, clique na célula volta à origem
- [x] S08 Teste de alinhamento: zoom 50/100/200% × escala de tela 1/1,5/2 × página girada
- [x] S09 Cache: assinatura do arquivo + extração; PDF alterado refaz
- [x] S10 `spike.md` com resultados, limitações e decisões

## Etapa 1: implementação (depois do spike)

- [x] T01 Fontes e extrações (`PdfSources`, `PdfRecipes`), rotas e assinatura `pdf:` (RF-3701, RF-3704, RF-3772, RF-3783)
- [x] T02 Cartão, situação, organização e mapa de uso (RF-3703)
- [x] T03 Editor: áreas, páginas, miniaturas, zoom, busca (RF-3710, RF-3711)
- [x] T04 Seleção por mouse, área e teclado; ação contextual; arrastar até a prévia (RF-3712..3715)
- [x] T05 Campos: criar, tipo, Como encontrar, posição frágil, obrigatório, variações de rótulo (RF-3720..3723)
- [x] T06 Tabelas: guias, junção de linhas, exclusões, continuação, nada inventado (RF-3730..3734)
- [x] T07 Prévia de impacto, exemplos, matriz e mudança de regra com desfazer (RF-3740..3743)
- [x] T08 De onde veio, nos dois sentidos, e saída de origem (RF-3750..3752)
- [x] T09 Estados, política de falha e correção só neste documento (RF-3760..3762)
- [x] T10 Saídas no Input Data, cache, subfluxo e linha de comando (RF-3770..3772)
- [x] T11 Limites, mensagens e nada de conteúdo em log (RF-3780..3782)
- [x] T12 Guia, Manual, prints e PDF de demonstração (RF-3790)
- [x] T13 Testes de navegador (`teste_navegador_app.py`, 17 conferências) e roteiro de teste com pessoas (`roteiro-teste-pessoas.md`)
- [ ] T14 Rodar as sessões com pessoas do roteiro e transformar os achados em ajustes
- [x] T15 Extrações salvas: escolher ao criar, copiar, trocar, exportar, importar e excluir (RF-3705)
- [x] T22 Tabela respeita a seleção: "depois de N linhas", bordas arrastáveis (baixo, cima e laterais) e Termina em com três opções (RF-3735)
- [x] T21 SQL do Regex e do Generate Rows (previsto na spec 033), conferidos com o motor; Generate Rows recusa nome de coluna de datas igual ao de uma coluna do calendário
- [x] T20 Aba SQL: a fonte PDF vira tabela de origem (como API e Jira), em vez de "nome de arquivo inválido"
- [x] T19 Documentos da fonte um a um: tirar, trazer de volta e adicionar PDFs; cartões de saída sem espremer (RF-3706)
- [x] T18 Ajustes da revisão: busca dos resultados (estilo global sobrescrito), logo do exemplo segue a marca (reconhecido por impressão SHA-256, porque o instalado só traz a pasta da marca ativa), seletor do Input Data com um grupo por PDF, clicar no cartão leva ao lugar no PDF, etapa 6 ligada às Transações e gráficos do PDF no dashboard
- [x] T17 Exemplo com PDFs reais: três relatórios da Receita Federal (gov.br, reprodução autorizada) e a etapa 6 do fluxo de exemplo
- [x] T16 Guia e dist nas duas marcas: Desata e PRO.DATA (PDFs do guia em docs/guia; instaladores e portáteis em dist/)
