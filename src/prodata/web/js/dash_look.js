// Aparência da página do dashboard (spec 042): paletas prontas, paleta geral e imagem de fundo.
// Vai também no HTML exportado (dashboard/viewer.py): nada aqui depende do programa.

import { h } from './dom.js';

/** Paletas com cores fixas (iguais nos dois temas). Marca e alternativa vêm das variáveis do tema. */
export const PALETTE_COLORS = {
  // Okabe & Ito (2008): distinguíveis com os tipos comuns de daltonismo. O preto virou cinza para o tema escuro.
  okabe_ito: ['#0072b2', '#e69f00', '#009e73', '#d55e00', '#56b4e9', '#cc79a7', '#f0e442', '#999999'],
  tableau10: ['#4e79a7', '#f28e2b', '#e15759', '#76b7b2', '#59a14f', '#edc948', '#b07aa1', '#ff9da7'],
  set2: ['#66c2a5', '#fc8d62', '#8da0cb', '#e78ac3', '#a6d854', '#ffd92f', '#e5c494', '#b3b3b3'],
  viridis: ['#440154', '#46327e', '#365c8d', '#277f8e', '#1fa187', '#4ac16d', '#a0da39', '#fde725'],
  blues: ['#08519c', '#2171b5', '#4292c6', '#6baed6', '#3182bd', '#9ecae1', '#1c5a99', '#c6dbef'],
  grays: ['#3d3d3d', '#5c5c5c', '#7a7a7a', '#969696', '#4d4d4d', '#b0b0b0', '#6b6b6b', '#c8c8c8'],
};

/** Paletas na ordem do painel, com nome e a marca de daltonismo. */
export const PALETTES = [
  { id: 'brand', label: 'Marca' },
  { id: 'alt', label: 'Alternativa' },
  { id: 'okabe_ito', label: 'Okabe-Ito', note: 'Para daltonismo' },
  { id: 'tableau10', label: 'Tableau 10' },
  { id: 'set2', label: 'Set2 (ColorBrewer)' },
  { id: 'viridis', label: 'Viridis', note: 'Lê em preto e branco' },
  { id: 'blues', label: 'Tons de azul' },
  { id: 'grays', label: 'Tons de cinza' },
  { id: 'personal', label: 'Personalizada' },
];

const KNOWN = new Set(PALETTES.map((p) => p.id));

let personal = []; // cores da paleta personalizada do dashboard aberto

/** Cores fixas de uma paleta (a personalizada vem do dashboard); null = cores do tema. */
export const fixedColors = (id) => (id === 'personal' ? (personal.length ? personal : null) : PALETTE_COLORS[id] || null);

/** Cor i (0..7) de uma paleta, como valor CSS: variável do tema ou cor fixa. */
export function paletteColor(id, i) {
  const fixed = fixedColors(id);
  if (fixed) return fixed[i % fixed.length];
  return `var(--${id === 'alt' ? 'alt' : 'series'}-${(i % 8) + 1})`;
}

let pagePalette = 'brand';
/** Usa a paleta geral de um dashboard sem desenhar a página (prévia no Designer). */
export function setPagePalette(id, colors = []) {
  pagePalette = KNOWN.has(id) ? id : 'brand';
  personal = (colors || []).filter((c) => /^#[0-9a-f]{6}$/i.test(c)).slice(0, 8);
}
export const personalColors = () => personal;
/** Paleta geral da página aberta (os visuais sem paleta própria usam esta). */
export const currentPagePalette = () => pagePalette;

const FITS = {
  cover: { backgroundSize: 'cover', backgroundRepeat: 'no-repeat' },
  contain: { backgroundSize: 'contain', backgroundRepeat: 'no-repeat' },
  repeat: { backgroundSize: 'auto', backgroundRepeat: 'repeat' },
  center: { backgroundSize: 'auto', backgroundRepeat: 'no-repeat' },
};

/** Luminância relativa (WCAG) de uma cor #rgb, #rrggbb ou rgb(...); null quando não dá para saber (variável, nome). */
export function luminance(color) {
  const text = String(color || '').trim();
  let rgb = null;
  const hex = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(text);
  if (hex) {
    const d = hex[1].length === 3 ? [...hex[1]].map((c) => c + c).join('') : hex[1];
    rgb = [0, 2, 4].map((i) => parseInt(d.slice(i, i + 2), 16));
  } else {
    const m = /^rgba?\(\s*(\d+)[\s,]+(\d+)[\s,]+(\d+)/i.exec(text);
    if (m) rgb = m.slice(1, 4).map(Number);
  }
  if (!rgb) return null;
  const [r, g, b] = rgb.map((v) => { const c = v / 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/**
 * Qual versão do logo da marca aparece: com cor de página própria, a que contrasta com ela; sem cor, a do tema.
 * O limite 0,18 é onde o branco e o preto têm o mesmo contraste com o fundo.
 */
export function logoTone(background) {
  const lum = luminance(background);
  if (lum === null) return {};
  const dark = lum < 0.18;
  return { '--logo-on-light': dark ? 'none' : 'block', '--logo-on-dark': dark ? 'block' : 'none' };
}

/**
 * Estilo e camada de fundo da página. Chame antes de montar os cartões: guarda a paleta geral.
 * A imagem é uma camada própria (não o fundo do elemento) para ter transparência sem apagar os visuais.
 */
export function pageLook(page, size) {
  setPagePalette(page?.palette, page?.personal_colors);
  const style = { width: `${size.width}px`, height: `${size.height}px`, backgroundColor: page?.background || null, ...logoTone(page?.background) };
  const image = String(page?.image || '');
  const backdrop = image.startsWith('data:image/')
    ? h('div', { class: 'dash-backdrop', 'aria-hidden': 'true', style: {
      backgroundImage: `url("${image}")`, backgroundPosition: 'center', opacity: String((page.image_opacity ?? 100) / 100),
      ...(FITS[page.image_fit] || FITS.cover) } })
    : null;
  return { style, backdrop };
}
