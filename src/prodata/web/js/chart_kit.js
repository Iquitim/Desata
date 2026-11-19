// Peças comuns dos gráficos SVG (escalas, legendas, cores e dicas), usadas por charts.js e charts_motion.js.

import { fixedColors, paletteColor } from './dash_look.js';
import { fmt, h } from './dom.js';

const SVG = 'http://www.w3.org/2000/svg';
export const MAX_SLICES = 8;

export function svg(tag, attrs = {}, ...children) {
  const el = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) if (v !== null && v !== undefined) el.setAttribute(k, v);
  el.append(...children.flat(Infinity).filter(Boolean));
  return el;
}

export function niceStep(max, ticks = 4) {
  if (max <= 0) return 1;
  const raw = max / ticks;
  const pow = 10 ** Math.floor(Math.log10(raw));
  const n = raw / pow;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * pow;
}

export function truncate(text, maxChars) {
  return text.length > maxChars ? `${text.slice(0, Math.max(1, maxChars - 1))}…` : text;
}

export const CHAR_W = 6.5;
export const LABEL_GAP = 8;

/**
 * Rótulos do eixo que cabem sem sobrepor (spec 021): um a cada N, cada um com o espaço de N categorias.
 * Devolve a função que diz se o índice mostra rótulo e o texto já cortado para esse espaço.
 */
export function axisLabels(labels, band) {
  const longest = Math.min(14, Math.max(1, ...labels.map((l) => String(l).length)));
  const every = Math.max(1, Math.ceil((longest * CHAR_W + LABEL_GAP) / Math.max(1, band)));
  const chars = Math.max(2, Math.floor((band * every - LABEL_GAP) / CHAR_W));
  const text = (label) => truncate(String(label), chars);
  return {
    show: (i) => i % every === 0,
    text,
    // Nas pontas, o rótulo ancora para dentro: centralizado, seria cortado pela borda do gráfico.
    anchor: (x, label, width) => {
      const half = (text(label).length * CHAR_W) / 2;
      if (x - half < 0) return { x: 2, 'text-anchor': 'start' };
      if (x + half > width) return { x: width - 2, 'text-anchor': 'end' };
      return { x, 'text-anchor': 'middle' };
    },
  };
}

export const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

const norm = (s) => String(s).trim().toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');

/** Campos que o texto da dica aceita, com o valor já formatado (spec 041, RF-4142). */
export function tipFields(label, value, o, s = null) {
  const pct = o.total ? `${fmt.number((value / o.total) * 100, 1)}%` : '';
  const fields = { categoria: label, valor: o.full(value), percentual: pct };
  if (o.xName) fields[o.xName] = label;
  if (o.yName) fields[o.yName] = o.full(value);
  for (const [c, v] of Object.entries(s?.tip || {})) fields[c] = v === null || v === undefined ? '—' : fmt.number(v);
  return fields;
}

/** Troca {campo} pelo valor. Campo que não existe: null (a dica volta ao padrão). */
export function fillTip(text, fields) {
  const byName = new Map(Object.entries(fields).map(([k, v]) => [norm(k), v]));
  let unknown = false;
  const out = esc(text).replace(/\{([^{}]{1,60})\}/g, (_, name) => {
    if (!byName.has(norm(name))) { unknown = true; return ''; }
    return `<b>${esc(byName.get(norm(name)))}</b>`;
  });
  return unknown ? null : out;
}

/** Nomes entre chaves que não são campos (para sublinhar no painel). */
export function unknownTipFields(text, fields) {
  const known = new Set(Object.keys(fields).map(norm));
  return [...String(text || '').matchAll(/\{([^{}]{1,60})\}/g)].map((m) => m[1]).filter((n) => !known.has(norm(n)));
}

