// Campos da seção Dica no painel Formato do Dashboard (spec 041, RF-4140..4143): as colunas extras (gravadas na
// caixa do gráfico, que as agrega) e o texto com campos entre chaves, com prévia ao vivo.

import { button, h } from './dom.js';
import { icon } from './icons.js';

/** Colunas extras: marca e desmarca; a caixa do gráfico recalcula ao executar. `ctx.tipColumns`: {options, value, set}. */
export function tipColumnsField(field, _value, _set, ctx) {
  const tc = ctx.tipColumns;
  if (!tc) return h('p', { class: 'field-help' }, 'Colunas extras valem para gráficos de uma série.');
  if (!tc.options.length) return h('p', { class: 'field-help' }, 'Execute o fluxo para escolher as colunas.');
  const chosen = new Set(tc.value);
  return h('div', { class: 'stack-xs' },
    h('div', { class: 'tip-cols' }, tc.options.map((c) => h('button', {
      type: 'button', class: ['chip', chosen.has(c) && 'on'], 'aria-pressed': String(chosen.has(c)),
      onclick: () => tc.set(chosen.has(c) ? tc.value.filter((x) => x !== c) : [...tc.value, c]),
    }, chosen.has(c) ? icon('check', 11) : icon('plus', 11), c))),
    tc.pending ? h('p', { class: 'field-help warn' }, icon('alert', 12), ' Execute o fluxo para as colunas aparecerem na dica.')
      : h('p', { class: 'field-help' }, 'Agregadas como o valor do gráfico (na contagem, somadas).'));
}

/** Texto da dica com campos: botões para inserir cada campo, prévia ao vivo e aviso de campo que não existe. */
export function tipTextField(field, value, set, ctx, id) {
  const area = h('textarea', { id, class: 'input', rows: 2, maxlength: 300, placeholder: field.placeholder || '', spellcheck: false }, value || '');
  const preview = h('div', { class: 'tip-preview chart-tip', role: 'status' });
  const warn = h('p', { class: 'field-help warn', hidden: true });
  const draw = () => {
    const p = ctx.tipPreview?.(area.value);
    if (!p) { preview.hidden = true; return; }
    preview.hidden = false;
    preview.innerHTML = p.html; // vem de tipHtml: texto escapado, só <span>/<b> nossos
    warn.hidden = !p.unknown.length;
    warn.replaceChildren(icon('alert', 12), ` Campo que não existe: ${p.unknown.map((n) => `{${n}}`).join(', ')}. A dica usa o padrão até corrigir.`);
    area.classList.toggle('invalid', p.unknown.length > 0);
  };
  let timer = 0;
  area.addEventListener('input', () => { draw(); clearTimeout(timer); timer = setTimeout(() => set(area.value), 350); });
  area.addEventListener('blur', () => { clearTimeout(timer); if (area.value !== (value || '')) set(area.value); });
  const insert = (name) => {
    const at = area.selectionStart ?? area.value.length;
    area.setRangeText(`{${name}}`, at, area.selectionEnd ?? at, 'end');
    area.focus();
    area.dispatchEvent(new Event('input'));
  };
  const names = ctx.tipPreview?.('')?.fields || [];
  requestAnimationFrame(draw);
  return h('div', { class: 'stack-xs' },
    area,
    names.length ? h('div', { class: 'tip-cols' }, h('span', { class: 'field-help' }, 'Inserir:'),
      names.map((n) => button({ label: `{${n}}`, size: 'sm', variant: 'ghost', onClick: () => insert(n) }))) : null,
    warn,
    h('span', { class: 'field-help' }, 'Prévia da dica (primeira categoria):'),
    preview);
}
