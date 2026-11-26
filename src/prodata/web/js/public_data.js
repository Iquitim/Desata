// Dados públicos do Brasil (spec 049, RF-4901..4905, RF-4936, RF-4939, RF-4949..4950, RF-4958..4959, RF-4965..4966).
// Menu à esquerda (categorias, mapa do Brasil, portais por esfera com todos os estados e capitais), busca no topo,
// cartões ou o painel de um lugar no meio e o detalhe da fonte à direita.
// Abrir o catálogo é o que permite ao programa acessar a internet por conta própria (constituição 1.8.1).
// A janela é montada uma vez e cada parte se atualiza no lugar: durante Atualizar o catálogo, só a barra de progresso
// e as contagens mudam, e a rolagem, o foco e o texto da busca ficam onde estão (RF-4959).

import { api } from './api.js';
import { button, debounce, h } from './dom.js';
import { icon } from './icons.js';
import { publicDetail } from './public_data_detail.js';
import { cardBadge, dot, worst } from './public_data_health.js';
import { brazilMap, SITUATION } from './public_map.js';
import { checkNews, refreshSaved } from './public_news.js';
import { liveSituation, othersList, placeCards, placePanel } from './public_places.js';
import { openDialog, toastError } from './ui.js';

const AGENCY_NAMES = { bcb: 'Banco Central', ibge: 'IBGE', ipea: 'Ipeadata', tesouro: 'Tesouro Nacional',
  comex: 'Comex Stat', receita: 'Receita Federal', calendario: 'Calendário' };
const SPECIALS = [
  { id: 'destaques', nome: 'Destaques', icone: 'star' },
  { id: 'favoritos', nome: 'Favoritos', icone: 'star' },
  { id: 'recentes', nome: 'Recentes', icone: 'clock' },
];

const state = {
  overview: null,
  // O que está escolhido no menu: { kind: 'especial' | 'categoria' | 'portal' | 'lugar' | 'mapa' | 'demais', id }
  section: { kind: 'especial', id: 'destaques' },
  query: '',
  results: [],
  places: [],
  placeDetail: null,
  placeBack: null,
  selected: null,
  loading: false,
  ticket: 0,
  detailEl: null,
  detailFor: null,
  // Adicionar ao fluxo / à vista Dados: ligado pela caixa Dados públicos (T12).
  onUse: null,
  // Situação dos órgãos (RF-4921): a última conferência, e a nova chega sem segurar a tela.
  health: null,
  checking: false,
  dialog: null,
  poll: null,
  favorites: new Set(),
  slots: null,
};

const number = (n) => Number(n || 0).toLocaleString('pt-BR');
const shortName = (nome) => nome.replace(/^Dados abertos d[aoe]s? /, '');