/** A dica de uma marca: o texto da pessoa, ou categoria, valor, % e colunas extras conforme o painel Formato. */
export function tipHtml(label, value, o, s = null, { percent = false } = {}) {
  const t = o.tip || {};
  const click = o.filterable && label !== 'Outros' ? '<em>Clique para filtrar</em>' : '';
  const fields = tipFields(label, value, o, s);
  if (t.text) {
    const filled = fillTip(t.text, fields);
    if (filled !== null) return `<span class="tip-text">${filled}</span>${click}`;
  }
  const extras = Object.entries(s?.tip || {}).map(([c, v]) => `<span>${esc(c)}: <b>${esc(v === null || v === undefined ? '—' : fmt.number(v))}</b></span>`).join('');
  return `${t.label === false ? '' : `<span>${esc(label)}</span>`}${t.value === false ? '' : `<b>${esc(o.full(value))}</b>`}`
    + `${(percent || t.percent) && fields.percentual ? `<span>${fields.percentual} do total</span>` : ''}${extras}${click}`;
}

/** Opções completas a partir do formato salvo no item (ou dos padrões de antes). */
export function options(opts = {}) {
  const affix = (s) => `${opts.prefix || ''}${s}${opts.suffix || ''}`;
  const decimals = opts.decimals ?? 1;
  // Com cor por categoria, o que não tem cor própria segue a paleta das demais; "page" é a paleta geral do dashboard.
  const chosen = opts.palette === 'custom' ? opts.other_palette : opts.palette;
  return {
    palette: !chosen || chosen === 'page' ? opts._page_palette || 'brand' : chosen,
    custom: opts.palette === 'custom',
    color: opts.color || '',
    categoryColors: opts.category_colors || {},
    labels: opts.data_labels, // undefined = comportamento original de cada gráfico
    grid: opts.grid ?? true,
    legend: opts.show_legend ?? true,
    legendPos: opts.legend_position || 'top',
    // Nome original de uma categoria renomeada no painel Formato: as cores seguem o dado, não o texto.
    keyOf: opts._keyOf || ((name) => name),
    filterable: Boolean(opts._filterable),
    selected: opts._selected || null,
    xTitle: opts.x_title || '',
    yTitle: opts.y_title || '',
    yMin: opts.y_min ?? null,
    yMax: opts.y_max ?? null,
    yLog: opts.y_scale === 'log',
    // Linha de referência da caixa Chart, com as cores acima e abaixo escolhidas no painel Formato.
    ref: opts._ref ? { value: opts._ref.value, label: opts._ref.label, paint: opts.ref_paint ?? true,
      above: opts.ref_above || 'var(--ok)', below: opts.ref_below || 'var(--err)' } : null,
    // Spec 042 (RF-4236): sem valores no eixo Y ou sem rótulos no eixo X, o espaço deles volta para o gráfico.
    yValues: opts.show_y_values ?? true,
    xLabels: opts.show_x_labels ?? true,
    tip: { label: opts.tip_label ?? true, value: opts.tip_value ?? true, percent: Boolean(opts.tip_percent), text: opts.tip_text || '' },
    xName: opts._x || '',
    yName: opts._y || '',
    total: opts._total ?? null,
    short: (v) => affix(opts.label_format === 'full' ? fmt.number(v, decimals) : fmt.compact(v)),
    full: (v) => affix(fmt.number(v, opts.label_format === 'full' ? decimals : undefined)),
  };
}

/**
 * Cor de uma marca. `multi`: cada categoria tem a sua cor (rosca); senão é uma série só (--series-1).
 * Devolve atributos SVG: classe da paleta ou estilo com a cor escolhida.
 */
export function paint(o, i, label, multi) {
  const slot = (i % MAX_SLICES) + 1;
  const custom = o.custom && o.categoryColors[o.keyOf(label)];
  if (custom) return { style: `fill:${custom}` };
  if (o.palette === 'single' && o.color) return { style: `fill:${o.color}${multi ? `;fill-opacity:${Math.max(0.35, 1 - i * 0.12)}` : ''}` };
  if (o.palette === 'alt') return multi ? { class: `a${slot}` } : { style: 'fill:var(--alt-1)' };
  if (fixedColors(o.palette)) return { style: `fill:${paletteColor(o.palette, multi ? i : 0)}` };
  return multi ? { class: `s${slot}` } : {};
}

