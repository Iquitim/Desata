// Espaço da equipe (spec 047, RF-4701..4705, RF-4716): o diálogo dos espaços, a escolha de um espaço e a lista de
// fluxos de um espaço, usada pela biblioteca. Opcional: sem espaço configurado, nada daqui aparece além do item de
// menu Espaços da equipe… (RF-4702).

import { api } from './api.js';
import { brand } from './brand.js';
import { chooseFolder } from './desktop.js';
import { button, fmt, h } from './dom.js';
import { icon } from './icons.js';
import { openDialog, toast, toastError } from './ui.js';
import { openMembersDialog, ROLE_NAMES } from './team_members.js';
import { openTeamSchedules } from './team_schedules.js';

let state = { configurado: false, espacos: [] };
export const teamState = () => state;
export const teamConfigured = () => Boolean(state.configurado);

const RANK = { leitor: 0, editor: 1, publicador: 2, administrador: 3 };
export const canWrite = (s) => s.estado === 'ok' && !s.protegido && RANK[s.papel] >= RANK.editor;
/** Espaços em que a pessoa é membro (lê): os que aparecem como aba da biblioteca. */
export const usableSpaces = () => state.espacos.filter((s) => (s.estado === 'ok' || s.estado === 'somente_leitura') && s.papel);

export async function refreshTeam() {
  try { state = await api.team(); } catch { /* sem a resposta, a tela fica como sem espaço */ }
  return state;
}

const STATE_LABEL = {
  ok: ['ok', 'Disponível'],
  somente_leitura: ['warn', 'Só leitura'],
  pasta_ausente: ['err', 'Pasta inacessível'],
  outra_marca: ['err', 'Indisponível'],
  invalido: ['err', 'Com problema'],
};

/** Arquivo › Espaços da equipe…: criar, entrar e sair, com a explicação do que é (e de que é opcional). */
export async function openSpacesDialog({ onChanged } = {}) {
  await refreshTeam();
  const nameInput = h('input', {
    class: 'input', maxlength: 80, value: state.identidade?.tem_nome ? state.identidade.nome : '',
    placeholder: state.identidade?.usuario ? `Ex.: ${state.identidade.usuario}` : 'Seu nome, como o time vai ver',
    'aria-label': 'Seu nome no espaço',
  });
  const list = h('div', { class: 'team-spaces' });
  const changed = async () => { await refreshTeam(); draw(); onChanged?.(); };

  const saveName = async () => {
    const nome = nameInput.value.trim();
    if (nome && nome !== state.identidade?.nome) await api.teamName(nome);
  };
  const add = async (acao) => {
    const folder = await chooseFolder('', 'Pasta do espaço da equipe', '\\\\servidor\\equipe ou D:\\OneDrive\\Equipe');
    if (!folder) return;
    let nome = '';
    if (acao === 'criar') {
      nome = await askSpaceName();
      if (!nome) return;
    }
    try {
      await saveName(); // antes: o pedido de entrada e a lista de membros levam o nome escolhido
      const space = await api.addSpace(acao, folder, nome);
      toast(acao === 'criar' ? `Espaço "${space.nome}" criado` : space.papel ? `Você entrou em "${space.nome}"` : `Pedido enviado para "${space.nome}"`, {
        kind: 'success',
        detail: space.papel ? 'Ele aparece como uma aba em Abrir da biblioteca.' : 'Um administrador do espaço precisa aceitar e escolher o seu papel.',
      });
      await changed();
    } catch (err) {
      toastError(err, acao === 'criar' ? 'Não foi possível criar o espaço' : 'Não foi possível entrar no espaço');
    }
  };
  const draw = () => {
    list.replaceChildren(...(state.espacos.length ? state.espacos.map((s) => {
      let [tone, label] = STATE_LABEL[s.estado] || STATE_LABEL.invalido;
      let reason = s.motivo;
      if (s.protegido) [tone, label, reason] = ['err', 'Protegido', `${s.protegido} Nada do espaço executa até um administrador conferir.`];
      else if (s.papel) label = ROLE_NAMES[s.papel];
      else if (s.pedido) [tone, label, reason] = ['warn', 'Pedido enviado', 'Aguardando um administrador aceitar e escolher o seu papel.'];
      return h('div', { class: 'team-space' },
        icon('folder', 16),
        h('div', { class: 'grow' }, h('strong', {}, s.nome),
          h('div', { class: 'wf-desc mono' }, s.caminho),
          reason ? h('div', { class: `team-reason ${tone}` }, reason) : null),
        h('span', { class: `team-chip ${tone}` }, label),
        s.papel ? button({ label: 'Membros…', size: 'sm', variant: 'ghost', onClick: () => openMembersDialog(s, changed) }) : null,
        s.papel ? button({ label: 'Agendamentos…', size: 'sm', variant: 'ghost', onClick: () => openTeamSchedules(s) }) : null,
        button({
          label: 'Sair', size: 'sm', variant: 'ghost', title: 'Sai do espaço neste computador. Nada é apagado da pasta.',
          onClick: async () => {
            try { await api.leaveSpace(s.id); await changed(); } catch (err) { toastError(err, 'Não foi possível sair'); }
          },
        }));
    }) : [h('p', { class: 'muted' }, 'Você ainda não está em nenhum espaço.')]));
  };
  draw();
  openDialog({
    title: 'Espaços da equipe',
    size: 'md',
    body: h('div', { class: 'form' },
      h('p', { class: 'dialog-text' }, `Um espaço é uma pasta compartilhada — da rede, do OneDrive ou do SharePoint — onde o time guarda os fluxos e trabalha junto. `
        + `É opcional: quem usa o ${brand.nome} só neste computador não precisa de nada disto, e nada muda para essa pessoa.`),
      h('label', { class: 'field' }, h('span', { class: 'field-label' }, 'Seu nome no espaço'), nameInput,
        h('span', { class: 'field-help' }, 'Aparece para o time em "quem está editando" e nas versões.')),
      h('div', { class: 'panel-subtitle' }, 'Seus espaços'), list,
      h('p', { class: 'field-help' }, 'Os dados das fontes, os resultados e as senhas nunca vão para a pasta do espaço.')),
    actions: [
      button({ label: 'Entrar num espaço…', icon: 'folder', onClick: () => add('entrar') }),
      button({ label: 'Criar espaço…', icon: 'plus', variant: 'primary', onClick: () => add('criar') }),
    ],
  });
}

