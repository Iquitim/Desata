// Componentes de interface reutilizáveis: toast, diálogo, confirmação e menu flutuante.

import { $, button, h } from './dom.js';
import { icon } from './icons.js';

// ------------------------------------------------------------------ toast

const TOAST_ICONS = { success: 'check-circle', error: 'alert', info: 'info' };

export function toast(message, { kind = 'info', detail = '', timeout = kind === 'error' ? 7000 : 3500 } = {}) {
  const region = $('#toasts');
  const el = h(
    'div',
    { class: `toast toast-${kind}`, role: kind === 'error' ? 'alert' : 'status' },
    icon(TOAST_ICONS[kind], 16),
    h('div', { class: 'toast-body' }, h('div', { class: 'toast-title' }, message),
      detail ? h('div', { class: 'toast-detail' }, detail) : null),
    button({ icon: 'x', title: 'Fechar', variant: 'ghost', size: 'sm', onClick: () => dismiss() }),
  );
  const dismiss = () => {
    el.classList.add('leaving');
    setTimeout(() => el.remove(), 150);
  };
  region.append(el);
  if (timeout) setTimeout(dismiss, timeout);
  return dismiss;
}

export function toastError(err, fallback = 'Algo deu errado') {
  console.error(err);
  toast(fallback, { kind: 'error', detail: err?.message || String(err) });
}

// ------------------------------------------------------------------ diálogo

/**
 * Abre um <dialog> modal. `body` é um nó; `actions` é uma lista de nós (botões).
 * Retorna { el, close }. `onClose` roda quando fechado por qualquer meio.
 */
export function openDialog({ title, body, actions = [], size = 'md', onClose } = {}) {
  const close = () => dialog.close();
  const dialog = h(
    'dialog',
    { class: `dialog dialog-${size}`, 'aria-label': title },
    h('header', { class: 'dialog-header' },
      h('h2', {}, title),
      button({ icon: 'x', title: 'Fechar (Esc)', variant: 'ghost', size: 'sm', onClick: close })),
    h('div', { class: 'dialog-body' }, body),
    actions.length ? h('footer', { class: 'dialog-footer' }, actions) : null,
  );
  dialog.addEventListener('close', () => {
    onClose?.();
    dialog.remove();
  });
  dialog.addEventListener('mousedown', (e) => {
    if (e.target === dialog) close(); // clique no backdrop
  });
  document.body.append(dialog);
  dialog.showModal();
  return { el: dialog, close };
}

export function confirmDialog({ title, message, confirm = 'Confirmar', danger = false }) {
  return new Promise((resolve) => {
    let answer = false;
    const { close } = openDialog({
      title,
      size: 'sm',
      body: h('p', { class: 'dialog-text' }, message),
      actions: [
        button({ label: 'Cancelar', onClick: () => close() }),
        button({
          label: confirm,
          variant: danger ? 'danger' : 'primary',
          onClick: () => { answer = true; resolve(true); close(); },
        }),
      ],
      onClose: () => resolve(answer),
    });
  });
}

// ------------------------------------------------------------------ menu flutuante

// Menu flutuante com submenus: menu.js (spec 044).
export { closeMenu, showMenu } from './menu.js';
