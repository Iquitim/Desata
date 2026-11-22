// Agendamentos (spec 044, RF-4434..4437): todos os fluxos agendados neste computador, com a próxima e a última
// execução e as ações. O aviso de falha (RF-4435) aparece ao abrir o programa e enquanto ele está aberto.

import { api } from './api.js';
import { button, fmt, h } from './dom.js';
import { icon } from './icons.js';
import { store } from './store.js';
import { brandNotice } from './run_notice.js';
import { openScheduleDialog } from './schedule_dialog.js';
import { confirmDialog, openDialog, toast, toastError } from './ui.js';

const STATUS = { ok: 'deu certo', failed: 'falhou', refused: 'recusado' };
const when = (iso) => {
  const d = new Date(iso);
  const today = new Date();
  const days = Math.round((new Date(today.toDateString()) - new Date(d.toDateString())) / 86400000);
  const clock = d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
  return days === 0 ? `hoje, ${clock}` : days === 1 ? `ontem, ${clock}` : `${d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })}, ${clock}`;
};
const withClass = (el, ...names) => { el.classList.add(...names); return el; };
const seconds = (a, b) => fmt.number((new Date(b) - new Date(a)) / 1000, 1);

function stateOf(item) {
  if (item.task === 'missing') return ['missing', 'Removido no Agendador do Windows'];
  if (item.paused) return ['paused', 'Desativado'];
  if (item.last && item.last.status !== 'ok') return ['failed', 'Última execução com problema'];
  return ['active', 'Ativo'];
}

function row(item, refresh) {
  const [state, label] = stateOf(item);
  const act = (fn, done) => async () => {
    try { await fn(); if (done) toast(done, { kind: 'success' }); await refresh(); } catch (err) { toastError(err, 'Não foi possível'); }
  };
  const last = item.last
    ? h('div', { class: ['sch-last', `sch-last-${item.last.status}`] },
      icon(item.last.status === 'ok' ? 'check-circle' : 'alert', 13),
      ` Última: ${when(item.last.finished_at)} · ${STATUS[item.last.status]} · ${seconds(item.last.started_at, item.last.finished_at)} s`,
      item.last.files ? ` · ${item.last.files} arquivo(s)` : '',
      item.last.message ? h('div', { class: 'sch-last-msg' }, item.last.message) : null)
    : h('div', { class: 'sch-last muted' }, 'Ainda não rodou.');
  const actions = h('div', { class: 'sch-actions' },
    button({ icon: 'play', title: 'Executar agora', size: 'sm', variant: 'ghost', disabled: item.task === 'missing', onClick: async () => {
      try {
        await api.runSchedule(item.id);
        toast('Executando em segundo plano', { detail: 'O resultado aparece aqui quando terminar.' });
        watchRun(item, refresh);
      } catch (err) { toastError(err, 'Não foi possível executar'); }
    } }),
    button({ icon: 'edit', label: 'Editar', size: 'sm', variant: 'ghost', onClick: () => openScheduleDialog(item, { onDone: refresh }) }),
    withClass(button({ icon: 'trash', label: 'Excluir', size: 'sm', variant: 'ghost', onClick: () => removeSchedule(item, refresh) }), 'sch-delete'));
  // Ativo ou desativado, num interruptor à vista: desativado, a tarefa continua no Windows, mas não roda.
  const active = h('label', { class: ['switch sch-switch', item.task === 'missing' && 'disabled'], title: item.paused ? 'Desativado: não roda até você ligar de novo' : 'Ativo: roda nos horários marcados' },
    h('input', { type: 'checkbox', checked: !item.paused, disabled: item.task === 'missing', 'aria-label': `Agendamento de ${item.name} ativo`,
      onchange: (e) => act(() => (e.target.checked ? api.resumeSchedule(item.id) : api.pauseSchedule(item.id)), e.target.checked ? 'Agendamento ativado' : 'Agendamento desativado')() }),
    h('span', { class: 'switch-track' }), h('span', { class: 'sch-switch-text' }, item.paused ? 'Desativado' : 'Ativo'));
  return h('div', { class: ['sch-item', `sch-${state}`], dataset: { id: item.id } },
    h('span', { class: 'sch-dot', title: label }),
    h('div', { class: 'sch-main' },
      h('div', { class: 'sch-name' }, item.name, item.paused ? h('span', { class: 'sch-tag' }, 'desativado') : null,
        item.space_id ? h('span', { class: 'sch-tag', title: 'Fluxo do espaço da equipe: roda a versão oficial' }, 'espaço · versão oficial') : null),
      // assumido por outra pessoa (spec 047, RF-4753): este computador não roda mais
      item.substituido_por ? h('div', { class: 'sch-missing' }, icon('alert', 13),
        ` Assumido por ${item.substituido_por.nome} (computador ${item.substituido_por.maquina}): não roda mais aqui. Pode excluir.`) : null,
      h('div', { class: 'sch-when' }, item.sentence, item.next_text ? h('span', { class: 'muted' }, ` · próxima: ${item.next_text}`) : null),
      last,
      item.task === 'missing' ? h('div', { class: 'sch-missing' }, icon('alert', 13), ' Removido no Agendador do Windows. ',
        button({ label: 'Recriar', size: 'sm', onClick: act(() => api.recreateSchedule(item.id), 'Tarefa recriada') })) : null),
    h('div', { class: 'sch-side' }, active, actions));
}

