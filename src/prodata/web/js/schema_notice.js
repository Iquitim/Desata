// Mudanças no formato das fontes (spec 046, RF-4601..4610): o fluxo lembra as colunas e os tipos de cada fonte e de
// cada saída; quando mudam, o aviso aparece na entrada (não na caixa que quebrou), com as caixas atingidas, a troca da
// coluna em todas as caixas e o "Entendi, usar o formato novo". O programa sugere e nunca troca sozinho.

import { api } from './api.js';
import { state } from './canvas_state.js';
import { button, fmt, h } from './dom.js';
import { icon } from './icons.js';
import { emit, isDirty, mutate, node, nodeResult, on, select, silently, store, toolOf } from './store.js';
import { isProtected } from './trust_banner.js';
import { openDialog, toast, toastError } from './ui.js';
import { versionsBlockedReason } from './versions_dialog.js';

const SOURCES = new Set(['io.input_data', 'io.input_folder', 'io.database_input']);
const OUTPUTS = new Set(['io.output_data']);
const TYPE_NAMES = { Int64: 'número inteiro', Float64: 'número', String: 'texto', Date: 'data', Datetime: 'data e hora', Boolean: 'sim/não' };
export const typeName = (t) => TYPE_NAMES[t] || t;
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
const nameOf = (id) => { const n = node(id); return n ? n.label || toolOf(n)?.name || n.type : id; };

export const schemaChange = (id) => {
  const n = node(id);
  return n && (SOURCES.has(n.type) || OUTPUTS.has(n.type)) ? nodeResult(id)?.extra?.schema_change || null : null;
};

// ---------------------------------------------------------------- lembrar (RF-4601)

/** Muda o fluxo sem passo de Desfazer. Num fluxo salvo, fica "não salvo" (o automático grava); nos outros, calado. */
function quietly(fn) {
  if (versionsBlockedReason() || isProtected()) { silently(fn); return; }
  fn(store.workflow);
  emit('dirty', isDirty());
}

const remembered = (wf, id, result) => ({ ports: result.extra.schema, seen_at: new Date().toISOString() });

/** Primeira leitura de uma fonte (ou primeira gravação de uma saída): só lembra, sem avisar. */
on('execution', () => {
  const wf = store.workflow;
  if (!wf) return;
  const learned = {};
  for (const n of wf.nodes) {
    if (!SOURCES.has(n.type) && !OUTPUTS.has(n.type)) continue;
    const res = nodeResult(n.id);
    if (!res?.extra?.schema || !['executed', 'cached'].includes(res.status) || wf.schemas?.[n.id]) continue;
    learned[n.id] = remembered(wf, n.id, res);
  }
  if (Object.keys(learned).length) quietly((w) => { w.schemas = { ...(w.schemas || {}), ...learned }; });
  if (lit.size) { lit.clear(); state.render(); }
});

/** "Entendi, usar o formato novo" (RF-4605): passa a lembrar o formato de agora. Desfazer volta. */
export function acceptFormat(id) {
  const res = nodeResult(id);
  if (!res?.extra?.schema) return;
  mutate((wf) => { wf.schemas = { ...(wf.schemas || {}), [id]: remembered(wf, id, res) }; }, { affects: [] });
  // o aviso some já: o resultado guardado deixa de trazer a diferença
  delete res.extra.schema_change;
  emit('execution');
  toast('Formato novo guardado', { kind: 'success', detail: 'Da próxima vez, as mudanças são comparadas com ele.' });
}

// ---------------------------------------------------------------- acender as caixas atingidas (RF-4603, RF-4655)

const lit = new Map(); // id -> colunas
export const driftHit = (id) => lit.get(id) || null;

export async function showAffected(sourceId, columns) {
  try {
    const found = await api.schemaImpact(store.workflow, sourceId, columns);
    lit.clear();
    for (const [column, { nodes, maybe }] of Object.entries(found)) {
      for (const id of [...nodes, ...maybe]) lit.set(id, [...(lit.get(id) || []), maybe.includes(id) && !nodes.includes(id) ? `${column}?` : column]);
    }
    state.render();
    if (!lit.size) toast('Nenhuma caixa usa essas colunas', { detail: 'O fluxo continua funcionando sem elas.' });
  } catch (err) {
    toastError(err, 'Não foi possível achar as caixas');
  }
}

