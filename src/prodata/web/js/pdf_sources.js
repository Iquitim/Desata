// Leitor de PDF como fonte da vista Dados (spec 037, RF-3701..3704): cadastro, saídas e a caixa no fluxo.
// O PDF é lido onde está (ou numa cópia enviada); os fluxos guardam só `pdf:<id>/<saída>`.

import { addNode } from './actions.js';
import { api } from './api.js';
import { viewportCenter } from './canvas.js';
import { chooseFolder, choosePdfFile, isDesktop } from './desktop.js';
import { button, debounce, fmt, h } from './dom.js';
import { icon } from './icons.js';
import { emit, PDF_PREFIX, store } from './store.js';
import { confirmDialog, toast, toastError } from './ui.js';

import { outputText } from './pdf_labels.js';

export { OUTPUT_TEXT, outputText } from './pdf_labels.js';
/** Dá para ler no fluxo: tem extração e o arquivo ou a pasta existe. Documento com falha não impede (a política decide). */
export const pdfUsable = (source) => !source.status?.draft && !source.status?.missing && !source.status?.error && Boolean(source.status?.files);

const baseName = (path) => String(path || '').split(/[\\/]/).filter(Boolean).pop() || '';
const stem = (path) => baseName(path).replace(/\.pdf$/i, '');

export async function refreshPdfSources() {
  try {
    store.pdfSources = await api.pdfSources();
  } catch {
    store.pdfSources = [];
  }
  emit('pdfs');
}

/** Input Data com uma saída da fonte; a principal é `campos`. */
export function addPdfNode(source, output = 'campos') {
  const c = viewportCenter();
  const label = output === 'campos' ? source.name : `${source.name} · ${outputText(output)[0]}`;
  addNode('io.input_data', c.x - 94, c.y - 28, { dataset: `${PDF_PREFIX}${source.id}/${output}`, __label: label });
}

/** Pergunta antes de excluir, dizendo o que acontece com o arquivo ou a pasta. */
export function confirmRemovePdf(source) {
  const what = source.stored ? 'A cópia enviada do PDF também é apagada.' : source.mode === 'pasta'
    ? `A pasta ${source.path} e os PDFs dela continuam onde estão.` : `O arquivo ${source.path} continua onde está.`;
  return confirmDialog({
    title: `Excluir ${source.name}?`,
    message: `${what} A extração e as correções feitas só nesta fonte também saem.`,
    confirm: 'Excluir', danger: true,
  });
}

export async function deletePdfSource(source) {
  await api.deletePdf(source.id);
  await refreshPdfSources();
}

export async function duplicatePdfSource(source) {
  try {
    const copy = await api.duplicatePdf(source.id);
    await refreshPdfSources();
    toast('Fonte duplicada', { kind: 'success', detail: `"${copy.name}" usa a mesma extração. Aponte para outro arquivo ou pasta em Cadastro.` });
    return copy;
  } catch (err) {
    toastError(err, 'Não foi possível duplicar');
    return null;
  }
}

/** Situação curta do cartão: rascunho, quantos documentos, o que está errado. */
export function pdfState(source) {
  const st = source.status || {};
  if (st.missing) return { label: source.mode === 'pasta' ? 'pasta não encontrada' : 'PDF não encontrado', tone: 'err' };
  if (st.error) return { label: 'padrão inválido', tone: 'err' };
  if (!st.files) return { label: 'nenhum PDF', tone: 'warn' };
  if (st.draft) return { label: 'rascunho', tone: 'warn' };
  const s = st.summary;
  if (s && s.falhou) return { label: `${s.falhou} com falha`, tone: 'warn' }; // a política de falha decide; a fonte continua usável
  if (s && s.revisar) return { label: `${s.revisar} a revisar`, tone: 'warn' };
  return { label: `${st.files} PDF${st.files > 1 ? 's' : ''}`, tone: 'ok' };
}

