// Versões anteriores (spec 046, RF-4631..4634): a lista do que foi guardado a cada Salvar, com a prévia do canvas e
// Restaurar. Restaurar entra como mudança não salva (Desfazer volta), e o que estava aberto vira uma versão guardada.

import { api } from './api.js';
import { NODE_MIN_H, NODE_W } from './canvas_geometry.js';
import { button, h } from './dom.js';
import { icon } from './icons.js';
import { mutate, select, store } from './store.js';
import { openDialog, toast, toastError } from './ui.js';

const SVG = 'http://www.w3.org/2000/svg';
const ORIGIN = {
  manual: ['save', 'Salvar'],
  auto: ['refresh', 'Salvar automático'],
  restore: ['undo', 'Antes de restaurar'],
  columns: ['columns', 'Antes de trocar colunas'],
  conflito: ['alert', 'Salvo enquanto outra pessoa editava'], // espaço da equipe (spec 047, RF-4761)
  copia: ['copy', 'Cópia da sincronização'], // RF-4762
};
const EXAMPLES = new Set(['demo_pipeline_360']);

/** Por que o fluxo aberto não tem versões (ou null, se tem). */
export function versionsBlockedReason() {
  const wf = store.workflow;
  if (!wf) return 'nenhum fluxo aberto';
  if (EXAMPLES.has(wf.id)) return 'o fluxo de exemplo não guarda versões (Salvar como faz a sua cópia)';
  if (wf.id.startsWith('licao_')) return 'o fluxo de uma lição não guarda versões';
  if (!store.filePath && !store.savedSnapshot) return 'as versões começam no primeiro Salvar';
  return null;
}

const when = (iso) => {
  const d = new Date(iso);
  const days = Math.round((new Date(new Date().toDateString()) - new Date(d.toDateString())) / 86400000);
  const clock = d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
  if (days === 0) return `hoje, ${clock}`;
  if (days === 1) return `ontem, ${clock}`;
  return `${d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: days > 300 ? 'numeric' : undefined })}, ${clock}`;
};

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

/** "o que muda se restaurar": a versão comparada com o que está aberto agora (o servidor conta de lá para cá). */
function summary(changes) {
  if (!changes) return '';
  const parts = [];
  // contado da versão para o fluxo de agora: o que foi "removido" desde então volta ao restaurar, e assim por diante
  if (changes.removed) parts.push(`${plural(changes.removed, 'caixa volta', 'caixas voltam')}`);
  if (changes.added) parts.push(`${plural(changes.added, 'caixa sai', 'caixas saem')}`);
  if (changes.changed) parts.push(`${plural(changes.changed, 'caixa volta à configuração de antes', 'caixas voltam à configuração de antes')}`);
  if (changes.moved) parts.push(`${plural(changes.moved, 'caixa muda de lugar', 'caixas mudam de lugar')}`);
  const wires = changes.wires_added + changes.wires_removed;
  if (wires) parts.push(plural(wires, 'ligação muda', 'ligações mudam'));
  if (changes.renamed) parts.push('o nome do fluxo muda');
  return parts.length ? parts.join(' · ') : 'Igual ao que está aberto agora';
}

/** JSON com as chaves em ordem: a tela e o servidor escrevem a mesma configuração em ordens diferentes. */
const stable = (v) => (Array.isArray(v) ? `[${v.map(stable).join(',')}]`
  : v && typeof v === 'object' ? `{${Object.keys(v).sort().filter((k) => v[k] !== undefined).map((k) => `${JSON.stringify(k)}:${stable(v[k])}`).join(',')}}`
    : JSON.stringify(v ?? null));

/** Mesma caixa nas duas versões? Campo ausente vale o padrão (rótulo vazio, ligada), como no servidor. */
const sameNode = (a, b) => a.type === b.type && (a.label || '') === (b.label || '') && Boolean(a.disabled) === Boolean(b.disabled)
  && stable(a.config || {}) === stable(b.config || {});

