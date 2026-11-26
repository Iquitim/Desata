// Lugares no catálogo (spec 049, RF-4949, RF-4950, RF-4958, RF-4965, RF-4966): o painel de um estado ou município,
// os cartões de lugar na busca e a lista Demais municípios. Os três caminhos (mapa, busca e menu) levam ao mesmo
// painel, e nada é lido da internet até a pessoa escolher uma fonte.

import { api } from './api.js';
import { openLink } from './desktop.js';
import { button, debounce, h } from './dom.js';
import { icon } from './icons.js';
import { SITUATION, tone } from './public_map.js';
import { toastError } from './ui.js';

const number = (n) => Number(n || 0).toLocaleString('pt-BR');
const checkedOn = (iso) => (iso ? iso.split('-').reverse().join('/') : '');

/**
 * Situação ao vivo de um lugar que lê direto: o portal pode ter recusado o programa ou ficado fora do ar desde a
 * conferência. ``portalState(id)`` devolve a linha do portal na visão geral ({ quantidade, erro }).
 */
export function liveSituation(place, portalState) {
  if (place.situacao !== 'le_direto' || !place.portal) return { situacao: place.situacao, motivo: place.motivo };
  const p = portalState(place.portal);
  if (p?.erro) return { situacao: /recusou o programa/.test(p.erro) ? 'bloqueia' : 'fora_do_ar', motivo: p.erro };
  return { situacao: 'le_direto', motivo: '', quantidade: p?.quantidade || 0 };
}

function pill(situacao) {
  return h('span', { class: `pd-place-pill pd-tone-${tone(situacao)}` }, SITUATION[situacao] || situacao);
}

/** Um portal (do estado, da capital ou de uma prefeitura), com a situação, o motivo e o que dá para fazer. */
function portalBlock(title, row, ctx) {
  if (!row) return null;
  const live = liveSituation(row, ctx.portalState);
  const actions = [];
  if (row.portal && live.situacao === 'le_direto') {
    actions.push(button({ icon: 'globe', label: `Ver conjuntos${live.quantidade ? ` (${number(live.quantidade)})` : ''}`, size: 'sm', variant: 'primary',
      onClick: () => ctx.onPortal(row.portal) }));
  }
  const page = row.pagina || (row.portal ? ctx.portalPage(row.portal) : '');
  if (page && live.situacao !== 'le_direto') actions.push(button({ icon: 'link', label: 'Abrir no navegador', size: 'sm', onClick: () => openLink(page) }));
  return h('div', { class: 'pd-place-portal' },
    h('div', { class: 'pd-place-portal-head' }, h('span', { class: 'pd-place-portal-title' }, title), pill(live.situacao)),
    live.motivo ? h('p', { class: 'pd-place-why' }, live.motivo) : null,
    row.situacao !== 'le_direto' && row.conferido ? h('p', { class: 'pd-place-when' }, `Conferido em ${checkedOn(row.conferido)}.`) : null,
    actions.length ? h('div', { class: 'pd-place-actions' }, actions) : null);
}

function sourceList(title, sources, ctx) {
  return h('section', { class: 'pd-place-sources' },
    h('h3', {}, title),
    h('p', { class: 'pd-note' }, 'Fontes federais já filtradas por este lugar: abra uma para ver o detalhe, a prévia e adicionar.'),
    h('div', { class: 'pd-place-source-list' }, sources.map((f) => h('button', {
      type: 'button', class: 'pd-place-source', onclick: () => ctx.onSource(f),
    }, icon('table', 15), h('span', {}, f.nome), f.nota ? h('small', {}, f.nota) : null))));
}

/** Buscar um município do estado: a lista vem do programa (IBGE), filtrada aqui mesmo. */
function municipalityFinder(uf, ctx) {
  const list = h('ul', { class: 'pd-place-mun-list' });
  const input = h('input', { type: 'search', class: 'input', placeholder: 'Buscar um município do estado…', 'aria-label': 'Buscar um município do estado' });
  let rows = [];
  const show = () => {
    const q = input.value.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
    const hits = rows.filter((r) => !q || r.chave.includes(q)).slice(0, q ? 60 : 12);
    list.replaceChildren(...hits.map((r) => h('li', {}, h('button', { type: 'button', class: 'pd-place-mun', onclick: () => ctx.onPlace(r.id) },
      r.nome, r.portal ? h('span', { class: 'pd-place-pill pd-tone-ok' }, 'portal próprio') : null))));
  };
  input.addEventListener('input', debounce(show, 120));
  api.publicMunicipalities(uf).then((data) => {
    rows = data.municipios.map((m) => ({ ...m, chave: m.nome.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase() }));
    show();
  }).catch((err) => toastError(err, 'Não foi possível listar os municípios'));
  return h('section', { class: 'pd-place-finder' }, h('h3', {}, 'Outros municípios'), input, list);
}