function when(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const days = Math.round((new Date(new Date().toDateString()) - new Date(d.toDateString())) / 86400000);
  if (days === 0) return `hoje, ${d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}`;
  if (days === 1) return 'ontem';
  return d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

const portalRow = (id) => state.overview?.portais.find((p) => p.id === id);

function agencyName(id) {
  return AGENCY_NAMES[id] || portalRow(id)?.nome || id;
}

function categoryIcon(entry) {
  if (entry.categoria) return state.overview?.categorias.find((c) => c.id === entry.categoria)?.icone || 'chart';
  if (entry.id.startsWith('ipea/')) return 'chart';
  if (entry.id.startsWith('ckan/')) return 'globe';
  return 'chart';
}

const places = (esfera) => state.overview.lugares.filter((p) => p.esfera === esfera && !p.mapa && (esfera === 'estadual' || p.capital));

// ------------------------------------------------------------------ dados

async function loadOverview() {
  state.overview = await api.publicOverview();
  return state.overview;
}

async function search() {
  const { kind, id } = state.section;
  if (!['especial', 'categoria', 'portal'].includes(kind)) { renderResults(); return; }
  const params = { q: state.query, limite: 200 };
  if (kind === 'especial') params.especial = id;
  if (kind === 'categoria') params.categoria = id;
  if (kind === 'portal') params.orgao = id;
  // Só a busca mais recente vale: uma resposta atrasada de antes não sobrescreve a nova.
  const ticket = ++state.ticket;
  state.loading = true;
  renderResults();
  let rows = [];
  let found = [];
  try {
    const answer = await api.publicSearch(params);
    rows = answer.resultados;
    found = answer.lugares || [];
  } catch (err) {
    if (ticket === state.ticket) toastError(err, 'Não foi possível buscar no catálogo');
  }
  if (ticket !== state.ticket) return;
  state.results = rows;
  state.places = found;
  state.loading = false;
  renderResults();
}

const searchSoon = debounce(search, 220);

function goTo(section) {
  state.section = section;
  state.selected = null;
  state.results = [];
  state.places = [];
  renderMenu();
  renderDetail();
  search();
}

/** Abre o painel de um estado ou município (do mapa, da busca, do menu ou de Demais municípios). */
async function openPlace(id, back = null) {
  state.placeBack = back || backFor(state.section);
  state.section = { kind: 'lugar', id };
  state.placeDetail = null;
  renderMenu();
  renderResults();
  try {
    state.placeDetail = await api.publicPlace(id);
  } catch (err) {
    toastError(err, 'Não foi possível abrir o lugar');
    return;
  }
  if (state.section.id === id) renderResults();
}

function backFor(section) {
  if (section.kind === 'mapa') return { label: 'Mapa do Brasil', go: () => goTo({ kind: 'mapa', id: 'mapa' }) };
  if (section.kind === 'demais') return { label: 'Demais municípios', go: () => goTo({ kind: 'demais', id: 'demais' }) };
  if (section.kind === 'lugar' && state.placeBack) return state.placeBack;
  if (state.query) return { label: 'Voltar à busca', go: () => goTo({ kind: 'especial', id: 'destaques' }) };
  return null;
}

/** Uma fonte federal filtrada pelo lugar: abre o detalhe com as escolhas já preenchidas. */
function openSourceFor(fonte) {
  state.initialChoices = { for: fonte.id, values: fonte.escolhas };
  state.selected = { id: fonte.id, nome: fonte.nome, orgao: '', servico: null };
  state.detailEl = null;
  renderDetail();
}

/** Atualiza em segundo plano e acompanha o progresso por órgão (RF-4933, RF-4959). */
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
      renderTop();
      patchMenu();
      if (['especial', 'categoria', 'portal'].includes(state.section.kind)) await search();
      return;
    }
    // Só a barra e as contagens: nada de redesenhar a janela enquanto a pessoa rola ou busca.
    renderTop();
    patchMenu(status.orgaos || {});
  }, 900);
}

/** Confere a situação dos órgãos (até 5 s, em paralelo). ``force``: Conferir de novo. */
async function checkHealth(force = false, services = null) {
  state.checking = true;
  renderTop();
  state.detailEl?.refreshHealth?.();
  try {
    state.health = await api.publicCheckHealth(force, services);
  } catch {
    // sem resposta do próprio programa: fica a última conferência
  }
  state.checking = false;
  renderTop();
  patchMenu();
  state.detailEl?.refreshHealth?.();
}

async function toggleFavorite(entry, e) {
  e.stopPropagation();
  try {
    const { favorita } = await api.publicFavorite(entry.id);
    if (favorita) state.favorites.add(entry.id); else state.favorites.delete(entry.id);
    state.overview.favoritos += favorita ? 1 : -1;
    patchMenu();
    if (state.section.id === 'favoritos') await search(); else renderResults();
  } catch (err) {
    toastError(err, 'Não foi possível marcar a favorita');
  }
}

// ------------------------------------------------------------------ menu

