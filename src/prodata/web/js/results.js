// Painel de resultados: dados paginados com perfil por coluna, perfil detalhado e log de execução.

import { addNode, connect } from './actions.js';
import { api } from './api.js';
import { button, debounce, fmt, h, persist, storage } from './dom.js';
import { isAreaFree } from './canvas.js';
import { cell, spacesBadge } from './datasets.js';
import { describe, openFilterEditor, toExpression } from './explore.js';
import { icon } from './icons.js';
import { panelControls } from './layout.js';
import { inspect, node, nodeResult, on, select, store, toolOf, visibleOutputs } from './store.js';
import { tableSkeleton } from './skeleton.js';
import { clearWidths, enableColumnResize, summaryButton, watchSummary } from './table_tools.js';
import { enableCellFocus } from './cell_focus.js';
import { cleaningCard } from './cleaning_ui.js';
import { recipeMenu } from './recipes_ui.js';
import { typeLabel, typeName } from './types.js';
import { showMenu, toast } from './ui.js';

const PAGE = 100;
const STATUS_ICONS = { executed: 'check-circle', cached: 'check-circle', error: 'alert', skipped: 'skip', disabled: 'power' };
const STATUS_LABELS = { executed: 'Executado', cached: 'Cache', error: 'Erro', skipped: 'Não executado', disabled: 'Desabilitado' };

const state = { tab: storage('prodata.results.tab', 'data'), offset: 0, search: '', sortCol: null, sortDesc: false, data: null, seq: 0, turn: null };
const els = {};

// Filtros exploratórios por saída inspecionada; cada saída lembra os seus durante a sessão.
const filtersByOutput = new Map();
const outputKey = () => `${store.workflow?.id}:${store.inspect.nodeId}:${store.inspect.anchor}`;
const currentFilters = () => filtersByOutput.get(outputKey()) || [];

/** A fonte do catálogo Dados públicos da caixa inspecionada (spec 049): dicionário de colunas e citação. */
function publicSource() {
  const id = store.inspect.nodeId;
  return ['io.public_data', 'io.input_data'].includes(node(id)?.type) ? nodeResult(id)?.extra?.fonte_publica || null : null; // e a pasta do CNPJ
}
const columnMeaning = (source, name) => source?.colunas?.find((c) => c.nome === name)?.descricao || '';

/** O cartão da fonte no alto do Perfil: de onde vêm os dados, quando foram lidos e como citar (RF-4963). */
function publicSourceCard(source) {
  if (!source) return null;
  const read = source.lido_em ? new Date(source.lido_em).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' }) : '';
  return h('section', { class: 'profile-source', 'aria-label': 'Fonte dos dados' },
    h('span', { class: 'profile-source-icon' }, icon('landmark', 16)),
    h('div', {},
      h('strong', {}, [source.nome, source.orgao].filter(Boolean).join(' · ')),
      read ? h('p', {}, `Lidos em ${read}, direto do órgão.`) : null,
      source.citacao ? h('p', {}, h('span', { class: 'muted' }, 'Como citar: '), source.citacao) : null,
      source.licenca ? h('p', { class: 'muted' }, source.licenca) : null,
      source.colunas?.length ? h('p', { class: 'muted small' }, 'O significado de cada coluna aparece no cartão dela e na dica do cabeçalho em Resultado.') : null));
}

function setFilters(list) {
  filtersByOutput.set(outputKey(), list);
  state.offset = 0;
  load();
}

function editFilter(x, y, index = null, preset = {}) {
  const columns = state.data?.profile?.columns || [];
  if (!columns.length) return;
  const list = currentFilters();
  openFilterEditor(x, y, {
    columns,
    initial: index === null ? preset : list[index],
    onApply: (cond) => setFilters(index === null ? [...list, cond] : list.map((f, i) => (i === index ? cond : f))),
  });
}

function filterAt(el, index = null, preset = {}) {
  const r = el.getBoundingClientRect();
  editFilter(r.left, r.bottom + 4, index, preset);
}

