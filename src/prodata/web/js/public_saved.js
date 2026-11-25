// A pasta Dados públicos da vista Dados (spec 049, RF-4915, RF-4935): as fontes do catálogo guardadas com as escolhas,
// para usar em vários fluxos. Cada uma mostra a última leitura neste computador, a situação do órgão, o aviso Dados
// novos e os fluxos que a usam. Nada aqui acessa a rede: a conferência com os órgãos é a do catálogo aberto.

import { api } from './api.js';
import { usageMap } from './data_map.js';
import { KINDS, publicUses } from './data_sources.js';
import { button, h } from './dom.js';
import { icon } from './icons.js';
import { openPublicData } from './public_data.js';
import { addPublicNode, choicesSummary, selectionOf } from './public_data_box.js';
import { dot, statusText } from './public_data_health.js';
import { refreshSaved, savedSources } from './public_news.js';
import { confirmDialog, toast, toastError } from './ui.js';

export const PUBLIC_PREFIX = 'public:';
const keyOf = (item) => `${PUBLIC_PREFIX}${item.key}`;
const when = (iso) => new Date(iso).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
const day = (iso) => new Date(`${String(iso).slice(0, 10)}T12:00:00`).toLocaleDateString('pt-BR');

/** "À vista Dados" no catálogo: guarda a fonte com as escolhas e abre o detalhe dela. */
export async function savePublic(entry, choices, info) {
  try {
    const item = await api.publicSavedAdd(selectionOf(entry, choices, info));
    // O catálogo está aberto: já pergunta ao órgão a última atualização desta fonte, para o aviso Dados novos.
    api.publicNewsCheck([item.fonte.id]).then(() => refreshSaved()).catch(() => {});
    await refreshSaved();
    toast(`${item.fonte.nome} está na vista Dados`, { kind: 'success', detail: 'Na pasta Dados públicos, para usar em quantos fluxos quiser.' });
    return keyOf(item);
  } catch (err) {
    toastError(err, 'Não foi possível guardar na vista Dados');
    return null;
  }
}

/** A pasta na lista da esquerda (aparece só com alguma fonte guardada). */
export function publicSection({ selectedKey, onOpen }) {
  const items = savedSources();
  if (!items.length) return null;
  return h('section', { class: 'team-defs pd-saved', 'aria-label': 'Dados públicos' },
    h('div', { class: 'team-defs-head' }, icon('landmark', 14), h('strong', {}, 'Dados públicos'), h('span', { class: 'muted' }, String(items.length))),
    items.map((item) => {
      const key = keyOf(item);
      const news = item.novidade?.novo;
      const down = item.situacao?.situacao === 'fora';
      return h('button', { type: 'button', class: ['team-def-item', key === selectedKey && 'selected'], 'aria-current': key === selectedKey ? 'true' : null, onclick: () => onOpen(key) },
        h('span', { class: 'team-def-icon', style: { '--kind': KINDS.public.color } }, icon('landmark', 14)),
        h('span', { class: 'team-def-name ellipsis' }, item.fonte.nome || item.fonte.id),
        news ? h('span', { class: 'pd-news-chip', title: item.novidade.texto }, 'Dados novos')
          : down ? h('span', { class: 'team-chip err', title: item.situacao.motivo || '' }, 'Fora do ar') : null);
    }));
}

function facts(item) {
  const f = item.fonte;
  const n = item.novidade || {};
  const row = (label, value) => (value ? h('div', { class: 'pd-saved-fact' }, h('span', { class: 'muted' }, label), h('span', {}, value)) : null);
  return h('section', { class: 'dv-card pd-saved-facts' },
    row('Escolhas', choicesSummary(f) || 'as do catálogo'),
    row('Última leitura neste computador', n.lido_em ? when(n.lido_em) : 'ainda não lida: use num fluxo e execute'),
    row('O órgão informou', n.atualizado ? `${n.rotulo || 'atualizada em'} ${day(n.atualizado)}` : 'confere ao abrir o catálogo'),
    row('Como citar', f.citacao),
    row('Licença', f.licenca),
    row('Código da fonte', h('code', {}, f.id)));
}