function menuItem({ kind, id, nome, icone, quantidade, aviso, situacao, key, onPick }) {
  const active = state.section.kind === kind && state.section.id === id;
  return h('button', {
    class: `pd-menu-item${active ? ' is-active' : ''}`, type: 'button', 'aria-current': active ? 'true' : null,
    title: aviso || null, dataset: { key: key || `${kind}:${id}` },
    // Os cartões da seção anterior saem na hora: nada de mostrar o de outra seção enquanto esta carrega.
    onclick: onPick || (() => goTo({ kind, id })),
  },
  icon(icone, 16),
  h('span', { class: 'pd-menu-name' }, nome),
  h('span', { class: 'pd-menu-dot' }, situacao && situacao !== 'nao_conferido' ? dot(situacao) : null),
  h('span', { class: 'pd-menu-warn', 'aria-label': aviso || null }, aviso ? icon('alert', 12) : null),
  h('span', { class: 'pd-menu-count' }, quantidade !== undefined ? number(quantidade) : ''));
}

/** Um estado ou capital: o portal quando lê direto; senão, o painel do lugar com o motivo. */
function placeItem(place) {
  const live = liveSituation(place, portalRow);
  const p = place.portal ? portalRow(place.portal) : null;
  if (place.situacao === 'le_direto' && p) {
    return menuItem({ kind: 'portal', id: p.id, nome: place.nome, icone: 'globe', key: `portal:${p.id}`,
      quantidade: p.quantidade || undefined, aviso: p.erro || p.aviso || '', situacao: worst(state.health, [p.servico]) });
  }
  return menuItem({ kind: 'lugar', id: place.id, nome: place.nome, icone: 'globe', key: `lugar:${place.id}`,
    aviso: `${SITUATION[live.situacao]}: ${live.motivo}`, onPick: () => openPlace(place.id, null) });
}

function menu() {
  const o = state.overview;
  const specials = SPECIALS.map((s) => menuItem({ kind: 'especial', ...s,
    quantidade: s.id === 'destaques' ? o.destaques : s.id === 'favoritos' ? o.favoritos : o.recentes }));
  const categories = o.categorias.map((c) => menuItem({ kind: 'categoria', ...c, situacao: worst(state.health, c.servicos) }));
  const federal = o.portais.filter((p) => p.esfera === 'federal').map((p) => menuItem({ kind: 'portal', id: p.id,
    nome: shortName(p.nome), icone: 'globe', quantidade: p.quantidade || undefined, aviso: p.erro || p.aviso || '',
    situacao: worst(state.health, [p.servico]) }));
  return h('nav', { class: 'pd-menu', 'aria-label': 'Categorias e portais' },
    specials, h('hr'), h('span', { class: 'pd-menu-title' }, 'Categorias'), categories,
    h('hr'), menuItem({ kind: 'mapa', id: 'mapa', nome: 'Mapa do Brasil', icone: 'map' }),
    h('hr'), h('span', { class: 'pd-menu-title' }, 'Portais de dados abertos'),
    h('div', { class: 'pd-menu-group' }, h('span', { class: 'pd-menu-sub' }, 'Federais'), federal),
    h('div', { class: 'pd-menu-group' }, h('span', { class: 'pd-menu-sub' }, 'Estaduais'), places('estadual').map(placeItem)),
    h('div', { class: 'pd-menu-group' }, h('span', { class: 'pd-menu-sub' }, 'Municipais (capitais)'), places('municipal').map(placeItem),
      menuItem({ kind: 'demais', id: 'demais', nome: 'Demais municípios', icone: 'building' })));
}

function renderMenu() {
  const slot = state.slots?.menu;
  if (!slot) return;
  const scroll = slot.firstChild?.scrollTop || 0;
  slot.replaceChildren(menu());
  slot.firstChild.scrollTop = scroll;
}

/**
 * Contagens, pontos e avisos do menu no lugar, sem recriar os botões (RF-4959). ``progress``: o que a atualização
 * em andamento já leu por órgão ({ id: número | 'lendo' | 'erro' | 'esperando' }).
 */