export function pdfMeta(source) {
  const st = source.status || {};
  const where = source.mode === 'pasta' ? `${source.pattern} · ${baseName(source.path)}` : source.stored ? 'cópia enviada' : `vinculado · ${baseName(source.path)}`;
  return st.draft ? `${where} · sem extração ainda` : `${where} · ${st.fields} campo(s)${st.tables ? `, ${st.tables} tabela(s)` : ''} · revisão ${st.revision}`;
}

// ------------------------------------------------------------------ cadastro

function field(label, control, help) {
  return h('div', { class: 'field' }, h('label', { class: 'field-label' }, label), control, help ? h('p', { class: 'field-help' }, help) : null);
}

const WAYS = {
  upload: { icon: 'upload', title: 'Enviar um PDF', text: 'O Desata guarda uma cópia. Bom para um documento que não muda.' },
  link: { icon: 'link', title: 'Vincular um PDF', text: 'Lido onde está, sempre na versão mais nova. Nada é copiado nem alterado.' },
  folder: { icon: 'directory', title: 'Pasta de PDFs', text: 'Todos os PDFs com o mesmo layout, como um por mês. Os novos entram sozinhos.' },
};

/** O desenho do que a fonte vira: PDFs → extração → saídas. */
function flowArt(count, mode) {
  const docs = Math.max(1, Math.min(count || 1, 3));
  return h('div', { class: 'pdf-art', role: 'img', 'aria-label': 'PDFs, depois a extração que você ensina, depois tabelas' },
    h('span', { class: 'pdf-art-docs' }, Array.from({ length: docs }, (_, i) => h('span', { class: 'pdf-art-doc', style: { '--i': String(i) } }, h('i'), h('i'), h('i')))),
    h('span', { class: 'pdf-art-step' }, icon('chevron-right', 14), h('small', {}, 'você marca')),
    h('span', { class: 'pdf-art-out' }, h('b', {}, 'campos'), h('b', {}, 'itens'), h('small', {}, mode === 'pasta' ? 'cada PDF da pasta' : '1 PDF')));
}