function askSpaceName() {
  return new Promise((resolve) => {
    let answer = '';
    const input = h('input', { class: 'input', maxlength: 80, placeholder: 'Ex.: Controladoria', 'aria-label': 'Nome do espaço' });
    const ok = button({ label: 'Criar', variant: 'primary', onClick: () => { answer = input.value.trim(); close(); } });
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && input.value.trim()) { e.preventDefault(); answer = input.value.trim(); close(); }
    });
    const { close } = openDialog({
      title: 'Nome do espaço', size: 'sm',
      body: h('div', { class: 'form' }, h('label', { class: 'field' }, h('span', { class: 'field-label' }, 'Nome'), input,
        h('span', { class: 'field-help' }, 'Como o time vai reconhecer o espaço, por exemplo o nome da área.'))),
      actions: [button({ label: 'Cancelar', onClick: () => close() }), ok],
      onClose: () => resolve(answer),
    });
    requestAnimationFrame(() => input.focus());
  });
}

/** Escolhe um espaço disponível para gravar (Salvar no espaço…, Mover para o espaço…). */
export function chooseSpace(title) {
  const spaces = state.espacos.filter(canWrite); // só onde o papel deixa salvar (Editor ou acima)
  if (!spaces.length) {
    toast('Nenhum espaço em que você possa salvar', { detail: 'Salvar num espaço é para Editor ou acima. Veja os seus espaços em Arquivo › Espaços da equipe…' });
    return Promise.resolve(null);
  }
  if (spaces.length === 1) return Promise.resolve(spaces[0]);
  return new Promise((resolve) => {
    let answer = null;
    const { close } = openDialog({
      title, size: 'sm',
      body: h('div', { class: 'wf-list' }, spaces.map((s) => h('div', { class: 'wf-item' },
        h('button', { type: 'button', class: 'wf-main', onclick: () => { answer = s; close(); } },
          icon('folder', 16), h('span', { class: 'grow' }, h('strong', {}, s.nome), h('span', { class: 'wf-desc mono' }, s.caminho)))))),
      actions: [button({ label: 'Cancelar', onClick: () => close() })],
      onClose: () => resolve(answer),
    });
  });
}

