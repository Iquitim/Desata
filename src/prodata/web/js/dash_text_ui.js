// Aba Texto do painel Formato (spec 042, RF-4260), no jeito da faixa do Office: escolha o texto (título, subtítulo,
// rótulos, eixos, número) e formate com fonte, tamanho, A↑/A↓, N/I/S, cor e alinhamento. O que não vale para aquele
// texto fica apagado, com a dica do porquê. Grava os mesmos campos do formato (title_bold, subtitle_size, font…).

import { h } from './dom.js';
import { icon } from './icons.js';

const FONTS = [
  ['theme', 'Fonte do tema', null],
  ['sans', 'Segoe UI', "'Segoe UI', Arial, sans-serif"],
  ['serif', 'Georgia', "Georgia, 'Times New Roman', serif"],
  ['mono', 'Consolas', "Consolas, 'Courier New', monospace"],
];
const familyOf = (id) => FONTS.find((f) => f[0] === id)?.[2] || null;
const SIZES = [9, 10, 11, 12, 13, 14, 16, 18, 20, 22, 24, 28, 32, 36, 40, 48, 56, 64, 72, 96];
const SWATCHES = ['#1f2937', '#6b7280', '#ffffff', '#c8302f', '#e8590c', '#e6a700', '#17744a', '#0072b2', '#2a78d6', '#7c3aed'];

// O que cada texto aceita: campo do formato de cada botão (ausente = apagado, com o motivo).
const TARGETS = [
  { id: 'title', label: 'Título', size: 'title_size', bold: 'title_bold', italic: 'title_italic', color: 'title_color', align: 'title_align' },
  { id: 'subtitle', label: 'Subtítulo', size: 'subtitle_size', bold: 'subtitle_bold', italic: 'subtitle_italic', color: 'subtitle_color' },
  { id: 'labels', label: 'Rótulos', bold: 'labels_bold', color: 'labels_color', why: 'Nos rótulos de dados, dá para mudar o negrito e a cor.' },
  { id: 'axis', label: 'Eixos', color: 'axis_text_color', why: 'Nos textos dos eixos, dá para mudar a cor; o tamanho segue o desenho do gráfico.' },
  { id: 'number', label: 'Número', size: 'value_size', color: 'value_color', align: 'align', why: 'O número do KPI é sempre em negrito.' },
];
let lastTarget = 'title';

