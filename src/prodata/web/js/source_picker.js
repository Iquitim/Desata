// Seletor de fontes (spec 041, RF-4120..4124): o cartão da fonte no Input Data e a janela grande, como a de abrir
// arquivo do Windows: pastas da vista Dados à esquerda, a lista no centro e a prévia à direita.

import { api } from './api.js';
import { button, fmt, h, persist, storage } from './dom.js';
import { icon } from './icons.js';
import { outputText } from './pdf_labels.js';
import { API_PREFIX, displayName, FOLDER_PREFIX, JIRA_PREFIX, PDF_PREFIX, QUERY_PREFIX, sourceKey, store } from './store.js';
import { openDialog } from './ui.js';

const RECENT_KEY = 'prodata.picker.recent';
const VIEW_KEY = 'prodata.picker.view';
const PICKABLE = ['file', 'folder', 'pdf', 'query', 'api', 'jira'];
const MAX_RECENT = 12;

/** Cada fonte que pode ir no Input Data, já com o valor que a caixa grava (uma linha por saída do PDF). */
function pickables(sources) {
  const out = [];
  for (const s of sources) {
    if (!PICKABLE.includes(s.kind)) continue;
    if (s.kind === 'pdf') {
      const outputs = s.raw.status?.outputs || ['campos'];
      const draft = Boolean(s.raw.status?.draft);
      for (const o of outputs) {
        out.push({ ...s, value: `${PDF_PREFIX}${s.id}/${o}`, title: `${s.title} · ${outputText(o)[0]}`, output: o,
          blocked: draft ? 'Leitor ainda em rascunho: conclua na vista Dados' : null });
      }
      continue;
    }
    const value = s.kind === 'file' ? s.raw.name : s.kind === 'folder' ? `${FOLDER_PREFIX}${s.id}`
      : s.kind === 'query' ? `${QUERY_PREFIX}${s.id}` : s.kind === 'api' ? `${API_PREFIX}${s.id}` : `${JIRA_PREFIX}${s.id}`;
    const blocked = s.loop ? 'Esta API pede um valor por linha: use a caixa API Loop'
      : s.state.tone === 'err' ? `Não funciona agora: ${s.state.label}` : null;
    out.push({ ...s, value, blocked });
  }
  return out;
}

const recent = () => { const r = storage(RECENT_KEY, []); return Array.isArray(r) ? r : []; };
const remember = (value) => persist(RECENT_KEY, [value, ...recent().filter((v) => v !== value)].slice(0, MAX_RECENT));

// ---------------------------------------------------------------- cartão no Input Data

const KIND_OF_VALUE = (v) => (!v ? null : v.startsWith(FOLDER_PREFIX) ? 'folder' : v.startsWith(PDF_PREFIX) ? 'pdf'
  : v.startsWith(QUERY_PREFIX) ? 'query' : v.startsWith(API_PREFIX) ? 'api' : v.startsWith(JIRA_PREFIX) ? 'jira' : 'file');
const KIND_INFO = {
  file: ['file', 'Arquivo', 'var(--cat-inout)'], folder: ['directory', 'Pasta de arquivos', 'var(--cat-inout)'],
  pdf: ['file-plus', 'Leitor de PDF', 'var(--cat-inout)'], query: ['server', 'Consulta de banco', 'var(--cat-transform)'],
  api: ['globe', 'API', 'var(--cat-ml)'], jira: ['list', 'Consulta do Jira', 'var(--cat-transform)'],
};

/** Nome que a pessoa vê para um valor gravado, e se ele existe neste computador. */
function describe(value) {
  const kind = KIND_OF_VALUE(value);
  if (!kind) return null;
  const id = value.slice(value.indexOf(':') + 1);
  const found = {
    file: () => store.datasets.find((d) => d.name === value),
    folder: () => store.folderSources.find((f) => f.id === id),
    pdf: () => store.pdfSources.find((p) => p.id === id.split('/')[0]),
    query: () => store.queries.find((q) => q.id === id),
    api: () => store.apis.find((a) => a.id === id),
    jira: () => store.jiraQueries.find((q) => q.id === id),
  }[kind]();
  const base = displayName(sourceKey(kind === 'pdf' ? `${PDF_PREFIX}${id.split('/')[0]}` : value)) || found?.name || (kind === 'file' ? value : id);
  const name = kind === 'pdf' ? `${base} · ${outputText(id.split('/')[1] || 'campos')[0]}` : base;
  return { kind, name, found: Boolean(found), raw: found };
}

/**
 * Campo Fonte do Input Data: o cartão com a fonte escolhida e o botão Trocar, que abre o seletor.
 * `extras`: os botões que já existiam ao lado (prévia, nova consulta).
 */
