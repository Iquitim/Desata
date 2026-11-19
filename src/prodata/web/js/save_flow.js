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
import { emit, isDirty, markSaved, on, store } from './store.js';
import { showMenu, toast, toastError } from './ui.js';

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

async function write(path, silent) {
  const sent = JSON.stringify(store.workflow);
  saving = true;
  try {
    if (path) {
      const res = await api.saveWorkflowFile(path, store.workflow);
      store.filePath = res.path;
      rememberRecent(res.path, store.workflow.name);
      emit('file');
      settle(sent);
      if (!silent) toast('Fluxo salvo', { kind: 'success', detail: res.path });
    } else {
      const saved = await api.saveWorkflow(store.workflow);
      settle(sent);
      if (!silent) toast('Fluxo salvo', { kind: 'success', detail: `Biblioteca do ${brand.nome} · ${saved.id}.prodata.json` });
    }
    return true;
  } finally {
    saving = false;
  }
}

/** Salva a aba ativa (Ctrl+S, botão do topo). Devolve true se salvou. Um Salvar manual religa o automático. */
export async function saveFlow() {
  blocked = null;
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

export async function saveAs() {
  const path = await chooseSaveFile(`${fileSlug(store.workflow.name)}.prodata.json`, dirname(store.filePath));
  return path ? saveToFile(path) : false;
}

/** Por que o automático não vale para o fluxo aberto (ou null, se vale). */
export function autoBlockedReason() {
  if (!store.workflow) return 'nenhum fluxo aberto';
  if (!store.savedSnapshot && !store.filePath) return 'este fluxo ainda não foi salvo: use Salvar uma vez';
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
        { label: 'Salvar automaticamente', icon: autoOn ? 'check' : 'refresh', onSelect: () => setAutosave(!autoOn) },
        { note: autoOn && why ? `Neste fluxo não: ${why}.` : 'Grava sozinho a cada mudança, nos fluxos já salvos uma vez.' },
        'separator',
        { label: 'Salvar como…', icon: 'directory', shortcut: 'Ctrl+Shift+S', onSelect: () => saveAs() },
        { label: 'Salvar com amostra dos dados…', icon: 'database', onSelect: () => shareDialog() },
      ]);
    },
  });
  arrow.classList.add('save-arrow');
  const wrap = h('div', { class: 'save-split' }, main, arrow);
  const draw = () => {
    const active = autosaveActive();
    wrap.classList.toggle('auto', autoOn);
    wrap.classList.toggle('auto-off-here', autoOn && !active);
    const why = autoBlockedReason();
    main.title = !autoOn ? 'Salvar (Ctrl+S)'
      : active ? `Salvamento automático ligado${lastSaved ? ` · salvo às ${hhmm(lastSaved)}` : ''} (Ctrl+S salva agora)`
        : `Salvamento automático ligado, mas não neste fluxo: ${why} (Ctrl+S)`;
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
