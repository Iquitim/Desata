// Definições da equipe na vista Dados (spec 048, RF-4801..4808): a pasta "Da equipe · <espaço>", o detalhe de cada
// definição, Compartilhar com a equipe… e o pedido da senha de cada pessoa. Sem espaço, nada daqui aparece.

import { api } from './api.js';
import { KINDS } from './data_sources.js';
import { button, fmt, h } from './dom.js';
import { icon } from './icons.js';
import { store } from './store.js';
import { canWrite, chooseSpace, teamConfigured, usableSpaces } from './team_spaces.js';
import { confirmDialog, openDialog, toast, toastError } from './ui.js';

const KIND_OF = { conexoes: 'conn', consultas: 'query', apis: 'api', constantes: 'const' };
const TIPO_OF = { conn: 'conexoes', query: 'consultas', api: 'apis', const: 'constantes' };
const ONE = { conexoes: 'conexão', consultas: 'consulta', apis: 'API', constantes: 'constante' };
const DB = { postgres: 'PostgreSQL', mssql: 'SQL Server', odbc: 'ODBC' };
const RANK = { leitor: 0, editor: 1, publicador: 2, administrador: 3 };
const defs = new Map(); // espaço → resposta de /definicoes

export const teamDefs = (spaceId) => defs.get(spaceId) || null;

/** Lê as definições de cada espaço em que a pessoa é membro. Sem espaço, não chama nada. */
export async function refreshTeamDefinitions() {
  defs.clear();
  if (!teamConfigured()) return;
  await Promise.all(usableSpaces().map(async (s) => {
    try { defs.set(s.id, await api.teamDefinitions(s.id)); } catch { /* espaço inacessível agora: fica de fora */ }
  }));
}

const rows = (data) => ['constantes', 'conexoes', 'consultas', 'apis'].flatMap((tipo) => (data?.[tipo] || []).map((d) => ({ ...d, tipo })));
export const teamKey = (spaceId, tipo, id) => `team:${spaceId}:${tipo}:${id}`;

/** A pasta "Da equipe · <espaço>" no fim da lista da vista Dados. */
export function teamSection({ selectedKey, onOpen }) {
  const spaces = usableSpaces().filter((s) => defs.has(s.id));
  if (!spaces.length) return null;
  return h('div', { class: 'team-defs' }, spaces.map((s) => {
    const items = rows(defs.get(s.id));
    return h('section', { class: 'team-defs-space' },
      h('div', { class: 'team-defs-head' }, icon('folder', 14), h('strong', {}, `Da equipe · ${s.nome}`),
        h('span', { class: 'muted' }, String(items.length))),
      items.length ? items.map((d) => {
        const kind = KINDS[KIND_OF[d.tipo]];
        const key = teamKey(s.id, d.tipo, d.id);
        const flag = !d.confere ? h('span', { class: 'team-chip err', title: d.motivo || '' }, 'Não confere')
          : d.campos?.length && !d.tem_segredo ? h('span', { class: 'team-chip warn', title: 'Falta a sua senha neste computador' }, 'Sua senha')
            : null;
        return h('button', { type: 'button', class: ['team-def-item', key === selectedKey && 'selected'], 'aria-current': key === selectedKey ? 'true' : null, onclick: () => onOpen(key) },
          h('span', { class: 'team-def-icon', style: { '--kind': kind.color } }, icon(kind.icon, 14)),
          h('span', { class: 'team-def-name ellipsis' }, d.nome), flag);
      }) : h('p', { class: 'muted small team-defs-empty' }, 'Nada compartilhado ainda. Numa fonte deste computador, use Compartilhar com a equipe….'));
  }));
}

function fields(d) {
  const c = d.conteudo || {};
  const line = (label, value, mono = false) => (value ? h('div', { class: 'team-def-field' }, h('span', { class: 'muted' }, label), h(mono ? 'code' : 'span', {}, value)) : null);
  if (d.tipo === 'conexoes') {
    return [line('Banco', DB[c.kind] || c.kind), line('Servidor', c.host ? `${c.host}${c.port ? `:${c.port}` : ''}` : ''), line('Database', c.database),
      line('Usuário', c.user), line('Fonte ODBC', c.odbc_dsn)];
  }
  if (d.tipo === 'consultas') {
    return [line('Conexão', c.connection), c.mode === 'table' ? line('Tabela', c.table, true) : h('pre', { class: 'team-def-sql mono' }, c.query || '')];
  }
  if (d.tipo === 'apis') {
    return [line('Endereço', `${c.method || 'GET'} ${c.url || ''}`, true),
      ...(c.params || []).filter((p) => !p.secret && p.name).map((p) => line(`Parâmetro ${p.name}`, p.value, true))];
  }
  return [line('Valor', c.value, true), line('Tipo', c.type), line('Descrição', c.description)];
}

