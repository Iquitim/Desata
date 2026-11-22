// Membros de um espaço da equipe (spec 047, RF-4711..4718): quem está, o que cada um pode fazer, pedidos de entrada e
// o que cada camada de segurança garante. Para a pessoa, são pessoas e papéis: a palavra "chave" não aparece.

import { api } from './api.js';
import { button, h } from './dom.js';
import { icon } from './icons.js';
import { openDialog, toast, toastError } from './ui.js';

export const ROLE_NAMES = { leitor: 'Leitor', editor: 'Editor', publicador: 'Publicador', administrador: 'Administrador' };
const ROLE_HELP = {
  leitor: 'abre e executa no próprio computador',
  editor: 'também salva versões',
  publicador: 'também marca a versão oficial, a que os agendamentos rodam',
  administrador: 'também cuida de quem entra e do papel de cada um',
};

const roleSelect = (value, onChange, disabled = false) => {
  const select = h('select', { class: 'input select-sm', 'aria-label': 'Papel', disabled },
    Object.entries(ROLE_NAMES).map(([k, label]) => h('option', { value: k, selected: k === value }, label)));
  select.addEventListener('change', () => onChange(select.value));
  return select;
};

/** O que cada camada garante, em português claro (RF-4716, RF-4718). */
function layersHelp() {
  return h('details', { class: 'team-help' },
    h('summary', {}, icon('shield', 14), 'Como o espaço fica seguro'),
    h('ul', {},
      h('li', {}, h('strong', {}, 'A permissão da pasta impede. '), 'Quem só pode ler a pasta não grava nada. Para dar acesso só de leitura: na pasta de rede, em Propriedades › Segurança; no OneDrive e no SharePoint, compartilhe com "Pode exibir".'),
      h('li', {}, h('strong', {}, 'As assinaturas detectam e recusam. '), 'Cada versão salva e a lista de membros levam a assinatura de quem fez. Algo mudado fora do programa, ou por quem não podia, abre protegido e não executa.'),
      h('li', {}, h('strong', {}, 'O limite. '), 'Quem pode gravar na pasta ainda pode apagar arquivos. O histórico de versões do OneDrive e do SharePoint ajuda a recuperar.')));
}

export async function openMembersDialog(space, onChanged) {
  const body = h('div', { class: 'form' }, h('p', { class: 'muted' }, 'Carregando os membros…'));
  const { close } = openDialog({ title: `Membros · ${space.nome}`, size: 'md', body, actions: [button({ label: 'Fechar', onClick: () => close() })] });

  const act = async (acao, usuario, papel) => {
    try {
      render(await api.changeMembers(space.id, acao, usuario, papel));
      onChanged?.();
      toast(acao === 'aceitar' ? 'Pessoa aceita no espaço' : acao === 'recusar' ? 'Pedido recusado' : acao === 'remover' ? 'Pessoa removida do espaço' : 'Papel alterado', { kind: 'success' });
    } catch (err) {
      toastError(err, 'Não foi possível mudar os membros');
    }
  };

  const render = (view) => {
    const admin = view.papel === 'administrador';
    const people = view.membros.map((m) => h('div', { class: 'team-member' },
      icon('user', 15),
      h('div', { class: 'grow' }, h('strong', {}, m.nome), h('span', { class: 'muted small' }, ` · ${m.usuario}`),
        h('div', { class: 'muted small' }, ROLE_HELP[m.papel])),
      admin ? roleSelect(m.papel, (papel) => act('papel', m.usuario, papel)) : h('span', { class: 'team-chip ok' }, ROLE_NAMES[m.papel]),
      admin ? button({ icon: 'trash', title: `Remover ${m.nome} do espaço`, size: 'sm', variant: 'ghost', onClick: () => act('remover', m.usuario) }) : null));
    const requests = view.pedidos.map((p) => {
      let papel = 'editor';
      return h('div', { class: 'team-member request' },
        icon('user', 15),
        h('div', { class: 'grow' }, h('strong', {}, p.nome), h('span', { class: 'muted small' }, ` · ${p.usuario}`),
          h('div', { class: 'muted small' }, 'Pediu para entrar no espaço')),
        roleSelect(papel, (v) => { papel = v; }),
        button({ label: 'Aceitar', size: 'sm', variant: 'primary', onClick: () => act('aceitar', p.usuario, papel) }),
        button({ label: 'Recusar', size: 'sm', variant: 'ghost', onClick: () => act('recusar', p.usuario) }));
    });
    body.replaceChildren(...[
      view.protegido ? h('div', { class: 'banner banner-error' }, icon('alert', 15), h('div', { class: 'banner-body' }, view.protegido)) : null,
      admin && view.um_administrador ? h('div', { class: 'banner banner-warn' }, icon('alert', 15), h('div', { class: 'banner-body' },
        'Só há um administrador. Promova mais alguém: sem administrador, ninguém consegue mudar os papéis do espaço.')) : null,
      requests.length ? h('div', { class: 'panel-subtitle' }, `Pedidos de entrada (${requests.length})`) : null,
      ...requests,
      h('div', { class: 'panel-subtitle' }, `Membros (${people.length})`),
      ...people,
      admin ? null : h('p', { class: 'field-help' }, 'Só um administrador muda os membros e os papéis.'),
      layersHelp()].filter(Boolean)); // null vira o texto "null" no replaceChildren
  };

  try {
    render(await api.spaceMembers(space.id));
  } catch (err) {
    toastError(err, 'Não foi possível ler os membros');
    close();
  }
}
