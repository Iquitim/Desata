// Fluxo em outro computador (spec 040, RF-4010..4017): o que falta aqui aparece em vermelho (aba Dados, vista Dados e
// a caixa no Designer), cada fonte tem a ação para resolver, e "Salvar com amostra dos dados" leva uma amostra.

import { api } from './api.js';
import { cnpjOfKey, openCnpjDownload } from './cnpj_ui.js';
import { allSources } from './data_sources.js';
import { chooseSaveFile } from './desktop.js';
import { button, debounce, fmt, h } from './dom.js';
import { icon } from './icons.js';
import { setSourceProblems } from './portable_state.js';
import { openSourcePicker } from './source_picker.js';
import { emit, markSaved, mutate, on, store } from './store.js';
import { openDialog, toast, toastError } from './ui.js';

export const portable = { sources: [] };

/** Confere as fontes do fluxo aberto. Rápido: só olha os cadastros, não lê dados. */
export const checkSources = debounce(async () => {
  if (!store.workflow) return;
  try {
    const res = await api.portableSources(store.workflow, store.space?.id || null);
    portable.sources = res.sources;
  } catch {
    portable.sources = [];
  }
  setSourceProblems(portable.sources);
  paintBadge();
  emit('sources');
}, 250);

const pending = () => portable.sources.filter((s) => s.state !== 'ok');
/** As tabelas do CNPJ que o fluxo usa e faltam aqui: já marcadas no download (RF-4972). */
const cnpjGroups = () => [...new Set(pending().map((s) => cnpjOfKey(s.key)?.grupo).filter(Boolean))];

/** Selo na aba Dados: vermelho com o que falta; laranja quando só há amostra. */
function paintBadge() {
  const tab = document.querySelector('#viewSwitch .segment[data-view="data"]');
  if (!tab) return;
  tab.querySelector('.tab-badge')?.remove();
  const missing = portable.sources.filter((s) => s.state === 'missing').length;
  const samples = portable.sources.filter((s) => s.state === 'sample').length;
  if (!missing && !samples) return;
  tab.append(h('span', {
    class: ['tab-badge', missing ? 'err' : 'warn'],
    title: missing ? `${missing} fonte(s) deste fluxo não estão neste computador` : `${samples} fonte(s) lidas da amostra que veio no fluxo`,
  }, String(missing || samples)));
}

// ---------------------------------------------------------- vista Dados: Faltam neste computador

const SAME_KIND = { file: 'file', folder: 'folder', pdf: 'pdf', query: 'query', api: 'api', jira: 'jira' };

/** Troca a fonte em todas as caixas do fluxo que a usam. O resto do fluxo não muda. */
function repoint(item, value) {
  mutate((wf) => {
    for (const n of wf.nodes) {
      if (!item.nodes.includes(n.id)) continue;
      if (n.type === 'io.input_data') {
        const out = item.kind === 'pdf' ? (n.config.dataset.split('/')[1] || 'campos') : null;
        n.config.dataset = out ? `${value.split('/')[0]}/${out}` : value;
      } else if (n.type === 'io.api_loop') n.config.source = value.replace(/^api:/, '');
    }
    if (wf.samples && value !== item.key) delete wf.samples[item.key];
  }, { structural: true });
  toast('Fonte trocada no fluxo', { kind: 'success', detail: `${item.label} → ${value}` });
  checkSources();
}

function dropSample(item) {
  mutate((wf) => { delete wf.samples[item.key]; }, { structural: true });
  checkSources();
}

/** Escolher o arquivo: entra na vista Dados com o mesmo nome que o fluxo espera, e o fluxo funciona sem mudar. */
function pickFile(item) {
  const input = h('input', { type: 'file', hidden: true, onchange: async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const ext = (name) => name.split('.').pop().toLowerCase();
    if (ext(file.name) !== ext(item.key)) {
      toast('Formato diferente do esperado', { kind: 'error', detail: `O fluxo lê ${item.key}; escolha um arquivo .${ext(item.key)}.` });
      return;
    }
    try {
      await api.uploadDataset(new File([file], item.key, { type: file.type }));
      emit('datasets');
      toast('Arquivo no lugar', { kind: 'success', detail: `${file.name} entrou como ${item.key}.` });
      checkSources();
    } catch (err) {
      toastError(err, 'Não foi possível usar o arquivo');
    }
  } });
  document.body.append(input);
  input.click();
  setTimeout(() => input.remove(), 60_000);
}

