// Formato de exibição da coluna no programa (spec 050): o formato que vale numa caixa (com a herança das anteriores),
// o diálogo do menu da coluna no Resultado e a receita Criar coluna de texto. Formatar fica em col_format.js, que
// também vai no HTML exportado.

import { addNode, connect } from './actions.js';
import { isAreaFree } from './canvas.js';
import { compact, DATE_PATTERNS, DEFAULTS, describe, effectiveFormats, formatValue, kindsFor, MASKS, SYMBOLS, UNSAFE } from './col_format.js';
import { button, fmt, h } from './dom.js';
import { icon } from './icons.js';
import { mutate, node, store } from './store.js';
import { openDialog, toast } from './ui.js';

/** Formatos que valem na caixa, cada um com `from` (onde foi definido). */
export function nodeFormats(nodeId) {
  const wf = store.workflow;
  if (!wf || !nodeId) return {};
  const ports = (type) => (store.tools[type]?.inputs || []).map((p) => p.id);
  return effectiveFormats(wf.column_formats || {}, wf.nodes, wf.edges, nodeId, ports);
}

/** De onde veio: "definido em Vendas do mês" (RF-5013). */
export function originText(spec, nodeId) {
  if (!spec?.from || spec.from === nodeId) return 'definido nesta caixa';
  const n = node(spec.from);
  return `definido em ${n?.label || n?.type || spec.from}`;
}

const KINDS = {
  none: { label: 'Sem formato', icon: 'x', example: 'como veio' },
  number: { label: 'Número', icon: 'hash', example: '1.234,50' },
  currency: { label: 'Moeda', icon: 'currency', example: 'R$ 1.234,50' },
  percent: { label: 'Porcentagem', icon: 'percent', example: '15%' },
  document: { label: 'Documento', icon: 'fingerprint', example: '123.456.789-01' },
  date: { label: 'Data', icon: 'calendar', example: '26/11/2026' },
};

/** Grava o formato (ou tira). Um Desfazer volta (RF-5007). */
function save(nodeId, column, spec, inherited) {
  mutate((wf) => {
    const all = { ...(wf.column_formats || {}) };
    const own = { ...(all[nodeId] || {}) };
    if (spec.kind === 'none' && !inherited) delete own[column];
    else own[column] = compact(spec);
    if (Object.keys(own).length) all[nodeId] = own;
    else delete all[nodeId];
    wf.column_formats = all;
  });
}

// ------------------------------------------------------------------ receita (RF-5041)

const quote = (s) => `'${String(s).replace(/'/g, "''")}'`;