/** Exploração → fluxo: cria um Filter com os filtros ativos ligado à saída inspecionada. */
function createFilterNode() {
  const filters = currentFilters();
  // Guarda a origem antes: criar o nó muda a seleção e a saída inspecionada.
  const { nodeId, anchor } = store.inspect;
  const source = node(nodeId);
  if (!filters.length || !source) return;
  const expression = toExpression(filters, state.data.profile.columns);
  const { x, y } = freeSpotNear(source);
  const created = addNode('prep.filter', x, y, { mode: 'expression', expression, __label: 'Filtro explorado' });
  if (created && connect(source.id, anchor, created.id, 'in')) {
    toast('Caixa Filter criada e ligada', { kind: 'success', detail: expression });
  }
}

/** Primeira posição livre (sem nós nem fios) à direita e abaixo do nó de origem. */
function freeSpotNear(source) {
  const x = source.x + 248;
  let y = source.y + 110;
  for (let i = 0; i < 30 && !isAreaFree(x, y); i += 1) y += 30;
  return { x, y };
}

function drawFilterBar() {
  const filters = currentFilters();
  els.filterBtn.querySelector('.count')?.remove();
  if (filters.length) els.filterBtn.append(h('span', { class: 'count' }, filters.length));
  els.filterBtn.classList.toggle('active', filters.length > 0);
  els.filterBar.hidden = !filters.length || state.tab === 'log';
  els.filterBar.replaceChildren(
    ...filters.map((f, i) => h('span', { class: 'filter-chip' },
      h('button', { type: 'button', class: 'filter-chip-main', title: 'Editar condição', onclick: (e) => filterAt(e.currentTarget, i) }, describe(f)),
      h('button', { type: 'button', class: 'chip-x', 'aria-label': 'Remover condição', onclick: () => setFilters(filters.filter((_, j) => j !== i)) }, icon('x', 12)))),
    button({ icon: 'plus', label: 'Condição', size: 'sm', variant: 'ghost', onClick: (e) => filterAt(e.currentTarget) }),
    h('div', { class: 'grow' }),
    button({ icon: 'workflow', label: 'Criar caixa Filter', size: 'sm', variant: 'ghost', title: 'Levar estes filtros para o fluxo como uma caixa Filter', onClick: createFilterNode }),
    button({ icon: 'x', label: 'Limpar', size: 'sm', variant: 'ghost', onClick: () => setFilters([]) }),
  );
}

// ---------------------------------------------------------------- tabela em tela cheia (spec 033)

export const inTableFocus = () => Boolean(els.root?.classList.contains('table-focus'));

function drawFocusButton() {
  const active = inTableFocus();
  els.focusBtn.title = active ? 'Recolher a tabela (Shift+F11 ou Esc)' : 'Expandir a tabela em tela cheia, para mostrar ou explorar (Shift+F11)';
  els.focusBtn.setAttribute('aria-label', els.focusBtn.title);
  els.focusBtn.setAttribute('aria-pressed', String(active));
  // Só o ícone: com o painel estreito, um rótulo encostava nos controles do painel.
  els.focusBtn.replaceChildren(icon(active ? 'minimize' : 'maximize', 15));
}

/** Liga, desliga ou alterna a tabela em tela cheia. Devolve se mudou alguma coisa. */
export function toggleTableFocus(force = null) {
  if (!els.root) return false;
  const next = force === null ? !inTableFocus() : force;
  if (next === inTableFocus()) return false;
  els.root.classList.toggle('table-focus', next);
  document.body.classList.toggle('table-focus-on', next);
  let hint = els.root.querySelector('.table-focus-hint');
  if (next && !hint) {
    hint = h('div', { class: 'focus-hint table-focus-hint', role: 'status' }, h('b', {}, 'Tabela em tela cheia'), ' · ', h('kbd', {}, 'Esc'), ' volta');
    els.root.append(hint);
    setTimeout(() => hint.remove(), 4000);
  } else if (!next) {
    hint?.remove();
  }
  drawFocusButton();
  return true;
}

