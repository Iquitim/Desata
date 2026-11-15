// Editor "Preparar extração" do leitor de PDF (spec 037, RF-3710..3762).
// Três áreas: Campos (o que já foi ensinado), Documento (a página) e Resultado (este documento e o teste nos outros).
// Marcar no PDF, ver o dado nascer e conferir de onde veio: cada mudança roda de verdade no documento aberto e numa
// amostra dos outros, e o painel mostra o que mudou, com desfazer.

import { api } from './api.js';
import { button, debounce, h } from './dom.js';
import { icon } from './icons.js';
import { fieldCard, tableCard } from './pdf_fields.js';
import { chip, clone, howText, reduced, showValue, STATE } from './pdf_format.js';
import { createViewer, toReading } from './pdf_page.js';
import { exportRecipe, importRecipe, recipesDialog } from './pdf_recipes.js';
import { outputText, refreshPdfSources } from './pdf_sources.js';
import { confirmDialog, showMenu, toast, toastError } from './ui.js';

/** replaceChildren escreveria `null` como texto: o conteúdo condicional some em vez disso. */
const fill = (el, ...kids) => el.replaceChildren(...kids.filter((k) => k !== null && k !== undefined && k !== false));

const SAMPLE = 12;
/**
 * `source`: a fonte; `opts`: { doc (chave para abrir), onSaved(recipe), onClose }.
 * Devolve { el, destroy }.
 */
