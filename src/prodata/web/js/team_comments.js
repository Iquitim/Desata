// Comentários nas caixas (spec 048, RF-4811..4816): selo na caixa, a conversa num painel ao lado do canvas, todos os
// comentários do fluxo e "N novos". Só em fluxos do espaço da equipe; fora dele, nada daqui aparece.

import { api } from './api.js';
import { button, h } from './dom.js';
import { icon } from './icons.js';
import { emit, on, select, store } from './store.js';
import { toast, toastError } from './ui.js';

const REFRESH_MS = 45000;
let data = null; // { spaceId, wid, conversas, por_caixa, novos, papel }
let host = null;
let chip = null;
const panel = { open: false, nodeId: null, replying: null, editing: null };
const drafts = new Map(); // o que a pessoa está escrevendo sobrevive aos redesenhos (a conversa recarrega sozinha)

const current = () => (store.space && store.workflow ? { spaceId: store.space.id, wid: store.workflow.id } : null);
const mine = () => (data && current() && data.spaceId === current().spaceId && data.wid === current().wid ? data : null);

/** Comentários abertos de uma caixa (o selo no canvas). */
export const commentCount = (nodeId) => mine()?.por_caixa?.[nodeId] || 0;
export const newComments = () => mine()?.novos || 0;

async function load({ seen = false } = {}) {
  const at = current();
  if (!at) { data = null; draw(); return; }
  try {
    const res = await api.comments(at.spaceId, at.wid, seen);
    const still = current();
    if (!still || still.spaceId !== at.spaceId || still.wid !== at.wid) return;
    data = { ...at, ...res };
  } catch { data = null; }
  emit('comments');
  draw();
}

async function send(body, okText) {
  const at = current();
  if (!at) return false;
  try {
    const res = await api.addComment(at.spaceId, at.wid, body);
    data = { ...at, ...res };
    panel.replying = null;
    panel.editing = null;
    emit('comments');
    draw();
    if (okText) toast(okText, { kind: 'success' });
    return true;
  } catch (err) { toastError(err, 'Não foi possível comentar'); return false; }
}

/** Menu da caixa: Comentar (só num fluxo do espaço). */
export function commentItems(nodeId) {
  if (!store.space) return [];
  return [{ label: commentCount(nodeId) ? `Comentários (${commentCount(nodeId)})` : 'Comentar', icon: 'chat', onSelect: () => openComments(nodeId) }];
}

export function openComments(nodeId = null) {
  panel.open = true;
  panel.nodeId = nodeId;
  panel.replying = null;
  if (nodeId) select(nodeId);
  load({ seen: true });
  draw();
  // a caixa comentada fica à vista, à esquerda do painel
  if (nodeId) requestAnimationFrame(() => emit('reveal:node', { id: nodeId, reserve: (host?.offsetWidth || 0) + 20 }));
}

const when = (iso) => {
  const d = new Date(iso);
  const today = new Date().toDateString() === d.toDateString();
  const clock = d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
  return today ? `hoje, ${clock}` : `${d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })}, ${clock}`;
};

const nodeLabel = (id, fallback) => {
  const n = store.workflow?.nodes.find((x) => x.id === id);
  if (!n) return `${fallback || 'caixa'} (caixa removida)`;
  return n.label || store.tools?.[n.type]?.name || n.type;
};

function composer({ key, placeholder, initial = '', submit, cancel }) {
  const area = h('textarea', { class: 'input cm-input', rows: 3, maxlength: 2000, placeholder, 'aria-label': placeholder }, drafts.get(key) ?? initial);
  area.addEventListener('input', () => drafts.set(key, area.value));
  const go = async () => {
    const text = area.value.trim();
    if (!text) return;
    drafts.delete(key); // antes de enviar: o redesenho depois do envio já vem vazio
    if (!(await submit(text))) drafts.set(key, text);
  };
  area.addEventListener('keydown', (e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); go(); } });
  const focused = document.activeElement?.dataset?.draft === key;
  area.dataset.draft = key;
  if (focused || !drafts.has(key)) requestAnimationFrame(() => { area.focus(); area.setSelectionRange(area.value.length, area.value.length); });
  return h('div', { class: 'cm-composer' }, area,
    h('div', { class: 'row cm-composer-actions' },
      h('span', { class: 'muted small grow' }, 'Ctrl+Enter envia'),
      cancel ? button({ label: 'Cancelar', size: 'sm', variant: 'ghost', onClick: cancel }) : null,
      button({ icon: 'chat', label: 'Enviar', size: 'sm', variant: 'primary', onClick: go })));
}

function message(item, thread) {
  const isThread = item === thread;
  const admin = data?.papel === 'administrador';
  const editing = panel.editing === item.id;
  return h('div', { class: ['cm-msg', !isThread && 'reply'] },
    h('div', { class: 'cm-meta' }, h('strong', {}, item.nome), h('span', { class: 'muted' }, ` · ${when(item.quando)}${item.editado ? ' · editado' : ''}`)),
    editing
      ? composer({ key: `edit:${item.id}`, placeholder: 'Editar o comentário', initial: item.texto, submit: (texto) => send({ tipo: 'editar', alvo: item.id, texto }), cancel: () => { panel.editing = null; draw(); } })
      : h('p', { class: 'cm-text' }, item.texto),
    !editing && (item.minha || admin) ? h('div', { class: 'cm-msg-actions' },
      item.minha ? button({ label: 'Editar', size: 'sm', variant: 'ghost', onClick: () => { panel.editing = item.id; draw(); } }) : null,
      button({ label: 'Apagar', size: 'sm', variant: 'ghost', onClick: () => send({ tipo: 'apagar', alvo: item.id }) })) : null);
}

