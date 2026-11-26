// Organizar: galeria de layouts prontos, desenhados com os visuais do próprio dashboard.

import { api } from './api.js';
import { PAGE_W, hintFor, pageHeight, rectOf } from './dash_model.js';
import { commitLayout, dash, page, ui } from './dash_state.js';
import { h } from './dom.js';
import { openDialog, toast, toastError } from './ui.js';

const TEMPLATE_INFO = {
  auto: ['Automático', 'Tamanho pelo tipo de visual, na ordem atual, sem buracos'],
  'kpis-top-2': ['KPIs no topo + 2 colunas', 'Indicadores em faixa, gráficos lado a lado'],
  'kpis-top-3': ['KPIs no topo + 3 colunas', 'Mais visuais por linha, para telas largas'],
  highlight: ['Destaque', 'Um gráfico grande e os demais ao lado'],
  'kpis-side': ['KPIs na lateral', 'Indicadores em coluna à esquerda'],
  report: ['Relatório', 'Um visual por linha, em largura total'],
};

/**
 * A galeria. Com visuais selecionados, a pessoa escolhe arrumar todos ou só os selecionados: um clique num visual
 * antes de abrir não muda o resultado sem avisar (com um só selecionado, o padrão é arrumar todos).
 */
export async function openOrganize() {
  const d = dash();
  const visuals = d.items.filter((i) => i.kind === 'visual');
  const picked = visuals.filter((i) => ui.selected.has(i.id));
  if (!visuals.length) { toast('Adicione caixas de BI ao fluxo para organizar o dashboard.'); return; }
  let onlyPicked = picked.length >= 2;
  const grid = h('div', { class: 'organize-grid' });
  const help = h('p', { class: 'muted organize-help' });
  let close = () => {};
  const draw = async () => {
    const chosen = onlyPicked ? picked : visuals;
    const obstacles = d.items.filter((i) => !chosen.includes(i)).map(rectOf);
    help.textContent = onlyPicked
      ? `Arruma só os ${chosen.length} visuais selecionados. Textos, imagens, formas e os outros visuais ficam onde estão. Ctrl+Z desfaz.`
      : 'Arruma todos os visuais. Textos, imagens e formas ficam onde estão. Ctrl+Z desfaz.';
    grid.replaceChildren(h('p', { class: 'muted' }, 'Montando os layouts…'));
    let result;
    try {
      result = await api.arrangeDashboard({
        page: d.page,
        items: chosen.map((i) => ({ id: i.id, hint: hintFor(i.node_id), rect: rectOf(i) })),
        obstacles,
      });
    } catch (err) {
      toastError(err, 'Não foi possível organizar');
      return;
    }
    const kinds = Object.fromEntries(chosen.map((i) => [i.id, hintFor(i.node_id).kind]));
    grid.replaceChildren(...Object.entries(TEMPLATE_INFO).map(([key, [label, desc]]) => h('button', {
      type: 'button', class: 'organize-option',
      onclick: () => { close(); applyArrangement(result[key]); },
    }, thumbnail(result[key], obstacles, kinds), h('strong', {}, label), h('span', { class: 'muted' }, desc),
    result[key].grew ? h('span', { class: 'organize-warn' }, 'Não cabe: a página vira altura livre') : null)));
  };
  const scope = picked.length ? h('div', { class: 'segmented-field organize-scope', role: 'radiogroup', 'aria-label': 'O que organizar' },
    [[false, `Todos os visuais (${visuals.length})`], [true, `Só os selecionados (${picked.length})`]].map(([value, label]) => h('button', {
      type: 'button', role: 'radio', class: ['seg-btn', onlyPicked === value && 'on'], 'aria-checked': String(onlyPicked === value),
      onclick: (e) => {
        onlyPicked = value;
        for (const b of e.currentTarget.parentElement.children) { b.classList.toggle('on', b === e.currentTarget); b.setAttribute('aria-checked', String(b === e.currentTarget)); }
        draw();
      },
    }, label))) : null;
  ({ close } = openDialog({ title: 'Organizar o dashboard', size: 'lg', body: h('div', {}, scope, help, grid) }));
  await draw();
}

function thumbnail(arr, obstacles, kinds) {
  const H = pageHeight(arr.page);
  const ns = 'http://www.w3.org/2000/svg';
  const el = (tag, attrs) => {
    const n = document.createElementNS(ns, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    return n;
  };
  const svgEl = el('svg', { viewBox: `0 0 ${PAGE_W} ${H}`, class: 'organize-thumb', 'aria-hidden': 'true' });
  svgEl.append(el('rect', { class: 'thumb-page', x: 0, y: 0, width: PAGE_W, height: H }));
  for (const o of obstacles) svgEl.append(el('rect', { class: 'thumb-fixed', x: o.x, y: o.y, width: o.w, height: o.h, rx: 12 }));
  for (const [id, r] of Object.entries(arr.positions)) {
    svgEl.append(el('rect', { class: `thumb-${kinds[id]}`, x: r.x, y: r.y, width: r.w, height: r.h, rx: 12 }));
  }
  return svgEl;
}

function applyArrangement(arr) {
  commitLayout((d) => {
    for (const i of d.items) if (arr.positions[i.id]) Object.assign(i, arr.positions[i.id]);
    d.page = { ...arr.page };
  });
  if (arr.grew) toast('Os visuais não couberam na página: a altura passou a ser livre.');
}