/** Criar (com as três formas de trazer o PDF) ou editar o cadastro. `existing`: a fonte, ou null. */
export function pdfSourceForm(existing = null, { onSaved } = {}, host = {}) {
  const value = { name: '', mode: 'arquivo', path: '', pattern: '*.pdf', recipe: '', ...(existing || {}) };
  const state = { way: existing ? (existing.mode === 'pasta' ? 'folder' : existing.stored ? 'upload' : 'link') : 'upload', file: null, count: 0 };
  const name = h('input', { class: 'input', maxlength: 80, value: value.name, placeholder: 'Ex.: Relatório mensal de vendas',
    oninput: (e) => { value.name = e.target.value; name.classList.remove('invalid'); } });
  const path = h('input', { class: 'input mono', value: value.path, oninput: (e) => { value.path = e.target.value; schedule(); },
    // caminho digitado (no navegador não há seletor do Windows): o nome também vem do arquivo ou da pasta
    onchange: (e) => suggestName(state.way === 'folder' ? baseName(e.target.value) : stem(e.target.value)) });
  const pattern = h('input', { class: 'input mono', value: value.pattern, placeholder: 'relatorio_*.pdf', oninput: (e) => { value.pattern = e.target.value; schedule(); } });
  const fileInput = h('input', { type: 'file', accept: 'application/pdf,.pdf', hidden: true, onchange: (e) => pickUpload(e.target.files[0]) });
  const drop = h('button', { type: 'button', class: 'pdf-drop', onclick: () => fileInput.click() });
  const live = h('div', { class: 'pdf-live' });
  // RF-3705: começar do zero ou de uma extração salva (só na criação; depois, pelo editor)
  const recipeSelect = h('select', { class: 'input', 'aria-label': 'Extração', onchange: (e) => { value.recipe = e.target.value; } },
    h('option', { value: '' }, 'Começar do zero, marcando no documento'));
  if (!existing) {
    api.pdfRecipes().then((items) => {
      if (!items.length) return;
      recipeSelect.append(h('optgroup', { label: 'Extrações salvas' }, items.map((r) => h('option', { value: r.id },
        `${r.nome} · ${[r.campos.length && `${r.campos.length} campo(s)`, r.tabelas.length && `${r.tabelas.length} tabela(s)`].filter(Boolean).join(', ') || 'sem campos'}`))));
      recipeField.hidden = false;
    }).catch(() => {});
  }
  const recipeField = h('div', { class: 'field', hidden: true }, h('label', { class: 'field-label' }, 'Extração'), recipeSelect,
    h('p', { class: 'field-help' }, 'Para PDFs com o mesmo layout de outra fonte: os campos já vêm prontos e você só confere.'));
  const form = h('div', { class: 'stack-sm' });
  const ways = h('div', { class: 'fd-modes pdf-ways', role: 'radiogroup', 'aria-label': 'Como trazer o PDF' });

  const suggestName = (text) => { if (!value.name.trim()) { value.name = text; name.value = text; } };
  const pickUpload = (file) => {
    if (!file) return;
    state.file = file;
    suggestName(stem(file.name));
    drawForm();
  };
  const pickLink = async () => {
    const chosen = await choosePdfFile(value.path);
    if (!chosen) return;
    value.path = chosen;
    path.value = chosen;
    suggestName(stem(chosen));
    schedule();
  };
  const pickFolder = async () => {
    const chosen = await chooseFolder(value.path);
    if (!chosen) return;
    value.path = chosen;
    path.value = chosen;
    suggestName(baseName(chosen));
    schedule();
  };
  const choose = (way) => { state.way = way; drawForm(); refresh(); };

  const drawForm = () => {
    ways.replaceChildren(...Object.entries(WAYS).map(([key, w]) => h('button', {
      type: 'button', role: 'radio', class: 'fd-mode', 'aria-checked': String(key === state.way), dataset: { way: key }, onclick: () => choose(key),
    }, h('span', { class: 'pdf-way-icon' }, icon(w.icon, 18)), h('span', { class: 'fd-mode-text' }, h('strong', {}, w.title), h('small', {}, w.text)))));
    const rows = [field('Nome', name, 'Como a fonte aparece na lista e nos fluxos.')];
    if (state.way === 'upload' && !existing) {
      drop.replaceChildren(icon(state.file ? 'file' : 'upload', 20),
        h('span', {}, state.file ? h('b', {}, state.file.name) : h('b', {}, 'Escolher o PDF'),
          h('small', {}, state.file ? `${fmt.bytes(state.file.size)} · clique para trocar` : 'ou arraste o arquivo para cá')));
      rows.push(field('Arquivo', drop));
    } else if (state.way === 'folder') {
      rows.push(field('Pasta', h('div', { class: 'row' }, path, button({ icon: 'directory', label: 'Escolher…', onClick: pickFolder })), 'Caminho completo. Só esta pasta, sem subpastas.'));
      rows.push(field('Quais PDFs', pattern, '* vale qualquer trecho. Ex.: relatorio_*.pdf'));
    } else {
      rows.push(field('Arquivo', h('div', { class: 'row' }, path, button({ icon: 'file', label: 'Escolher…', onClick: pickLink })),
        isDesktop() ? 'O PDF é lido onde está, sempre na versão mais nova.' : 'Caminho completo do PDF, como D:\\Relatorios\\outubro.pdf.'));
    }
    if (!existing) rows.push(recipeField);
    form.replaceChildren(...rows);
    primary.querySelector('span').textContent = existing ? 'Salvar' : 'Preparar extração';
    refresh();
  };

  const refresh = () => {
    const mode = state.way === 'folder' ? 'pasta' : 'arquivo';
    const parts = [h('span', { class: 'org-preview-label' }, 'O que vai acontecer'), flowArt(state.count, mode)];
    if (state.way === 'upload' && !existing) {
      parts.push(h('p', { class: 'field-help' }, state.file ? 'Depois de enviar, o documento abre para você marcar os dados.' : 'Escolha o PDF para começar.'));
    } else if (!value.path.trim()) {
      parts.push(h('p', { class: 'field-help' }, mode === 'pasta' ? 'Escolha a pasta para ver quantos PDFs entram.' : 'Escolha o PDF para começar.'));
    } else if (mode === 'pasta') {
      parts.push(h('p', { class: 'field-help' }, 'O número de PDFs aparece depois de salvar, na visão geral.'));
    }
    parts.push(h('ol', { class: 'pdf-steps' },
      h('li', {}, 'Você marca no documento o que quer, como o total ou uma tabela.'),
      h('li', {}, 'O Desata aprende onde achar e testa nos outros PDFs.'),
      h('li', {}, 'Os fluxos leem o resultado pelo Input Data.')));
    live.replaceChildren(...parts);
  };
  const schedule = debounce(refresh, 300);

  const save = async () => {
    if (!value.name.trim()) { name.focus(); name.classList.add('invalid'); return; }
    try {
      let saved;
      if (state.way === 'upload' && !existing) {
        if (!state.file) { fileInput.click(); return; }
        saved = await api.uploadPdf(state.file, value.name.trim(), value.recipe || '');
      } else {
        const body = { name: value.name.trim(), mode: state.way === 'folder' ? 'pasta' : 'arquivo', path: value.path.trim(), pattern: value.pattern || '*.pdf',
          policy: value.policy || 'parar', examples: value.examples || [], page_column: Boolean(value.page_column), ...(existing ? {} : { recipe: value.recipe || '' }) };
        saved = existing ? await api.updatePdf(existing.id, body) : await api.createPdf(body);
      }
      await refreshPdfSources();
      toast(existing ? 'Cadastro salvo' : 'Fonte criada', { kind: 'success', detail: existing ? '' : 'Agora marque no documento os dados que você quer.' });
      onSaved?.(saved, { isNew: !existing });
    } catch (err) {
      toastError(err, 'Não foi possível salvar');
    }
  };
  const primary = button({ icon: 'check', label: existing ? 'Salvar' : 'Preparar extração', variant: 'primary', onClick: save });

  drop.addEventListener('dragover', (e) => { e.preventDefault(); drop.classList.add('over'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('over'));
  drop.addEventListener('drop', (e) => { e.preventDefault(); drop.classList.remove('over'); pickUpload([...e.dataTransfer.files].find((f) => /\.pdf$/i.test(f.name))); });

  drawForm();
  return {
    title: existing ? `Editar ${existing.name}` : 'Novo leitor de PDF',
    body: h('div', { class: 'fd-wrap' },
      existing ? null : h('div', { class: 'pdf-example' }, icon('info', 14),
        h('span', {}, 'Sem um PDF à mão? Experimente com três relatórios de vendas de exemplo, um deles com dois totais.'),
        button({ icon: 'play', label: 'Usar os PDFs de exemplo', size: 'sm', onClick: async () => {
          try { const saved = await api.createPdfExample(); await refreshPdfSources(); onSaved?.(saved, { isNew: true }); } catch (err) { toastError(err, 'Não foi possível abrir o exemplo'); }
        } })),
      existing && existing.stored ? h('p', { class: 'field-help' }, icon('info', 12), ' Esta fonte usa uma cópia enviada. Para trocar o documento, crie outra fonte ou duplique esta.') : ways,
      h('div', { class: 'fd-editor' }, h('div', { class: 'stack-sm' }, form, fileInput), live)),
    actions: [button({ label: 'Cancelar', variant: 'ghost', onClick: () => host.close?.() }), primary],
  };
}