export function initResults(root) {
  els.root = root;
  els.title = h('div', { class: 'results-title' });
  els.anchors = h('div', { class: 'segmented small', role: 'tablist', 'aria-label': 'Saída' });
  els.turn = h('div', { class: 'results-turn' }); // laço (spec 041): qual volta mostrar
  els.search = h('input', {
    class: 'input input-search input-sm', type: 'search', placeholder: 'Buscar nas linhas', 'aria-label': 'Buscar nas linhas',
    oninput: debounce((e) => { state.search = e.target.value; state.offset = 0; load(); }, 300),
  });
  els.pager = h('div', { class: 'pager' });
  els.tabs = h('div', { class: 'tabs', role: 'tablist' },
    ['data', 'profile', 'log'].map((t) => h('button', {
      type: 'button', role: 'tab', class: 'tab', dataset: { tab: t },
      onclick: () => { state.tab = t; persist('prodata.results.tab', t); draw(); },
    }, { data: 'Resultado', profile: 'Perfil', log: 'Log' }[t])));
  els.body = h('div', { class: 'results-body' });
  watchSummary(els.body); // resumo das colunas (spec 041)
  els.filterBtn = button({
    icon: 'filter', label: 'Filtros', size: 'sm', variant: 'ghost',
    title: 'Filtros exploratórios: só mudam esta visualização, não o fluxo',
    onClick: (e) => filterAt(e.currentTarget),
  });
  els.filterBar = h('div', { class: 'results-row filter-bar', hidden: true });

  els.focusBtn = button({ icon: 'maximize', title: '', size: 'sm', variant: 'ghost', onClick: () => toggleTableFocus() });
  els.focusBtn.classList.add('results-focus');
  drawFocusButton();
  root.replaceChildren(
    h('div', { class: 'results-toolbar' },
      h('div', { class: 'results-row' }, els.tabs, h('div', { class: 'grow' }), els.pager, els.focusBtn, panelControls('results')),
      h('div', { class: 'results-row' }, els.title, els.anchors, els.turn, h('div', { class: 'grow' }), summaryButton(), els.filterBtn, els.search),
      els.filterBar),
    els.body);

  on('inspect', () => { state.offset = 0; state.sortCol = null; state.turn = null; load(); });
  // o ponto de limpeza na caixa (spec 048) abre o Perfil dela, onde estão as recomendações
  on('show:profile', () => { state.tab = 'profile'; persist('prodata.results.tab', 'profile'); draw(); });
  on('execution', () => load());
  on('numbers', () => draw()); // separador decimal (spec 038)
  on('workflow:loaded', () => { state.data = null; draw(); });
  draw();
}

async function load() {
  const { nodeId, anchor } = store.inspect;
  const res = nodeResult(nodeId);
  const port = res?.anchors?.[anchor];
  state.data = null;
  if (!nodeId || !anchor || !port || port.kind === 'model' || !['executed', 'cached'].includes(res.status)) {
    draw();
    return;
  }
  const seq = ++state.seq;
  els.body.classList.add('loading');
  try {
    const filters = currentFilters();
    const data = await api.results(store.workflow.id, nodeId, anchor, {
      offset: state.offset, limit: PAGE, search: state.search,
      ...(state.sortCol ? { sort_col: state.sortCol, sort_desc: state.sortDesc } : {}),
      ...(filters.length ? { filters: JSON.stringify(filters) } : {}),
      ...(state.turn && res.extra?.loop ? { loop_end: res.extra.loop.end, turn: state.turn } : {}),
    });
    if (seq === state.seq) state.data = data;
  } catch (err) {
    if (seq === state.seq) state.data = { error: err.message };
  } finally {
    els.body.classList.remove('loading');
  }
  if (seq === state.seq) draw();
}

/** Caixa dentro de um laço: escolher a volta (spec 041, RF-4168). Sem escolha, mostra a última. */
function drawTurn() {
  const loop = nodeResult(store.inspect.nodeId)?.extra?.loop;
  const own = loop && loop.end !== store.inspect.nodeId; // o Fim mostra o que sai do laço, não uma volta
  if (!own || !loop.turns) { els.turn.replaceChildren(); return; }
  const input = h('input', {
    class: 'input input-sm', type: 'number', min: 1, max: loop.turns, value: state.turn || loop.turns, 'aria-label': 'Volta',
    onchange: (e) => { const v = Math.max(1, Math.min(loop.turns, Number(e.target.value) || loop.turns)); state.turn = v === loop.turns ? null : v; state.offset = 0; load(); },
  });
  els.turn.replaceChildren(h('span', { class: 'muted' }, 'Volta'), input, h('span', { class: 'muted' }, `de ${loop.turns}`));
}

