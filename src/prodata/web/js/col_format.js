// Formato de exibição da coluna (spec 050): moeda, número, porcentagem, documento e data. Só a aparência muda: o
// dado, o tipo e o CSV ficam como estão. Vai também no HTML exportado (dashboard/viewer.py): nada aqui depende do
// programa. A herança segue a mesma regra do motor (domain/display_formats.py), com os casos de
// tests/fixtures/formatos_heranca.json.

import { fmt, localNumber } from './dom.js';

export const MONTHS = ['jan.', 'fev.', 'mar.', 'abr.', 'mai.', 'jun.', 'jul.', 'ago.', 'set.', 'out.', 'nov.', 'dez.'];
export const MASKS = { cpf: '###.###.###-##', cnpj: '##.###.###/####-##', cep: '#####-###' };
export const MASK_NAMES = { cpf: 'CPF', cnpj: 'CNPJ', cep: 'CEP', phone: 'Telefone' };
export const DATE_PATTERNS = { dmy: 'dd/mm/aaaa', my: 'mm/aaaa', dmy_hm: 'dd/mm/aaaa hh:mm', long: '26 de nov. de 2026', iso: 'aaaa-mm-dd' };
export const SYMBOLS = ['R$', 'US$', '€', '£', '¥'];
export const DEFAULTS = { decimals: 2, thousands: true, symbol: 'R$', base: 'fraction', mask: 'cpf', pattern: 'dmy' };
const KEEP = { number: ['decimals', 'thousands'], currency: ['decimals', 'symbol'], percent: ['decimals', 'base'], document: ['mask'], date: ['pattern'] };
const NUMERIC = new Set(['Int64', 'Float64']);
const VALUE_AGGS = new Set(['sum', 'mean', 'min', 'max', 'median']);
// Os mesmos caracteres que o motor recusa (RF-5052): o texto vai para a tela, o HTML e o formato do Excel.
export const UNSAFE = /[<>"'\\\u0000-\u001f]/;

/** Os formatos que cabem num tipo de coluna (RF-5002). */
export function kindsFor(type) {
  if (NUMERIC.has(type)) return type === 'Int64' ? ['number', 'currency', 'percent', 'document'] : ['number', 'currency', 'percent'];
  if (type === 'String') return ['document'];
  if (type === 'Date' || type === 'Datetime') return ['date'];
  return [];
}

/** Só os campos do tipo, como o motor grava (DisplayFormat.compact). */
export function compact(spec) {
  const full = { ...DEFAULTS, ...spec };
  return { kind: full.kind, ...Object.fromEntries((KEEP[full.kind] || []).map((k) => [k, full[k]])) };
}

const plain = (v, d, thousands = true) => (thousands ? fmt.number(v, d) : localNumber(Number(v).toFixed(d).replace('.', ',')));

function number(spec, v, compactMode) {
  const d = spec.decimals ?? DEFAULTS.decimals;
  if (spec.kind === 'percent') {
    const p = (spec.base || DEFAULTS.base) === 'fraction' ? v * 100 : v;
    return `${compactMode && Math.abs(p) >= 1000 ? fmt.compact(p) : fmt.number(p, d)}%`;
  }
  const body = (x) => (compactMode && Math.abs(x) >= 1000 ? fmt.compact(x) : plain(x, d, spec.thousands ?? DEFAULTS.thousands));
  if (spec.kind === 'currency') {
    const symbol = spec.symbol ?? DEFAULTS.symbol;
    return `${v < 0 ? '-' : ''}${symbol ? `${symbol} ` : ''}${body(Math.abs(v))}`;
  }
  return body(v);
}

function fill(mask, digits) {
  let i = 0;
  return [...mask].map((c) => (c === '#' ? digits[i++] : c)).join('');
}

function documentText(spec, value) {
  const fromNumber = typeof value === 'number';
  if (fromNumber && !Number.isInteger(value)) return { text: String(value), bad: 'não é um número inteiro' };
  let digits = fromNumber ? String(Math.abs(value)) : String(value).replace(/\D/g, '');
  const key = spec.mask || DEFAULTS.mask;
  const name = MASK_NAMES[key] || 'a máscara';
  if (key === 'phone') {
    if (digits.length === 10) return { text: fill('(##) ####-####', digits), bad: null };
    if (digits.length === 11) return { text: fill('(##) #####-####', digits), bad: null };
    return { text: String(value), bad: `tem ${digits.length} dígitos; telefone tem 10 ou 11` };
  }
  const mask = MASKS[key] || key;
  const size = [...mask].filter((c) => c === '#').length;
  if (fromNumber && digits.length < size) digits = digits.padStart(size, '0'); // o zero à esquerda volta (RF-5004)
  if (digits.length !== size) return { text: String(value), bad: `tem ${digits.length} dígitos; ${name} tem ${size}` };
  return { text: fill(mask, digits), bad: null };
}

const ISO = /^(\d{4})-(\d{2})(?:-(\d{2}))?(?:[T ](\d{2}):(\d{2}))?/;

function dateText(spec, value) {
  const m = ISO.exec(String(value));
  if (!m) return { text: String(value), bad: 'não é uma data' };
  const [, y, mo, d = '01', hh = '00', mi = '00'] = m;
  const pattern = spec.pattern || DEFAULTS.pattern;
  const text = {
    dmy: `${d}/${mo}/${y}`,
    my: `${mo}/${y}`,
    dmy_hm: `${d}/${mo}/${y} ${hh}:${mi}`,
    long: `${Number(d)} de ${MONTHS[Number(mo) - 1] || mo} de ${y}`,
    iso: `${y}-${mo}-${d}`,
  }[pattern];
  return { text: text ?? String(value), bad: null };
}

/**
 * O valor no formato: `{ text, bad }`, com `bad` dizendo por que não coube (o texto volta como veio, RF-5031).
 * Sem formato (ou nulo): null, e quem chamou mostra como sempre mostrou. `compact`: eixo e rótulos (R$ 1,2 mi).
 */
export function formatValue(spec, value, { compact: compactMode = false } = {}) {
  if (!spec || !spec.kind || spec.kind === 'none' || value === null || value === undefined) return null;
  if (spec.kind === 'document') return documentText(spec, value);
  if (spec.kind === 'date') return dateText(spec, value);
  const n = typeof value === 'number' ? value : Number(value);
  if (typeof value === 'boolean' || !Number.isFinite(n) || (typeof value === 'string' && !value.trim())) {
    return { text: String(value), bad: 'não é um número' };
  }
  return { text: number(spec, n, compactMode), bad: null };
}

/** Texto do valor no formato, ou o que `fallback` daria sem formato. Para quem não marca o que não coube. */
export const formatted = (spec, value, fallback, opts) => formatValue(spec, value, opts)?.text ?? fallback(value);

/** Selo curto do cabeçalho (RF-5013). */
export function badge(spec) {
  switch (spec?.kind) {
    case 'currency': return spec.symbol || '$';
    case 'percent': return '%';
    case 'number': return localNumber('1,2');
    case 'document': return MASK_NAMES[spec.mask] || '###';
    case 'date': return { dmy: 'dd/mm', my: 'mm/aa', dmy_hm: 'dd/mm hh', long: 'nov.', iso: 'aaaa-mm' }[spec.pattern] || 'data';
    default: return '';
  }
}

const casas = (d) => `${d} ${d === 1 ? 'casa' : 'casas'}`;

/** O formato por extenso, para a dica e o diálogo. */
export function describe(spec) {
  const s = { ...DEFAULTS, ...spec };
  switch (s.kind) {
    case 'currency': return `Moeda ${s.symbol || '(sem símbolo)'}, ${casas(s.decimals)}`;
    case 'percent': return `Porcentagem, ${casas(s.decimals)} (${s.base === 'fraction' ? '0,15 → 15%' : '15 → 15%'})`;
    case 'number': return `Número, ${casas(s.decimals)}${s.thousands ? ', com milhar' : ', sem milhar'}`;
    case 'document': return MASK_NAMES[s.mask] ? `Documento: ${MASK_NAMES[s.mask]}` : `Documento: máscara ${s.mask}`;
    case 'date': return `Data: ${DATE_PATTERNS[s.pattern]}`;
    case 'none': return 'Sem formato';
    default: return '';
  }
}

/**
 * Formatos que valem na caixa: os dela e, por coluna que ela não definiu, os das entradas, na ordem das portas da
 * ferramenta (a primeira entrada ganha). `none` bloqueia o herdado e não aparece. Cada formato leva `from`: a caixa
 * onde foi definido (RF-5013).
 */
export function effectiveFormats(formats, nodes, edges, nodeId, ports = () => []) {
  const types = new Map((nodes || []).map((n) => [n.id, n.type]));
  const incoming = new Map();
  for (const e of edges || []) {
    if (!incoming.has(e.target)) incoming.set(e.target, []);
    incoming.get(e.target).push(e);
  }
  const memo = new Map();
  const walk = (id, seen) => {
    if (memo.has(id)) return memo.get(id);
    const order = ports(types.get(id)) || [];
    const rank = (h) => (order.includes(h) ? [order.indexOf(h), ''] : [order.length, h]);
    const list = [...(incoming.get(id) || [])].sort((a, b) => {
      const [ra, ha] = rank(a.targetHandle || 'in');
      const [rb, hb] = rank(b.targetHandle || 'in');
      return ra - rb || ha.localeCompare(hb);
    });
    const out = {};
    for (const e of list) {
      if (seen.has(e.source)) continue;
      for (const [col, spec] of Object.entries(walk(e.source, new Set([...seen, id])))) if (!(col in out)) out[col] = spec;
    }
    for (const [col, spec] of Object.entries(formats?.[id] || {})) out[col] = { ...spec, from: id };
    memo.set(id, out);
    return out;
  };
  return Object.fromEntries(Object.entries(walk(nodeId, new Set())).filter(([, s]) => s.kind && s.kind !== 'none'));
}

const isNumericKind = (spec) => ['number', 'currency', 'percent'].includes(spec?.kind);

/** Formato dos valores de um visual (RF-5023, RF-5024): soma, média, mínimo ou máximo de coluna com formato numérico. */
export function valueFormatFor(w, formats) {
  const column = w.widget_type === 'kpi' ? w.column : w.y_column;
  const agg = w.widget_type === 'kpi' ? w.metric : w.agg;
  const spec = column && VALUE_AGGS.has(agg) ? formats?.[column] : null;
  return isNumericKind(spec) ? spec : null;
}

const isLabelKind = (spec) => spec?.kind === 'date' || spec?.kind === 'document';
/** Formato das categorias de um visual: a coluna do eixo com formato de data ou documento (número em categoria,
 * como o ano, ficaria "2.026,00"). */
export const labelFormatFor = (w, formats) => (isLabelKind(formats?.[w.x_column]) ? formats[w.x_column] : null);

/** Nomes das categorias no formato da coluna, para o mesmo caminho dos nomes trocados no painel Formato. */
export function autoLabels(w, formats) {
  const out = {};
  const put = (spec, label) => {
    if (!spec || label === null || label === undefined || label === 'Outros') return;
    const r = formatValue(spec, label);
    if (r && !r.bad && r.text !== String(label)) out[label] = r.text;
  };
  const lf = labelFormatFor(w, formats);
  for (const s of w.series || []) put(lf, s.label);
  for (const p of w.points || []) put(lf, p.label);
  const sf = isLabelKind(formats?.[w.series_column]) ? formats[w.series_column] : null;
  for (const n of w.series_names || []) put(sf, n);
  return out;
}