/** Categoria que dá para clicar (filtra a página); "Outros" junta várias e não é um valor. */
export const catAttr = (o, label) => (o.filterable && label !== 'Outros' ? { 'data-cat': o.keyOf(label) } : {});
/** Com um filtro nesta coluna, o que ficou de fora aparece apagado. */
export const isDim = (o, label) => Boolean(o.selected && !o.selected.has(o.keyOf(label)));

/** Quais índices recebem número em destaque ("Todos" mostra cada um; spaced() tira os que se encostariam). */
export function labelled(series, mode, fallback) {
  const pick = mode ?? fallback;
  if (pick === 'all') return new Set(series.map((_, i) => i));
  if (pick === 'none' || !series.length) return new Set();
  const max = series.reduce((best, s, i) => (s.value > series[best].value ? i : best), 0);
  const min = series.reduce((best, s, i) => (s.value < series[best].value ? i : best), 0);
  return new Set(pick === 'max_min' ? [max, min] : pick === 'last' ? [series.length - 1] : [max]);
}

/**
 * Com muitos rótulos, mantém só os que não encostam no anterior (em x): nada se sobrepõe (spec 042, RF-4235).
 * `xOf(i)` é o centro do rótulo; `textOf(i)`, o texto.
 */
export function spaced(shown, xOf, textOf) {
  if (shown.size < 2) return shown;
  const out = new Set();
  let right = -Infinity;
  for (const i of [...shown].sort((a, b) => xOf(a) - xOf(b))) {
    const half = (String(textOf(i)).length * CHAR_W) / 2 + 2;
    if (xOf(i) - half >= right) { out.add(i); right = xOf(i) + half; }
  }
  return out;
}

/** Tooltip compartilhado por um cartão; as marcas declaram data-tip. */
export function withTooltip(card, chart) {
  const tip = h('div', { class: 'chart-tip', role: 'tooltip', hidden: true });
  chart.addEventListener('pointermove', (e) => {
    const mark = e.target.closest('[data-tip]');
    if (!mark) { tip.hidden = true; return; }
    tip.hidden = false;
    tip.innerHTML = mark.dataset.tip;
    // O cartão pode estar dentro de uma página escalada (dashboard, spec 014): converte para px do cartão.
    const r = card.getBoundingClientRect();
    const k = card.offsetWidth ? r.width / card.offsetWidth : 1;
    const x = Math.max(4, Math.min((e.clientX - r.left) / k + 12, card.offsetWidth - tip.offsetWidth - 8));
    tip.style.transform = `translate(${x}px, ${Math.max(4, (e.clientY - r.top) / k - tip.offsetHeight - 10)}px)`;
  });
  chart.addEventListener('pointerleave', () => { tip.hidden = true; });
  card.append(tip);
}

export function roundedBar(x, y, w, hgt, vertical) {
  if (hgt <= 0 || w <= 0) return '';
  const r = Math.min(4, (vertical ? w : hgt) / 2, vertical ? hgt : w);
  return vertical
    ? `M${x},${y + hgt} V${y + r} Q${x},${y} ${x + r},${y} H${x + w - r} Q${x + w},${y} ${x + w},${y + r} V${y + hgt} Z`
    : `M${x},${y} H${x + w - r} Q${x + w},${y} ${x + w},${y + r} V${y + hgt - r} Q${x + w},${y + hgt} ${x + w - r},${y + hgt} H${x} Z`;
}

export function yGrid(sc, y, m, width, o) {
  const out = [];
  for (const v of sc.ticks) {
    if (o.grid) out.push(svg('line', { class: 'grid', x1: m.left, x2: width - m.right, y1: y(v), y2: y(v) }));
    if (o.yValues !== false) out.push(svg('text', { class: 'tick y-tick', x: m.left - 8, y: y(v) + 4, 'text-anchor': 'end' }, fmt.compact(v)));
  }
  return out;
}

