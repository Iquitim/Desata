// Adicionar rápido: a lista de ferramentas ao puxar um fio para o vazio ou dar duplo clique.

import { addNode, connect, firstInput, spliceIntoEdge } from './actions.js';
import { NODE_MIN_H, NODE_W } from './canvas_geometry.js';
import { h } from './dom.js';
import { icon } from './icons.js';
import { countNext, suggestedNext } from './canvas_snap.js';
import { node, store, toolOf } from './store.js';

export function openQuickAdd(clientX, clientY, source) {
  const fromPort = source.nodeId
    ? toolOf(node(source.nodeId)).outputs.find((p) => p.id === source.port)
    : null;
  const kind = fromPort?.kind || 'data';
  const tools = Object.values(store.tools).filter((t) => !t.hidden && (!fromPort || firstInput(t.type, kind))
    && (!source.splice || (firstInput(t.type) && t.outputs.some((p) => p.kind !== 'model'))));

  const fromType = source.nodeId ? node(source.nodeId)?.type : null;
  // Próxima caixa sugerida (spec 046, RF-4646): o que mais veio depois desta ferramenta neste computador.
  const suggested = fromType ? suggestedNext(fromType, tools.map((t) => t.type)).map((type) => store.tools[type]) : [];

  const list = h('div', { class: 'quick-list', role: 'listbox' });
  const input = h('input', { class: 'input', placeholder: fromPort ? 'Conectar a…' : 'Adicionar ferramenta…', 'aria-label': 'Buscar ferramenta' });
  const panel = h('div', { class: 'quick-add', style: { left: `${clientX}px`, top: `${clientY}px` } }, input, list);
  let active = 0;
  let shown = [];

  const choose = (t) => {
    panel.remove();
    const at = source.to;
    const created = addNode(t.type, at.x, at.y - NODE_MIN_H / 2);
    if (created && source.nodeId && connect(source.nodeId, source.port, created.id, firstInput(t.type, kind).id)) countNext(fromType, t.type);
    if (created && source.splice) spliceIntoEdge(source.splice, created.id, { nodeWidth: NODE_W });
  };
  const item = (t, i) => h('button', {
    type: 'button', role: 'option', class: ['quick-item', i === active && 'active'], dataset: { category: t.category },
    onclick: () => choose(t),
  }, h('span', { class: 'tool-icon' }, icon(t.icon, 15)), h('span', {}, t.name));
  const draw = () => {
    const q = input.value.trim().toLowerCase();
    if (!q && suggested.length) {
      const rest = tools.filter((t) => !suggested.includes(t)).slice(0, Math.max(3, 8 - suggested.length));
      shown = [...suggested, ...rest];
      active = Math.min(active, shown.length - 1);
      list.replaceChildren(
        h('div', { class: 'quick-group' }, 'Sugeridas'), ...suggested.map((t, i) => item(t, i)),
        h('div', { class: 'quick-group' }, 'Outras'), ...rest.map((t, i) => item(t, i + suggested.length)));
      return;
    }
    shown = tools.filter((t) => !q || `${t.name} ${t.description}`.toLowerCase().includes(q)).slice(0, 8);
    active = Math.min(active, Math.max(0, shown.length - 1));
    list.replaceChildren(...shown.map((t, i) => item(t, i)));
  };
  input.addEventListener('input', () => { active = 0; draw(); });
  input.addEventListener('keydown', (ev) => {
    if (ev.key === 'ArrowDown') { active = Math.min(active + 1, shown.length - 1); draw(); ev.preventDefault(); }
    if (ev.key === 'ArrowUp') { active = Math.max(active - 1, 0); draw(); ev.preventDefault(); }
    if (ev.key === 'Enter' && shown[active]) choose(shown[active]);
    if (ev.key === 'Escape') panel.remove();
  });
  const outside = (ev) => {
    if (!panel.contains(ev.target)) {
      panel.remove();
      document.removeEventListener('pointerdown', outside, true);
    }
  };
  document.addEventListener('pointerdown', outside, true);
  document.body.append(panel);
  const r = panel.getBoundingClientRect();
  panel.style.left = `${Math.min(clientX, innerWidth - r.width - 8)}px`;
  panel.style.top = `${Math.min(clientY, innerHeight - 320)}px`;
  draw();
  input.focus();
}
