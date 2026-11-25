// Filtro na leitura do CNPJ (spec 049, RF-4957), no editor da fonte de pasta: CNPJ (vários, em qualquer formato),
// UF, município, CNAE principal e situação cadastral; e Só as empresas destes estabelecimentos. O programa lê os
// arquivos aos poucos e guarda só as linhas que passam: Estabelecimentos inteiro não cabe na memória.

import { api } from './api.js';
import { button, debounce, h } from './dom.js';
import { icon } from './icons.js';
import { store } from './store.js';
import { toastError } from './ui.js';

const UFS = ['AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MT', 'MS', 'MG', 'PA', 'PB', 'PR', 'PE', 'PI', 'RJ', 'RN',
  'RS', 'RO', 'RR', 'SC', 'SP', 'SE', 'TO'];
const SITUATIONS = [['02', 'Ativa'], ['08', 'Baixada'], ['04', 'Inapta'], ['03', 'Suspensa'], ['01', 'Nula']];
const names = new Map(); // código → nome (municípios e CNAEs já vistos na busca)

const groupOf = (layout) => (layout || '').replace('receita.cnpj/', '');
const fmtCnpj = (v) => (v.length === 14 ? `${v.slice(0, 2)}.${v.slice(2, 5)}.${v.slice(5, 8)}/${v.slice(8, 12)}-${v.slice(12)}`
  : `${v.slice(0, 2)}.${v.slice(2, 5)}.${v.slice(5, 8)}`);

/** CNPJ: cola a lista, o programa converte e mostra como entendeu cada linha (o inválido não entra em silêncio). */
function cnpjField(value, changed) {
  const current = () => value.layout_filter.cnpj || [];
  const box = h('textarea', { class: 'input mono', rows: 3, placeholder: '00.000.000/0001-91\n12.345.678\n191 (zeros perdidos no Excel)', 'aria-label': 'CNPJs' });
  const result = h('div', { class: 'cf-result' });
  const chips = h('div', { class: 'cf-chips' });
  const drawChips = () => chips.replaceChildren(...current().map((v) => h('span', { class: 'cf-chip' },
    `${fmtCnpj(v)}${v.length === 8 ? ' · empresa inteira' : ''}`,
    h('button', { type: 'button', 'aria-label': `Tirar ${fmtCnpj(v)}`, onclick: () => { set(current().filter((x) => x !== v)); } }, '×'))));
  const set = (list) => {
    value.layout_filter = { ...value.layout_filter, cnpj: list };
    if (!list.length) delete value.layout_filter.cnpj;
    drawChips();
    changed();
  };
  const read = async () => {
    if (!box.value.trim()) return;
    try {
      const answer = await api.publicCnpjList(box.value);
      set([...new Set([...current(), ...answer.validos.map((v) => v.valor)])]);
      result.replaceChildren(
        ...answer.validos.map((v) => h('p', { class: 'cf-ok' }, icon('check-circle', 12), ` ${v.entrada} → ${v.mostrado} (${v.tipo === 'empresa' ? 'empresa inteira: matriz e filiais' : 'um estabelecimento'})`)),
        ...(answer.repetidos || []).map((v) => h('p', { class: 'cf-ok' }, icon('copy', 12), ` ${v.entrada} → ${v.mostrado} (repetido: já estava na lista)`)),
        ...answer.invalidos.map((v) => h('p', { class: 'cf-bad' }, icon('alert', 12), ` ${v.entrada}: não é um CNPJ válido, ficou de fora`)));
      box.value = answer.invalidos.map((v) => v.entrada).join('\n');
    } catch (err) {
      toastError(err, 'Não foi possível conferir os CNPJs');
    }
  };
  drawChips();
  return h('div', { class: 'field' }, h('span', { class: 'field-label' }, 'CNPJ'),
    box, h('div', { class: 'row' }, button({ icon: 'check', label: 'Conferir e incluir', size: 'sm', onClick: read }),
      h('span', { class: 'field-help' }, 'Um por linha ou separados por vírgula, com ou sem pontuação.')),
    result, chips);
}

function ufField(value, changed) {
  const chosen = new Set(value.layout_filter.uf || []);
  return h('div', { class: 'field' }, h('span', { class: 'field-label' }, 'UF'),
    h('div', { class: 'cf-ufs', role: 'group', 'aria-label': 'UFs' }, UFS.map((uf) => h('button', {
      type: 'button', class: ['cf-uf', chosen.has(uf) && 'on'], 'aria-pressed': String(chosen.has(uf)),
      onclick: (e) => {
        if (chosen.has(uf)) chosen.delete(uf); else chosen.add(uf);
        e.currentTarget.classList.toggle('on', chosen.has(uf));
        e.currentTarget.setAttribute('aria-pressed', String(chosen.has(uf)));
        value.layout_filter = { ...value.layout_filter, uf: [...chosen] };
        if (!chosen.size) delete value.layout_filter.uf;
        changed();
      },
    }, uf))));
}

