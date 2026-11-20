// Menu flutuante (botão direito e menus do topo), com submenus (spec 044): um item com `submenu` mostra o valor atual
// à direita e abre a lista ao lado, ao passar o mouse, clicar ou apertar →. Teclado: ↑ ↓ andam, → abre, ← volta.
//
// items: [{ label, icon, color, onSelect, danger, disabled, shortcut, checked, radio, value, submenu: () => items }
//         | 'separator' | { heading } | { note }]

import { h } from './dom.js';
import { icon } from './icons.js';

let openMenu = null;
let openSub = null;
let subTimer = 0;

export function closeMenu() {
  clearTimeout(subTimer);
  openSub?.remove();
  openSub = null;
  openMenu?.remove();
  openMenu = null;
}

function closeSub() {
  clearTimeout(subTimer);
  openSub?.parentButton?.setAttribute('aria-expanded', 'false');
  openSub?.remove();
  openSub = null;
}

/** Ícone com cor própria no menu, como a cor de uma pasta (spec 034). */
function tinted(svg, color) {
  if (color) svg.style.color = color;
  return svg;
}

function lead(item) {
  if (item.checked !== undefined) return item.checked ? icon('check', 15) : h('span', { class: 'icon' });
  return item.icon ? tinted(icon(item.icon, 15), item.color) : h('span', { class: 'icon' });
}

function itemEl(item, level) {
  if (item === 'separator' || item.heading || item.note) {
    return h('div', item.heading ? { class: 'menu-heading' } : item.note ? { class: 'menu-note' } : { class: 'menu-sep', role: 'separator' }, item.heading || item.note || null);
  }
  const role = item.checked === undefined ? 'menuitem' : item.radio ? 'menuitemradio' : 'menuitemcheckbox';
  const btn = h('button', {
    type: 'button', role, class: ['menu-item', item.danger && 'danger', item.submenu && 'has-sub', item.checked && 'checked'], disabled: item.disabled,
    'aria-checked': item.checked === undefined ? null : String(Boolean(item.checked)),
    'aria-haspopup': item.submenu ? 'menu' : null, 'aria-expanded': item.submenu ? 'false' : null,
    title: item.title || null,
    onclick: () => {
      if (item.submenu) { openSubmenu(btn, item); return; }
      closeMenu();
      item.onSelect();
    },
  },
  lead(item),
  h('span', { class: 'menu-label' }, item.label),
  item.submenu
    ? h('span', { class: 'menu-more' }, item.value ? h('span', { class: 'menu-value' }, item.value) : null, icon('chevron-right', 13))
    : item.shortcut ? h('kbd', {}, item.shortcut) : null);
  btn.addEventListener('pointerenter', () => {
    if (level === 0) {
      clearTimeout(subTimer);
      if (item.submenu && !item.disabled) subTimer = setTimeout(() => openSubmenu(btn, item, false), 140);
      else if (openSub) subTimer = setTimeout(closeSub, 220);
    } else clearTimeout(subTimer);
  });
  return btn;
}

function build(items, level) {
  const menu = h('div', { class: ['menu', level && 'submenu'], role: 'menu' }, items.map((item) => itemEl(item, level)));
  menu.addEventListener('keydown', (e) => navigate(e, menu, level));
  return menu;
}

const enabled = (menu) => [...menu.querySelectorAll(':scope > .menu-item:not([disabled])')];

function navigate(e, menu, level) {
  const list = enabled(menu);
  const at = list.indexOf(document.activeElement);
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    e.preventDefault();
    const next = list[(at + (e.key === 'ArrowDown' ? 1 : -1) + list.length) % list.length];
    next?.focus();
  } else if (e.key === 'ArrowRight' && document.activeElement?.classList.contains('has-sub')) {
    e.preventDefault();
    document.activeElement.click();
  } else if ((e.key === 'ArrowLeft' || e.key === 'Escape') && level) {
    e.preventDefault();
    e.stopPropagation();
    const parent = openSub?.parentButton;
    closeSub();
    parent?.focus();
  }
}

function place(menu, x, y) {
  const { innerWidth, innerHeight } = window;
  const rect = menu.getBoundingClientRect();
  menu.style.left = `${Math.max(8, Math.min(x, innerWidth - rect.width - 8))}px`;
  menu.style.top = `${Math.max(8, Math.min(y, innerHeight - rect.height - 8))}px`; // lista longa: rola por dentro
}

function openSubmenu(btn, item, focus = true) {
  if (openSub?.parentButton === btn) { if (focus) enabled(openSub)[0]?.focus(); return; }
  closeSub();
  const sub = build(item.submenu(), 1);
  sub.parentButton = btn;
  (document.querySelector('dialog[open]') || document.body).append(sub);
  const r = btn.getBoundingClientRect();
  const width = sub.getBoundingClientRect().width;
  // Ao lado do item; sem espaço à direita, abre à esquerda do menu.
  const parent = btn.closest('.menu').getBoundingClientRect();
  const x = r.right + width + 6 > window.innerWidth ? parent.left - width + 2 : parent.right - 2;
  place(sub, x, r.top - 5);
  btn.setAttribute('aria-expanded', 'true');
  sub.addEventListener('pointerenter', () => clearTimeout(subTimer));
  openSub = sub;
  if (focus) enabled(sub)[0]?.focus();
}

export function showMenu(x, y, items) {
  closeMenu();
  const menu = build(items, 0);
  (document.querySelector('dialog[open]') || document.body).append(menu); // numa janela, fora dela ficaria por baixo
  place(menu, x, y);
  openMenu = menu;
  menu.querySelector('.menu-item:not([disabled])')?.focus();
}

document.addEventListener('pointerdown', (e) => {
  if (openMenu && !openMenu.contains(e.target) && !openSub?.contains(e.target)) closeMenu();
});
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape') return;
  if (openSub) closeSub();
  else closeMenu();
});