function card(item) {
  const sample = item.state === 'sample';
  const options = SAME_KIND[item.kind] ? allSources().filter((s) => s.kind === SAME_KIND[item.kind] && s.dragValue) : [];
  const when = sample ? new Date(item.sample.created_at).toLocaleDateString('pt-BR') : '';
  return h('li', { class: ['pt-item', sample ? 'sample' : 'missing'], dataset: { key: item.key } },
    h('div', { class: 'pt-head' },
      icon(sample ? 'database' : 'alert', 14),
      h('b', { class: 'ellipsis', title: item.key }, item.label),
      h('span', { class: ['pt-tag', sample ? 'warn' : 'err'] }, sample ? 'Amostra' : 'falta')),
    h('small', { class: 'pt-meta' }, sample
      ? `${item.kind_label} · ${fmt.int(item.sample.rows)} linhas, de ${when}. O fluxo roda com a amostra até você apontar a fonte.`
      : `${item.kind_label} · usada em ${item.nodes.length} caixa(s). Não está neste computador.`),
    item.sample?.linked ? h('p', { class: 'pt-linked' }, icon('link', 12),
      ' Quem enviou lia este arquivo de uma pasta do próprio computador (arquivo vinculado). Peça o arquivo e escolha aqui; até lá, vale a amostra.') : null,
    h('div', { class: 'pt-actions' },
      cnpjOfKey(item.key) ? button({ icon: 'download', label: 'Baixar os dados do CNPJ aqui…', size: 'sm', variant: 'primary', // RF-4972
        title: `O CNPJ é de cada computador: baixe o mês ${cnpjOfKey(item.key).mes} e o fluxo funciona sem trocar nada`,
        onClick: () => openCnpjDownload({ mes: cnpjOfKey(item.key).mes, grupos: cnpjGroups() }) }) : null,
      item.kind === 'file' ? button({ icon: 'upload', label: 'Escolher o arquivo', size: 'sm', variant: sample ? '' : 'primary', onClick: () => pickFile(item) }) : null,
      options.length ? button({ icon: 'folder', label: item.kind === 'file' ? 'Usar um arquivo daqui…' : 'Usar uma fonte daqui…', size: 'sm',
        title: `Escolher uma fonte deste computador no lugar de ${item.label}`,
        onClick: () => openSourcePicker({ kinds: [SAME_KIND[item.kind]], title: `No lugar de ${item.label}`, onPick: (v) => repoint(item, v) }) }) : null,
      !options.length && item.kind !== 'file' ? h('span', { class: 'field-help' }, `${item.action} na vista Dados (Adicionar) e escolha aqui.`) : null,
      sample ? button({ icon: 'trash', label: 'Apagar a amostra', size: 'sm', variant: 'ghost', onClick: () => dropSample(item) }) : null));
}

/** A seção no topo da lista da vista Dados; nada quando o fluxo tem tudo neste computador. */
export function missingSection() {
  const list = pending();
  if (!list.length) return null;
  const missing = list.filter((s) => s.state === 'missing').length;
  return h('section', { class: ['pt-box', missing ? 'err' : 'warn'], 'aria-label': 'Fontes que faltam neste computador' },
    h('div', { class: 'pt-title' }, icon(missing ? 'alert' : 'database', 15),
      h('b', {}, missing ? 'Faltam neste computador' : 'Lendo a amostra do fluxo'),
      h('span', { class: 'org-count' }, String(list.length))),
    h('p', { class: 'field-help' }, missing
      ? `O fluxo “${store.workflow.name}” usa fontes que não estão aqui. Aponte cada uma para ele rodar.`
      : 'Estas fontes não estão aqui: o fluxo roda com a amostra que veio no arquivo.'),
    h('ul', { class: 'pt-list' }, list.map(card)));
}

// ---------------------------------------------------------- Salvar com amostra dos dados

const ROW_CHOICES = [100, 500, 1000];
const MASKS = {
  '': 'manter',
  cpf: 'máscara de CPF',
  cnpj: 'máscara de CNPJ',
  email: 'máscara de e-mail',
  keep_first: 'só o início',
  keep_last: 'só o fim (4)',
  code: 'código estável',
  fixed: 'trocar por ***',
};

/**
 * "Salvar com amostra dos dados" (spec 040, RF-4013, RF-4019): cada fonte escolhe quantas linhas e o que mascarar,
 * com as colunas pessoais já marcadas e uma prévia mascarada. Só a amostra muda: a fonte e o fluxo, não.
 */