/** A aba inteira. `fields`: os campos desta aba; `values`: o formato atual (com os padrões). */
export function textTab(fields, values, onChange) {
  const has = new Set(fields.map((f) => f.name));
  const spec = Object.fromEntries(fields.map((f) => [f.name, f]));
  const state = { ...values };
  const targets = TARGETS.filter((t) => has.has(t.color));
  let target = targets.find((t) => t.id === lastTarget) || targets[0];
  const refreshers = [];
  const refresh = () => refreshers.forEach((fn) => fn());
  const watch = (fn) => { refreshers.push(fn); return fn; };
  const set = (name, value) => { state[name] = value; onChange([name], value); refresh(); };
  const sizeOf = () => (target.size ? state[target.size] ?? spec[target.size]?.default : null);
  const clampSize = (v) => { const f = spec[target.size]; return Math.max(f.min ?? 8, Math.min(f.max ?? 96, v)); };

  // ---------------------------------------------------------------- qual texto
  const picker = h('div', { class: 'rb-target', role: 'tablist', 'aria-label': 'Texto que você está formatando' },
    targets.map((t) => {
      const b = h('button', { type: 'button', role: 'tab', class: 'rb-target-btn', onclick: () => { target = t; lastTarget = t.id; refresh(); } }, t.label);
      watch(() => { b.classList.toggle('on', t === target); b.setAttribute('aria-selected', String(t === target)); });
      return b;
    }));

  // ---------------------------------------------------------------- botões da faixa
  const btn = (content, title, onclick) => h('button', { type: 'button', class: 'rb-btn', title, 'aria-label': title, onclick }, content);
  const enable = (el, ok, why) => { el.disabled = !ok; el.title = ok ? el.getAttribute('aria-label') : why; };
  const whyNot = (what) => target.why || `${target.label}: ${what} não se aplica.`;

  const font = h('select', { class: 'rb-font', 'aria-label': 'Fonte do cartão', title: 'Fonte do cartão: vale para todos os textos do visual',
    onchange: (e) => set('font', e.target.value) },
  FONTS.map(([id, label, family]) => h('option', { value: id, style: family ? { fontFamily: family } : null }, label)));
  watch(() => { font.value = state.font || 'theme'; font.style.fontFamily = familyOf(state.font) || ''; font.disabled = !has.has('font'); });

  const size = h('select', { class: 'rb-size', 'aria-label': 'Tamanho da fonte', onchange: (e) => set(target.size, clampSize(Number(e.target.value))) });
  watch(() => {
    const ok = Boolean(target.size);
    const current = sizeOf();
    const f = ok ? spec[target.size] : null;
    const list = ok ? [...new Set([...SIZES.filter((s) => s >= (f.min ?? 8) && s <= (f.max ?? 96)), current])].sort((a, b) => a - b) : [];
    size.replaceChildren(...(ok ? list.map((s) => h('option', { value: s }, String(s))) : [h('option', { value: '' }, '—')]));
    size.value = ok ? String(current) : '';
    enable(size, ok, whyNot('o tamanho'));
  });
  const grow = btn(h('span', { class: 'rb-aa' }, 'A', h('sup', {}, '+')), 'Aumentar a fonte', () => set(target.size, clampSize(sizeOf() + 1)));
  const shrink = btn(h('span', { class: 'rb-aa small' }, 'A', h('sup', {}, '−')), 'Diminuir a fonte', () => set(target.size, clampSize(sizeOf() - 1)));
  watch(() => { enable(grow, Boolean(target.size), whyNot('o tamanho')); enable(shrink, Boolean(target.size), whyNot('o tamanho')); });

  const flag = (key, content, label) => {
    const b = btn(content, label, () => set(target[key], !state[target[key]]));
    watch(() => {
      const field = target[key];
      const on = field ? (state[field] ?? spec[field]?.default) : false;
      b.classList.toggle('on', Boolean(on));
      b.setAttribute('aria-pressed', String(Boolean(on)));
      enable(b, Boolean(field), key === 'underline' ? 'Sublinhado vale nas caixas de texto do dashboard.' : whyNot(label.toLowerCase()));
    });
    return b;
  };
  const bold = flag('bold', h('b', {}, 'N'), 'Negrito');
  const italic = flag('italic', h('i', { class: 'rb-i' }, 'I'), 'Itálico');
  const underline = flag('underline', h('u', {}, 'S'), 'Sublinhado');

  // Cor: "A" com a barra da cor atual; a seta abre a paleta (tema, cores prontas e Mais cores…).
  const bar = h('span', { class: 'rb-bar' });
  const colorBtn = btn(h('span', { class: 'rb-color-a' }, 'A', bar), 'Cor da fonte', () => { if (state[target.color]) set(target.color, state[target.color]); else toggleMenu(); });
  const more = h('input', { type: 'color', class: 'rb-more-input', 'aria-label': 'Mais cores', oninput: (e) => set(target.color, e.target.value) });
  const menu = h('div', { class: 'rb-menu', hidden: true, role: 'dialog', 'aria-label': 'Cor da fonte' },
    h('button', { type: 'button', class: 'rb-theme', onclick: () => { set(target.color, ''); menu.hidden = true; } }, h('span', { class: 'rb-theme-dot' }), 'Cor do tema'),
    h('div', { class: 'rb-swatches' }, SWATCHES.map((c) => h('button', { type: 'button', class: 'rb-swatch', title: c, 'aria-label': c, style: { background: c },
      onclick: () => { set(target.color, c); menu.hidden = true; } }))),
    h('label', { class: 'rb-more' }, icon('palette', 14), 'Mais cores…', more));
  const toggleMenu = () => { menu.hidden = !menu.hidden; };
  const arrow = btn(icon('chevron-down', 12), 'Escolher a cor', toggleMenu);
  arrow.classList.add('rb-arrow');
  watch(() => { bar.style.background = state[target.color] || 'var(--text)'; if (state[target.color]) more.value = state[target.color]; menu.hidden = true; });

  const alignBtn = (value, iconName, label) => {
    const b = btn(icon(iconName, 15), label, () => set(target.align, value));
    watch(() => {
      b.classList.toggle('on', Boolean(target.align) && (state[target.align] ?? spec[target.align]?.default) === value);
      enable(b, Boolean(target.align), whyNot('o alinhamento'));
    });
    return b;
  };

  const ribbon = h('div', { class: 'rb' },
    h('div', { class: 'rb-line' }, font, size, grow, shrink),
    h('div', { class: 'rb-line' },
      h('span', { class: 'rb-group' }, bold, italic, underline),
      h('span', { class: 'rb-sep' }),
      h('span', { class: 'rb-group rb-color-group' }, colorBtn, arrow, menu),
      h('span', { class: 'rb-sep' }),
      h('span', { class: 'rb-group' }, alignBtn('left', 'align-left', 'Alinhar à esquerda'), alignBtn('center', 'align-center', 'Centralizar'))));

  // ---------------------------------------------------------------- prévia
  const pTitle = h('div', { class: 'tx-p-title', dataset: { t: 'title' } }, 'Título do visual');
  const pSub = h('div', { class: 'tx-p-sub', dataset: { t: 'subtitle' } }, 'Subtítulo com o que o visual mostra');
  const pLabel = h('span', { class: 'tx-p-label', dataset: { t: 'labels' } }, '125,3');
  const pAxis = h('span', { class: 'tx-p-axis', dataset: { t: 'axis' } }, 'RJ · RS · GO');
  const pNumber = h('div', { class: 'tx-p-number', dataset: { t: 'number' } }, 'R$ 21,9 mi');
  const preview = h('div', { class: 'tx-preview', 'aria-hidden': 'true' },
    h('div', { class: 'tx-p-kicker' }, 'Prévia'), pTitle, has.has('subtitle_color') ? pSub : null,
    has.has('labels_color') ? h('div', { class: 'tx-p-chart' }, h('span', { class: 'tx-p-bar' }), pLabel, pAxis) : null,
    has.has('value_color') ? pNumber : null);
  // Clicar num texto da prévia escolhe o que formatar, como selecionar o texto no Office.
  preview.addEventListener('click', (e) => {
    const t = targets.find((x) => x.id === e.target.closest('[data-t]')?.dataset.t);
    if (t) { target = t; lastTarget = t.id; refresh(); }
  });
  preview.removeAttribute('aria-hidden');
  watch(() => {
    preview.style.fontFamily = familyOf(state.font) || '';
    Object.assign(pTitle.style, {
      fontWeight: state.title_bold === false ? '400' : '600', fontStyle: state.title_italic ? 'italic' : '',
      color: state.title_color || '', fontSize: `${state.title_size || 14}px`, textAlign: state.title_align === 'center' ? 'center' : '',
      fontFamily: familyOf(state.font) || 'var(--font-title, var(--font))',
    });
    Object.assign(pSub.style, { fontWeight: state.subtitle_bold ? '600' : '', fontStyle: state.subtitle_italic ? 'italic' : '', color: state.subtitle_color || '', fontSize: `${state.subtitle_size || 12}px` });
    Object.assign(pLabel.style, { fontWeight: state.labels_bold === false ? '400' : '600', color: state.labels_color || '' });
    pAxis.style.color = state.axis_text_color || '';
    Object.assign(pNumber.style, { fontSize: `${Math.min(36, state.value_size || 30)}px`, color: state.value_color || '', textAlign: state.align === 'center' ? 'center' : '' });
    for (const el of preview.querySelectorAll('[data-t]')) el.classList.toggle('picked', el.dataset.t === target.id);
  });

  refresh();
  return h('div', { class: 'tx-tab' }, picker, ribbon, preview,
    h('p', { class: 'field-help' }, 'Escolha o texto acima (ou clique nele na prévia) e formate como no Word ou no Excel. A fonte vale para o visual inteiro.'));
}
