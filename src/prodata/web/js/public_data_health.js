// Situação dos órgãos na tela (spec 049, RF-4921..4924): pontos no menu, selo no cartão, bloco no detalhe com
// Conferir de novo e a barra dos últimos 30 dias. "No ar" só depois de conferir: nunca um selo verde sem conferência.

import { button, h } from './dom.js';
import { icon } from './icons.js';

const ORDER = { fora: 3, lenta: 2, nao_conferido: 1, no_ar: 0 };
const LABELS = { no_ar: 'No ar', lenta: 'Lenta', fora: 'Fora do ar', nao_conferido: 'Não conferido' };

export function worst(health, serviceIds = []) {
  let out = null;
  for (const id of serviceIds) {
    const s = health?.servicos?.[id]?.situacao || 'nao_conferido';
    if (out === null || ORDER[s] > ORDER[out]) out = s;
  }
  return out || 'nao_conferido';
}

function ago(iso) {
  if (!iso) return '';
  const minutes = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (minutes < 1) return 'conferido agora';
  if (minutes < 60) return `conferido há ${minutes} min`;
  const hours = Math.round(minutes / 60);
  return hours < 24 ? `conferido há ${hours} h` : `conferido em ${new Date(iso).toLocaleDateString('pt-BR')}`;
}

const clock = (iso) => new Date(iso).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });

/** O ponto do menu e do cartão: cor e texto para leitores de tela. */
export function dot(situation, title = '') {
  return h('span', { class: `pd-dot is-${situation}`, title: title || LABELS[situation], role: 'img', 'aria-label': LABELS[situation] });
}

export function statusText(row) {
  if (!row || row.situacao === 'nao_conferido') return row?.motivo || 'Ainda não conferido';
  if (row.situacao === 'fora') return `Fora do ar desde ${clock(row.desde || row.conferido_em)}`;
  return LABELS[row.situacao];
}

/** O selo do cartão: só aparece quando o órgão não está no ar (o cartão normal já diz que está tudo bem). */
export function cardBadge(row) {
  if (!row || row.situacao === 'no_ar' || row.situacao === 'nao_conferido') return null;
  return h('span', { class: `pd-status is-${row.situacao}`, title: row.motivo || '' }, dot(row.situacao), statusText(row));
}

/** A barra dos últimos 30 dias, do que este computador viu (RF-4924). */
function historyBar(history = {}) {
  const days = [];
  const today = new Date();
  for (let i = 29; i >= 0; i -= 1) {
    const d = new Date(today.getFullYear(), today.getMonth(), today.getDate() - i);
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    const s = history[key];
    days.push(h('span', { class: `pd-day is-${s || 'none'}`, title: `${d.toLocaleDateString('pt-BR')}: ${s ? LABELS[s] : 'sem conferência'}` }));
  }
  return h('div', { class: 'pd-history' },
    h('div', { class: 'pd-history-bar', role: 'img', 'aria-label': 'Situação nos últimos 30 dias' }, days),
    h('small', { class: 'field-help' }, 'Últimos 30 dias: o que este computador viu, não um dado oficial do órgão.'));
}

/** O bloco de situação no detalhe da fonte, com Conferir de novo. */
export function healthBlock(row, { onRecheck, busy = false, offline = false } = {}) {
  const situation = row?.situacao || 'nao_conferido';
  return h('section', { class: `pd-health is-${situation}` },
    h('div', { class: 'pd-health-head' },
      dot(situation),
      h('strong', {}, offline ? 'Sem conexão com a internet agora' : statusText(row)),
      row?.conferido_em ? h('small', {}, ago(row.conferido_em)) : null,
      button({ icon: 'refresh', label: busy ? 'Conferindo…' : 'Conferir de novo', size: 'sm', variant: 'ghost', disabled: busy, onClick: onRecheck })),
    situation === 'fora' && row.motivo ? h('p', { class: 'pd-health-why' }, icon('alert', 13), ` ${row.motivo}`) : null,
    situation === 'lenta' && row.motivo ? h('p', { class: 'pd-health-why' }, row.motivo) : null,
    historyBar(row?.historico));
}
