// Quem está editando (spec 047, RF-4721..4724): abrir um fluxo do espaço para editar ou só para ver, renovar a marca
// de edição enquanto ele está aberto, soltá-la ao fechar e a faixa "Aberto só para ver" com o botão Editar.

import { api } from './api.js';
import { button, h } from './dom.js';
import { icon } from './icons.js';
import { emit, loadWorkflow, on, store } from './store.js';
import { activeIndex, tabCount, tabInfo } from './tabs.js';
import { openDialog, toast, toastError } from './ui.js';

const RENEW_MS = 30000;
const held = new Set(); // "espaco|fluxo" das marcas que este computador segura agora
const keyOf = (spaceId, wid) => `${spaceId}|${wid}`;
let bar = null;

const since = (iso) => {
  const d = new Date(iso);
  const today = new Date().toDateString() === d.toDateString();
  const clock = d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
  return today ? `desde ${clock}` : `desde ${d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })}, ${clock}`;
};
const editingText = (e) => `${e.nome} está editando ${since(e.desde)}`;

/** "Ana está editando desde 10:32": abrir só para ver, editar mesmo assim ou desistir. */
function askConflict(editing, name) {
  return new Promise((resolve) => {
    let answer = null;
    const pick = (value) => { answer = value; close(); };
    const { close } = openDialog({
      title: 'Este fluxo está sendo editado',
      size: 'sm',
      body: h('div', { class: 'form' },
        h('p', { class: 'dialog-text' }, h('strong', {}, editingText(editing)), ` em "${name}".`),
        h('p', { class: 'field-help' }, 'Abrindo só para ver, você acompanha sem mexer e pode editar quando ficar livre. '
          + 'Editando mesmo assim, as duas versões podem divergir; nada se perde, mas alguém vai precisar juntar.')),
      actions: [
        button({ label: 'Cancelar', onClick: () => close() }),
        button({ label: 'Editar mesmo assim', variant: 'ghost', onClick: () => pick('editar') }),
        button({ label: 'Abrir só para ver', icon: 'eye', variant: 'primary', onClick: () => pick('ver') }),
      ],
      onClose: () => resolve(answer),
    });
  });
}

function setReadonly(value) {
  store.readonly = value;
  emit('readonly');
  emit('selection'); // o Configurar se redesenha com os campos desativados (ou não)
}

/** Abre um fluxo do espaço decidindo o modo. ``quiet``: sem perguntas (reabrir abas ao iniciar). */
export async function openSpaceFlow(space, workflowId, open, { quiet = false, autorun = true } = {}) {
  let res = await api.spaceEditing(space.id, workflowId, 'abrir');
  let readonly = null;
  if (res.modo === 'conflito') {
    const workflowName = res.nome || workflowId;
    const choice = quiet ? 'ver' : await askConflict(res.editando, workflowName);
    if (!choice) return false;
    if (choice === 'editar') res = await api.spaceEditing(space.id, workflowId, 'abrir', true);
    else readonly = { motivo: editingText(res.editando), editando: res.editando };
  } else if (res.modo === 'ver') {
    readonly = { motivo: res.motivo, editando: null, papel: true };
  }
  const workflow = await api.spaceFlow(space.id, workflowId);
  await open(workflow, { space: { id: space.id, nome: space.nome }, autorun });
  if (res.modo === 'editar') held.add(keyOf(space.id, workflowId));
  setReadonly(readonly);
  return true;
}