/** Miniatura do canvas da versão, nas cores das famílias; marca o que volta e o que muda em relação a agora. */
export function preview(version) {
  const current = new Map((store.workflow?.nodes || []).map((n) => [n.id, n]));
  const nodes = version.nodes || [];
  const svg = document.createElementNS(SVG, 'svg');
  svg.setAttribute('class', 'ver-preview');
  svg.setAttribute('role', 'img');
  if (!nodes.length) {
    svg.setAttribute('viewBox', '0 0 400 200');
    svg.setAttribute('aria-label', 'Versão sem caixas');
    const t = document.createElementNS(SVG, 'text');
    Object.entries({ x: 200, y: 100, 'text-anchor': 'middle', class: 'ver-empty-text' }).forEach(([k, v]) => t.setAttribute(k, v));
    t.textContent = 'Sem caixas nesta versão';
    svg.append(t);
    return svg;
  }
  const boxes = [...nodes.map((n) => ({ x: n.x, y: n.y, w: NODE_W, h: NODE_MIN_H })),
    ...(version.containers || []).map((c) => ({ x: c.x, y: c.y, w: c.width, h: c.height }))];
  const pad = 40;
  const minX = Math.min(...boxes.map((b) => b.x)) - pad;
  const minY = Math.min(...boxes.map((b) => b.y)) - pad;
  const maxX = Math.max(...boxes.map((b) => b.x + b.w)) + pad;
  const maxY = Math.max(...boxes.map((b) => b.y + b.h)) + pad;
  svg.setAttribute('viewBox', `${minX} ${minY} ${maxX - minX} ${maxY - minY}`);
  svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
  let back = 0;
  let changed = 0;
  const el = (tag, attrs, text) => {
    const e = document.createElementNS(SVG, tag);
    Object.entries(attrs).forEach(([k, v]) => e.setAttribute(k, v));
    if (text) e.textContent = text;
    return e;
  };
  for (const c of version.containers || []) {
    svg.append(el('rect', { x: c.x, y: c.y, width: c.width, height: c.height, rx: 10, class: 'ver-container', style: `--c:${c.color || '#64748b'}` }));
    if (c.title) svg.append(el('text', { x: c.x + 12, y: c.y + 22, class: 'ver-container-title' }, c.title));
  }
  const byId = new Map(nodes.map((n) => [n.id, n]));
  for (const e of version.edges || []) {
    const a = byId.get(e.source);
    const b = byId.get(e.target);
    if (!a || !b) continue;
    const x1 = a.x + NODE_W; const y1 = a.y + NODE_MIN_H / 2;
    const x2 = b.x; const y2 = b.y + NODE_MIN_H / 2;
    const mid = Math.max(30, Math.abs(x2 - x1) / 2);
    svg.append(el('path', { d: `M${x1},${y1} C${x1 + mid},${y1} ${x2 - mid},${y2} ${x2},${y2}`, class: 'ver-edge' }));
  }
  for (const n of nodes) {
    const tool = store.tools?.[n.type];
    const now = current.get(n.id);
    const state = !now ? 'back' : sameNode(now, n) ? '' : 'changed';
    if (state === 'back') back += 1;
    if (state === 'changed') changed += 1;
    const g = el('g', { class: `ver-node ${state}`, 'data-category': tool?.category || 'prep' });
    g.append(el('rect', { x: n.x, y: n.y, width: NODE_W, height: NODE_MIN_H, rx: 8 }));
    g.append(el('rect', { x: n.x, y: n.y, width: 6, height: NODE_MIN_H, rx: 3, class: 'ver-node-band' }));
    g.append(el('text', { x: n.x + 16, y: n.y + NODE_MIN_H / 2 + 5, class: 'ver-node-text' }, (n.label || tool?.name || n.type).slice(0, 22)));
    if (state) g.append(el('title', {}, state === 'back' ? 'Volta ao restaurar' : 'Volta à configuração desta versão'));
    svg.append(g);
  }
  svg.setAttribute('aria-label', `Prévia com ${plural(nodes.length, 'caixa', 'caixas')}`
    + `${back ? `, ${plural(back, 'volta', 'voltam')}` : ''}${changed ? `, ${changed} com configuração diferente` : ''}`);
  return svg;
}

function legend() {
  return h('div', { class: 'ver-legend' },
    h('span', { class: 'ver-key back' }, 'Volta ao restaurar'),
    h('span', { class: 'ver-key changed' }, 'Configuração diferente da atual'));
}

