// Fios organizados (spec 041, RF-4110..4113): segmentos retos com cantos arredondados que desviam das caixas.
// Só contas, sem tocar na tela. Cada fio procura o caminho numa grade esparsa, feita das bordas das caixas que
// estão perto dele (A* com custo por curva); depois os fios que correm juntos ganham pistas separadas.

const MARGIN = 14; // folga em volta das caixas
const STUB = 18; // quanto o fio sai reto da porta
const BEND = 26; // custo de cada curva, em px: prefere menos curvas a caminhos um pouco mais curtos
const RADIUS = 7;
const LANE = 7; // distância entre fios que correm juntos
const MAX_LANES = 3;

export const WIRE_STUB = STUB;

/** Retângulo inflado: o fio não entra. */
const inflate = (r, m = MARGIN) => ({ x1: r.x1 - m, y1: r.y1 - m, x2: r.x2 + m, y2: r.y2 + m });

const insideOpen = (o, x, y) => x > o.x1 + 0.5 && x < o.x2 - 0.5 && y > o.y1 + 0.5 && y < o.y2 - 0.5;

function crosses(o, x1, y1, x2, y2) {
  if (x1 === x2) {
    const [a, b] = y1 < y2 ? [y1, y2] : [y2, y1];
    return x1 > o.x1 + 0.5 && x1 < o.x2 - 0.5 && b > o.y1 + 0.5 && a < o.y2 - 0.5;
  }
  const [a, b] = x1 < x2 ? [x1, x2] : [x2, x1];
  return y1 > o.y1 + 0.5 && y1 < o.y2 - 0.5 && b > o.x1 + 0.5 && a < o.x2 - 0.5;
}

/** Fila de prioridade mínima (heap binário). */
class Heap {
  constructor() { this.items = []; }
  push(item, key) {
    const a = this.items;
    a.push([key, item]);
    let i = a.length - 1;
    while (i > 0) {
      const p = (i - 1) >> 1;
      if (a[p][0] <= a[i][0]) break;
      [a[p], a[i]] = [a[i], a[p]];
      i = p;
    }
  }
  pop() {
    const a = this.items;
    const top = a[0];
    const last = a.pop();
    if (a.length) {
      a[0] = last;
      let i = 0;
      for (;;) {
        const l = 2 * i + 1;
        const r = l + 1;
        let m = i;
        if (l < a.length && a[l][0] < a[m][0]) m = l;
        if (r < a.length && a[r][0] < a[m][0]) m = r;
        if (m === i) break;
        [a[m], a[i]] = [a[i], a[m]];
        i = m;
      }
    }
    return top?.[1];
  }
  get size() { return this.items.length; }
}

const uniqSorted = (values) => [...new Set(values.map((v) => Math.round(v)))].sort((p, q) => p - q);

/** Caminho de `s` a `t` (já fora das portas) numa janela; null quando não há. */
function search(s, t, obstacles, pad) {
  const box = {
    x1: Math.min(s.x, t.x) - pad, y1: Math.min(s.y, t.y) - pad,
    x2: Math.max(s.x, t.x) + pad, y2: Math.max(s.y, t.y) + pad,
  };
  const near = obstacles.filter((o) => o.x2 > box.x1 && o.x1 < box.x2 && o.y2 > box.y1 && o.y1 < box.y2);
  const xs = uniqSorted([s.x, t.x, box.x1, box.x2, ...near.flatMap((o) => [o.x1, o.x2])]).filter((x) => x >= box.x1 && x <= box.x2);
  const ys = uniqSorted([s.y, t.y, box.y1, box.y2, ...near.flatMap((o) => [o.y1, o.y2])]).filter((y) => y >= box.y1 && y <= box.y2);
  const free = (i, j) => !near.some((o) => insideOpen(o, xs[i], ys[j]));
  const si = xs.indexOf(Math.round(s.x));
  const sj = ys.indexOf(Math.round(s.y));
  const ti = xs.indexOf(Math.round(t.x));
  const tj = ys.indexOf(Math.round(t.y));
  if (si < 0 || sj < 0 || ti < 0 || tj < 0) return null;
  const W = xs.length;
  const key = (i, j, d) => (j * W + i) * 4 + d; // d: 0 direita, 1 esquerda, 2 baixo, 3 cima
  const DIRS = [[1, 0], [-1, 0], [0, 1], [0, -1]];
  const best = new Map();
  const from = new Map();
  const heap = new Heap();
  const h = (i, j) => Math.abs(xs[i] - xs[ti]) + Math.abs(ys[j] - ys[tj]);
  const start = key(si, sj, 0); // sai da porta para a direita
  best.set(start, 0);
  heap.push([si, sj, 0, start], h(si, sj));
  while (heap.size) {
    const [i, j, d, k] = heap.pop();
    const g = best.get(k);
    if (i === ti && j === tj) {
      // chega andando para a direita na porta de entrada: uma curva a mais se chegou de outro jeito
      const pts = [];
      let cur = k;
      while (cur !== undefined) {
        const cell = Math.floor(cur / 4);
        pts.push({ x: xs[cell % W], y: ys[Math.floor(cell / W)] });
        cur = from.get(cur);
      }
      return { points: pts.reverse(), cost: g + (d === 0 ? 0 : BEND) };
    }
    for (let nd = 0; nd < 4; nd += 1) {
      if ((d ^ 1) === nd && (d < 2) === (nd < 2)) continue; // não volta pelo mesmo caminho
      const ni = i + DIRS[nd][0];
      const nj = j + DIRS[nd][1];
      if (ni < 0 || nj < 0 || ni >= W || nj >= ys.length || !free(ni, nj)) continue;
      if (near.some((o) => crosses(o, xs[i], ys[j], xs[ni], ys[nj]))) continue;
      const step = Math.abs(xs[ni] - xs[i]) + Math.abs(ys[nj] - ys[j]) + (nd === d ? 0 : BEND);
      const nk = key(ni, nj, nd);
      const ng = g + step;
      if (ng < (best.get(nk) ?? Infinity)) {
        best.set(nk, ng);
        from.set(nk, k);
        heap.push([ni, nj, nd, nk], ng + h(ni, nj));
      }
    }
  }
  return null;
}

