// Painel Campos do editor de PDF (spec 037, RF-3720..3734, RF-3762): o que já foi ensinado, com nome, tipo,
// como encontrar, obrigatório, variações do rótulo, correção só neste documento e as regras de cada tabela.

import { api } from './api.js';
import { button, h } from './dom.js';
import { icon } from './icons.js';
import { chip, howText, showValue, slug } from './pdf_format.js';
import { toast, toastError } from './ui.js';

/** Clique em campo, lista, botão ou resumo do cartão não navega: só o resto do cartão leva ao documento. */
const isControl = (el) => Boolean(el.closest('input, select, textarea, button, summary, label, a, details[open] > :not(summary)'));

export function fieldCard(ctx, spec, f) {
  const { E, source, viewer, colorOf, change, setFocus, removeItem, uniqueName, drawFields, evaluateCurrent, runSample } = ctx;
  const c = colorOf(spec.nome);
  const best = f?.candidatos?.[0];
  const rename = (value) => {
    const next = slug(value.trim());
    if (!next || next === spec.nome) return drawFields();
    const fresh = uniqueName(next);
    E.colors[fresh] = E.colors[spec.nome];
    change(`renomear ${spec.nome} para ${fresh}`, (r) => { r.campos.find((x) => x.nome === spec.nome).nome = fresh; }, { sample: false });
    if (E.focus === spec.nome) E.focus = fresh;
  };
  const card = h('article', { class: ['pe-card', E.focus === spec.nome && 'active'], dataset: { field: spec.nome }, style: { '--c': c },
    title: best ? 'Clique para ver no documento' : '',
    onclick: (e) => { if (!isControl(e.target) && best && !f?.corrigido) viewer.reveal(best.origem, c); },
    onmouseenter: () => viewer.focusOwner(spec.nome), onmouseleave: () => viewer.focusOwner(E.focus) },
  h('div', { class: 'pe-card-head' },
    h('input', { class: 'pe-name', value: spec.nome, 'aria-label': 'Nome do campo', spellcheck: false, onchange: (e) => rename(e.target.value),
      onkeydown: (e) => { if (e.key === 'Enter') e.target.blur(); } }),
    f ? chip(f.estado, f.corrigido ? 'Corrigido' : undefined) : null,
    button({ icon: 'target', title: E.focus === spec.nome ? 'Tirar do foco' : 'Focar: mostrar na página e marcar outro rótulo', variant: 'ghost', size: 'sm',
      'aria-pressed': String(E.focus === spec.nome), onClick: () => setFocus(spec.nome) }),
    button({ icon: 'x', title: `Remover ${spec.nome}`, variant: 'ghost', size: 'sm', onClick: () => removeItem('campos', spec) })),
  h('div', { class: 'pe-value-row' },
    f?.estado === 'encontrado'
      ? h('button', { type: 'button', class: 'pe-value', title: 'Ver de onde veio', onclick: () => best && viewer.reveal(best.origem, c) }, showValue(f.valor, spec.tipo))
      : h('span', { class: 'pe-value none' }, f?.estado === 'ambiguo' ? 'nenhum valor escolhido' : f ? 'sem valor' : '—'),
    f?.texto ? h('span', { class: 'pe-orig' }, `no PDF: “${f.texto}”`) : null),
  h('div', { class: 'pe-how' },
    h('span', { class: 'pe-how-text' }, icon('search', 12), ' ', howText(spec.regra)),
    spec.regra.tipo === 'posicao' ? h('span', { class: 'pe-fragile', title: 'Se o layout mudar, o valor some ou vem errado. Marque o rótulo ao lado do valor e tecle R para trocar.' }, icon('alert', 11), ' frágil') : null),
  h('div', { class: 'pe-card-controls' },
    h('select', { class: 'input input-sm', 'aria-label': 'Tipo', onchange: (e) => change(`mudar o tipo de ${spec.nome}`, (r) => { r.campos.find((x) => x.nome === spec.nome).tipo = e.target.value; }) },
      Object.entries(E.tipos).map(([k, label]) => h('option', { value: k, selected: k === spec.tipo }, label))),
    spec.regra.tipo !== 'posicao' ? h('select', { class: 'input input-sm', 'aria-label': 'Onde fica o valor',
      onchange: (e) => change(`procurar ${spec.nome} ${e.target.value === 'direita' ? 'à direita' : 'abaixo'}`, (r) => { r.campos.find((x) => x.nome === spec.nome).regra.direcao = e.target.value; }) },
    h('option', { value: 'direita', selected: spec.regra.direcao === 'direita' }, 'à direita do rótulo'),
    h('option', { value: 'abaixo', selected: spec.regra.direcao === 'abaixo' }, 'abaixo do rótulo')) : null,
    h('label', { class: 'pe-check' }, h('input', { type: 'checkbox', checked: spec.obrigatorio,
      onchange: (e) => change(`${e.target.checked ? 'exigir' : 'não exigir'} ${spec.nome}`, (r) => { r.campos.find((x) => x.nome === spec.nome).obrigatorio = e.target.checked; }) }), ' obrigatório')));
if (spec.regra.tipo !== 'posicao') card.append(variations(ctx, spec));
if (f && f.estado === 'ambiguo') {
  card.append(h('p', { class: 'pe-why tone-warn' }, icon('alert', 12), ` ${f.motivo}: o Desata não escolhe sozinho.`),
    h('div', { class: 'pe-cands' }, f.candidatos.map((cd, i) => h('button', { type: 'button', class: 'pe-cand', onclick: () => { viewer.reveal(cd.origem, c); document.body.dataset.pdfGesture = 'ambiguo'; } }, `${i + 1} · ${cd.texto}`))),
    h('p', { class: 'field-help' }, 'Marque o rótulo certo no documento e tecle R, ou corrija só neste documento.'));
} else if (f && f.estado !== 'encontrado') {
  card.append(h('p', { class: 'pe-why tone-err' }, icon('alert', 12), ` ${f.motivo || ''}`));
}
const fix = f ? correctionBox(ctx, spec, f) : null;
if (fix) card.append(fix);
return card;
}

