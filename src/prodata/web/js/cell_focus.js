// Célula em destaque (spec 041, RF-4133): clicar destaca a célula, marca a linha e a coluna e mostra o valor inteiro
// num rodapé. Setas movem, Ctrl+C copia, Esc tira. Serve à tabela de resultados e ao visual Tabela do Dashboard,
// inclusive no HTML exportado (por isso só depende de dom.js).

import { h } from './dom.js';

/**
 * Liga o destaque numa tabela. `wrap` é o elemento que rola (recebe o foco do teclado).
 * `valueAt(td, row, col)`: o valor inteiro a mostrar; `nameAt(col)`: o nome da coluna; `firstCol`: a primeira coluna
 * que pode ser destacada (1 quando a 0 é o número da linha); `rowLabel(row)`: o número da linha no rodapé.
 * Devolve o rodapé, para quem chama pôr logo abaixo da tabela.
 */
export function enableCellFocus(wrap, table, { valueAt, nameAt, firstCol = 0, rowLabel = (r) => r + 1 } = {}) {
  const foot = h('div', { class: 'cell-foot', hidden: true, role: 'status', 'aria-live': 'polite' });
  let at = null; // { row, col }
  const rows = () => table.tBodies[0]?.rows || [];
  const cellAt = (r, c) => rows()[r]?.cells[c] || null;

  const clear = () => {
    for (const el of table.querySelectorAll('.cell-focus, .row-focus, .col-focus')) el.classList.remove('cell-focus', 'row-focus', 'col-focus');
    at = null;
    foot.hidden = true;
  };

  const show = (r, c) => {
    const td = cellAt(r, c);
    if (!td || td.colSpan > 1) return;
    clear();
    at = { row: r, col: c };
    td.parentElement.classList.add('row-focus');
    for (const tr of rows()) tr.cells[c]?.classList.add('col-focus');
    table.tHead?.rows[0]?.cells[c]?.classList.add('col-focus');
    td.classList.add('cell-focus');
    td.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    const value = valueAt ? valueAt(td, r, c) : td.textContent;
    const name = nameAt ? nameAt(c) : table.tHead?.rows[0]?.cells[c]?.textContent || '';
    foot.replaceChildren(
      h('span', { class: 'cell-foot-where' }, `${name} · linha ${rowLabel(r)}`),
      h('span', { class: ['cell-foot-value', (value === null || value === undefined) && 'null'] }, value === null || value === undefined ? 'nulo' : String(value)),
      h('span', { class: 'cell-foot-keys' }, 'Ctrl+C copia · Esc tira'));
    foot.hidden = false;
  };

  wrap.tabIndex = wrap.tabIndex >= 0 ? wrap.tabIndex : 0;
  wrap.classList.add('cell-focusable');
  table.addEventListener('click', (e) => {
    const td = e.target.closest('tbody td');
    if (!td || td.cellIndex < firstCol || e.target.closest('button, a, input')) return;
    const r = td.parentElement.sectionRowIndex;
    if (at && at.row === r && at.col === td.cellIndex) clear();
    else show(r, td.cellIndex);
    wrap.focus({ preventScroll: true });
  });
  wrap.addEventListener('keydown', (e) => {
    if (!at) return;
    const moves = { ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1] };
    if (moves[e.key]) {
      e.preventDefault();
      const [dr, dc] = moves[e.key];
      const r = Math.max(0, Math.min(rows().length - 1, at.row + dr));
      const c = Math.max(firstCol, Math.min((rows()[r]?.cells.length || 1) - 1, at.col + dc));
      show(r, c);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation(); // o primeiro Esc tira o destaque; o seguinte sai da tela cheia
      clear();
    } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'c' && !window.getSelection()?.toString()) {
      e.preventDefault();
      const td = cellAt(at.row, at.col);
      const value = valueAt ? valueAt(td, at.row, at.col) : td?.textContent;
      navigator.clipboard?.writeText(value === null || value === undefined ? '' : String(value)).then(() => {
        const keys = foot.querySelector('.cell-foot-keys');
        if (keys) keys.textContent = 'Copiado';
      }).catch(() => {});
    }
  });
  return foot;
}