/** Tira pontos que não são curva (no meio de um segmento reto). */
function simplify(points) {
  const out = [];
  for (const p of points) {
    const n = out.length;
    if (n && out[n - 1].x === p.x && out[n - 1].y === p.y) continue;
    if (n >= 2 && ((out[n - 2].x === out[n - 1].x && out[n - 1].x === p.x) || (out[n - 2].y === out[n - 1].y && out[n - 1].y === p.y))) out[n - 1] = p;
    else out.push(p);
  }
  return out;
}

/**
 * Rota de um fio, da porta `a` (saída) à porta `b` (entrada), desviando de `obstacles` (retângulos {x1,y1,x2,y2}
 * das caixas, sem as duas pontas). Devolve os pontos, ou null quando nem a janela maior acha caminho.
 */
export function routeWire(a, b, obstacles, ends = []) {
  const s = { x: a.x + STUB, y: a.y };
  const t = { x: b.x - STUB, y: b.y };
  // As caixas das pontas também são obstáculo, mas só depois da saída: o fio não volta por dentro delas.
  // Caixas muito juntas: tenta com folga menor antes de desistir. Caixa encostada na porta sai da conta.
  for (const margin of [MARGIN, 6, 2]) {
    const obs = [...obstacles, ...ends].map((r) => inflate(r, margin)).filter((o) => !insideOpen(o, s.x, s.y) && !insideOpen(o, t.x, t.y));
    for (const pad of [120, 360, 900]) {
      const found = search(s, t, obs, pad);
      if (found) return simplify([a, ...found.points, b]);
    }
  }
  return null;
}

/**
 * Pistas (RF-4111): segmentos de fios diferentes que correm sobre a mesma linha são afastados; fios da mesma porta
 * de saída dividem o tronco. `routes`: [{ id, group, points }]. Mexe nos pontos internos (nunca nas portas).
 */
