// Recomendações de limpeza (spec 048, RF-4831..4835): no Perfil, cada problema comum vira uma linha com a contagem,
// exemplos "antes → depois" e Corrigir, que insere logo depois da caixa a ferramenta que já existe, configurada (um
// Desfazer volta). No canvas, só um ponto discreto na caixa onde o problema surge; nada abre sozinho e nada corrige sozinho.

import { api } from './api.js';
import { button, h, uid } from './dom.js';
import { icon } from './icons.js';
import { descendants, emit, inspect, mutate, node, on, select, store } from './store.js';
import { confirmDialog, toast } from './ui.js';

const SHOWN = 3;
const KIND_ICONS = { espacos: 'scissors', numero_texto: 'hash', data_texto: 'clock', caixa: 'type', texto_vazio: 'alert', linhas_repetidas: 'copy' };
const cache = new Map(); // "fluxo|caixa|porta|execução" → recomendações
let counts = {}; // caixa de entrada → quantas recomendações (o ponto no canvas)
const expanded = new Set();

let runSeq = 0; // muda a cada execução: as recomendações são do último resultado
const runStamp = () => runSeq;
const keyOf = (nodeId, anchor) => `${store.workflow?.id}|${nodeId}|${anchor}|${runStamp()}|${JSON.stringify(store.workflow?.ignored_cleaning?.[nodeId] || [])}`;

/** Quantas recomendações a caixa tem (o ponto discreto no canvas, onde o problema surge). */
export const cleaningCount = (nodeId) => counts[nodeId] || 0;

async function fetchFor(nodeId, anchor) {
  const key = keyOf(nodeId, anchor);
  if (!cache.has(key)) {
    cache.set(key, api.cleaningRecommend(store.workflow, nodeId, anchor).then((r) => (r.disponivel ? r.recomendacoes : [])).catch(() => []));
  }
  return cache.get(key);
}

const recKey = (r) => `${r.tipo}|${r.coluna}`;

/**
 * Depois de executar: o ponto no canvas fica na caixa onde cada problema surge. Uma caixa de entrada mostra todos;
 * uma caixa do meio, só os que as caixas antes dela não tinham (o mesmo problema herdado não repete o ponto). O
 * Perfil de qualquer caixa continua com a lista completa.
 */
async function refreshCounts() {
  const wf = store.workflow;
  if (!wf || !store.execution) { counts = {}; emit('cleaning'); return; }
  const results = store.execution.node_results || {};
  const tables = wf.nodes.filter((n) => {
    const spec = store.tools?.[n.type];
    return spec?.outputs?.some((p) => p.kind !== 'model') && !n.type.startsWith('bi.') && !n.disabled
      && ['executed', 'cached'].includes(results[n.id]?.status);
  });
  const found = new Map();
  const queue = [...tables];
  const worker = async () => { // poucas de cada vez: o servidor calcula sobre o resultado guardado
    while (queue.length) {
      const n = queue.shift();
      const anchor = store.tools[n.type].outputs.find((p) => p.kind !== 'model')?.id || 'out';
      found.set(n.id, new Set((await fetchFor(n.id, anchor)).map(recKey)));
    }
  };
  await Promise.all([worker(), worker(), worker(), worker()]);
  if (store.workflow !== wf) return;
  const next = {};
  for (const n of tables) {
    const mine = found.get(n.id) || new Set();
    const before = new Set(wf.edges.filter((e) => e.target === n.id).flatMap((e) => [...(found.get(e.source) || [])]));
    const fresh = [...mine].filter((k) => !before.has(k)).length;
    if (fresh) next[n.id] = fresh;
  }
  counts = next;
  emit('cleaning');
}

/** Insere a ferramenta logo depois da caixa, com os fios que saíam dela passando pela nova (um passo de Desfazer). */
function insertAfter(nodeId, port, fix) {
  const spec = store.tools[fix.tool];
  const src = node(nodeId);
  if (!spec || !src) return null;
  const id = uid('n');
  const input = spec.inputs.find((p) => p.kind !== 'model')?.id || 'in';
  const shift = 260;
  const after = new Set(descendants(nodeId));
  mutate((wf) => {
    for (const n of wf.nodes) if (after.has(n.id)) n.x += shift;
    wf.nodes.push({ id, type: fix.tool, label: spec.name, x: Math.round((src.x + shift) / 10) * 10, y: src.y,
      config: { ...structuredClone(spec.default_config), ...structuredClone(fix.config) } });
    for (const e of wf.edges) {
      if (e.source === nodeId && (e.sourceHandle || 'out') === port) { e.source = id; e.sourceHandle = fix.port || 'out'; }
    }
    wf.edges.push({ id: uid('e'), source: nodeId, sourceHandle: port, target: id, targetHandle: input });
  }, { affects: [id], structural: true });
  select(id);
  inspect(id);
  return spec.name;
}

