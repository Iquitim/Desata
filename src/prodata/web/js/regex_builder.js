// Regex sem escrever expressão regular (spec 039): marcar o trecho num valor de verdade, ajustar as peças e ver,
// ao vivo, onde casa. A tabela de peças vem do catálogo (nodes/regex_pieces.py) e o padrão é montado do mesmo
// jeito que no motor, para a prévia bater com a execução. A expressão escrita à mão continua no Avançado.

import { button, fmt, h } from './dom.js';
import { icon } from './icons.js';

const SPECIAL = new Set('\\.^$|?*+()[]{}');
const escape = (text) => [...text].map((c) => (SPECIAL.has(c) ? `\\${c}` : c)).join('');
const COLORS = 6; // cores das colunas novas (rx-c0 … rx-c5)
const SHOWN = 8;

function pieceRegex(p, cat) {
  const spec = cat[p.kind] || cat.literal;
  let part;
  if (p.kind === 'literal') part = escape(p.text || '');
  else if (spec.repeat) part = spec.base + (p.count == null ? '+' : p.count === 1 ? '' : `{${p.count}}`);
  else if (spec.ready && spec.base.includes('|')) part = `(?:${spec.base})`;
  else part = spec.base;
  return p.take ? `(${part})` : part;
}

/** O mesmo padrão de ``pattern_of`` no Python. */
export const patternOf = (pieces, cat) => pieces.map((p) => pieceRegex(p, cat)).join('');

export function namesOf(pieces, whole = '') {
  const taken = pieces.filter((p) => p.take);
  if (!taken.length) return pieces.length ? [whole.trim() || 'trecho'] : [];
  return taken.map((p, i) => (p.name || '').trim() || `grupo_${i + 1}`);
}

const LITERAL_NAMES = { '/': 'uma barra', '-': 'um hífen', '.': 'um ponto', ',': 'uma vírgula', ' ': 'um espaço', ':': 'dois-pontos', '(': 'um parêntese', ')': 'um parêntese' };

/** A peça em português: "2 dígitos", "uma barra", "um CPF". */
export function sayPiece(p, cat) {
  const spec = cat[p.kind] || {};
  if (p.kind === 'literal') return LITERAL_NAMES[p.text] || `“${p.text || ''}”`;
  if (spec.repeat) {
    const [one, many] = spec.unit;
    if (p.count == null) return { digits: 'um número', word: 'uma palavra', alnum: 'letras e números', space: 'espaços' }[p.kind];
    return `${p.count} ${p.count === 1 ? one : many}`;
  }
  return spec.say || spec.label || p.kind;
}

/** Peças que descrevem o trecho marcado: uma peça pronta, se ele é inteiro uma; senão números, espaços e texto fixo. */
export function infer(text, cat) {
  for (const kind of ['email', 'cnpj', 'cpf', 'date', 'phone', 'cep', 'decimal']) {
    if (cat[kind] && new RegExp(`^(?:${cat[kind].base})$`, 'u').test(text)) return [{ kind, take: false, name: '', text: '', count: null }];
  }
  const out = [];
  for (const m of text.matchAll(/(\d+)|(\s+)|([^\d\s]+)/gu)) {
    if (m[1]) out.push({ kind: 'digits', count: m[1].length, take: false, name: '', text: '' });
    else if (m[2]) out.push({ kind: 'space', count: null, take: false, name: '', text: '' });
    else out.push({ kind: 'literal', text: m[3], take: false, name: '', count: null });
  }
  return out;
}

function compile(pattern, ignoreCase) {
  if (!pattern) return null;
  try { return new RegExp(pattern, ignoreCase ? 'diu' : 'du'); } catch { return null; }
}