export async function shareDialog({ onSaved } = {}) {
  const body = h('div', { class: 'stack-md pt-share' }, h('p', { class: 'muted' }, 'Lendo as primeiras linhas de cada fonte…'));
  const choice = new Map(); // fonte → {rows, mask}
  const open = new Set();
  let preview = null;
  const saveBtn = button({ icon: 'save', label: 'Escolher onde salvar…', variant: 'primary', disabled: true, onClick: () => save() });
  const dlg = openDialog({ title: 'Salvar com amostra dos dados', body, size: 'lg', actions: [button({ label: 'Cancelar', onClick: () => dlg.close() }), saveBtn] });
  const estimate = (s) => Math.round((s.size || 0) * (choice.get(s.key).rows / Math.max(1, s.rows)));
  const total = () => preview.sources.filter((s) => choice.has(s.key)).reduce((n, s) => n + estimate(s), 0);

  const masked = (s) => Object.values(choice.get(s.key)?.mask || {}).filter(Boolean).length;
  async function drawPreview(s, box) {
    box.replaceChildren(h('p', { class: 'muted' }, 'Mascarando a prévia…'));
    try {
      const p = await api.portableMaskPreview(store.workflow, s.key, choice.get(s.key).mask);
      box.replaceChildren(h('div', { class: 'pt-preview' }, h('table', {},
        h('thead', {}, h('tr', {}, p.columns.map((c) => h('th', { class: choice.get(s.key).mask[c] ? 'masked' : '' }, c)))),
        h('tbody', {}, p.rows.map((r) => h('tr', {}, p.columns.map((c) => h('td', { class: choice.get(s.key).mask[c] ? 'masked' : '' }, r[c] === null ? '' : String(r[c])))))))));
    } catch (err) {
      box.replaceChildren(h('p', { class: 'text-error' }, err.message));
    }
  }

  function sourceRow(s) {
    const on = choice.has(s.key);
    const usable = s.rows !== undefined;
    const opt = choice.get(s.key);
    const head = h('div', { class: 'pt-row' },
      h('label', { class: 'pe-check' }, h('input', { type: 'checkbox', checked: on, disabled: !usable,
        onchange: (e) => { if (e.target.checked) choice.set(s.key, { rows: Math.min(1000, s.available || 1000), mask: { ...s.mask } }); else choice.delete(s.key); draw(); } }),
      h('span', { class: 'ellipsis' }, s.label, s.linked ? h('span', { class: 'pt-tag-linked', title: 'Arquivo vinculado: lido de uma pasta deste computador' }, ' vinculado') : null)),
      !usable ? h('small', { class: 'muted' }, s.reason || '—') : on ? h('span', { class: 'pt-row-opts' },
        h('select', { class: 'input input-sm', 'aria-label': `Linhas de ${s.label}`, onchange: (e) => { opt.rows = Number(e.target.value); draw(); } },
          ROW_CHOICES.filter((n) => n <= Math.max(100, s.available || 0) || n === 100).map((n) => h('option', { value: n, selected: opt.rows === n }, `${fmt.int(Math.min(n, s.available || n))} linhas`))),
        button({ icon: masked(s) ? 'lock' : 'shield', label: masked(s) ? `${masked(s)} mascarada(s)` : 'Mascarar…', size: 'sm', variant: masked(s) ? '' : 'ghost',
          'aria-expanded': String(open.has(s.key)), onClick: () => { if (open.has(s.key)) open.delete(s.key); else open.add(s.key); draw(); } }),
        h('small', { class: 'muted nowrap' }, fmt.bytes(estimate(s)))) : h('small', { class: 'muted' }, `${fmt.int(s.available || 0)} linhas disponíveis`));
    if (!on || !open.has(s.key)) return h('li', { class: 'pt-src' }, head);
    const box = h('div', {});
    const cols = h('div', { class: 'pt-cols' }, s.columns.map((c) => h('label', { class: 'pt-col' },
      h('span', { class: 'ellipsis', title: c.name }, c.name, s.mask[c.name] ? h('small', { class: 'pt-guess', title: 'Parece dado pessoal' }, ' pessoal') : null),
      h('select', { class: 'input input-sm', 'aria-label': `Máscara de ${c.name}`, onchange: (e) => {
        if (e.target.value) opt.mask[c.name] = e.target.value; else delete opt.mask[c.name];
        drawPreview(s, box);
        head.querySelector('.btn[aria-expanded]').lastChild.textContent = masked(s) ? `${masked(s)} mascarada(s)` : 'Mascarar…';
      } }, Object.entries(MASKS).map(([k, label]) => h('option', { value: k, selected: (opt.mask[c.name] || '') === k }, label))))));
    drawPreview(s, box);
    return h('li', { class: 'pt-src open' }, head, h('div', { class: 'pt-mask' }, cols, box));
  }

  /** Arquivo vinculado: quem receber não tem a pasta. O caminho nunca vai no arquivo; o aviso vai, para os dois lados. */
  const linkedWarning = () => {
    const linked = preview.sources.filter((s) => s.linked);
    if (!linked.length) return null;
    const without = linked.filter((s) => !choice.has(s.key));
    return h('div', { class: ['pt-linked-box', without.length && 'strong'] }, icon('link', 14), h('span', {},
      h('b', {}, linked.length === 1 ? `${linked[0].label} é um arquivo vinculado` : `${linked.length} fontes são arquivos vinculados`),
      ': são lidos de uma pasta deste computador, que quem receber não tem. O caminho não vai no arquivo; quem receber vai ver o aviso e precisar apontar o arquivo.',
      without.length ? h('b', {}, ` Sem amostra (${without.map((s) => s.label).join(', ')}), essa parte do fluxo não roda do outro lado.`) : ' Até lá, roda com a amostra.'));
  };

  const draw = () => {
    const used = total();
    const over = used > preview.limit;
    saveBtn.disabled = over || !choice.size;
    body.replaceChildren(...[
      h('p', {}, `A amostra vai junto no arquivo .prodata.json, para quem receber rodar o fluxo sem as fontes. Só a amostra é mascarada: a fonte e o fluxo não mudam. Para salvar sem amostra, use Salvar como.`),
      h('ul', { class: 'pt-list' }, preview.sources.map(sourceRow)),
      h('div', { class: ['pt-meter', over && 'over'] }, h('i', { style: { width: `${Math.min(100, (used / preview.limit) * 100)}%` } }),
        h('span', {}, `${fmt.bytes(used)} de ${fmt.bytes(preview.limit)}`)),
      linkedWarning(),
      h('p', { class: 'api-warn' }, icon('shield', 14),
        ' A amostra leva dados de verdade: confira as colunas mascaradas. O salvamento entra no registro de exportações. Caminhos, senhas e conexões nunca vão no arquivo.'),
      over ? h('p', { class: 'text-error' }, 'Passa do limite: diminua as linhas ou tire fontes.') : null,
      !choice.size ? h('p', { class: 'field-help' }, 'Marque pelo menos uma fonte.') : null,
    ].filter(Boolean));
  };

  let saving = false;
  async function save() {
    // o Enter que confirma o caminho devolve o foco a este botão: sem a trava, a gravação abriria de novo
    if (saving) return;
    saving = true;
    saveBtn.disabled = true;
    const name = (store.workflow.name || 'fluxo').normalize('NFKD').replace(/[^\w-]+/g, '_').replace(/^_+|_+$/g, '') || 'fluxo';
    const path = await chooseSaveFile(`${name}.prodata.json`, '');
    if (!path) { saving = false; saveBtn.disabled = false; return; }
    try {
      const res = await api.portableShare(store.workflow, path, Object.fromEntries(choice));
      store.workflow.samples = res.workflow.samples; // os próximos salvamentos levam a mesma amostra
      store.filePath = res.path;
      markSaved();
      dlg.close();
      onSaved?.(res.path);
      toast('Fluxo salvo com amostra', { kind: 'success', detail: res.path });
    } catch (err) {
      toastError(err, 'Não foi possível salvar');
      saving = false;
      saveBtn.disabled = false;
    }
  }
  try {
    preview = await api.portablePreview(store.workflow);
    for (const s of preview.sources) if (s.rows !== undefined) choice.set(s.key, { rows: Math.min(1000, s.available || 1000), mask: { ...s.mask } });
    draw();
  } catch (err) {
    body.replaceChildren(h('p', { class: 'text-error' }, icon('alert', 14), ` ${err.message}`));
  }
}

export function initPortable() {
  for (const event of ['workflow:loaded', 'datasets', 'queries', 'apis', 'folders', 'pdfs', 'connections', 'workflows']) on(event, () => checkSources());
  on('workflow:changed', ({ structural } = {}) => { if (structural) checkSources(); });
}
