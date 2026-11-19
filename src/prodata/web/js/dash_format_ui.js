// Painel Formato em abas (spec 042, RF-4232/4233): uma aba por seção, paleta por amostras e botões com ícone.

import { currentPagePalette, fixedColors, PALETTES } from './dash_look.js';
import { h } from './dom.js';
import { renderFields } from './fields.js';
import { icon } from './icons.js';
import { textTab } from './dash_text_ui.js';

const TAB_KEY = 'prodata.dash.formatTab';
// Os campos sem seção (título, subtítulo, número do KPI) ficam na aba Cartão, junto com o estilo do cartão.
const TABS = {
  'Cartão': { label: 'Cartão', icon: 'panel' },
  'Cores': { label: 'Cores', icon: 'palette' },
  'Texto': { label: 'Texto', icon: 'type' },
  'Rótulos e legenda': { label: 'Rótulos', icon: 'tag' },
  'Eixos': { label: 'Eixos', icon: 'axes' },
  'Dica': { label: 'Dica', icon: 'info' },
  'Cores por faixa': { label: 'Faixas', icon: 'quality' },
};

let activeTab = (() => { try { return localStorage.getItem(TAB_KEY) || 'Cartão'; } catch { return 'Cartão'; } })();
function remember(tab) {
  activeTab = tab;
  try { localStorage.setItem(TAB_KEY, tab); } catch { /* sem armazenamento: vale só nesta sessão */ }
}

/** Amostras de uma paleta (5 cores), em valores CSS. */
function swatches(id, color) {
  if (id === 'page') return swatches(currentPagePalette());
  if (id === 'single') return [0, 1, 2, 3, 4].map((i) => ({ background: color || 'var(--series-1)', opacity: String(Math.max(0.35, 1 - i * 0.16)) }));
  const fixed = fixedColors(id);
  return [0, 1, 2, 3, 4].map((i) => ({ background: fixed ? fixed[i % fixed.length] : `var(--${id === 'alt' ? 'alt' : 'series'}-${i + 1})` }));
}

const paletteInfo = (id) => PALETTES.find((p) => p.id === id);

/** Marca o botão escolhido na hora (o painel só é refeito quando a escolha muda outros campos). */
function pick(e, value, set) {
  for (const b of e.currentTarget.parentElement.children) {
    b.classList.toggle('on', b === e.currentTarget);
    b.setAttribute('aria-checked', String(b === e.currentTarget));
  }
  set(value);
}

/** Paleta escolhida por amostras; no visual, diz se segue a paleta do dashboard (RF-4238). */
function paletteField(field, value, set, ctx, id, values) {
  const options = field.options || PALETTES.map((p) => ({ value: p.id, label: p.label }));
  const own = field.name === 'palette' && value && value !== 'page';
  const pageName = paletteInfo(currentPagePalette())?.label || 'Marca';
  const status = field.name !== 'palette' || ctx.pagePanel ? null : h('div', { class: 'palette-status' },
    h('span', {}, own ? 'Paleta própria' : `Usa a paleta do dashboard (${pageName})`),
    own ? h('button', { type: 'button', class: 'link-btn', onclick: () => set('page') }, 'Voltar à do dashboard') : null);
  return h('div', { id, class: 'palette-pick', role: 'radiogroup', 'aria-label': field.title },
    status,
    h('div', { class: 'palette-grid' }, options.map((o) => {
      const info = paletteInfo(o.value);
      const custom = o.value === 'custom';
      return h('button', {
        type: 'button', role: 'radio', class: ['palette-opt', o.value === value && 'on'], 'aria-checked': String(o.value === value),
        title: info?.note ? `${o.label} · ${info.note}` : o.label, onclick: (e) => pick(e, o.value, set),
      },
      custom ? h('span', { class: 'palette-dots' }, icon('paintbrush', 14))
        : h('span', { class: 'palette-dots' }, swatches(o.value, values?.color).map((style) => h('i', { style }))),
      h('span', { class: 'palette-name' }, o.value === 'page' ? 'Do dashboard' : (info?.label || o.label)),
      info?.note ? h('span', { class: 'palette-note' }, icon('eye', 11), info.note) : null);
    })));
}

const SEGMENT_ICONS = {
  title_align: { left: 'align-left', center: 'align-center' },
  align: { left: 'align-left', center: 'align-center', right: 'align-right' },
  legend_position: { top: 'legend-top', bottom: 'legend-bottom' },
  vertical: { top: 'arrow-up', middle: 'minimize', bottom: 'arrow-down' },
};

/** Escolha entre poucas opções: botões lado a lado, com ícone quando há um. */
function segmentedField(field, value, set, _ctx, id) {
  const icons = SEGMENT_ICONS[field.name] || {};
  return h('div', { id, class: 'segmented-field', role: 'radiogroup', 'aria-label': field.title },
    field.options.map((o) => h('button', {
      type: 'button', role: 'radio', class: ['seg-btn', o.value === value && 'on'], 'aria-checked': String(o.value === value),
      title: o.label, onclick: (e) => pick(e, o.value, set),
    }, icons[o.value] ? icon(icons[o.value], 15) : null, h('span', {}, o.label))));
}

