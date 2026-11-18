// Recolher (spec 041, RF-4101..4104): caixa compacta e etapa recolhida num cartão. É só desenho: a execução, o SQL e
// o cache não mudam. Os nós de uma etapa recolhida são os mesmos de sempre (centro dentro do retângulo da etapa).

import { nodesInside } from './actions.js';
import { NODE_W, portPoint } from './canvas_geometry.js';
import { fmt, h } from './dom.js';
import { icon } from './icons.js';
import { timingOn } from './node_timing.js';
import { sourceProblem } from './portable_state.js';
import { mutate, nodeResult, on, select, store, toolOf } from './store.js';

export const CARD_W = 260;
export const CARD_H = 92;
const MAX_ICONS = 11;

/** Nó escondido → a etapa recolhida que o guarda. */
export function hiddenNodes() {
  const out = new Map();
  for (const c of store.workflow?.containers || []) {
    if (!c.collapsed) continue;
    for (const n of nodesInside(c, NODE_W)) if (!out.has(n.id)) out.set(n.id, c);
  }
  return out;
}

/** As duas pontas do fio, já trocando o nó escondido pelo lado do cartão da etapa. Null: o fio fica dentro do cartão. */
export function edgeEnds(e, byId, hidden) {
  const s = byId.get(e.source);
  const t = byId.get(e.target);
  if (!s || !t) return null;
  const cs = hidden.get(s.id);
  const ct = hidden.get(t.id);
  if (cs && cs === ct) return null;
  const a = cs ? { x: cs.x + CARD_W, y: cs.y + CARD_H / 2 } : portPoint(s, e.sourceHandle, true);
  const b = ct ? { x: ct.x, y: ct.y + CARD_H / 2 } : portPoint(t, e.targetHandle, false);
  return { a, b, card: Boolean(cs || ct) };
}

// ---------------------------------------------------------------- ações (um passo de desfazer cada)

export function setNodesCollapsed(ids, collapsed) {
  const set = new Set(ids);
  mutate((wf) => { for (const n of wf.nodes) if (set.has(n.id)) n.collapsed = collapsed; });
}

export function setContainersCollapsed(ids, collapsed) {
  const set = new Set(ids);
  // Recolher vence a seleção: a caixa selecionada que vai sumir deixa de estar selecionada.
  if (collapsed) {
    const chosen = store.selection?.nodeId;
    const inside = chosen && (store.workflow.containers || []).some((c) => set.has(c.id) && nodesInside(c, NODE_W).some((n) => n.id === chosen));
    if (inside) select(null);
  }
  mutate((wf) => { for (const c of wf.containers || []) if (set.has(c.id)) c.collapsed = collapsed; });
}

export const allContainers = () => (store.workflow?.containers || []).map((c) => c.id);

/** Recolhe as caixas desativadas: ficam pequenas, sem sumir. */
export const collapseDisabled = () => setNodesCollapsed(store.workflow.nodes.filter((n) => n.disabled).map((n) => n.id), true);

/** A caixa escolhida (busca, erro, "Faltam neste computador", soltar dentro da etapa) nunca fica escondida. */
function revealSelected() {
  const id = store.selection?.nodeId;
  if (!id || (store.selection.nodeIds?.length || 0) > 1) return;
  const c = hiddenNodes().get(id);
  if (c) setContainersCollapsed([c.id], false);
}
on('selection', revealSelected);
on('workflow:changed', revealSelected);

// ---------------------------------------------------------------- cartão da etapa recolhida

/** Conteúdo do cartão: quantas caixas, os ícones e o estado do conjunto. */
export function containerCard(c) {
  const members = nodesInside(c, NODE_W);
  const errors = members.filter((n) => nodeResult(n.id)?.status === 'error').length;
  const missing = members.filter((n) => sourceProblem(n.id)?.state === 'missing').length;
  const sample = members.filter((n) => sourceProblem(n.id)?.state === 'sample').length;
  const ran = members.filter((n) => ['executed', 'cached'].includes(nodeResult(n.id)?.status)).length;
  const time = timingOn() ? members.reduce((s, n) => s + (nodeResult(n.id)?.status === 'executed' ? nodeResult(n.id).elapsed_ms || 0 : 0), 0) : 0;
  const state = errors ? ['err', `${errors} com erro`] : missing ? ['err', `${missing} sem fonte`] : sample ? ['warn', `${sample} com amostra`]
    : ran ? ['ok', 'executada'] : ['idle', 'não executada'];
  const icons = members.slice(0, MAX_ICONS).map((n) => h('span', {
    class: ['card-icon', nodeResult(n.id)?.status === 'error' && 'err'], dataset: { category: toolOf(n)?.category || 'prep' },
    title: n.label || toolOf(n)?.name || n.type,
  }, icon(toolOf(n)?.icon || 'info', 13)));
  return h('div', { class: 'container-card', title: 'Duplo clique para expandir a etapa' },
    h('div', { class: 'card-row' },
      h('span', { class: 'card-count' }, `${members.length} ${members.length === 1 ? 'caixa' : 'caixas'}`),
      h('span', { class: ['card-state', state[0]] }, state[1]),
      time ? h('span', { class: 'card-time', title: 'Soma do tempo das caixas da etapa na última execução' }, fmt.ms(time)) : null,
      h('button', {
        type: 'button', class: 'card-expand', title: 'Expandir a etapa',
        onclick: (ev) => { ev.stopPropagation(); setContainersCollapsed([c.id], false); },
      }, icon('maximize', 12))),
    h('div', { class: 'card-icons' }, icons, members.length > MAX_ICONS ? h('span', { class: 'card-more' }, `+${members.length - MAX_ICONS}`) : null));
}
