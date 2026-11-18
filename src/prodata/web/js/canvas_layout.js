// Organizar o fluxo (spec 041, RF-4114): caixas em colunas da esquerda para a direita, seguindo os fios, com cada
// etapa junta. Primeiro arruma as caixas dentro de cada etapa; depois arruma as etapas (e as caixas soltas) entre si.
// Um passo só de desfazer.

import { nodesInside } from './actions.js';
import { NODE_W, nodeHeight } from './canvas_geometry.js';
import { mutate, store } from './store.js';

const GAP_X = 70;
const GAP_Y = 34;
const BLOCK_GAP_X = 80;
const BLOCK_GAP_Y = 50;
const PAD = 20;
const TITLE = 34;
const DESC = 26;
const snap = (v) => Math.round(v / 10) * 10;

/** Camadas por caminho mais longo e ordem por baricentro: `ids`, `links` [[de, para]], `size(id)` → {w, h}. */
function layered(ids, links, size, initialY, gapX = GAP_X, gapY = GAP_Y) {
  const set = new Set(ids);
  const inside = links.filter(([s, t]) => set.has(s) && set.has(t) && s !== t);
  const preds = new Map(ids.map((id) => [id, []]));
  for (const [s, t] of inside) preds.get(t).push(s);
  const layer = new Map();
  const visiting = new Set();
  const depth = (id) => {
    if (layer.has(id)) return layer.get(id);
    if (visiting.has(id)) return 0; // ciclo (não deveria haver): não trava
    visiting.add(id);
    const d = preds.get(id).length ? Math.max(...preds.get(id).map(depth)) + 1 : 0;
    visiting.delete(id);
    layer.set(id, d);
    return d;
  };
  ids.forEach(depth);
  const columns = [];
  for (const id of ids) (columns[layer.get(id)] ||= []).push(id);
  for (const col of columns) col?.sort((a, b) => initialY(a) - initialY(b));
  // duas passadas de baricentro: cada caixa perto da média das de antes
  for (let pass = 0; pass < 2; pass += 1) {
    const pos = new Map();
    columns.forEach((col) => col?.forEach((id, i) => pos.set(id, i)));
    for (const col of columns.slice(1)) {
      col?.sort((a, b) => {
        const bar = (id) => { const p = preds.get(id).filter((x) => pos.has(x)); return p.length ? p.reduce((s, x) => s + pos.get(x), 0) / p.length : pos.get(id); };
        return bar(a) - bar(b);
      });
      col?.forEach((id, i) => pos.set(id, i));
    }
  }
  const place = new Map();
  let x = 0;
  let height = 0;
  for (const col of columns) {
    if (!col) continue;
    const width = Math.max(...col.map((id) => size(id).w));
    let y = 0;
    for (const id of col) {
      place.set(id, { x, y });
      y += size(id).h + gapY;
    }
    height = Math.max(height, y - gapY);
    x += width + gapX;
  }
  return { place, width: Math.max(0, x - gapX), height };
}

/** Arruma o fluxo inteiro. Devolve quantas caixas mudaram de lugar. */
export function organizeFlow() {
  const wf = store.workflow;
  if (!wf?.nodes.length) return 0;
  const owner = new Map(); // caixa → etapa (a primeira que a contém)
  for (const c of wf.containers || []) for (const n of nodesInside(c, NODE_W)) if (!owner.has(n.id)) owner.set(n.id, c.id);
  const links = wf.edges.map((e) => [e.source, e.target]);
  const byId = new Map(wf.nodes.map((n) => [n.id, n]));
  const nodeSize = (id) => ({ w: NODE_W, h: nodeHeight(byId.get(id)) });

  // 1) dentro de cada etapa
  const blocks = new Map(); // id do bloco → { w, h, y0, inner?: Map, container? }
  for (const c of wf.containers || []) {
    const ids = wf.nodes.filter((n) => owner.get(n.id) === c.id).map((n) => n.id);
    if (!ids.length) continue;
    const inner = layered(ids, links, nodeSize, (id) => byId.get(id).y);
    const top = TITLE + (c.description ? DESC : 0);
    blocks.set(`c:${c.id}`, { container: c, inner: inner.place, w: inner.width + PAD * 2, h: inner.height + top + PAD, top, y0: c.y });
  }
  for (const n of wf.nodes) if (!owner.has(n.id)) blocks.set(`n:${n.id}`, { node: n, w: NODE_W, h: nodeHeight(n), y0: n.y });

  // 2) os blocos entre si
  const blockOf = (id) => (owner.has(id) ? `c:${owner.get(id)}` : `n:${id}`);
  const blockLinks = links.map(([s, t]) => [blockOf(s), blockOf(t)]).filter(([s, t]) => s !== t);
  const outer = layered([...blocks.keys()], blockLinks, (id) => ({ w: blocks.get(id).w, h: blocks.get(id).h }), (id) => blocks.get(id).y0, BLOCK_GAP_X, BLOCK_GAP_Y);
  const origin = {
    x: Math.min(...wf.nodes.map((n) => n.x), ...(wf.containers || []).map((c) => c.x)),
    y: Math.min(...wf.nodes.map((n) => n.y), ...(wf.containers || []).map((c) => c.y)),
  };
  let moved = 0;
  mutate((draft) => {
    const nodes = new Map(draft.nodes.map((n) => [n.id, n]));
    for (const [id, b] of blocks) {
      const at = outer.place.get(id);
      const bx = snap(origin.x + at.x);
      const by = snap(origin.y + at.y);
      if (b.node) {
        const n = nodes.get(b.node.id);
        if (n.x !== bx || n.y !== by) moved += 1;
        Object.assign(n, { x: bx, y: by });
        continue;
      }
      const c = draft.containers.find((k) => k.id === b.container.id);
      Object.assign(c, { x: bx, y: by, width: snap(b.w), height: snap(b.h) });
      for (const [nid, p] of b.inner) {
        const n = nodes.get(nid);
        const nx = snap(bx + PAD + p.x);
        const ny = snap(by + b.top + p.y);
        if (n.x !== nx || n.y !== ny) moved += 1;
        Object.assign(n, { x: nx, y: ny });
      }
    }
  }, { structural: true });
  return moved;
}
