// Menus do topo (spec 029, RF-2981): Arquivo e Exibir, com texto, e os comandos que a busca (Ctrl+K) também usa.
// O botão de tema fica fora dos menus, à vista no topo.

import { shareDialog } from './portable.js';
import { openScheduleDialog } from './schedule_dialog.js';
import { NUMBER_STYLES, button, getNumberStyle, setNumberStyle } from './dom.js';
import { icon } from './icons.js';
import { densityMenuItem, panelMenuItems, resetLayout } from './layout.js';
import { emit, store } from './store.js';
import { showMenu } from './ui.js';
export { isStopping, stopRun } from './run_stop.js'; // o Executar vira Parar enquanto roda (spec 041)
import { setTiming, timingOn } from './node_timing.js';
import { setSummary, summaryShown } from './table_tools.js';
import { allContainers, collapseDisabled, setContainersCollapsed } from './canvas_collapse.js';
import { setWireMode, wireMode } from './canvas_wires.js';
import { organizeFlow } from './canvas_layout.js';
import { fitView } from './canvas.js';

export { slowestNote } from './node_timing.js';

function menuButton(label, iconName, items) {
  // o ícone só aparece em janela estreita, quando o texto sai (o nome continua no título e no leitor de tela)
  const el = button({
    icon: iconName, label, title: label, 'aria-label': label, variant: 'ghost', 'aria-haspopup': 'menu',
    onClick: (e) => {
      const r = e.currentTarget.getBoundingClientRect();
      showMenu(r.left, r.bottom + 4, items());
    },
  });
  el.classList.add('top-menu');
  el.append(icon('chevron-down', 13));
  return el;
}

const fileItems = (a) => [
  { label: 'Novo fluxo', icon: 'file-plus', onSelect: a.newWorkflow },
  'separator',
  { label: 'Abrir da biblioteca…', icon: 'folder', shortcut: 'Ctrl+O', onSelect: a.openLibrary },
  { label: 'Abrir arquivo…', icon: 'file', onSelect: () => a.openFile() },
  'separator',
  { label: 'Salvar', icon: 'save', shortcut: 'Ctrl+S', onSelect: a.save },
  { label: 'Salvar como…', icon: 'directory', shortcut: 'Ctrl+Shift+S', onSelect: a.saveAs },
  { label: 'Salvar com amostra dos dados…', icon: 'database', onSelect: () => shareDialog() },
  'separator',
  { label: 'Executar sem abrir o programa…', icon: 'clock', onSelect: openScheduleDialog },
];

const viewItems = (a) => [
  { heading: 'Painéis' },
  ...panelMenuItems(),
  { label: a.inFocus() ? 'Sair do modo foco' : 'Modo foco', icon: 'maximize', shortcut: 'F11', disabled: store.view !== 'designer', onSelect: a.toggleFocus },
  'separator',
  densityMenuItem(),
  { heading: 'Canvas' },
  { label: 'Organizar o fluxo', icon: 'columns', disabled: store.view !== 'designer' || !store.workflow?.nodes.length, onSelect: () => { organizeFlow(); requestAnimationFrame(() => fitView()); } },
  { label: 'Fios organizados', icon: wireMode() === 'routed' ? 'check' : null, onSelect: () => setWireMode('routed') },
  { label: 'Fios curvos', icon: wireMode() === 'curved' ? 'check' : null, onSelect: () => setWireMode('curved') },
  { label: 'Recolher todas as etapas', icon: 'minimize', disabled: !allContainers().length, onSelect: () => setContainersCollapsed(allContainers(), true) },
  { label: 'Expandir todas as etapas', icon: 'maximize', disabled: !allContainers().length, onSelect: () => setContainersCollapsed(allContainers(), false) },
  { label: 'Recolher as caixas desativadas', icon: 'power', disabled: !store.workflow?.nodes.some((n) => n.disabled), onSelect: collapseDisabled },
  { label: 'Tempo nas caixas', icon: timingOn() ? 'check' : 'clock', onSelect: () => setTiming(!timingOn()) },
  { label: 'Resumo das colunas na tabela', icon: summaryShown() ? 'check' : 'chart', onSelect: () => setSummary(!summaryShown()) },
  { heading: 'Números' },
  ...Object.entries(NUMBER_STYLES).map(([style, sample]) => ({
    label: style === 'virgula' ? `${sample} · vírgula decimal` : `${sample} · ponto decimal`,
    icon: getNumberStyle() === style ? 'check' : null,
    onSelect: () => { setNumberStyle(style); emit('numbers'); },
  })),
  'separator',
  { label: 'Atalhos do teclado', icon: 'keyboard', shortcut: '?', onSelect: a.shortcuts },
  { label: 'Restaurar layout padrão', icon: 'refresh', onSelect: resetLayout },
];

/** Os menus do topo. `a`: as ações do programa, montadas em main.js. */
export const topMenus = (a) => [menuButton('Arquivo', 'file', () => fileItems(a)), menuButton('Exibir', 'eye', () => viewItems(a))];

/** O que a busca oferece como "Ações". */
export const commandList = (a) => [
  { name: 'Executar', detail: 'o fluxo inteiro', icon: 'play', end: 'Ctrl+Enter', keywords: 'rodar processar', run: a.run },
  { name: 'Salvar', detail: 'o fluxo aberto', icon: 'save', end: 'Ctrl+S', keywords: 'gravar', run: a.save },
  { name: 'Salvar como…', detail: 'escolher a pasta', icon: 'directory', end: 'Ctrl+Shift+S', keywords: 'gravar copia', run: a.saveAs },
  { name: 'Novo fluxo', icon: 'file-plus', keywords: 'criar', run: a.newWorkflow },
  { name: 'Abrir da biblioteca…', icon: 'folder', end: 'Ctrl+O', keywords: 'fluxos', run: a.openLibrary },
  { name: 'Abrir arquivo…', icon: 'file', run: () => a.openFile() },
  { name: 'Ir para Dados', detail: 'fontes e constantes', icon: 'database', keywords: 'vista cadastrar', run: () => a.setView('data') },
  { name: 'Ir para Designer', detail: 'o canvas do fluxo', icon: 'workflow', keywords: 'vista', run: () => a.setView('designer') },
  { name: 'Ir para Dashboard', detail: 'o relatório', icon: 'dashboard', keywords: 'vista painel', run: () => a.setView('dashboard') },
  { name: 'Ir para SQL', detail: 'o código do fluxo', icon: 'terminal', keywords: 'vista', run: () => a.setView('sql') },
  { name: 'Nova etapa', detail: 'agrupar caixas', icon: 'group', end: 'G', keywords: 'grupo organizar', run: a.newStage },
  { name: 'Modo foco', detail: 'só o fluxo na tela', icon: 'maximize', end: 'F11', keywords: 'tela cheia esconder paineis', run: a.focusFromAnywhere },
  { name: 'Trocar o tema', detail: 'claro ou escuro', icon: 'moon', keywords: 'dark escuro claro aparencia', run: a.toggleTheme },
  { name: 'Atalhos do teclado', icon: 'keyboard', end: '?', keywords: 'ajuda', run: a.shortcuts },
  { name: 'Abrir o Manual', detail: 'o guia do programa', icon: 'book', end: 'F1', keywords: 'ajuda guia documentacao', run: a.manual },
];
