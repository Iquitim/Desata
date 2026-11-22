// Salvar (spec 042, RF-4211..4213): botão próprio no topo, com a seta de Salvar automaticamente.
// O automático só grava fluxos que já foram salvos uma vez (biblioteca ou arquivo escolhido), nunca um fluxo em modo
// protegido, uma lição ou um exemplo aberto pelo Manual (esses abrem como "não salvos" até o primeiro Salvar).

import { api } from './api.js';
import { brand } from './brand.js';
import { chooseSaveFile, dirname } from './desktop.js';
import { button, debounce, h, persist, storage } from './dom.js';
import { icon } from './icons.js';
import { shareDialog } from './portable.js';
import { persistTabs } from './tabs.js';
import { isProtected } from './trust_banner.js';
import { emit, isDirty, markSaved, mutate, on, store } from './store.js';
import { openDialog, showMenu, toast, toastError } from './ui.js';
import { reloadFromSpace } from './team_editing.js';
import { chooseSpace, teamConfigured, teamState } from './team_spaces.js';
import { openVersionsDialog } from './versions_dialog.js';

export const RECENT_FILES = 'prodata.recentFiles';
const AUTO_KEY = 'prodata.autosave';
const AUTO_DELAY = 3000;
// O exemplo que abre com o programa fica na biblioteca, mas é do programa: nunca grava sozinho.
const EXAMPLES = new Set(['demo_pipeline_360']);

let autoOn = Boolean(storage(AUTO_KEY, false));
let lastSaved = null; // hora do último salvamento (automático ou não)
let blocked = null; // fluxo em que o automático falhou: desligado até o próximo Salvar manual
let saving = false;

/** Fluxos abertos/salvos fora da biblioteca, mais recentes primeiro (só neste computador). */
export function rememberRecent(path, name) {
  const items = storage(RECENT_FILES, []).filter((r) => r.path.toLowerCase() !== path.toLowerCase());
  persist(RECENT_FILES, [{ path, name, at: new Date().toISOString() }, ...items].slice(0, 8));
}

const flowKey = () => store.filePath || store.workflow?.id || '';

/** Marca como salvo o que foi enviado; uma mudança feita durante o envio continua "não salva". */
function settle(sent) {
  if (JSON.stringify(store.workflow) === sent) markSaved();
  else { store.savedSnapshot = sent; emit('dirty', isDirty()); }
  lastSaved = new Date();
  persistTabs();
  emit('tabs');
  emit('autosave');
}

async function write(path, silent, origin = silent ? 'auto' : 'manual') {
  const sent = JSON.stringify(store.workflow);
  saving = true;
  try {
    if (store.space && !path) {
      // Fluxo do espaço da equipe (spec 047): grava na pasta do espaço, nunca na biblioteca
      const space = store.space;
      let res;
      try {
        res = await api.saveSpaceFlow(space.id, store.workflow, { base: space.base, origem: SPACE_ORIGINS.has(origin) ? origin : 'manual' });
      } catch (err) {
        if (err.code !== 'conflict') throw err;
        if (silent) { blocked = flowKey(); emit('autosave'); } // o automático para até a pessoa escolher
        conflictDialog(err.message); // RF-4761: nada sobrescrito, as duas versões guardadas
        return false;
      }
      if (store.space === space) store.space = { ...space, base: res.sha256, nova: null, atualizado: null };
      settle(sent);
      emit('readonly');
      if (res.adiado) {
        toast('Salvo neste computador; o envio para o espaço fica para depois', { detail: 'A sincronização está segurando o arquivo. O programa tenta de novo sozinho, sem perder nada.' });
      } else if (!silent) toast('Fluxo salvo no espaço', { kind: 'success', detail: `Espaço da equipe "${space.nome}"` });
    } else if (path) {
      const res = await api.saveWorkflowFile(path, store.workflow, origin);
      store.filePath = res.path;
      rememberRecent(res.path, store.workflow.name);
      emit('file');
      settle(sent);
      if (!silent) toast('Fluxo salvo', { kind: 'success', detail: res.path });
    } else {
      const saved = await api.saveWorkflow(store.workflow, origin);
      settle(sent);
      if (!silent) toast('Fluxo salvo', { kind: 'success', detail: `Biblioteca do ${brand.nome} · ${saved.id}.prodata.json` });
    }
    return true;
  } finally {
    saving = false;
  }
}

