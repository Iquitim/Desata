// Blocos de lista que recolhem (spec 041, RF-4105..4108): cada item da lista do Configurar (fórmulas, agregações,
// chaves, regras…) vira um cartão de uma linha com nome, resumo e estado, e expande ao clicar. O nome e o recolhido
// ficam em `_ui` dentro do item: o motor ignora e a assinatura do cache não olha (engine/graph.py).

import { button, h } from './dom.js';
import { icon } from './icons.js';

const MAX_SUMMARY = 90;

const shown = (v) => (v === null || v === undefined || v === '' ? '' : Array.isArray(v) ? v.join(', ') : String(v));

function optionLabel(fields, name, value) {
  const f = fields.find((x) => x.name === name);
  return f?.options?.find((o) => o.value === value)?.label ?? shown(value);
}

/** Resumo de uma linha do item, pelo que ele tem (fórmula, chave, agregação, ordenação…), ou os valores em ordem. */
export function summarize(item, fields = []) {
  const it = item || {};
  let text;
  if ('expression' in it && ('column' in it || 'existing' in it)) {
    const left = it.target === 'existing' ? it.existing : it.column;
    text = it.expression ? `${left || '?'} = ${it.expression}` : left || '';
  } else if ('left' in it && 'right' in it) {
    text = it.left || it.right ? `${it.left || '?'} = ${it.right || it.left || '?'}` : '';
  } else if ('agg' in it) {
    text = it.column ? `${optionLabel(fields, 'agg', it.agg)} de ${it.column}${it.alias ? ` → ${it.alias}` : ''}` : '';
  } else if ('measure' in it) {
    const cols = [it.column_a, it.column_b].filter(Boolean).join(' × ');
    text = `${optionLabel(fields, 'measure', it.measure)}${cols ? ` · ${cols}` : ''}`;
  } else if ('descending' in it) {
    text = it.column ? `${it.column} ${it.descending ? '↓ decrescente' : '↑ crescente'}` : '';
  } else {
    text = fields.filter((f) => f.widget !== 'hidden' && f.widget !== 'toggle')
      .map((f) => (f.options ? optionLabel(fields, f.name, it[f.name]) : shown(it[f.name]))).filter(Boolean).slice(0, 3).join(' · ');
  }
  text = String(text || '').replace(/\s+/g, ' ').trim();
  return text.length > MAX_SUMMARY ? `${text.slice(0, MAX_SUMMARY - 1)}…` : text;
}

/** Erro visível dentro do bloco (expressão inválida, coluna que não existe): o cartão recolhido também mostra. */
function watchErrors(body, card) {
  const paint = () => {
    const bad = body.querySelector('.expr-status.err, .input.invalid');
    card.classList.toggle('has-error', Boolean(bad));
    const state = card.querySelector('.li-state');
    if (state) {
      state.replaceChildren(...(bad ? [icon('alert', 12)] : []));
      state.title = bad ? (bad.textContent || 'Este item tem um problema: expanda para ver') : '';
    }
  };
  new MutationObserver(paint).observe(body, { subtree: true, childList: true, attributes: true, attributeFilter: ['class'] });
  requestAnimationFrame(paint);
}

/** Troca o nome por um campo de texto; Enter ou sair grava, Esc cancela, vazio volta ao número. */
function renameInline(label, current, onName) {
  const input = h('input', { class: 'input input-sm li-rename', value: current || '', placeholder: 'Nome do item', 'aria-label': 'Nome do item', maxlength: 60 });
  let done = false;
  const finish = (save) => {
    if (done) return;
    done = true;
    if (save && input.value.trim() !== (current || '')) onName(input.value.trim());
    else input.replaceWith(label);
  };
  input.addEventListener('keydown', (e) => {
    e.stopPropagation();
    if (e.key === 'Enter') { e.preventDefault(); finish(true); }
    if (e.key === 'Escape') { e.preventDefault(); finish(false); }
  });
  input.addEventListener('blur', () => finish(true));
  input.addEventListener('click', (e) => e.stopPropagation());
  label.replaceWith(input);
  input.focus();
  input.select();
}

