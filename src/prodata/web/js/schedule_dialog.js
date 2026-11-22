// Agendar (spec 044, RF-4431..4438): frequência em botões, horário, dias em fichas e uma frase de resumo que acompanha
// cada escolha. A linha de comando (spec 033) continua em Avançado; fora do Windows, é só ela que aparece.

import { api } from './api.js';
import { brand } from './brand.js';
import { button, debounce, h } from './dom.js';
import { icon } from './icons.js';
import { isDirty, store } from './store.js';
import { isProtected } from './trust_banner.js';
import { saveFlow } from './save_flow.js';
import { openDialog, toast, toastError } from './ui.js';

const FREQUENCIES = [
  { id: 'daily', label: 'Todo dia', icon: 'repeat' },
  { id: 'weekly', label: 'Dias da semana', icon: 'columns' },
  { id: 'monthly', label: 'Todo mês', icon: 'clock' },
  { id: 'hourly', label: 'A cada X horas', icon: 'refresh' },
];
const DAYS = [['S', 'Segunda'], ['T', 'Terça'], ['Q', 'Quarta'], ['Q', 'Quinta'], ['S', 'Sexta'], ['S', 'Sábado'], ['D', 'Domingo']];
const HOURS = [1, 2, 3, 4, 6, 8, 12];

// ------------------------------------------------------------------ linha de comando (Avançado)

function copyRow(label, text, help) {
  const code = h('code', { class: 'cli-line mono' }, text);
  return h('div', { class: 'field' },
    h('span', { class: 'field-label' }, label),
    h('div', { class: 'row' }, code, button({
      icon: 'copy', title: 'Copiar', onClick: async () => {
        try {
          await navigator.clipboard.writeText(text);
          toast('Copiado', { kind: 'success' });
        } catch {
          const range = document.createRange();
          range.selectNodeContents(code);
          const sel = window.getSelection();
          sel.removeAllRanges();
          sel.addRange(range);
          toast('O comando está selecionado: use Ctrl+C para copiar.');
        }
      },
    })),
    help ? h('p', { class: 'field-help' }, help) : null);
}

function commandLine(windows) {
  const wf = store.workflow;
  const cli = store.catalog?.cli_command || 'prodata';
  // Arquivo de fora da biblioteca roda pelo caminho; o da biblioteca, pelo ID, que não muda com o nome.
  const target = store.space ? `espaco:${store.space.id}/${wf.id}` : store.filePath ? `"${store.filePath}"` : wf.id;
  const run = `${cli} run ${target}`;
  const task = `schtasks /Create /TN "${brand.nome} ${wf.name.replace(/"/g, '')}" /SC DAILY /ST 06:00 /TR "${run.replace(/"/g, '\\"')}"`;
  return h('div', { class: 'form' },
    copyRow('Linha de comando deste fluxo', run, 'Termina com código 0 se tudo executou e 1 se alguma caixa falhou. O relatório de cada execução fica na pasta de dados, em logs/execucoes.'),
    windows ? copyRow('Ou crie a tarefa à mão', task, 'Cole no Prompt de Comando. Para outro horário ou dia, mude /ST e /SC.') : null,
    h('p', { class: 'field-help' }, 'Saída em "Perguntar ao executar" nunca sobrescreve sem alguém para responder: cria um arquivo novo com data e hora. Para manter sempre o mesmo nome, escolha "Substituir o arquivo" no Output Data.'));
}

// ------------------------------------------------------------------ o diálogo

const defaults = () => ({ frequency: 'weekly', time: '06:00', weekdays: [0, 1, 2, 3, 4], month_day: 1, every_hours: 4, options: { catch_up: true, wake: false, on_battery: true } });

