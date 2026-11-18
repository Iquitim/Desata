// Fios no canvas (spec 041, RF-4112, RF-4113): organizados (padrão) ou curvos, a escolha da pessoa neste computador.
// Calcula as rotas de todos os fios de uma vez e guarda; durante o arrasto, fio cuja ponta mudou fica curvo
// (provisório) e se acomoda ao soltar.

import { CARD_H, CARD_W, edgeEnds, hiddenNodes } from './canvas_collapse.js';
import { nodeHeight, nodeWidth } from './canvas_geometry.js';
import { routeWire, separateLanes } from './canvas_route.js';
import { state } from './canvas_state.js';
import { persist, storage } from './dom.js';
import { emit, store } from './store.js';

const KEY = 'prodata.view.wires';
const TITLE_H = 28; // a barra de título da etapa também é obstáculo

let mode = storage(KEY, 'routed') === 'curved' ? 'curved' : 'routed';
let cache = { key: null, routes: new Map(), ends: new Map() };

export const wireMode = () => mode;

/** Esquece as rotas guardadas (as próximas são recalculadas). */
export function resetWires() {
  cache = { key: null, routes: new Map(), ends: new Map() };
}

export function setWireMode(next) {
  mode = next === 'curved' ? 'curved' : 'routed';
  persist(KEY, mode);
  emit('wires');
}

const rectOf = (n) => ({ x1: n.x, y1: n.y, x2: n.x + nodeWidth(n), y2: n.y + nodeHeight(n) });
const endKey = ({ a, b }) => `${Math.round(a.x)},${Math.round(a.y)}>${Math.round(b.x)},${Math.round(b.y)}`;

/**
 * Rotas dos fios: Map id → pontos. Vazio no modo curvo. No arrasto (`state.moving`), devolve só as rotas
 * cujas pontas não mudaram; as outras ficam de fora e o fio é desenhado curvo até soltar.
 */
export function wireRoutes() {
  const wf = store.workflow;
  if (mode !== 'routed' || !wf) return new Map();
  const byId = new Map(wf.nodes.map((n) => [n.id, n]));
  const hidden = hiddenNodes();
  const obstacles = [];
  for (const n of wf.nodes) if (!hidden.has(n.id)) obstacles.push({ owner: n.id, ...rectOf(n) });
  for (const c of wf.containers || []) {
    if (c.collapsed) obstacles.push({ owner: `card:${c.id}`, x1: c.x, y1: c.y, x2: c.x + CARD_W, y2: c.y + CARD_H });
    else { // o título ocupa só o texto, à esquerda, e o interruptor, à direita: o resto da faixa é passagem
      obstacles.push({ owner: `title:${c.id}`, x1: c.x, y1: c.y, x2: c.x + Math.min(c.width, 40 + (c.title || '').length * 7.5), y2: c.y + TITLE_H });
      obstacles.push({ owner: `switch:${c.id}`, x1: c.x + c.width - 46, y1: c.y, x2: c.x + c.width, y2: c.y + TITLE_H });
    }
  }
  const ends = new Map();
  for (const e of wf.edges) {
    const found = edgeEnds(e, byId, hidden);
    if (found) ends.set(e.id, found);
  }
  const key = JSON.stringify([obstacles.map((o) => [o.x1, o.y1, o.x2, o.y2]), [...ends].map(([id, x]) => [id, endKey(x)])]);
  if (key === cache.key) return cache.routes;
  if (state.moving) {
    // provisório: o que não mudou continua organizado; o resto fica curvo até soltar
    const kept = new Map();
    for (const [id, x] of ends) if (cache.ends.get(id) === endKey(x) && cache.routes.has(id)) kept.set(id, cache.routes.get(id));
    return kept;
  }
  const routes = [];
  for (const e of wf.edges) {
    const found = ends.get(e.id);
    if (!found) continue;
    const s = hidden.get(e.source);
    const t = hidden.get(e.target);
    const own = new Set([s ? `card:${s.id}` : e.source, t ? `card:${t.id}` : e.target]);
    const points = routeWire(found.a, found.b, obstacles.filter((o) => !own.has(o.owner)), obstacles.filter((o) => own.has(o.owner)));
    if (points) routes.push({ id: e.id, group: `${e.source}:${e.sourceHandle}`, points });
  }
  separateLanes(routes, obstacles);
  cache = { key, routes: new Map(routes.map((r) => [r.id, r.points])), ends: new Map([...ends].map(([id, x]) => [id, endKey(x)])) };
  return cache.routes;
}