function patchMenu(progress = {}) {
  const nav = state.slots?.menu?.firstChild;
  if (!nav || !state.overview) return;
  const o = state.overview;
  const setCount = (key, value) => {
    const el = nav.querySelector(`[data-key="${CSS.escape(key)}"] .pd-menu-count`);
    if (el) el.textContent = value === undefined || value === '' ? '' : number(value);
  };
  setCount('especial:destaques', o.destaques);
  setCount('especial:favoritos', o.favoritos);
  setCount('especial:recentes', o.recentes);
  for (const p of o.portais) {
    const key = `portal:${p.id}`;
    const now = progress[p.id];
    const el = nav.querySelector(`[data-key="${CSS.escape(key)}"]`);
    if (!el) continue;
    if (typeof now === 'number' || /^\d+$/.test(String(now ?? ''))) setCount(key, Number(now));
    else if (now === 'lendo') el.querySelector('.pd-menu-count').textContent = '…';
    else setCount(key, p.quantidade || '');
    const sit = worst(state.health, [p.servico]);
    el.querySelector('.pd-menu-dot').replaceChildren(...(sit && sit !== 'nao_conferido' ? [dot(sit)] : []));
    const warn = now === 'erro' ? 'Não foi possível ler agora; o motivo aparece quando a atualização termina.' : (p.erro || p.aviso || '');
    el.title = warn;
    el.querySelector('.pd-menu-warn').replaceChildren(...(warn ? [icon('alert', 12)] : []));
  }
  for (const c of o.categorias) {
    const el = nav.querySelector(`[data-key="${CSS.escape(`categoria:${c.id}`)}"] .pd-menu-dot`);
    const sit = worst(state.health, c.servicos);
    if (el) el.replaceChildren(...(sit && sit !== 'nao_conferido' ? [dot(sit)] : []));
  }
}

// ------------------------------------------------------------------ meio: cartões, mapa, lugar

function badge(entry) {
  return entry.destaque
    ? h('span', { class: 'pd-badge pd-badge-ready', title: 'Conferida uma a uma, com as colunas explicadas' }, icon('check', 11), 'Pronto')
    : h('span', { class: 'pd-badge pd-badge-auto', title: 'Leitura automática: confira a prévia antes de usar' }, 'Leitura automática');
}

