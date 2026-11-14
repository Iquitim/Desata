# Spec 037: leitor visual de PDFs na vista Dados (0.8.5)

Status: Em andamento (spike) · Criada: 2026-11-14

## Contexto

Relatórios, extratos e documentos com campos e tabelas chegam em PDF e são copiados à mão para planilhas. O Desata
deve deixar a pessoa **ensinar uma extração apontando no próprio documento**, ver o dado aparecer numa tabela e
reaplicar o que ensinou nos próximos PDFs, sem código, sem regex e sem saber o que é OCR.

O PDF entra como **fonte da vista Dados**, como arquivos, pastas, consultas e APIs: tem nome de exibição, pasta da
organização, responsável, situação, mapa de uso, e é lido pelo **Input Data**. Não há editor paralelo no Designer.

**Princípio inegociável:** marcar no PDF, ver o dado nascer e conferir de onde veio, de forma fluida, visual e
confiável. Nenhum valor é escolhido em silêncio quando há dúvida.

## Princípios de experiência

| ID | Princípio |
|---|---|
| P1 | A página é a interface: a pessoa marca o próprio documento, não preenche formulários antes. |
| P2 | Resultado antes de configuração: a primeira marcação já cria a coluna e mostra a célula. |
| P3 | Toda ação tem consequência visível na página e na prévia, na hora. |
| P4 | Significado antes de coordenada: "à direita de 'Total líquido'", não "x=412, y=88". |
| P5 | Um clique de volta à origem: da célula ao trecho destacado na página certa, e da marcação à célula. |
| P6 | Ambiguidade não é acerto: com mais de um candidato, o campo fica Ambíguo, com os candidatos à vista. |
| P7 | Correção ensinável: corrigir só neste documento ou mudar a regra, vendo o impacto antes. |
| P8 | Continuidade com o Desata: mesmas capacidades e palavras das outras fontes. |
| P9 | Sem jargão na primeira camada: Campo, Tabela, Rótulo, De onde veio, Testar em outros arquivos. |
| P10 | Tudo também pelo teclado, e nenhum estado comunicado só por cor. |

## Histórias

- Como analista de controladoria, quero marcar o total líquido num relatório e vê-lo como coluna, sem código.
- Como analista de operações, quero marcar a tabela de filiais e ter uma linha por filial, mesmo em várias páginas.
- Como quem fecha o mês, quero salvar a extração e rodá-la nos PDFs novos de uma pasta, sem reconfigurar.
- Como revisor, quero clicar num número da tabela e ver de onde ele saiu no documento.
- Como responsável pelo processo, quero saber quais documentos e campos falharam antes de publicar o resultado.

## Requisitos

### Fonte PDF na vista Dados

| ID | Requisito |
|---|---|
| RF-3701 | Em **Adicionar → PDF**, a pessoa cria uma fonte de um PDF (cópia enviada ou arquivo vinculado, lido onde está) ou de uma **pasta de PDFs** com padrão de nome (`relatorio_*.pdf`), sem subpastas. |
| RF-3702 | Ao escolher o arquivo ou a pasta, o editor **Preparar extração** abre na própria vista Dados, em área ampliável. A fonte pode ser salva como **rascunho**, sem extração ainda. |
| RF-3703 | O cartão da fonte mostra nome de exibição, pasta da organização, responsável, arquivo ou pasta, situação, última leitura, as saídas que produz, a revisão da extração e a contagem de documentos aprovados, a revisar e com falha. Entra nos filtros "Com problema" e "Sem uso" e no mapa de uso. |
| RF-3704 | **Duplicar a fonte** cria outra com a mesma extração, para apontar para outro arquivo ou pasta. |

### Editor Preparar extração

| ID | Requisito |
|---|---|
| RF-3710 | Três áreas recolhíveis: **Campos** (o que já foi ensinado), **Documento** (a página) e **Resultado** (a prévia). Em janela estreita, o documento fica em foco e as outras áreas alternam. O modo foco do Desata vale aqui. |
| RF-3711 | O documento tem páginas, miniaturas, zoom (ajustar à largura, ajustar à página e porcentagens), busca de texto com os achados destacados e navegação entre eles. |
| RF-3712 | As palavras do PDF são selecionáveis por cima da imagem da página: clique numa palavra, arraste para várias ou desenhe uma área. A seleção acompanha exatamente o texto em qualquer zoom, resolução de tela e página girada. |
| RF-3713 | **Seleção pelo teclado:** setas andam palavra a palavra (e linha a linha), Shift estende, Enter abre as ações, Esc desfaz a seleção. O foco é sempre visível. |
| RF-3714 | Sobre a seleção aparece uma ação curta, só com o que vale no contexto: **Criar campo**, **Criar tabela**, **Usar como rótulo** (de um campo existente). Estado vazio ensina com uma frase e um desenho: "Marque uma informação no documento para virar coluna". |
| RF-3715 | Arrastar a seleção até a prévia cria o campo naquele lugar (ou associa a uma coluna existente). Clicar em Criar campo faz o mesmo. |

### Campos

