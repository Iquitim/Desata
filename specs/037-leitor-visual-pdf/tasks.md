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

- [ ] T01 Fontes e extrações (`PdfSources`, `PdfRecipes`), rotas e assinatura `pdf:` (RF-3701, RF-3704, RF-3772, RF-3783)
- [ ] T02 Cartão, situação, organização e mapa de uso (RF-3703)
- [ ] T03 Editor: áreas, páginas, miniaturas, zoom, busca (RF-3710, RF-3711)
- [ ] T04 Seleção por mouse, área e teclado; ação contextual; arrastar até a prévia (RF-3712..3715)
- [ ] T05 Campos: criar, tipo, Como encontrar, posição frágil, obrigatório, variações de rótulo (RF-3720..3723)
- [ ] T06 Tabelas: guias, junção de linhas, exclusões, continuação, nada inventado (RF-3730..3734)
- [ ] T07 Prévia de impacto, exemplos, matriz e mudança de regra com desfazer (RF-3740..3743)
- [ ] T08 De onde veio, nos dois sentidos, e saída de origem (RF-3750..3752)
- [ ] T09 Estados, política de falha e correção só neste documento (RF-3760..3762)
- [ ] T10 Saídas no Input Data, cache, subfluxo e linha de comando (RF-3770..3772)
- [ ] T11 Limites, mensagens e nada de conteúdo em log (RF-3780..3782)
- [ ] T12 Guia, Manual, prints e PDF de demonstração (RF-3790)
- [ ] T13 Testes de navegador e roteiro de teste com pessoas