export async function openVersionsDialog({ choose = null } = {}) {
  const why = versionsBlockedReason();
  if (why) { toast('Versões anteriores', { detail: `Indisponível: ${why}.` }); return; }
  const wf = store.workflow;
  const path = store.filePath || null;
  const space = store.space; // espaço da equipe: as versões ficam na pasta do espaço, com o autor (RF-4731)
  const list = h('div', { class: 'ver-list', role: 'listbox', 'aria-label': 'Versões guardadas' });
  const side = h('div', { class: 'ver-side' }, h('p', { class: 'muted' }, 'Carregando…'));
  const restoreBtn = button({ icon: 'undo', label: 'Restaurar esta versão', variant: 'primary', disabled: true });
  let chosen = null;
  // espaço da equipe (spec 048): juntar a versão de outra pessoa com a que está aberta, caixa por caixa
  const mergeBtn = space ? button({ icon: 'columns', label: 'Juntar com a que está aberta', variant: 'ghost', disabled: true, onClick: async () => {
    if (!chosen) return;
    close();
    const { openMergeDialog } = await import('./merge_dialog.js');
    openMergeDialog({ outra: chosen.item.id, nome: chosen.item.autor_nome });
  } }) : null;

  const { close } = openDialog({
    title: `Versões anteriores · ${wf.name}`,
    size: 'xl',
    body: h('div', { class: 'ver-layout' }, list, side),
    actions: [
      h('span', { class: 'ver-foot muted' }, space
        ? `Guardadas na pasta do espaço "${space.nome}", para todos do espaço (até 50 por fluxo).`
        : 'Guardadas neste computador, a cada Salvar (até 30 por fluxo).'),
      button({ label: 'Fechar', onClick: () => close() }),
      mergeBtn,
      restoreBtn,
    ].filter(Boolean),
  });

  let items = [];
  try {
    items = space ? await api.spaceVersions(space.id, wf.id, wf) : await api.versions(wf.id, wf, path);
  } catch (err) {
    toastError(err, 'Não foi possível ler as versões');
    close();
    return;
  }
  list.replaceChildren();
  if (!items.length) {
    side.replaceChildren(h('div', { class: 'ver-empty' }, icon('clock', 28),
      h('strong', {}, 'Ainda não há versões guardadas deste fluxo'),
      h('p', {}, 'A partir de agora, cada Salvar guarda uma versão aqui. Com o salvamento automático, uma a cada 10 minutos de trabalho.')));
    return;
  }

  const show = async (item, row) => {
    list.querySelectorAll('.ver-item').forEach((r) => r.setAttribute('aria-selected', String(r === row)));
    side.replaceChildren(h('p', { class: 'muted' }, 'Carregando a prévia…'));
    restoreBtn.disabled = true;
    try {
      const version = space ? await api.spaceVersion(space.id, wf.id, item.id) : await api.version(wf.id, item.id, path);
      if (row.getAttribute('aria-selected') !== 'true') return; // a pessoa já escolheu outra
      chosen = { item, version };
      const same = item.changes && Object.entries(item.changes).every(([, v]) => !v);
      side.replaceChildren(
        h('div', { class: 'ver-side-head' },
          h('strong', {}, when(item.created_at)),
          space ? h('span', { class: 'ver-author' }, icon('user', 12), item.autor_nome) : null,
          space && !item.confere ? h('span', { class: 'ver-chip warn', title: 'Sem a assinatura de um membro que podia editar: ao restaurar, você confere e salva com a sua.' }, icon('alert', 12), 'Assinatura não confere') : null,
          h('span', { class: 'ver-chip' }, icon(ORIGIN[item.origin][0], 12), ORIGIN[item.origin][1]),
          version.name !== wf.name ? h('span', { class: 'muted' }, `nome: ${version.name}`) : null),
        h('p', { class: 'ver-changes' }, same ? 'Igual ao que está aberto agora.' : `Se restaurar: ${summary(item.changes)}.`),
        preview(version),
        legend());
      restoreBtn.disabled = same || Boolean(store.readonly);
      if (mergeBtn) mergeBtn.disabled = same || Boolean(store.readonly) || item.origin === 'restore';
      if (store.readonly) restoreBtn.title = 'Aberto só para ver: para restaurar, comece a editar.';
    } catch (err) {
      side.replaceChildren(h('p', { class: 'field-error' }, err.message || 'Não foi possível abrir esta versão.'));
    }
  };

  if (choose && !items.some((item) => item.id === choose)) choose = null; // já saiu do histórico: mostra a mais nova
  items.forEach((item, i) => {
    const row = h('button', { type: 'button', class: 'ver-item', role: 'option', 'aria-selected': 'false' },
      h('span', { class: 'ver-item-when' }, when(item.created_at)),
      space ? h('span', { class: 'ver-item-author' }, item.autor_nome) : null,
      h('span', { class: 'ver-item-origin' }, icon(ORIGIN[item.origin][0], 12), ORIGIN[item.origin][1]),
      h('span', { class: 'ver-item-sum' }, `${plural(item.node_count, 'caixa', 'caixas')} · ${summary(item.changes)}`));
    row.addEventListener('click', () => show(item, row));
    row.addEventListener('keydown', (e) => {
      const rows = [...list.querySelectorAll('.ver-item')];
      const k = rows.indexOf(row) + (e.key === 'ArrowDown' ? 1 : e.key === 'ArrowUp' ? -1 : 0);
      if (k !== rows.indexOf(row) && rows[k]) { e.preventDefault(); rows[k].focus(); rows[k].click(); }
    });
    list.append(row);
    if (choose ? item.id === choose : i === 0) show(item, row);
  });

  restoreBtn.addEventListener('click', async () => {
    if (!chosen) return;
    restoreBtn.disabled = true;
    try {
      if (space) await api.recordSpaceVersion(space.id, wf.id, store.workflow); // o que estava aberto não se perde
      else await api.recordVersion(wf.id, store.workflow, 'restore', path);
    } catch (err) {
      toastError(err, 'Não foi possível guardar a versão atual antes de restaurar');
      restoreBtn.disabled = false;
      return;
    }
    restoreVersion(chosen.version);
    close();
    toast('Versão restaurada', { kind: 'success', detail: `De ${when(chosen.item.created_at)}. Ainda não salva: Salvar grava, Ctrl+Z desfaz.` });
  });
}

/** Coloca a versão no lugar do fluxo aberto, num passo só de Desfazer. O id, o arquivo e a amostra continuam. */
export function restoreVersion(version) {
  mutate((wf) => {
    const keep = { id: wf.id, samples: wf.samples };
    for (const key of Object.keys(wf)) delete wf[key];
    Object.assign(wf, structuredClone(version), keep);
  }, { structural: true, affects: version.nodes.map((n) => n.id) });
  select(null); // a caixa selecionada pode não existir na versão restaurada
}