const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const toHex = (c) => (/^#[0-9a-f]{6}$/i.test(c) ? c.toLowerCase() : '#888888');

/** Até 8 cores da paleta personalizada (spec 042, RF-4255): clicar numa amostra troca a cor; + acrescenta; × tira. */
function personalField(field, value, set, _ctx, id) {
  // Vazia: começa pelas cores da marca, para a pessoa só trocar o que quiser.
  const colors = value?.length ? [...value] : [1, 2, 3, 4, 5].map((i) => toHex(cssVar(`--series-${i}`)));
  const save = (next) => set(next.slice(0, 8));
  return h('div', { id, class: 'personal-colors' },
    colors.map((c, i) => h('span', { class: 'personal-swatch' },
      h('input', { type: 'color', value: c, 'aria-label': `Cor ${i + 1}`, onchange: (e) => { colors[i] = e.target.value; save(colors); } }),
      colors.length > 2 ? h('button', { type: 'button', class: 'personal-remove', title: 'Tirar esta cor', onclick: () => save(colors.filter((_, k) => k !== i)) }, '×') : null)),
    colors.length < 8 ? h('button', { type: 'button', class: 'personal-add', title: 'Acrescentar uma cor', onclick: () => save([...colors, colors.at(-1)]) }, '+') : null);
}

/** Número de uma faixa curta (opacidade, cantos): controle deslizante com o valor ao lado. */
function sliderField(field, value, set, _ctx, id) {
  const shown = h('output', { class: 'slider-value' }, String(value ?? field.default));
  return h('div', { class: 'slider-field' },
    h('input', { id, type: 'range', min: field.min ?? 0, max: field.max ?? 100, step: field.step || 1, value: value ?? field.default,
      oninput: (e) => { shown.textContent = e.target.value; }, onchange: (e) => set(Number(e.target.value)) }),
    shown);
}

export const FORMAT_WIDGETS = { palette: paletteField, segmented: segmentedField, personal_colors: personalField, slider: sliderField };

/**
 * Campos do formato em abas. Sem seções (texto, imagem, forma), um formulário só.
 * Os valores ganham os padrões de todos os campos: um campo pode depender (show_if) de outro que está noutra aba.
 */
export function formatTabs(fields, values, onChange, ctx = {}) {
  const local = { ...ctx, widgets: FORMAT_WIDGETS };
  const tabOf = (f) => (!f.group || f.group === 'Cartão' ? 'Cartão' : f.group);
  const tabs = [...new Set(fields.filter((f) => f.widget !== 'hidden').map(tabOf))];
  if (tabs.length < 2) return renderFields(fields, values, onChange, local);
  const full = { ...Object.fromEntries(fields.map((f) => [f.name, f.default])), ...values };
  const current = tabs.includes(activeTab) ? activeTab : tabs[0];
  const body = h('div', { class: 'format-tab-body', role: 'tabpanel' });
  const bar = h('div', { class: 'format-tabs', role: 'tablist' });
  const show = (tab) => {
    remember(tab);
    for (const b of bar.children) {
      b.classList.toggle('on', b.dataset.tab === tab);
      b.setAttribute('aria-selected', String(b.dataset.tab === tab));
    }
    const subset = fields.filter((f) => tabOf(f) === tab).map((f, i) => ({ ...f, group: undefined, _i: i }))
      .sort((a, b) => (a.order ?? 100 + a._i) - (b.order ?? 100 + b._i));
    if (tab === 'Texto') { body.replaceChildren(textTab(subset, full, onChange)); return; }
    // Blocos com título ("sub"), na ordem dos campos: Eixo Y, Eixo X, Grade, Linha de referência.
    const blocks = [];
    for (const f of subset) {
      const last = blocks.at(-1);
      if (last && last.sub === (f.sub || '')) last.fields.push(f);
      else blocks.push({ sub: f.sub || '', fields: [f] });
    }
    body.replaceChildren(...blocks.map((blk) => h('div', { class: ['format-block', blk.sub && 'titled'] },
      blk.sub ? h('div', { class: 'format-block-head' }, blk.sub) : null, renderFields(blk.fields, full, onChange, local))));
  };
  bar.append(...tabs.map((tab) => {
    const info = TABS[tab] || { label: tab, icon: 'settings' };
    return h('button', { type: 'button', role: 'tab', class: 'format-tab', dataset: { tab }, title: info.label, onclick: () => show(tab) },
      icon(info.icon, 16), h('span', {}, info.label));
  }));
  show(current);
  return h('div', { class: 'format-tabbed' }, bar, body);
}