export function variations(ctx, spec) {
  const { E, source, viewer, colorOf, change, setFocus, removeItem, uniqueName, drawFields, evaluateCurrent, runSample } = ctx;
  const input = h('input', { class: 'input input-sm', placeholder: 'outro jeito de escrever o rótulo', 'aria-label': `Variação do rótulo de ${spec.nome}`,
    onkeydown: (e) => { if (e.key === 'Enter') add(); } });
  const add = () => {
    const text = input.value.trim();
    if (!text || spec.regra.rotulos.includes(text)) return;
    change(`aceitar “${text}” como rótulo de ${spec.nome}`, (r) => { r.campos.find((x) => x.nome === spec.nome).regra.rotulos.push(text); });
  };
  return h('details', { class: 'pe-more' }, h('summary', {}, `Rótulos aceitos (${spec.regra.rotulos.length})`),
    h('ul', { class: 'pe-labels' }, spec.regra.rotulos.map((label) => h('li', {}, h('span', {}, `“${label}”`),
      spec.regra.rotulos.length > 1 ? button({ icon: 'x', title: `Tirar “${label}”`, variant: 'ghost', size: 'sm',
        onClick: () => change(`tirar “${label}” de ${spec.nome}`, (r) => { const g = r.campos.find((x) => x.nome === spec.nome).regra; g.rotulos = g.rotulos.filter((x) => x !== label); }) }) : null))),
    h('div', { class: 'row' }, input, button({ icon: 'plus', label: 'Aceitar', size: 'sm', onClick: add })),
    h('p', { class: 'field-help' }, 'Maiúsculas, acentos e espaços a mais não contam.'));
}

