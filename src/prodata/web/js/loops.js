// Laço no canvas (spec 041, RF-4160..4168): os pares Início/Fim, o corpo entre eles, as variáveis para o
// autocompletar, a moldura do laço e o botão Parar enquanto as voltas rodam. Espelho de prodata/engine/loops.py.

import { h } from './dom.js';
import { icon } from './icons.js';
import { descendants, nodeResult, store, upstreamColumns } from './store.js';

export const LOOP_START = 'flow.loop_start';
export const LOOP_END = 'flow.loop_end';

function ancestors(id) {
  const out = new Set();
  const stack = [id];
  while (stack.length) {
    const current = stack.pop();
    for (const e of store.workflow.edges) {
      if (e.target === current && !out.has(e.source)) {
        out.add(e.source);
        stack.push(e.source);
      }
    }
  }
  return out;
}

/** Os laços do fluxo: [{ start, end, body: Set }]. */
export function loopsOf() {
  const wf = store.workflow;
  if (!wf) return [];
  const starts = new Set(wf.nodes.filter((n) => n.type === LOOP_START).map((n) => n.id));
  const out = [];
  for (const e of wf.nodes.filter((n) => n.type === LOOP_END)) {
    const s = e.config?.start;
    if (!starts.has(s)) continue;
    const up = ancestors(e.id);
    if (!up.has(s)) continue;
    const body = new Set([...descendants(s)].filter((id) => up.has(id) && id !== e.id));
    out.push({ start: s, end: e.id, body });
  }
  return out;
}

/** A caixa está dentro de algum laço (ou é o Fim dele)? */
export const inLoop = (id) => Boolean(id) && loopsOf().some((l) => l.body.has(id) || l.end === id);

/** Variáveis do laço como constantes, para o autocompletar e o destaque das fórmulas da caixa selecionada. */
export function loopVariables(id = store.selection?.nodeId) {
  const loop = id && loopsOf().find((l) => l.body.has(id) || l.end === id);
  if (!loop) return [];
  // O tipo de [#valor] segue o Início: faixa de números, de datas, ou a coluna escolhida.
  const cfg = store.workflow.nodes.find((n) => n.id === loop.start)?.config || {};
  const colType = (upstreamColumns(loop.start) || []).find((c) => c.name === cfg.column)?.type || '';
  const kind = cfg.mode === 'while' ? 'number' : cfg.mode === 'range' ? (!cfg.unit || cfg.unit === 'number' ? 'number' : 'date')
    : cfg.values?.trim() ? 'text' : /Int|Float|Decimal/.test(colType) ? 'number' : /Date/.test(colType) ? 'date' : 'text';
  const sample = { number: '1', date: '2026-01-01', text: 'a' }[kind];
  return [
    { name: 'valor', type: kind, value: 'o valor da volta', sample, scope: 'loop', description: 'O valor, número ou data de cada volta.' },
    { name: 'volta', type: 'number', value: '1, 2, 3…', sample: '1', scope: 'loop', description: 'O número da volta.' },
    { name: 'total', type: 'number', value: 'quantas voltas', sample: '1', scope: 'loop', description: 'Quantas voltas o laço tem (0 no modo Enquanto).' },
  ];
}

// ---------------------------------------------------------------- moldura no canvas

const MODE_TEXT = (cfg) => (cfg.mode === 'range' ? `de ${cfg.start ?? 1} até ${cfg.end ?? 10}`
  : cfg.mode === 'while' ? 'enquanto a condição valer' : cfg.column ? `para cada ${cfg.column}` : 'para cada valor');