/**
 * Um item da lista. `ui` é o `_ui` do item e `setUi(patch)` grava nele. `title` e `extra` vão no cabeçalho
 * (ex.: o nome da regra do Data Quality); `actions` são os botões (subir, descer, excluir).
 */
export function listItem({ index, item, fields, body, setUi, actions = [], title = null, className = '' }) {
  const ui = item?._ui || {};
  const collapsed = Boolean(ui.collapsed);
  // Sem nome: recolhido mostra só o resumo; aberto mostra "sem nome" (ou o tipo, como a regra do Data Quality).
  const label = h('span', { class: ['li-name', !ui.name && !title && 'li-unnamed', !ui.name && !title && collapsed && 'li-empty'], title: 'Dois cliques para dar um nome' },
    ui.name || title || (collapsed ? '' : 'sem nome'));
  const rename = () => renameInline(label, ui.name, (name) => setUi({ name: name || undefined }));
  const toggle = button({
    icon: collapsed ? 'chevron-right' : 'chevron-down', size: 'sm', variant: 'ghost',
    title: collapsed ? 'Expandir este item' : 'Recolher este item', onClick: () => setUi({ collapsed: !collapsed }),
  });
  toggle.classList.add('li-toggle');
  toggle.setAttribute('aria-expanded', String(!collapsed));
  const summary = collapsed ? h('span', { class: 'li-summary mono' }, summarize(item, fields) || 'vazio') : null;
  const head = h('div', { class: 'list-item-head', title: collapsed ? 'Clique para expandir' : null },
    toggle,
    h('span', { class: 'list-item-index' }, `${index + 1}`),
    h('span', { class: 'li-title' }, label, ui.name && title ? h('small', { class: 'li-kind' }, title) : null, summary),
    h('span', { class: 'li-state' }),
    h('div', { class: 'row gap-0 li-actions' },
      button({ icon: 'edit', title: 'Dar um nome a este item (ou dois cliques no nome)', size: 'sm', variant: 'ghost', onClick: rename }),
      ...actions));
  // Dois cliques no título dão um nome; um clique no cartão recolhido expande (espera um instante para não brigar).
  let pending = null;
  head.addEventListener('dblclick', (e) => {
    if (e.target.closest('button, input')) return;
    clearTimeout(pending);
    rename();
  });
  if (collapsed) {
    head.addEventListener('click', (e) => {
      if (e.target.closest('button, input') || e.detail > 1) return;
      pending = setTimeout(() => setUi({ collapsed: false }), 230);
    });
  }
  body.classList.add('list-item-fields');
  body.hidden = collapsed;
  const card = h('div', { class: ['list-item', collapsed && 'collapsed', collapsed && (ui.name || title) && 'two-lines', className] }, head, body);
  watchErrors(body, card);
  return card;
}

/** "Recolher todos / Expandir todos" no topo da lista, a partir de dois itens. */
export function listToolbar(items, setAllUi) {
  if (items.length < 2) return null;
  const allCollapsed = items.every((it) => it?._ui?.collapsed);
  return h('div', { class: 'li-toolbar' },
    h('span', { class: 'field-help' }, `${items.length} itens`),
    button({
      icon: allCollapsed ? 'maximize' : 'minimize', label: allCollapsed ? 'Expandir todos' : 'Recolher todos', size: 'sm', variant: 'ghost',
      onClick: () => setAllUi({ collapsed: !allCollapsed }),
    }));
}

/** O item com o `_ui` atualizado (sem gravar chaves vazias). */
export function withUi(item, patch) {
  const ui = { ...(item?._ui || {}), ...patch };
  for (const k of Object.keys(ui)) if (ui[k] === undefined || ui[k] === false || ui[k] === '') delete ui[k];
  const next = { ...item };
  if (Object.keys(ui).length) next._ui = ui; else delete next._ui;
  return next;
}
