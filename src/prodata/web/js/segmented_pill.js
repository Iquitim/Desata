// Pílula deslizante (spec 046, RF-4651): nos controles segmentados, o destaque escorrega do botão antigo ao novo,
// ajustando a largura, em 200 ms, sem quique nem brilho. Vale para todos os `.segmented` do programa, inclusive os que
// redesenham os botões a cada clique: a pílula é um elemento próprio, que volta para o lugar e só muda de posição.
// Com "reduzir movimento" no sistema, a troca é instantânea (CSS).

import { h } from './dom.js';

const pills = new WeakMap();
const sizes = typeof ResizeObserver === 'function' ? new ResizeObserver((entries) => entries.forEach((e) => place(e.target))) : null;

const isOn = (b) => b.getAttribute('aria-selected') === 'true' || b.getAttribute('aria-checked') === 'true' || b.classList.contains('active');
const chosen = (seg) => [...seg.children].find((b) => b.classList?.contains('segment') && isOn(b)) || null;

function place(seg) {
  const pill = pills.get(seg);
  if (!pill) return;
  if (pill.parentNode !== seg) seg.prepend(pill); // o controle redesenhou os botões: a pílula volta, do mesmo lugar
  const b = chosen(seg);
  if (!b || !b.offsetWidth) {
    pill.style.opacity = '0';
    return;
  }
  Object.assign(pill.style, {
    opacity: '1', left: `${b.offsetLeft}px`, top: `${b.offsetTop}px`, width: `${b.offsetWidth}px`, height: `${b.offsetHeight}px`,
  });
  if (!seg.classList.contains('seg-ready')) requestAnimationFrame(() => seg.classList.add('seg-ready')); // sem animar na 1ª vez
}

function enhance(seg) {
  if (pills.has(seg)) return;
  pills.set(seg, h('span', { class: 'seg-pill', 'aria-hidden': 'true' }));
  seg.classList.add('has-pill');
  sizes?.observe(seg);
  place(seg);
}

/** Liga a pílula nos controles que já existem e nos que aparecerem depois (diálogos, painéis). */
export function startPills(root = document.body) {
  root.querySelectorAll('.segmented').forEach(enhance);
  const watcher = new MutationObserver((records) => {
    const touched = new Set();
    for (const r of records) {
      for (const added of r.addedNodes) {
        if (added.nodeType !== 1) continue;
        if (added.matches('.segmented')) enhance(added);
        added.querySelectorAll?.('.segmented').forEach(enhance);
      }
      const seg = r.target.nodeType === 1 ? r.target.closest('.segmented') : null;
      if (seg && pills.has(seg)) touched.add(seg);
    }
    touched.forEach(place);
  });
  watcher.observe(root, { subtree: true, childList: true, attributes: true, attributeFilter: ['aria-selected', 'aria-checked', 'class'] });
  return watcher;
}
