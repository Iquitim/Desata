# Plano da spec 037

## Biblioteca

**pypdfium2** (Apache-2.0 / BSD-3; PDFium, BSD-3): abre o PDF, desenha a página como imagem e dá a caixa de cada
caractere. Roda local, sem rede. O spike confirma que o pacote distribuído não traz o motor de JavaScript nem XFA
(formulários dinâmicos) e mede o custo no pacote.

## Leitura isolada

`prodata/documents/worker.py`: um processo filho (multiprocessing, `spawn`) faz toda a leitura de PDF: abrir, palavras
com posição, imagem da página. O processo principal só recebe dados prontos.

- **Tempo limite** por pedido; ao estourar, o filho é encerrado e recriado no próximo pedido.
- **Memória:** no Windows, o filho entra num *Job Object* com limite de memória por processo (via `ctypes`); fora do
  Windows, `resource.setrlimit(RLIMIT_AS)`. Antes de abrir: tamanho do arquivo; depois de abrir: número de páginas;
  na imagem: escala máxima e pixels máximos.
- **Uma leitura por vez** por processo filho (o PDFium não é seguro entre threads); a fila serializa os pedidos.
- Erros voltam como códigos (`protegido`, `malformado`, `sem_texto`, `grande_demais`, `tempo_esgotado`, `memoria`),
  nunca com trecho do documento.
- No executável (PyInstaller), `multiprocessing.freeze_support()` nos dois pontos de entrada.

## Palavras e coordenadas

Os caracteres viram palavras (quebra por espaço, por mudança de linha e por distância), e as palavras viram linhas.
Toda caixa é guardada **normalizada** (0 a 1, origem no canto superior esquerdo da página como ela aparece, já com a
rotação aplicada). A tela posiciona a camada de palavras em porcentagem sobre a imagem: o alinhamento não depende de
zoom, escala da tela nem resolução da imagem.

As palavras de cada arquivo ficam em cache (memória e disco), pela assinatura do arquivo (tamanho, data e um resumo do
conteúdo): reavaliar uma regra não relê o PDF.

## Extração (motor, sem interface)

`prodata/documents/recipe.py`: modelo Pydantic versionado (`schema_version`, `id`, `revisao`), com campos (nome, tipo,
obrigatório, regra) e tabelas (área de referência, guias, coluna que inicia linha, exclusões, fim). Regras de campo:
`rotulo` (rótulos, direção direita/abaixo, distância máxima), `secao` (dentro de um bloco que começa num rótulo) e
`posicao` (área fixa, frágil). O resumo de conteúdo (`digest`) entra no cache.

`prodata/documents/extract.py`: aplica a receita às palavras de um documento e devolve, por campo, o estado, os
candidatos (com caixa e página) e o valor convertido; por tabela, as linhas com a origem de cada célula.

- Rótulo: busca normalizada (sem acento, maiúscula e espaço extra); o valor é o grupo de palavras na direção pedida até
  um espaço grande ou o fim da linha (direita) ou a próxima linha que se sobrepõe na horizontal (abaixo).
- Vários rótulos encontrados com valores **diferentes** = Ambíguo; com o **mesmo** valor = Encontrado.
- Conversão por tipo (`types.py`): moeda e número no padrão brasileiro, datas, mês/ano, sim/não. Falhou = Inválido, sem
  inventar valor.
- Tabela: palavras dentro da área, agrupadas por linha; células pelas guias; uma linha nova começa quando a coluna
  escolhida tem valor, senão o texto se junta à linha anterior; cabeçalho repetido e rodapé reconhecidos pelo texto;
  continuação nas páginas seguintes a partir do cabeçalho até o texto de fim.

## Fonte na vista Dados

`PdfSources` guarda as fontes (`<datasets>_pdfs.json`) e `PdfRecipes` as extrações (`<datasets>_extracoes.json`),
separadas: a fonte aponta para a extração (id e revisão), e duplicar a fonte copia a referência. Segue o modelo da pasta
de arquivos: arquivo enviado, vinculado ou pasta com padrão, situação no cartão, organização e mapa de uso.

Input Data: `pdf:<id>/<saída>`. `DatasetStore.signature()` reconhece `pdf:`: arquivos (assinatura) + `digest` da
extração + versão do motor, então cache, subfluxos e linha de comando acompanham sem código próprio.

## Tela

Novo módulo `pdf_editor.js` (e partes em `pdf_page.js`, `pdf_table.js`), dentro da vista Dados:

- Página: imagem gerada pelo servidor, camada de palavras em porcentagem, seleção por clique, arraste, área e teclado.
- Barra de ação contextual sobre a seleção; prévia à direita com células clicáveis; Como encontrar editável.
- Tabela: guias arrastáveis desenhadas sobre a página; prévia das linhas; casos duvidosos destacados.
- Impacto e matriz: pedidos ao servidor que rodam em segundo plano, com cancelamento.

## Testes

PDFs sintéticos versionados em `tests/fixtures/pdf/` (gerados por script a partir de HTML pelo Chrome, com as
variações): campos com rótulo; mesmo layout com cabeçalho em outra altura; dois totais; tabela com célula de várias
linhas; tabela em duas páginas; página girada; escaneado (só imagem); protegido por senha; malformado.

Testes do motor (sem interface), da leitura isolada (tempo e memória), do cache, da API e de navegador (seleção em vários
zooms e escalas, teclado, origem, impacto, matriz).

## Spike (etapa 0)

Prova, de ponta a ponta e com esses PDFs: imagem e palavras; seleção alinhada em zoom e escala diferentes; regra por
rótulo; célula e volta à origem; estados nos layouts semelhantes; tabela com célula de várias linhas e guias; PDF
escaneado, protegido e quebrado isolados; cache refeito quando o PDF muda. O código do motor nasce já em
`prodata/documents/`; a tela do spike é um protótipo à parte, em `specs/037-leitor-visual-pdf/spike/`, fora do pacote.
Resultados em `spike.md`.
