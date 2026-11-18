// Tabela de resultados (spec 041, RF-4130..4132): resumo das colunas que liga e desliga e largura das colunas.

import { button, h, persist, storage } from './dom.js';
import { emit, on } from './store.js';

const SUMMARY_KEY = 'prodata.results.summary'; // true, false ou null (automático pela altura do painel)
const WIDTHS_KEY = 'prodata.results.widths';
const LOW_PANEL = 260;
const MAX_KEYS = 200;
const MIN_W = 60;
const MAX_W = 900;

let summaryPref = storage(SUMMARY_KEY, null);
let lowPanel = false;

/** O resumo aparece? A escolha da pessoa vence; sem escolha, some com o painel baixo. */
export const summaryShown = () => (summaryPref === null ? !lowPanel : summaryPref === true);

export function setSummary(show) {
  summaryPref = !!show;
  persist(SUMMARY_KEY, summaryPref);
  emit('table-summary');
}

/** Botão da barra da aba Resultado. */
export function summaryButton() {
  const btn = button({ icon: 'chart', label: 'Resumo', size: 'sm', variant: 'ghost', onClick: () => setSummary(!summaryShown()) });
  const paint = () => {
    btn.classList.toggle('active', summaryShown());
    btn.setAttribute('aria-pressed', String(summaryShown()));
    btn.title = summaryShown()
      ? 'Esconder o resumo das colunas (minigráfico, preenchimento e total)'
      : 'Mostrar o resumo das colunas (minigráfico, preenchimento e total)';
  };
  paint();
  on('table-summary', paint);
  return btn;
}

/** Aplica a escolha no corpo da aba e acompanha a altura do painel. */
export function watchSummary(body) {
  const apply = () => body.classList.toggle('no-summary', !summaryShown());
  apply();
  on('table-summary', apply);
  new ResizeObserver(() => {
    const low = body.clientHeight > 0 && body.clientHeight < LOW_PANEL;
    if (low === lowPanel) return;
    lowPanel = low;
    apply();
    if (summaryPref === null) emit('table-summary');
  }).observe(body);
}

// ---------------------------------------------------------------- larguras

function allWidths() {
  const all = storage(WIDTHS_KEY, {});
  return all && typeof all === 'object' ? all : {};
}

function saveWidth(key, column, px) {
  const all = allWidths();
  const entry = { ...(all[key] || {}) };
  if (px === null) delete entry[column];
  else entry[column] = Math.round(px);
  delete all[key];
  if (Object.keys(entry).length) all[key] = entry; // o mais recente fica no fim; os antigos saem primeiro
  const keys = Object.keys(all);
  for (const old of keys.slice(0, Math.max(0, keys.length - MAX_KEYS))) delete all[old];
  persist(WIDTHS_KEY, all);
}

export function clearWidths(key) {
  const all = allWidths();
  delete all[key];
  persist(WIDTHS_KEY, all);
}

function setColumnWidth(table, index, px) {
  const cells = [table.tHead?.rows[0]?.cells[index], ...[...(table.tBodies[0]?.rows || [])].map((tr) => tr.cells[index])];
  for (const cell of cells) {
    if (!cell || cell.colSpan > 1) continue;
    const v = px === null ? '' : `${px}px`;
    cell.style.width = v;
    cell.style.minWidth = v;
    cell.style.maxWidth = v;
  }
}

/** Largura que cabe o conteúdo visível da coluna. */
function fitWidth(table, index) {
  setColumnWidth(table, index, null);
  let widest = MIN_W;
  for (const cell of [table.tHead?.rows[0]?.cells[index], ...[...(table.tBodies[0]?.rows || [])].map((tr) => tr.cells[index])]) {
    if (!cell || cell.colSpan > 1) continue;
    const saved = cell.style.maxWidth;
    cell.style.maxWidth = 'none';
    widest = Math.max(widest, cell.scrollWidth + 2);
    cell.style.maxWidth = saved;
  }
  return Math.min(MAX_W, widest);
}

/**
 * Bordas arrastáveis no cabeçalho. `key` identifica a saída (fluxo, caixa e porta); `names[i]` é a coluna do índice i.
 * Dois cliques na borda ajustam ao conteúdo visível.
 */
export function enableColumnResize(table, key, names, firstCol = 1) {
  const saved = allWidths()[key] || {};
  const head = table.tHead?.rows[0];
  if (!head) return;
  [...head.cells].forEach((th, i) => {
    if (i < firstCol) return;
    const name = names[i];
    if (saved[name]) setColumnWidth(table, i, saved[name]);
    const grip = h('span', { class: 'col-resize', title: 'Arraste para mudar a largura · dois cliques ajustam ao conteúdo', 'aria-hidden': 'true' });
    grip.addEventListener('click', (e) => e.stopPropagation());
    grip.addEventListener('dblclick', (e) => {
      e.stopPropagation();
      const px = fitWidth(table, i);
      setColumnWidth(table, i, px);
      saveWidth(key, name, px);
    });
    grip.addEventListener('pointerdown', (e) => {
      e.preventDefault();
      e.stopPropagation();
      const start = e.clientX;
      const from = th.getBoundingClientRect().width;
      grip.setPointerCapture(e.pointerId);
      table.classList.add('resizing');
      const move = (ev) => setColumnWidth(table, i, Math.max(MIN_W, Math.min(MAX_W, from + ev.clientX - start)));
      const up = (ev) => {
        grip.removeEventListener('pointermove', move);
        table.classList.remove('resizing');
        if (Math.abs(ev.clientX - start) > 2) saveWidth(key, name, Math.max(MIN_W, Math.min(MAX_W, from + ev.clientX - start)));
      };
      grip.addEventListener('pointermove', move);
      grip.addEventListener('pointerup', up, { once: true });
    });
    th.append(grip);
  });
}