export function pdfEditor(source, opts = {}) {
  const E = {
    docs: [], doc: null, info: null, recipe: null, saved: false, tipos: {},
    results: {}, sample: null, running: null, history: [], future: [], colors: {}, next: 0,
    focus: null, suggestion: null, sugSeq: 0, change: null, saving: 'idle', revision: 0,
    tab: 'doc', side: 'result', narrow: false, show: { fields: true, result: true },
  };
  const colorOf = (name) => `var(--series-${((E.colors[name] ?? 0) % 8) + 1})`;
  const assign = (name) => { if (!(name in E.colors)) E.colors[name] = E.next++; };

  // ---------------------------------------------------------- estrutura
  const docSelect = h('select', { class: 'input pe-doc-select', 'aria-label': 'Documento', onchange: (e) => openDoc(e.target.value) });
  const saveState = h('span', { class: 'pe-save', 'aria-live': 'polite' });
  const toggleFields = h('button', { type: 'button', class: 'btn btn-ghost pe-toggle', 'aria-pressed': 'true', onclick: () => togglePanel('fields') }, icon('list', 14), h('span', {}, 'Campos'));
  const toggleResult = h('button', { type: 'button', class: 'btn btn-ghost pe-toggle', 'aria-pressed': 'true', onclick: () => togglePanel('result') }, icon('table', 14), h('span', {}, 'Resultado'));
  const recipeBtn = h('button', { type: 'button', class: 'btn btn-ghost pe-recipe-btn', title: 'Extrações salvas: copiar, trocar, exportar, importar', onclick: (e) => recipeMenu(e) },
    icon('copy', 14), h('span', {}, 'Extração'), icon('chevron-down', 12));
  const helpBtn = button({ icon: 'book', title: 'Manual neste tópico (F1)', variant: 'ghost', onClick: () => window.dispatchEvent(new Event('prodata:manual-here')) });
  const gesture = (name) => { document.body.dataset.pdfGesture = name; };
  const wideBtn = button({ icon: 'maximize', title: 'Ampliar o editor (Esc volta)', variant: 'ghost', onClick: () => setWide(!document.body.classList.contains('pdf-wide')) });
  const undoBtn = button({ icon: 'undo', title: 'Desfazer (Ctrl+Z)', variant: 'ghost', disabled: true, onClick: () => undo() });
  const redoBtn = button({ icon: 'redo', title: 'Refazer (Ctrl+Y)', variant: 'ghost', disabled: true, onClick: () => redo() });
  const bar = h('div', { class: 'pe-bar' },
    h('span', { class: 'pe-bar-label' }, icon('file', 14)), docSelect, saveState,
    h('span', { class: 'pe-grow' }), recipeBtn, undoBtn, redoBtn, toggleFields, toggleResult, helpBtn, wideBtn);
  const fieldsPane = h('aside', { class: 'pe-fields', 'aria-label': 'Campos ensinados' });
  const resultPane = h('aside', { class: 'pe-result', 'aria-label': 'Resultado' });
  const viewer = createViewer({
    onSelection: () => fetchSuggestion(),
    onPrimary: () => (E.focus && E.labelMode ? useAsLabel() : createField()),
    onTable: () => createTable(),
    onLabel: () => useAsLabel(),
    onWordClick: (i) => revealOwner(i),
    onCarry: () => createField(),
    dropTarget: () => resultPane,
    renderAction,
  });
  const docPane = h('section', { class: 'pe-doc', 'aria-label': 'Documento' }, viewer.el);
  const grid = h('div', { class: 'pe-layout' }, fieldsPane, docPane, resultPane);
  const el = h('div', { class: 'pe' }, bar, grid);

  function togglePanel(which) {
    if (E.narrow) { E.side = which; } else { E.show[which] = !E.show[which]; }
    drawLayout();
  }
  function drawLayout() {
    const showFields = E.narrow ? E.side === 'fields' : E.show.fields;
    const showResult = E.narrow ? E.side === 'result' : E.show.result;
    fieldsPane.hidden = !showFields;
    resultPane.hidden = !showResult;
    toggleFields.setAttribute('aria-pressed', String(showFields));
    toggleResult.setAttribute('aria-pressed', String(showResult));
    grid.dataset.layout = `${showFields ? 'f' : ''}d${showResult ? 'r' : ''}`;
  }
  new ResizeObserver(() => {
    const narrow = el.clientWidth < 1150;
    if (narrow !== E.narrow) { E.narrow = narrow; drawLayout(); }
  }).observe(el);

  function setWide(on) {
    document.body.classList.toggle('pdf-wide', on);
    wideBtn.replaceChildren(icon(on ? 'minimize' : 'maximize', 16));
    wideBtn.title = on ? 'Voltar ao tamanho normal (Esc)' : 'Ampliar o editor (Esc volta)';
    window.dispatchEvent(new Event('resize'));
  }
  const onKey = (e) => {
    if (!el.isConnected) return;
    if (e.key === 'Escape' && document.body.classList.contains('pdf-wide') && !e.defaultPrevented) setWide(false);
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z' && !e.shiftKey && !isField(e.target)) { e.preventDefault(); undo(); }
    if ((e.ctrlKey || e.metaKey) && (e.key.toLowerCase() === 'y' || (e.shiftKey && e.key.toLowerCase() === 'z')) && !isField(e.target)) { e.preventDefault(); redo(); }
  };
  const isField = (t) => t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT');
  document.addEventListener('keydown', onKey);

  // ---------------------------------------------------------- extrações salvas (RF-3705)
  async function reload() {
    const current = await api.pdfSources().then((all) => all.find((p) => p.id === source.id)).catch(() => null);
    if (current) Object.assign(source, current);
    E.history = [];
    E.future = [];
    E.results = {};
    E.sample = null;
    E.change = null;
    E.colors = {};
    E.next = 0;
    opts.doc = E.doc;
    await init();
  }
  function recipeMenu(e) {
    const r = e.currentTarget.getBoundingClientRect();
    const has = E.saved && (E.recipe.campos.length || E.recipe.tabelas.length);
    showMenu(r.left, r.bottom + 4, [
      { heading: E.saved ? `“${E.recipe.nome}” · revisão ${E.revision}` : 'Extração ainda não salva' },
      { label: 'Copiar como extração nova', icon: 'copy', disabled: !has, onSelect: async () => {
        try {
          const out = await api.forkPdfRecipe(source.id);
          toast('Extração copiada', { kind: 'success', detail: `Esta fonte agora usa “${out.recipe.nome}”. A original não muda.` });
          await refreshPdfSources();
          reload();
        } catch (err) { toastError(err, 'Não foi possível copiar'); }
      } },
      { label: 'Trocar por outra extração…', icon: 'refresh', onSelect: () => recipesDialog(source, reload) },
      { label: 'Exportar extração', icon: 'download', disabled: !has, onSelect: () => exportRecipe(E.recipe.id) },
      { label: 'Importar extração…', icon: 'upload', onSelect: async () => { if (await importRecipe(source.id)) reload(); } },
      'separator',
      { label: 'Extrações salvas…', icon: 'list', onSelect: () => recipesDialog(source, reload) },
    ]);
  }

  // ---------------------------------------------------------- carregar
  async function init() {
    fieldsPane.replaceChildren(h('p', { class: 'muted pe-pad' }, 'Abrindo…'));
    try {
      const [docs, rec] = await Promise.all([api.pdfDocs(source.id), api.pdfRecipe(source.id)]);
      E.docs = docs.docs;
      E.recipe = rec.recipe;
      E.saved = rec.saved;
      E.tipos = rec.tipos;
      E.revision = rec.saved ? rec.recipe.revisao : 0;
      E.shared = rec.shared;
      for (const f of E.recipe.campos) assign(f.nome);
      for (const t of E.recipe.tabelas) assign(t.nome);
      if (docs.error) {
        fieldsPane.replaceChildren(h('p', { class: 'api-warn pe-pad' }, icon('alert', 14), ` ${docs.error}`));
        return;
      }
      drawDocSelect();
      drawSave();
      const first = E.docs.find((d) => d.key === opts.doc) || E.docs.find((d) => !d.example && !d.missing) || E.docs[0];
      if (first) await openDoc(first.key);
      else fieldsPane.replaceChildren(h('p', { class: 'api-warn pe-pad' }, 'Nenhum PDF nesta fonte. Confira o arquivo ou a pasta em Cadastro.'));
      runSample();
    } catch (err) {
      fieldsPane.replaceChildren(h('p', { class: 'text-error pe-pad' }, icon('alert', 14), ` ${err.message}`));
    }
  }

  function drawDocSelect() {
    const label = (d) => {
      const r = E.results[d.key] || E.sample?.results?.[d.key];
      const mark = r ? { aprovado: '✓', revisar: '!', falhou: '×' }[r.estado] || '' : '';
      return `${mark ? `${mark} ` : ''}${d.name}${d.example ? ' (exemplo)' : ''}`;
    };
    const real = E.docs.filter((d) => !d.example);
    const examples = E.docs.filter((d) => d.example);
    fill(docSelect, 
      h('optgroup', { label: `Documentos da fonte (${real.length})` }, real.map((d) => h('option', { value: d.key, selected: d.key === E.doc }, label(d)))),
      examples.length ? h('optgroup', { label: 'Exemplos (só para testar)' }, examples.map((d) => h('option', { value: d.key, selected: d.key === E.doc }, label(d)))) : null);
  }

  async function openDoc(key, then) {
    E.doc = key;
    E.suggestion = null;
    drawDocSelect();
    try {
      E.info = await api.pdfWords(source.id, key);
    } catch (err) {
      E.info = { erro: 'falha', mensagem: err.message, pages: [], words: [] };
    }
    viewer.load(source.id, key, E.info);
    await evaluateCurrent();
    then?.();
  }

  // ---------------------------------------------------------- salvar, desfazer
  function drawSave() {
    const text = {
      idle: E.saved ? `Salvo · revisão ${E.revision}` : 'Rascunho: marque um dado para começar',
      saving: 'Salvando…', saved: `Salvo · revisão ${E.revision}`, error: 'Não foi salvo',
    }[E.saving];
    saveState.replaceChildren(icon(E.saving === 'error' ? 'alert' : E.saving === 'saving' ? 'clock' : 'check', 12), text);
    saveState.className = ['pe-save', E.saving === 'error' && 'tone-err'].filter(Boolean).join(' ');
    undoBtn.disabled = !E.history.length;
    redoBtn.disabled = !E.future.length;
  }
  const save = debounce(async () => {
    if (!E.recipe.campos.length && !E.recipe.tabelas.length && !E.saved) return;
    E.saving = 'saving';
    drawSave();
    try {
      const out = await api.savePdfRecipe(source.id, E.recipe);
      E.saved = true;
      E.revision = out.recipe.revisao;
      E.recipe.revisao = out.recipe.revisao;
      E.recipe.id = out.recipe.id;
      E.saving = 'saved';
      opts.onSaved?.(out);
      refreshPdfSources();
    } catch (err) {
      E.saving = 'error';
      toastError(err, 'Não foi possível salvar a extração');
    }
    drawSave();
  }, 500);

  /** Toda mudança passa por aqui: guarda para desfazer, salva, roda no documento e na amostra. */
  function change(label, mutate, { sample = true } = {}) {
    E.history.push({ recipe: clone(E.recipe), label });
    if (E.history.length > 60) E.history.shift();
    E.future = [];
    mutate(E.recipe);
    save();
    const done = evaluateCurrent();
    if (sample) runSample({ compare: label });
    drawSave();
    return done;
  }
  function undo() {
    const last = E.history.pop();
    if (!last) return;
    E.future.push({ recipe: clone(E.recipe), label: last.label });
    E.recipe = last.recipe;
    save();
    evaluateCurrent();
    runSample({ compare: `desfazer “${last.label}”` });
    viewer.announce(`Desfeito: ${last.label}`);
    drawSave();
  }
  function redo() {
    const next = E.future.pop();
    if (!next) return;
    E.history.push({ recipe: clone(E.recipe), label: next.label });
    E.recipe = next.recipe;
    save();
    evaluateCurrent();
    runSample({ compare: next.label });
    drawSave();
  }

  // ---------------------------------------------------------- avaliar (execução real)
  let currentSeq = 0;
  async function evaluateCurrent() {
    const seq = ++currentSeq;
    if (!E.doc) return;
    if (!E.recipe.campos.length && !E.recipe.tabelas.length) {
      E.results[E.doc] = null;
      drawAll();
      return;
    }
    try {
      const out = await api.evaluatePdf(source.id, E.recipe, { docs: [E.doc] });
      if (seq !== currentSeq) return;
      E.results[E.doc] = out.results[E.doc] || null;
    } catch (err) {
      if (seq !== currentSeq) return;
      toastError(err, 'Não foi possível aplicar a extração');
    }
    drawAll();
  }

  const runSample = debounce(async ({ compare = null, all = false } = {}) => {
    E.running?.abort();
    if (!E.recipe.campos.length && !E.recipe.tabelas.length) { E.sample = null; drawResult(); return; }
    const controller = new AbortController();
    E.running = controller;
    const before = E.sample?.results ? { ...E.sample.results } : null;
    const keys = E.docs.filter((d) => !d.missing).map((d) => d.key);
    const chosen = all ? keys : [E.doc, ...keys.filter((k) => k !== E.doc)].filter(Boolean).slice(0, SAMPLE);
    drawResult();
    try {
      const out = await api.evaluatePdf(source.id, E.recipe, { docs: chosen, limit: Math.max(chosen.length, 1), signal: controller.signal });
      if (E.running !== controller) return;
      E.sample = out;
      E.sample.requested = chosen.length;
      if (compare && before && Object.keys(before).length > 1) E.change = compareRuns(compare, before, out.results);
    } catch (err) {
      if (err.name !== 'AbortError') toastError(err, 'Não foi possível testar nos outros arquivos');
    } finally {
      if (E.running === controller) E.running = null;
    }
    drawDocSelect();
    drawResult();
  }, 450);

  /** RF-3743: o que mudou nos documentos testados, com os números da execução real. */
  function compareRuns(label, before, after) {
    const rank = { aprovado: 2, revisar: 1, falhou: 0 };
    let kept = 0;
    let fixed = 0;
    let broke = 0;
    const broken = [];
    for (const [key, now] of Object.entries(after)) {
      const was = before[key];
      if (!was) continue;
      if (was.estado === now.estado) kept += 1;
      else if (rank[now.estado] > rank[was.estado]) fixed += 1;
      else { broke += 1; broken.push(key); }
    }
    return fixed || broke ? { label, kept, fixed, broke, broken } : null;
  }

  // ---------------------------------------------------------- sugestão e barra de ação
  const fetchSuggestion = debounce(async () => {
    const words = viewer.selection();
    E.suggestion = null;
    if (!words.length) { viewer.refreshAction(); return; }
    const seq = ++E.sugSeq;
    try {
      const sug = await api.suggestPdfField(source.id, E.doc, words);
      if (seq === E.sugSeq) { E.suggestion = sug; viewer.refreshAction(); }
    } catch {
      if (seq === E.sugSeq) viewer.refreshAction();
    }
  }, 90);

  function renderAction(words, lines) {
    const text = words.map((w) => w.t).join(' ');
    const sug = E.suggestion;
    const many = lines >= 3;
    const focusSpec = E.focus ? E.recipe.campos.find((f) => f.nome === E.focus) : null;
    const res = sug?.resultado;
    const value = res && res.estado === 'encontrado' ? showValue(res.valor, sug.campo.tipo) : text;
    const sub = sug ? [`${E.tipos[sug.campo.tipo]} · ${sug.explicacao.split(':')[0]}`, sug.fragil ? h('span', { class: 'pe-fragile' }, ' · frágil') : null] : 'lendo…';
    const fieldBtn = button({ label: 'Criar campo', variant: many || focusSpec ? '' : 'primary', size: 'sm', onClick: () => createField() });
    fieldBtn.append(h('kbd', {}, focusSpec ? '' : 'Enter'));
    const tableBtn = lines >= 2 ? button({ label: 'Criar tabela', variant: many ? 'primary' : '', size: 'sm', onClick: () => createTable() }) : null;
    tableBtn?.append(h('kbd', {}, 'T'));
    const labelBtn = focusSpec ? button({ label: `Usar como rótulo de ${focusSpec.nome}`, variant: 'primary', size: 'sm', onClick: () => useAsLabel() }) : null;
    labelBtn?.append(h('kbd', {}, 'R'));
    return [
      many ? h('div', { class: 'pv-action-val' }, h('b', {}, `${lines} linhas marcadas`), h('small', {}, 'Tabela: colunas pelos espaços em branco'))
        : h('div', { class: 'pv-action-val' }, h('b', {}, value.length > 42 ? `${value.slice(0, 40)}…` : value), h('small', {}, sub)),
      labelBtn, many ? [tableBtn, fieldBtn] : [fieldBtn, tableBtn],
    ];
  }

  function uniqueName(base) {
    const taken = new Set([...E.recipe.campos, ...E.recipe.tabelas].map((x) => x.nome));
    let name = base || 'campo';
    let n = 2;
    while (taken.has(name)) name = `${base}_${n++}`;
    return name;
  }

  async function createField() {
    const words = viewer.selection();
    if (!words.length) return;
    let sug = E.suggestion;
    if (!sug) {
      try { sug = await api.suggestPdfField(source.id, E.doc, words); } catch (err) { toastError(err, 'Não foi possível criar o campo'); return; }
    }
    gesture('campo');
    const campo = { ...sug.campo, nome: uniqueName(sug.campo.nome) };
    const from = viewer.selectionRect();
    const text = words.map((w) => w.t).join(' ');
    assign(campo.nome);
    viewer.clearSelection();
    await change(`criar o campo ${campo.nome}`, (r) => { r.campos.push(campo); });
    flyTo(from, text, resultPane.querySelector(`[data-cell="${CSS.escape(campo.nome)}"]`) || fieldsPane.querySelector(`[data-field="${CSS.escape(campo.nome)}"]`));
    viewer.pulseOwner(campo.nome);
    const r = E.results[E.doc]?.campos?.find((f) => f.nome === campo.nome);
    viewer.announce(`Campo ${campo.nome} criado: ${r ? showValue(r.valor, campo.tipo) : ''}.`);
  }

  async function createTable() {
    const words = viewer.selection();
    if (viewer.selectionLines() < 2) { viewer.announce('Marque o cabeçalho e ao menos uma linha da tabela.'); return; }
    const page = words[0].p;
    const on = words.filter((w) => w.p === page);
    const area = [Math.max(0, Math.min(...on.map((w) => w.b[0])) - 0.01), Math.max(0, Math.min(...on.map((w) => w.b[1])) - 0.003),
      Math.min(1, Math.max(...on.map((w) => w.b[2])) + 0.01), Math.min(1, Math.max(...on.map((w) => w.b[3])) + 0.003)];
    let sug;
    try { sug = await api.suggestPdfTable(source.id, E.doc, page, area, 'tabela'); } catch (err) { toastError(err, 'Não foi possível montar a tabela'); return; }
    gesture('tabela');
    const tabela = { ...sug.tabela, nome: uniqueName(sug.tabela.nome) };
    const from = viewer.selectionRect();
    assign(tabela.nome);
    viewer.clearSelection();
    await change(`criar a tabela ${tabela.nome}`, (r) => { r.tabelas.push(tabela); });
    flyTo(from, `${on.length} palavras`, resultPane.querySelector(`[data-table="${CSS.escape(tabela.nome)}"]`));
    toast(`Tabela ${tabela.nome} criada`, { kind: 'success', detail: sug.explicacao });
  }

  /** "Usar como rótulo" (RF-3714, RF-3721): o texto marcado passa a ser o rótulo do campo em foco. */
  function useAsLabel() {
    const spec = E.focus ? E.recipe.campos.find((f) => f.nome === E.focus) : null;
    const words = viewer.selection();
    if (!spec || !words.length) { viewer.announce('Escolha um campo na lista e marque o rótulo no documento.'); return; }
    const label = words.map((w) => w.t).join(' ').replace(/:\s*$/, '').trim();
    const current = E.results[E.doc]?.campos?.find((f) => f.nome === spec.nome);
    const target = current?.candidatos?.[0]?.origem?.[0];
    let direcao = 'direita';
    if (target && target.p === words[0].p) {
      const t = viewer.pageAngle(target.p);
      const lab = toReading([Math.min(...words.map((w) => w.b[0])), Math.min(...words.map((w) => w.b[1])), Math.max(...words.map((w) => w.b[2])), Math.max(...words.map((w) => w.b[3]))], t);
      const val = toReading(target.b, t);
      const sameLine = Math.abs((lab[1] + lab[3]) / 2 - (val[1] + val[3]) / 2) < (lab[3] - lab[1]);
      direcao = sameLine ? 'direita' : 'abaixo';
    }
    const found = current?.estado === 'encontrado';
    change(`usar “${label}” como rótulo de ${spec.nome}`, (r) => {
      const f = r.campos.find((x) => x.nome === spec.nome);
      if (f.regra.tipo === 'rotulo' && found && f.regra.direcao === direcao) {
        if (!f.regra.rotulos.includes(label)) f.regra.rotulos.push(label);
      } else {
        f.regra = { tipo: 'rotulo', rotulos: [label], direcao, distancia: 0.3 };
      }
    });
    viewer.clearSelection();
    E.labelMode = false;
    toast(found ? `“${label}” vale como rótulo de ${spec.nome}` : `${spec.nome} agora fica ${direcao === 'direita' ? 'à direita' : 'abaixo'} de “${label}”`, { kind: 'success' });
  }

  function flyTo(from, text, target) {
    if (!target) return;
    target.scrollIntoView({ block: 'nearest', behavior: reduced() ? 'auto' : 'smooth' });
    target.classList.remove('pe-born');
    void target.offsetWidth;
    target.classList.add('pe-born');
    if (!from || reduced()) return;
    const to = target.getBoundingClientRect();
    const ghost = h('div', { class: 'pe-fly' }, text);
    document.body.append(ghost);
    ghost.animate([
      { left: `${from.left}px`, top: `${from.top}px`, width: `${from.width}px`, height: `${from.height}px`, opacity: 1 },
      { left: `${to.left}px`, top: `${to.top}px`, width: `${Math.min(to.width, 260)}px`, height: `${Math.min(to.height, 40)}px`, opacity: 0.15 },
    ], { duration: 560, easing: 'cubic-bezier(.2,.7,.2,1)', fill: 'forwards' }).onfinish = () => ghost.remove();
  }

  // ---------------------------------------------------------- desenho
  function drawAll() {
    drawFields();
    drawResult();
    drawMarks();
  }

  function drawMarks() {
    const r = E.results[E.doc];
    if (!r || E.info?.erro) { viewer.setMarks({ fields: [], tables: [] }); return; }
    const fields = E.recipe.campos.map((spec, k) => {
      const f = r.campos?.[k];
      return f && !f.corrigido ? { name: spec.nome, color: colorOf(spec.nome), state: f.estado, candidates: f.candidatos, focus: E.focus === spec.nome } : null;
    }).filter(Boolean);
    const tables = E.recipe.tabelas.map((spec, k) => {
      const t = r.tabelas?.[k];
      if (!t) return null;
      const regions = {};
      for (const row of t.linhas) {
        for (const cell of Object.values(row.celulas)) {
          for (const o of cell.origem) {
            const b = toReading(o.b, viewer.pageAngle(o.p));
            const g = (regions[o.p] ||= [spec.limites[0], 1, spec.limites[1], 0]);
            g[1] = Math.min(g[1], b[1] - 0.006);
            g[3] = Math.max(g[3], b[3] + 0.006);
          }
        }
      }
      return {
        spec, color: colorOf(spec.nome), regions, rows: t.linhas.length, ignored: t.ignoradas,
        onMove: (final, extra) => moveGuide(spec, final, extra),
      };
    }).filter(Boolean);
    viewer.setMarks({ fields, tables });
  }

  let guideBusy = false;
  let guideAgain = false;
  let guideStart = null;
  function moveGuide(spec, final, extra = {}) {
    gesture('tabela');
    // a guia já mudou no objeto da receita: a prévia ao vivo roda só no documento aberto
    if (!guideStart) guideStart = clone(E.recipe);
    if (final) {
      const before = guideStart;
      guideStart = null;
      E.history.push({ recipe: before, label: `mover uma guia de ${spec.nome}` });
      E.future = [];
      save();
      evaluateCurrent().then(() => { if (extra.refocus !== undefined) viewer.el.querySelectorAll('.pv-guide')[extra.refocus]?.focus(); });
      runSample({ compare: `mover uma guia de ${spec.nome}` });
      drawSave();
      return;
    }
    if (guideBusy) { guideAgain = true; return; }
    guideBusy = true;
    api.evaluatePdf(source.id, E.recipe, { docs: [E.doc] }).then((out) => {
      E.results[E.doc] = out.results[E.doc];
      drawFields();
      drawResult();
    }).catch(() => {}).finally(() => {
      guideBusy = false;
      if (guideAgain) { guideAgain = false; moveGuide(spec, false); }
    });
  }

  // ---------- painel Campos
  function drawFields() {
    const r = E.results[E.doc];
    const parts = [h('div', { class: 'pe-pane-head' }, h('h3', {}, 'Campos'),
      h('span', { class: 'pe-count' }, String(E.recipe.campos.length + E.recipe.tabelas.length)))];
    if (!E.recipe.campos.length && !E.recipe.tabelas.length) {
      parts.push(h('div', { class: 'pe-empty' },
        h('div', { class: 'pe-empty-art', 'aria-hidden': 'true' }, h('span', { class: 'pe-empty-word' }, 'Total líquido:'), h('span', { class: 'pe-empty-pick' }, 'R$ 834.086,00'),
          icon('chevron-right', 16), h('span', { class: 'pe-empty-col' }, h('b', {}, 'total_liquido'), h('small', {}, '834.086,00'))),
        h('b', {}, 'Marque uma informação no documento para virar coluna'),
        h('ol', {},
          h('li', {}, 'Clique num valor, ou dê dois cliques para pegar o valor inteiro.'),
          h('li', {}, 'Confira a prévia em cima da seleção e tecle ', h('kbd', {}, 'Enter'), '.'),
          h('li', {}, 'Para uma tabela, arraste sobre ela e tecle ', h('kbd', {}, 'T'), '.'),
          h('li', {}, 'Pelo teclado: clique no documento e use as setas, com ', h('kbd', {}, 'Shift'), ' para marcar.'))));
    }
    const ctx = { E, source, viewer, colorOf, change, setFocus, removeItem, uniqueName, drawFields, evaluateCurrent, runSample };
    E.recipe.campos.forEach((spec, k) => parts.push(fieldCard(ctx, spec, r?.campos?.[k])));
    E.recipe.tabelas.forEach((spec, k) => parts.push(tableCard(ctx, spec, r?.tabelas?.[k])));
    if (E.shared > 1) parts.push(h('p', { class: 'field-help pe-pad' }, icon('info', 12), ` Esta extração é usada por ${E.shared} fontes: mudar aqui muda nas outras também.`));
    fieldsPane.replaceChildren(...parts);
  }

  function setFocus(name) {
    gesture('rotulo');
    E.focus = E.focus === name ? null : name;
    E.labelMode = Boolean(E.focus);
    fieldsPane.querySelectorAll('[data-field], [data-table]').forEach((c) => c.classList.toggle('active', (c.dataset.field || c.dataset.table) === E.focus));
    viewer.focusOwner(E.focus);
    viewer.refreshAction();
    if (E.focus) viewer.announce(`Campo ${E.focus} em foco. Marque um texto no documento e tecle R para usá-lo como rótulo.`);
  }

  async function removeItem(kind, spec) {
    const ok = await confirmDialog({ title: `Remover ${spec.nome}?`, message: 'Dá para desfazer com Ctrl+Z.', confirm: 'Remover', danger: true });
    if (!ok) return;
    if (E.focus === spec.nome) setFocus(spec.nome);
    change(`remover ${spec.nome}`, (r) => { r[kind] = r[kind].filter((x) => x.nome !== spec.nome); });
  }

  // ---------- painel Resultado
  function drawResult() {
    const tabs = h('div', { class: 'pe-tabs', role: 'tablist', 'aria-label': 'Resultado' },
      [['doc', 'Este documento'], ['test', 'Testar em outros arquivos']].map(([k, label]) => h('button', {
        type: 'button', role: 'tab', class: 'pe-tab', 'aria-selected': String(E.tab === k), onclick: () => { E.tab = k; drawResult(); },
      }, label, k === 'test' && E.sample ? h('span', { class: 'pe-count' }, `${E.sample.evaluated}`) : null)));
    const parts = [h('div', { class: 'pe-pane-head' }, h('h3', {}, 'Resultado'), impactChip()), tabs];
    if (E.change) parts.push(changeBanner(E.change));
    parts.push(E.tab === 'doc' ? docResult() : testResult());
    resultPane.replaceChildren(...parts);
  }

  function impactChip() {
    if (E.running) return h('span', { class: 'pe-chip tone-info' }, icon('clock', 11), 'testando…', h('button', { type: 'button', class: 'link', onclick: () => { E.running?.abort(); E.running = null; drawResult(); } }, 'cancelar'));
    if (!E.sample) return null;
    const c = E.sample.counts;
    return h('button', { type: 'button', class: 'pe-impact', title: 'Ver o teste nos outros arquivos', onclick: () => { E.tab = 'test'; drawResult(); } },
      `${E.sample.evaluated} de ${E.sample.total} avaliados`,
      c.aprovado ? chip('aprovado', String(c.aprovado)) : null, c.revisar ? chip('revisar', String(c.revisar)) : null, c.falhou ? chip('falhou', String(c.falhou)) : null);
  }

  function changeBanner(ch) {
    return h('div', { class: ['pe-change', ch.broke ? 'tone-warn' : 'tone-ok'], role: 'status' },
      h('div', {}, h('b', {}, `Depois de ${ch.label}:`), ' ',
        `${ch.kept} mantido${ch.kept === 1 ? '' : 's'} · ${ch.fixed} corrigido${ch.fixed === 1 ? '' : 's'} · ${ch.broke} passa${ch.broke === 1 ? '' : 'ram'} a falhar`,
        h('small', {}, ' (execução real nos documentos testados)')),
      h('div', { class: 'row' },
        ch.broke ? button({ label: 'Ver quais', size: 'sm', onClick: () => { E.tab = 'test'; E.change = null; drawResult(); } }) : null,
        button({ icon: 'undo', label: 'Desfazer', size: 'sm', onClick: () => { E.change = null; undo(); } }),
        button({ label: 'Manter', size: 'sm', variant: 'ghost', onClick: () => { E.change = null; drawResult(); } })));
  }

  function docResult() {
    const r = E.results[E.doc];
    if (!E.recipe.campos.length && !E.recipe.tabelas.length) {
      return h('div', { class: 'pe-result-empty' }, icon('table', 22), h('p', {}, 'Os dados que você marcar aparecem aqui, na hora, como colunas de uma tabela.'),
        h('p', { class: 'field-help' }, 'Também dá para arrastar a seleção até aqui.'));
    }
    if (E.info?.erro) return h('p', { class: 'api-warn' }, icon('alert', 14), ` Este PDF não pode ser lido: ${E.info.mensagem}.`);
    if (!r) return h('p', { class: 'muted' }, 'Aplicando…');
    const out = [h('div', { class: 'pe-doc-state' }, chip(r.estado), h('span', {}, r.motivo || 'Tudo encontrado neste documento.'))];
    if (E.recipe.campos.length) {
      out.push(h('section', { class: 'pe-out' },
        h('div', { class: 'pe-out-head' }, h('b', {}, outputText('campos')[0]), h('small', {}, 'uma linha por documento')),
        h('table', { class: 'pe-grid' },
          h('tbody', {}, E.recipe.campos.map((spec, k) => {
            const f = r.campos?.[k];
            const best = f?.candidatos?.[0];
            return h('tr', { class: f && f.estado !== 'encontrado' ? 'doubt' : '' },
              h('th', { scope: 'row' }, h('span', { class: 'pe-dot', style: { '--c': colorOf(spec.nome) } }), spec.nome),
              h('td', { class: spec.tipo !== 'texto' ? 'num' : '' },
                h('button', { type: 'button', dataset: { cell: spec.nome }, title: best ? `De onde veio: página ${best.origem[0]?.p + 1}` : f?.motivo || '',
                  onclick: () => { if (best && !f.corrigido) viewer.reveal(best.origem, colorOf(spec.nome)); setFocus(spec.nome); } },
                f?.estado === 'encontrado' ? showValue(f.valor, spec.tipo) : h('span', { class: 'pe-miss' }, STATE[f?.estado]?.[2] || '—'),
                f?.corrigido ? h('span', { class: 'pe-fixed', title: 'corrigido só neste documento' }, icon('edit', 10)) : null)));
          })))));
    }
    E.recipe.tabelas.forEach((spec, k) => out.push(tableGrid(spec, r.tabelas?.[k])));
    return h('div', { class: 'pe-result-body' }, out);
  }

  function tableGrid(spec, t) {
    const c = colorOf(spec.nome);
    const rows = t?.linhas || [];
    const numeric = new Set(spec.colunas.filter((col) => col.tipo !== 'texto').map((col) => col.nome));
    const reps = (t?.ignoradas || []).filter((x) => x.motivo === 'cabeçalho repetido').length;
    const merged = rows.filter((x) => x.linhas > 1).length;
    return h('section', { class: 'pe-out', dataset: { table: spec.nome }, style: { '--c': c } },
      h('div', { class: 'pe-out-head' }, h('b', {}, outputText(`itens_${spec.nome}`)[0]), h('small', {}, `${rows.length} linhas`)),
      t?.problema ? h('p', { class: 'pe-why tone-err' }, icon('alert', 12), ` ${t.problema}`) : null,
      h('div', { class: 'pe-grid-wrap' }, h('table', { class: 'pe-grid pe-grid-wide' },
        h('thead', {}, h('tr', {}, h('th', { class: 'rn' }, '#'), spec.colunas.map((col) => h('th', { title: E.tipos[col.tipo] }, col.nome)))),
        h('tbody', {}, rows.map((row, i) => h('tr', { class: row.duvida ? 'doubt' : '', title: row.duvida || '' },
          h('td', { class: 'rn' }, String(i + 1), row.linhas > 1 ? h('span', { class: 'pe-merged', title: `${row.linhas} linhas do PDF unidas` }, `↵${row.linhas}`) : null,
            row.duvida ? h('span', { class: 'pe-doubt', title: row.duvida }, icon('alert', 10)) : null),
          spec.colunas.map((col) => {
            const cell = row.celulas[col.nome] || { texto: '', origem: [] };
            const shown = cell.erro ? `⚠ ${cell.texto}` : cell.valor !== null && cell.valor !== undefined ? showValue(cell.valor, col.tipo) : '';
            return h('td', { class: numeric.has(col.nome) ? 'num' : '' }, h('button', { type: 'button', title: cell.texto ? `De onde veio: “${cell.texto}”` : '',
              onclick: () => cell.origem.length && viewer.reveal(cell.origem, c) }, shown));
          })))))),
      h('p', { class: 'field-help' }, `Terminou em: ${t?.fim || '—'}`, reps ? ` · ${reps} cabeçalho repetido ignorado` : '', merged ? ` · ${merged} com texto em mais de uma linha, unidas` : ''));
  }

  function testResult() {
    const s = E.sample;
    if (!E.recipe.campos.length && !E.recipe.tabelas.length) return h('p', { class: 'muted' }, 'Crie um campo primeiro.');
    const out = [];
    const total = E.docs.filter((d) => !d.missing).length;
    out.push(h('div', { class: 'pe-test-head' },
      h('p', {}, s ? h('b', {}, `${s.evaluated} de ${s.total} documentos avaliados`) : 'Ainda não testado', s && s.evaluated < s.total ? ' (uma amostra)' : ''),
      E.running ? button({ label: 'Cancelar', size: 'sm', onClick: () => { E.running?.abort(); E.running = null; drawResult(); } })
        : button({ icon: 'play', label: s && s.evaluated >= total ? 'Testar de novo' : `Testar em todos (${total})`, size: 'sm', onClick: () => runSample({ all: true }) })));
    if (!s) return h('div', {}, out);
    out.push(h('div', { class: 'pe-impact-grid' }, E.recipe.campos.map((spec) => {
      const per = s.fields[spec.nome] || {};
      return h('div', { class: 'pe-impact-row' }, h('span', { class: 'pe-dot', style: { '--c': colorOf(spec.nome) } }), h('b', {}, spec.nome),
        ['encontrado', 'ausente', 'ambiguo', 'invalido'].map((k) => (per[k] ? chip(k, `${per[k]} ${STATE[k][2].toLowerCase()}`) : null)),
        per.nao_suportado ? chip('nao_suportado', `${per.nao_suportado} ilegível`) : null);
    })));
    const docs = E.docs.filter((d) => s.results[d.key]);
    out.push(h('div', { class: 'pe-grid-wrap pe-matrix-wrap' }, h('table', { class: 'pe-grid pe-matrix' },
      h('thead', {}, h('tr', {}, h('th', {}, 'Documento'), h('th', {}, 'Situação'),
        E.recipe.campos.map((spec) => h('th', {}, spec.nome)), E.recipe.tabelas.map((spec) => h('th', {}, spec.nome)))),
      h('tbody', {}, docs.map((d) => {
        const r = s.results[d.key];
        const broke = E.change?.broken?.includes(d.key);
        return h('tr', { class: [d.key === E.doc && 'current', broke && 'broke'] },
          h('th', { scope: 'row' }, h('button', { type: 'button', class: 'pe-doc-link', onclick: () => openDoc(d.key) }, d.name, d.example ? h('small', {}, ' exemplo') : null)),
          h('td', {}, chip(r.estado)),
          E.recipe.campos.map((spec, k) => {
            const f = r.campos?.[k];
            if (!f) return h('td', {}, '—');
            return h('td', {}, h('button', { type: 'button', class: ['pe-mcell', `st-${f.estado}`], title: f.motivo || STATE[f.estado][2],
              onclick: () => openDoc(d.key, () => { const best = E.results[d.key]?.campos?.[k]?.candidatos?.[0]; if (best) viewer.reveal(best.origem, colorOf(spec.nome)); E.tab = 'doc'; drawResult(); }) },
            icon(STATE[f.estado][1], 11), f.estado === 'encontrado' ? showValue(f.valor, spec.tipo) : STATE[f.estado][2]));
          }),
          E.recipe.tabelas.map((spec, k) => {
            const t = r.tabelas?.[k];
            return h('td', {}, t ? h('span', { class: ['pe-mcell', t.problema ? 'st-ausente' : t.linhas.some((x) => x.duvida) ? 'st-ambiguo' : 'st-encontrado'] },
              t.problema ? 'ajustar' : `${t.linhas.length} linhas`) : '—');
          }));
      })))));
    if (s.evaluated < s.total) out.push(h('p', { class: 'field-help' }, `Os outros ${s.total - s.evaluated} documentos não foram avaliados ainda. "Testar em todos" avalia até 200.`));
    return h('div', { class: 'pe-result-body' }, out);
  }

  // ---------------------------------------------------------- do PDF para o dado
  function revealOwner(i) {
    const r = E.results[E.doc];
    const w = E.info.words[i];
    if (!r || !w) return;
    const cx = (w.b[0] + w.b[2]) / 2;
    const cy = (w.b[1] + w.b[3]) / 2;
    const inside = (o) => o.p === w.p && cx >= o.b[0] && cx <= o.b[2] && cy >= o.b[1] && cy <= o.b[3];
    for (const [k, f] of (r.campos || []).entries()) {
      if (f.candidatos?.some((cd) => cd.origem.some(inside))) {
        const name = E.recipe.campos[k]?.nome;
        flash(fieldsPane.querySelector(`[data-field="${CSS.escape(name)}"]`));
        flash(resultPane.querySelector(`[data-cell="${CSS.escape(name)}"]`));
        viewer.announce(`Este valor é o campo ${name}: ${howText(E.recipe.campos[k].regra)}.`);
        return;
      }
    }
    for (const [k, t] of (r.tabelas || []).entries()) {
      for (const [ri, row] of t.linhas.entries()) {
        const ci = t.colunas.findIndex((col) => row.celulas[col]?.origem.some(inside));
        if (ci < 0) continue;
        if (E.tab !== 'doc') { E.tab = 'doc'; drawResult(); }
        const btn = resultPane.querySelectorAll(`[data-table="${CSS.escape(E.recipe.tabelas[k].nome)}"] tbody tr`)[ri]?.querySelectorAll('td')[ci + 1]?.querySelector('button');
        flash(btn);
        viewer.announce(`Linha ${ri + 1}, coluna ${t.colunas[ci]} da tabela ${E.recipe.tabelas[k].nome}.`);
        return;
      }
    }
  }
  function flash(node) {
    if (!node) return;
    node.scrollIntoView({ block: 'nearest', behavior: reduced() ? 'auto' : 'smooth' });
    node.classList.remove('pe-flash');
    void node.offsetWidth;
    node.classList.add('pe-flash');
  }

  drawLayout();
  init();
  return {
    el,
    destroy() {
      delete document.body.dataset.pdfGesture;
      E.running?.abort();
      document.removeEventListener('keydown', onKey);
      setWide(false);
    },
    focusDoc: () => viewer.focus(),
    open: (key) => { if (key && key !== E.doc) openDoc(key); },
  };
}