/** Excluir, com confirmação (na lista e no Editar). */
export async function removeSchedule(item, done) {
  const ok = await confirmDialog({ title: 'Excluir agendamento', message: `Excluir o agendamento de "${item.name}" (${item.sentence.toLowerCase()})? A tarefa sai do Agendador do Windows. O fluxo continua na biblioteca. Para só parar por um tempo, desative em vez de excluir.`, confirm: 'Excluir', danger: true });
  if (!ok) return false;
  try {
    await api.deleteSchedule(item.id);
    toast('Agendamento excluído', { kind: 'success' });
    await done?.();
    return true;
  } catch (err) { toastError(err, 'Não foi possível excluir'); return false; }
}

/** Depois de "Executar agora": atualiza a lista quando a execução aparecer no histórico (até 2 minutos). */
function watchRun(item, refresh) {
  const before = item.last?.finished_at || '';
  let tries = 0;
  const tick = async () => {
    tries += 1;
    try {
      const { items } = await api.schedules();
      const now = items.find((i) => i.id === item.id);
      if (now?.last && now.last.finished_at !== before) {
        await refresh();
        toast(now.last.status === 'ok' ? `"${item.name}" executou` : `"${item.name}" ${STATUS[now.last.status]}`,
          { kind: now.last.status === 'ok' ? 'success' : 'error', detail: now.last.message || '' });
        return;
      }
    } catch { /* tenta de novo */ }
    if (tries < 60) setTimeout(tick, 2000);
  };
  setTimeout(tick, 2000);
}

export async function openSchedulesList() {
  const list = h('div', { class: 'sch-list' }, h('p', { class: 'muted' }, 'Carregando…'));
  const refresh = async () => {
    try {
      const { supported, items } = await api.schedules();
      if (!supported) {
        list.replaceChildren(h('p', { class: 'muted' }, 'O agendamento com botões existe no Windows. Use Arquivo › Agendar este fluxo… para ver a linha de comando.'));
        return;
      }
      list.replaceChildren(...(items.length ? items.map((i) => row(i, refresh)) : [h('div', { class: 'sch-empty' },
        icon('clock', 28), h('strong', {}, 'Nenhum fluxo agendado ainda'),
        h('p', { class: 'muted' }, 'Agende um fluxo para ele rodar sozinho, sem abrir o programa: as saídas ficam prontas antes de você chegar.'),
        store.workflow ? button({ icon: 'clock', label: 'Agendar o fluxo aberto', variant: 'primary', onClick: () => openScheduleDialog(null, { onDone: refresh }) }) : null)]));
    } catch (err) {
      list.replaceChildren(h('p', { class: 'text-error' }, err.message));
    }
  };
  openDialog({ title: 'Agendamentos', size: 'lg', body: h('div', { class: 'sch-list-wrap' }, list,
    h('p', { class: 'field-help' }, 'Cada agendamento é uma tarefa do Agendador de Tarefas do Windows, com o nome do programa e do fluxo. Roda com você conectado ao Windows.')) });
  await refresh();
}

/** Depois de excluir um fluxo da biblioteca: pergunta se o agendamento dele também sai (RF-4437). */
export async function offerRemoveSchedules(workflowId, name) {
  let items = [];
  try { items = (await api.schedules()).items.filter((i) => i.workflow_id === workflowId); } catch { return; }
  if (!items.length) return;
  const yes = await confirmDialog({ title: 'Excluir o agendamento também?', message: `"${name}" tinha ${items.length === 1 ? 'um agendamento' : `${items.length} agendamentos`} (${items.map((i) => i.sentence.toLowerCase()).join('; ')}). Sem o fluxo, ele vai falhar. Excluir?`, confirm: 'Excluir agendamento', danger: true });
  if (!yes) return;
  for (const i of items) await api.deleteSchedule(i.id).catch((err) => toastError(err, 'Não foi possível excluir o agendamento'));
}

/** Aviso de falha das execuções agendadas: ao abrir o programa e a cada 5 minutos (RF-4435). */
export function watchScheduleFailures() {
  const check = async () => {
    let failures = [];
    try { failures = await api.scheduleFailures(); } catch { return; }
    if (!failures.length) return;
    const last = failures.at(-1);
    await api.scheduleFailuresSeen().catch(() => {});
    brandNotice({
      tone: 'error',
      title: failures.length === 1 ? 'Um agendamento falhou' : `${failures.length} execuções agendadas falharam`,
      flow: `${last.name} · ${when(last.finished_at)}`,
      detail: last.message || STATUS[last.status],
      action: { icon: 'clock', label: 'Ver agendamentos', onClick: openSchedulesList },
      sticky: true,
    });
  };
  setTimeout(check, 2500);
  setInterval(check, 5 * 60 * 1000);
}