async function fixIt(nodeId, anchor, rec) {
  const tool = store.tools[rec.correcao.tool]?.name || rec.correcao.tool;
  const ok = await confirmDialog({
    title: `Corrigir: ${rec.titulo}`,
    message: [
      `Insere uma caixa ${tool} logo depois de "${node(nodeId)?.label || 'esta caixa'}", já configurada, e liga o que vinha depois nela.`,
      rec.exemplos?.length ? `O que muda: ${rec.exemplos.slice(0, 3).map((x) => `${x.antes} → ${x.depois}`).join(' · ')}.` : '',
      'Um Desfazer volta.',
    ].filter(Boolean).join(' '),
    confirm: `Inserir ${tool}`,
  });
  if (!ok) return;
  const name = insertAfter(nodeId, anchor, rec.correcao);
  if (name) toast(`${name} inserida`, { kind: 'success', detail: 'Execute para ver o resultado. Ctrl+Z desfaz.' });
}

function ignore(nodeId, rec) {
  mutate((wf) => {
    wf.ignored_cleaning = wf.ignored_cleaning || {};
    const list = new Set(wf.ignored_cleaning[nodeId] || []);
    list.add(rec.id);
    wf.ignored_cleaning[nodeId] = [...list];
  }, { key: `cleaning:${nodeId}` });
  toast('Recomendação ignorada nesta coluna', { detail: 'Vale para quem abrir o fluxo depois. Ctrl+Z desfaz.' });
}

function row(nodeId, anchor, rec, readonly) {
  return h('li', { class: 'cl-item' },
    h('span', { class: 'cl-icon' }, icon(KIND_ICONS[rec.tipo] || 'sparkles', 14)),
    h('div', { class: 'cl-text' },
      h('strong', {}, rec.titulo),
      h('p', { class: 'muted small' }, rec.detalhe),
      rec.exemplos?.length ? h('div', { class: 'cl-examples' }, rec.exemplos.slice(0, 3).map((x) => h('span', { class: 'cl-example mono' },
        x.antes, h('span', { class: 'cl-arrow', 'aria-label': 'vira' }, '→'), x.depois))) : null),
    h('div', { class: 'cl-actions' },
      button({ icon: 'wand', label: 'Corrigir', size: 'sm', variant: 'primary', disabled: readonly, title: readonly ? 'Aberto só para ver' : 'Inserir a caixa que corrige, já configurada',
        onClick: () => fixIt(nodeId, anchor, rec) }),
      button({ label: 'Ignorar', size: 'sm', variant: 'ghost', disabled: readonly, title: 'Não mostrar de novo nesta coluna (fica gravado no fluxo)',
        onClick: () => ignore(nodeId, rec) })));
}

/** O cartão de recomendações no alto do Perfil (preenchido quando a resposta chega). */
export function cleaningCard() {
  const { nodeId, anchor } = store.inspect;
  const host = h('section', { class: 'cl-card', hidden: true, 'aria-label': 'Recomendações de limpeza' });
  if (!nodeId || !store.workflow) return host;
  const want = keyOf(nodeId, anchor || 'out');
  fetchFor(nodeId, anchor || 'out').then((recs) => {
    if (keyOf(nodeId, anchor || 'out') !== want || !recs.length) return;
    const all = expanded.has(want);
    host.hidden = false;
    host.replaceChildren(...[
      h('header', { class: 'cl-head' }, icon('sparkles', 15), h('strong', {}, recs.length === 1 ? '1 coisa para limpar' : `${recs.length} coisas para limpar`),
        h('span', { class: 'muted small' }, recs[0].amostra ? ' · contadas nas primeiras 200 mil linhas' : '')),
      h('ul', { class: 'cl-list' }, (all ? recs : recs.slice(0, SHOWN)).map((r) => row(nodeId, anchor || 'out', r, Boolean(store.readonly)))),
      recs.length > SHOWN ? button({ label: all ? 'Ver menos' : `Ver todas (${recs.length})`, size: 'sm', variant: 'ghost',
        onClick: () => { if (all) expanded.delete(want); else expanded.add(want); host.replaceWith(cleaningCard()); } }) : null].filter(Boolean)); // null viraria o texto "null"
  });
  return host;
}

export function initCleaning() {
  on('execution', () => { runSeq += 1; refreshCounts().catch(() => {}); });
  on('workflow:loaded', () => { counts = {}; emit('cleaning'); });
}
