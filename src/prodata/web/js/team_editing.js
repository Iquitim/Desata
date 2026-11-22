// Quem está editando (spec 047, RF-4721..4724): abrir um fluxo do espaço para editar ou só para ver, renovar a marca
// de edição enquanto ele está aberto, soltá-la ao fechar e a faixa "Aberto só para ver" com o botão Editar.

import { api } from './api.js';
import { button, h } from './dom.js';
import { icon } from './icons.js';
import { emit, isDirty, loadWorkflow, on, store } from './store.js';
import { activeIndex, tabCount, tabInfo } from './tabs.js';
import { openDialog, toast, toastError } from './ui.js';
import { openVersionsDialog } from './versions_dialog.js';

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
  const got = await api.spaceFlow(space.id, workflowId);
  // base: o que foi aberto, para o Salvar descobrir se outra pessoa salvou depois (RF-4761)
  await open(got.fluxo, { space: { id: space.id, nome: space.nome, base: got.sha256, atualizado: got.atualizado || null }, autorun });
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
    await reloadFromSpace(); // o que estava aberto pode ter ficado para trás
    held.add(keyOf(space.id, workflow.id));
    setReadonly(null);
    toast('Agora você está editando', { kind: 'success', detail: 'Os outros veem o seu nome em "quem está editando".' });
  } catch (err) {
    toastError(err, 'Não foi possível começar a editar');
  }
}

const ago = (iso) => {
  const min = Math.max(0, Math.round((Date.now() - new Date(iso)) / 60000));
  if (min < 1) return 'agora há pouco';
  if (min < 60) return `há ${min} min`;
  return since(iso);
};

/** Troca o que está aberto pela versão de trabalho do espaço (com a nova base). Desfazer não volta para a antiga. */
export async function reloadFromSpace() {
  const { space, workflow } = store;
  if (!space || !workflow) return;
  const got = await api.spaceFlow(space.id, workflow.id);
  for (const n of got.fluxo.nodes) n.config = { ...structuredClone(store.tools?.[n.type]?.default_config || {}), ...n.config };
  store.space = { ...space, base: got.sha256, atualizado: null, nova: null };
  loadWorkflow(got.fluxo, { saved: true });
  emit('readonly');
}

/** Recarregar (RF-4733): com mudanças não salvas, nada é trocado sem a pessoa pedir; e o que ela fez vira versão. */
async function reload() {
  const { space, workflow } = store;
  if (!space || !workflow) return;
  try {
    if (isDirty()) {
      const ok = await new Promise((resolve) => {
        let answer = false;
        const { close } = openDialog({
          title: 'Recarregar a versão do espaço?',
          size: 'sm',
          body: h('p', { class: 'dialog-text' }, 'Você tem mudanças não salvas. Elas ficam guardadas em Versões anteriores, '
            + 'e o fluxo passa a mostrar a versão nova do espaço.'),
          actions: [
            button({ label: 'Cancelar', onClick: () => close() }),
            button({ icon: 'refresh', label: 'Guardar as minhas e recarregar', variant: 'primary', onClick: () => { answer = true; close(); } }),
          ],
          onClose: () => resolve(answer),
        });
      });
      if (!ok) return;
      if (!store.readonly) await api.recordSpaceVersion(space.id, workflow.id, workflow);
    }
    await reloadFromSpace();
    toast('Fluxo recarregado', { kind: 'success', detail: 'Agora você vê a versão mais nova do espaço.' });
  } catch (err) {
    toastError(err, 'Não foi possível recarregar');
  }
}

/** Faixa de novidade: alguém salvou enquanto o fluxo está aberto (Recarregar) ou desde a última vez (Ver o que mudou). */
function newsBar() {
  const sp = store.space;
  if (!sp) return null;
  const dismiss = () => { store.space = { ...sp, atualizado: null }; drawBar(); };
  if (sp.nova) {
    return h('div', { class: 'readonly-bar news-bar', role: 'status' },
      icon('refresh', 15),
      h('div', { class: 'grow' }, h('strong', {}, `${sp.nova.nome} salvou uma versão nova`), h('span', {}, ` ${ago(sp.nova.quando)}`)),
      button({ icon: 'refresh', label: 'Recarregar', size: 'sm', variant: 'primary', onClick: reload }));
  }
  if (sp.atualizado) {
    const versao = sp.atualizado.versao_vista;
    return h('div', { class: 'readonly-bar news-bar', role: 'status' },
      icon('clock', 15),
      h('div', { class: 'grow' }, h('strong', {}, `Atualizado por ${sp.atualizado.nome}`), h('span', {}, ` ${ago(sp.atualizado.quando)}`)),
      versao ? button({ icon: 'eye', label: 'Ver o que mudou', size: 'sm', variant: 'ghost',
        onClick: () => { dismiss(); openVersionsDialog({ choose: versao }); } }) : null,
      button({ icon: 'x', size: 'sm', variant: 'ghost', 'aria-label': 'Fechar o aviso', onClick: dismiss }));
  }
  return null;
}

