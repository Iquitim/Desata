# Spike da spec 037: leitor visual de PDF

**Conclusão:** viável, sem cortar escopo. Os três desafios técnicos que poderiam derrubar a experiência (alinhamento,
direção do texto e isolamento) foram resolvidos no próprio spike, e o motor já nasceu no pacote com testes. A
implementação completa na vista Dados (T01..T13) pode começar.

O protótipo usa o motor de verdade e os tokens do Desata. Para rodar:

```
uv run python specs/037-leitor-visual-pdf/spike/prototipo.py           # http://127.0.0.1:8737
uv run --with playwright --with pillow python specs/037-leitor-visual-pdf/spike/teste_navegador.py <pasta>
```

## O que foi provado

| Tarefa | Resultado |
|---|---|
| S01 PDFs sintéticos | 10 arquivos em `tests/fixtures/pdf/` (script `spike/gerar_pdfs.py`). "Total geral" é sempre a soma das linhas, para os testes conferirem valores de verdade. |
| S02 Leitura isolada | Processo filho (`spawn`) com Job Object no Windows (`RLIMIT_AS` fora dele). Tempo esgotado em 2 s volta como `tempo_esgotado`; pedir 2 GB com teto de 600 MB volta como `memoria`. Nos dois casos o programa segue, e o pedido seguinte sobe um leitor novo. Primeira leitura: ~190 ms com a subida do processo; depois, ~5 ms. |
| S03 Palavras e imagem | Caixas normalizadas (0 a 1, origem em cima à esquerda, rotação aplicada). A imagem respeita o limite de pixels. Escaneado → `sem_texto`, senha → `protegido`, cortado → `malformado`. |
| S04 Biblioteca | pypdfium2 5.15.2 (Apache-2.0/BSD-3; PDFium BSD-3). `PDFIUM_INFO` sem V8 e sem XFA: o PDFium distribuído não executa JavaScript nem formulário dinâmico. Custo: 7,8 MB. |
| S05 Regras de campo | Rótulo à direita ou abaixo, com variações, sem acento nem maiúscula; seção; posição fixa marcada como frágil. Os estados Encontrado, Ausente, Ambíguo, Inválido e Não suportado aparecem nos PDFs certos. Os tipos seguem o padrão brasileiro. |
| S06 Tabelas | Guias pelos espaços em branco, que não cortam palavra do cabeçalho. "Nova linha quando *filial* tem valor" une a observação de duas linhas. O cabeçalho repetido na página 2 é ignorado e a tabela para em "Total geral": 32 linhas, soma igual ao total impresso. |
| S07 Protótipo de tela | Ver abaixo. |
| S08 Alinhamento | No Chrome: zoom 50/100/200% × escala de tela 1/1,5/2 × 3 documentos (normal, página girada, conteúdo girado dentro do PDF). Em todas as 27 combinações, **0 palavras fora do texto**. A medida conta os pixels de tinta dentro de cada caixa desenhada pela tela. |
| S09 Cache | A chave é o conteúdo do PDF (BLAKE2), não o nome. Trocar o arquivo com o mesmo nome refaz palavras e extração; reabrir o programa aproveita o disco. Um PDF quebrado não é relido; tempo esgotado e memória não ficam guardados. Arquivo aberto com senha nunca vai para o disco. |

Testes: `tests/test_pdf_engine.py`, 38 casos (tipos, leitura, motor, sugestões, rotação, leitura isolada e cache). Os
critérios CA-01 a CA-05 estão cobertos no motor e no navegador.

## A experiência no protótipo

- **Marcar:** clique numa palavra, dois cliques no valor inteiro, arraste uma área. Pelo teclado: setas andam pelas
  palavras na ordem de leitura, Shift estende, Home/End vão ao início e ao fim da linha.
- **Ver o dado nascer:** a barra sobre a seleção mostra, antes de criar, o valor convertido, o tipo e como o Desata vai
  achar o valor ("R$ 834.086,00 · Moeda (R$) · à direita de 'Total líquido'"). Enter cria o campo; ele "voa" da página
  para o painel e pulsa na página com o nome. Com três ou mais linhas marcadas, o botão principal vira Criar tabela (T).