const localHas = (tipo, id) => ({
  conexoes: () => (store.connections || []).some((x) => x.id === id),
  consultas: () => (store.queries || []).some((x) => x.id === id),
  apis: () => (store.apis || []).some((x) => x.id === id),
  constantes: () => (store.constants || []).some((x) => x.name === id),
}[tipo]());

/** O detalhe de uma definição da equipe, na área principal da vista Dados. */
export function teamDetail(key, { refresh, close }) {
  const [, spaceId, tipo, id] = key.split(':');
  const space = usableSpaces().find((s) => s.id === spaceId);
  const data = defs.get(spaceId);
  const d = rows(data).find((x) => x.tipo === tipo && x.id === id);
  if (!space || !d) return h('div', { class: 'dv-detail' }, h('p', { class: 'muted' }, 'Essa definição não está mais no espaço.'));
  const kind = KINDS[KIND_OF[tipo]];
  const editor = RANK[data.papel] >= RANK.editor && canWrite(space);
  const act = (label, fn) => async () => { try { await fn(); await refresh(); } catch (err) { toastError(err, label); } };
  const actions = [
    d.confere && d.campos?.length ? button({ icon: 'lock', label: d.tem_segredo ? 'Trocar a minha senha' : 'Digitar a minha senha',
      variant: d.tem_segredo ? 'ghost' : 'primary', onClick: async () => { if (await secretDialog(spaceId, [{ ...d, campos: d.campos }])) await refresh(); } }) : null,
    d.confere ? button({ icon: 'download', label: 'Trazer para este computador', variant: 'ghost',
      title: 'Uma cópia na vista Dados daqui, para editar e depois atualizar na equipe. A senha não vem.',
      onClick: act('Não foi possível trazer', async () => {
        await api.bringDefinition(spaceId, tipo, id);
        toast('Trazida para este computador', { kind: 'success', detail: 'Edite a cópia daqui e use Atualizar na equipe… para mandar de volta.' });
      }) }) : null,
    editor ? button({ icon: 'trash', label: 'Excluir da equipe', variant: 'ghost', onClick: async () => {
      const ok = await confirmDialog({ title: `Excluir ${d.nome} da equipe?`, message: 'Os fluxos do espaço que usam esta definição passam a procurar a deste computador de cada pessoa.', confirm: 'Excluir', danger: true });
      if (ok) await act('Não foi possível excluir', () => api.deleteDefinition(spaceId, tipo, id))();
      if (ok) close();
    } }) : null,
  ].filter(Boolean);
  return h('div', { class: 'dv-detail' },
    h('header', { class: 'dv-head' },
      h('span', { class: 'dv-head-icon', style: { '--kind': kind.color } }, icon(kind.icon, 22)),
      h('div', { class: 'dv-head-text' }, h('h2', {}, d.nome),
        h('div', { class: 'dv-head-chips' },
          h('span', { class: 'dv-chip' }, icon('folder', 12), ` Da equipe · ${space.nome}`),
          d.confere ? h('span', { class: 'team-chip ok' }, 'Confere') : h('span', { class: 'team-chip err' }, 'Não confere'))),
      h('div', { class: 'dv-head-actions' }, actions)),
    h('div', { class: 'dv-body' },
      !d.confere ? h('div', { class: 'banner banner-error' }, icon('alert', 15), h('div', { class: 'banner-body' },
        `${d.motivo} Nenhum fluxo usa esta ${ONE[tipo]} até alguém da equipe salvar de novo pelo programa.`)) : null,
      h('div', { class: 'dv-card team-def-card' },
        h('p', { class: 'muted small' }, `Salva por ${d.autor_nome || 'desconhecido'}${d.quando ? ` em ${fmt.date(d.quando)}` : ''}.`
          + ' Nos fluxos do espaço, vale esta; fora do espaço, a deste computador.'),
        ...fields(d)),
      localHas(tipo, id) ? h('p', { class: 'field-help' }, icon('info', 12),
        ` Este computador também tem uma ${ONE[tipo]} com esse identificador. Num fluxo do espaço vale a da equipe; nos outros fluxos, a daqui.`) : null,
      d.campos?.length ? h('p', { class: 'field-help' }, icon('shield', 12),
        ' A senha não vai para a pasta da equipe: cada pessoa digita a sua uma vez, e ela fica no cofre do Windows deste computador.') : null));
}