| ID | Requisito |
|---|---|
| RF-3720 | Criar campo sugere nome (a partir do rótulo vizinho) e tipo pelo conteúdo: texto, inteiro, decimal, moeda (R$), data, mês/ano, sim/não. A coluna aparece na prévia **na hora**, com o valor convertido e o original ao lado. Nome e tipo mudam ali mesmo, sem janela. |
| RF-3721 | O Desata propõe como encontrar o campo nos outros documentos, em linguagem simples: "à direita de 'Total líquido'", "abaixo de 'Competência'", "dentro da seção 'Resumo'". A escolha fica visível em **Como encontrar** e pode ser trocada ou corrigida (inclusive marcando outro rótulo no documento). |
| RF-3722 | Localizar por posição fixa na página existe como última opção e aparece marcado como **frágil**, com a explicação do porquê. |
| RF-3723 | Cada campo pode ser obrigatório. Rótulos aceitam variações ("Total líquido", "Valor líquido") e ignoram maiúsculas, acentos e espaços extras. |

### Tabelas

| ID | Requisito |
|---|---|
| RF-3730 | Criar tabela a partir de uma área marcada: o Desata propõe as **guias de coluna** pelos espaços em branco verticais e a linha de cabeçalho. As guias são arrastáveis (e ajustáveis pelo teclado); colunas podem ser unidas, separadas e renomeadas. |
| RF-3731 | Linhas quebradas (célula com texto em duas ou mais linhas) são unidas por uma regra visível: "nova linha começa quando a coluna X tem valor". A pessoa escolhe a coluna e vê o resultado na hora; casos duvidosos ficam destacados. |
| RF-3732 | Cabeçalhos repetidos, rodapés e subtotais são **sugeridos** para exclusão, com confirmação; nada é excluído sozinho. |
| RF-3733 | A tabela pode continuar nas páginas seguintes: começa pelo cabeçalho e termina num texto que a pessoa marca ("Total geral") ou no fim do documento. |
| RF-3734 | Nenhuma linha é inventada: se a geometria não permite reconstruir a tabela, a área mostra o problema e pede ajuste. |

### Prévia, impacto e testes

| ID | Requisito |
|---|---|
| RF-3740 | Ao criar ou mudar uma regra, a **prévia de impacto** mostra, numa amostra dos PDFs da fonte, quantos documentos deram Encontrado, Ausente, Ambíguo e Inválido, sempre dizendo quantos foram de fato avaliados ("10 de 37 avaliados"). A avaliação roda sem travar o editor e pode ser cancelada. |
| RF-3741 | Em fonte de um PDF só, o editor oferece **Adicionar arquivos de exemplo** para testar as regras em outros PDFs antes de virar pasta; os exemplos não entram nos dados. |
| RF-3742 | **Testar em outros arquivos** monta a matriz documento × campo (e linhas de cada tabela) com os estados e o resultado do documento (Aprovado, Revisar, Falhou), informando quantos documentos foram testados. Clicar numa célula abre aquele documento na página certa, com os candidatos destacados. |
| RF-3743 | Ao mudar uma regra já usada, o Desata mostra antes de confirmar o que muda nos documentos testados: quantos mantiveram o resultado, quantos foram corrigidos e quantos passaram a falhar. A mudança pode ser desfeita. Os números vêm de execução real, nunca de estimativa. |

### De onde veio

| ID | Requisito |
|---|---|
| RF-3750 | Clicar numa célula da prévia (ou da matriz) abre o documento na página exata e destaca o trecho que gerou o valor, com o rótulo usado e a regra. |
| RF-3751 | Clicar numa marcação no documento mostra o campo, a regra e as células que ela gerou. |
| RF-3752 | Cada valor guarda a origem: documento, página, região e palavras de origem, campo, regra e revisão da extração. Nas saídas, as colunas `documento` e `pagina` existem como opção; a origem completa fica na saída de rastreio, sem poluir as colunas do negócio. |

### Estados, falhas e correções

| ID | Requisito |
|---|---|
| RF-3760 | Estados por campo: **Encontrado** (um valor válido), **Ausente** (nenhum candidato), **Ambíguo** (mais de um candidato plausível), **Inválido** (achou, mas não converte), **Não suportado** (página sem texto legível). Estados por documento: **Aprovado**, **Revisar**, **Falhou**. Todos com texto e ícone, além da cor. |
| RF-3761 | Política de falha da fonte, explicada em linguagem simples: **parar a execução**, **entregar só os aprovados** (com o relatório de falhas) ou **entregar todos com a situação**. A opção segura (parar, quando há campo obrigatório) vem sugerida. |
| RF-3762 | **Corrigir só neste documento**: a pessoa informa o valor certo para um documento, sem mudar a regra. A correção fica registrada (quem, quando, valor original e corrigido), aparece marcada na prévia e nas saídas, e deixa de valer se o documento mudar. |

### Saídas e uso no fluxo

