// Visão geral do leitor de PDF na vista Dados (spec 037, RF-3703, RF-3741, RF-3761, RF-3762, RF-3770).
// Documentos com a situação, saídas com prévia, política de falha em linguagem simples, correções e exemplos.

import { api } from './api.js';
import { stat } from './data_stats.js';
import { previewTable } from './datasets.js';
import { choosePdfFile } from './desktop.js';
import { button, fmt, h } from './dom.js';
import { icon } from './icons.js';
import { chip } from './pdf_format.js';
import { exportRecipe, recipesDialog } from './pdf_recipes.js';
import { addPdfNode, outputText, refreshPdfSources } from './pdf_sources.js';
import { confirmDialog, toast, toastError } from './ui.js';

/** replaceChildren escreveria `null` como texto: o conteúdo condicional some em vez disso. */
const fill = (el, ...kids) => el.replaceChildren(...kids.filter((k) => k !== null && k !== undefined && k !== false));

const MATRIX_MAX = 200;
// Atualizar a lista redesenha a vista (e esta visão geral): só quando o resumo mudou, e no máximo a cada 30 s.
const refreshed = new Map();
const same = (a, b) => Boolean(a && b) && ['aprovado', 'revisar', 'falhou'].every((k) => (a[k] || 0) === (b[k] || 0));
const POLICIES = {
  parar: ['Parar a execução', 'Se algum documento falhar, o fluxo para e diz qual foi e por quê. Nada sai pela metade. Melhor quando há campo obrigatório.'],
  aprovados: ['Entregar só os aprovados', 'Os documentos que falharam ficam de fora dos dados e aparecem na saída falhas, para alguém conferir.'],
  todos: ['Entregar todos, com a situação', 'Todos os documentos entram, com a coluna situacao (Aprovado, Revisar, Falhou). Quem usa decide o que fazer.'],
};
const when = (iso) => (iso ? new Date(iso).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' }) : '—');

function body(source, extra = {}) {
  return {
    name: source.name, mode: source.mode, path: source.path, pattern: source.pattern, policy: source.policy,
    examples: source.examples || [], page_column: Boolean(source.page_column), ...extra,
  };
}

/** `ctx`: openEditor(docKey), refresh(), showDesigner(). */
export function pdfOverview(source, ctx) {
  const st = source.status || {};
  const box = h('div', { class: 'stack-md pdf-overview' });
  if (st.draft) {
    box.append(h('section', { class: 'dv-card pdf-hero' },
      h('div', { class: 'pdf-hero-art', 'aria-hidden': 'true' },
        h('span', { class: 'pdf-hero-page' }, h('i'), h('i', { class: 'pick' }), h('i'), h('i')),
        icon('chevron-right', 18),
        h('span', { class: 'pdf-hero-table' }, h('b', {}, 'total'), h('b', {}, 'competência'), h('span'), h('span'))),
      h('div', { class: 'stack-sm' },
        h('h3', {}, 'Ensine a extração apontando no documento'),
        h('p', {}, 'Clique no valor que você quer, como o total, e ele vira coluna na hora. Depois o Desata testa nos outros PDFs e mostra o que achou.'),
        h('div', { class: 'row' }, button({ icon: 'target', label: 'Preparar extração', variant: 'primary', onClick: () => ctx.openEditor() })))));
  }
  const stats = h('div', { class: 'dv-stats' },
    stat('Documentos', fmt.int(st.files || 0), docsNote(source)),
    stat('Extração', st.draft ? 'rascunho' : `revisão ${st.revision}`, st.draft ? 'ainda sem campos' : `${st.fields} campo(s), ${st.tables} tabela(s)`),
    stat('Se falhar', POLICIES[source.policy][0]),
    stat('Última avaliação', st.checked_at ? when(st.checked_at) : '—', st.summary ? summaryText(st.summary) : ''));
  box.append(stats);
  if (st.missing || st.error) box.append(h('p', { class: 'api-warn' }, icon('alert', 14), ` ${st.error}`));
  const docs = h('section', { class: 'dv-card stack-sm pdf-docs' }, h('h3', {}, 'Documentos'), h('p', { class: 'muted' }, st.draft ? 'Lendo…' : 'Avaliando…'));
  if (st.draft) {
    box.append(docs);
  } else {
    const outputs = h('section', { class: 'dv-card stack-sm' });
    box.append(h('div', { class: 'dv-split' }, docs, policyCard(source, ctx)), outputs);
    drawOutputs(source, outputs, ctx);
  }
  drawDocs(source, docs, ctx);
  box.append(h('section', { class: 'dv-card pdf-recipe-card' }, icon('copy', 18),
    h('div', { class: 'pdf-recipe-main' }, h('b', {}, st.draft ? 'Sem extração ainda' : `Extração: revisão ${st.revision}`),
      h('small', {}, st.draft ? 'Marque os campos no editor, ou use uma extração salva de outra fonte com o mesmo layout.' : `${st.fields} campo(s), ${st.tables} tabela(s). Pode ser usada por outras fontes, exportada ou copiada.`)),
    h('div', { class: 'row' },
      st.draft ? null : button({ icon: 'download', label: 'Exportar', size: 'sm', variant: 'ghost', onClick: () => exportRecipe(source.recipe) }),
      button({ icon: 'list', label: 'Extrações salvas…', size: 'sm', onClick: () => recipesDialog(source, () => ctx.refresh()) }))));
  const fixes = h('section', { class: 'dv-card stack-sm', hidden: true });
  box.append(fixes);
  drawCorrections(source, fixes, ctx);
  if (source.mode === 'arquivo') box.append(examplesCard(source, ctx));
  return box;
}

function docsNote(source) {
  const st = source.status || {};
  const base = source.mode === 'pasta' ? source.pattern : source.stored ? 'cópia enviada' : 'lido onde está';
  const added = (source.added || []).length;
  return [base, added && `${added} adicionado${added === 1 ? '' : 's'}`, st.left_out && `${st.left_out} fora`].filter(Boolean).join(' · ');
}

function summaryText(s) {
  return [s.aprovado && `${s.aprovado} aprovado(s)`, s.revisar && `${s.revisar} a revisar`, s.falhou && `${s.falhou} com falha`].filter(Boolean).join(' · ') || 'nenhum documento';
}

async function drawDocs(source, card, ctx) {
  const st = source.status || {};
  try {
    const listing = await api.pdfDocs(source.id);
    const real = listing.docs.filter((d) => !d.example && !d.missing);
    let out = null;
    if (!st.draft && real.length) {
      const { recipe } = await api.pdfRecipe(source.id);
      const keys = real.slice(0, MATRIX_MAX).map((d) => d.key);
      out = await api.evaluatePdf(source.id, recipe, { docs: keys, limit: Math.max(keys.length, 1) });
      if (!same(out.counts, st.summary) && Date.now() - (refreshed.get(source.id) || 0) > 30000) {
        refreshed.set(source.id, Date.now());
        refreshPdfSources();
      }
    }
    const last = real.length <= 1;
    const rows = real.map((d) => {
      const r = out?.results[d.key];
      const note = r ? (r.motivo || (r.corrigidos?.length ? `corrigido: ${r.corrigidos.join(', ')}` : 'tudo encontrado')) : (d.added ? 'adicionado aqui' : '');
      return h('li', { class: 'pdf-doc-item', dataset: { doc: d.name } },
        h('button', { type: 'button', class: 'pdf-doc-row', onclick: () => ctx.openEditor(d.key), title: 'Abrir no editor, com os campos destacados' },
          icon('file', 14), h('span', { class: 'ellipsis' }, d.name, d.added ? h('span', { class: 'pdf-doc-tag', title: 'Cópia guardada pelo programa' }, 'adicionado') : null),
          r ? chip(r.estado) : h('span'),
          note ? h('small', { class: 'ellipsis' }, note) : null),
        button({ icon: d.added ? 'trash' : 'x', variant: 'ghost', size: 'sm', disabled: last,
          title: last ? 'A fonte precisa de pelo menos um PDF' : d.added ? 'Apagar a cópia guardada pelo programa' : 'Tirar da fonte (o arquivo fica onde está)',
          onClick: () => leaveOut(source, d, ctx) }));
    });
    const c = out?.counts;
    fill(card,
      h('div', { class: 'row space-between' }, h('h3', {}, 'Documentos'),
        h('div', { class: 'row pdf-doc-actions' },
          out ? h('span', { class: 'field-help' }, `${out.evaluated} de ${real.length} avaliados`) : null,
          addButton(source, ctx))),
      c ? h('div', { class: 'row pdf-counts' }, chip('aprovado', `${c.aprovado} aprovado${c.aprovado === 1 ? '' : 's'}`),
        chip('revisar', `${c.revisar} a revisar`), chip('falhou', `${c.falhou} com falha`)) : null,
      h('ul', { class: 'pdf-doc-list' }, rows),
      out && out.evaluated < real.length ? h('p', { class: 'field-help' }, `Os outros ${real.length - out.evaluated} serão lidos na execução do fluxo.`) : null,
      leftOutBox(source, listing.left_out || [], ctx));
  } catch (err) {
    fill(card, h('div', { class: 'row space-between' }, h('h3', {}, 'Documentos'), addButton(source, ctx)),
      h('p', { class: 'text-error' }, icon('alert', 14), ` ${err.message}`));
  }
}

/** RF-3706: soma PDFs à fonte. O programa guarda uma cópia; a pasta da pessoa não é tocada. */
function addButton(source, ctx) {
  const input = h('input', { type: 'file', accept: 'application/pdf,.pdf', multiple: true, hidden: true,
    onchange: async (e) => {
      const files = [...e.target.files];
      e.target.value = '';
      if (!files.length) return;
      try {
        const res = await api.addPdfDocs(source.id, files);
        await refreshPdfSources();
        toast(res.added.length === 1 ? 'PDF adicionado' : `${res.added.length} PDFs adicionados`,
          { kind: 'success', detail: 'O programa guardou uma cópia. A pasta original não foi alterada.' });
        ctx.refresh();
      } catch (err) {
        toastError(err, 'Não foi possível adicionar');
      }
    } });
  return h('span', {}, input, button({ icon: 'plus', label: 'Adicionar PDFs', size: 'sm', title: 'Somar um ou vários PDFs a esta fonte', onClick: () => input.click() }));
}

async function leaveOut(source, doc, ctx) {
  if (doc.added) {
    const ok = await confirmDialog({
      title: 'Apagar esta cópia?',
      message: `“${doc.name}” foi adicionado aqui, e o programa guardou uma cópia. A cópia será apagada; o arquivo de onde ela veio não muda.`,
      confirm: 'Apagar a cópia', danger: true,
    });
    if (!ok) return;
  }
  try {
    const res = await api.leavePdfDoc(source.id, doc.name);
    await refreshPdfSources();
    toast(res.deleted ? 'Cópia apagada' : 'Tirado da fonte', {
      kind: 'success',
      detail: res.deleted ? doc.name : `${doc.name} continua no disco. Para usar de novo, veja “Fora da fonte”.`,
    });
    ctx.refresh();
  } catch (err) {
    toastError(err, 'Não foi possível tirar');
  }
}

function leftOutBox(source, list, ctx) {
  if (!list.length) return null;
  const back = async (name) => {
    try {
      await api.bringBackPdfDoc(source.id, name);
      await refreshPdfSources();
      toast('De volta à fonte', { kind: 'success', detail: name });
      ctx.refresh();
    } catch (err) {
      toastError(err, 'Não foi possível trazer de volta');
    }
  };
  return h('details', { class: 'pdf-left-out', open: list.length <= 3 },
    h('summary', {}, `Fora da fonte (${list.length})`),
    h('p', { class: 'field-help' }, 'Ficam de fora da extração e das saídas. Os arquivos continuam onde estavam.'),
    h('ul', { class: 'pdf-fixes' }, list.map((d) => h('li', { dataset: { doc: d.name } }, icon('file', 14), h('span', { class: 'ellipsis' }, d.name),
      button({ icon: 'undo', label: 'Trazer de volta', size: 'sm', variant: 'ghost', onClick: () => back(d.name) })))));
}

function policyCard(source, ctx) {
  const st = source.status || {};
  const save = async (policy) => {
    try {
      await api.updatePdf(source.id, body(source, { policy }));
      await refreshPdfSources();
      toast('Política salva', { kind: 'success', detail: POLICIES[policy][0] });
      ctx.refresh();
    } catch (err) {
      toastError(err, 'Não foi possível salvar');
    }
  };
  return h('section', { class: 'dv-card stack-sm' },
    h('h3', {}, 'Quando um documento falhar'),
    h('div', { class: 'pdf-policies', role: 'radiogroup', 'aria-label': 'Política de falha' },
      Object.entries(POLICIES).map(([key, [title, text]]) => h('label', { class: ['pdf-policy', source.policy === key && 'active'] },
        h('input', { type: 'radio', name: `pol-${source.id}`, value: key, checked: source.policy === key, onchange: () => save(key) }),
        h('span', {}, h('strong', {}, title, key === 'parar' ? h('small', { class: 'pdf-safe' }, ' sugerida') : null), h('small', {}, text))))),
    h('label', { class: 'pe-check' }, h('input', { type: 'checkbox', checked: Boolean(source.page_column),
      onchange: async (e) => {
        try { await api.updatePdf(source.id, body(source, { page_column: e.target.checked })); await refreshPdfSources(); ctx.refresh(); } catch (err) { toastError(err, 'Não foi possível salvar'); }
      } }), ' Coluna pagina nas tabelas'),
    st.fields ? null : h('p', { class: 'field-help' }, 'Sem campo obrigatório, nenhum documento falha por falta de valor.'));
}

async function drawOutputs(source, card, ctx) {
  const outs = source.status?.outputs || ['campos'];
  const preview = h('div', { class: 'stack-sm' });
  const show = async (name) => {
    card.querySelectorAll('.pdf-out').forEach((x) => x.classList.toggle('active', x.dataset.out === name));
    fill(preview, h('p', { class: 'muted' }, 'Lendo…'));
    try {
      const p = await api.pdfOutput(source.id, name, 50);
      fill(preview, 
        p.stops ? h('p', { class: 'api-warn' }, icon('alert', 14), ` ${p.failed} documento(s) falharam: com a política "Parar a execução", o fluxo para aqui. A prévia mostra mesmo assim, para você conferir.`) : null,
        h('p', { class: 'field-help' }, `${fmt.int(p.row_count)} linha(s) de ${p.documents} documento(s).`),
        previewTable(p.columns, p.rows.slice(0, 15)));
    } catch (err) {
      fill(preview, h('p', { class: 'text-error' }, icon('alert', 14), ` ${err.message}`));
    }
  };
  fill(card, 
    h('div', { class: 'row space-between' }, h('h3', {}, 'Saídas'), h('span', { class: 'field-help' }, 'O Input Data lê cada uma como uma tabela')),
    h('div', { class: 'pdf-outs' }, outs.map((name) => {
      const [title, text] = outputText(name);
      return h('div', { class: 'pdf-out', dataset: { out: name } },
        h('button', { type: 'button', class: 'pdf-out-main', onclick: () => show(name) }, icon(name === 'falhas' ? 'alert' : name === 'origem' ? 'target' : 'table', 16),
          h('span', {}, h('b', {}, title), h('small', {}, text), h('code', { title: `pdf:${source.id}/${name}` }, name))),
        button({ icon: 'plus', title: `Adicionar ${title} ao fluxo`, size: 'sm', onClick: () => { addPdfNode(source, name); ctx.showDesigner(); } }));
    })),
    preview);
  show('campos');
}

async function drawCorrections(source, card, ctx) {
  try {
    const list = await api.pdfCorrections(source.id);
    if (!list.length) return;
    card.hidden = false;
    fill(card, 
      h('div', { class: 'row space-between' }, h('h3', {}, 'Corrigido só em um documento'), h('span', { class: 'org-count' }, String(list.length))),
      h('p', { class: 'field-help' }, 'Valores informados à mão, sem mudar a regra. Cada um vale enquanto o PDF for o mesmo; se o arquivo mudar, deixa de valer sozinho.'),
      h('ul', { class: 'pdf-fixes' }, list.map((c) => h('li', {},
        h('span', {}, h('b', {}, c.campo), ' em ', h('span', { class: 'mono' }, c.documento), ': ',
          c.original ? h('s', {}, c.original) : h('i', {}, 'sem valor'), ' → ', h('b', {}, c.valor)),
        h('small', {}, `${c.quem} · ${when(c.quando)}`),
        button({ icon: 'trash', title: 'Desfazer a correção', variant: 'ghost', size: 'sm',
          onClick: async () => { await api.removePdfCorrection(source.id, c.id).catch((err) => toastError(err, 'Não foi possível desfazer')); ctx.refresh(); } })))));
  } catch {
    card.hidden = true;
  }
}

/** RF-3741: outros PDFs só para testar a extração de uma fonte de um PDF; não entram nos dados. */
function examplesCard(source, ctx) {
  const save = async (examples) => {
    try {
      await api.updatePdf(source.id, body(source, { examples }));
      await refreshPdfSources();
      ctx.refresh();
    } catch (err) {
      toastError(err, 'Não foi possível salvar');
    }
  };
  const add = async () => {
    const chosen = await choosePdfFile();
    if (chosen && !(source.examples || []).includes(chosen)) save([...(source.examples || []), chosen]);
  };
  return h('section', { class: 'dv-card stack-sm' },
    h('div', { class: 'row space-between' }, h('h3', {}, 'Arquivos de exemplo'), button({ icon: 'plus', label: 'Adicionar exemplo', size: 'sm', onClick: add })),
    h('p', { class: 'field-help' }, 'Outros PDFs com o mesmo layout, só para testar a extração antes de virar uma pasta. Eles não entram nos dados.'),
    (source.examples || []).length
      ? h('ul', { class: 'pdf-fixes' }, source.examples.map((p) => h('li', {}, icon('file', 14), h('span', { class: 'mono ellipsis', title: p }, p),
        button({ icon: 'x', title: 'Tirar o exemplo', variant: 'ghost', size: 'sm', onClick: () => save(source.examples.filter((x) => x !== p)) }))))
      : null);
}