/** Selo da versão oficial (spec 047, RF-4751): quem publicou e se a versão de trabalho está à frente. */
function officialChip(o) {
  if (!o) return null;
  if (!o.confere) return h('span', { class: 'team-chip err', title: o.motivo || 'A versão oficial não confere' }, icon('alert', 11), ' Oficial não confere');
  const title = `Versão oficial publicada por ${o.nome}${o.quando ? ` em ${fmt.date(o.quando)}` : ''}. ${o.atual ? 'É a mesma da versão de trabalho.' : 'A versão de trabalho tem mudanças depois dela.'}`;
  return h('span', { class: `team-chip ${o.atual ? 'ok' : 'warn'}`, title }, icon('star', 11), o.atual ? ' Oficial' : ' Oficial · trabalho à frente');
}

/** A lista de fluxos de um espaço, para a aba dele em Abrir da biblioteca. */
export function spacePane(space, { onOpen, onCopied }) {
  const box = h('div', { class: 'wf-list' }, h('p', { class: 'muted' }, 'Carregando os fluxos do espaço…'));
  (async () => {
    try {
      const flows = await api.spaceFlows(space.id);
      box.replaceChildren(...(flows.length ? flows.map((f) => h('div', { class: 'wf-item' },
        h('button', { type: 'button', class: 'wf-main', onclick: () => onOpen(f) },
          icon('workflow', 16), h('span', { class: 'grow' }, h('strong', {}, f.name),
            h('small', { class: 'muted' }, ` · ${f.node_count} caixas · ${fmt.date(f.modified_at)}`)),
            f.editando ? h('span', { class: 'team-chip warn', title: `${f.editando} está editando agora` }, icon('edit', 11), ` ${f.editando}`) : null,
            officialChip(f.oficial)),
        button({
          icon: 'copy', title: 'Fazer uma cópia em Meus fluxos', size: 'sm', variant: 'ghost',
          onClick: async () => {
            try {
              const copy = await api.copyFromSpace(space.id, f.id);
              toast('Cópia feita em Meus fluxos', { kind: 'success', detail: copy.name });
              onCopied?.(copy);
            } catch (err) { toastError(err, 'Não foi possível copiar'); }
          },
        }))) : [h('p', { class: 'muted' }, 'Nenhum fluxo neste espaço ainda. Use Salvar no espaço… ou Mover para o espaço… para trazer um.')]));
    } catch (err) {
      box.replaceChildren(h('p', { class: 'field-error' }, err.message || 'Não foi possível ler o espaço.'));
    }
  })();
  return box;
}

/** Abrir da biblioteca: com algum espaço, abas "Meus fluxos" e uma por espaço; sem espaço, a biblioteca de sempre
 * (RF-4702, RF-4703). */
export function libraryTabs(libraryBody, { onOpen, onCopied }) {
  const spaces = usableSpaces();
  if (!teamConfigured() || !spaces.length) return libraryBody;
  const pane = h('div', { class: 'stack-sm' }, libraryBody);
  const tabs = h('div', { class: 'segmented small team-tabs', role: 'tablist', 'aria-label': 'Onde estão os fluxos' });
  const show = (key) => {
    tabs.querySelectorAll('.segment').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.key === key)));
    const space = spaces.find((s) => s.id === key);
    pane.replaceChildren(space
      ? spacePane(space, { onOpen: (f) => onOpen(space, f), onCopied })
      : libraryBody);
  };
  for (const [key, label] of [['__meus', 'Meus fluxos'], ...spaces.map((s) => [s.id, s.nome])]) {
    tabs.append(h('button', { type: 'button', class: 'segment', role: 'tab', dataset: { key }, 'aria-selected': String(key === '__meus'),
      onclick: () => show(key) }, key === '__meus' ? icon('workflow', 13) : icon('folder', 13), label));
  }
  return h('div', { class: 'stack-sm' }, tabs, pane);
}

/** Botão "Mover para o espaço…" de um fluxo de Meus fluxos (só com algum espaço que aceita gravar). */
export function moveButton(workflow, onMoved) {
  if (!state.espacos.some(canWrite)) return null;
  return button({
    icon: 'folder', title: 'Mover para o espaço da equipe…', size: 'sm', variant: 'ghost',
    onClick: async () => {
      const space = await chooseSpace(`Mover "${workflow.name}" para…`);
      if (!space) return;
      try {
        await api.moveToSpace(space.id, workflow.id);
        toast(`"${workflow.name}" está no espaço "${space.nome}"`, { kind: 'success', detail: 'Saiu de Meus fluxos. O time já pode abrir.' });
        onMoved?.(space);
      } catch (err) { toastError(err, 'Não foi possível mover'); }
    },
  });
}