/** Agenda o fluxo aberto, ou edita `existing` (um item da lista de agendamentos). `onDone` recebe o item salvo. */
export async function openScheduleDialog(existing = null, { onDone } = {}) {
  const wf = store.workflow;
  if (!existing && !wf) return;
  let listed = { supported: true, items: [] };
  try { listed = await api.schedules(); } catch { /* o diálogo funciona sem a lista */ }
  // Fluxo do espaço da equipe (spec 047, RF-4752): agenda a versão oficial do espaço, não a cópia aberta
  const space = existing ? (existing.space_id || '') : (store.space?.id || '');
  const target = existing ? { workflow_id: existing.workflow_id, file_path: existing.file_path, space_id: space, name: existing.name }
    : { workflow_id: store.filePath && !space ? '' : wf.id, file_path: space ? '' : store.filePath || '', space_id: space, name: wf.name };
  const isOpenFlow = !existing || (wf && (existing.space_id ? existing.space_id === store.space?.id && existing.workflow_id === wf.id
    : existing.workflow_id ? existing.workflow_id === wf.id && !store.space : existing.file_path === store.filePath));
  const keyOf = (i) => `${i.space_id || ''}|${i.workflow_id || i.file_path}`;
  const others = existing ? [] : listed.items.filter((i) => keyOf(i) === keyOf(target));

  if (!listed.supported) {
    openDialog({ title: 'Executar sem abrir o programa', size: 'lg', body: h('div', { class: 'form' },
      h('p', {}, `O agendamento com botões existe no Windows. Aqui, use a linha de comando no agendador do seu sistema (cron, launchd).`),
      commandLine(false)) });
    return;
  }

  const plan = { ...defaults(), ...(existing || {}), options: { ...defaults().options, ...(existing?.options || {}) } };
  const sentence = h('strong', { class: 'sch-sentence' }, '…');
  const next = h('span', { class: 'sch-next' });
  const week = h('div', { class: 'sch-week', 'aria-hidden': 'true' });
  const body = h('div', { class: 'sch-form' });
  const errorBox = h('p', { class: 'text-error small', hidden: true });
  const dirty = !space && isOpenFlow && (isDirty() || (!store.savedSnapshot && !store.filePath));
  const protectedFlow = !space && isOpenFlow && isProtected(); // no espaço, quem decide é a assinatura do Publicador

  const state = { active: !existing?.paused };
  const refreshPreview = debounce(async () => {
    try {
      const p = await api.schedulePreview({ ...target, ...plan, workflow_id: target.workflow_id || '', file_path: target.file_path || '', space_id: target.space_id || '' });
      sentence.textContent = `Roda ${p.sentence.charAt(0).toLowerCase()}${p.sentence.slice(1)}`;
      next.textContent = state.active ? `Próxima: ${p.next_text}` : 'Desativado: não roda até ser ativado';
      errorBox.hidden = true;
    } catch (err) { errorBox.textContent = err.message; errorBox.hidden = false; }
  }, 120);

  const drawWeek = () => {
    const runs = (d) => plan.frequency !== 'weekly' || plan.weekdays.includes(d);
    week.replaceChildren(...[...DAYS.map(([letter, name], d) => h('span', { class: ['sch-day', plan.frequency !== 'monthly' && runs(d) && 'on'], title: name }, letter)),
      plan.frequency === 'monthly' ? h('span', { class: 'sch-day-note' }, `dia ${plan.month_day}`) : null,
      plan.frequency === 'hourly' ? h('span', { class: 'sch-day-note' }, hourList()) : null].filter(Boolean));
  };
  const hourList = () => {
    const [hh, mm] = plan.time.split(':').map(Number);
    const out = [];
    for (let t = hh * 60 + mm; t < 24 * 60 && out.length < 6; t += plan.every_hours * 60) out.push(`${String(Math.floor(t / 60)).padStart(2, '0')}:${String(t % 60).padStart(2, '0')}`);
    return out.join(' · ') + (24 * 60 - (hh * 60 + mm) > plan.every_hours * 60 * 6 ? ' …' : '');
  };

  const changed = () => { draw(); drawWeek(); refreshPreview(); };
  const segment = h('div', { class: 'segmented sch-freq', role: 'tablist', 'aria-label': 'Frequência' });
  const draw = () => {
    segment.replaceChildren(...FREQUENCIES.map((f) => h('button', {
      type: 'button', class: 'segment', role: 'tab', 'aria-selected': String(plan.frequency === f.id), dataset: { freq: f.id },
      onclick: () => { plan.frequency = f.id; changed(); },
    }, icon(f.icon, 14), f.label)));
    const time = h('label', { class: 'field sch-time' }, h('span', { class: 'field-label' }, plan.frequency === 'hourly' ? 'A partir das' : 'Horário'),
      h('input', { type: 'time', class: 'input', value: plan.time, required: true, onchange: (e) => { if (e.target.value) { plan.time = e.target.value; drawWeek(); refreshPreview(); } } }));
    let extra = null;
    if (plan.frequency === 'weekly') {
      extra = h('div', { class: 'field' }, h('span', { class: 'field-label' }, 'Dias'),
        h('div', { class: 'sch-chips', role: 'group', 'aria-label': 'Dias da semana' }, DAYS.map(([letter, name], d) => h('button', {
          type: 'button', class: ['sch-chip', plan.weekdays.includes(d) && 'on'], 'aria-pressed': String(plan.weekdays.includes(d)), title: name, 'aria-label': name,
          onclick: () => { plan.weekdays = plan.weekdays.includes(d) ? plan.weekdays.filter((x) => x !== d) : [...plan.weekdays, d].sort(); changed(); },
        }, letter))),
        h('div', { class: 'sch-quick' },
          button({ label: 'Dias úteis', size: 'sm', variant: 'ghost', onClick: () => { plan.weekdays = [0, 1, 2, 3, 4]; changed(); } }),
          button({ label: 'Todos', size: 'sm', variant: 'ghost', onClick: () => { plan.weekdays = [0, 1, 2, 3, 4, 5, 6]; changed(); } })));
    } else if (plan.frequency === 'monthly') {
      extra = h('label', { class: 'field' }, h('span', { class: 'field-label' }, 'Dia do mês'),
        h('select', { class: 'input', onchange: (e) => { plan.month_day = Number(e.target.value); drawWeek(); refreshPreview(); } },
          Array.from({ length: 28 }, (_, i) => h('option', { value: i + 1, selected: plan.month_day === i + 1 }, String(i + 1)))),
        h('span', { class: 'field-help' }, 'Até 28, para valer em todos os meses.'));
    } else if (plan.frequency === 'hourly') {
      extra = h('div', { class: 'field' }, h('span', { class: 'field-label' }, 'A cada'),
        h('div', { class: 'sch-chips' }, HOURS.map((n) => h('button', {
          type: 'button', class: ['sch-chip wide', plan.every_hours === n && 'on'], 'aria-pressed': String(plan.every_hours === n),
          onclick: () => { plan.every_hours = n; changed(); },
        }, `${n} h`))));
    }
    const option = (key, label, help) => h('label', { class: 'switch', title: help },
      h('input', { type: 'checkbox', checked: plan.options[key], onchange: (e) => { plan.options[key] = e.target.checked; } }),
      h('span', { class: 'switch-track' }), h('span', {}, label));
    body.replaceChildren(
      h('div', { class: 'field' }, h('span', { class: 'field-label' }, 'Quando'), segment),
      h('div', { class: 'sch-row' }, time, extra),
      h('div', { class: 'field sch-options' }, h('span', { class: 'field-label' }, 'Opções'),
        existing ? h('label', { class: 'switch', title: 'Desativado, a tarefa continua no Windows, mas não roda.' },
          h('input', { type: 'checkbox', checked: state.active, onchange: (e) => { state.active = e.target.checked; summary.classList.toggle('off', !state.active); refreshPreview(); } }),
          h('span', { class: 'switch-track' }), h('span', {}, h('strong', {}, 'Agendamento ativo'))) : null,
        option('catch_up', 'Se o computador estiver desligado na hora, rodar assim que ligar', 'Sem isso, o horário perdido é pulado.'),
        option('wake', 'Acordar o computador para rodar', 'Se ele estiver em suspensão. Não liga um computador desligado.'),
        option('on_battery', 'Rodar também na bateria', 'Desligado: no notebook, só roda ligado na tomada.')));
  };
  draw();
  drawWeek();
  refreshPreview();

  const summary = h('div', { class: ['sch-summary', !state.active && 'off'] }, h('span', { class: 'sch-summary-icon' }, icon('clock', 20)), h('div', { class: 'sch-summary-text' }, sentence, next, week));
  const notes = [
    space ? h('p', { class: 'hint-box small' }, icon('star', 14), ' Roda a versão oficial do espaço, conferida na hora pela assinatura de um Publicador. '
      + 'Mudanças salvas depois só entram quando alguém publicar de novo. O time vê este agendamento em Espaços da equipe › Agendamentos.') : null,
    protectedFlow ? h('p', { class: 'hint-box small sch-block' }, icon('lock', 14), ' Este fluxo veio de fora e ainda não foi confiado. Confira o que ele faz na faixa do topo e escolha Confiar e executar antes de agendar.') : null,
    !protectedFlow && dirty ? h('p', { class: 'hint-box small' }, store.savedSnapshot || store.filePath
      ? 'Há mudanças não salvas: o agendamento roda a versão salva. "Salvar e agendar" salva antes.'
      : 'Este fluxo ainda não foi salvo. "Salvar e agendar" salva e agenda de uma vez.') : null,
    others.length ? h('p', { class: 'field-help' }, `Este fluxo já tem ${others.length === 1 ? 'um agendamento' : `${others.length} agendamentos`}: ${others.map((o) => o.sentence.toLowerCase()).join('; ')}. Este será mais um.`) : null,
  ];
  const advanced = isOpenFlow ? h('details', { class: 'sch-advanced' }, h('summary', {}, 'Avançado: linha de comando'), commandLine(true)) : null;

  const save = async () => {
    try {
      if (isOpenFlow && dirty) {
        const ok = await saveFlow();
        if (!ok || isDirty()) return;
        target.workflow_id = store.filePath ? '' : store.workflow.id;
        target.file_path = store.filePath || '';
        target.name = store.workflow.name;
      }
      const payload = { ...target, frequency: plan.frequency, time: plan.time, weekdays: plan.weekdays, month_day: plan.month_day, every_hours: plan.every_hours, options: plan.options };
      let item = existing ? await api.updateSchedule(existing.id, payload) : await api.createSchedule(payload);
      if (existing && Boolean(item.paused) === state.active) item = state.active ? await api.resumeSchedule(existing.id) : await api.pauseSchedule(existing.id);
      close();
      toast(existing ? 'Agendamento salvo' : 'Fluxo agendado', { kind: 'success', detail: `${item.sentence}${item.next_text ? ` · próxima: ${item.next_text}` : ''}. Veja em Arquivo › Agendamentos.` });
      onDone?.(item);
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.hidden = false;
      if (!/regra da empresa/.test(err.message)) toastError(err, 'Não foi possível agendar');
    }
  };
  const deleteButton = existing ? button({ icon: 'trash', label: 'Excluir agendamento', variant: 'ghost', onClick: async () => {
    const { removeSchedule } = await import('./schedules_list.js');
    if (await removeSchedule(existing, onDone)) close();
  } }) : null;
  deleteButton?.classList.add('sch-delete', 'sch-delete-left');
  const primary = button({ icon: 'clock', label: existing ? 'Salvar agendamento' : dirty ? 'Salvar e agendar' : 'Agendar', variant: 'primary', disabled: protectedFlow, onClick: save });
  const { close } = openDialog({
    title: existing ? `Editar agendamento · ${target.name}` : `Agendar · ${target.name}`,
    size: 'lg',
    body: h('div', { class: 'sch-dialog' },
      h('div', { class: 'sch-layout' }, body, summary),
      ...notes,
      h('p', { class: 'field-help sch-security' }, icon('shield', 13), ` Roda com você conectado ao Windows, sem abrir janela, e grava as saídas como num Executar. O ${brand.nome} nunca pede nem guarda a senha do Windows.`),
      errorBox,
      advanced),
    actions: [
      existing ? deleteButton : null,
      button({ label: 'Cancelar', onClick: () => close() }), primary].filter(Boolean),
  });
}
