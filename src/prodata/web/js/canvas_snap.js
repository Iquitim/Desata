// Fio inteligente (spec 046, RF-4641..4646): para onde vai o fio que está sendo puxado e o que acontece ao soltar.
//
// Três zonas, medidas em pixels de TELA (não encolhem com o zoom):
// - perto de uma entrada compatível (ímã de 28 px) ou sobre a caixa: liga;
// - numa faixa de 60 px em volta das caixas: neutro, soltar não faz nada (a pessoa provavelmente errou a caixa);
// - longe de tudo: soltar abre a lista de ferramentas, com a próxima caixa sugerida no topo.

import { connect, connectionError } from './actions.js';
import { hiddenNodes } from './canvas_collapse.js';
import { nodeHeight, nodeWidth, portPoint } from './canvas_geometry.js';
import { els, toWorld, view } from './canvas_state.js';
import { h, persist, storage } from './dom.js';
import { icon } from './icons.js';
import { node, store, toolOf, visibleInputs } from './store.js';

export const MAGNET_PX = 28;
export const NEUTRAL_PX = 60;

const occupiedEdge = (nodeId, portId) => store.workflow.edges.find((e) => e.target === nodeId && e.targetHandle === portId) || null;
const nodeName = (n) => n.label || toolOf(n)?.name || n.type;

/** Para onde o fio vai se for solto agora. */
export function wireTarget(g, clientX, clientY) {
  const world = toWorld(clientX, clientY);
  const hidden = hiddenNodes();
  let best = null;
  let inside = null;
  let near = false;
  for (const n of store.workflow.nodes) {
    if (n.id === g.nodeId || hidden.has(n.id)) continue;
    const w = nodeWidth(n);
    const ht = nodeHeight(n);
    const dx = Math.max(n.x - world.x, 0, world.x - (n.x + w));
    const dy = Math.max(n.y - world.y, 0, world.y - (n.y + ht));
    const gap = Math.hypot(dx, dy) * view.zoom;
    if (gap === 0) inside = n;
    else if (gap <= NEUTRAL_PX) near = true;
    if (gap > MAGNET_PX + 20) continue;
    for (const p of visibleInputs(n)) {
      if (connectionError(g.nodeId, g.port, n.id, p.id)) continue;
      const pt = portPoint(n, p.id, false);
      const d = Math.hypot(pt.x - world.x, pt.y - world.y) * view.zoom;
      if (d <= MAGNET_PX && (!best || d < best.d)) best = { n, p, d, pt };
    }
  }
  if (best) return portTarget(best.n, best.p);
  if (inside) {
    const all = visibleInputs(inside);
    const ok = all.filter((p) => !connectionError(g.nodeId, g.port, inside.id, p.id));
    if (!ok.length) {
      const reason = all.length ? connectionError(g.nodeId, g.port, inside.id, all[0].id) : 'Esta caixa não tem entrada.';
      return { kind: 'invalid', nodeId: inside.id, reason };
    }
    const free = ok.filter((p) => !occupiedEdge(inside.id, p.id));
    if (ok.length === 1) return portTarget(inside, ok[0]);
    if (free.length === 1) return portTarget(inside, free[0]);
    return { kind: 'node', nodeId: inside.id, candidates: free.length ? free : ok };
  }
  return near ? { kind: 'neutral' } : { kind: 'empty' };
}

function portTarget(n, p) {
  const edge = occupiedEdge(n.id, p.id);
  return { kind: 'port', nodeId: n.id, port: p.id, point: portPoint(n, p.id, false), replaces: edge?.id || null };
}

// ---------------------------------------------------------------- durante o arrasto

let tip = null;

/** Começo do arrasto: acende as entradas compatíveis e esmaece as demais (RF-4643). */
export function startWiring(g) {
  els.viewport.classList.add('wiring');
  for (const el of els.nodes.querySelectorAll('.port.in')) {
    const ok = !connectionError(g.nodeId, g.port, el.dataset.node, el.dataset.port);
    el.classList.toggle('wire-ok', ok);
    el.classList.toggle('wire-no', !ok);
  }
}