export function clearAffected() {
  if (!lit.size) return;
  lit.clear();
  state.render();
}

/** Selo no canvas: a fonte (ou a saída) mudou de formato. */
export function driftBadge(n) {
  const change = schemaChange(n.id);
  if (!change) return null;
  const out = OUTPUTS.has(n.type);
  return h('span', {
    class: 'node-missing node-drift',
    title: out ? 'O arquivo desta saída mudou de formato em relação à última gravação.' : 'Esta fonte mudou de formato desde a última leitura: veja no Configurar.',
  }, icon('alert', 11), out ? 'saída mudou' : 'formato mudou');
}

// ---------------------------------------------------------------- aviso no Configurar (RF-4602..4606)

const chip = (text, kind) => h('span', { class: `drift-chip ${kind}` }, text);

export function schemaNotice(n) {
  const change = schemaChange(n.id);
  if (!change) return null;
  if (OUTPUTS.has(n.type)) return outputNotice(n, change);
  return h('div', { class: 'drift-block' }, sourceNotice(n, change), driftExplainer(n, change));
}

/** Como funciona (RF-4610): o formato lembrado e o de agora lado a lado, com o que entrou, saiu e mudou. */
function driftExplainer(n, change) {
  const before = store.workflow.schemas?.[n.id]?.ports?.out || [];
  const now = nodeResult(n.id)?.extra?.schema?.out || [];
  const retyped = new Map(change.retyped.map((r) => [r.name, r]));
  const renamedTo = new Map((change.renames || []).map((r) => [r.old, r.new]));
  const cell = (c, kind, note) => h('div', { class: `dx-col ${kind}` }, h('span', { class: 'dx-name' }, c.name),
    h('span', { class: 'dx-type' }, note || typeName(c.type)));
  const left = before.map((c) => cell(c, change.removed.includes(c.name) ? 'removed' : retyped.has(c.name) ? 'retyped' : '',
    renamedTo.has(c.name) ? `${typeName(c.type)} · talvez → ${renamedTo.get(c.name)}` : null));
  const right = now.map((c) => cell(c, change.added.includes(c.name) ? 'added' : retyped.has(c.name) ? 'retyped' : ''));
  return h('details', { class: 'explainer drift-explainer' },
    h('summary', { class: 'x-head' }, icon('info', 14), h('strong', {}, 'Como funciona'),
      h('span', { class: 'muted' }, 'o formato lembrado e o de agora'), h('span', { class: 'x-toggle' }, icon('chevron-right', 14))),
    h('div', { class: 'dx-grid' },
      h('div', { class: 'dx-side' }, h('div', { class: 'dx-head' }, 'Lembrado'), ...left),
      h('div', { class: 'dx-arrow' }, icon('chevron-right', 14)),
      h('div', { class: 'dx-side' }, h('div', { class: 'dx-head' }, 'Agora'), ...right)),
    h('p', { class: 'muted dx-caption' }, 'O fluxo guarda só os nomes e os tipos das colunas de cada fonte, nunca os valores. '
      + 'A cada execução, compara com o que veio: verde entrou, vermelho saiu, âmbar mudou de tipo. '
      + 'Nas execuções agendadas, uma coluna usada que sumiu para tudo antes de gravar qualquer arquivo.'));
}

const showValue = (v, type) => (['Int64', 'Float64'].includes(type) && v !== '' && !Number.isNaN(Number(v))
  ? fmt.number(Number(v), type === 'Int64' ? 0 : 2) : v);