function draw() {
  drawTurn();
  for (const t of els.tabs.children) t.setAttribute('aria-selected', String(t.dataset.tab === state.tab));
  drawHeader();
  drawFilterBar();
  if (state.tab === 'log') els.body.replaceChildren(logView());
  else els.body.replaceChildren(state.tab === 'profile' ? profileView() : dataView());
}

function drawHeader() {
  const n = node(store.inspect.nodeId);
  const spec = toolOf(n);
  const res = nodeResult(n?.id);
  const via = store.inspect.via;
  const target = via && node(via.nodeId);
  if (target) {
    // Entrada de uma caixa (spec 012): mostra o que chega pela porta, vindo da caixa de origem.
    const tSpec = toolOf(target);
    const port = tSpec?.inputs.find((p) => p.id === via.port);
    els.title.replaceChildren(h('span', { class: 'results-via' }, icon('arrow-down', 14),
      `Entrada [${port?.label || via.port}] de ${target.label || tSpec?.name}`,
      h('span', { class: 'muted' }, ` ← ${n?.label || spec?.name || ''}`)));
  } else {
    els.title.replaceChildren(n ? h('span', {}, icon(spec.icon, 14), n.label || spec.name) : h('span', { class: 'muted' }, 'Nenhuma caixa selecionada'));
  }
  const outs = n ? visibleOutputs(n) : [];
  els.anchors.replaceChildren(...(!target && (outs.length > 1 || outs[0]?.kind === 'model') ? outs : []).map((o) => {
    const count = res?.anchors?.[o.id];
    return h('button', {
      type: 'button', role: 'tab', class: 'segment', 'aria-selected': String(store.inspect.anchor === o.id),
      title: o.title, onclick: () => inspect(n.id, o.id),
    }, h('b', {}, o.label), count ? h('span', { class: 'muted' }, count.kind === 'model' ? 'modelo' : fmt.compact(count.row_count)) : null);
  }));
  const d = state.data;
  const showPager = state.tab === 'data' && d?.rows;
  els.search.hidden = state.tab === 'log';
  els.filterBtn.hidden = state.tab === 'log';
  const narrowed = d && d.filtered_count !== d.row_count;
  els.pager.replaceChildren(...(showPager ? [
    h('span', { class: 'muted', title: narrowed ? `${fmt.int(d.filtered_count)} de ${fmt.int(d.row_count)} linhas após filtros/busca` : null },
      d.filtered_count
        ? `${fmt.int(d.offset + 1)}–${fmt.int(Math.min(d.offset + PAGE, d.filtered_count))} de ${fmt.int(d.filtered_count)}${narrowed ? ` (de ${fmt.compact(d.row_count)})` : ''}`
        : '0 linhas'),
    button({ icon: 'chevron-left', title: 'Página anterior', size: 'sm', variant: 'ghost', disabled: d.offset === 0,
      onClick: () => { state.offset = Math.max(0, state.offset - PAGE); load(); } }),
    button({ icon: 'chevron-right', title: 'Próxima página', size: 'sm', variant: 'ghost', disabled: d.offset + PAGE >= d.filtered_count,
      onClick: () => { state.offset += PAGE; load(); } }),
  ] : []));
}

function empty(iconName, title, detail) {
  return h('div', { class: 'empty' }, icon(iconName, 22), h('strong', {}, title), detail ? h('span', {}, detail) : null);
}

function guard() {
  const { nodeId, anchor } = store.inspect;
  if (!nodeId) return empty('table', 'Selecione uma caixa', 'Clique numa caixa ou numa das saídas dela para ver os dados.');
  const res = nodeResult(nodeId);
  if (!res) return empty('play', 'Caixa ainda não executada', 'Execute o fluxo (Ctrl+Enter) para ver os dados.');
  if (res.status === 'error') return empty('alert', 'Esta caixa falhou', res.error);
  if (res.status === 'skipped' || res.status === 'disabled') return empty('skip', STATUS_LABELS[res.status], res.error);
  const port = res.anchors?.[anchor];
  if (port?.kind === 'model') return modelCard(port.metrics);
  if (state.data?.error) return empty('alert', 'Não foi possível carregar', state.data.error);
  if (!state.data) return tableSkeleton();
  return null;
}

