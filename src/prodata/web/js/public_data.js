// Dados públicos do Brasil (spec 049, RF-4901..4905, RF-4936, RF-4939): o catálogo dentro do programa.
// Menu de categorias e portais à esquerda, busca no topo, cartões no meio e o detalhe da fonte à direita.
// Abrir o catálogo é o que permite ao programa acessar a internet por conta própria (constituição 1.8.1).

import { api } from './api.js';
import { button, debounce, h } from './dom.js';
import { icon } from './icons.js';
import { publicDetail } from './public_data_detail.js';
import { openDialog, toastError } from './ui.js';

const AGENCY_NAMES = { bcb: 'Banco Central', ibge: 'IBGE', ipea: 'Ipeadata', tesouro: 'Tesouro Nacional',
  comex: 'Comex Stat', receita: 'Receita Federal', calendario: 'Calendário' };
const SPECIALS = [
  { id: 'destaques', nome: 'Destaques', icone: 'star' },
  { id: 'favoritos', nome: 'Favoritos', icone: 'star' },
  { id: 'recentes', nome: 'Recentes', icone: 'clock' },
];
const SPHERES = { federal: 'Federais', estadual: 'Estaduais', municipal: 'Municipais' };

const state = {
  overview: null,
  // O que está escolhido no menu: { kind: 'especial' | 'categoria' | 'portal', id }
  section: { kind: 'especial', id: 'destaques' },
  query: '',
  results: [],
  selected: null,
  loading: false,
  ticket: 0,
  detailEl: null,
  detailFor: null,
  // Adicionar ao fluxo / à vista Dados: ligado pela caixa Dados públicos (T12).
  onUse: null,
  dialog: null,
  poll: null,
  favorites: new Set(),
};

const number = (n) => Number(n || 0).toLocaleString('pt-BR');

