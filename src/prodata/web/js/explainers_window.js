// "Como funciona" do Rank e do Append Fields (spec 044). Usam a configuração e, quando as caixas anteriores já
// executaram, uma amostra dos dados que chegam. Só ilustram: o resultado de verdade é o do motor.

import { api } from './api.js';
import { fmt, h } from './dom.js';
import { nodeResult, store } from './store.js';

const show = (v) => (v === null || v === undefined || v === '' ? '—' : typeof v === 'number' ? fmt.number(v) : String(v));
const blank = (v) => v === null || v === undefined || v === '';

/** Linhas que chegam numa entrada da caixa, se a anterior já executou. */
function inputRows(n, port, limit = 40) {
  const edge = store.workflow.edges.find((e) => e.target === n.id && e.targetHandle === port);
  if (!edge || !nodeResult(edge.source)?.anchors?.[edge.sourceHandle]) return Promise.resolve(null);
  return api.results(store.workflow.id, edge.source, edge.sourceHandle, { limit }).then((p) => p.rows).catch(() => null);
}

/** Quantas linhas chegam numa entrada, pela última execução da caixa anterior (null = ainda não executou). */
export function inputCount(n, port) {
  const edge = store.workflow.edges.find((e) => e.target === n.id && e.targetHandle === port);
  const anchor = edge ? nodeResult(edge.source)?.anchors?.[edge.sourceHandle] : null;
  return Number.isFinite(anchor?.row_count) ? { rows: anchor.row_count, cols: anchor.columns?.length ?? null } : null;
}

// ------------------------------------------------------------------ Rank

const RANK_EXAMPLE = [
  { vendedor: 'Ana', regiao: 'Sul', vendas: 120 }, { vendedor: 'Davi', regiao: 'Norte', vendas: 90 },
  { vendedor: 'Bia', regiao: 'Sul', vendas: 300 }, { vendedor: 'Eva', regiao: 'Norte', vendas: 150 },
  { vendedor: 'Caio', regiao: 'Sul', vendas: 300 }, { vendedor: 'Gil', regiao: 'Sul', vendas: 80 },
  { vendedor: 'Fábio', regiao: 'Norte', vendas: 150 },
];

function compare(a, b) {
  if (a === b) return 0;
  if (blank(a)) return 1;
  if (blank(b)) return -1;
  return a < b ? -1 : 1;
}

/** O mesmo cálculo do motor: ordena por grupo e classificação (vazios por último), numera e trata o empate. */
export function rankRows(rows, { order, groups, method }) {
  const keyOf = (r) => JSON.stringify(groups.map((g) => r[g]));
  const sorted = rows.map((row, at) => ({ row, at })).sort((x, y) => {
    for (const g of groups) { const c = compare(x.row[g], y.row[g]); if (c) return c; }
    for (const o of order) {
      const c = compare(x.row[o.column], y.row[o.column]);
      if (c) return o.descending && !blank(x.row[o.column]) && !blank(y.row[o.column]) ? -c : c;
    }
    return x.at - y.at;
  }).map((s) => s.row);
  const out = [];
  let key = null; let n = 0; let dense = 0; let tieStart = 0; let prev = null; let tie = -1;
  for (const row of sorted) {
    const k = keyOf(row);
    if (k !== key) { key = k; n = 0; dense = 0; prev = null; }
    n += 1;
    const same = prev && order.every((o) => compare(row[o.column], prev[o.column]) === 0);
    if (!same) { dense += 1; tieStart = n; tie += 1; }
    out.push({ row, group: k, tie, position: method === 'row' ? n : method === 'dense' ? dense : tieStart, tied: false });
    prev = row;
  }
  // Marca os empates de verdade (dois ou mais com o mesmo valor no mesmo grupo).
  const counts = new Map();
  for (const r of out) counts.set(r.tie, (counts.get(r.tie) || 0) + 1);
  for (const r of out) r.tied = counts.get(r.tie) > 1;
  return out;
}