function threadEl(t) {
  const fresh = new Set(data?.novos_ids || []);
  const isNew = fresh.has(t.id) || t.respostas.some((r) => fresh.has(r.id));
  return h('article', { class: ['cm-thread', t.resolvido && 'resolved', isNew && 'new'] },
    panel.nodeId ? null : h('button', { type: 'button', class: 'cm-box', title: 'Selecionar a caixa', onclick: () => select(t.caixa) },
      icon('workflow', 12), nodeLabel(t.caixa, t.rotulo)),
    isNew ? h('span', { class: 'cm-new' }, 'novo') : null,
    message(t, t),
    t.respostas.map((r) => message(r, t)),
    t.resolvido ? h('p', { class: 'muted small' }, `Resolvido por ${t.resolvido_por}.`) : null,
    panel.replying === t.id
      ? composer({ key: `reply:${t.id}`, placeholder: 'Responder', submit: (texto) => send({ tipo: 'resposta', alvo: t.id, texto }), cancel: () => { panel.replying = null; draw(); } })
      : h('div', { class: 'cm-thread-actions' },
        t.resolvido ? null : button({ label: 'Responder', size: 'sm', variant: 'ghost', onClick: () => { panel.replying = t.id; draw(); } }),
        button({ icon: t.resolvido ? 'undo' : 'check', label: t.resolvido ? 'Reabrir' : 'Resolver', size: 'sm', variant: 'ghost',
          onClick: () => send({ tipo: t.resolvido ? 'reabrir' : 'resolver', alvo: t.id }) })));
}

function draw() {
  drawChip();
  if (!host) return;
  if (!panel.open || !current()) { host.hidden = true; host.replaceChildren(); return; }
  host.hidden = false;
  const all = mine()?.conversas || [];
  const shown = panel.nodeId ? all.filter((t) => t.caixa === panel.nodeId) : all;
  const open = shown.filter((t) => !t.resolvido);
  const done = shown.filter((t) => t.resolvido);
  const title = panel.nodeId ? `Comentários · ${nodeLabel(panel.nodeId)}` : `Comentários do fluxo (${all.filter((t) => !t.resolvido).length})`;
  host.replaceChildren(h('aside', { class: 'cm-panel', role: 'complementary', 'aria-label': title },
    h('header', { class: 'cm-head' }, icon('chat', 16), h('strong', { class: 'grow' }, title),
      panel.nodeId ? button({ label: 'Todas', size: 'sm', variant: 'ghost', title: 'Os comentários de todas as caixas', onClick: () => { panel.nodeId = null; draw(); } }) : null,
      button({ icon: 'x', size: 'sm', variant: 'ghost', 'aria-label': 'Fechar os comentários', onClick: () => { panel.open = false; draw(); } })),
    h('div', { class: 'cm-body' },
      open.length || done.length ? null : h('p', { class: 'muted cm-empty' }, panel.nodeId
        ? 'Nenhum comentário nesta caixa ainda. Pergunte ou anote algo para quem abrir o fluxo depois.'
        : 'Nenhum comentário neste fluxo. Clique com o botão direito numa caixa e escolha Comentar.'),
      open.map(threadEl),
      done.length ? h('details', { class: 'cm-done' }, h('summary', {}, `Resolvidos (${done.length})`), done.map(threadEl)) : null),
    panel.nodeId ? h('footer', { class: 'cm-foot' }, composer({
      key: `new:${panel.nodeId}`,
      placeholder: 'Escreva um comentário nesta caixa',
      submit: (texto) => send({ tipo: 'comentario', caixa: panel.nodeId, rotulo: nodeLabel(panel.nodeId), texto }, 'Comentário enviado'),
    })) : null));
}

/** O botão "Comentários (3)" sobre o canvas, com o selo de novos. */
function drawChip() {
  if (!chip) return;
  const d = mine();
  const open = d ? d.conversas.filter((t) => !t.resolvido).length : 0;
  if (!current() || (!open && !d?.novos)) { chip.hidden = true; chip.replaceChildren(); return; }
  chip.hidden = false;
  chip.replaceChildren(h('button', { type: 'button', class: ['cm-chip', d.novos && 'has-new'], title: 'Comentários do fluxo', onclick: () => openComments(null) },
    icon('chat', 14), `Comentários (${open})`, d.novos ? h('span', { class: 'cm-chip-new' }, `${d.novos} ${d.novos === 1 ? 'novo' : 'novos'}`) : null));
}

export function initTeamComments(root) {
  host = h('div', { class: 'cm-host', hidden: true });
  chip = h('div', { class: 'cm-chip-host', hidden: true });
  root.append(host, chip);
  on('workflow:loaded', () => { panel.open = false; data = null; draw(); load(); });
  on('tabs', () => { if (!mine()) load(); });
  setInterval(() => { if (current() && document.visibilityState === 'visible') load({ seen: panel.open }); }, REFRESH_MS);
}