function sourceNotice(n, change) {
  const affected = change.affected || {};
  const used = (c) => Object.keys(affected[c] || {}).length;
  const maybe = (c) => (change.maybe?.[c] || []).length;
  const stillUsed = change.removed.filter((c) => used(c));
  const watched = [...change.removed, ...change.retyped.map((r) => r.name)];
  const rows = [];
  if (change.added.length) {
    rows.push(h('div', { class: 'drift-row' }, h('span', { class: 'drift-label' }, plural(change.added.length, 'coluna nova', 'colunas novas')),
      h('div', { class: 'drift-chips' }, change.added.map((c) => chip(c, 'added')))));
  }
  for (const c of change.removed) {
    rows.push(h('div', { class: 'drift-row' },
      h('span', { class: 'drift-label' }, 'Sumiu'),
      h('div', { class: 'drift-item' }, chip(c, 'removed'),
        h('span', { class: 'drift-note' }, used(c) ? `usada em ${plural(used(c), 'caixa', 'caixas')}${maybe(c) ? ` (e talvez em ${plural(maybe(c), 'caixa SQL', 'caixas SQL')})` : ''}` : 'nenhuma caixa usa'),
        used(c) ? button({ icon: 'refresh', label: 'Trocar por…', size: 'sm', onClick: () => openSwapDialog(n.id, c) }) : null)));
  }
  for (const r of change.retyped) {
    rows.push(h('div', { class: 'drift-row' },
      h('span', { class: 'drift-label' }, 'Mudou de tipo'),
      h('div', { class: 'drift-item' }, chip(r.name, 'retyped'),
        h('span', { class: 'drift-note' }, `${typeName(r.old)} → ${typeName(r.new)}`,
          r.examples?.length ? `, por causa de ${r.examples.map((v) => `"${v}"`).join(', ')}` : '',
          used(r.name) ? ` · usada em ${plural(used(r.name), 'caixa', 'caixas')}` : ''))));
  }
  const total = new Set(watched.flatMap((c) => Object.keys(affected[c] || {}))).size;
  return h('div', { class: 'banner banner-warn drift-notice', role: 'status' },
    icon('alert', 15),
    h('div', { class: 'banner-body' },
      h('div', { class: 'drift-title' }, 'A fonte mudou de formato desde a última leitura'),
      h('div', { class: 'drift-rows' }, rows),
      h('div', { class: 'banner-detail' }, stillUsed.length
        ? 'Troque cada coluna que sumiu pela nova (vale em todas as caixas de uma vez, e um Desfazer volta), ou corrija a fonte.'
        : 'Nenhuma caixa depende das colunas que sumiram. Se o formato novo está certo, guarde-o.'),
      h('div', { class: 'banner-action drift-actions' },
        total ? button({ icon: 'target', label: `Mostrar ${plural(total, 'caixa atingida', 'caixas atingidas')}`, size: 'sm', onClick: () => showAffected(n.id, watched) }) : null,
        button({ icon: 'check', label: 'Entendi, usar o formato novo', size: 'sm', variant: stillUsed.length ? 'ghost' : 'primary', onClick: () => acceptFormat(n.id) }))));
}

function outputNotice(n, change) {
  const parts = Object.entries(change).map(([port, d]) => h('div', { class: 'drift-rows' },
    Object.keys(change).length > 1 ? h('strong', {}, `Entrada ${port}`) : null,
    d.added.length ? h('div', { class: 'drift-row' }, h('span', { class: 'drift-label' }, 'A mais'), h('div', { class: 'drift-chips' }, d.added.map((c) => chip(c, 'added')))) : null,
    d.removed.length ? h('div', { class: 'drift-row' }, h('span', { class: 'drift-label' }, 'A menos'), h('div', { class: 'drift-chips' }, d.removed.map((c) => chip(c, 'removed')))) : null,
    d.retyped.length ? h('div', { class: 'drift-row' }, h('span', { class: 'drift-label' }, 'Outro tipo'),
      h('div', { class: 'drift-chips' }, d.retyped.map((r) => chip(`${r.name}: ${typeName(r.old)} → ${typeName(r.new)}`, 'retyped')))) : null));
  return h('div', { class: 'banner banner-warn drift-notice', role: 'status' },
    icon('alert', 15),
    h('div', { class: 'banner-body' },
      h('div', { class: 'drift-title' }, 'O arquivo desta saída mudou de formato'),
      ...parts,
      h('div', { class: 'banner-detail' }, 'Quem consome este arquivo (um relatório, outro fluxo) pode quebrar. Em Avançado, dá para parar a execução quando isso acontecer.'),
      h('div', { class: 'banner-action' },
        button({ icon: 'check', label: 'Entendi, este é o formato certo', size: 'sm', onClick: () => acceptFormat(n.id) }))));
}