function modelCard(m) {
  const rows = m.task === 'classification'
    ? [['Acurácia (validação)', `${fmt.number(m.accuracy_pct)}%`], ['F1 ponderado (validação)', `${fmt.number(m.f1_pct)}%`]]
    : [['R² (validação)', fmt.number(m.r2, 3)], ['Erro absoluto médio', fmt.number(m.mae)]];
  return h('div', { class: 'model-card' },
    h('div', { class: 'model-head' }, icon('brain', 18), h('strong', {}, 'Modelo treinado'),
      h('span', { class: 'badge' }, m.algorithm), h('span', { class: 'badge' }, m.task === 'classification' ? 'Classificação' : 'Regressão')),
    h('dl', { class: 'stats' }, rows.map(([k, v]) => h('div', { class: 'stat' }, h('dt', {}, k), h('dd', {}, v))),
      h('div', { class: 'stat' }, h('dt', {}, 'Treino / validação'), h('dd', {}, `${fmt.int(m.train_rows)} / ${fmt.int(m.validation_rows)}`))),
    h('p', { class: 'muted' }, 'Conecte a saída [M] a uma caixa Predictor para aplicar o modelo. A saída [I] mostra a importância das variáveis.'));
}

function qualityBar(c) {
  return h('div', {
    class: 'quality', title: `${c.ok_pct}% preenchido · ${c.empty_pct}% vazio · ${c.null_pct}% nulo`,
  }, h('span', { class: 'q-ok', style: { width: `${c.ok_pct}%` } }), h('span', { class: 'q-empty', style: { width: `${c.empty_pct}%` } }),
  h('span', { class: 'q-null', style: { width: `${c.null_pct}%` } }));
}

/** Quantos valores diferentes há entre os preenchidos: o nulo também conta como um valor em `unique_count`. */
function identifierNote(c) {
  const filled = (c.total ?? 0) - (c.null_count ?? 0);
  const distinct = (c.unique_count ?? 0) - (c.null_count ? 1 : 0);
  if (filled < 2) return '';
  if (distinct === filled && ['String', 'Int64'].includes(c.type)) return 'todos diferentes';
  return c.type === 'String' && distinct / filled >= 0.95 ? 'quase todos diferentes' : '';
}

/** Faixa do histograma com o separador decimal escolhido (spec 038); categorias seguem o texto. */
function binLabel(b) {
  if (typeof b.lo !== 'number') return b.label;
  const show = (v) => fmt.number(Number(v.toPrecision(4)));
  return b.lo === b.hi ? show(b.lo) : `${show(b.lo)} – ${show(b.hi)}`;
}

/** A distribuição só aparece quando informa: em coluna de identificador, as barras saem todas iguais (RF-2922). */
function sparkline(c) {
  const note = identifierNote(c);
  if (note) return h('div', { class: 'th-note', title: `${fmt.int(c.unique_count)} valores diferentes` }, note);
  return h('div', { class: 'spark' }, c.histogram.map((b) => h('span', {
    style: { height: `${Math.max(6, b.pct)}%` }, title: `${binLabel(b)}: ${fmt.int(b.count)}`,
  })));
}

