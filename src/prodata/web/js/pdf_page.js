// Visor do documento no leitor de PDF (spec 037, RF-3711..3715): páginas, palavras selecionáveis, zoom, busca,
// miniaturas, marcas dos campos e tabelas, guias arrastáveis e a volta à origem.
// A camada de palavras fica em porcentagem sobre a imagem: o alinhamento não depende de zoom, escala de tela nem
// resolução da imagem (validado no spike: 0 palavras fora do texto em 27 combinações).

import { api } from './api.js';
import { button, h } from './dom.js';
import { icon } from './icons.js';

const ZOOMS = [0.5, 0.67, 0.8, 1, 1.25, 1.5, 2, 2.5, 3];
const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
const mid = (w) => (w.b[1] + w.b[3]) / 2;
const norm = (t) => t.normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase();
export const boxStyle = (b) => ({ left: `${b[0] * 100}%`, top: `${b[1] * 100}%`, width: `${(b[2] - b[0]) * 100}%`, height: `${(b[3] - b[1]) * 100}%` });

// Espaço de leitura: o texto corre da esquerda para a direita (o mesmo do motor, layout.py).
export function toReading([x0, y0, x1, y1], t) {
  if (t === 90) return [y0, 1 - x1, y1, 1 - x0];
  if (t === 180) return [1 - x1, 1 - y1, 1 - x0, 1 - y0];
  if (t === 270) return [1 - y1, x0, 1 - y0, x1];
  return [x0, y0, x1, y1];
}
export function toScreen([x0, y0, x1, y1], t) {
  if (t === 90) return [1 - y1, x0, 1 - y0, x1];
  if (t === 180) return [1 - x1, 1 - y1, 1 - x0, 1 - y0];
  if (t === 270) return [y0, 1 - x1, y1, 1 - x0];
  return [x0, y0, x1, y1];
}

/**
 * `opts`: onSelection(words), onPrimary(), onTable(), onLabel(), onWordClick(index), onCarry(words) (soltou a
 * seleção sobre o Resultado), dropTarget() (o elemento que aceita a seleção arrastada), renderAction(words) → elemento.
 */
