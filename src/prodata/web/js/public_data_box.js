// A caixa Dados públicos no fluxo (spec 049, RF-4915, RF-4938): criar pelo catálogo e o cartão do Configurar,
// com Trocar a fonte ou as escolhas e Aceitar o novo formato.

import { addNode } from './actions.js';
import { api } from './api.js';
import { viewportCenter } from './canvas.js';
import { button, h } from './dom.js';
import { registerWidget } from './fields.js';
import { icon } from './icons.js';
import { openPublicData } from './public_data.js';
import { toast, toastError } from './ui.js';

const PERIOD_WORDS = (p) => {
  if (!p) return '';
  if (p.kind === 'ultimos_anos') return p.anos === 1 ? 'último ano' : `últimos ${p.anos} anos`;
  if (p.kind === 'desde') return `desde ${new Date(`${p.inicio}T12:00:00`).toLocaleDateString('pt-BR')}`;
  if (p.kind === 'intervalo') return `${new Date(`${p.inicio}T12:00:00`).toLocaleDateString('pt-BR')} a ${new Date(`${p.fim}T12:00:00`).toLocaleDateString('pt-BR')}`;
  return 'todo o período';
};

/** A configuração da caixa a partir do que foi escolhido no catálogo. O fluxo guarda só referência e escolhas. */
export function selectionOf(entry, choices, info = {}) {
  return {
    id: entry.id,
    nome: info?.nome || entry.nome || entry.id,
    orgao: info?.orgao || '',
    citacao: info?.citacao || '',
    licenca: info?.licenca || '',
    escolhas: { ...choices },
  };
}

/** Adicionar ao fluxo: a caixa no centro do canvas, já configurada. */
export function addPublicNode(entry, choices, info) {
  const c = viewportCenter();
  const fonte = selectionOf(entry, choices, info);
  const created = addNode('io.public_data', c.x - 94, c.y - 28, { fonte, __label: fonte.nome });
  if (created) toast(`${fonte.nome} entrou no fluxo`, { kind: 'success', detail: 'Execute para ler direto do órgão.' });
  return created;
}

function summary(fonte) {
  const e = fonte.escolhas || {};
  const parts = [PERIOD_WORDS(e.periodo)];
  if (e.moeda) parts.push(e.moeda);
  if (e.local && e.local !== 'BR') parts.push(e.local);
  if (e.nivel) parts.push({ N1: 'Brasil', N2: 'regiões', N3: 'estados', N6: 'municípios' }[e.nivel] || e.nivel);
  if (e.consulta) parts.push(e.consulta);
  if (e.formato_aceito?.membro) parts.push(e.formato_aceito.membro);
  return parts.filter(Boolean).join(' · ');
}

/** O cartão do Configurar (widget ``public_source``). */
export function publicSourceField(field, value, set, ctx) {
  const fonte = value && typeof value === 'object' ? value : {};
  const choose = () => openPublicData({
    select: fonte.id ? { id: fonte.id, nome: fonte.nome, orgao: fonte.orgao } : null,
    choices: fonte.id ? fonte.escolhas : null,
    useLabel: 'Usar nesta caixa',
    onUse: (entry, choices, _target, info) => set(selectionOf(entry, choices, info)),
  });
  const changed = typeof ctx.publicError === 'string' && ctx.publicError.startsWith('O órgão mudou o arquivo');
  const accept = async () => {
    const e = fonte.escolhas || {};
    try {
      const p = await api.publicFilePreview(fonte.id, e.arquivo, e.formato_aceito?.opcoes || {}, e.formato_aceito?.membro || '');
      set({ ...fonte, escolhas: { ...e, formato_aceito: p.formato_aceito } });
      toast('Novo formato aceito', { kind: 'success', detail: 'Execute de novo para ler com as colunas novas.' });
    } catch (err) {
      toastError(err, 'Não foi possível ler o arquivo de novo');
    }
  };
  if (!fonte.id) {
    return h('div', { class: 'pd-box pd-box-empty' },
      icon('landmark', 18),
      h('div', {}, h('strong', {}, 'Nenhuma fonte escolhida'), h('p', { class: 'field-help' }, 'Selic, IPCA, municípios, CNPJ, portais de dados abertos…')),
      button({ icon: 'search', label: 'Escolher no catálogo…', variant: 'primary', onClick: choose }));
  }
  return h('div', { class: 'pd-box' },
    h('div', { class: 'pd-box-head' }, icon('landmark', 18),
      h('div', {}, h('strong', {}, fonte.nome), h('p', { class: 'field-help' }, [fonte.orgao, summary(fonte)].filter(Boolean).join(' · ')))),
    changed ? h('div', { class: 'pd-box-changed' }, icon('alert', 13),
      h('span', {}, 'O órgão mudou o arquivo. Confira na prévia antes de aceitar.'),
      button({ label: 'Ver no catálogo', size: 'sm', onClick: choose }),
      button({ label: 'Aceitar o novo formato', size: 'sm', variant: 'primary', onClick: accept })) : null,
    h('div', { class: 'row' }, button({ icon: 'edit', label: 'Trocar a fonte ou as escolhas…', size: 'sm', onClick: choose })));
}

registerWidget('public_source', publicSourceField);