function card(entry) {
  const favorite = state.favorites.has(entry.id);
  // Dentro de um portal, o nome dele em cada cartão é ruído: fica só o que diferencia (o grupo, quando difere).
  const inPortal = state.section.kind === 'portal' && state.section.id === entry.orgao;
  const portalOrg = portalRow(entry.orgao)?.orgao || '';
  const group = entry.grupo && !entry.destaque && !portalOrg.startsWith(entry.grupo) ? entry.grupo : null;
  const meta = [inPortal ? null : agencyName(entry.orgao), entry.periodicidade, group].filter(Boolean).join(' · ');
  const updated = entry.atualizado ? `atualizado em ${when(entry.atualizado)}` : entry.direto ? 'confere ao abrir' : '';
  const health = state.health?.servicos?.[entry.servico];
  return h('article', {
    class: `pd-card${state.selected?.id === entry.id ? ' is-selected' : ''}${health?.situacao === 'fora' ? ' is-down' : ''}`, tabindex: '0', role: 'button',
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
  cardBadge(health),
  h('div', { class: 'pd-card-foot' }, badge(entry), updated ? h('span', { class: 'pd-card-date' }, updated) : null));
}

function select(entry) {
  state.selected = entry;
  state.initialChoices = null;
  api.publicRecent(entry.id).then(() => { state.overview.recentes = Math.min(20, state.overview.recentes + 1); patchMenu(); }).catch(() => {});
  for (const el of state.slots.results.querySelectorAll('.pd-card.is-selected')) el.classList.remove('is-selected');
  state.slots.results.querySelector(`.pd-card[aria-label="${CSS.escape(entry.nome)}"]`)?.classList.add('is-selected');
  renderDetail();
}

function sectionTitle() {
  const { kind, id } = state.section;
  if (kind === 'especial' && id === 'destaques' && state.query) return `Busca: “${state.query}”`;
  if (kind === 'especial') return SPECIALS.find((s) => s.id === id).nome;
  if (kind === 'categoria') return state.overview.categorias.find((c) => c.id === id)?.nome || id;
  return portalRow(id)?.nome || id;
}

function emptyState() {
  const { kind, id } = state.section;
  if (state.query) return ['Nada encontrado', `Nenhuma fonte com "${state.query}" aqui. Tente outra palavra ou procure em Destaques.`];
  if (id === 'favoritos') return ['Nenhuma favorita ainda', 'Marque a estrela de uma fonte para ela aparecer aqui.'];
  if (id === 'recentes') return ['Nada aberto ainda', 'As fontes que você abrir aparecem aqui.'];
  if (kind === 'portal' || id === 'series') return ['Catálogo ainda não lido', 'Use Atualizar o catálogo para ler a lista deste portal direto da fonte.'];
  return ['Nada aqui', ''];
}

function placeCtx() {
  return {
    back: state.placeBack,
    portalState: portalRow,
    portalPage: (id) => portalRow(id)?.pagina || '',
    onPortal: (id) => goTo({ kind: 'portal', id }),
    onSource: openSourceFor,
    onPlace: (pid) => openPlace(pid, state.placeBack),
  };
}

function sources() {
  const { kind } = state.section;
  if (kind === 'mapa') {
    const states = places('estadual').map((p) => ({ ...p, ...liveSituation(p, portalRow) }));
    return h('section', { class: 'pd-results' }, h('div', { class: 'pd-results-head' }, h('h2', {}, 'Mapa do Brasil')),
      brazilMap(states, { onPick: (s) => openPlace(s.id, backFor({ kind: 'mapa' })) }));
  }
  if (kind === 'demais') return othersList(places('estadual'), { onPlace: (pid) => openPlace(pid, backFor({ kind: 'demais' })) });
  if (kind === 'lugar') {
    if (!state.placeDetail) return h('section', { class: 'pd-results' }, h('p', { class: 'pd-loading' }, 'Abrindo o lugar…'));
    return placePanel(state.placeDetail, placeCtx());
  }
  const portal = kind === 'portal' ? portalRow(state.section.id) : null;
  const head = h('div', { class: 'pd-results-head' },
    h('h2', {}, sectionTitle()),
    h('span', { class: 'pd-results-count' }, state.loading ? 'buscando…' : `${number(state.results.length)} fonte(s)`),
    portal?.erro ? h('p', { class: 'pd-note pd-note-err' }, icon('alert', 13), ` ${portal.erro} Mostrando o catálogo lido em ${when(portal.lido_em) || 'nenhuma data'}.`) : null,
    portal?.aviso ? h('p', { class: 'pd-note' }, icon('info', 13), ` ${portal.aviso}`) : null,
    portal?.nota ? h('p', { class: 'pd-note' }, portal.nota) : null);
  const where = state.query ? placeCards(state.places, (pid) => openPlace(pid, { label: 'Voltar à busca', go: () => goTo({ kind: 'especial', id: 'destaques' }) })) : null;
  if (!state.loading && !state.results.length) {
    const [title, text] = emptyState();
    return h('section', { class: 'pd-results' }, head, where,
      where ? h('p', { class: 'pd-note' }, 'Nenhuma fonte com esse nome; os lugares acima levam aos dados de cada um.')
        : h('div', { class: 'pd-empty' }, icon('search', 28), h('strong', {}, title), h('p', {}, text)));
  }
  return h('section', { class: 'pd-results', 'aria-busy': state.loading ? 'true' : 'false' }, head, where,
    h('div', { class: 'pd-grid' }, state.results.map(card)));
}

function renderResults() {
  const slot = state.slots?.results;
  if (!slot || !state.overview) return;
  const keep = slot.firstChild?.dataset?.section === `${state.section.kind}:${state.section.id}`;
  const scroll = keep ? slot.firstChild.scrollTop : 0;
  const fresh = sources();
  fresh.dataset.section = `${state.section.kind}:${state.section.id}`;
  slot.replaceChildren(fresh);
  fresh.scrollTop = scroll;
}

// ------------------------------------------------------------------ detalhe e topo

function detail() {
  const e = state.selected;
  if (!e) {
    return h('aside', { class: 'pd-detail pd-detail-empty' },
      icon('table', 30), h('strong', {}, 'Escolha uma fonte'),
      h('p', {}, 'O detalhe mostra o período, a última atualização, as colunas explicadas, a prévia e como citar.'));
  }
  // O mesmo elemento enquanto a fonte não muda: redesenhar o painel não recarrega o detalhe nem perde as escolhas.
  if (!state.detailEl || state.detailFor !== e.id) {
    const initial = state.initialChoices?.for === e.id ? state.initialChoices.values : null;
    state.detailEl = publicDetail(e, {
      iconFor: categoryIcon, agencyName, initialChoices: initial,
      onUse: state.onUse ? (entry, escolhas, target, info) => {
        if (target === 'dados') state.onUseData?.(entry, escolhas, info);
        else state.onUse(entry, escolhas, target, info);
        state.dialog?.close();
      } : null,
      canUseData: Boolean(state.onUseData),
      useLabel: state.useLabel,
      health: (sid) => state.health?.servicos?.[sid] || null,
      offline: () => Boolean(state.health?.sem_conexao),
      checking: () => state.checking,
      recheck: (sid) => checkHealth(true, sid ? [sid] : null),
    });
    state.detailFor = e.id;
  }
  return state.detailEl;
}

function renderDetail() {
  const slot = state.slots?.detail;
  if (!slot) return;
  const next = detail();
  if (slot.firstChild !== next) slot.replaceChildren(next);
}

/** A faixa do topo: progresso da atualização (barra e contagem), ou a data do catálogo e a conferência. */
function refreshBar() {
  const o = state.overview;
  const job = o.atualizacao || {};
  if (job.rodando) {
    const all = Object.entries(job.orgaos || {});
    const done = all.filter(([, s]) => s !== 'esperando' && s !== 'lendo');
    const failed = done.filter(([, s]) => s === 'erro').map(([id]) => shortName(agencyName(id)));
    const reading = all.filter(([, s]) => s === 'lendo').map(([id]) => shortName(agencyName(id)));
    const pct = all.length ? Math.round((done.length / all.length) * 100) : 0;
    return h('div', { class: 'pd-refresh pd-refreshing', role: 'status' },
      h('span', {}, icon('refresh', 13, 'spin'), ` ${number(done.length)} de ${number(all.length)} catálogos lidos`),
      h('span', { class: 'pd-progress', 'aria-hidden': 'true' }, h('span', { style: { width: `${pct}%` } })),
      reading.length ? h('span', { class: 'pd-job is-running' }, `lendo: ${reading.slice(0, 3).join(', ')}${reading.length > 3 ? '…' : ''}`) : null,
      failed.length ? h('span', { class: 'pd-job is-err', title: 'O motivo aparece no menu quando a atualização termina.' }, `não leram: ${failed.join(', ')}`) : null);
  }
  const read = o.lido_em ? `catálogo lido ${when(o.lido_em)}` : 'catálogo dos órgãos ainda não lido: os destaques já funcionam';
  if (state.health?.sem_conexao) {
    // Sem internet não é órgão fora do ar (RF-4923): uma faixa só, sem acusar ninguém.
    return h('div', { class: 'pd-refresh pd-offline', role: 'status' }, icon('alert', 13),
      ` Sem conexão com a internet agora. A busca e o catálogo funcionam com o que foi lido${o.lido_em ? ` (${when(o.lido_em)})` : ''}.`);
  }
  return h('div', { class: 'pd-refresh' }, h('span', {}, read), state.checking ? h('span', { class: 'pd-job is-running' }, 'conferindo os órgãos…') : null);
}

function renderTop() {
  if (!state.slots) return;
  state.slots.bar.replaceChildren(refreshBar());
  state.slots.refreshButton.disabled = Boolean(state.overview.atualizacao?.rodando);
}

/** Monta a janela uma vez: busca, faixa, botão e as três colunas, cada uma com o seu lugar (RF-4959). */
function mount() {
  const body = state.dialog.el.querySelector('.pd-root');
  const input = h('input', { type: 'search', class: 'input', placeholder: 'Buscar: selic, ipca, Campinas, 432, CNPJ…', 'aria-label': 'Buscar no catálogo',
    value: state.query, oninput: (e) => {
      state.query = e.target.value;
      if (!['especial', 'categoria', 'portal'].includes(state.section.kind)) { state.section = { kind: 'especial', id: 'destaques' }; renderMenu(); }
      searchSoon();
    } });
  const refreshButton = button({ icon: 'refresh', label: 'Atualizar o catálogo', onClick: startRefresh });
  state.slots = {
    bar: h('div', { class: 'pd-bar-slot' }),
    refreshButton,
    menu: h('div', { class: 'pd-menu-slot' }),
    results: h('div', { class: 'pd-results-slot' }),
    detail: h('div', { class: 'pd-detail-slot' }),
  };
  body.replaceChildren(
    h('div', { class: 'pd-top' }, h('label', { class: 'pd-search' }, icon('search', 16), input), state.slots.bar, refreshButton),
    h('div', { class: 'pd-columns' }, state.slots.menu, state.slots.results, state.slots.detail));
  renderTop();
  renderMenu();
  renderResults();
  renderDetail();
}

/**
 * Abre o catálogo. Com o catálogo dos órgãos velho (mais de 7 dias) ou nunca lido, atualiza sozinho em segundo plano.
 * ``select``: já abre o detalhe dessa fonte (com ``choices``), como no Trocar da caixa. ``onUse(fonte, escolhas,
 * destino, info)``: o que o Adicionar faz; ``onUseData``: Adicionar à vista Dados (sem ele, o botão não aparece).
 */
export async function openPublicData({ select: chosen = null, choices = null, onUse = null, onUseData = null, useLabel = null } = {}) {
  state.useLabel = useLabel;
  state.onUse = onUse;
  state.onUseData = onUseData;
  state.initialChoices = choices && chosen ? { for: chosen.id, values: choices } : null;
  state.selected = chosen ? { id: chosen.id, nome: chosen.nome || chosen.id, orgao: chosen.orgao || '', servico: null } : null;
  state.detailEl = null;
  state.detailFor = null;
  state.slots = null;
  if (['lugar', 'mapa', 'demais'].includes(state.section.kind)) state.section = { kind: 'especial', id: 'destaques' };
  const root = h('div', { class: 'pd-root' }, h('p', { class: 'pd-loading' }, 'Abrindo o catálogo…'));
  state.dialog = openDialog({
    title: 'Dados públicos do Brasil', body: root, size: 'xl',
    onClose: () => { clearInterval(state.poll); state.dialog = null; state.detailEl = null; state.detailFor = null; state.slots = null; },
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
  try {
    state.health = await api.publicHealth();
  } catch {
    state.health = null;
  }
  mount();
  await search();
  // Em paralelo: os selos chegam conforme as respostas (RF-4921); a pasta da vista Dados mostra a situação nova.
  checkHealth(false).then(() => refreshSaved());
  checkNews(); // junto com a situação: a última atualização das fontes em uso, para o aviso Dados novos (RF-4935)
  if (state.overview.atualizacao?.rodando) followRefresh();
  else if (state.overview.desatualizado) startRefresh();
}