/** A cada movimento: ponta do fio, entrada ou caixa acesa, fio antigo tracejado e etiqueta junto ao cursor. */
export function showWireTarget(g, t, clientX, clientY) {
  clearMarks();
  if (t.kind === 'port') {
    els.nodes.querySelector(`.port.in[data-node="${CSS.escape(t.nodeId)}"][data-port="${CSS.escape(t.port)}"]`)?.classList.add('can-drop');
    if (t.replaces) els.svg.querySelector(`g.edge[data-edge="${CSS.escape(t.replaces)}"]`)?.classList.add('will-replace');
  }
  if (t.kind === 'node' || t.kind === 'port') els.nodes.querySelector(`.node[data-id="${CSS.escape(t.nodeId)}"]`)?.classList.add('drop-node');
  if (t.kind === 'invalid') els.nodes.querySelector(`.node[data-id="${CSS.escape(t.nodeId)}"]`)?.classList.add('drop-invalid');
  const text = tipText(t);
  if (!text) { tip?.remove(); tip = null; return; }
  if (!tip) {
    tip = h('div', { class: 'wire-tip', role: 'status' });
    els.viewport.append(tip);
  }
  const r = els.viewport.getBoundingClientRect();
  tip.className = `wire-tip wire-tip-${t.kind}`;
  tip.replaceChildren(t.kind === 'empty' ? icon('plus', 12) : t.kind === 'invalid' ? icon('alert', 12) : icon('link', 12), h('span', {}, text));
  tip.style.left = `${clientX - r.left + 14}px`;
  tip.style.top = `${clientY - r.top + 16}px`;
}

function tipText(t) {
  if (t.kind === 'port') {
    const n = node(t.nodeId);
    const inputs = visibleInputs(n);
    const port = inputs.find((p) => p.id === t.port);
    const which = inputs.length > 1 && port ? ` · entrada ${port.label}` : '';
    return `${t.replaces ? 'Trocar a ligação de' : 'Ligar em'} ${nodeName(n)}${which}`;
  }
  if (t.kind === 'node') return `Ligar em ${nodeName(node(t.nodeId))}: escolher a entrada`;
  if (t.kind === 'invalid') return t.reason;
  if (t.kind === 'empty') return 'Soltar para adicionar uma caixa';
  return '';
}

function clearMarks() {
  els.nodes.querySelectorAll('.port.in.can-drop, .port.in.cannot-drop').forEach((p) => p.classList.remove('can-drop', 'cannot-drop'));
  els.nodes.querySelectorAll('.node.drop-node, .node.drop-invalid').forEach((n) => n.classList.remove('drop-node', 'drop-invalid'));
  els.svg.querySelectorAll('g.edge.will-replace').forEach((e) => e.classList.remove('will-replace'));
}

/** Fim do arrasto (soltou ou cancelou): tudo volta ao normal. */
export function endWiring() {
  clearMarks();
  els.viewport.classList.remove('wiring');
  els.nodes.querySelectorAll('.port.in.wire-ok, .port.in.wire-no').forEach((p) => p.classList.remove('wire-ok', 'wire-no'));
  tip?.remove();
  tip = null;
}

// ---------------------------------------------------------------- ao soltar

/** Liga de verdade e conta a ligação para a sugestão da próxima caixa. */
export function wire(source, sourceHandle, target, targetHandle) {
  const ok = connect(source, sourceHandle, target, targetHandle);
  if (ok) countNext(node(source)?.type, node(target)?.type);
  return ok;
}