| ID | Requisito |
|---|---|
| RF-3770 | Saídas da fonte: `campos` (uma linha por documento), uma por tabela (`itens_<nome>`, uma linha por item, com o documento de origem), `falhas` (documento, campo, tipo de falha, motivo, página) e `origem` (rastreio de cada valor). Todas com `documento_id` e `revisao` disponíveis. |
| RF-3771 | O Input Data lê `pdf:<id>/<saída>`; arrastar a fonte para o canvas cria o Input Data com a saída principal, e a lista de fontes mostra as saídas. Fluxos existentes não mudam. |
| RF-3772 | A fonte é refeita quando o PDF (ou um arquivo da pasta) muda, entra ou sai, ou quando a extração muda; senão, o resultado guardado é aproveitado. Vale para o Designer, subfluxos e a linha de comando, que segue a política de falha (código de saída 1 quando a política manda parar). |

### Confiabilidade e segurança

| ID | Requisito |
|---|---|
| RF-3780 | O PDF é lido localmente, num **processo separado**, com tempo limite e limite de memória; um PDF quebrado ou hostil nunca derruba o programa. Tamanho, páginas, resolução de imagem e leituras simultâneas têm limites, mostrados ao exceder. |
| RF-3781 | PDF sem camada de texto (escaneado) é reconhecido e explicado ("este PDF é uma imagem; o Desata ainda não lê texto de imagens"). PDF protegido por senha, malformado ou grande demais tem mensagem própria. Conteúdo ativo (JavaScript, anexos, formulários) nunca é executado. |
| RF-3782 | Trechos do documento não vão para logs, telemetria nem mensagens de erro técnicas; aparecem só na tela, onde a pessoa confere. A saída `falhas` traz o motivo sem copiar o conteúdo, a não ser que a pessoa peça. |
| RF-3783 | A extração é um objeto declarativo e versionado, com identificador e revisão, referenciado pela fonte, sem nome de marca, tema, caminho local nem segredo. O cache usa o conteúdo da extração, não só o número da revisão. |

### Guia

| ID | Requisito |
|---|---|
| RF-3790 | Guia e Manual com a seção do leitor de PDF, prints nos dois temas, o esquema visual de "como a regra encontra o dado" e um exemplo para experimentar com PDF de demonstração. O Manual abre no tópico do gesto atual (marcar campo, rótulo, tabela, ambiguidade, origem). |

## Fora do escopo da 0.8.5

- **OCR** (ler texto de PDF escaneado): exige motor e modelos pesados, com riscos próprios; spec própria.
- **Sugestões por IA**: mesma razão, e exige revisão humana desenhada à parte.
- **Vários layouts na mesma fonte** com escolha automática de extração: depende de ver as receitas em uso real.
- Editar, assinar ou anotar PDFs.

## Critérios de aceite

| ID | Critério | Requisitos |
|---|---|---|
| CA-01 | Marcar `R$ 125.430,00` e Criar campo mostra a coluna com 125430.00, tipo moeda, e liga à origem, sem sair da tela. | RF-3714, RF-3720, RF-3750 |
| CA-02 | Dois PDFs iguais com o cabeçalho em alturas diferentes: a regra "à direita de 'Total líquido'" acha o valor nos dois. | RF-3721 |
| CA-03 | PDF com dois totais candidatos: o campo fica Ambíguo, com os dois destacados; nenhum valor escolhido. | RF-3760 |
| CA-04 | Tabela Filial × Valor com uma célula em duas linhas: uma linha por filial depois de escolher a coluna que inicia linha. | RF-3730, RF-3731 |
| CA-05 | Tabela que continua na página 2 até "Total geral": todas as linhas, sem o cabeçalho repetido. | RF-3732, RF-3733 |
| CA-06 | Clicar numa célula abre a página exata com o trecho destacado; clicar na marcação mostra a célula. | RF-3750, RF-3751 |
| CA-07 | Criar campo pelo teclado, sem mouse, do início ao fim. | RF-3713 |
| CA-08 | A seleção coincide com o texto em 50%, 100%, 200%, com escala de tela 100%, 150% e 200%, e em página girada. | RF-3712 |
| CA-09 | Prévia de impacto diz "N de M avaliados" com os quatro estados e abre os casos problemáticos. | RF-3740, RF-3742 |
| CA-10 | Mudar uma regra mostra mantidos, corrigidos e que passaram a falhar, e permite desfazer. | RF-3743 |
| CA-11 | Arquivo novo na pasta entra na próxima execução; PDF alterado refaz a caixa; sem mudança, aproveita. | RF-3772 |
| CA-12 | Documento sem campo obrigatório com política "parar": a execução falha com mensagem clara, inclusive na linha de comando. | RF-3761, RF-3772 |
| CA-13 | PDF quebrado, protegido, escaneado ou que estoura o limite: mensagem clara, programa de pé, nada no log além do tipo de falha. | RF-3780..3782 |
| CA-14 | Fonte arrastada para o canvas cria Input Data; as saídas campos, itens, falhas e origem aparecem na lista. | RF-3770, RF-3771 |
| CA-15 | Duplicar a fonte para outra pasta aplica a mesma extração; os resultados identificam a revisão. | RF-3704, RF-3783 |
| CA-16 | Correção só neste documento aparece marcada e deixa de valer quando o documento muda. | RF-3762 |