export function sourceCard(value, set, extras = []) {
  const d = describe(value);
  const open = () => openSourcePicker({ value, onPick: set });
  if (!d) {
    return h('div', { class: 'src-card empty' },
      h('span', { class: 'src-card-icon' }, icon('database', 16)),
      h('span', { class: 'src-card-text' }, h('b', {}, 'Nenhuma fonte escolhida'), h('small', {}, 'Escolha entre as fontes da vista Dados')),
      button({ icon: 'folder', label: 'Escolher', size: 'sm', variant: 'primary', onClick: open }));
  }
  const [ic, label, color] = KIND_INFO[d.kind];
  const meta = d.kind === 'file' && d.raw ? `${label} · ${fmt.bytes(d.raw.size_bytes)}` : label;
  return h('div', { class: ['src-card', !d.found && 'missing'], style: { '--src-color': color } },
    h('span', { class: 'src-card-icon' }, icon(ic, 16)),
    h('span', { class: 'src-card-text', title: value },
      h('b', {}, d.name),
      h('small', {}, d.found ? meta : 'não encontrada neste computador')),
    button({ icon: 'folder', label: 'Trocar', size: 'sm', title: 'Escolher outra fonte', onClick: open }),
    ...extras);
}

// ---------------------------------------------------------------- a janela

/**
 * Abre o seletor. `onPick(value)` recebe o valor que a caixa grava. `value`: a fonte atual, que já vem selecionada.
 * `kinds`: limitar os tipos (ex.: só arquivos, em "Usar uma fonte daqui").
 */
