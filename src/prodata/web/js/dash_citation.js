// Citação automática das fontes públicas (spec 049, RF-4963): no rodapé do dashboard, da imagem e do HTML exportado.
// "Fonte: Banco Central do Brasil, SGS 432 — Taxa Selic; IBGE, tabela 6579. Lidos em 21/11/2026." A licença que pede
// atribuição (a ODbL do Banco Central e do Tesouro) vem escrita logo abaixo. Este módulo vai junto no HTML exportado:
// não usa o estado do programa, só o que recebe.

import { h } from './dom.js';

const day = (iso) => new Date(iso).toLocaleDateString('pt-BR');
const ATTRIBUTION = /ODbL|Open Database License/i;
const CHARS_PER_LINE = 190; // o que cabe numa linha da página de 1600 px, para a altura da faixa na imagem

/** As citações das caixas Dados públicos que executaram, sem repetir; ``null`` quando o fluxo não tem nenhuma. */
export function buildCitation(nodes = [], results = {}) {
  const seen = new Map();
  for (const n of nodes) {
    if (!['io.public_data', 'io.input_data'].includes(n.type) || n.disabled) continue; // Input Data: a pasta do CNPJ
    const f = results?.[n.id]?.extra?.fonte_publica;
    if (!f?.citacao) continue;
    const before = seen.get(f.citacao);
    // A mesma fonte lida em momentos diferentes: vale a leitura mais antiga, que é a que o dashboard pode estar mostrando.
    if (!before || (f.lido_em && (!before.lido_em || f.lido_em < before.lido_em))) seen.set(f.citacao, f);
  }
  const items = [...seen.values()];
  if (!items.length) return null;
  const days = [...new Set(items.map((f) => (f.lido_em ? day(f.lido_em) : '')).filter(Boolean))];
  const sources = days.length > 1 ? items.map((f) => (f.lido_em ? `${f.citacao} (lido em ${day(f.lido_em)})` : f.citacao)) : items.map((f) => f.citacao);
  return {
    texto: `Fonte: ${sources.join('; ')}.${days.length === 1 ? ` Lidos em ${days[0]}.` : ''}`,
    licencas: [...new Set(items.map((f) => f.licenca || '').filter((l) => ATTRIBUTION.test(l)))],
  };
}

/** O rodapé com a citação. ``action``: um botão ao lado (no programa, Ocultar). */
export function citationFooter(citation, { action = null, width = null } = {}) {
  if (!citation) return null;
  return h('footer', { class: 'dash-citation', ...(width ? { style: { width: `${width}px` } } : {}) },
    h('div', { class: 'dash-citation-text' },
      h('p', {}, citation.texto),
      citation.licencas.map((l) => h('p', { class: 'dash-citation-license' }, l))),
    action);
}

/** A altura da faixa da citação na imagem (a página tem largura fixa). */
export function citationHeight(citation) {
  if (!citation) return 0;
  const lines = [citation.texto, ...citation.licencas].reduce((n, text) => n + Math.ceil(text.length / CHARS_PER_LINE), 0);
  return 30 + lines * 22; // 10 px de margem em cima e 20 de preenchimento
}