function when(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const days = Math.round((new Date(new Date().toDateString()) - new Date(d.toDateString())) / 86400000);
  if (days === 0) return `hoje, ${d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}`;
  if (days === 1) return 'ontem';
  return d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

function agencyName(id) {
  return AGENCY_NAMES[id] || state.overview?.portais.find((p) => p.id === id)?.nome || id;
}

function categoryIcon(entry) {
  if (entry.categoria) return state.overview?.categorias.find((c) => c.id === entry.categoria)?.icone || 'chart';
  if (entry.id.startsWith('ipea/')) return 'chart';
  if (entry.id.startsWith('ckan/')) return 'globe';
  return 'chart';
}

// ------------------------------------------------------------------ dados

async function loadOverview() {
  state.overview = await api.publicOverview();
  return state.overview;
}

async function search() {
  const { kind, id } = state.section;
  const params = { q: state.query, limite: 200 };
  if (kind === 'especial') params.especial = id;
  if (kind === 'categoria') params.categoria = id;
  if (kind === 'portal') params.orgao = id;
  // Só a busca mais recente vale: uma resposta atrasada de antes não sobrescreve a nova.
  const ticket = ++state.ticket;
  state.loading = true;
  draw();
  let rows = [];
  try {
    rows = (await api.publicSearch(params)).resultados;
  } catch (err) {
    if (ticket === state.ticket) toastError(err, 'Não foi possível buscar no catálogo');
  }
  if (ticket !== state.ticket) return;
  state.results = rows;
  state.loading = false;
  draw();
}

const searchSoon = debounce(search, 220);

/** Atualiza em segundo plano e acompanha o progresso por órgão (RF-4933). */
async function startRefresh() {
  try {
    await api.publicRefresh();
  } catch (err) {
    toastError(err, 'Não foi possível atualizar o catálogo');
    return;
  }
  followRefresh();
}

function followRefresh() {
  clearInterval(state.poll);
  state.poll = setInterval(async () => {
    if (!state.dialog) { clearInterval(state.poll); return; }
    let status;
    try {
      status = await api.publicRefreshStatus();
    } catch {
      return;
    }
    state.overview = { ...state.overview, atualizacao: status };
    if (!status.rodando) {
      clearInterval(state.poll);
      await loadOverview();
      await search();
      return;
    }
    draw();
  }, 900);
}

async function toggleFavorite(entry, e) {
  e.stopPropagation();
  try {
    const { favorita } = await api.publicFavorite(entry.id);
    if (favorita) state.favorites.add(entry.id); else state.favorites.delete(entry.id);
    state.overview.favoritos += favorita ? 1 : -1;
    if (state.section.id === 'favoritos') await search(); else draw();
  } catch (err) {
    toastError(err, 'Não foi possível marcar a favorita');
  }
}

// ------------------------------------------------------------------ desenho

function menuItem({ kind, id, nome, icone, quantidade, aviso }) {
  const active = state.section.kind === kind && state.section.id === id;
  return h('button', {
    class: `pd-menu-item${active ? ' is-active' : ''}`, type: 'button', 'aria-current': active ? 'true' : null,
    title: aviso || null,
    // Os cartões da seção anterior saem na hora: nada de mostrar o de outra seção enquanto esta carrega.
    onclick: () => { state.section = { kind, id }; state.selected = null; state.results = []; search(); },
  },
  icon(icone, 16),
  h('span', { class: 'pd-menu-name' }, nome),
  aviso ? h('span', { class: 'pd-menu-warn', 'aria-label': aviso }, icon('alert', 12)) : null,
  quantidade !== undefined ? h('span', { class: 'pd-menu-count' }, number(quantidade)) : null);
}

function menu() {
  const o = state.overview;
  const specials = SPECIALS.map((s) => menuItem({ kind: 'especial', ...s,
    quantidade: s.id === 'destaques' ? o.destaques : s.id === 'favoritos' ? o.favoritos : o.recentes }));
  const categories = o.categorias.map((c) => menuItem({ kind: 'categoria', ...c }));
  const groups = Object.entries(SPHERES).map(([sphere, title]) => {
    const rows = o.portais.filter((p) => p.esfera === sphere);
    return h('div', { class: 'pd-menu-group' },
      h('span', { class: 'pd-menu-sub' }, title),
      rows.map((p) => menuItem({ kind: 'portal', id: p.id, nome: p.nome.replace(/^Dados abertos d[aoe]s? /, ''),
        icone: 'globe', quantidade: p.quantidade || undefined, aviso: p.erro || p.aviso || '' })));
  });
  return h('nav', { class: 'pd-menu', 'aria-label': 'Categorias e portais' },
    specials, h('hr'), h('span', { class: 'pd-menu-title' }, 'Categorias'), categories,
    h('hr'), h('span', { class: 'pd-menu-title' }, 'Portais de dados abertos'), groups);
}

function badge(entry) {
  return entry.destaque
    ? h('span', { class: 'pd-badge pd-badge-ready', title: 'Conferida uma a uma, com as colunas explicadas' }, icon('check', 11), 'Pronto')
    : h('span', { class: 'pd-badge pd-badge-auto', title: 'Leitura automática: confira a prévia antes de usar' }, 'Leitura automática');
}

function card(entry) {
  const favorite = state.favorites.has(entry.id);
  // Dentro de um portal, o nome dele em cada cartão é ruído: fica só o que diferencia (o grupo, quando difere).
  const inPortal = state.section.kind === 'portal' && state.section.id === entry.orgao;
  const portalOrg = state.overview.portais.find((p) => p.id === entry.orgao)?.orgao || '';
  const group = entry.grupo && !entry.destaque && !portalOrg.startsWith(entry.grupo) ? entry.grupo : null;
  const meta = [inPortal ? null : agencyName(entry.orgao), entry.periodicidade, group].filter(Boolean).join(' · ');
  const updated = entry.atualizado ? `atualizado em ${when(entry.atualizado)}` : entry.direto ? 'confere ao abrir' : '';
  return h('article', {
    class: `pd-card${state.selected?.id === entry.id ? ' is-selected' : ''}`, tabindex: '0', role: 'button',
    'aria-label': entry.nome,
    onclick: () => select(entry),
    onkeydown: (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(entry); } },
  },
  h('div', { class: 'pd-card-head' },
    h('span', { class: 'pd-card-icon' }, icon(categoryIcon(entry), 18)),
    h('div', { class: 'pd-card-title' }, h('h3', {}, entry.nome), h('p', { class: 'pd-card-meta' }, meta)),
    h('button', { class: `pd-star${favorite ? ' is-on' : ''}`, type: 'button', title: favorite ? 'Tirar das favoritas' : 'Marcar como favorita',
      'aria-pressed': favorite ? 'true' : 'false', onclick: (e) => toggleFavorite(entry, e) }, icon('star', 15))),
  entry.resumo ? h('p', { class: 'pd-card-summary' }, entry.resumo) : null,
  h('div', { class: 'pd-card-foot' }, badge(entry), updated ? h('span', { class: 'pd-card-date' }, updated) : null));
}

