// Nomes das saídas do leitor de PDF (spec 037), sem dependências: usados na vista Dados e no seletor do Input Data.

export const OUTPUT_TEXT = {
  campos: ['Resumo de cada documento', 'uma linha por documento, uma coluna por campo'],
  falhas: ['Falhas', 'o que faltou ou ficou em dúvida, documento por documento, sem copiar o conteúdo'],
  origem: ['Origem', 'de onde veio cada valor: página e região do documento'],
};

export const outputText = (name) => OUTPUT_TEXT[name]
  || [`Linhas de “${name.replace(/^itens_/, '')}”`, 'uma linha por item, com o documento de origem'];