/** O valor com o trecho que casou destacado; cada coluna nova com a sua cor. */
function sample(value, re) {
  const m = re ? re.exec(value) : null;
  if (!m) return { el: h('span', { class: 'rx-text' }, value), hit: false };
  const [start, end] = m.indices[0];
  const groups = (m.indices.slice(1) || []).map((g, i) => (g ? { s: g[0], e: g[1], c: i % COLORS } : null)).filter(Boolean);
  const inner = [];
  let at = start;
  for (const g of groups) {
    if (g.s < at) continue;
    if (g.s > at) inner.push(value.slice(at, g.s));
    inner.push(h('mark', { class: `rx-g rx-c${g.c}` }, value.slice(g.s, g.e)));
    at = g.e;
  }
  if (at < end) inner.push(value.slice(at, end));
  return { el: h('span', { class: 'rx-text' }, value.slice(0, start), h('mark', { class: 'rx-hit' }, ...inner), value.slice(end)), hit: true };
}

// estado só da tela (qual peça está aberta, se a paleta está à vista), preservado entre redesenhos do formulário
const ui = { open: null, palette: false };

export function regexBuilder(field, value, set, ctx, _id, values = {}) {
  const cat = field.catalog;
  const pieces = Array.isArray(value) ? value : [];
  const mode = values.mode || 'extract';
  const generated = patternOf(pieces, cat);
  const handWritten = Boolean(values.pattern) && (!pieces.length || values.pattern !== generated);
  const pattern = handWritten ? values.pattern : generated;
  const re = compile(pattern, values.ignore_case);

  const commit = (next, whole = (values.names || [])[0] || '') => {
    ctx.update('pattern', patternOf(next, cat));
    if (mode === 'extract') ctx.update('names', namesOf(next, whole));
    set(next.map((p) => ({ ...p })));
  };
  const change = (i, patch) => commit(pieces.map((p, j) => (j === i ? { ...p, ...patch } : p)));

  const root = h('div', { class: 'rx' });
  if (handWritten && pieces.length) {
    root.append(h('div', { class: 'rx-banner' }, icon('alert', 14),
      h('span', {}, 'A expressão foi editada à mão no Avançado e não bate mais com as peças.'),
      button({ label: 'Voltar às peças', size: 'sm', onClick: () => commit(pieces) }),
      button({ label: 'Ficar com a expressão', size: 'sm', variant: 'ghost', onClick: () => set([]) })));
  } else if (handWritten) {
    root.append(h('p', { class: 'field-help rx-note' }, icon('info', 13),
      ' Esta caixa usa uma expressão escrita à mão (veja Avançado). Para montar por peças, marque um trecho num exemplo abaixo.'));
  }

  // 1. exemplos da coluna, selecionáveis
  const samples = h('div', { class: 'rx-samples' }, h('p', { class: 'muted' }, 'Lendo os valores…'));
  const tally = h('p', { class: 'field-help rx-tally' });
  root.append(h('div', { class: 'rx-step' },
    h('span', { class: 'field-label' }, values.column ? `Exemplos de [${values.column}]` : 'Exemplos da coluna'),
    h('p', { class: 'field-help' }, icon('pointer', 12), ' Selecione com o mouse o trecho que você quer, num dos exemplos.'),
    samples, tally));
  const pick = (e) => {
    const sel = window.getSelection();
    const text = sel?.toString() || '';
    if (!text.trim() || !e.currentTarget.contains(sel.anchorNode)) return;
    sel.removeAllRanges();
    ui.open = null;
    commit(infer(text, cat), '');
  };
  const fillSamples = (list) => {
    if (!list.length) { samples.replaceChildren(h('p', { class: 'muted' }, 'A coluna não tem valores de texto.')); return; }
    let hit = 0;
    let total = 0;
    const misses = [];
    for (const v of list) {
      total += v.count;
      if (re && re.test(v.value)) hit += v.count; else if (misses.length < 3) misses.push(v.value);
    }
    samples.replaceChildren(...list.slice(0, SHOWN).map((v) => {
      const s = sample(v.value, re);
      return h('div', { class: ['rx-sample', s.hit && 'hit', pattern && !s.hit && 'miss'], onmouseup: pick, title: 'Selecione o trecho que você quer' },
        h('span', { class: 'rx-mark' }, pattern ? icon(s.hit ? 'check' : 'x', 12) : null), s.el);
    }));
    tally.replaceChildren(...(pattern && re ? [
      h('b', {}, `Tem o trecho em ${fmt.int(hit)} de ${fmt.int(total)} linhas`),
      list.length >= 500 ? ' (nos 500 valores mais frequentes)' : '',
      misses.length ? h('span', { class: 'muted' }, ` · sem o trecho: ${misses.map((m) => `“${m.length > 30 ? `${m.slice(0, 30)}…` : m}”`).join(', ')}`) : null,
    ] : pattern ? [h('span', { class: 'text-error' }, 'A expressão não é válida aqui: confira no Avançado.')] : []).filter((x) => x !== ''));
  };
  if (!values.column) samples.replaceChildren(h('p', { class: 'muted' }, 'Escolha a coluna para ver os exemplos.'));
  else {
    ctx.values?.(values.column)
      .then((data) => fillSamples((data.values || []).filter((v) => v.value !== null && v.value !== '').map((v) => ({ value: String(v.value), count: v.count }))))
      .catch(() => samples.replaceChildren(h('p', { class: 'muted' }, 'Execute o fluxo para ver exemplos da coluna. Enquanto isso, escolha peças nos cartões.')));
  }

  // 2. o trecho, peça por peça
  const say = pieces.map((p) => sayPiece(p, cat)).join(', ');
  const chips = pieces.map((p, i) => {
    const taken = pieces.slice(0, i).filter((x) => x.take).length;
    return h('button', {
      type: 'button', class: ['rx-chip', p.take && `rx-c${taken % COLORS}`, ui.open === i && 'open'], 'aria-expanded': String(ui.open === i),
      title: 'Ajustar esta peça', onclick: () => { ui.open = ui.open === i ? null : i; ui.palette = false; set(pieces.map((x) => ({ ...x }))); },
    }, icon((cat[p.kind] || {}).icon || 'edit', 12), h('span', {}, sayPiece(p, cat)), p.take && mode === 'extract' ? h('small', {}, `→ ${(p.name || '').trim() || `grupo_${taken + 1}`}`) : null);
  });
  root.append(h('div', { class: 'rx-step' },
    h('span', { class: 'field-label' }, 'O trecho, peça por peça'),
    pieces.length ? h('p', { class: 'rx-say' }, h('b', {}, 'Procura: '), say) : h('p', { class: 'field-help' }, 'Marque um trecho num exemplo, ou monte com as peças.'),
    h('div', { class: 'rx-chips' }, ...chips,
      button({ icon: 'plus', label: pieces.length ? 'Peça' : 'Adicionar peça', size: 'sm', variant: 'ghost', 'aria-expanded': String(ui.palette),
        onClick: () => { ui.palette = !ui.palette; ui.open = null; set(pieces.map((x) => ({ ...x }))); } })),
    ui.palette ? palette(cat, (kind) => { ui.palette = false; commit([...pieces, { kind, take: false, name: '', text: kind === 'literal' ? '-' : '', count: cat[kind].repeat ? null : null }]); }) : null,
    ui.open !== null && pieces[ui.open] ? editor(pieces[ui.open], ui.open, pieces, cat, mode, change, commit) : null,
    mode === 'extract' && pieces.length && !pieces.some((p) => p.take)
      ? h('label', { class: 'rx-whole' }, 'Nome da coluna nova',
        h('input', { class: 'input input-sm', value: (values.names || [])[0] || 'trecho', onchange: (e) => commit(pieces, e.target.value) }),
        h('small', { class: 'field-help' }, 'O trecho inteiro vira esta coluna. Para separar em várias, abra uma peça e marque “Vira coluna”.'))
      : null,
    mode === 'replace' && pieces.some((p) => p.take) ? insertButtons(pieces, cat, ctx, values) : null));
  return root;
}