/** Município e CNAE: busca pelo nome na tabela baixada junto, sem decorar o código da Receita. */
function lookupField(value, changed, { key, table, label, placeholder }) {
  const current = () => value.layout_filter[key] || [];
  const chips = h('div', { class: 'cf-chips' });
  const list = h('div', { class: 'cf-options', role: 'listbox', 'aria-label': label });
  const set = (codes) => {
    value.layout_filter = { ...value.layout_filter, [key]: codes };
    if (!codes.length) delete value.layout_filter[key];
    draw();
    changed();
  };
  const draw = () => chips.replaceChildren(...current().map((c) => h('span', { class: 'cf-chip' }, names.get(`${table}:${c}`) ? `${c} · ${names.get(`${table}:${c}`)}` : c,
    h('button', { type: 'button', 'aria-label': `Tirar ${c}`, onclick: () => set(current().filter((x) => x !== c)) }, '×'))));
  const search = debounce(async (q) => {
    if (!q.trim()) { list.replaceChildren(); return; }
    try {
      const answer = await api.publicCnpjValues(value.id, table, q);
      if (!answer.disponivel) {
        list.replaceChildren(h('p', { class: 'field-help' }, `A tabela ${label} não foi baixada junto: digite o código e tecle Enter.`));
        return;
      }
      const more = answer.total > answer.valores.length
        ? [h('p', { class: 'field-help' }, `Mais ${answer.total - answer.valores.length}: refine a busca.`)] : [];
      list.replaceChildren(...answer.valores.map((v) => {
        names.set(`${table}:${v.codigo}`, v.descricao);
        return h('button', { type: 'button', class: 'cf-option', role: 'option', onclick: () => set([...new Set([...current(), v.codigo])]) },
          h('code', {}, v.codigo), ` ${v.descricao}`);
      }), ...more); // null viraria o texto "null"
    } catch {
      list.replaceChildren();
    }
  }, 250);
  const input = h('input', { class: 'input', placeholder, 'aria-label': `Buscar ${label}`,
    oninput: (e) => search(e.target.value),
    onkeydown: (e) => { if (e.key === 'Enter' && /^\d+$/.test(e.target.value.trim())) { set([...new Set([...current(), e.target.value.trim()])]); e.target.value = ''; list.replaceChildren(); } } });
  draw();
  return h('div', { class: 'field' }, h('span', { class: 'field-label' }, label), input, list, chips);
}

function situationField(value, changed) {
  const chosen = new Set(value.layout_filter.situacao_cadastral || []);
  return h('div', { class: 'field' }, h('span', { class: 'field-label' }, 'Situação cadastral'),
    h('div', { class: 'row cf-situations' }, SITUATIONS.map(([code, label]) => h('label', { class: 'fd-check' },
      h('input', { type: 'checkbox', checked: chosen.has(code), onchange: (e) => {
        if (e.target.checked) chosen.add(code); else chosen.delete(code);
        value.layout_filter = { ...value.layout_filter, situacao_cadastral: [...chosen] };
        if (!chosen.size) delete value.layout_filter.situacao_cadastral;
        changed();
      } }), ` ${label}`))));
}

function companiesField(value, changed) {
  const options = (store.folderSources || []).filter((s) => s.layout === 'receita.cnpj/estabelecimentos');
  const select = h('select', { class: 'input', 'aria-label': 'Fonte de Estabelecimentos', onchange: (e) => { value.layout_companies_of = e.target.value; changed(); } },
    h('option', { value: '' }, 'Todas as empresas (sem este filtro)'),
    options.map((s) => h('option', { value: s.id, selected: value.layout_companies_of === s.id },
      `${s.name}${Object.keys(s.layout_filter || {}).length ? '' : ' (sem filtro: todas)'}`)));
  return h('div', { class: 'field' }, h('span', { class: 'field-label' }, 'Só as empresas destes estabelecimentos'), select,
    h('p', { class: 'field-help' }, options.length
      ? 'Lê só as empresas que aparecem na fonte de Estabelecimentos escolhida, com o filtro dela (por exemplo, as de SP com um CNAE).'
      : 'Baixe Estabelecimentos do mesmo mês para usar este filtro.'));
}

/** A seção no editor da fonte de pasta com leiaute do CNPJ. ``changed``: refaz a prévia. */
export function layoutFilterSection(value, changed) {
  value.layout_filter = { ...(value.layout_filter || {}) };
  const group = groupOf(value.layout);
  const parts = group === 'estabelecimentos' ? [
    cnpjField(value, changed), ufField(value, changed),
    lookupField(value, changed, { key: 'municipio', table: 'municipios', label: 'Município', placeholder: 'Buscar: Campinas, Recife…' }),
    lookupField(value, changed, { key: 'cnae_fiscal_principal', table: 'cnaes', label: 'CNAE principal', placeholder: 'Buscar: padaria, 4721…' }),
    situationField(value, changed),
  ] : ['empresas', 'socios', 'simples'].includes(group) ? [cnpjField(value, changed), companiesField(value, changed)] : [];
  if (!parts.length) return null;
  return h('section', { class: 'cf-section', 'aria-label': 'Filtro na leitura' },
    h('div', { class: 'cf-head' }, icon('filter', 14), h('b', {}, 'Filtro na leitura'),
      h('span', { class: 'field-help' }, 'Lê os arquivos aos poucos e guarda só as linhas que passam. Acima de 1/4 da memória, o programa pergunta antes de continuar.')),
    ...parts);
}
