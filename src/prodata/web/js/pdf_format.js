// Formatação do leitor de PDF (spec 037): valores no padrão brasileiro, situações com ícone e texto (RF-3760)
// e "como encontrar" em linguagem simples (RF-3721).

import { fmt, h } from './dom.js';
import { icon } from './icons.js';

export const STATE = {
  encontrado: ['ok', 'check', 'Encontrado'], ausente: ['err', 'x', 'Ausente'], ambiguo: ['warn', 'alert', 'Ambíguo'],
  invalido: ['err', 'alert', 'Inválido'], nao_suportado: ['err', 'x', 'Não suportado'],
  aprovado: ['ok', 'check', 'Aprovado'], revisar: ['warn', 'alert', 'Revisar'], falhou: ['err', 'x', 'Falhou'],
};
export const chip = (state, text) => {
  const [tone, ic, label] = STATE[state] || ['info', 'info', state];
  return h('span', { class: ['pe-chip', `tone-${tone}`] }, icon(ic, 11), text || label);
};
export const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
const brl = { format: (v) => fmt.intl(v, { style: 'currency', currency: 'BRL' }) };
const num = { format: (v) => fmt.intl(v, { maximumFractionDigits: 6 }) };

export function showValue(value, kind) {
  if (value === null || value === undefined) return '—';
  if (kind === 'moeda') return brl.format(Number(value));
  if (kind === 'inteiro' || kind === 'decimal') return num.format(Number(value));
  if (kind === 'data') { const [y, m, d] = String(value).split('-'); return `${d}/${m}/${y}`; }
  if (kind === 'mes_ano') {
    const [y, m] = String(value).split('-');
    return new Date(+y, +m - 1, 1).toLocaleDateString('pt-BR', { month: 'short', year: 'numeric' }).replace('. de ', '/').replace(' de ', '/');
  }
  if (kind === 'sim_nao') return value ? 'Sim' : 'Não';
  return String(value);
}

export function howText(rule) {
  if (rule.tipo === 'posicao') return `na mesma posição da página ${rule.pagina + 1}`;
  const where = rule.direcao === 'direita' ? 'à direita de' : 'abaixo de';
  const labels = rule.rotulos.map((r) => `“${r}”`).join(' ou ');
  const words = rule.palavras ? `, só ${rule.palavras === 1 ? 'a primeira palavra' : `as ${rule.palavras} primeiras palavras`}` : '';
  return rule.tipo === 'secao' ? `${where} ${labels}, dentro de “${rule.inicio[0]}”${words}` : `${where} ${labels}${words}`;
}

export const clone = (x) => JSON.parse(JSON.stringify(x));
export const slug = (text) => text.normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '').slice(0, 60);

// ------------------------------------------------------------------ curingas no rótulo (0.9.6)

const MONTHS = new Set(['janeiro', 'fevereiro', 'marco', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro',
  'jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']);
const plainWord = (w) => w.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/^[:;,.()[\]"'–-]+|[:;,.()[\]"'–-]+$/g, '');
const DATE = /^(\d{1,2}[/.-])?\d{1,2}[/.-]\d{2,4}$|^\d{4}-\d{2}(-\d{2})?$/;
export const isWildcard = (w) => /^\[(mês|mes|ano|data|número|numero|\*)\]$/i.test(w);

/** O curinga de uma palavra que muda de um PDF para outro: [mês], [ano], [data], [número] ou [*]. */
export function wildcardFor(word) {
  const t = plainWord(word);
  if (MONTHS.has(t)) return '[mês]';
  if (/^(19|20)\d\d$/.test(t)) return '[ano]';
  if (DATE.test(t)) return '[data]';
  if (/^[-+]?\d[\d.,]*%?$/.test(t)) return '[número]';
  return '[*]';
}

/** O rótulo marcado, com mês, ano e data já como curinga (a mesma regra do programa ao propor um campo). */
export function generalizeLabel(label) {
  const changed = [];
  const words = label.split(/\s+/).filter(Boolean).map((w) => {
    if (isWildcard(w)) return w;
    const wild = wildcardFor(w);
    if (['[mês]', '[ano]', '[data]'].includes(wild)) { changed.push(`${w.replace(/[:;,.]+$/, '')} → ${wild}`); return wild; }
    return w;
  });
  return { label: words.join(' '), changed };
}