/** Botão Editar da faixa: tenta pegar a edição; se livre, recarrega a versão mais nova do espaço e libera. */
async function startEditing(force = false) {
  const { space, workflow } = store;
  if (!space || !workflow) return;
  try {
    const res = await api.spaceEditing(space.id, workflow.id, 'abrir', force);
    if (res.modo === 'conflito') {
      const choice = await askConflict(res.editando, workflow.name);
      if (choice === 'editar') await startEditing(true);
      return;
    }
    if (res.modo === 'ver') { toast('Você só pode ver este fluxo', { detail: res.motivo }); return; }
    const fresh = await api.spaceFlow(space.id, workflow.id); // o que estava aberto pode ter ficado para trás
    loadWorkflow(fresh, { saved: true });
    held.add(keyOf(space.id, workflow.id));
    setReadonly(null);
    toast('Agora você está editando', { kind: 'success', detail: 'Os outros veem o seu nome em "quem está editando".' });
  } catch (err) {
    toastError(err, 'Não foi possível começar a editar');
  }
}

function drawBar() {
  if (!bar) return;
  const ro = store.readonly;
  if (!ro) { bar.hidden = true; bar.replaceChildren(); return; }
  bar.hidden = false;
  const canTry = !ro.papel; // papel de Leitor ou pasta sem escrita: o botão não ajudaria
  bar.replaceChildren(h('div', { class: 'readonly-bar', role: 'status' },
    icon('eye', 15),
    h('div', { class: 'grow' }, h('strong', {}, 'Aberto só para ver'), h('span', {}, ` · ${ro.motivo}`)),
    canTry ? button({ icon: 'edit', label: ro.editando ? 'Editar mesmo assim' : 'Editar', size: 'sm', variant: ro.editando ? 'ghost' : 'primary',
      onClick: () => startEditing(Boolean(ro.editando)) }) : null));
}

/** Marcas que já não têm aba aberta são soltas (aba fechada); as abertas em edição são renovadas. */
function openEditKeys() {
  const keys = new Set();
  for (let i = 0; i < tabCount(); i += 1) {
    const t = tabInfo(i);
    if (t.space && t.id && !t.readonly) keys.add(keyOf(t.space.id, t.id));
  }
  return keys;
}

function reconcile() {
  const open = openEditKeys();
  for (const key of [...held]) {
    if (open.has(key)) continue;
    held.delete(key);
    const [spaceId, wid] = key.split('|');
    api.spaceEditing(spaceId, wid, 'soltar').catch(() => {});
  }
}

async function tick() {
  for (const key of [...held]) {
    const [spaceId, wid] = key.split('|');
    try {
      const res = await api.spaceEditing(spaceId, wid, 'renovar');
      if (!res.ok) {
        held.delete(key);
        if (store.space?.id === spaceId && store.workflow?.id === wid && res.editando) {
          toast('Outra pessoa começou a editar este fluxo', { detail: `${editingText(res.editando)}. Ao salvar, as duas versões ficam guardadas.` });
        }
      }
    } catch { /* sem rede agora: tenta de novo na próxima volta */ }
  }
  const ro = store.readonly;
  if (ro?.editando && store.space && store.workflow && activeIndex() >= 0) {
    try {
      const res = await api.spaceEditing(store.space.id, store.workflow.id, 'estado');
      if (!res.editando) setReadonly({ ...ro, editando: null, motivo: 'A edição ficou livre: clique em Editar para continuar daqui.' });
    } catch { /* tenta de novo */ }
  }
}

export function initTeamEditing(root) {
  bar = h('div', { class: 'readonly-host', hidden: true });
  root.append(bar);
  on('readonly', drawBar);
  on('workflow:loaded', drawBar);
  on('tabs', reconcile);
  let last = 0;
  on('readonly:blocked', () => {
    if (Date.now() - last < 4000) return;
    last = Date.now();
    toast('Aberto só para ver', { detail: store.readonly?.motivo || 'Este fluxo não pode ser mudado agora.' });
  });
  setInterval(tick, RENEW_MS);
  window.addEventListener('beforeunload', () => {
    for (const key of held) {
      const [spaceId, wid] = key.split('|');
      fetch(`/api/equipe/espacos/${encodeURIComponent(spaceId)}/fluxos/${encodeURIComponent(wid)}/edicao`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ acao: 'soltar' }), keepalive: true,
      }).catch(() => {});
    }
  });
}