/** Margens com espaço para os títulos dos eixos, quando houver. */
export function margins(base, o) {
  const left = o.yValues === false ? 12 : base.left;
  const bottom = o.xLabels === false ? 10 : base.bottom;
  return { ...base, left: left + (o.yTitle ? 16 : 0), bottom: bottom + (o.xTitle ? 18 : 0) };
}

export function axisTitles(o, m, width, height) {
  return [
    o.xTitle ? svg('text', { class: 'axis-title', x: m.left + (width - m.left - m.right) / 2, y: height - 4, 'text-anchor': 'middle' }, o.xTitle) : null,
    o.yTitle ? svg('text', { class: 'axis-title', x: 0, y: 0, 'text-anchor': 'middle',
      transform: `translate(12 ${m.top + (height - m.top - m.bottom) / 2}) rotate(-90)` }, o.yTitle) : null,
  ];
}

/**
 * Escala do eixo Y: automática a partir de zero, ou com mínimo/máximo escolhidos no formato. Devolve as marcas do
 * eixo (`ticks`) e `frac(v)`, a posição de 0 (embaixo) a 1 (em cima). Com `o.yLog` (spec 042, RF-4257), a escala é
 * logarítmica de base 10: zero e negativos não cabem e ficam no pé do eixo.
 */
export function yScale(values, o, fromZero) {
  const positive = values.filter((v) => v > 0);
  if (o.yLog && positive.length) return logScale(positive, o);
  const dataMin = Math.min(...values);
  const dataMax = Math.max(...values);
  let lo = o.yMin ?? (fromZero ? Math.min(0, dataMin) : Math.min(0, dataMin));
  let hi = o.yMax ?? dataMax;
  if (hi <= lo) hi = lo + 1;
  const step = niceStep(hi - lo);
  if (o.yMin === null || o.yMin === undefined) lo = Math.floor(lo / step) * step;
  if (o.yMax === null || o.yMax === undefined) hi = Math.ceil(hi / step) * step || 1;
  const ticks = [];
  for (let v = lo; v <= hi + 1e-9; v += step) ticks.push(v);
  return { lo, hi, step, ticks, log: false, frac: (v) => (Math.min(hi, Math.max(lo, v)) - lo) / (hi - lo) };
}

function logScale(positive, o) {
  // Limites redondos na sequência 1, 2, 5, 10…: o gráfico usa a altura toda, sem décadas vazias.
  const nice = [1, 2, 5];
  const floor = (v) => { const e = Math.floor(Math.log10(v)); return [...nice].reverse().map((k) => k * 10 ** e).find((c) => c <= v * (1 + 1e-9)) ?? 10 ** e; };
  const ceil = (v) => { const e = Math.floor(Math.log10(v)); return [...nice, 10].map((k) => k * 10 ** e).find((c) => c >= v * (1 - 1e-9)); };
  const lo = o.yMin > 0 ? o.yMin : floor(Math.min(...positive));
  let hi = o.yMax > lo ? o.yMax : ceil(Math.max(...positive));
  if (hi <= lo) hi = lo * 10;
  const a = Math.log10(lo);
  const b = Math.log10(hi);
  const ticks = [];
  for (let e = Math.floor(a) - 1; e <= Math.ceil(b); e += 1) {
    for (const k of nice) { const v = k * 10 ** e; if (v >= lo * (1 - 1e-9) && v <= hi * (1 + 1e-9)) ticks.push(v); }
  }
  // Muitas décadas: só as potências de 10, para os rótulos não se amontoarem.
  const shown = ticks.length > 7 ? ticks.filter((v) => Math.abs(Math.log10(v) % 1) < 1e-9) : ticks;
  return { lo, hi, step: 0, ticks: shown, log: true, frac: (v) => (v <= 0 ? 0 : Math.min(1, Math.max(0, (Math.log10(v) - a) / (b - a)))) };
}