function dataView() {
  const blocked = guard();
  if (blocked) return blocked;
  const { profile, rows } = state.data;
  const cols = profile.columns;
  if (!cols.length) return empty('table', 'Tabela sem colunas');
  const sortIcon = (name) => (state.sortCol === name ? icon(state.sortDesc ? 'arrow-down' : 'arrow-up', 12) : null);
  const sortBy = (name, desc) => { state.sortCol = name; state.sortDesc = desc; state.offset = 0; load(); };
  const filtered = new Set(currentFilters().map((f) => f.column));
  const source = publicSource(); // dicionário de colunas da fonte pública (RF-4912)
  const head = h('tr', {}, h('th', { class: 'rownum' }, '#'), cols.map((c) => h('th', {
    class: ['sortable', state.sortCol === c.name && 'sorted', filtered.has(c.name) && 'filtered'],
    title: [columnMeaning(source, c.name), 'Clique para ordenar · botão direito para mais opções'].filter(Boolean).join('\n\n'),
    onclick: () => {
      if (state.sortCol !== c.name) sortBy(c.name, false);
      else if (!state.sortDesc) sortBy(c.name, true);
      else { state.sortCol = null; state.offset = 0; load(); }
    },
    oncontextmenu: (e) => {
      e.preventDefault();
      showMenu(e.clientX, e.clientY, [
        { label: 'Filtrar esta coluna…', icon: 'filter', onSelect: () => editFilter(e.clientX, e.clientY, null, { column: c.name }) },
        'separator',
        { label: 'Ordenar crescente', icon: 'arrow-up', onSelect: () => sortBy(c.name, false) },
        { label: 'Ordenar decrescente', icon: 'arrow-down', onSelect: () => sortBy(c.name, true) },
        'separator',
        { label: 'Larguras automáticas', icon: 'columns', onSelect: () => { clearWidths(outputKey()); draw(); } },
        ...recipeMenu(c, state.data.profile), // receitas prontas: IPCA e PTAX (spec 049)
      ]);
    },
  },
  h('div', { class: 'th-top' }, h('span', { class: 'th-name' }, c.name), spacesBadge(c.empty_count || 0, c.padded_count || 0), sortIcon(c.name),
    h('button', {
      type: 'button', class: 'th-filter', title: `Filtrar ${c.name}`, 'aria-label': `Filtrar ${c.name}`,
      onclick: (e) => { e.stopPropagation(); filterAt(e.currentTarget, null, { column: c.name }); },
    }, icon('filter', 12)),
    h('span', { class: 'th-type', title: typeName(c.type) }, typeLabel(c.type))),
  columnTotal(c), qualityBar(c), sparkline(c))));
  const body = rows.length
    ? rows.map((r, i) => h('tr', {}, h('td', { class: 'rownum' }, state.data.offset + i + 1), cols.map((c, ci) => {
      const td = cell(r[c.name], c.type);
      td.dataset.ci = ci;
      return td;
    })))
    : [h('tr', {}, h('td', { colspan: cols.length + 1, class: 'muted pad' }, 'Nenhuma linha corresponde aos filtros ou à busca.'))];
  const tbody = h('tbody', {}, body);
  // Clique direito numa célula: filtrar por aquele valor (ou excluí-lo).
  tbody.addEventListener('contextmenu', (e) => {
    const td = e.target.closest('td[data-ci]');
    if (!td) return;
    e.preventDefault();
    const c = cols[Number(td.dataset.ci)];
    const value = rows[td.parentElement.rowIndex - 1]?.[c.name];
    const add = (cond) => setFilters([...currentFilters(), cond]);
    const shown = value === null || value === undefined ? null : String(value);
    showMenu(e.clientX, e.clientY, shown === null ? [
      { label: `Somente ${c.name} nulo`, icon: 'filter', onSelect: () => add({ column: c.name, op: 'is_null' }) },
      { label: `Excluir ${c.name} nulo`, icon: 'x', onSelect: () => add({ column: c.name, op: 'not_null' }) },
    ] : [
      { label: `Filtrar ${c.name} = ${shown.slice(0, 40)}`, icon: 'filter', onSelect: () => add({ column: c.name, op: 'eq', value: shown }) },
      { label: `Excluir ${shown.slice(0, 40)}`, icon: 'x', onSelect: () => add({ column: c.name, op: 'ne', value: shown }) },
      'separator',
      { label: 'Filtrar esta coluna…', icon: 'plus', onSelect: () => editFilter(e.clientX, e.clientY, null, { column: c.name, value: shown }) },
    ]);
  });
  const table = h('table', { class: 'data-table' }, h('thead', {}, head), tbody);
  const wrap = h('div', { class: 'table-wrap' }, table);
  enableColumnResize(table, outputKey(), ['#', ...cols.map((c) => c.name)]); // spec 041
  const foot = enableCellFocus(wrap, table, {
    firstCol: 1, nameAt: (ci) => cols[ci - 1]?.name, valueAt: (td, r, ci) => rows[r]?.[cols[ci - 1]?.name], rowLabel: (r) => state.data.offset + r + 1,
  });
  return h('div', { class: 'table-shell' }, wrap, foot);
}