/** RF-3762: corrigir só neste documento, sem mudar a regra, com registro de quem, quando e o valor de antes. */
export function correctionBox(ctx, spec, f) {
  const { E, source, viewer, colorOf, change, setFocus, removeItem, uniqueName, drawFields, evaluateCurrent, runSample } = ctx;
  const docInfo = E.docs.find((d) => d.key === E.doc);
  if (docInfo?.example) return null;
  if (f.corrigido) {
    const when = new Date(f.corrigido.em).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
    return h('p', { class: 'pe-fix-done' }, icon('edit', 12),
      ` Corrigido só neste documento por ${f.corrigido.por} em ${when}${f.corrigido.original ? `; o PDF dizia “${f.corrigido.original}”` : ''}. `,
      h('button', { type: 'button', class: 'link', onclick: async () => {
        await api.removePdfCorrection(source.id, f.corrigido.id).catch((err) => toastError(err, 'Não foi possível desfazer'));
        evaluateCurrent();
        runSample();
      } }, 'Desfazer correção'));
  }
  if (f.estado === 'encontrado') return null;
  const input = h('input', { class: 'input input-sm', placeholder: E.tipos[spec.tipo], 'aria-label': `Valor certo de ${spec.nome} neste documento` });
  const apply = async () => {
    if (!input.value.trim()) { input.focus(); return; }
    try {
      await api.addPdfCorrection(source.id, E.doc, spec.nome, input.value.trim());
      toast('Corrigido só neste documento', { kind: 'success', detail: 'A regra não muda. Se o PDF mudar, a correção deixa de valer.' });
      evaluateCurrent();
      runSample();
    } catch (err) {
      toastError(err, 'Não foi possível corrigir');
    }
  };
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter') apply(); });
  return h('details', { class: 'pe-more pe-fix' }, h('summary', {}, 'Corrigir só neste documento'),
    h('div', { class: 'row' }, input, button({ label: 'Corrigir', size: 'sm', variant: 'primary', onClick: apply })),
    h('p', { class: 'field-help' }, 'Fica registrado quem corrigiu, quando e o valor de antes. Vale só enquanto este PDF for o mesmo.'));
}

