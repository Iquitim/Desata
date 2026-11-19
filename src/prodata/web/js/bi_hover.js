// Prévia do visual ao passar o mouse numa caixa de BI no Designer (spec 042, RF-4221).
// Usa o mesmo cartão do Dashboard, com o formato e a paleta da página; some ao tirar o mouse, arrastar ou clicar.

import { visualCard } from './dash_cards.js';
import { setPagePalette } from './dash_look.js';
import { h } from './dom.js';
import { icon } from './icons.js';
import { liveWidgets, on, store } from './store.js';

const BI_TYPES = new Set(['bi.chart', 'bi.kpi_card', 'bi.venn', 'bi.table']);
const DELAY = 500;
const W = 380;
const H = 240;

let timer = null;
let card = null;
let current = null;
let muted = []; // dicas nativas (title) da caixa, guardadas enquanto a prévia está aberta

function hide() {
  clearTimeout(timer);
  timer = null;
  current = null;
  card?.remove();
  card = null;
  for (const [el, text] of muted) el.setAttribute('title', text);
  muted = [];
}

function content(node) {
  const w = liveWidgets().find((x) => x.node_id === node.id);
  if (!w) {
    return h('div', { class: 'bi-hover-empty' }, icon('play', 16),
      h('span', {}, store.running ? 'Executando…' : 'Execute para ver a prévia'));
  }
  const dash = store.workflow.dashboard;
  setPagePalette(dash?.page?.palette, dash?.page?.personal_colors);
  const item = dash?.items?.find((i) => i.kind === 'visual' && i.node_id === node.id);
  const f = { ...(item?.format || {}), animate: false };
  // O Venn precisa de altura para os círculos e os números não se sobreporem (spec 042, RF-4254).
  const el = visualCard(w, { width: W, height: w.widget_type === 'venn' ? 330 : H - 70, fmt: f, compact: true });
  return h('div', {}, el,
    store.pending.has(node.id) ? h('p', { class: 'bi-hover-note' }, icon('clock', 12), ' Prévia da última execução: a caixa mudou desde então.') : null);
}

function show(nodeEl, node) {
  card?.remove();
  // A dica nativa da caixa apareceria por cima da prévia: sai enquanto ela está aberta.
  muted = [nodeEl, ...nodeEl.querySelectorAll('[title]')].filter((el) => el.hasAttribute('title')).map((el) => [el, el.getAttribute('title')]);
  for (const [el] of muted) el.removeAttribute('title');
  card = h('div', { class: 'bi-hover', role: 'tooltip', style: { width: `${W}px` } }, content(node));
  document.body.append(card);
  const r = nodeEl.getBoundingClientRect();
  const right = r.right + 12 + W <= window.innerWidth - 8;
  const left = right ? r.right + 12 : Math.max(8, r.left - 12 - W);
  const top = Math.max(8, Math.min(r.top, window.innerHeight - card.offsetHeight - 8));
  card.style.left = `${left}px`;
  card.style.top = `${top}px`;
}

/** Liga a prévia no canvas (chamado uma vez, pelo initCanvas). */
export function initBiHover(root) {
  root.addEventListener('pointerover', (e) => {
    if (e.buttons) return;
    const nodeEl = e.target.closest?.('.node[data-id]');
    const id = nodeEl?.dataset.id;
    if (!id || id === current) return;
    const node = store.workflow?.nodes.find((n) => n.id === id);
    hide();
    if (!node || !BI_TYPES.has(node.type)) return;
    current = id;
    timer = setTimeout(() => { if (current === id && nodeEl.isConnected) show(nodeEl, node); }, DELAY);
  });
  root.addEventListener('pointerout', (e) => {
    const from = e.target.closest?.('.node[data-id]');
    if (from && !from.contains(e.relatedTarget)) hide();
  });
  root.addEventListener('pointerdown', hide, true);
  root.addEventListener('wheel', hide, { passive: true });
  on('workflow:loaded', hide);
}