function palette(cat, add) {
  const card = (kind) => h('button', { type: 'button', class: 'rx-card', onclick: () => add(kind), title: `Adicionar: ${cat[kind].label}` },
    h('span', { class: 'rx-card-head' }, icon(cat[kind].icon || 'plus', 13), h('b', {}, cat[kind].label)),
    cat[kind].example ? h('small', { class: 'mono' }, cat[kind].example) : h('small', {}, cat[kind].say || (cat[kind].repeat ? 'quantos houver' : 'o texto que você escrever')));
  const ready = Object.keys(cat).filter((k) => cat[k].ready);
  const basic = Object.keys(cat).filter((k) => !cat[k].ready);
  return h('div', { class: 'rx-palette' },
    h('span', { class: 'field-label' }, 'Prontas'), h('div', { class: 'rx-cards' }, ready.map(card)),
    h('span', { class: 'field-label' }, 'Para montar'), h('div', { class: 'rx-cards' }, basic.map(card)));
}

function editor(p, i, pieces, cat, mode, change, commit) {
  const spec = cat[p.kind] || {};
  const move = (d) => { const next = [...pieces]; [next[i], next[i + d]] = [next[i + d], next[i]]; ui.open = i + d; commit(next); };
  return h('div', { class: 'rx-editor' },
    h('div', { class: 'rx-editor-row' },
      h('select', { class: 'input input-sm', 'aria-label': 'Tipo da peça', onchange: (e) => change(i, { kind: e.target.value, count: null, text: e.target.value === 'literal' ? p.text || '-' : '' }) },
        Object.entries(cat).map(([k, s]) => h('option', { value: k, selected: k === p.kind }, s.label))),
      i > 0 ? button({ icon: 'chevron-left', title: 'Mover para a esquerda', size: 'sm', variant: 'ghost', onClick: () => move(-1) }) : null,
      i < pieces.length - 1 ? button({ icon: 'chevron-right', title: 'Mover para a direita', size: 'sm', variant: 'ghost', onClick: () => move(1) }) : null,
      button({ icon: 'trash', title: 'Tirar esta peça', size: 'sm', variant: 'ghost', onClick: () => { ui.open = null; commit(pieces.filter((_, j) => j !== i)); } })),
    p.kind === 'literal'
      ? h('label', { class: 'rx-editor-row' }, 'Texto', h('input', { class: 'input input-sm', value: p.text || '', onchange: (e) => change(i, { text: e.target.value }) }))
      : null,
    spec.repeat
      ? h('label', { class: 'rx-editor-row' }, 'Quantos',
        h('select', { class: 'input input-sm', onchange: (e) => change(i, { count: e.target.value === 'any' ? null : Number(e.target.value) }) },
          h('option', { value: 'any', selected: p.count == null }, `quantos houver (1 ou mais ${spec.unit[1]})`),
          ...Array.from({ length: 12 }, (_, k) => k + 1).map((n) => h('option', { value: n, selected: p.count === n }, `exatamente ${n}`)),
          p.count > 12 ? h('option', { value: p.count, selected: true }, `exatamente ${p.count}`) : null))
      : null,
    mode === 'extract' || mode === 'replace'
      ? h('label', { class: 'rx-editor-row pe-check' },
        h('input', { type: 'checkbox', checked: Boolean(p.take), onchange: (e) => change(i, { take: e.target.checked }) }),
        mode === 'extract' ? ' Vira coluna' : ' Guardar para usar no texto novo',
        p.take && mode === 'extract' ? h('input', { class: 'input input-sm', placeholder: 'nome da coluna', 'aria-label': 'Nome da coluna', value: p.name || '', onchange: (e) => change(i, { name: e.target.value }) }) : null)
      : null);
}

/** Trocar: insere as peças guardadas no texto novo sem precisar saber de $1, $2… */
function insertButtons(pieces, cat, ctx, values) {
  const taken = pieces.filter((p) => p.take);
  return h('div', { class: 'rx-insert' }, h('span', { class: 'field-help' }, 'Inserir no texto novo:'),
    taken.map((p, i) => button({ label: `${i + 1}: ${(p.name || '').trim() || sayPiece(p, cat)}`, size: 'sm', title: `Acrescenta $${i + 1} ao "Trocar por"`,
      onClick: () => ctx.update('replacement', `${values.replacement || ''}$${i + 1}`) })));
}