export function tableCard(ctx, spec, t) {
  const { E, source, viewer, colorOf, change, setFocus, removeItem, uniqueName, drawFields, evaluateCurrent, runSample } = ctx;
  const c = colorOf(spec.nome);
  const rows = t?.linhas || [];
  const doubts = rows.filter((x) => x.duvida).length;
  const edit = (label, fn, o) => change(label, (r) => fn(r.tabelas.find((x) => x.nome === spec.nome)), o);
  const columns = h('ul', { class: 'pe-cols' }, spec.colunas.map((col, k) => h('li', { class: 'pe-col' },
    h('input', { class: 'input input-sm mono', value: col.nome, 'aria-label': `Nome da coluna ${k + 1}`,
      onchange: (e) => {
        const next = slug(e.target.value) || col.nome;
        if (next === col.nome || spec.colunas.some((x) => x.nome === next)) { e.target.value = col.nome; return; }
        edit(`renomear a coluna ${col.nome}`, (tb) => {
          if (tb.coluna_inicio === col.nome) tb.coluna_inicio = next;
          tb.colunas[k].nome = next;
        }, { sample: false });
      } }),
    h('select', { class: 'input input-sm', 'aria-label': `Tipo da coluna ${col.nome}`, onchange: (e) => edit(`mudar o tipo de ${col.nome}`, (tb) => { tb.colunas[k].tipo = e.target.value; }) },
      Object.entries(E.tipos).map(([key, label]) => h('option', { value: key, selected: key === col.tipo }, label))),
    k < spec.colunas.length - 1 ? button({ icon: 'join', title: `Unir ${col.nome} com a próxima coluna`, variant: 'ghost', size: 'sm',
      onClick: () => edit(`unir ${col.nome} com ${spec.colunas[k + 1].nome}`, (tb) => {
        const gone = tb.colunas[k + 1].nome;
        tb.guias.splice(k, 1);
        tb.colunas.splice(k + 1, 1);
        if (tb.coluna_inicio === gone) tb.coluna_inicio = null;
      }) }) : null,
    button({ icon: 'split', title: `Separar ${col.nome} em duas colunas`, variant: 'ghost', size: 'sm',
      onClick: () => edit(`separar ${col.nome}`, (tb) => {
        const left = k === 0 ? tb.limites[0] : tb.guias[k - 1];
        const right = k === tb.colunas.length - 1 ? tb.limites[1] : tb.guias[k];
        tb.guias.splice(k, 0, Math.round(((left + right) / 2) * 10000) / 10000);
        let name = `${col.nome}_2`;
        let n = 3;
        while (tb.colunas.some((x) => x.nome === name)) name = `${col.nome}_${n++}`;
        tb.colunas.splice(k + 1, 0, { nome: name, tipo: 'texto' });
      }) }))));
  const startSelect = h('select', { class: 'input input-sm', 'aria-label': 'Quando começa uma linha nova',
    onchange: (e) => edit(e.target.value ? `nova linha quando ${e.target.value} tem valor` : 'cada linha do PDF é uma linha', (tb) => { tb.coluna_inicio = e.target.value || null; }) },
  h('option', { value: '', selected: !spec.coluna_inicio }, 'cada linha do PDF'),
  spec.colunas.map((col) => h('option', { value: col.nome, selected: col.nome === spec.coluna_inicio }, `“${col.nome}” tem valor`)));
  // RF-3733: a tabela começa na linha que tem estes textos, na ordem. Menos texto = vale para mais versões do layout.
  const headInput = h('input', { class: 'input input-sm', value: spec.cabecalho.join(', '), 'aria-label': 'Textos do cabeçalho da tabela',
    title: 'Separe por vírgula. Se o cabeçalho muda de um mês para outro, deixe só o que se repete.',
    onchange: (e) => {
      const parts = e.target.value.split(',').map((s) => s.trim()).filter(Boolean);
      if (!parts.length) { e.target.value = spec.cabecalho.join(', '); return; }
      edit('mudar onde a tabela começa', (tb) => { tb.cabecalho = parts; });
    } });
  // RF-3735: num texto, depois de N linhas (o corte da pessoa) ou no fim do documento; a borda de baixo faz o mesmo
  const endKind = spec.max_linhas ? 'linhas' : spec.fim.length ? 'texto' : 'documento';
  const endText = h('input', { class: 'input input-sm', value: spec.fim.join(', '), placeholder: 'ex.: Total geral', 'aria-label': 'Texto que encerra a tabela',
    hidden: endKind !== 'texto',
    onchange: (e) => edit('mudar onde a tabela termina', (tb) => { tb.fim = e.target.value.split(',').map((s) => s.trim()).filter(Boolean); tb.max_linhas = null; }) });
  const endCount = h('input', { class: 'input input-sm pe-end-n', type: 'number', min: 1, step: 1, value: spec.max_linhas || rows.length || 10, 'aria-label': 'Quantas linhas',
    hidden: endKind !== 'linhas',
    onchange: (e) => { const n = Math.max(1, Math.round(Number(e.target.value) || 1)); edit(`terminar depois de ${n} linhas`, (tb) => { tb.max_linhas = n; tb.fim = []; }); } });
  const endSelect = h('select', { class: 'input input-sm', 'aria-label': 'Onde a tabela termina',
    onchange: (e) => {
      const kind = e.target.value;
      if (kind === 'texto') { endText.hidden = false; endCount.hidden = true; endText.focus(); return; } // grava ao escrever
      if (kind === 'linhas') {
        const n = rows.length || 10;
        edit(`terminar depois de ${n} linhas`, (tb) => { tb.max_linhas = n; tb.fim = []; });
        return;
      }
      edit('ir até o fim do documento', (tb) => { tb.max_linhas = null; tb.fim = []; });
    } },
  h('option', { value: 'texto', selected: endKind === 'texto' }, 'num texto'),
  h('option', { value: 'linhas', selected: endKind === 'linhas' }, 'depois de N linhas'),
  h('option', { value: 'documento', selected: endKind === 'documento' }, 'no fim do documento'));
  const endInput = h('span', { class: 'pe-end' }, endSelect, endText, endCount);
  const suggestions = exclusionHints(ctx, spec, t);
  const firstCell = rows.flatMap((r) => Object.values(r.celulas)).find((cell) => cell.origem?.length);
  return h('article', { class: ['pe-card', 'pe-card-table', E.focus === spec.nome && 'active'], dataset: { table: spec.nome }, style: { '--c': c },
    title: firstCell ? 'Clique para ver a tabela no documento' : '',
    onclick: (e) => { if (!isControl(e.target) && firstCell) viewer.reveal(firstCell.origem, c); },
    onmouseenter: () => viewer.focusOwner(spec.nome), onmouseleave: () => viewer.focusOwner(E.focus) },
  h('div', { class: 'pe-card-head' },
    icon('table', 14),
    h('input', { class: 'pe-name', value: spec.nome, 'aria-label': 'Nome da tabela', spellcheck: false,
      onchange: (e) => {
        const next = slug(e.target.value);
        if (!next || next === spec.nome) return drawFields();
        const fresh = uniqueName(next);
        E.colors[fresh] = E.colors[spec.nome];
        edit(`renomear a tabela ${spec.nome}`, (tb) => { tb.nome = fresh; }, { sample: false });
      } }),
    t?.problema ? chip('falhou', 'Ajustar') : chip(doubts ? 'revisar' : 'aprovado', `${rows.length} linhas`),
    button({ icon: 'x', title: `Remover ${spec.nome}`, variant: 'ghost', size: 'sm', onClick: () => removeItem('tabelas', spec) })),
  t?.problema ? h('p', { class: 'pe-why tone-err' }, icon('alert', 12), ` ${t.problema}. Ajuste o cabeçalho, as guias ou onde termina; nenhuma linha é inventada.`) : null,
  h('div', { class: 'pe-table-rule' },
    h('label', {}, 'Começa em ', headInput),
    h('label', {}, 'Nova linha quando ', startSelect),
    h('label', {}, 'Termina em ', endInput),
    h('label', { class: 'pe-check' }, h('input', { type: 'checkbox', checked: spec.continua,
      onchange: (e) => edit(e.target.checked ? 'seguir nas páginas seguintes' : 'ficar só na página do cabeçalho', (tb) => { tb.continua = e.target.checked; }) }), ' continua nas páginas seguintes')),
  h('details', { class: 'pe-more', open: spec.colunas.length <= 4 }, h('summary', {}, `Colunas (${spec.colunas.length})`), columns,
    h('p', { class: 'field-help' }, 'Arraste as guias tracejadas na página, ou foque uma guia e use as setas. As bordas da caixa da tabela também se arrastam: a de cima escolhe o cabeçalho, a de baixo onde termina.')),
  spec.excluir.length ? h('div', { class: 'pe-excl' }, h('span', { class: 'field-help' }, 'Linhas excluídas:'),
    spec.excluir.map((x) => h('span', { class: 'pe-tag' }, `começa com “${x}”`,
      button({ icon: 'x', title: 'Voltar a incluir', variant: 'ghost', size: 'sm', onClick: () => edit(`voltar a incluir “${x}”`, (tb) => { tb.excluir = tb.excluir.filter((y) => y !== x); }) })))) : null,
  suggestions.length ? h('div', { class: 'pe-suggest' }, icon('info', 12),
    h('span', {}, `Parece subtotal ou rodapé: ${suggestions.map((s) => `“${s}”`).join(', ')}. Excluir essas linhas?`),
    button({ label: 'Excluir', size: 'sm', onClick: () => edit(`excluir linhas ${suggestions.join(', ')}`, (tb) => { tb.excluir = [...new Set([...tb.excluir, ...suggestions])]; }) })) : null);
}

/** RF-3732: sugere (nunca exclui sozinho) linhas que parecem subtotal, total ou rodapé. */
export function exclusionHints(ctx, spec, t) {
  const { E, source, viewer, colorOf, change, setFocus, removeItem, uniqueName, drawFields, evaluateCurrent, runSample } = ctx;
  if (!t) return [];
  const hint = /^(sub-?total|total|totais|soma|p[aá]gina|continua)/i;
  const first = spec.colunas[0]?.nome;
  const found = new Set();
  for (const row of t.linhas) {
    const text = String(row.celulas[first]?.texto || '').trim();
    const m = text.match(hint);
    if (m) found.add(text.split(/\s+/).slice(0, 2).join(' '));
  }
  return [...found].filter((x) => !spec.excluir.includes(x) && !spec.fim.includes(x)).slice(0, 3);
}