export function separateLanes(routes, obstacles = []) {
  const solid = obstacles.map((r) => inflate(r, 3));
  const blocked = (x1, y1, x2, y2) => solid.some((o) => crosses(o, x1, y1, x2, y2));
  for (const vertical of [true, false]) {
    const lines = new Map();
    for (const r of routes) {
      const p = r.points;
      for (let i = 1; i < p.length - 2; i += 1) { // não mexe no primeiro nem no último segmento (portas)
        const q = p[i];
        const w = p[i + 1];
        if (vertical ? q.x !== w.x : q.y !== w.y) continue;
        const at = vertical ? q.x : q.y;
        const lo = vertical ? Math.min(q.y, w.y) : Math.min(q.x, w.x);
        const hi = vertical ? Math.max(q.y, w.y) : Math.max(q.x, w.x);
        if (!lines.has(at)) lines.set(at, []);
        lines.get(at).push({ r, i, lo, hi });
      }
    }
    for (const segs of lines.values()) {
      if (segs.length < 2) continue;
      segs.sort((p, q) => p.lo - q.lo);
      // grupos que se sobrepõem; dentro de cada um, uma pista por porta de saída
      let cluster = [];
      let end = -Infinity;
      const flush = () => {
        const groups = [...new Set(cluster.map((s) => s.r.group))];
        if (groups.length > 1) {
          cluster.forEach((s) => {
            const k = groups.indexOf(s.r.group);
            const offset = Math.max(-MAX_LANES, Math.min(MAX_LANES, k - (groups.length - 1) / 2)) * LANE;
            const p = s.r.points;
            const [q, w] = [p[s.i], p[s.i + 1]];
            const moved = vertical ? [q.x + offset, q.y, w.x + offset, w.y] : [q.x, q.y + offset, w.x, w.y + offset];
            if (!offset || blocked(...moved)) return; // afastar entraria numa caixa: fica na linha
            if (vertical) { p[s.i] = { ...p[s.i], x: p[s.i].x + offset }; p[s.i + 1] = { ...p[s.i + 1], x: p[s.i + 1].x + offset }; }
            else { p[s.i] = { ...p[s.i], y: p[s.i].y + offset }; p[s.i + 1] = { ...p[s.i + 1], y: p[s.i + 1].y + offset }; }
          });
        }
        cluster = [];
      };
      for (const s of segs) {
        if (s.lo >= end) flush();
        cluster.push(s);
        end = Math.max(end, s.hi);
      }
      flush();
    }
  }
  // depois de afastar, os vizinhos de cada ponto movido precisam continuar retos
  for (const r of routes) {
    const p = r.points;
    for (let i = 1; i < p.length - 1; i += 1) {
      const prev = p[i - 1];
      if (prev.x !== p[i].x && prev.y !== p[i].y) {
        // segmento ficou torto: corrige pelo eixo do segmento seguinte
        if (i + 1 < p.length && p[i + 1].x === p[i].x) p[i] = { ...p[i], y: prev.y };
        else p[i] = { ...p[i], x: prev.x };
      }
    }
  }
  return routes;
}

/** Caminho SVG com cantos arredondados. */
export function roundedPath(points) {
  if (points.length < 2) return '';
  let d = `M ${points[0].x} ${points[0].y}`;
  for (let i = 1; i < points.length - 1; i += 1) {
    const p = points[i - 1];
    const q = points[i];
    const n = points[i + 1];
    const r = Math.min(RADIUS, Math.hypot(q.x - p.x, q.y - p.y) / 2, Math.hypot(n.x - q.x, n.y - q.y) / 2);
    const ax = q.x - Math.sign(q.x - p.x) * r;
    const ay = q.y - Math.sign(q.y - p.y) * r;
    const bx = q.x + Math.sign(n.x - q.x) * r;
    const by = q.y + Math.sign(n.y - q.y) * r;
    d += ` L ${ax} ${ay} Q ${q.x} ${q.y} ${bx} ${by}`;
  }
  const last = points[points.length - 1];
  return `${d} L ${last.x} ${last.y}`;
}

/** Ponto no meio do comprimento do fio (rótulo com a contagem de linhas). */
export function polylineMid(points) {
  const lens = points.slice(1).map((p, i) => Math.hypot(p.x - points[i].x, p.y - points[i].y));
  let half = lens.reduce((s, x) => s + x, 0) / 2;
  for (let i = 0; i < lens.length; i += 1) {
    if (half <= lens[i]) {
      const u = lens[i] ? half / lens[i] : 0;
      return { x: points[i].x + (points[i + 1].x - points[i].x) * u, y: points[i].y + (points[i + 1].y - points[i].y) * u };
    }
    half -= lens[i];
  }
  return points[points.length - 1];
}

/** Pontos ao longo do fio, para saber se o mouse passa perto (inserir caixa no fio, clicar no fio). */
export function polylineSamples(points, step = 14) {
  const out = [];
  for (let i = 1; i < points.length; i += 1) {
    const p = points[i - 1];
    const q = points[i];
    const n = Math.max(1, Math.ceil(Math.hypot(q.x - p.x, q.y - p.y) / step));
    for (let k = 0; k < n; k += 1) out.push({ x: p.x + ((q.x - p.x) * k) / n, y: p.y + ((q.y - p.y) * k) / n });
  }
  return out;
}

/** Seta na chegada de um fio organizado: sempre entra na porta da esquerda para a direita. */
export function arrowInto(b, gap = 9) {
  const x = b.x - gap;
  return `M ${x - 5} ${b.y - 4} L ${x} ${b.y} L ${x - 5} ${b.y + 4}`;
}
