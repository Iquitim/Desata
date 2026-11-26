// Mapa do Brasil no catálogo (spec 049, RF-4958): os 27 estados coloridos pela situação do portal estadual.
// O desenho vem da malha do IBGE, simplificado por scripts/gerar_mapa_brasil.py e guardado no programa: abrir o
// mapa não usa internet. A mesma lista vai em botões, para quem navega pelo teclado.

import { ESTADOS, VIEWBOX } from './brasil_mapa.js';
import { h } from './dom.js';

const SVG = 'http://www.w3.org/2000/svg';

export const SITUATION = {
  le_direto: 'Lê direto',
  bloqueia: 'Bloqueia leitura automática',
  outra_plataforma: 'Outra plataforma',
  fora_do_ar: 'Fora do ar',
  sem_dados: 'Sem dados para ler',
  sem_portal: 'Sem portal encontrado',
};

/** Três tons no mapa: lê direto, existe portal mas o programa não lê agora, nenhum portal. */
export function tone(situacao) {
  if (situacao === 'le_direto') return 'ok';
  if (situacao === 'sem_portal') return 'none';
  return 'partial';
}

function svg(tag, attrs = {}, ...children) {
  const el = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) if (v !== null && v !== undefined) el.setAttribute(k, v);
  el.append(...children.flat().filter(Boolean));
  return el;
}

/**
 * ``states``: os 27 lugares estaduais (com ``situacao`` e ``motivo`` já com a situação ao vivo do portal);
 * ``onPick(place)``: abre o painel do estado.
 */
export function brazilMap(states, { onPick }) {
  const byCode = new Map(states.map((s) => [s.ibge, s]));
  const tip = h('div', { class: 'pd-map-tip', hidden: true });
  const paths = Object.entries(ESTADOS).map(([code, d]) => {
    const s = byCode.get(code);
    if (!s) return null;
    const label = `${s.nome} · ${SITUATION[s.situacao] || ''}`;
    const path = svg('path', { d, class: `pd-uf pd-tone-${tone(s.situacao)}`, 'data-uf': s.uf }, svg('title', {}, label));
    path.addEventListener('click', () => onPick(s));
    path.addEventListener('mousemove', (e) => {
      const box = e.currentTarget.ownerSVGElement.parentElement.getBoundingClientRect();
      tip.hidden = false;
      tip.textContent = label;
      tip.style.left = `${e.clientX - box.left + 12}px`;
      tip.style.top = `${e.clientY - box.top + 12}px`;
    });
    path.addEventListener('mouseleave', () => { tip.hidden = true; });
    return path;
  });
  const legend = h('div', { class: 'pd-map-legend' },
    [['ok', 'O programa lê o portal do estado'], ['partial', 'Há portal, mas o programa não lê agora'], ['none', 'Nenhum portal encontrado']]
      .map(([t, text]) => h('span', {}, h('i', { class: `pd-map-swatch pd-tone-${t}` }), text)));
  const keys = h('div', { class: 'pd-map-keys', role: 'list', 'aria-label': 'Estados' },
    [...states].sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR')).map((s) => h('button', {
      type: 'button', class: `pd-map-key pd-tone-${tone(s.situacao)}`, role: 'listitem',
      title: `${s.nome}: ${SITUATION[s.situacao] || ''}${s.motivo ? ` — ${s.motivo}` : ''}`,
      onclick: () => onPick(s),
    }, h('b', {}, s.uf), ' ', s.nome)));
  return h('div', { class: 'pd-map' },
    h('p', { class: 'pd-note' }, 'Clique num estado para ver o portal dele, o da capital, as outras prefeituras com portal e os dados federais do estado e de cada município.'),
    h('div', { class: 'pd-map-canvas' }, svg('svg', { viewBox: VIEWBOX, class: 'pd-map-svg', role: 'img', 'aria-label': 'Mapa do Brasil por estado' }, paths), tip),
    legend, keys);
}
