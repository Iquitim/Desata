// Extrações salvas do leitor de PDF (spec 037, RF-3705): escolher uma ao criar a fonte, copiar como nova, trocar,
// exportar, importar e excluir. Só existem para PDF: as outras fontes já chegam como tabela.

import { api } from './api.js';
import { saveDownload } from './desktop.js';
import { button, h } from './dom.js';
import { icon } from './icons.js';
import { refreshPdfSources } from './pdf_sources.js';
import { confirmDialog, openDialog, toast, toastError } from './ui.js';

/** "2 campos, 1 tabela": o que a extração tira. */
export function recipeSummary(r) {
  const parts = [r.campos.length && `${r.campos.length} campo${r.campos.length > 1 ? 's' : ''}`, r.tabelas.length && `${r.tabelas.length} tabela${r.tabelas.length > 1 ? 's' : ''}`];
  return parts.filter(Boolean).join(', ') || 'sem campos ainda';
}

export async function exportRecipe(recipeId) {
  try {
    const res = await fetch(`/api/pdfs/recipes/${encodeURIComponent(recipeId)}/export`);
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Não foi possível exportar');
    const name = decodeURIComponent((res.headers.get('content-disposition') || '').match(/filename\*=UTF-8''([^;]+)/)?.[1] || 'extracao.extracao.json');
    const saved = await saveDownload(name, await res.blob());
    if (saved) toast('Extração exportada', { kind: 'success', detail: 'O arquivo não leva caminho nem senha: pode mandar para um colega.' });
  } catch (err) {
    toastError(err, 'Não foi possível exportar a extração');
  }
}

/** Escolhe um arquivo .extracao.json e importa; com `sourceId`, a fonte já passa a usar a extração importada. */
export function importRecipe(sourceId = null) {
  return new Promise((resolve) => {
    const input = h('input', { type: 'file', accept: '.json,application/json', hidden: true, onchange: async (e) => {
      const file = e.target.files[0];
      input.remove();
      if (!file) { resolve(null); return; }
      try {
        const fd = new FormData();
        fd.append('file', file);
        if (sourceId) fd.append('source', sourceId);
        const out = await api.importPdfRecipe(fd);
        await refreshPdfSources();
        toast('Extração importada', { kind: 'success', detail: `"${out.recipe.nome}": ${recipeSummary({ campos: out.recipe.campos, tabelas: out.recipe.tabelas })}.` });
        resolve(out.recipe);
      } catch (err) {
        toastError(err, 'Não foi possível importar');
        resolve(null);
      }
    } });
    document.body.append(input);
    input.click();
  });
}

/** Excluir: se alguma fonte usa, a tela diz quais e que elas voltam a rascunho. */
export async function deleteRecipe(r) {
  const users = r.fontes.map((f) => f.name);
  const ok = await confirmDialog({
    title: `Excluir a extração "${r.nome}"?`,
    message: users.length
      ? `Ela é usada por ${users.length} fonte(s): ${users.join(', ')}. Essas fontes voltam a rascunho e os fluxos que as leem param até você marcar os campos de novo.`
      : 'Nenhuma fonte usa esta extração. Ela some da lista de extrações salvas.',
    confirm: 'Excluir', danger: true,
  });
  if (!ok) return false;
  try {
    await api.deletePdfRecipe(r.id, users.length > 0);
    await refreshPdfSources();
    toast('Extração excluída', { kind: 'success', detail: users.length ? `${users.join(', ')} voltaram a rascunho.` : '' });
    return true;
  } catch (err) {
    toastError(err, 'Não foi possível excluir');
    return false;
  }
}

/**
 * A lista de extrações salvas. `source`: a fonte aberta (oferece "Usar nesta fonte"), ou null.
 * `onChanged()`: chamado quando a fonte passou a usar outra extração.
 */
export async function recipesDialog(source = null, onChanged = () => {}) {
  const list = h('div', { class: 'pdf-recipes' }, h('p', { class: 'muted' }, 'Carregando…'));
  const draw = async () => {
    let items;
    try { items = await api.pdfRecipes(); } catch (err) { list.replaceChildren(h('p', { class: 'text-error' }, err.message)); return; }
    if (!items.length) {
      list.replaceChildren(h('p', { class: 'muted' }, 'Nenhuma extração salva ainda. Elas nascem quando você marca o primeiro campo num PDF.'));
      return;
    }
    list.replaceChildren(...items.map((r) => {
      const mine = source && source.recipe === r.id;
      return h('article', { class: ['pdf-recipe', mine && 'current'] },
        h('div', { class: 'pdf-recipe-main' },
          h('b', {}, r.nome, mine ? h('span', { class: 'pe-chip tone-info' }, 'nesta fonte') : null),
          h('small', {}, `${recipeSummary(r)} · revisão ${r.revisao}`),
          h('small', {}, r.fontes.length ? `Usada por: ${r.fontes.map((f) => f.name).join(', ')}` : 'Nenhuma fonte usa agora')),
        h('div', { class: 'row' },
          source && !mine ? button({ icon: 'check', label: 'Usar nesta fonte', size: 'sm', onClick: async () => {
            try {
              await api.usePdfRecipe(source.id, r.id);
              await refreshPdfSources();
              toast('Extração trocada', { kind: 'success', detail: `"${source.name}" agora usa "${r.nome}".` });
              dialog.close();
              onChanged();
            } catch (err) { toastError(err, 'Não foi possível trocar'); }
          } }) : null,
          button({ icon: 'download', title: `Exportar "${r.nome}"`, variant: 'ghost', size: 'sm', onClick: () => exportRecipe(r.id) }),
          button({ icon: 'trash', title: `Excluir "${r.nome}"`, variant: 'ghost', size: 'sm', onClick: async () => { if (await deleteRecipe(r)) { draw(); if (mine) onChanged(); } } })));
    }));
  };
  const dialog = openDialog({
    title: 'Extrações salvas',
    size: 'md',
    body: h('div', { class: 'stack-sm' },
      h('p', { class: 'field-help' }, icon('info', 12), ' Uma extração ensina a ler um layout de PDF. Várias fontes podem usar a mesma: melhorar a regra numa melhora em todas.'),
      list),
    actions: [
      button({ icon: 'upload', label: 'Importar extração…', onClick: async () => { const r = await importRecipe(); if (r) draw(); } }),
      button({ label: 'Fechar', variant: 'primary', onClick: () => dialog.close() }),
    ],
  });
  draw();
  return dialog;
}