/** Valores do eixo com a linha de referência, para ela sempre caber na escala. */
export const withRef = (values, o) => (o.ref ? [...values, o.ref.value] : values);

/** Cor de uma marca pela linha de referência (acima ou abaixo), ou null sem linha ou sem pintar. */
export const refFill = (o, v) => (o.ref?.paint ? (v >= o.ref.value ? o.ref.above : o.ref.below) : null);

/** A linha de referência na horizontal (gráficos com eixo Y), com o rótulo e o valor na ponta direita. */
export function refLine(o, y, x1, x2) {
  if (!o.ref) return null;
  const yy = y(o.ref.value);
  return svg('g', { class: 'ref-line', 'data-tip': `<span>${esc(o.ref.label)}</span><b>${esc(o.full(o.ref.value))}</b>` },
    svg('line', { x1, x2, y1: yy, y2: yy }),
    svg('text', { x: x2 - 2, y: yy - 5, 'text-anchor': 'end' }, `${o.ref.label} · ${o.short(o.ref.value)}`));
}

/** Cor (CSS) da série i: a mesma regra de paint(), em forma de valor para fill/stroke. */
export function tone(o, i, name) {
  if (o.custom && o.categoryColors[o.keyOf(name)]) return o.categoryColors[o.keyOf(name)];
  if (o.palette === 'single' && o.color) return o.color;
  return paletteColor(o.palette, i % MAX_SLICES);
}

/** Gráfico com legenda acima ou abaixo (ou sem legenda, se o formato pedir) e rodapé opcional. */
export function framed(o, legend, chart, foot = null) {
  return h('div', { class: 'multi-chart' },
    o.legend && o.legendPos === 'top' ? legend : null, chart, o.legend && o.legendPos === 'bottom' ? legend : null, foot);
}

export const LEGEND_H = 30;

/** Legenda em linha: com 2 ou mais séries vem ligada por padrão (a cor nunca identifica sozinha). */
export const LEGEND_LINE = 22;
export const PARETO_LEGEND_W = 460;
export const LEGEND_MAX_LINES = 3;
export const LEGEND_NAME_CHARS = 26;
export const legendItemWidth = (name) => 24 + Math.min(LEGEND_NAME_CHARS, String(name).length) * CHAR_W;

/**
 * Quantos nomes da legenda cabem em até 3 linhas, e em quantas linhas ficam (spec 021).
 * O resto vira "+N", com os nomes no detalhe: a legenda nunca toma o espaço do gráfico.
 */
export function legendLayout(names, width) {
  let line = 1;
  let used = 0;
  let fits = 0;
  for (const name of names) {
    const need = legendItemWidth(name) + 14;
    if (used + need > width && used) { line += 1; used = 0; }
    if (line > LEGEND_MAX_LINES) break;
    used += need;
    fits += 1;
  }
  // O "+N" também precisa caber na última linha.
  if (fits < names.length && used + 60 > width && fits > 1) fits -= 1;
  return { fits, height: Math.min(line, LEGEND_MAX_LINES) * LEGEND_LINE };
}

export function legendRow(names, colors, width = Infinity) {
  const { fits } = legendLayout(names, width);
  const hidden = names.slice(fits);
  return h('ul', { class: 'legend-row' }, names.slice(0, fits).map((n, i) => h('li', { title: n },
    h('i', { class: 'swatch', style: { background: colors[i], opacity: colors[i] === colors[0] && i ? Math.max(0.35, 1 - i * 0.12) : null } }),
    h('span', { class: 'ellipsis' }, n))),
  hidden.length ? h('li', { class: 'legend-more', title: hidden.join('\n') }, `+${hidden.length}`) : null);
}

export function multiTip(label, rows, o, total) {
  return `<span>${esc(label)}</span>${rows.map(([n, v]) => `<span>${esc(n)}: <b>${esc(o.full(v))}</b></span>`).join('')}`
    + (total === undefined ? '' : `<span>Total: <b>${esc(o.full(total))}</b></span>`);
}