/** O painel de um lugar (``detail``: resposta de /api/catalogo/lugar). */
export function placePanel(detail, ctx) {
  const state = detail.esfera === 'estadual';
  const head = h('div', { class: 'pd-place-head' },
    ctx.back ? button({ icon: 'undo', label: ctx.back.label, size: 'sm', variant: 'ghost', onClick: ctx.back.go }) : null,
    h('h2', {}, detail.nome, h('span', { class: 'pd-place-uf' }, state ? detail.uf : `${detail.uf} · ${detail.estado}`)));
  if (state) {
    return h('section', { class: 'pd-results pd-place' }, head,
      h('div', { class: 'pd-place-portals' },
        portalBlock('Portal do estado', detail.portal_estado, ctx),
        portalBlock(`Prefeitura de ${detail.capital.nome} (capital)`, detail.capital, ctx),
        detail.prefeituras.map((p) => portalBlock(`Prefeitura de ${p.nome}`, p, ctx))),
      sourceList(`Dados de ${detail.nome}`, detail.fontes, ctx),
      municipalityFinder(detail.uf, ctx));
  }
  return h('section', { class: 'pd-results pd-place' }, head,
    h('div', { class: 'pd-place-portals' }, detail.portal
      ? portalBlock(`Prefeitura de ${detail.nome}`, detail.portal, ctx)
      : h('p', { class: 'pd-note' }, icon('info', 13), ' A prefeitura não tem portal de dados abertos conferido. As fontes federais abaixo trazem os dados do município.')),
    sourceList(`Dados de ${detail.nome}`, detail.fontes, ctx),
    button({ icon: 'map', label: `Ver ${detail.estado}`, size: 'sm', variant: 'ghost', onClick: () => ctx.onPlace(`est:${detail.id.slice(4, 6)}`) }));
}

/** Os lugares achados pela busca, antes das fontes (RF-4965). */
export function placeCards(places, onPick) {
  if (!places?.length) return null;
  return h('div', { class: 'pd-place-cards' },
    h('h3', { class: 'pd-results-sub' }, 'Lugares'),
    h('div', { class: 'pd-place-card-row' }, places.map((p) => h('button', {
      type: 'button', class: 'pd-place-card', onclick: () => onPick(p.id),
    }, icon(p.esfera === 'estadual' ? 'map' : 'building', 16),
    h('span', {}, h('b', {}, p.esfera === 'estadual' ? p.nome : `${p.nome} (${p.uf})`), h('small', {}, p.resumo))))));
}

/** Demais municípios (RF-4966): os estados em ordem, cada um abre a lista dele, com os de portal próprio no topo. */
export function othersList(states, ctx) {
  const filter = h('input', { type: 'search', class: 'input', placeholder: 'Filtrar os estados…', 'aria-label': 'Filtrar os estados' });
  const groups = [...states].sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR')).map((s) => {
    const box = h('ul', { class: 'pd-place-mun-list' });
    const details = h('details', { class: 'pd-others-state', dataset: { nome: s.nome.toLowerCase() } },
      h('summary', {}, h('b', {}, s.uf), ' ', s.nome), box);
    details.addEventListener('toggle', () => {
      if (!details.open || box.childElementCount) return;
      box.append(h('li', { class: 'pd-note' }, 'carregando…'));
      api.publicMunicipalities(s.uf).then((data) => {
        box.replaceChildren(...data.municipios.map((m) => h('li', {}, h('button', { type: 'button', class: 'pd-place-mun', onclick: () => ctx.onPlace(m.id) },
          m.nome, m.portal ? h('span', { class: 'pd-place-pill pd-tone-ok' }, 'portal próprio') : null))));
      }).catch((err) => toastError(err, 'Não foi possível listar os municípios'));
    });
    return details;
  });
  filter.addEventListener('input', () => {
    const q = filter.value.toLowerCase().trim();
    for (const g of groups) g.hidden = Boolean(q) && !g.dataset.nome.includes(q);
  });
  return h('section', { class: 'pd-results pd-others' },
    h('div', { class: 'pd-results-head' }, h('h2', {}, 'Demais municípios'),
      h('p', { class: 'pd-note' }, 'As capitais estão em Municipais. Para achar um município direto, digite o nome na busca do topo.')),
    filter, h('div', { class: 'pd-others-list' }, groups));
}