const SPACE_ORIGINS = new Set(['manual', 'auto', 'restore']);

/** "Bruno salvou enquanto você editava" (RF-4761): ver as duas, ficar com a minha ou abrir a do colega. */
function conflictDialog(message) {
  const { close } = openDialog({
    title: 'Outra pessoa salvou este fluxo',
    size: 'sm',
    body: h('div', { class: 'form' },
      h('p', { class: 'dialog-text' }, message),
      h('p', { class: 'field-help' }, 'A sua versão está guardada em Versões anteriores, com o seu nome. Escolha qual fica como a versão do espaço; a outra continua guardada.')),
    actions: [
      button({ icon: 'clock', label: 'Ver as duas', variant: 'ghost', onClick: () => { close(); openVersionsDialog(); } }),
      button({ icon: 'refresh', label: 'Abrir a do colega', onClick: async () => {
        close();
        try { await reloadFromSpace(); toast('Agora você vê a versão do colega', { detail: 'A sua está em Versões anteriores.' }); } catch (err) { toastError(err, 'Não foi possível abrir'); }
      } }),
      button({ icon: 'save', label: 'Ficar com a minha', variant: 'primary', onClick: async () => {
        close();
        const sent = JSON.stringify(store.workflow);
        try {
          const res = await api.saveSpaceFlow(store.space.id, store.workflow, { forcar: true });
          store.space = { ...store.space, base: res.sha256, nova: null, atualizado: null };
          settle(sent);
          emit('readonly');
          toast('A sua versão ficou no espaço', { kind: 'success', detail: 'A do colega está em Versões anteriores.' });
        } catch (err) { toastError(err, 'Não foi possível salvar'); }
      } }),
    ],
  });
}

/**
 * Primeiro Salvar de um fluxo nunca salvo (spec 045): pergunta o nome, para a biblioteca não juntar fluxos chamados
 * "Novo fluxo". Devolve o nome, TO_FOLDER (a pessoa preferiu Salvar como…) ou null (cancelou).
 */
const TO_FOLDER = Symbol('pasta');
async function askFirstName() {
  let names = [];
  try { names = (await api.workflows()).map((w) => w.name.toLowerCase()); } catch { /* sem a lista, salva mesmo assim */ }
  return new Promise((resolve) => {
    let answer = null;
    const input = h('input', { class: 'input', value: store.workflow.name, 'aria-label': 'Nome do fluxo', maxlength: 120 });
    const warn = h('p', { class: 'field-help' });
    const check = () => {
      const name = input.value.trim();
      warn.textContent = !name ? 'Dê um nome ao fluxo.'
        : names.includes(name.toLowerCase()) ? 'Já existe um fluxo com esse nome na biblioteca: os dois continuam, cada um com o seu arquivo.' : '';
      ok.disabled = !name;
    };
    const finish = (value) => { answer = value; close(); };
    const ok = button({ icon: 'save', label: 'Salvar', variant: 'primary', onClick: () => finish(input.value.trim()) });
    input.addEventListener('input', check);
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && input.value.trim()) { e.preventDefault(); finish(input.value.trim()); } });
    const { close } = openDialog({
      title: 'Salvar o fluxo',
      size: 'sm',
      body: h('div', { class: 'form' },
        h('label', { class: 'field' }, h('span', { class: 'field-label' }, 'Nome do fluxo'), input, warn),
        h('p', { class: 'field-help' }, `Vai para a biblioteca do ${brand.nome}, em Arquivo › Abrir da biblioteca. Para guardar numa pasta sua (do projeto, da rede, do OneDrive), use Salvar numa pasta.`)),
      actions: [
        button({ icon: 'directory', label: 'Salvar numa pasta…', variant: 'ghost', onClick: () => finish(TO_FOLDER) }),
        button({ label: 'Cancelar', onClick: () => close() }),
        ok,
      ],
      onClose: () => resolve(answer),
    });
    check();
    requestAnimationFrame(() => { input.focus(); input.select(); });
  });
}

