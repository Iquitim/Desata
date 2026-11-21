// Erro de uma caixa, com o conserto à mão (spec 046, RF-4621..4623): a frase em português, as colunas parecidas
// (um clique troca), "Escolher outra coluna" (leva ao campo), o aviso da entrada quando a coluna sumiu da fonte e,
// recolhido, o texto técnico original.

import { api } from './api.js';
import { button, h } from './dom.js';
import { icon } from './icons.js';
import { schemaChange } from './schema_notice.js';
import { mutate, select, store } from './store.js';
import { toast, toastError } from './ui.js';

/** Entrada de onde a coluna sumiu (aviso de formato aberto), se houver. */
function sourceThatLost(column) {
  return store.workflow.nodes.find((n) => schemaChange(n.id)?.removed?.includes(column))?.id || null;
}

/** Leva ao campo que cita a coluna: lista, seleção ou fórmula, com um destaque rápido. */
export function focusColumnField(column) {
  const panel = document.querySelector('#leftPanel');
  if (!panel) return;
  const candidates = [...panel.querySelectorAll('select, input, textarea, .tag, .chip, .formula-input, [contenteditable]')];
  const target = candidates.find((el) => el.value === column || el.textContent?.trim() === column)
    || candidates.find((el) => (el.value || el.textContent || '').includes(`[${column}]`));
  if (!target) {
    toast(`Não achei um campo com "${column}"`, { detail: 'Confira as fórmulas e listas do Configurar.' });
    return;
  }
  const box = target.closest('.field, .list-item, .formula-card') || target;
  box.scrollIntoView({ block: 'center', behavior: 'smooth' });
  box.classList.remove('flash-field');
  void box.offsetWidth;
  box.classList.add('flash-field');
  if (typeof target.focus === 'function') target.focus({ preventScroll: true });
}

async function useColumn(n, old, chosen) {
  try {
    const r = await api.schemaRename(store.workflow, n.id, old, chosen, true);
    if (!r.changed.length) {
      toast(`Não achei "${old}" nos campos desta caixa`, { detail: 'Use Escolher outra coluna para trocar à mão.' });
      return;
    }
    const fresh = r.workflow.nodes.find((k) => k.id === n.id);
    mutate((wf) => { wf.nodes.find((k) => k.id === n.id).config = fresh.config; }, { affects: [n.id] });
    toast(`"${old}" trocada por "${chosen}" nesta caixa`, { kind: 'success', detail: 'Execute para conferir. Ctrl+Z desfaz.' });
  } catch (err) {
    toastError(err, 'Não foi possível trocar a coluna');
  }
}

export function errorDetails(n, res) {
  const hint = res.extra?.error_hint;
  const technical = res.extra?.error_detail;
  const parts = [];
  if (res.error_field) parts.push(h('div', {}, `Campo: ${res.error_field}`));
  if (hint?.kind === 'column_missing') {
    for (const column of hint.columns) {
      const near = hint.similar?.[column] || [];
      const from = sourceThatLost(column);
      parts.push(h('div', { class: 'err-fix' },
        h('span', {}, from ? `"${column}" sumiu da fonte.` : near.length ? `Parecidas com "${column}":` : `"${column}" não chega nesta caixa.`),
        ...near.map((s) => button({ label: s, size: 'sm', title: `Usar "${s}" no lugar de "${column}" nesta caixa`, onClick: () => useColumn(n, column, s) })),
        button({ icon: 'target', label: 'Escolher outra coluna', size: 'sm', variant: 'ghost', onClick: () => focusColumnField(column) }),
        from ? button({ icon: 'alert', label: 'Ver o aviso da entrada', size: 'sm', variant: 'ghost', onClick: () => select(from) }) : null));
    }
  }
  if (technical && technical !== res.error) {
    parts.push(h('details', { class: 'err-tech' }, h('summary', {}, icon('info', 12), 'Detalhes técnicos'),
      h('pre', {}, technical)));
  }
  return parts.length ? h('div', { class: 'err-parts' }, parts) : null;
}
