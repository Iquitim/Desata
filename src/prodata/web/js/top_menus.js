// Menus do topo (spec 029, RF-2981): Arquivo e Exibir, com texto, e os comandos que a busca (Ctrl+K) também usa.
// O botão de tema fica fora dos menus, à vista no topo.

import { shareDialog } from './portable.js';
import { openScheduleDialog } from './schedule_dialog.js';
import { openSchedulesList } from './schedules_list.js';
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
import { autoBlockedReason, autosaveActive, setAutosave } from './save_flow.js';
import { runNoticeOn, setRunNotice } from './run_notice.js';
import { openVersionsDialog, versionsBlockedReason } from './versions_dialog.js';
import { openSpacesDialog } from './team_spaces.js';

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
  { label: 'Versões anteriores…', icon: 'undo', disabled: Boolean(versionsBlockedReason()), title: versionsBlockedReason() ? `Indisponível: ${versionsBlockedReason()}.` : 'O que foi guardado a cada Salvar, com prévia e Restaurar', onSelect: () => openVersionsDialog() },
  'separator',
  { label: 'Agendar este fluxo…', icon: 'clock', disabled: !store.workflow, onSelect: () => openScheduleDialog() },
  { label: 'Agendamentos…', icon: 'list', onSelect: openSchedulesList },
  'separator',
  // Espaço da equipe (spec 047): o único item de equipe que aparece para quem usa só no computador (RF-4702).
  { label: 'Espaços da equipe…', icon: 'folder', title: 'Trabalhar junto numa pasta compartilhada (opcional)', onSelect: () => openSpacesDialog() },
];

// Exibir (spec 044): o que é escolha entre opções vira submenu, com o valor atual à direita; o que liga e desliga
// fica à vista, com a marca de ligado.
const NUMBER_NAMES = { virgula: 'vírgula decimal', ponto: 'ponto decimal' };
const viewItems = (a) => {
  const containers = allContainers().length;
  return [
    { label: 'Painéis', icon: 'panel', submenu: () => [...panelMenuItems(), 'separator', { label: 'Restaurar layout padrão', icon: 'refresh', onSelect: resetLayout }] },
    densityMenuItem(),
    { label: a.inFocus() ? 'Sair do modo foco' : 'Modo foco', icon: 'maximize', shortcut: 'F11', disabled: store.view !== 'designer', onSelect: a.toggleFocus },
    { heading: 'Canvas' },
    { label: 'Organizar o fluxo', icon: 'columns', disabled: store.view !== 'designer' || !store.workflow?.nodes.length, onSelect: () => { organizeFlow(); requestAnimationFrame(() => fitView()); } },
    { label: 'Fios', icon: 'workflow', value: wireMode() === 'routed' ? 'organizados' : 'curvos', submenu: () => [
      { label: 'Organizados (desviam das caixas)', checked: wireMode() === 'routed', radio: true, onSelect: () => setWireMode('routed') },
      { label: 'Curvos', checked: wireMode() === 'curved', radio: true, onSelect: () => setWireMode('curved') },
    ] },
    { label: 'Etapas e caixas', icon: 'group', submenu: () => [
      { label: 'Recolher todas as etapas', icon: 'minimize', disabled: !containers, onSelect: () => setContainersCollapsed(allContainers(), true) },
      { label: 'Expandir todas as etapas', icon: 'maximize', disabled: !containers, onSelect: () => setContainersCollapsed(allContainers(), false) },
      'separator',
      { label: 'Recolher as caixas desativadas', icon: 'power', disabled: !store.workflow?.nodes.some((n) => n.disabled), onSelect: collapseDisabled },
    ] },
    { label: 'Tempo nas caixas', checked: timingOn(), onSelect: () => setTiming(!timingOn()) },
    { heading: 'Tabela e avisos' },
    { label: 'Resumo das colunas na tabela', checked: summaryShown(), onSelect: () => setSummary(!summaryShown()) },
    { label: 'Aviso ao terminar a execução', checked: runNoticeOn(), onSelect: () => setRunNotice(!runNoticeOn()) },
    { label: 'Números', icon: 'hash', value: NUMBER_STYLES[getNumberStyle()], submenu: () => Object.entries(NUMBER_STYLES).map(([style, sample]) => ({
      label: `${sample} · ${NUMBER_NAMES[style] || style}`, checked: getNumberStyle() === style, radio: true,
      onSelect: () => { setNumberStyle(style); emit('numbers'); },
    })) },
    'separator',
    { label: 'Atalhos do teclado', icon: 'keyboard', shortcut: '?', onSelect: a.shortcuts },
  ];
};

/** Os menus do topo. `a`: as ações do programa, montadas em main.js. */
export const topMenus = (a) => [menuButton('Arquivo', 'file', () => fileItems(a)), menuButton('Exibir', 'eye', () => viewItems(a))];

/** O que a busca oferece como "Ações". */
export const commandList = (a) => [
  { name: 'Executar', detail: 'o fluxo inteiro', icon: 'play', end: 'Ctrl+Enter', keywords: 'rodar processar', run: a.run },
  { name: 'Salvar', detail: 'o fluxo aberto', icon: 'save', end: 'Ctrl+S', keywords: 'gravar', run: a.save },
  { name: 'Salvar como…', detail: 'escolher a pasta', icon: 'directory', end: 'Ctrl+Shift+S', keywords: 'gravar copia', run: a.saveAs },
  { name: 'Salvar com amostra dos dados…', detail: 'para quem não tem as fontes', icon: 'database', keywords: 'compartilhar enviar amostra mascara', run: () => shareDialog() },
  ...(autoBlockedReason() ? [] : [{ name: autosaveActive() ? 'Desligar o salvamento automático' : 'Salvar automaticamente', detail: 'fluxos já salvos', icon: 'refresh', keywords: 'auto save autosave gravar sozinho', run: () => setAutosave(!autosaveActive()) }]),
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