/** Salva a aba ativa (Ctrl+S, botão do topo). Devolve true se salvou. Um Salvar manual religa o automático. */
export async function saveFlow() {
  blocked = null;
  if (store.readonly) { toast('Aberto só para ver: nada para salvar', { detail: store.readonly.motivo }); return false; }
  if (!store.filePath && !store.savedSnapshot && store.workflow) {
    const name = await askFirstName();
    if (name === null) return false;
    if (name === TO_FOLDER) return saveAs();
    if (name !== store.workflow.name) mutate((wf) => { wf.name = name; }, { key: 'wf:name' });
  }
  try {
    return await write(store.filePath, false);
  } catch (err) {
    toastError(err, 'Não foi possível salvar');
    return false;
  }
}

export async function saveToFile(path) {
  blocked = null;
  try {
    return await write(path, false);
  } catch (err) {
    toastError(err, 'Não foi possível salvar');
    return false;
  }
}

const fileSlug = (name) => (name || 'fluxo').normalize('NFKD').replace(/[^\w-]+/g, '_').replace(/^_+|_+$/g, '') || 'fluxo';

const canPublish = () => {
  const space = store.space && teamState().espacos.find((s) => s.id === store.space.id);
  return Boolean(space && (space.papel === 'publicador' || space.papel === 'administrador'));
};

/** Publicar como oficial (spec 047, RF-4751): a versão salva no espaço vira a que os agendamentos rodam. */
async function publishOfficial() {
  if (isDirty()) {
    toast('Salve antes de publicar', { detail: 'A versão oficial é a que está salva no espaço; as mudanças não salvas ficariam de fora.' });
    return;
  }
  try {
    await api.publishOfficial(store.space.id, store.workflow.id);
    toast('Publicada como versão oficial', { kind: 'success', detail: 'Os agendamentos deste fluxo passam a rodar esta versão. A biblioteca do espaço mostra o selo.' });
  } catch (err) {
    toastError(err, 'Não foi possível publicar');
  }
}

/** Salvar no espaço da equipe…: grava uma cópia do fluxo aberto no espaço, e a aba passa a ser a do espaço. */
export async function saveToSpace() {
  const space = await chooseSpace('Salvar no espaço da equipe');
  if (!space) return false;
  let res;
  try {
    res = await api.saveSpaceFlow(space.id, store.workflow);
  } catch (err) {
    toastError(err, 'Não foi possível salvar no espaço');
    return false;
  }
  store.space = { id: space.id, nome: space.nome, base: res.sha256 };
  store.filePath = null;
  markSaved();
  persistTabs();
  emit('file');
  emit('tabs');
  toast(`Salvo no espaço "${space.nome}"`, { kind: 'success', detail: 'Daqui em diante, Salvar grava no espaço. A cópia que estava antes continua onde estava.' });
  return true;
}

export async function saveAs() {
  const path = await chooseSaveFile(`${fileSlug(store.workflow.name)}.prodata.json`, dirname(store.filePath));
  return path ? saveToFile(path) : false;
}

/** Por que o automático não vale para o fluxo aberto (ou null, se vale). */
export function autoBlockedReason() {
  if (!store.workflow) return 'nenhum fluxo aberto';
  if (!store.savedSnapshot && !store.filePath) return 'este fluxo ainda não foi salvo: use Salvar uma vez';
  if (store.readonly) return 'o fluxo está aberto só para ver';
  if (isProtected()) return 'o fluxo está em modo protegido';
  if (EXAMPLES.has(store.workflow.id)) return 'é o fluxo de exemplo (Salvar como faz a sua cópia)';
  if (store.workflow.id.startsWith('licao_')) return 'é o fluxo de uma lição';
  if (blocked && blocked === flowKey()) return 'houve um erro ao salvar: use Salvar para religar';
  return null;
}

