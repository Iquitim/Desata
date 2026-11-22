// Agendamentos do time (spec 047, RF-4753): os agendamentos dos fluxos do espaço em todos os computadores — de quem,
// onde, a próxima e a última execução — e "Assumir este agendamento" (Publicador).

import { api } from './api.js';
import { button, fmt, h } from './dom.js';
import { icon } from './icons.js';
import { openDialog, toast, toastError } from './ui.js';

const RANK = { leitor: 0, editor: 1, publicador: 2, administrador: 3 };
const STATUS = { ok: ['ok', 'Concluído'], failed: ['err', 'Falhou'], refused: ['err', 'Não executou'] };

function lastRun(u) {
  if (!u) return h('span', { class: 'muted' }, 'Ainda não rodou');
  const [tone, label] = STATUS[u.status] || ['warn', u.status];
  return h('span', { class: `team-reason ${tone}`, title: u.message || '' },
    `Última: ${label}${u.finished_at ? `, ${fmt.date(u.finished_at)}` : ''}${u.message ? ` · ${u.message}` : ''}`);
}

export async function openTeamSchedules(space) {
  const list = h('div', { class: 'team-members' }, h('p', { class: 'muted' }, 'Carregando…'));
  const body = h('div', { class: 'form' },
    h('p', { class: 'field-help' }, 'Cada agendamento roda a versão oficial do fluxo, no computador de quem agendou. '
      + 'Se essa pessoa sair de férias, um Publicador pode assumir: a tarefa passa para o computador dele, e o anterior deixa de rodar.'),
    list);
  const { close } = openDialog({ title: `Agendamentos · ${space.nome}`, size: 'md', body,
    actions: [button({ label: 'Fechar', onClick: () => close() })] });

  const draw = async () => {
    let view;
    try {
      view = await api.teamSchedules(space.id);
    } catch (err) {
      list.replaceChildren(h('p', { class: 'field-error' }, err.message || 'Não foi possível ler os agendamentos.'));
      return;
    }
    const canAssume = RANK[view.papel] >= RANK.publicador;
    const items = view.agendamentos;
    if (!items.length) {
      list.replaceChildren(h('div', { class: 'ver-empty' }, icon('clock', 28), h('strong', {}, 'Nenhum fluxo do espaço está agendado'),
        h('p', {}, 'Abra um fluxo do espaço e use Arquivo › Agendar. O agendamento roda a versão oficial.')));
      return;
    }
    list.replaceChildren(...items.map((s) => {
      let chip = null;
      if (s.substituido_por) chip = h('span', { class: 'team-chip warn' }, `Assumido por ${s.substituido_por.nome}`);
      else if (!s.confere) chip = h('span', { class: 'team-chip err', title: 'O estado publicado não tem a assinatura de um membro.' }, 'Não confere');
      else if (s.pausado) chip = h('span', { class: 'team-chip warn' }, 'Desativado');
      else if (s.meu) chip = h('span', { class: 'team-chip ok' }, 'Seu');
      const assume = canAssume && s.confere && !s.meu && !s.substituido_por
        ? button({ label: 'Assumir', size: 'sm', variant: 'ghost', title: 'Cria a tarefa neste computador e o computador anterior deixa de rodar.',
          onClick: async () => {
            try {
              const item = await api.assumeSchedule(space.id, s.id);
              toast('Agendamento assumido', { kind: 'success', detail: `${item.sentence}, neste computador. O de ${s.nome} deixa de rodar.` });
              draw();
            } catch (err) { toastError(err, 'Não foi possível assumir'); }
          } }) : null;
      return h('div', { class: 'team-member' }, icon('clock', 16),
        h('div', { class: 'grow' },
          h('strong', {}, s.fluxo_nome || s.fluxo),
          h('div', { class: 'wf-desc' }, `${s.frase} · de ${s.nome} em ${s.maquina || 'outro computador'}`
            + `${s.proxima && !s.substituido_por ? ` · próxima: ${fmt.date(s.proxima)}` : ''}`),
          lastRun(s.ultima)),
        chip, assume);
    }));
  };
  draw();
}