/** Soma das colunas numéricas e contagem de não nulos nas demais, da tabela inteira ou dos filtros ativos (spec 021). */
function columnTotal(c) {
  const sum = c.stats?.sum;
  if (typeof sum === 'number') {
    return h('div', { class: 'th-total', title: `Soma: ${fmt.number(sum)}` }, `Σ ${fmt.compact(sum)}`);
  }
  const empty = (c.null_count ?? 0) + (c.empty_count ?? 0);
  const filled = Math.max(0, (c.total ?? 0) - empty);
  return h('div', { class: ['th-total', empty && 'has-empty'], title: `${fmt.int(filled)} linhas preenchidas · ${fmt.int(empty)} vazias` },
    empty ? `${fmt.int(empty)} ${empty === 1 ? 'vazio' : 'vazios'}` : 'sem vazios');
}

function profileView() {
  const blocked = guard();
  if (blocked) return blocked;
  const note = state.data.profile_scope === 'filtered'
    ? h('div', { class: 'profile-note' }, icon('filter', 13),
      `Perfil das ${fmt.int(state.data.filtered_count)} linhas filtradas (de ${fmt.int(state.data.row_count)}).`)
    : null;
  // recomendações de limpeza (spec 048): o cartão aparece no alto quando a resposta chega
  const source = publicSource();
  return h('div', {}, note, publicSourceCard(source), cleaningCard(), h('div', { class: 'profile-grid' }, state.data.profile.columns.map((c) => {
    const s = c.stats || {};
    const meaning = columnMeaning(source, c.name);
    const numeric = s.mean !== undefined;
    const facts = numeric
      ? [['Mín', s.min], ['Média', s.mean], ['Mediana', s.median], ['Máx', s.max], ['Desvio', s.std], ['Soma', s.sum]]
      : [['Distintos', c.unique_count], ['Mais comum', s.top ?? '—'], ['Ocorrências', s.top_count ?? 0]];
    return h('section', { class: 'profile-card' },
      h('header', {}, h('strong', { class: 'mono ellipsis' }, c.name), h('span', { class: 'th-type', title: `${typeName(c.type)} (${c.raw_type})` }, typeLabel(c.type))),
      meaning ? h('p', { class: 'profile-meaning' }, meaning) : null,
      qualityBar(c),
      h('div', { class: 'q-legend' }, h('span', {}, h('i', { class: 'q-ok' }), `${c.ok_pct}% ok`),
        h('span', {}, h('i', { class: 'q-empty' }), `${c.empty_pct}% vazio`), h('span', {}, h('i', { class: 'q-null' }), `${c.null_pct}% nulo`),
        c.padded_count ? h('span', { class: 'th-spaces', title: 'Valores com espaço no início ou no fim: "SP " não casa com "SP"' }, icon('alert', 11), `${fmt.int(c.padded_count)} com espaço sobrando`) : null),
      h('dl', { class: 'facts' }, facts.map(([k, v]) => h('div', {}, h('dt', {}, k),
        h('dd', { class: 'ellipsis', title: String(v) }, typeof v === 'number' ? fmt.number(v) : v)))),
      c.histogram.length ? h('div', { class: 'hist' }, c.histogram.map((b) => h('div', { class: 'hist-row', title: `${binLabel(b)}: ${fmt.int(b.count)}` },
        h('span', { class: 'hist-label ellipsis' }, binLabel(b)), h('span', { class: 'hist-bar' }, h('i', { style: { width: `${b.pct}%` } })),
        h('span', { class: 'hist-count' }, fmt.compact(b.count))))) : null);
  })));
}

function logView() {
  const logs = store.execution?.logs || [];
  if (!logs.length) return empty('list', 'Sem execuções', 'O log da última execução aparece aqui.');
  return h('div', { class: 'table-wrap' }, h('table', { class: 'data-table log-table' },
    h('thead', {}, h('tr', {}, h('th', {}, 'Status'), h('th', {}, 'Caixa'), h('th', {}, 'Mensagem'), h('th', { class: 'num' }, 'Tempo'))),
    h('tbody', {}, logs.map((l) => h('tr', {
      class: ['clickable', `log-${l.status}`],
      onclick: () => { select(l.node_id); inspect(l.node_id); state.tab = 'data'; draw(); },
    }, h('td', {}, h('span', { class: `status-chip ${l.status}` }, icon(STATUS_ICONS[l.status] || 'info', 13), STATUS_LABELS[l.status] || l.status)),
    h('td', {}, l.node_name), h('td', { class: 'wrap' }, l.message), h('td', { class: 'num' }, fmt.ms(l.elapsed_ms)))))));
}

export function showLog() {
  state.tab = 'log';
  draw();
}