function select(entry) {
  state.selected = entry;
  api.publicRecent(entry.id).then(() => { state.overview.recentes = Math.min(20, state.overview.recentes + 1); }).catch(() => {});
  draw();
}

function sectionTitle() {
  const { kind, id } = state.section;
  if (kind === 'especial') return SPECIALS.find((s) => s.id === id).nome;
  if (kind === 'categoria') return state.overview.categorias.find((c) => c.id === id)?.nome || id;
  return state.overview.portais.find((p) => p.id === id)?.nome || id;
}

function emptyState() {
  const { kind, id } = state.section;
  if (state.query) return ['Nada encontrado', `Nenhuma fonte com "${state.query}" aqui. Tente outra palavra ou procure em Destaques.`];
  if (id === 'favoritos') return ['Nenhuma favorita ainda', 'Marque a estrela de uma fonte para ela aparecer aqui.'];
  if (id === 'recentes') return ['Nada aberto ainda', 'As fontes que você abrir aparecem aqui.'];
  if (kind === 'portal' || id === 'series') return ['Catálogo ainda não lido', 'Use Atualizar o catálogo para ler a lista deste portal direto da fonte.'];
  return ['Nada aqui', ''];
}

function results() {
  const portal = state.section.kind === 'portal' ? state.overview.portais.find((p) => p.id === state.section.id) : null;
  const head = h('div', { class: 'pd-results-head' },
    h('h2', {}, sectionTitle()),
    h('span', { class: 'pd-results-count' }, state.loading ? 'buscando…' : `${number(state.results.length)} fonte(s)`),
    portal?.erro ? h('p', { class: 'pd-note pd-note-err' }, icon('alert', 13), ` ${portal.erro} Mostrando o catálogo lido em ${when(portal.lido_em) || 'nenhuma data'}.`) : null,
    portal?.aviso ? h('p', { class: 'pd-note' }, icon('info', 13), ` ${portal.aviso}`) : null,
    portal?.nota ? h('p', { class: 'pd-note' }, portal.nota) : null);
  if (!state.loading && !state.results.length) {
    const [title, text] = emptyState();
    return h('section', { class: 'pd-results' }, head,
      h('div', { class: 'pd-empty' }, icon('search', 28), h('strong', {}, title), h('p', {}, text)));
  }
  return h('section', { class: 'pd-results', 'aria-busy': state.loading ? 'true' : 'false' }, head,
    h('div', { class: 'pd-grid' }, state.results.map(card)));
}