/** Retângulos das molduras (coordenadas do canvas), com o texto. `rectOf(node)` vem do canvas. */
export function loopFrames(rectOf) {
  const byId = new Map(store.workflow.nodes.map((n) => [n.id, n]));
  return loopsOf().flatMap((l) => {
    const rects = [l.start, ...l.body, l.end].map((id) => byId.get(id)).filter(Boolean).map(rectOf);
    // Tudo no mesmo cartão de etapa recolhida: sem moldura (spec 045).
    if (rects.length && rects.every((r) => r.card && r.card === rects[0].card)) return [];
    const pad = 16;
    const x1 = Math.min(...rects.map((r) => r.x1)) - pad;
    const y1 = Math.min(...rects.map((r) => r.y1)) - pad - 20;
    const x2 = Math.max(...rects.map((r) => r.x2)) + pad;
    const y2 = Math.max(...rects.map((r) => r.y2)) + pad;
    const res = nodeResult(l.end);
    const turns = res?.extra?.loop?.turns;
    const text = `Laço · ${MODE_TEXT(byId.get(l.start).config || {})}${turns ? ` · ${turns} ${turns === 1 ? 'volta' : 'voltas'}` : ''}`;
    return { id: l.end, x1, y1, x2, y2, text, error: res?.status === 'error' };
  });
}

export function frameEl(f) {
  return h('div', {
    class: ['loop-frame', f.error && 'err'], dataset: { loop: f.id },
    style: { left: `${f.x1}px`, top: `${f.y1}px`, width: `${f.x2 - f.x1}px`, height: `${f.y2 - f.y1}px` },
  }, h('span', { class: 'loop-frame-label' }, icon('repeat', 12), f.text));
}


// ---------------------------------------------------------------- erro de desenho, antes de executar (RF-4167)

const MAX_DEPTH = 3;
let problemsCache = { key: null, map: new Map() };

/** Caixa → o que está errado no desenho do laço. As mesmas regras de prodata/engine/loops.py. */
export function loopProblems() {
  const wf = store.workflow;
  if (!wf) return new Map();
  const key = JSON.stringify([wf.edges.map((e) => [e.source, e.target]), wf.nodes.filter((n) => n.type === LOOP_START || n.type === LOOP_END).map((n) => [n.id, n.config?.start])]);
  if (key === problemsCache.key) return problemsCache.map;
  const out = new Map();
  const types = new Map(wf.nodes.map((n) => [n.id, n.type]));
  const paired = new Set();
  const loops = [];
  for (const e of wf.nodes.filter((n) => n.type === LOOP_END)) {
    const s = e.config?.start;
    if (types.get(s) !== LOOP_START) { out.set(e.id, 'Este Fim do loop não tem o Início: crie o laço pela paleta (Loop) ou apague esta caixa.'); continue; }
    const up = ancestors(e.id);
    if (!up.has(s)) { out.set(e.id, 'Ligue o Início do loop até este Fim, passando pelas caixas que vão repetir.'); continue; }
    if (paired.has(s)) { out.set(e.id, 'Este Início do loop já tem um Fim: cada laço tem um Início e um Fim.'); continue; }
    paired.add(s);
    loops.push({ start: s, end: e.id, body: new Set([...descendants(s)].filter((id) => up.has(id) && id !== e.id)) });
  }
  for (const s of wf.nodes.filter((n) => n.type === LOOP_START)) {
    if (!paired.has(s.id)) out.set(s.id, 'Falta o Fim do loop: ligue as caixas que vão repetir até um Fim do loop.');
  }
  for (const l of loops) {
    for (const edge of wf.edges) {
      const escapes = !l.body.has(edge.target) && edge.target !== l.end;
      if (l.body.has(edge.source) && escapes) out.set(edge.source, 'Esta caixa está dentro do laço e manda dados para fora sem passar pelo Fim do loop.');
      if (edge.source === l.start && escapes) out.set(l.start, 'O Início do loop só pode ligar nas caixas do laço.');
    }
  }
  const within = (a, b) => [a.start, a.end, ...a.body].every((id) => b.body.has(id));
  for (const a of loops) {
    for (const b of loops) {
      if (a === b) continue;
      const touches = [a.start, a.end, ...a.body].some((id) => b.body.has(id));
      if (touches && !within(a, b) && !within(b, a) && !out.has(a.end)) out.set(a.end, 'Dois laços se cruzam: um laço de dentro precisa ficar inteiro entre o Início e o Fim do outro.');
    }
    const depth = 1 + loops.filter((b) => b !== a && within(a, b)).length;
    if (depth > MAX_DEPTH) out.set(a.end, `Laço dentro de laço vai até ${MAX_DEPTH} níveis.`);
  }
  problemsCache = { key, map: out };
  return out;
}