const METHOD_TEXT = {
  row: 'cada linha tem uma posição só: no empate, quem chegou antes fica na frente',
  rank: 'empatados dividem a posição, e a seguinte é pulada (1, 1, 3)',
  dense: 'empatados dividem a posição, sem pular a seguinte (1, 1, 2)',
};

async function rank(n, cfg, { mini, arrow }) {
  const order = (cfg.order_by || []).filter((o) => o.column);
  const groups = cfg.group_by || [];
  const method = cfg.method || 'rank';
  const real = await inputRows(n, 'in', 60);
  const live = Boolean(real?.length) && order.every((o) => o.column in real[0]) && groups.every((g) => g in real[0]);
  const rows = live ? real : RANK_EXAMPLE;
  const useOrder = live ? order : order.length ? order.map((o) => ({ ...o, column: 'vendas' })).slice(0, 1) : [{ column: 'vendas', descending: true }];
  const useGroups = live ? groups : groups.length ? ['regiao'] : [];
  const label = live ? null : 'vendedor';
  const name = (cfg.column || '').trim() || 'posicao';
  const ranked = rankRows(rows, { order: useOrder, groups: useGroups, method });
  const top = cfg.keep_top ? Math.max(1, Number(cfg.top) || 1) : null;

  const firstCol = live ? Object.keys(rows[0]).find((c) => !useGroups.includes(c) && !useOrder.some((o) => o.column === c)) : label;
  // No máximo três colunas mais a posição: o painel é estreito.
  const cols = [...useGroups, ...(firstCol && useGroups.length + useOrder.length < 3 ? [firstCol] : []), ...useOrder.map((o) => o.column)].slice(0, 3);
  const before = mini('Como chegam', cols.map((c) => ({ text: c })), rows.slice(0, 7).map((r) => cols.map((c) => ({ text: show(r[c]) }))));
  let tone = 0;
  const toneOf = new Map();
  const shown = [];
  let lastGroup = null; let perGroup = 0;
  for (const r of ranked) {
    if (r.group !== lastGroup) { lastGroup = r.group; perGroup = 0; }
    perGroup += 1;
    if (perGroup <= (top ? top + 2 : 6) && shown.length < 10) shown.push(r);
  }
  const after = mini('Depois: em ordem, com a posição', [...cols.map((c) => ({ text: c })), { text: name, kind: 'to' }], shown.map((r) => {
    const out = top && r.position > top;
    if (r.tied && !toneOf.has(r.tie)) toneOf.set(r.tie, `g${tone++ % 3}`);
    const kind = out ? 'alone' : r.tied ? toneOf.get(r.tie) : null;
    return [...cols.map((c) => ({ text: show(r.row[c]), kind: out ? 'alone' : null })),
      { text: out ? `${r.position}º · fora` : `${r.position}º`, kind: kind || 'to', title: r.tied ? 'Empate' : null }];
  }));
  const tied = ranked.find((r) => r.tied);
  const tiedNames = tied && firstCol ? ranked.filter((r) => r.tie === tied.tie).map((r) => show(r.row[firstCol])).slice(0, 3) : [];
  const example = tied
    ? ` Aqui, ${tiedNames.length ? tiedNames.join(' e ') : 'duas linhas'} empatam em ${show(tied.row[useOrder[0].column])}: ${
      method === 'row' ? 'cada um ganha uma posição, pela ordem de chegada' : `os dois ficam em ${tied.position}º`}.`
    : '';
  const caption = `${useGroups.length ? `Em cada ${useGroups.join(' + ')}, a contagem recomeça do 1. ` : ''}Quando empata, ${METHOD_TEXT[method]}.${example}${
    top ? ` Só ficam as posições até ${top}${method === 'row' ? '' : ': com empate, podem vir mais linhas'}.` : ''} Vazios ficam por último.`;
  return {
    body: [before, arrow(useOrder.map((o) => `${o.column} ${o.descending ? '↓' : '↑'}`).join(', ')), after],
    caption,
    sample: live,
  };
}