- **Rastrear a origem, nos dois sentidos:** clicar num valor ou numa célula rola a página até a origem e pulsa a caixa,
  inclusive na página 2. Clicar no PDF sobre um valor já extraído destaca o campo ou a célula no painel.
- **Ajustar e ver na hora:** arrastar uma guia (ou usar as setas) muda a prévia ao vivo. No teste, "São Paulo" virou
  "São Paulo R$" e voltou ao soltar. Coluna que inicia linha, texto de fim, tipo, nome e obrigatório mudam ali mesmo.
- **Impacto:** a extração roda em todos os documentos a cada mudança. O painel mostra "Avaliado em 9 de 9: 4 aprovados
  · 2 para revisar · 3 falharam", com o motivo em cada documento.
- **Ambíguo e ilegível:** com dois totais, nenhum valor é escolhido; os dois aparecem numerados na página e no painel.
  Escaneado, protegido e danificado mostram o motivo em linguagem simples, e os outros seguem.
- Claro e escuro pelos tokens. Situação sempre com ícone e texto, além da cor. `prefers-reduced-motion` respeitado.

## Problemas encontrados e resolvidos

1. **Direção do texto.** O motor agrupava linhas pela horizontal da tela. Isso falhava na página girada e, pior, no caso
   mais comum de relatório em paisagem: página em pé com rotação, em que o texto corre na vertical dentro do PDF e o
   leitor nem formava as palavras. Correção:
   - o leitor detecta a direção dominante pela sequência dos caracteres e monta as palavras nesse referencial;
   - cada página informa o ângulo de leitura (`t`);
   - o motor trabalha no "espaço de leitura", e a origem continua em coordenadas de tela.

   Resultado: a mesma extração dá o mesmo resultado nas três versões do relatório.
2. **O PDFium reordena os caracteres pela rotação da página** e mistura linhas. A rotação agora é zerada só na memória
   antes de ler o texto; o arquivo não é alterado.
3. **Guia arrastada travava:** a prévia ao vivo redesenhava as marcas e destruía o elemento em arraste. Agora, durante
   o arraste, só o painel é atualizado; as marcas voltam ao soltar.
4. **Rótulos das marcas cobriam o texto do PDF.** Em repouso, só o contorno colorido aparece. O nome surge com o card em
   foco, na origem pulsando, no campo recém-criado e sempre nos candidatos ambíguos, que precisam do número.
5. **A barra de ação piscava** porque era recriada a cada sugestão. Agora anima só quando aparece.

## Limitações e decisões para a implementação

- **Fora do escopo, como combinado:** OCR (escaneado fica Não suportado, com explicação), sugestões por IA e vários
  layouts numa mesma extração.
- **A posição fixa usa o espaço de leitura da página.** Ela fica frágil de propósito e é assim explicada na tela.
- **Nomes de coluna e campo** são gerados sem acento (`total_liquido`), como os nomes de coluna do resto do Desata. O
  rótulo original aparece em "Como encontrar".
- **Prévia de impacto:** o protótipo avalia todos os documentos, que são poucos. Na vista Dados, a amostra é limitada e
  o painel mostra "N de M avaliados", com cancelamento.
- **Linhas que só continuam texto** (sem a coluna que inicia linha) são unidas à linha anterior. Uma continuação com
  valor numa coluna que não é texto marca a linha como duvidosa, sem descartar nada.
- **Cache em disco** guarda as palavras (texto do documento) na pasta de dados do programa, como os demais caches de
  dados. Não guarda nada de PDF com senha, e nada disso vai para log.
- **Empacotamento:** `multiprocessing.freeze_support()` precisa entrar nos dois pontos de entrada do executável (T11),
  e o teste do instalador deve abrir um PDF pelo leitor isolado.
- **Correção só neste documento** (RF-3762) vai usar a mesma assinatura de conteúdo do cache: se o PDF muda, a correção
  deixa de valer sozinha.
