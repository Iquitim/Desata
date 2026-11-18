// Tempo nas caixas (spec 041, RF-4150..4152): o tempo da última execução em cada caixa e a mais lenta.

import { emit, store, toolOf } from './store.js';
import { fmt, h, persist, storage } from './dom.js';

const KEY = 'prodata.view.timing';
let on = storage(KEY, false) === true;

export const timingOn = () => on;

export function setTiming(value) {
  on = !!value;
  persist(KEY, on);
  emit('timing');
}

/** Caixas executadas agora (fora do cache), com o tempo. */
function measured() {
  const results = store.execution?.node_results || {};
  return Object.entries(results)
    .filter(([, r]) => r.status === 'executed' && Number.isFinite(r.elapsed_ms))
    .map(([id, r]) => ({ id, ms: r.elapsed_ms }));
}

/** O que mostrar numa caixa: texto e peso (`top` entre as três mais lentas, `mid`, `low`), ou null. */
export function timingOf(id) {
  if (!on || store.running) return null;
  const res = store.execution?.node_results?.[id];
  if (!res) return null;
  if (res.status === 'cached') return { text: 'cache', level: 'cache', before: res.elapsed_ms > 0 ? fmt.ms(res.elapsed_ms) : null };
  if (res.status !== 'executed' || !Number.isFinite(res.elapsed_ms)) return null;
  const all = measured();
  const total = all.reduce((s, x) => s + x.ms, 0) || 1;
  const share = res.elapsed_ms / total;
  const top = all.filter((x) => x.ms / total > 0.05).sort((a, b) => b.ms - a.ms).slice(0, 3);
  const level = top.some((x) => x.id === id) ? 'top' : share > 0.02 ? 'mid' : 'low';
  return { text: fmt.ms(res.elapsed_ms), level, share };
}

/** Selo de tempo para a caixa (canvas). */
export function timingBadge(id) {
  const t = timingOf(id);
  if (!t) return null;
  const title = t.level === 'cache' ? `Veio do cache: não precisou executar${t.before ? `. Quando executou de verdade, levou ${t.before}` : ''}`
    : `Última execução: ${t.text} · ${fmt.number(t.share * 100, 0)}% do tempo do fluxo${t.level === 'top' ? ' · entre as mais lentas' : ''}`;
  return h('span', { class: ['node-time', t.level], title }, t.text);
}

/** "mais lenta: Join (4,8 s)" para a barra de status; o clique mostra a caixa. */
export function slowestNote(reveal) {
  if (!on || store.running) return null;
  const [first] = measured().sort((a, b) => b.ms - a.ms);
  const node = first && store.workflow.nodes.find((n) => n.id === first.id);
  if (!node) return null;
  const name = node.label || toolOf(node)?.name || node.type;
  return h('button', {
    type: 'button', class: 'status-slowest', title: 'Mostrar a caixa mais lenta',
    onclick: () => reveal?.(node.id),
  }, `· mais lenta: ${name} (${fmt.ms(first.ms)})`);
}