/** "Compartilhar com a equipe…" (ou "Atualizar na equipe…") numa fonte deste computador. */
export function shareButton(source, onDone) {
  const tipo = TIPO_OF[source.kind];
  if (!tipo || !teamConfigured() || !usableSpaces().some(canWrite)) return null;
  const id = source.kind === 'const' ? source.raw.name : source.raw.id;
  const already = usableSpaces().some((s) => rows(defs.get(s.id)).some((d) => d.tipo === tipo && d.id === id));
  return button({ icon: 'folder', label: already ? 'Atualizar na equipe…' : 'Compartilhar com a equipe…', variant: 'ghost', onClick: async () => {
    const space = await chooseSpace(already ? 'Atualizar na equipe' : 'Compartilhar com a equipe');
    if (!space) return;
    try {
      await api.shareDefinition(space.id, tipo, id);
      toast(already ? 'Atualizada na equipe' : 'Compartilhada com a equipe', { kind: 'success',
        detail: `Espaço "${space.nome}". A senha não foi junto: cada pessoa digita a sua.` });
      await refreshTeamDefinitions();
      onDone?.();
    } catch (err) { toastError(err, 'Não foi possível compartilhar'); }
  } });
}

const LABELS = { senha: 'Senha', token: 'Token', key: 'Chave', password: 'Senha', client_secret: 'Segredo do cliente' };

/** Pede a senha (ou token) de cada pessoa para conexões e APIs da equipe. Devolve true se guardou. */
export function secretDialog(spaceId, items) {
  return new Promise((resolve) => {
    let saved = false;
    const inputs = [];
    const body = h('div', { class: 'form' },
      h('p', { class: 'field-help' }, 'Fica só no cofre do Windows deste computador: não vai para a pasta da equipe nem para o fluxo.'),
      items.map((it) => h('fieldset', { class: 'team-secret' },
        h('legend', {}, h('strong', {}, `${ONE[it.tipo]} ${it.nome}`), it.servidor || it.conteudo?.host
          ? h('span', { class: 'muted' }, ` · ${it.servidor || it.conteudo.host}${it.usuario || it.conteudo?.user ? `, usuário ${it.usuario || it.conteudo.user}` : ''}`) : null),
        (it.campos || ['senha']).map((campo) => {
          const input = h('input', { type: 'password', class: 'input', autocomplete: 'off', 'aria-label': `${LABELS[campo] || campo} de ${it.nome}` });
          inputs.push({ it, campo, input });
          return h('label', { class: 'field' }, h('span', { class: 'field-label' }, LABELS[campo.replace(/^(param|header):/, '')] || campo), input);
        }))));
    const save = async () => {
      try {
        for (const it of items) {
          const valores = Object.fromEntries(inputs.filter((x) => x.it === it && x.input.value).map((x) => [x.campo, x.input.value]));
          if (Object.keys(valores).length) await api.setDefinitionSecret(spaceId, it.tipo, it.id, valores);
        }
        saved = true;
        close();
      } catch (err) { toastError(err, 'Não foi possível guardar'); }
    };
    const { close } = openDialog({
      title: items.length === 1 ? 'Sua senha para usar esta definição da equipe' : 'Suas senhas para as definições da equipe',
      size: 'sm',
      body,
      actions: [button({ label: 'Agora não', onClick: () => close() }), button({ icon: 'lock', label: 'Guardar', variant: 'primary', onClick: save })],
      onClose: () => resolve(saved),
    });
    requestAnimationFrame(() => inputs[0]?.input.focus());
  });
}

/** Antes de executar um fluxo do espaço: pede de uma vez as senhas que faltam (RF-4804). Devolve false se desistiu. */
export async function ensureSecrets(spaceId, workflow) {
  let missing = [];
  try { missing = await api.missingSecrets(spaceId, workflow); } catch { return true; } // sem resposta: a caixa explica
  if (!missing.length) return true;
  return secretDialog(spaceId, missing);
}