// ------------------------------------------------------------------ Append Fields

export const APPEND_WARN = 100_000;
export const APPEND_HEAVY = 1_000_000;
export const APPEND_MAX = 10_000_000;

/** Conta e nível de aviso do Append Fields com o que chegou nas entradas. */
export function appendEstimate(n) {
  const t = inputCount(n, 'T');
  const s = inputCount(n, 'S');
  if (!t || !s) return null;
  const rows = t.rows * s.rows;
  const level = rows > APPEND_MAX ? 'error' : rows > APPEND_HEAVY ? 'heavy' : rows > APPEND_WARN ? 'warn' : 'ok';
  return { t, s, rows, cols: t.cols !== null && s.cols !== null ? t.cols + s.cols : null, level };
}

const APPEND_T = [{ produto: 'Café', preco: 10 }, { produto: 'Chá', preco: 8 }, { produto: 'Suco', preco: 12 }];
const APPEND_S = [{ cenario: 'Base', fator: 1 }, { cenario: 'Alta', fator: 1.1 }];

async function append(n, cfg, { mini, arrow }) {
  const [realT, realS] = await Promise.all([inputRows(n, 'T', 3), inputRows(n, 'S', 3)]);
  const live = Boolean(realT?.length && realS?.length);
  const T = (live ? realT : APPEND_T).slice(0, 3);
  const S = (live ? realS : APPEND_S).slice(0, 2);
  const colsT = Object.keys(T[0]).slice(0, live ? 1 : 2); // painel estreito: com dados reais, uma coluna de cada lado
  const colsS = Object.keys(S[0]).slice(0, live ? 1 : 2);
  const prefix = cfg.prefix ?? 's_';
  const outS = colsS.map((c) => (colsT.includes(c) || Object.keys(T[0]).includes(c) ? `${prefix}${c}` : c));
  const tTable = mini('[T] Destino', colsT.map((c) => ({ text: c })), T.map((r, i) => colsT.map((c) => ({ text: show(r[c]), kind: `g${i % 3}`, link: `t${i}` }))));
  const sTable = mini('[S] Fonte', colsS.map((c) => ({ text: c })), S.map((r, j) => colsS.map((c) => ({ text: show(r[c]), kind: 'from', link: `s${j}` }))));
  const result = mini('Resultado: cada linha de [T] com cada linha de [S]', [...colsT.map((c) => ({ text: c })), ...outS.map((c) => ({ text: c, kind: 'to' }))],
    T.flatMap((r, i) => S.map((s, j) => [
      ...colsT.map((c) => ({ text: show(r[c]), kind: `g${i % 3}`, link: `t${i}` })),
      ...colsS.map((c) => ({ text: show(s[c]), kind: 'from', link: `s${j}` })),
    ])));
  const est = appendEstimate(n);
  const count = est ? `${fmt.int(est.t.rows)} × ${fmt.int(est.s.rows)} = ${fmt.int(est.rows)} linhas` : `${T.length} × ${S.length} = ${T.length * S.length} linhas`;
  const clash = outS.find((c, k) => c !== colsS[k]);
  return {
    body: [h('div', { class: 'x-pair' }, tTable, sTable), arrow(count), result],
    caption: `Não precisa de coluna em comum: cada linha de [T] se repete uma vez para cada linha de [S] (${count}). Serve para aplicar parâmetros ou cenários a todas as linhas. Para juntar por uma coluna em comum, use o Join.${
      clash ? ` Coluna com o mesmo nome nos dois lados ganha o prefixo: ${clash}.` : ''} Passe o mouse numa linha para ver de onde veio.`,
    sample: live,
  };
}

export const WINDOW_EXPLAINERS = { rank, append_fields: append };