function drawBar() {
  if (!bar) return;
  const ro = store.readonly;
  const news = newsBar();
  if (!ro && !news) { bar.hidden = true; bar.replaceChildren(); return; }
  if (!ro) { bar.hidden = false; bar.replaceChildren(news); placeBar(); return; }
  bar.hidden = false;
  const canTry = !ro.papel; // papel de Leitor ou pasta sem escrita: o botão não ajudaria
  bar.replaceChildren(h('div', { class: 'readonly-bar', role: 'status' },
    icon('eye', 15),
    h('div', { class: 'grow' }, h('strong', {}, 'Aberto só para ver'), h('span', {}, ` · ${ro.motivo}`)),
    canTry ? button({ icon: 'edit', label: ro.editando ? 'Editar mesmo assim' : 'Editar', size: 'sm', variant: ro.editando ? 'ghost' : 'primary',
      onClick: () => startEditing(Boolean(ro.editando)) }) : null), ...(news ? [news] : []));
  placeBar();
}

/** As faixas da equipe ficam logo abaixo da faixa de confiança, quando ela aparece (as duas no topo do canvas). */
function placeBar() {
  const trust = document.querySelector('.trust-host');
  const below = trust && !trust.hidden ? trust.offsetHeight + 8 : 0;
  bar.style.top = below ? `${10 + below}px` : '';
}

/** Versão de trabalho do espaço diferente da que está aberta, salva por outra pessoa: oferece Recarregar. */
function noticeVersion(versao) {
  const sp = store.space;
  if (!sp || !versao || versao.minha || !sp.base || versao.sha256 === sp.base) return;
  if (sp.nova?.sha256 === versao.sha256) return;
  store.space = { ...sp, nova: versao, atualizado: null };
  drawBar();
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
  const activeKey = store.space && store.workflow ? keyOf(store.space.id, store.workflow.id) : null;
  let activeVersion;
  for (const key of [...held]) {
    const [spaceId, wid] = key.split('|');
    try {
      const res = await api.spaceEditing(spaceId, wid, 'renovar');
      if (key === activeKey) activeVersion = res.versao;
      if (res.enviados?.length) {
        toast('Enviado para o espaço', { kind: 'success', detail: 'O que a sincronização tinha segurado já está na pasta do espaço.' });
      }
      if (!res.ok) {
        held.delete(key);
        if (store.space?.id === spaceId && store.workflow?.id === wid && res.editando) {
          toast('Outra pessoa começou a editar este fluxo', { detail: `${editingText(res.editando)}. Ao salvar, as duas versões ficam guardadas.` });
        }
      }
    } catch { /* sem rede agora: tenta de novo na próxima volta */ }
  }
  const ro = store.readonly;
  if (activeKey && activeVersion === undefined && activeIndex() >= 0) {
    try {
      const res = await api.spaceEditing(store.space.id, store.workflow.id, 'estado');
      activeVersion = res.versao;
      if (ro?.editando && !res.editando) setReadonly({ ...ro, editando: null, motivo: 'A edição ficou livre: clique em Editar para continuar daqui.' });
    } catch { /* tenta de novo */ }
  }
  if (activeKey === (store.space && store.workflow ? keyOf(store.space.id, store.workflow.id) : null)) noticeVersion(activeVersion);
}

export function initTeamEditing(root) {
  bar = h('div', { class: 'readonly-host', hidden: true });
  root.append(bar);
  const trust = document.querySelector('.trust-host');
  if (trust && window.ResizeObserver) new ResizeObserver(() => { if (!bar.hidden) placeBar(); }).observe(trust);
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