// ---------------------------------------------------------------- Trocar por… (RF-4604)

export function openSwapDialog(sourceId, column) {
  const change = schemaChange(sourceId);
  const res = nodeResult(sourceId);
  if (!change || !res?.extra?.schema?.out) return;
  const current = res.extra.schema.out;
  const old = (store.workflow.schemas?.[sourceId]?.ports?.out || []).find((c) => c.name === column);
  const hint = (change.renames || []).find((r) => r.old === column);
  const used = Object.keys(change.affected?.[column] || {});
  const ordered = [...current.filter((c) => change.added.includes(c.name)), ...current.filter((c) => !change.added.includes(c.name))];
  let chosen = hint?.new || null;
  const ok = button({ icon: 'refresh', label: `Trocar em ${plural(used.length, 'caixa', 'caixas')}`, variant: 'primary', disabled: !chosen });
  const list = h('div', { class: 'swap-list', role: 'radiogroup', 'aria-label': 'Coluna nova' }, ordered.map((c) => {
    const radio = h('input', { type: 'radio', name: 'swap-col', value: c.name, checked: c.name === chosen,
      onchange: () => { chosen = c.name; ok.disabled = false; } });
    return h('label', { class: ['swap-option', c.name === hint?.new && 'suggested'] }, radio,
      h('span', { class: 'swap-name' }, c.name),
      h('span', { class: ['swap-type', old && c.type !== old.type && 'differs'] }, typeName(c.type)),
      c.name === hint?.new ? h('span', { class: 'swap-values' }, hint.values.map((v) => showValue(v, hint.type)).join(' · ') || '(vazia)') : null,
      c.name === hint?.new ? h('span', { class: 'swap-badge' }, 'sugerida') : change.added.includes(c.name) ? h('span', { class: 'swap-badge new' }, 'nova') : null);
  }));
  const { close } = openDialog({
    title: `Trocar a coluna ${column}`,
    size: 'md',
    body: h('div', { class: 'form' },
      h('p', { class: 'dialog-text' }, `"${column}" (${old ? typeName(old.type) : 'tipo desconhecido'}) sumiu de ${nameOf(sourceId)} e é usada em `,
        h('strong', {}, used.map(nameOf).join(', ')), '. Escolha a coluna que ocupa o lugar dela:'),
      list,
      h('p', { class: 'field-help' }, hint
        ? 'A sugerida tem o mesmo tipo da que sumiu. Confira pelos primeiros valores: o formato lembrado guarda só nomes e tipos, nunca valores.'
        : 'Nenhuma coluna nova tem o mesmo tipo da que sumiu: escolha com cuidado.'),
      h('p', { class: 'field-help' }, 'Antes da troca, a versão de agora fica guardada em Versões anteriores. Um Desfazer volta tudo de uma vez.')),
    actions: [button({ label: 'Cancelar', onClick: () => close() }), ok],
  });
  ok.addEventListener('click', async () => {
    ok.disabled = true;
    try {
      await swapColumn(sourceId, column, chosen);
      close();
    } catch (err) {
      toastError(err, 'Não foi possível trocar a coluna');
      ok.disabled = false;
    }
  });
}

/** A troca é feita pelo motor e aplicada aqui num passo só de Desfazer. */
export async function swapColumn(sourceId, column, chosen) {
  if (!versionsBlockedReason()) {
    await api.recordVersion(store.workflow.id, store.workflow, 'columns', store.filePath || null);
  }
  const r = await api.schemaRename(store.workflow, sourceId, column, chosen);
  const byId = new Map(r.workflow.nodes.map((n) => [n.id, n]));
  mutate((wf) => {
    for (const n of wf.nodes) if (r.changed.includes(n.id)) n.config = byId.get(n.id).config;
  }, { affects: r.changed });
  clearAffected();
  select(sourceId);
  toast(`"${column}" trocada por "${chosen}"`, {
    kind: 'success',
    detail: `${plural(r.changed.length, 'caixa mudou', 'caixas mudaram')}.${r.maybe.length ? ` Confira o texto das caixas SQL: ${r.maybe.map(nameOf).join(', ')}.` : ''} Execute para conferir.`,
  });
}