function detail() {
  const e = state.selected;
  if (!e) {
    return h('aside', { class: 'pd-detail pd-detail-empty' },
      icon('table', 30), h('strong', {}, 'Escolha uma fonte'),
      h('p', {}, 'O detalhe mostra o período, a última atualização, as colunas explicadas, a prévia e como citar.'));
  }
  // O mesmo elemento enquanto a fonte não muda: redesenhar o painel não recarrega o detalhe nem perde as escolhas.
  if (!state.detailEl || state.detailFor !== e.id) {
    state.detailEl = publicDetail(e, { iconFor: categoryIcon, agencyName, onUse: state.onUse });
    state.detailFor = e.id;
  }
  return state.detailEl;
}

function refreshBar() {
  const o = state.overview;
  const job = o.atualizacao || {};
  if (job.rodando) {
    const parts = Object.entries(job.orgaos || {}).map(([id, s]) => {
      const label = agencyName(id).replace(/^Dados abertos d[aoe]s? /, '');
      if (s === 'esperando') return null;
      if (s === 'lendo') return h('span', { class: 'pd-job is-running' }, `${label}: lendo…`);
      if (s === 'erro') return h('span', { class: 'pd-job is-err' }, `${label}: fora do ar`);
      return h('span', { class: 'pd-job is-done' }, `${label}: ${number(s)}`);
    }).filter(Boolean);
    return h('div', { class: 'pd-refresh', role: 'status' }, icon('refresh', 13, 'spin'), ' Lendo os catálogos direto dos órgãos… ', parts);
  }
  const read = o.lido_em ? `catálogo lido ${when(o.lido_em)}` : 'catálogo dos órgãos ainda não lido: os destaques já funcionam';
  return h('div', { class: 'pd-refresh' }, h('span', {}, read));
}

function draw() {
  if (!state.dialog || !state.overview) return;
  const body = state.dialog.el.querySelector('.pd-root');
  const scroll = body.querySelector('.pd-results')?.scrollTop || 0;
  const input = body.querySelector('.pd-search input');
  const hadFocus = document.activeElement === input;
  const caret = input?.selectionStart;
  body.replaceChildren(
    h('div', { class: 'pd-top' },
      h('label', { class: 'pd-search' }, icon('search', 16),
        h('input', { type: 'search', class: 'input', placeholder: 'Buscar: selic, ipca, municípios, 432, CNPJ…', 'aria-label': 'Buscar no catálogo',
          value: state.query, oninput: (e) => { state.query = e.target.value; searchSoon(); } })),
      refreshBar(),
      button({ icon: 'refresh', label: 'Atualizar o catálogo', disabled: Boolean(state.overview.atualizacao?.rodando), onClick: startRefresh })),
    h('div', { class: 'pd-columns' }, menu(), results(), detail()));
  const fresh = body.querySelector('.pd-results');
  if (fresh) fresh.scrollTop = scroll;
  if (hadFocus) {
    const next = body.querySelector('.pd-search input');
    next.focus();
    next.setSelectionRange(caret, caret);
  }
}

/** Abre o catálogo. Com o catálogo dos órgãos velho (mais de 7 dias) ou nunca lido, atualiza sozinho em segundo plano. */
export async function openPublicData() {
  const root = h('div', { class: 'pd-root' }, h('p', { class: 'pd-loading' }, 'Abrindo o catálogo…'));
  state.dialog = openDialog({
    title: 'Dados públicos do Brasil', body: root, size: 'xl',
    onClose: () => { clearInterval(state.poll); state.dialog = null; state.detailEl = null; state.detailFor = null; },
  });
  state.dialog.el.classList.add('pd-dialog');
  try {
    await loadOverview();
    const favs = await api.publicSearch({ especial: 'favoritos', limite: 500 });
    state.favorites = new Set(favs.resultados.map((r) => r.id));
  } catch (err) {
    toastError(err, 'Não foi possível abrir o catálogo');
    state.dialog.close();
    return;
  }
  await search();
  if (state.overview.atualizacao?.rodando) followRefresh();
  else if (state.overview.desatualizado) startRefresh();
}