export function createViewer(opts) {
  const V = {
    sourceId: null, doc: null, info: null, fit: 'width', zoom: 1,
    lines: [], order: [], pos: new Map(), lineOf: new Map(),
    sel: new Set(), anchor: null, cursor: null,
    hits: [], hit: -1, marks: null, current: 0,
  };
  const scroller = h('div', { class: 'pv-scroll', tabindex: '0', role: 'application',
    'aria-label': 'Páginas do documento. Setas andam pelas palavras, Shift marca, Enter cria o campo, T cria tabela, Esc limpa.' });
  const pagesEl = h('div', { class: 'pv-pages' });
  const thumbs = h('nav', { class: 'pv-thumbs', 'aria-label': 'Miniaturas das páginas', hidden: true });
  const live = h('div', { class: 'sr-only', 'aria-live': 'polite' });
  scroller.append(pagesEl);

  // ---------------------------------------------------------- barra do documento
  const pageLabel = h('span', { class: 'pv-page-label', 'aria-live': 'polite' }, '');
  const zoomLabel = h('span', {}, 'Largura');
  const zoomBtn = h('button', { type: 'button', class: 'btn btn-ghost pv-zoom', title: 'Zoom', onclick: (e) => zoomMenu(e) }, zoomLabel, icon('chevron-down', 12));
  const search = h('input', { type: 'search', class: 'input pv-search', placeholder: 'Buscar no documento', 'aria-label': 'Buscar no documento',
    oninput: () => runSearch(search.value), onkeydown: (e) => { if (e.key === 'Enter') { e.preventDefault(); stepHit(e.shiftKey ? -1 : 1); } if (e.key === 'Escape') { search.value = ''; runSearch(''); scroller.focus(); } } });
  const hitLabel = h('span', { class: 'pv-hits' }, '');
  const thumbBtn = button({ icon: 'panel', title: 'Miniaturas das páginas', variant: 'ghost', onClick: () => { thumbs.hidden = !thumbs.hidden; thumbBtn.setAttribute('aria-pressed', String(!thumbs.hidden)); if (!thumbs.hidden) drawThumbs(); } });
  const toolbar = h('div', { class: 'pv-toolbar', role: 'toolbar', 'aria-label': 'Documento' },
    thumbBtn,
    button({ icon: 'chevron-up', title: 'Página anterior (PgUp)', variant: 'ghost', onClick: () => goPage(V.current - 1) }),
    pageLabel,
    button({ icon: 'chevron-down', title: 'Próxima página (PgDn)', variant: 'ghost', onClick: () => goPage(V.current + 1) }),
    h('span', { class: 'pv-sep' }),
    button({ icon: 'zoom-out', title: 'Diminuir zoom (−)', variant: 'ghost', onClick: () => stepZoom(-1) }),
    zoomBtn,
    button({ icon: 'zoom-in', title: 'Aumentar zoom (+)', variant: 'ghost', onClick: () => stepZoom(1) }),
    h('span', { class: 'pv-sep' }),
    h('div', { class: 'pv-search-wrap' }, icon('search', 14), search, hitLabel,
      button({ icon: 'chevron-up', title: 'Achado anterior (Shift+Enter)', variant: 'ghost', size: 'sm', onClick: () => stepHit(-1) }),
      button({ icon: 'chevron-down', title: 'Próximo achado (Enter)', variant: 'ghost', size: 'sm', onClick: () => stepHit(1) })));
  const body = h('div', { class: 'pv-body' }, thumbs, scroller);
  const el = h('div', { class: 'pv' }, toolbar, body, live);

  // ---------------------------------------------------------- palavras em ordem de leitura
  function buildOrder(words) {
    const idx = words.map((_, i) => i).sort((a, b) => words[a].p - words[b].p || mid(words[a]) - mid(words[b]));
    const lines = [];
    for (const i of idx) {
      const w = words[i];
      const hgt = w.b[3] - w.b[1];
      const last = lines[lines.length - 1];
      if (last && last.p === w.p && Math.abs(mid(w) - last.mid) < 0.5 * Math.min(hgt, last.h)) last.items.push(i);
      else lines.push({ p: w.p, mid: mid(w), h: hgt, items: [i] });
    }
    for (const ln of lines) ln.items.sort((a, b) => words[a].b[0] - words[b].b[0]);
    V.lines = lines.map((l) => l.items);
    V.order = V.lines.flat();
    V.pos = new Map(V.order.map((i, k) => [i, k]));
    V.lineOf = new Map();
    V.lines.forEach((items, k) => items.forEach((i) => V.lineOf.set(i, k)));
  }

  // ---------------------------------------------------------- páginas (sob demanda)
  const baseWidth = () => Math.max(Math.min(scroller.clientWidth - 48, 1100), 280);
  function pageWidth(p) {
    const pg = V.info.pages[p];
    if (V.fit === 'page') {
      const byHeight = (scroller.clientHeight - 40) * (pg.w / pg.h);
      return Math.max(Math.min(baseWidth(), byHeight), 200);
    }
    return baseWidth() * (V.fit === 'width' ? 1 : V.zoom);
  }
  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) if (entry.isIntersecting) fillPage(entry.target);
  }, { root: scroller, rootMargin: '600px 0px' });
  const visible = new IntersectionObserver((entries) => {
    const best = entries.filter((e) => e.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
    if (best) { V.current = +best.target.dataset.page; drawPageLabel(); }
  }, { root: scroller, threshold: [0.25, 0.5, 0.75] });

  function drawPages() {
    observer.disconnect();
    visible.disconnect();
    pagesEl.replaceChildren();
    if (!V.info) return;
    if (V.info.erro) {
      pagesEl.append(h('div', { class: 'pv-empty' }, icon('alert', 28), h('b', {}, 'Este PDF não pode ser lido'),
        h('p', {}, V.info.erro === 'sem_texto'
          ? 'Ele é uma imagem (escaneado): não há texto para marcar. O Desata ainda não lê texto de imagens. Os outros documentos continuam normais.'
          : `${V.info.mensagem}. Os outros documentos continuam normais.`)));
      return;
    }
    V.info.pages.forEach((pg, p) => {
      const page = h('div', { class: 'pv-page', dataset: { page: String(p) } }, h('div', { class: 'pv-page-num' }, `Página ${p + 1}`));
      pagesEl.append(page);
      observer.observe(page);
      visible.observe(page);
    });
    layout();
  }

  function fillPage(page) {
    if (page.dataset.filled) return;
    page.dataset.filled = '1';
    const p = +page.dataset.page;
    const layer = h('div', { class: 'pv-layer' });
    V.info.words.forEach((w, i) => {
      if (w.p !== p) return;
      layer.append(h('span', { class: ['pv-w', V.sel.has(i) && 'sel', V.cursor === i && 'cursor'], dataset: { i: String(i) }, style: boxStyle(w.b) }));
    });
    page.prepend(h('img', { alt: `Página ${p + 1}`, draggable: 'false' }));
    page.append(layer, h('div', { class: 'pv-marks' }));
    bindSelection(page, layer);
    loadImage(page);
    drawMarksOn(p);
    drawHitsOn(p);
  }

  function loadImage(page) {
    const img = page.querySelector('img');
    if (!img) return;
    const p = +page.dataset.page;
    const pg = V.info.pages[p];
    const scale = Math.min(4, Math.ceil(((page.clientWidth * devicePixelRatio) / pg.w) * 4) / 4) || 1;
    const src = api.pdfPageUrl(V.sourceId, V.doc, p, scale);
    if (img.dataset.src === src) return;
    const pre = new Image();
    pre.onload = () => { img.src = src; img.dataset.src = src; };
    pre.src = src;
  }

  let imgTimer = 0;
  function layout() {
    if (!V.info || V.info.erro) return;
    pagesEl.querySelectorAll('.pv-page').forEach((page) => {
      const p = +page.dataset.page;
      const pg = V.info.pages[p];
      const width = pageWidth(p);
      page.style.width = `${width}px`;
      page.style.height = `${(width * pg.h) / pg.w}px`;
    });
    zoomLabel.textContent = V.fit === 'width' ? 'Largura' : V.fit === 'page' ? 'Página' : `${Math.round(V.zoom * 100)}%`;
    clearTimeout(imgTimer);
    imgTimer = setTimeout(() => pagesEl.querySelectorAll('.pv-page[data-filled]').forEach(loadImage), 140);
    renderAction();
  }

  function setZoom(z, anchor) {
    const ax = anchor ? anchor.x : scroller.clientWidth / 2;
    const ay = anchor ? anchor.y : scroller.clientHeight / 2;
    const rx = (scroller.scrollLeft + ax) / Math.max(pagesEl.scrollWidth, 1);
    const ry = (scroller.scrollTop + ay) / Math.max(pagesEl.scrollHeight, 1);
    if (z === 'width' || z === 'page') V.fit = z;
    else { V.fit = 'zoom'; V.zoom = Math.min(3, Math.max(0.5, z)); }
    layout();
    scroller.scrollLeft = rx * pagesEl.scrollWidth - ax;
    scroller.scrollTop = ry * pagesEl.scrollHeight - ay;
  }
  const currentZoom = () => (V.fit === 'zoom' ? V.zoom : pageWidth(V.current) / baseWidth());
  const stepZoom = (dir) => {
    const z = currentZoom();
    setZoom(dir > 0 ? ZOOMS.find((x) => x > z + 1e-3) ?? 3 : [...ZOOMS].reverse().find((x) => x < z - 1e-3) ?? 0.5);
  };
  function zoomMenu(e) {
    const r = e.currentTarget.getBoundingClientRect();
    const menu = h('div', { class: 'menu pv-zoom-menu', role: 'menu', style: { left: `${r.left}px`, top: `${r.bottom + 4}px` } },
      [['width', 'Ajustar à largura'], ['page', 'Ajustar à página'], ...ZOOMS.map((z) => [z, `${Math.round(z * 100)}%`])].map(([z, label]) => h('button', {
        type: 'button', role: 'menuitem', class: 'menu-item', onclick: () => { menu.remove(); setZoom(z); scroller.focus(); },
      }, label)));
    document.body.append(menu);
    const close = (ev) => { if (!menu.contains(ev.target)) { menu.remove(); document.removeEventListener('pointerdown', close, true); } };
    setTimeout(() => document.addEventListener('pointerdown', close, true));
    menu.querySelector('button')?.focus();
  }

  function drawPageLabel() {
    if (!V.info || V.info.erro) { pageLabel.textContent = ''; return; }
    pageLabel.textContent = `Página ${V.current + 1} de ${V.info.pages.length}`;
    thumbs.querySelectorAll('.pv-thumb').forEach((t) => t.setAttribute('aria-current', String(+t.dataset.page === V.current)));
  }
  function goPage(p) {
    if (!V.info?.pages?.length) return;
    const target = pagesEl.querySelector(`.pv-page[data-page="${Math.max(0, Math.min(p, V.info.pages.length - 1))}"]`);
    target?.scrollIntoView({ block: 'start', behavior: reduced() ? 'auto' : 'smooth' });
  }
  function drawThumbs() {
    if (!V.info || V.info.erro) { thumbs.replaceChildren(); return; }
    thumbs.replaceChildren(...V.info.pages.map((pg, p) => h('button', {
      type: 'button', class: 'pv-thumb', dataset: { page: String(p) }, 'aria-label': `Página ${p + 1}`, 'aria-current': String(p === V.current), onclick: () => goPage(p),
    }, h('img', { alt: '', loading: 'lazy', src: api.pdfPageUrl(V.sourceId, V.doc, p, 0.5), style: { aspectRatio: `${pg.w} / ${pg.h}` } }), h('small', {}, String(p + 1)))));
  }

  // ---------------------------------------------------------- busca
  function runSearch(q) {
    const wanted = norm(q.trim());
    V.hits = [];
    V.hit = -1;
    if (wanted && V.info?.words) {
      const tokens = wanted.split(/\s+/);
      for (const line of V.lines) {
        const words = line.map((i) => norm(V.info.words[i].t));
        for (let k = 0; k < words.length; k += 1) {
          if (tokens.length === 1 ? words[k].includes(tokens[0]) : tokens.every((t, j) => (words[k + j] || '').startsWith(t) || (j === 0 && words[k].endsWith(t)))) {
            V.hits.push(line.slice(k, k + tokens.length));
          }
        }
      }
    }
    hitLabel.textContent = q.trim() ? (V.hits.length ? `${V.hits.length} achado${V.hits.length > 1 ? 's' : ''}` : 'nada encontrado') : '';
    pagesEl.querySelectorAll('.pv-page[data-filled]').forEach((page) => drawHitsOn(+page.dataset.page));
    if (V.hits.length) stepHit(1);
  }
  function drawHitsOn(p) {
    const marks = pagesEl.querySelector(`.pv-page[data-page="${p}"] .pv-marks`);
    if (!marks) return;
    marks.querySelectorAll('.pv-hit').forEach((x) => x.remove());
    V.hits.forEach((group, k) => {
      const words = group.map((i) => V.info.words[i]).filter((w) => w.p === p);
      if (!words.length) return;
      const b = [Math.min(...words.map((w) => w.b[0])), Math.min(...words.map((w) => w.b[1])), Math.max(...words.map((w) => w.b[2])), Math.max(...words.map((w) => w.b[3]))];
      marks.append(h('div', { class: ['pv-hit', k === V.hit && 'current'], style: boxStyle(b) }));
    });
  }
  function stepHit(dir) {
    if (!V.hits.length) return;
    V.hit = (V.hit + dir + V.hits.length) % V.hits.length;
    hitLabel.textContent = `${V.hit + 1} de ${V.hits.length}`;
    const first = V.info.words[V.hits[V.hit][0]];
    revealBox(first.p, first.b);
    pagesEl.querySelectorAll('.pv-page[data-filled]').forEach((page) => drawHitsOn(+page.dataset.page));
  }

  // ---------------------------------------------------------- seleção
  const pageOf = (p) => pagesEl.querySelector(`.pv-page[data-page="${p}"]`);
  function pagePoint(page, e) {
    const r = page.getBoundingClientRect();
    return { x: (e.clientX - r.left) / r.width, y: (e.clientY - r.top) / r.height, px: e.clientX, py: e.clientY };
  }

  function bindSelection(page, layer) {
    let drag = null;
    let band = null;
    let ghost = null;
    layer.addEventListener('pointerdown', (e) => {
      if (e.button !== 0) return;
      scroller.focus({ preventScroll: true });
      const target = e.target.closest('.pv-w');
      const index = target ? +target.dataset.i : null;
      drag = { start: pagePoint(page, e), moved: false, target: index, shift: e.shiftKey, add: e.ctrlKey || e.metaKey,
        carry: index !== null && V.sel.has(index) && V.sel.size > 0 && !e.shiftKey && !e.ctrlKey };
      layer.setPointerCapture(e.pointerId);
    });
    layer.addEventListener('pointermove', (e) => {
      if (!drag) return;
      const cur = pagePoint(page, e);
      if (!drag.moved && Math.hypot(cur.px - drag.start.px, cur.py - drag.start.py) < 5) return;
      drag.moved = true;
      if (drag.carry) { // arrastar a seleção até o Resultado (RF-3715)
        if (!ghost) {
          ghost = h('div', { class: 'pv-carry' }, icon('plus', 12), selectedText().slice(0, 40));
          document.body.append(ghost);
          opts.dropTarget?.()?.classList.add('pe-drop-ready');
        }
        ghost.style.left = `${e.clientX + 12}px`;
        ghost.style.top = `${e.clientY + 12}px`;
        const over = opts.dropTarget?.()?.contains(document.elementFromPoint(e.clientX, e.clientY));
        opts.dropTarget?.()?.classList.toggle('pe-drop-over', Boolean(over));
        return;
      }
      const x0 = Math.min(drag.start.x, cur.x);
      const y0 = Math.min(drag.start.y, cur.y);
      const x1 = Math.max(drag.start.x, cur.x);
      const y1 = Math.max(drag.start.y, cur.y);
      if (!band) { band = h('div', { class: 'pv-band' }); page.append(band); }
      Object.assign(band.style, boxStyle([x0, y0, x1, y1]));
      const p = +page.dataset.page;
      const hit = [];
      V.info.words.forEach((w, i) => { if (w.p === p && w.b[0] < x1 && w.b[2] > x0 && w.b[1] < y1 && w.b[3] > y0) hit.push(i); });
      setSelection(drag.add ? new Set([...V.sel, ...hit]) : new Set(hit), { live: true });
    });
    layer.addEventListener('pointerup', (e) => {
      if (!drag) return;
      band?.remove();
      band = null;
      const d = drag;
      drag = null;
      if (d.carry && d.moved) {
        ghost?.remove();
        ghost = null;
        const target = opts.dropTarget?.();
        target?.classList.remove('pe-drop-ready', 'pe-drop-over');
        if (target?.contains(document.elementFromPoint(e.clientX, e.clientY))) opts.onCarry?.(selectedWords());
        return;
      }
      if (d.moved) {
        const sorted = [...V.sel].sort((a, b) => V.pos.get(a) - V.pos.get(b));
        V.anchor = sorted[0] ?? null;
        V.cursor = sorted.at(-1) ?? null;
        setSelection(V.sel);
        return;
      }
      if (d.target === null) { V.anchor = V.cursor = null; setSelection(new Set()); return; }
      if (d.shift && V.anchor !== null) { V.cursor = d.target; selectRange(V.anchor, d.target); return; }
      if (d.add) {
        const next = new Set(V.sel);
        if (next.has(d.target)) next.delete(d.target);
        else next.add(d.target);
        V.anchor = V.cursor = d.target;
        setSelection(next);
        return;
      }
      V.anchor = V.cursor = d.target;
      setSelection(new Set([d.target]));
      opts.onWordClick?.(d.target);
    });
    layer.addEventListener('dblclick', (e) => {
      const t = e.target.closest('.pv-w');
      if (!t) return;
      const group = valueGroup(+t.dataset.i);
      V.anchor = group[0];
      V.cursor = group.at(-1);
      setSelection(new Set(group));
    });
  }

  function valueGroup(i) {
    const words = V.info.words;
    const line = V.lines[V.lineOf.get(i)];
    const k = line.indexOf(i);
    const pg = V.info.pages[words[i].p];
    const ratio = [90, 270].includes(pg.t) ? pg.w / pg.h : pg.h / pg.w;
    const gap = (a, b) => {
      const ra = toReading(words[a].b, pg.t || 0);
      const rb = toReading(words[b].b, pg.t || 0);
      return (rb[0] - ra[2]) / Math.max(ra[3] - ra[1], 1e-4) / ratio;
    };
    let a = k;
    let b = k;
    while (a > 0 && gap(line[a - 1], line[a]) <= 1.5 && !words[line[a - 1]].t.endsWith(':')) a -= 1;
    while (b < line.length - 1 && gap(line[b], line[b + 1]) <= 1.5) b += 1;
    return line.slice(a, b + 1);
  }

  function selectRange(a, b) {
    const [lo, hi] = [V.pos.get(a), V.pos.get(b)].sort((x, y) => x - y);
    setSelection(new Set(V.order.slice(lo, hi + 1)));
  }

  function setSelection(sel, { live: isLive = false } = {}) {
    pagesEl.querySelectorAll('.pv-w.sel, .pv-w.cursor').forEach((x) => x.classList.remove('sel', 'cursor'));
    V.sel = sel;
    for (const i of sel) pagesEl.querySelector(`.pv-w[data-i="${i}"]`)?.classList.add('sel');
    if (V.cursor !== null) pagesEl.querySelector(`.pv-w[data-i="${V.cursor}"]`)?.classList.add('cursor');
    renderAction();
    if (isLive) return;
    live.textContent = sel.size ? `Marcado: ${selectedText()}. Enter cria o campo.` : '';
    opts.onSelection?.(selectedWords());
  }

  const selectedWords = () => [...V.sel].sort((a, b) => V.pos.get(a) - V.pos.get(b)).map((i) => V.info.words[i]);
  const selectedText = () => selectedWords().map((w) => w.t).join(' ');
  const selectedLines = () => new Set([...V.sel].map((i) => V.lineOf.get(i))).size;

  // ---------------------------------------------------------- barra de ação sobre a seleção
  function renderAction() {
    const old = pagesEl.querySelector('.pv-action');
    if (!V.sel.size || !opts.renderAction) { old?.remove(); return; }
    const words = selectedWords();
    const p = words[0].p;
    const page = pageOf(p);
    if (!page) return;
    const on = words.filter((w) => w.p === p);
    const x0 = Math.min(...on.map((w) => w.b[0]));
    const y0 = Math.min(...on.map((w) => w.b[1]));
    const content = opts.renderAction(words, selectedLines());
    if (!content) { old?.remove(); return; }
    const bar = h('div', { class: 'pv-action', role: 'toolbar', 'aria-label': 'Ações da seleção', style: { left: `${x0 * 100}%`, top: `${y0 * 100}%` },
      onpointerdown: (e) => e.stopPropagation() }, content);
    if (old && old.parentElement === page && old.style.left === bar.style.left && old.style.top === bar.style.top) bar.style.animation = 'none';
    old?.remove();
    page.append(bar);
    const pr = page.getBoundingClientRect();
    const br = bar.getBoundingClientRect();
    if (br.right > pr.right) bar.style.left = `${Math.max(0, (pr.width - br.width) / pr.width) * 100}%`;
    if (br.top < scroller.getBoundingClientRect().top + 4) bar.classList.add('below'); // sem espaço em cima: vai para baixo
  }

  function selectionRect() {
    const els = [...V.sel].map((i) => pagesEl.querySelector(`.pv-w[data-i="${i}"]`)).filter(Boolean);
    if (!els.length) return null;
    const rs = els.map((x) => x.getBoundingClientRect());
    const left = Math.min(...rs.map((r) => r.left));
    const top = Math.min(...rs.map((r) => r.top));
    return { left, top, width: Math.max(...rs.map((r) => r.right)) - left, height: Math.max(...rs.map((r) => r.bottom)) - top };
  }

  // ---------------------------------------------------------- teclado
  scroller.addEventListener('keydown', (e) => {
    if (!V.info || V.info.erro) return;
    const k = e.key;
    if (k === 'Enter') { e.preventDefault(); if (V.sel.size) opts.onPrimary?.(); return; }
    if ((k === 't' || k === 'T') && !e.ctrlKey) { e.preventDefault(); opts.onTable?.(); return; }
    if ((k === 'r' || k === 'R') && !e.ctrlKey) { e.preventDefault(); opts.onLabel?.(); return; }
    if (k === 'Escape') { if (V.sel.size) { e.stopPropagation(); V.anchor = V.cursor = null; setSelection(new Set()); } return; }
    if (k === '+' || k === '=') { e.preventDefault(); stepZoom(1); return; }
    if (k === '-') { e.preventDefault(); stepZoom(-1); return; }
    if (k === '0') { e.preventDefault(); setZoom('width'); return; }
    if (k === 'PageDown' || k === 'PageUp') { e.preventDefault(); goPage(V.current + (k === 'PageDown' ? 1 : -1)); return; }
    if ((e.ctrlKey || e.metaKey) && k === 'f') { e.preventDefault(); search.focus(); search.select(); return; }
    if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End'].includes(k)) return;
    e.preventDefault();
    if (V.cursor === null) V.cursor = firstVisibleWord();
    else {
      const pos = V.pos.get(V.cursor);
      const line = V.lineOf.get(V.cursor);
      const items = V.lines[line];
      if (k === 'ArrowRight') V.cursor = V.order[Math.min(pos + 1, V.order.length - 1)];
      else if (k === 'ArrowLeft') V.cursor = V.order[Math.max(pos - 1, 0)];
      else if (k === 'Home') V.cursor = items[0];
      else if (k === 'End') V.cursor = items.at(-1);
      else {
        const target = V.lines[Math.min(Math.max(line + (k === 'ArrowDown' ? 1 : -1), 0), V.lines.length - 1)];
        const w = V.info.words[V.cursor];
        const cx = (w.b[0] + w.b[2]) / 2;
        V.cursor = target.reduce((best, i) => {
          const b = V.info.words[i].b;
          const d = Math.abs((b[0] + b[2]) / 2 - cx);
          return d < best[1] ? [i, d] : best;
        }, [target[0], Infinity])[0];
      }
    }
    const cw = V.info.words[V.cursor];
    fillPage(pageOf(cw.p));
    if (e.shiftKey && V.anchor !== null) selectRange(V.anchor, V.cursor);
    else { V.anchor = V.cursor; setSelection(new Set([V.cursor])); }
    pagesEl.querySelector(`.pv-w[data-i="${V.cursor}"]`)?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  });

  function firstVisibleWord() {
    const top = scroller.getBoundingClientRect().top;
    for (const i of V.order) {
      const node = pagesEl.querySelector(`.pv-w[data-i="${i}"]`);
      if (node && node.getBoundingClientRect().top >= top) return i;
    }
    return V.order[0];
  }

  scroller.addEventListener('wheel', (e) => {
    if (!e.ctrlKey) return;
    e.preventDefault();
    const r = scroller.getBoundingClientRect();
    setZoom(currentZoom() * (e.deltaY < 0 ? 1.1 : 1 / 1.1), { x: e.clientX - r.left, y: e.clientY - r.top });
  }, { passive: false });
  new ResizeObserver(() => { if (V.info && !V.info.erro) layout(); }).observe(scroller);

  // ---------------------------------------------------------- marcas (campos, tabelas, linhas ignoradas, guias)
  function drawMarksOn(p) {
    const marks = pageOf(p)?.querySelector('.pv-marks');
    if (!marks || !V.marks) return;
    marks.querySelectorAll(':scope > :not(.pv-hit)').forEach((x) => x.remove());
    const t = V.info.pages[p]?.t || 0;
    for (const f of V.marks.fields) {
      f.candidates.forEach((cd, n) => {
        for (const o of cd.origem.filter((x) => x.p === p)) {
          const tag = f.state === 'ambiguo' ? `${f.name} · ${n + 1}?` : f.name;
          marks.append(h('div', { class: ['pv-mark', f.state === 'ambiguo' && 'show', f.focus && 'focus'], dataset: { owner: f.name }, style: { ...boxStyle(o.b), '--c': f.color } },
            h('span', { class: 'pv-mark-tag' }, tag)));
        }
        for (const o of (cd.rotulo || []).filter((x) => x.p === p)) {
          marks.append(h('div', { class: 'pv-mark label', dataset: { owner: f.name }, style: { ...boxStyle(o.b), '--c': f.color } }));
        }
      });
    }
    for (const tb of V.marks.tables) {
      const reading = tb.regions[p];
      if (reading) {
        marks.append(h('div', { class: 'pv-region', dataset: { owner: tb.spec.nome }, style: { ...boxStyle(toScreen(reading, t)), '--c': tb.color } },
          h('span', { class: 'pv-mark-tag right' }, `${tb.spec.nome} · ${tb.rows} linhas`)));
        tb.spec.guias.forEach((_, gi) => marks.append(guideHandle(tb, gi, p, reading, t)));
        // RF-3735: a borda de cima na página do cabeçalho, a de baixo na última página, as laterais em todas
        const pages = Object.keys(tb.regions).map(Number);
        const edges = ['left', 'right'];
        if (p === Math.min(...pages)) edges.push('top');
        if (p === Math.max(...pages)) edges.push('bottom');
        for (const edge of edges) marks.append(edgeHandle(tb, edge, p, reading, t));
      }
      for (const ig of tb.ignored) {
        for (const o of ig.origem.filter((x) => x.p === p)) {
          const b = toReading(o.b, t);
          marks.append(h('div', { class: 'pv-ignored', style: boxStyle(toScreen([tb.spec.limites[0], b[1] - 0.003, tb.spec.limites[1], b[3] + 0.003], t)) },
            h('span', {}, ig.motivo)));
        }
      }
    }
  }

  /** Borda da tabela: cima e baixo vão ao motor (cabeçalho e fim); as laterais mudam a faixa da tabela na hora. */
  function edgeHandle(tb, edge, p, reading, t) {
    const spec = tb.spec;
    const side = edge === 'left' || edge === 'right';
    const LABEL = {
      top: 'Borda de cima: a primeira linha abaixo dela é o cabeçalho',
      bottom: 'Borda de baixo: a tabela termina aqui (antes de um texto, ou depois de N linhas)',
      left: 'Borda da esquerda da tabela', right: 'Borda da direita da tabela',
    };
    let cur = { top: reading[1], bottom: reading[3], left: spec.limites[0], right: spec.limites[1] }[edge];
    const node = h('button', { type: 'button', class: ['pv-edge', `pv-edge-${edge}`], style: { '--c': tb.color },
      'aria-label': `${LABEL[edge]}, da tabela ${spec.nome}. Setas movem a borda.`, title: `${LABEL[edge]}. Arraste para ajustar.` });
    const place = () => {
      const box = side ? [cur, reading[1], cur, reading[3]] : [reading[0], cur, reading[2], cur];
      const [x0, y0, x1, y1] = toScreen(box, t);
      const upright = Math.abs(x1 - x0) < Math.abs(y1 - y0);
      node.classList.toggle('upright', upright);
      Object.assign(node.style, upright
        ? { left: `${x0 * 100}%`, top: `${y0 * 100}%`, height: `${(y1 - y0) * 100}%`, width: '' }
        : { left: `${x0 * 100}%`, top: `${y0 * 100}%`, width: `${(x1 - x0) * 100}%`, height: '' });
    };
    place();
    const clamp = (v) => {
      if (edge === 'left') return Math.min(Math.max(v, 0), (spec.guias[0] ?? spec.limites[1]) - 0.01);
      if (edge === 'right') return Math.max(Math.min(v, 1), (spec.guias.at(-1) ?? spec.limites[0]) + 0.01);
      return Math.min(Math.max(v, 0), 1);
    };
    const set = (v, final) => {
      cur = Math.round(clamp(v) * 10000) / 10000;
      place();
      if (side) {
        spec.limites = edge === 'left' ? [cur, spec.limites[1]] : [spec.limites[0], cur];
        tb.onMove?.(final);
      } else if (final) {
        tb.onEdge?.(edge, p, cur);
      }
    };
    node.addEventListener('pointerdown', (e) => {
      e.stopPropagation();
      e.preventDefault();
      node.setPointerCapture(e.pointerId);
      const page = node.closest('.pv-page');
      const move = (ev) => {
        const pt = pagePoint(page, ev);
        const r = toReading([pt.x, pt.y, pt.x, pt.y], t);
        set(side ? r[0] : r[1], false);
      };
      const up = () => { node.removeEventListener('pointermove', move); node.removeEventListener('pointerup', up); set(cur, true); };
      node.addEventListener('pointermove', move);
      node.addEventListener('pointerup', up);
    });
    let idle = null;
    node.addEventListener('keydown', (e) => {
      const keys = side ? { ArrowRight: 1, ArrowLeft: -1 } : { ArrowDown: 1, ArrowUp: -1 };
      if (!(e.key in keys)) return;
      e.preventDefault();
      e.stopPropagation();
      set(cur + keys[e.key] * (e.shiftKey ? 0.01 : 0.003), false);
      clearTimeout(idle);
      idle = setTimeout(() => set(cur, true), 450); // espera parar de teclar para ir ao motor
    });
    return node;
  }

  function guideHandle(tb, gi, p, reading, t) {
    const spec = tb.spec;
    const across = t === 90 || t === 270;
    const place = (node) => {
      const g = spec.guias[gi];
      const [x0, y0, x1, y1] = toScreen([g, reading[1], g, reading[3]], t);
      Object.assign(node.style, across
        ? { left: `${x0 * 100}%`, width: `${(x1 - x0) * 100}%`, top: `${y0 * 100}%`, height: '' }
        : { left: `${x0 * 100}%`, top: `${y0 * 100}%`, height: `${(y1 - y0) * 100}%`, width: '' });
    };
    const node = h('button', { type: 'button', class: ['pv-guide', across && 'across'], style: { '--c': tb.color },
      'aria-label': `Guia ${gi + 1} da tabela ${spec.nome}. Setas movem a guia.`, title: 'Arraste para ajustar a coluna (ou use as setas)' });
    place(node);
    const clamp = (x) => Math.min(Math.max(x, (spec.guias[gi - 1] ?? spec.limites[0]) + 0.01), (spec.guias[gi + 1] ?? spec.limites[1]) - 0.01);
    node.addEventListener('pointerdown', (e) => {
      e.stopPropagation();
      e.preventDefault();
      node.setPointerCapture(e.pointerId);
      const page = node.closest('.pv-page');
      const move = (ev) => {
        const pt = pagePoint(page, ev);
        spec.guias[gi] = Math.round(clamp(toReading([pt.x, pt.y, pt.x, pt.y], t)[0]) * 10000) / 10000;
        place(node);
        tb.onMove?.(false);
      };
      const up = () => { node.removeEventListener('pointermove', move); node.removeEventListener('pointerup', up); tb.onMove?.(true); };
      node.addEventListener('pointermove', move);
      node.addEventListener('pointerup', up);
    });
    node.addEventListener('keydown', (e) => {
      const keys = across ? { ArrowDown: 1, ArrowUp: -1 } : { ArrowRight: 1, ArrowLeft: -1 };
      if (!(e.key in keys)) return;
      e.preventDefault();
      e.stopPropagation();
      const sign = t === 180 || t === 270 ? -keys[e.key] : keys[e.key];
      spec.guias[gi] = Math.round(clamp(spec.guias[gi] + sign * (e.shiftKey ? 0.01 : 0.002)) * 10000) / 10000;
      place(node);
      tb.onMove?.(true, { refocus: gi });
    });
    return node;
  }

  function revealBox(p, b, color) {
    const page = pageOf(p);
    if (!page) return;
    fillPage(page);
    const top = page.offsetTop + b[1] * page.offsetHeight - scroller.clientHeight / 2 + 40;
    const left = page.offsetLeft + ((b[0] + b[2]) / 2) * page.offsetWidth - scroller.clientWidth / 2;
    scroller.scrollTo({ top, left, behavior: reduced() ? 'auto' : 'smooth' });
    if (color) {
      const pulse = h('div', { class: 'pv-mark pulse show', style: { ...boxStyle(b), '--c': color } });
      page.querySelector('.pv-marks')?.append(pulse);
      setTimeout(() => pulse.remove(), 2400);
    }
  }

  // ---------------------------------------------------------- interface pública
  return {
    el,
    focus: () => scroller.focus({ preventScroll: true }),
    get info() { return V.info; },
    get doc() { return V.doc; },
    load(sourceId, doc, info) {
      V.sourceId = sourceId;
      V.doc = doc;
      V.info = info;
      V.sel = new Set();
      V.anchor = V.cursor = null;
      V.current = 0;
      V.hits = [];
      hitLabel.textContent = '';
      search.value = '';
      buildOrder(info.words || []);
      scroller.scrollTo(0, 0);
      drawPages();
      drawPageLabel();
      if (!thumbs.hidden) drawThumbs();
    },
    setMarks(model) {
      V.marks = model;
      pagesEl.querySelectorAll('.pv-page[data-filled]').forEach((page) => drawMarksOn(+page.dataset.page));
    },
    focusOwner(owner) {
      pagesEl.querySelectorAll('.pv-mark, .pv-region').forEach((m) => {
        m.classList.toggle('dim', owner !== null && m.dataset.owner !== owner);
        m.classList.toggle('focus', owner !== null && m.dataset.owner === owner);
      });
    },
    pulseOwner(owner) {
      pagesEl.querySelectorAll(`.pv-mark[data-owner="${CSS.escape(owner)}"]`).forEach((m) => {
        m.classList.add('born');
        setTimeout(() => m.classList.remove('born'), 2500);
      });
    },
    reveal(origem, color) {
      if (!origem?.length) return;
      document.body.dataset.pdfGesture = 'origem';
      revealBox(origem[0].p, origem[0].b, color);
      for (const part of origem.slice(1)) {
        const page = pageOf(part.p);
        if (!page) continue;
        fillPage(page);
        const pulse = h('div', { class: 'pv-mark pulse show', style: { ...boxStyle(part.b), '--c': color } });
        page.querySelector('.pv-marks')?.append(pulse);
        setTimeout(() => pulse.remove(), 2400);
      }
      live.textContent = `De onde veio: página ${origem[0].p + 1}.`;
    },
    selection: selectedWords,
    selectionText: selectedText,
    selectionLines: selectedLines,
    selectionRect,
    clearSelection() { V.anchor = V.cursor = null; setSelection(new Set()); },
    refreshAction: renderAction,
    announce(text) { live.textContent = text; },
    pageAngle: (p) => V.info?.pages?.[p]?.t || 0,
  };
}