export const autosaveActive = () => autoOn && !autoBlockedReason();

const autoTick = debounce(async () => {
  if (!autosaveActive() || !isDirty()) return;
  if (saving) { autoTick(); return; }
  const key = flowKey();
  try {
    await write(store.filePath, true);
  } catch (err) {
    blocked = key;
    emit('autosave');
    toastError(err, 'Salvamento automático desligado neste fluxo');
  }
}, AUTO_DELAY);

export function setAutosave(onOff) {
  if (onOff && autoBlockedReason()) return; // fluxo nunca salvo (ou protegido, exemplo, lição): não liga
  autoOn = Boolean(onOff);
  persist(AUTO_KEY, autoOn);
  emit('autosave');
  if (autoOn) autoTick();
}
export const autosaveOn = () => autoOn;

const hhmm = (d) => d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });

/** Botão Salvar do topo, com a seta do automático e o selo discreto quando ele está ligado. */
export function saveButton() {
  const main = button({ icon: 'save', variant: 'ghost', 'aria-label': 'Salvar', onClick: () => saveFlow() });
  main.classList.add('save-main');
  const badge = h('span', { class: 'save-auto-badge', 'aria-hidden': 'true' }, icon('refresh', 8));
  main.append(badge);
  const arrow = button({
    icon: 'chevron-down', variant: 'ghost', title: 'Salvar como, com amostra e automático', 'aria-label': 'Opções de salvar', 'aria-haspopup': 'menu',
    onClick: (e) => {
      const r = e.currentTarget.getBoundingClientRect();
      const why = autoBlockedReason();
      showMenu(Math.max(8, r.right - 270), r.bottom + 4, [
        // Só liga num fluxo que pode salvar sozinho (spec 045): o nunca salvo, o protegido, o exemplo e a lição não.
        { label: 'Salvar automaticamente', checked: autosaveActive(), disabled: Boolean(why), onSelect: () => setAutosave(!autoOn) },
        { note: why ? `Indisponível: ${why}.` : 'Grava sozinho a cada mudança, nos fluxos já salvos uma vez.' },
        'separator',
        { label: 'Salvar como…', icon: 'directory', shortcut: 'Ctrl+Shift+S', onSelect: () => saveAs() },
        { label: 'Salvar com amostra dos dados…', icon: 'database', onSelect: () => shareDialog() },
        // Só com algum espaço da equipe (spec 047, RF-4702): sem espaço, o menu é o de sempre.
        ...(teamConfigured() ? [{ label: 'Salvar no espaço da equipe…', icon: 'folder', disabled: Boolean(store.space), onSelect: () => saveToSpace() }] : []),
        // Versão oficial (RF-4751): só para fluxo do espaço e quem é Publicador ou Administrador
        ...(canPublish() ? [{ label: 'Publicar como oficial', icon: 'star', onSelect: () => publishOfficial() }] : []),
      ]);
    },
  });
  arrow.classList.add('save-arrow');
  const wrap = h('div', { class: 'save-split' }, main, arrow);
  const draw = () => {
    // O selo só aparece quando o fluxo aberto está de fato salvando sozinho (spec 045).
    const active = autosaveActive();
    wrap.classList.toggle('auto', active);
    wrap.classList.remove('auto-off-here');
    main.title = active ? `Salvamento automático ligado${lastSaved ? ` · salvo às ${hhmm(lastSaved)}` : ''} (Ctrl+S salva agora)` : 'Salvar (Ctrl+S)';
    // Com o automático cuidando do fluxo, o selo "não salvo" não pisca a cada mudança.
    const dirtyBadge = document.getElementById('dirtyBadge');
    if (dirtyBadge && active) dirtyBadge.hidden = true;
  };
  on('autosave', draw);
  on('workflow:loaded', draw);
  on('file', draw);
  on('dirty', (dirty) => { draw(); if (dirty) autoTick(); });
  draw();
  return wrap;
}