/** Várias entradas livres na caixa: um seletor pequeno ali mesmo, com a letra e o que cada uma recebe (RF-4642). */
export function choosePort(clientX, clientY, g, t) {
  const n = node(t.nodeId);
  document.querySelector('.port-chooser')?.remove();
  const panel = h('div', { class: 'port-chooser', role: 'menu', 'aria-label': `Entrada de ${nodeName(n)}` },
    h('div', { class: 'port-chooser-title' }, `Ligar em qual entrada de ${nodeName(n)}?`));
  const close = () => { panel.remove(); document.removeEventListener('pointerdown', outside, true); document.removeEventListener('keydown', onKey, true); };
  const outside = (ev) => { if (!panel.contains(ev.target)) close(); };
  const onKey = (ev) => {
    if (ev.key === 'Escape') { ev.preventDefault(); close(); }
    const items = [...panel.querySelectorAll('.port-choice')];
    const i = items.indexOf(document.activeElement);
    if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
      ev.preventDefault();
      items[(i + (ev.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length]?.focus();
    }
  };
  for (const p of t.candidates) {
    const taken = occupiedEdge(n.id, p.id);
    panel.append(h('button', {
      type: 'button', class: 'port-choice', role: 'menuitem',
      onclick: () => { close(); wire(g.nodeId, g.port, n.id, p.id); },
    }, h('span', { class: 'port-choice-letter' }, p.label), h('span', { class: 'port-choice-text' }, p.title || p.label,
      taken ? h('small', {}, 'troca a ligação que já existe') : null)));
  }
  document.body.append(panel);
  const r = panel.getBoundingClientRect();
  panel.style.left = `${Math.min(clientX + 8, innerWidth - r.width - 8)}px`;
  panel.style.top = `${Math.min(clientY + 8, innerHeight - r.height - 8)}px`;
  document.addEventListener('pointerdown', outside, true);
  document.addEventListener('keydown', onKey, true);
  panel.querySelector('.port-choice')?.focus();
}

// ---------------------------------------------------------------- próxima caixa sugerida (RF-4646)

const NEXT_KEY = 'prodata.nextTools';
const MAX_SUGGESTED = 5;
// Para quem começa: o que costuma vir depois de cada família, até haver contagem neste computador.
const STARTERS = {
  inout: ['prep.select', 'prep.filter', 'prep.cleanse', 'prep.formula', 'transform.join'],
  prep: ['prep.filter', 'prep.formula', 'transform.summarize', 'transform.join', 'io.output_data'],
  transform: ['prep.filter', 'prep.sort', 'prep.formula', 'bi.chart', 'io.output_data'],
  control: ['prep.filter', 'io.output_data', 'prep.select'],
  ml: ['ml.predictor', 'io.output_data'],
};
const OVERRIDES = { 'transform.summarize': ['prep.sort', 'bi.chart', 'prep.formula', 'io.output_data', 'transform.join'] };

function counts() {
  const raw = storage(NEXT_KEY, {});
  return raw && typeof raw === 'object' ? raw : {};
}

function countNext(from, to) {
  if (!from || !to) return;
  const all = counts();
  const row = all[from] && typeof all[from] === 'object' ? all[from] : {};
  row[to] = (Number(row[to]) || 0) + 1;
  all[from] = row;
  persist(NEXT_KEY, all); // só neste computador: nada sai daqui
}

/** As ferramentas sugeridas depois de ``fromType``, entre as que cabem na porta (``allowed``: tipos). */
export function suggestedNext(fromType, allowed) {
  const ok = new Set(allowed);
  const row = counts()[fromType] || {};
  const learned = Object.entries(row).filter(([t]) => ok.has(t)).sort((a, b) => b[1] - a[1]).map(([t]) => t);
  const category = store.tools[fromType]?.category;
  const starters = (OVERRIDES[fromType] || STARTERS[category] || []).filter((t) => ok.has(t) && t !== fromType);
  return [...new Set([...learned, ...starters])].slice(0, MAX_SUGGESTED);
}

export { countNext };