/** O detalhe na área da direita: Usar no fluxo, Trocar e Excluir. */
export function publicSavedDetail(key, { showDesigner, openFlow, refresh, close }) {
  const item = savedSources().find((s) => keyOf(s) === key);
  if (!item) return h('div', { class: 'dv-detail' }, h('p', { class: 'muted' }, 'Essa fonte não está mais na vista Dados.'));
  const f = item.fonte;
  const uses = publicUses(f.id);
  const health = item.situacao;
  const news = item.novidade?.novo ? item.novidade : null;
  const use = () => {
    if (addPublicNode({ id: f.id, nome: f.nome }, f.escolhas || {}, f)) showDesigner();
  };
  const change = () => openPublicData({
    select: { id: f.id, nome: f.nome, orgao: f.orgao },
    choices: f.escolhas,
    useLabel: 'Guardar estas escolhas',
    onUse: async (entry, choices, _target, info) => {
      try {
        await api.publicSavedUpdate(item.key, selectionOf(entry, choices, info));
        await refreshSaved();
        refresh();
        toast('Escolhas guardadas', { kind: 'success', detail: 'Os fluxos que já usam esta fonte continuam com as escolhas deles.' });
      } catch (err) {
        toastError(err, 'Não foi possível guardar');
      }
    },
  });
  const remove = async () => {
    const ok = await confirmDialog({
      title: `Tirar ${f.nome} da vista Dados?`,
      message: uses.length ? `Os ${uses.length} fluxo(s) que usam esta fonte continuam funcionando: cada caixa guarda a própria fonte e as escolhas.`
        : 'Nenhum fluxo da biblioteca usa esta fonte. Ela continua no catálogo para escolher de novo.',
      confirm: 'Tirar da vista Dados', danger: true,
    });
    if (!ok) return;
    try {
      await api.publicSavedDelete(item.key);
    } catch (err) {
      toastError(err, 'Não foi possível tirar');
      return;
    }
    await refreshSaved();
    close();
  };
  const situation = health?.situacao || 'nao_conferido';
  return h('div', { class: 'dv-detail' },
    h('header', { class: 'dv-head' },
      h('span', { class: 'dv-head-icon', style: { '--kind': KINDS.public.color } }, icon('landmark', 22)),
      h('div', { class: 'dv-head-text' }, h('h2', {}, f.nome || f.id),
        h('p', {}, ['Dados públicos', f.orgao].filter(Boolean).join(' · ')),
        h('div', { class: 'dv-head-chips' },
          h('span', { class: 'dv-chip pd-saved-health', title: health?.motivo || '' }, dot(situation), statusText(health)),
          news ? h('span', { class: 'dv-chip pd-news-chip' }, icon('sparkles', 12), 'Dados novos') : null,
          h('span', { class: ['dv-chip', 'dv-chip-use', !uses.length && 'none'] }, uses.length ? `Usada em ${uses.length} fluxo(s)` : 'Ainda não usada em fluxos'))),
      h('div', { class: 'dv-head-actions' },
        button({ icon: 'plus', label: 'Usar no fluxo', variant: 'primary', onClick: use }),
        button({ icon: 'edit', label: 'Trocar as escolhas…', onClick: change }),
        button({ icon: 'trash', label: 'Tirar da vista Dados', variant: 'ghost', onClick: remove }))),
    news ? h('div', { class: 'pd-news-note', role: 'status' }, icon('sparkles', 14),
      h('span', {}, `${news.texto} Os fluxos que usam esta fonte leem os dados novos na próxima execução.`)) : null,
    facts(item),
    h('section', { class: 'stack-sm' }, h('h3', { class: 'pd-saved-title' }, 'Onde é usada'),
      usageMap({ kind: 'public', name: f.nome || f.id, meta: f.orgao || '' }, uses, openFlow)));
}