export async function openSourcePicker({ value = '', onPick, kinds = PICKABLE, title = 'Escolher a fonte' } = {}) {
  const [{ allSources, KINDS, refreshUsage, usageText, matches }, { folders, colorOf }] = await Promise.all([
    import('./data_sources.js'), import('./organization.js'),
  ]);
  await refreshUsage().catch(() => {});
  const ui = { scope: 'all', query: '', sort: 'name', view: storage(VIEW_KEY, 'list'), selected: value || null };
  let items = [];
  const reload = () => { items = pickables(allSources()).filter((s) => kinds.includes(s.kind)); };
  reload();

  const scopes = () => [
    ['all', 'Todas as fontes', 'database', items.length],
    ['pinned', 'Fixadas', 'star', items.filter((s) => s.info?.pinned).length],
    ['recent', 'Recentes', 'clock', items.filter((s) => recent().includes(s.value)).length],
  ];
  const inScope = (s) => {
    if (ui.scope === 'all') return true;
    if (ui.scope === 'pinned') return s.info?.pinned;
    if (ui.scope === 'recent') return recent().includes(s.value);
    if (ui.scope === 'nofolder') return !s.info?.folder;
    if (ui.scope.startsWith('folder:')) return s.info?.folder === ui.scope.slice(7);
    if (ui.scope.startsWith('kind:')) return s.kind === ui.scope.slice(5);
    return true;
  };
  const visible = () => {
    const list = items.filter((s) => inScope(s) && matches(s, ui.query));
    const by = { name: (a, b) => a.title.localeCompare(b.title, 'pt-BR'), kind: (a, b) => a.kind.localeCompare(b.kind) || a.title.localeCompare(b.title, 'pt-BR'),
      usage: (a, b) => usageText(b).localeCompare(usageText(a)) || a.title.localeCompare(b.title, 'pt-BR') };
    if (ui.scope === 'recent') return list.sort((a, b) => recent().indexOf(a.value) - recent().indexOf(b.value));
    return list.sort(by[ui.sort]);
  };

  const nav = h('nav', { class: 'sp-nav', 'aria-label': 'Onde procurar' });
  const list = h('div', { class: 'sp-list', role: 'listbox', tabindex: 0, 'aria-label': 'Fontes' });
  const side = h('aside', { class: 'sp-preview', 'aria-live': 'polite' });
  const search = h('input', { class: 'input input-search', type: 'search', placeholder: 'Buscar por nome, descrição, pasta ou fluxo', 'aria-label': 'Buscar fonte',
    oninput: (e) => { ui.query = e.target.value; drawList(); } });
  const sort = h('select', { class: 'input input-sm', 'aria-label': 'Ordenar', onchange: (e) => { ui.sort = e.target.value; drawList(); } },
    [['name', 'Nome'], ['kind', 'Tipo'], ['usage', 'Uso']].map(([v, t]) => h('option', { value: v }, `Ordenar por ${t.toLowerCase()}`)));
  const viewBtn = button({ icon: ui.view === 'grid' ? 'list' : 'dashboard', size: 'sm', variant: 'ghost', title: 'Lista ou ícones',
    onClick: () => { ui.view = ui.view === 'grid' ? 'list' : 'grid'; persist(VIEW_KEY, ui.view); viewBtn.replaceChildren(icon(ui.view === 'grid' ? 'list' : 'dashboard', 14)); drawList(); } });
  const pickBtn = button({ icon: 'check', label: 'Escolher', variant: 'primary', onClick: () => choose(ui.selected) });

  let dialog = null;
  const choose = (v) => {
    const s = items.find((x) => x.value === v);
    if (!s || s.blocked) return;
    remember(v);
    dialog?.close();
    onPick?.(v);
  };

  const navItem = (id, text, ic, count, color = null) => h('button', {
    type: 'button', class: ['sp-nav-item', ui.scope === id && 'active'], onclick: () => { ui.scope = id; drawNav(); drawList(); },
  }, ic ? icon(ic, 14) : h('span', { class: 'sp-dot', style: { background: color } }), h('span', { class: 'ellipsis' }, text), h('small', {}, String(count)));
  const drawNav = () => {
    const kindsHere = PICKABLE.filter((k) => kinds.includes(k) && items.some((s) => s.kind === k));
    nav.replaceChildren(...[
      ...scopes().map(([id, t, ic, n]) => navItem(id, t, ic, n)),
      folders().length ? h('div', { class: 'sp-nav-title' }, 'Pastas') : null,
      ...folders().map((f) => navItem(`folder:${f.id}`, f.name, null, items.filter((s) => s.info?.folder === f.id).length, colorOf(f))),
      folders().length ? navItem('nofolder', 'Sem pasta', 'folder-closed', items.filter((s) => !s.info?.folder).length) : null,
      h('div', { class: 'sp-nav-title' }, 'Tipos'),
      ...kindsHere.map((k) => navItem(`kind:${k}`, KINDS[k].title, KINDS[k].icon, items.filter((s) => s.kind === k).length)),
    ].filter(Boolean));
  };

  const row = (s) => h('div', {
    class: ['sp-item', ui.selected === s.value && 'selected', s.blocked && 'blocked'], role: 'option', 'aria-selected': String(ui.selected === s.value),
    'aria-disabled': s.blocked ? 'true' : null, dataset: { value: s.value }, title: s.blocked || s.title, style: { '--src-color': KINDS[s.kind].color },
    onclick: () => select(s.value), ondblclick: () => choose(s.value),
  },
  h('span', { class: 'sp-item-icon' }, icon(KINDS[s.kind].icon, ui.view === 'grid' ? 22 : 15)),
  h('span', { class: 'sp-item-text' }, h('b', { class: 'ellipsis' }, s.title), h('small', { class: 'ellipsis' }, s.blocked || s.meta)),
  ui.view === 'list' ? h('span', { class: 'sp-item-kind' }, KINDS[s.kind].one) : null,
  ui.view === 'list' ? h('span', { class: ['sp-item-use', usageText(s) === 'sem uso' && 'muted'] }, usageText(s)) : null);

  const drawList = () => {
    const shown = visible();
    list.className = `sp-list ${ui.view === 'grid' ? 'grid' : ''}`;
    list.replaceChildren(...(shown.length ? shown.map(row) : [h('p', { class: 'sp-empty' }, ui.query ? `Nada encontrado para "${ui.query}".` : 'Nenhuma fonte aqui.')]));
    list.querySelector('.sp-item.selected')?.scrollIntoView({ block: 'nearest' });
  };

  let previewSeq = 0;
  const select = (v) => {
    ui.selected = v;
    for (const el of list.querySelectorAll('.sp-item')) {
      const on = el.dataset.value === v;
      el.classList.toggle('selected', on);
      el.setAttribute('aria-selected', String(on));
      if (on) el.scrollIntoView({ block: 'nearest' });
    }
    const s = items.find((x) => x.value === v);
    pickBtn.disabled = !s || Boolean(s.blocked);
    drawPreview(s);
  };

  const drawPreview = (s) => {
    const seq = ++previewSeq;
    if (!s) { side.replaceChildren(h('p', { class: 'muted' }, 'Escolha uma fonte para ver as primeiras linhas.')); return; }
    const table = h('div', { class: 'sp-table' }, h('p', { class: 'muted' }, 'Carregando a prévia…'));
    side.replaceChildren(...[
      h('div', { class: 'sp-preview-head', style: { '--src-color': KINDS[s.kind].color } }, icon(KINDS[s.kind].icon, 18), h('div', {},
        h('b', {}, s.title), h('small', {}, `${KINDS[s.kind].one} · ${s.meta}`))),
      s.info?.description || s.raw?.description ? h('p', { class: 'sp-desc' }, s.info.description || s.raw.description) : null,
      h('p', { class: 'sp-use' }, icon('workflow', 12), ` ${usageText(s)}`),
      s.blocked ? h('p', { class: 'api-warn' }, icon('alert', 13), ` ${s.blocked}`) : null,
      table].filter(Boolean));
    const show = (p) => { if (seq === previewSeq) import('./datasets.js').then(({ previewTable }) => table.replaceChildren(previewTable(p.columns, p.rows.slice(0, 12)))); };
    const fail = (err) => { if (seq === previewSeq) table.replaceChildren(h('p', { class: 'text-error' }, err.message)); };
    if (s.kind === 'file') api.previewDataset(s.raw.name, {}, 20).then(show, fail);
    else if (s.kind === 'folder') api.previewFolder(s.raw, 20).then(show, fail);
    else if (s.kind === 'query') api.previewQuery({ connection: s.raw.connection, mode: s.raw.mode, table: s.raw.table, query: s.raw.query }, 20).then(show, fail);
    else {
      // API, Jira e PDF: a prévia chama a rede ou lê os documentos; só quando a pessoa pedir.
      table.replaceChildren(s.kind === 'api' || s.kind === 'jira'
        ? button({ icon: 'eye', label: s.kind === 'api' ? 'Carregar prévia (chama a API)' : 'Carregar prévia (consulta o Jira)', size: 'sm', onClick: () => {
          table.replaceChildren(h('p', { class: 'muted' }, 'Carregando…'));
          (s.kind === 'api' ? api.previewApi(s.raw, 20) : api.previewJira({ ...s.raw, rows: 20 })).then(show, fail);
        } })
        : h('p', { class: 'muted' }, 'A prévia do PDF fica na vista Dados, com o documento ao lado.'));
    }
  };

  // Teclado: setas andam na lista, Enter escolhe, digitar vai para a busca.
  const onKey = (e) => {
    const shown = visible();
    const at = shown.findIndex((s) => s.value === ui.selected);
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      const step = ui.view === 'grid' && e.target === list ? 1 : 1;
      const next = shown[Math.max(0, Math.min(shown.length - 1, at + (e.key === 'ArrowDown' ? step : -step)))];
      if (next) select(next.value);
    } else if (e.key === 'Enter' && ui.selected) {
      e.preventDefault();
      choose(ui.selected);
    } else if (e.target === list && e.key.length === 1 && !e.ctrlKey && !e.metaKey) {
      search.focus();
    }
  };
  search.addEventListener('keydown', onKey);
  list.addEventListener('keydown', onKey);

  const afterCreate = async (picked) => { reload(); drawNav(); drawList(); if (picked) select(picked); };
  const createButtons = [
    kinds.includes('file') ? button({ icon: 'upload', label: 'Enviar arquivo', size: 'sm', onClick: async () => {
      const { accept, uploadFiles } = await import('./datasets.js');
      const input = h('input', { type: 'file', accept: accept(), multiple: false });
      input.addEventListener('change', () => uploadFiles([...input.files], { onUploaded: (info) => afterCreate(info.name) }));
      input.click();
    } }) : null,
    kinds.includes('query') ? button({ icon: 'server', label: 'Nova consulta', size: 'sm', onClick: async () => {
      const { openQueryEditor } = await import('./connections.js');
      openQueryEditor({ onSaved: (saved) => afterCreate(`${QUERY_PREFIX}${saved.id}`) });
    } }) : null,
    kinds.includes('api') ? button({ icon: 'globe', label: 'Nova API', size: 'sm', onClick: async () => {
      const { openApiEditor } = await import('./apis.js');
      openApiEditor({ onSaved: (saved) => afterCreate(`${API_PREFIX}${saved.id}`) });
    } }) : null,
  ].filter(Boolean);

  drawNav();
  drawList();
  select(ui.selected);
  const body = h('div', { class: 'sp' },
    nav,
    h('section', { class: 'sp-main' }, h('div', { class: 'sp-bar' }, search, sort, viewBtn), list,
      h('div', { class: 'sp-create' }, h('span', { class: 'field-help' }, 'Não achou?'), ...createButtons)),
    side);
  dialog = openDialog({ title, body, size: 'xl', actions: [button({ label: 'Cancelar', variant: 'ghost', onClick: () => dialog.close() }), pickBtn] });
  requestAnimationFrame(() => search.focus());
  return dialog;
}