/** Regex e substituição de uma máscara com #: "###.###" → ^(\d{3})(\d{3})$ e \1.\2 */
function maskRegex(mask) {
  const groups = [];
  let replace = '';
  for (const run of mask.match(/#+|[^#]+/g) || []) {
    if (run[0] === '#') { groups.push(run.length); replace += `\\${groups.length}`; } else replace += run;
  }
  return { pattern: `^${groups.map((n) => `(\\d{${n}})`).join('')}$`, replace, size: groups.reduce((a, b) => a + b, 0) };
}

/** Expressão da Formula que dá o mesmo texto da tela (com os separadores do padrão brasileiro). */
export function textFormula(spec, column, type) {
  const c = `[${column}]`;
  const d = spec.decimals ?? DEFAULTS.decimals;
  switch (spec.kind) {
    case 'number':
      return spec.thousands === false ? `Replace(FormatNumber(${c}, ${d}), '.', '')` : `FormatNumber(${c}, ${d})`;
    case 'currency': {
      const s = spec.symbol ? `${spec.symbol} ` : '';
      return `IF ${c} < 0 THEN Concat(${quote(`-${s}`)}, FormatNumber(Abs(${c}), ${d})) ELSE Concat(${quote(s)}, FormatNumber(${c}, ${d})) ENDIF`;
    }
    case 'percent':
      return `Concat(FormatNumber(${spec.base === 'hundred' ? c : `${c} * 100`}, ${d}), '%')`;
    case 'date': {
      if (spec.pattern === 'long') {
        return `Concat(ToString(Day(${c})), ' de ', Substring('jan.fev.mar.abr.mai.jun.jul.ago.set.out.nov.dez.', (Month(${c}) - 1) * 4 + 1, 4), ' de ', ToString(Year(${c})))`;
      }
      const f = { dmy: '%d/%m/%Y', my: '%m/%Y', dmy_hm: '%d/%m/%Y %H:%M', iso: '%Y-%m-%d' }[spec.pattern || 'dmy'];
      return `DateFormat(${c}, '${f}')`;
    }
    case 'document': {
      const digits = type === 'String' ? `DigitsOnly(${c})` : `ToString(ToInteger(${c}))`;
      const branch = (mask, last) => {
        const { pattern, replace, size } = maskRegex(mask);
        const value = type === 'String' ? digits : `PadLeft(${digits}, ${size}, '0')`;
        return { test: `RegexMatch(${value}, '${pattern}')`, out: `RegexReplace(${value}, '${pattern}', '${replace}')`, last };
      };
      const masks = spec.mask === 'phone' ? ['(##) ####-####', '(##) #####-####'] : [MASKS[spec.mask] || spec.mask];
      // número de telefone com zero à esquerda não existe: só o texto completa a máscara de 10 ou 11 dígitos
      const parts = masks.map((m) => branch(m));
      const whens = parts.map((p, i) => `${i ? 'ELSEIF' : 'IF'} ${p.test} THEN ${p.out}`).join(' ');
      return `${whens} ELSE ToString(${c}) ENDIF`;
    }
    default:
      return '';
  }
}

function insertTextColumn(nodeId, port, column, spec, type) {
  const source = node(nodeId);
  if (!source) return;
  const x = source.x + 248;
  let y = source.y + 110;
  for (let i = 0; i < 30 && !isAreaFree(x, y); i += 1) y += 30;
  const expression = textFormula(spec, column, type);
  const created = addNode('prep.formula', x, y, {
    formulas: [{ target: 'new', column: `${column}_texto`, type: 'String', expression }],
    __label: `${column} como texto`,
  });
  if (created && connect(nodeId, port, created.id, 'in')) {
    toast(`Coluna ${column}_texto criada numa Formula`, { kind: 'success', detail: 'A coluna original ficou como está. Ctrl+Z desfaz.' });
  }
}

// ------------------------------------------------------------------ diálogo (RF-5001..5007, RF-5032)

const field = (label, control, help) => h('label', { class: 'field' }, h('span', { class: 'field-label' }, label), control,
  help ? h('span', { class: 'field-help' }, help) : null);

/**
 * Formato de exibição de uma coluna. `column`: a coluna do perfil ({ name, type }); `rows`: as linhas da página
 * aberta, para a prévia; `port`: a saída inspecionada; `onDone`: redesenhar o Resultado.
 */
export function openFormatDialog({ nodeId, port = 'out', column, rows = [], onDone }) {
  const current = nodeFormats(nodeId)[column.name] || null;
  const own = store.workflow.column_formats?.[nodeId]?.[column.name] || null;
  const inheritedFrom = current && current.from !== nodeId ? current : null;
  const kinds = ['none', ...kindsFor(column.type)];
  // Sugestão inicial: número e data começam no primeiro formato que cabe; texto começa sem formato (aplicar Documento
  // sem olhar marcaria tudo como "não cabe"), a não ser que o nome diga que é documento.
  const looksLikeDocument = /cpf|cnpj|cep|telefone|celular|fone/i.test(column.name);
  const first = column.type === 'String' && !looksLikeDocument ? 'none' : kinds[1] || 'none';
  let spec = { ...DEFAULTS, ...(current || { kind: own?.kind === 'none' ? 'none' : first }) };
  if ((column.type === 'Int64' || column.type === 'String') && !current && looksLikeDocument) {
    spec = { ...spec, kind: 'document', mask: /cnpj/i.test(column.name) ? 'cnpj' : /cep/i.test(column.name) ? 'cep' : /fone|cel/i.test(column.name) ? 'phone' : 'cpf' };
  }
  if (!kinds.includes(spec.kind)) spec.kind = 'none';
  const samples = [...new Set(rows.map((r) => r[column.name]).filter((v) => v !== null && v !== undefined).map((v) => JSON.stringify(v)))]
    .slice(0, 50).map((v) => JSON.parse(v));

  const kindRow = h('div', { class: 'cf-kinds', role: 'radiogroup', 'aria-label': 'Tipo de formato' });
  const options = h('div', { class: 'cf-options' });
  const preview = h('div', { class: 'cf-preview' });
  const scheme = h('div', { class: 'cf-scheme', 'aria-label': 'Como funciona' });
  const errorEl = h('p', { class: 'field-error', hidden: true });

  const set = (patch) => { spec = { ...spec, ...patch }; draw(); };
  const valid = () => {
    if (spec.kind === 'currency' && (UNSAFE.test(spec.symbol || '') || (spec.symbol || '').length > 6)) return 'Símbolo com até 6 caracteres, sem aspas nem < >.';
    if (spec.kind === 'document' && !(spec.mask in MASKS) && spec.mask !== 'phone') {
      if (!spec.mask.includes('#')) return 'A máscara precisa de pelo menos um # (um dígito).';
      if (UNSAFE.test(spec.mask) || spec.mask.length > 40) return 'Máscara com até 40 caracteres, sem aspas nem < >.';
    }
    return null;
  };

  function drawKinds() {
    kindRow.replaceChildren(...kinds.map((k) => h('button', {
      type: 'button', role: 'radio', class: ['cf-kind', spec.kind === k && 'on'], 'aria-checked': String(spec.kind === k),
      dataset: { kind: k }, onclick: () => set({ kind: k }),
    }, icon(KINDS[k].icon, 16), h('b', {}, KINDS[k].label), h('span', { class: 'muted' }, KINDS[k].example))));
  }

  function drawOptions() {
    const decimals = () => field('Casas decimais', h('input', { class: 'input', type: 'number', min: 0, max: 6, value: spec.decimals,
      'aria-label': 'Casas decimais', oninput: (e) => { const n = Math.max(0, Math.min(6, Number(e.target.value) || 0)); spec.decimals = n; drawPreview(); } }));
    const parts = {
      none: () => [h('p', { class: 'field-help' }, inheritedFrom ? `Tira o formato herdado (${describe(inheritedFrom)}, ${originText(inheritedFrom, nodeId)}) desta caixa em diante.` : 'A coluna aparece como o motor entrega.')],
      number: () => [decimals(), h('label', { class: 'check' }, h('input', { type: 'checkbox', checked: spec.thousands !== false, onchange: (e) => set({ thousands: e.target.checked }) }), ' Separador de milhar')],
      currency: () => {
        const other = !SYMBOLS.includes(spec.symbol);
        const input = h('input', { class: 'input', value: other ? spec.symbol : '', maxlength: 6, placeholder: 'Ex.: CHF', 'aria-label': 'Outro símbolo', hidden: !other,
          oninput: (e) => { spec.symbol = e.target.value; drawPreview(); } });
        return [field('Moeda', h('div', { class: 'cf-inline' }, h('select', { class: 'input', 'aria-label': 'Moeda', onchange: (e) => set({ symbol: e.target.value === '*' ? '' : e.target.value }) },
          SYMBOLS.map((s) => h('option', { value: s, selected: !other && spec.symbol === s }, s)), h('option', { value: '*', selected: other }, 'Outro…')), input)), decimals()];
      },
      percent: () => [decimals(), field('O valor guardado é', h('select', { class: 'input', 'aria-label': 'Base da porcentagem', onchange: (e) => set({ base: e.target.value }) },
        h('option', { value: 'fraction', selected: spec.base !== 'hundred' }, 'Fração: 0,15 vira 15%'),
        h('option', { value: 'hundred', selected: spec.base === 'hundred' }, 'Já em pontos: 15 vira 15%')))],
      document: () => {
        const free = !(spec.mask in MASKS) && spec.mask !== 'phone';
        return [field('Documento', h('select', { class: 'input', 'aria-label': 'Documento', onchange: (e) => set({ mask: e.target.value === '*' ? '###-###' : e.target.value }) },
          h('option', { value: 'cpf', selected: spec.mask === 'cpf' }, 'CPF · 000.000.000-00'), h('option', { value: 'cnpj', selected: spec.mask === 'cnpj' }, 'CNPJ · 00.000.000/0000-00'),
          h('option', { value: 'cep', selected: spec.mask === 'cep' }, 'CEP · 00000-000'), h('option', { value: 'phone', selected: spec.mask === 'phone' }, 'Telefone · (00) 00000-0000'),
          h('option', { value: '*', selected: free }, 'Máscara livre…'))),
        free ? field('Máscara', h('input', { class: 'input mono', value: spec.mask, maxlength: 40, 'aria-label': 'Máscara', oninput: (e) => { spec.mask = e.target.value; drawPreview(); } }),
          'Cada # é um dígito; o resto aparece como está. Ex.: ###.###-#') : null,
        column.type === 'Int64' ? h('p', { class: 'field-help' }, 'Guardado como número, o zero à esquerda volta na tela.') : null];
      },
      date: () => [field('Como mostrar', h('select', { class: 'input', 'aria-label': 'Formato da data', onchange: (e) => set({ pattern: e.target.value }) },
        Object.entries(DATE_PATTERNS).map(([k, label]) => h('option', { value: k, selected: spec.pattern === k }, label))))],
    };
    options.replaceChildren(...(parts[spec.kind] || parts.none)().filter(Boolean));
  }

  function drawPreview() {
    const problem = valid();
    errorEl.hidden = !problem;
    errorEl.textContent = problem || '';
    apply.disabled = Boolean(problem);
    textBtn.disabled = Boolean(problem) || spec.kind === 'none';
    const shown = samples.slice(0, 6);
    const results = samples.map((v) => (spec.kind === 'none' ? null : formatValue(spec, v)));
    const bad = results.filter((r) => r?.bad).length;
    preview.replaceChildren(
      h('table', { class: 'data-table compact cf-table' },
        h('thead', {}, h('tr', {}, h('th', {}, 'Como está'), h('th', {}, 'Como fica'))),
        h('tbody', {}, shown.length ? shown.map((v, i) => {
          const r = results[i];
          return h('tr', {}, h('td', { class: 'mono' }, String(v)),
            h('td', { class: [r?.bad && 'fmt-bad'], title: r?.bad || null }, r ? r.text : String(v), r?.bad ? h('span', { class: 'cf-why' }, ` ${r.bad}`) : null));
        }) : h('tr', {}, h('td', { colspan: 2, class: 'muted' }, 'Sem valores na página aberta.')))),
      h('p', { class: ['field-help', bad && 'cf-warn'] }, bad
        ? `${fmt.int(bad)} de ${fmt.int(samples.length)} valores da página não cabem: aparecem como estão, marcados.`
        : samples.length ? `${fmt.int(samples.length)} ${samples.length === 1 ? 'valor conferido' : 'valores conferidos'} da página aberta.` : ''));
    const first = samples.find((v, i) => !results[i]?.bad) ?? samples[0];
    const after = first === undefined ? '—' : spec.kind === 'none' ? String(first) : formatValue(spec, first)?.text ?? String(first);
    scheme.replaceChildren(
      h('div', { class: 'cf-step' }, h('span', { class: 'muted' }, 'Guardado'), h('b', { class: 'mono' }, first === undefined ? '—' : String(first))),
      icon('chevron-right', 16),
      h('div', { class: 'cf-step cf-step-fmt' }, h('span', { class: 'muted' }, 'Formato'), h('b', {}, spec.kind === 'none' ? 'nenhum' : describe(spec))),
      icon('chevron-right', 16),
      h('div', { class: 'cf-step' }, h('span', { class: 'muted' }, 'Na tela'), h('b', {}, after)));
  }

  function draw() { drawKinds(); drawOptions(); drawPreview(); }

  const apply = button({ label: 'Aplicar', variant: 'primary', onClick: () => {
    if (valid()) return;
    save(nodeId, column.name, spec, Boolean(inheritedFrom));
    dlg.close();
    onDone?.();
  } });
  const textBtn = button({ label: 'Criar coluna de texto…', icon: 'function', variant: 'ghost', title: 'Uma Formula com o texto formatado, para gravar no CSV', onClick: () => openTextRecipe() });
  function openTextRecipe() {
    const expression = textFormula(spec, column.name, column.type);
    const box = openDialog({
      title: 'Criar coluna de texto', size: 'md',
      body: h('div', { class: 'stack-sm' },
        h('p', {}, `Uma caixa Formula entra logo depois desta e cria `, h('code', {}, `${column.name}_texto`), ' com o texto formatado. A coluna original fica como está.'),
        h('pre', { class: 'cf-expr mono' }, expression),
        h('p', { class: 'field-help' }, 'Dá para abrir a Formula e mudar a expressão. O texto usa o padrão brasileiro (1.234,56).')),
      actions: [button({ label: 'Cancelar', onClick: () => box.close() }),
        button({ label: 'Criar a Formula', variant: 'primary', onClick: () => { box.close(); dlg.close(); insertTextColumn(nodeId, port, column.name, spec, column.type); } })],
    });
  }

  const dlg = openDialog({
    title: `Formato de exibição · ${column.name}`,
    size: 'lg',
    body: h('div', { class: 'cf-dialog' },
      h('div', { class: 'cf-left' }, kindRow, options, errorEl),
      h('div', { class: 'cf-right' }, preview),
      h('div', { class: 'cf-foot' }, scheme,
        h('p', { class: 'field-help' }, icon('info', 12), ` O dado não muda: contas, filtros e o CSV usam o valor guardado. Vale nesta caixa e nas seguintes enquanto a coluna se chamar `,
          h('code', {}, column.name), '.', inheritedFrom ? ` Hoje: ${describe(inheritedFrom)}, ${originText(inheritedFrom, nodeId)}.` : ''))),
    actions: [textBtn, h('span', { class: 'grow' }), button({ label: 'Cancelar', onClick: () => dlg.close() }), apply],
  });
  draw();
  return dlg;
}
