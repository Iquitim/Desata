// Detalhe de uma fonte do catálogo (spec 049, RF-4911..4915, RF-4937, RF-4938, RF-4940): o máximo de informação
// antes de usar, as escolhas com valores prontos, a prévia de verdade e, nos portais, o arquivo com prévia obrigatória.

import { api } from './api.js';
import { openLink } from './desktop.js';
import { button, h } from './dom.js';
import { openHolidayEditor } from './holidays_editor.js';
import { healthBlock } from './public_data_health.js';
import { icon } from './icons.js';

const PERIODS = [
  ['ultimos_anos:1', 'Último ano'], ['ultimos_anos:2', 'Últimos 2 anos'], ['ultimos_anos:5', 'Últimos 5 anos'],
  ['ultimos_anos:10', 'Últimos 10 anos'], ['desde', 'Desde…'], ['intervalo', 'De… até…'], ['tudo', 'Tudo'],
];
const KIND_WORDS = { data: 'data', numero: 'número', inteiro: 'número inteiro', texto: 'texto' };
const SITUATIONS = {
  legivel: ['Lê direto', 'ok'], grande: ['Arquivo grande', 'warn'], odata: ['Serviço do Banco Central', 'ok'], so_link: ['Só no navegador', 'muted'],
};
const DELIMITERS = [['auto', 'Automático'], [';', 'Ponto e vírgula (;)'], [',', 'Vírgula (,)'], ['\t', 'Tabulação'], ['|', 'Barra (|)']];
const ENCODINGS = [['auto', 'Automática'], ['utf-8', 'UTF-8'], ['cp1252', 'Windows-1252'], ['latin-1', 'ISO-8859-1']];

const size = (n) => (n == null ? '' : n > 1e9 ? `${(n / 1e9).toFixed(1)} GB` : n > 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1e3))} KB`);

function dateText(text) {
  if (!text) return '';
  const iso = /^\d{4}-\d{2}-\d{2}/.test(text) ? text.slice(0, 10) : null;
  if (iso) return new Date(`${iso}T12:00:00`).toLocaleDateString('pt-BR');
  if (/^\d{6}$/.test(text)) return `${text.slice(4)}/${text.slice(0, 4)}`;
  return text;
}

function periodValue(choice) {
  if (!choice) return 'ultimos_anos:5';
  return choice.kind === 'ultimos_anos' ? `ultimos_anos:${choice.anos}` : choice.kind;
}

/** O detalhe de uma fonte. ``ctx.onUse(fonte, escolhas)`` adiciona (a caixa no fluxo chega na T12). */
export function publicDetail(entry, ctx = {}) {
  const st = { info: null, error: null, choices: {}, preview: null, previewing: false, previewError: null,
    resource: null, filePreview: null, fileError: null, fileBusy: false, options: {}, member: '',
    odata: null, odataError: null, entry: null, params: {}, currencies: null };
  const root = h('aside', { class: 'pd-detail', 'aria-label': `Detalhe de ${entry.nome}`, 'aria-busy': 'true' },
    h('p', { class: 'pd-loading' }, 'Conferindo com o órgão…'));

  // replaceChildren escreveria null e listas como texto ("null"): achata e tira os vazios.
  const redraw = () => root.replaceChildren(...render().flat(Infinity).filter((n) => n !== null && n !== undefined && n !== false));
  root.refreshHealth = () => { if (st.info || st.error) redraw(); };
  const serviceId = () => st.info?.servico || entry.servico || null;
  const healthRow = () => ctx.health?.(serviceId()) || null;
  const setChoice = (key, value) => { st.choices = { ...st.choices, [key]: value }; st.preview = null; redraw(); };

  async function load() {
    try {
      st.info = await api.publicDescribe(entry.id);
      for (const field of st.info.escolhas) if (field.padrao !== undefined && field.padrao !== null) st.choices[field.id] = field.padrao;
      if (ctx.initialChoices) {
        // Trocar, na caixa do fluxo: volta com as escolhas que ela já tinha.
        st.choices = { ...st.choices, ...ctx.initialChoices };
        st.options = { ...(ctx.initialChoices.formato_aceito?.opcoes || {}) };
        st.member = ctx.initialChoices.formato_aceito?.membro || '';
        if (ctx.initialChoices.consulta) st.entry = ctx.initialChoices.consulta;
        if (ctx.initialChoices.parametros) st.params = { ...ctx.initialChoices.parametros };
      }
    } catch (err) {
      st.error = err.message || String(err);
    }
    root.setAttribute('aria-busy', 'false');
    redraw();
    const again = st.info?.arquivos?.find((a) => a.id === ctx.initialChoices?.arquivo);
    if (again && again.situacao !== 'so_link') chooseFile(again, true);
    else if (st.info?.leitura === 'pronta' && st.info.id !== 'receita.cnpj/dados-abertos') runPreview();
  }

  async function runPreview() {
    st.previewing = true; st.previewError = null; redraw();
    try {
      st.preview = await api.publicPreview(entry.id, st.choices);
    } catch (err) {
      st.preview = null;
      st.previewError = err.message || String(err);
    }
    st.previewing = false; redraw();
  }

  async function chooseFile(resource, keep = false) {
    st.resource = resource; st.filePreview = null; st.fileError = null; st.odata = null; st.odataError = null;
    if (!keep) { st.options = {}; st.member = ''; }
    st.choices = { ...st.choices, arquivo: resource.id };
    redraw();
    if (resource.situacao === 'legivel') readFile();
    if (resource.situacao === 'odata') {
      try {
        st.odata = await api.publicOdata(entry.id, resource.id);
        const first = st.odata.consultas.find((c) => c.nome === (keep && st.entry ? st.entry : st.odata.consulta)) || st.odata.consultas[0];
        st.entry = first?.nome || null;
        st.choices = { ...st.choices, consulta: st.entry };
      } catch (err) {
        st.odataError = err.message || String(err);
      }
      redraw();
    }
  }

  async function readFile() {
    st.fileBusy = true; st.fileError = null; redraw();
    try {
      st.filePreview = await api.publicFilePreview(entry.id, st.resource.id, st.options, st.member);
      st.options = { ...st.filePreview.opcoes };
      st.member = st.filePreview.membro;
      st.choices = { ...st.choices, formato_aceito: st.filePreview.formato_aceito };
    } catch (err) {
      st.filePreview = null;
      st.fileError = err.message || String(err);
    }
    st.fileBusy = false; redraw();
  }

  // ---------------------------------------------------------------- pedaços

  function header() {
    const i = st.info || entry;
    return h('header', { class: 'pd-detail-head' },
      h('span', { class: 'pd-card-icon' }, icon(ctx.iconFor?.(entry) || 'chart', 20)),
      h('div', {},
        h('h2', {}, i.nome || entry.nome),
        h('p', { class: 'pd-card-meta' },
          i.orgao || ctx.agencyName?.(entry.orgao) || '',
          i.pagina ? [' · ', h('a', { href: i.pagina, class: 'pd-link', onclick: (e) => { e.preventDefault(); openLink(i.pagina); } },
            'página oficial ', icon('link', 11))] : null)));
  }

  function badge() {
    return st.info?.leitura === 'pronta' || entry.destaque
      ? h('span', { class: 'pd-badge pd-badge-ready' }, icon('check', 11), 'Pronto: conferida uma a uma, com as colunas explicadas')
      : h('span', { class: 'pd-badge pd-badge-auto' }, 'Leitura automática: confira a prévia antes de usar');
  }

  function facts() {
    const i = st.info;
    const rows = [];
    if (i.periodo?.inicio) rows.push(['Período', `${dateText(i.periodo.inicio)} a ${i.periodo.fim ? dateText(i.periodo.fim) : 'hoje'}`]);
    if (i.periodicidade) rows.push(['Periodicidade', i.periodicidade]);
    if (i.granularidade) rows.push(['Nível', i.granularidade]);
    if (i.unidade) rows.push(['Unidade', i.unidade]);
    if (i.atualizado) rows.push([i.atualizado_rotulo ? i.atualizado_rotulo.replace(/ em$/, '') : 'Atualização', dateText(i.atualizado)]);
    if (entry.codigo && !entry.id.startsWith('calendario')) rows.push(['Código', h('span', { class: 'mono' }, entry.codigo)]);
    return rows.length ? h('dl', { class: 'pd-facts' }, rows.map(([k, v]) => [h('dt', {}, k[0].toUpperCase() + k.slice(1)), h('dd', {}, v)])) : null;
  }

  function periodField(field) {
    const value = st.choices.periodo || field.padrao || {};
    const current = periodValue(value);
    const select = h('select', { class: 'input', 'aria-label': 'Período', onchange: (e) => {
      const v = e.target.value;
      const year = new Date().getFullYear();
      const next = v.startsWith('ultimos_anos') ? { kind: 'ultimos_anos', anos: Number(v.split(':')[1]) }
        : v === 'desde' ? { kind: 'desde', inicio: value.inicio || `${year - 5}-01-01` }
          : v === 'intervalo' ? { kind: 'intervalo', inicio: value.inicio || `${year - 1}-01-01`, fim: value.fim || `${year - 1}-12-31` }
            : { kind: 'tudo' };
      setChoice('periodo', next);
    } }, PERIODS.map(([v, label]) => h('option', { value: v, selected: v === current }, label)));
    const dates = [];
    if (value.kind === 'desde' || value.kind === 'intervalo') {
      dates.push(h('input', { type: 'date', class: 'input', value: value.inicio || '', 'aria-label': 'Início',
        onchange: (e) => setChoice('periodo', { ...value, inicio: e.target.value }) }));
    }
    if (value.kind === 'intervalo') {
      dates.push(h('input', { type: 'date', class: 'input', value: value.fim || '', 'aria-label': 'Fim',
        onchange: (e) => setChoice('periodo', { ...value, fim: e.target.value }) }));
    }
    const hint = value.kind === 'ultimos_anos' ? 'Relativo: no agendamento, sempre os mais recentes.' : '';
    return [select, ...dates, hint ? h('small', { class: 'field-help' }, hint) : null];
  }

  function field(f) {
    const value = st.choices[f.id];
    let control;
    if (f.tipo === 'periodo') control = periodField(f);
    else if (f.tipo === 'opcoes') {
      control = h('select', { class: 'input', onchange: (e) => setChoice(f.id, isNaN(Number(e.target.value)) ? e.target.value : Number(e.target.value)) },
        f.opcoes.map((o) => h('option', { value: o.valor, selected: String(o.valor) === String(value) }, o.rotulo)));
    } else if (f.tipo === 'varios') {
      const chosen = new Set(value || []);
      control = h('div', { class: 'pd-checks' }, f.opcoes.map((o) => h('label', {},
        h('input', { type: 'checkbox', checked: chosen.has(o.valor), onchange: (e) => {
          const next = new Set(chosen);
          if (e.target.checked) next.add(o.valor); else next.delete(o.valor);
          setChoice(f.id, [...next]);
        } }), ' ', o.rotulo)));
    } else if (f.tipo === 'local') {
      control = [h('input', { class: 'input', value: value || 'BR', placeholder: 'BR, SP ou 3509502',
        onchange: (e) => setChoice(f.id, e.target.value.trim().toUpperCase()) }),
      h('small', { class: 'field-help' }, 'BR, a sigla do estado (SP) ou o código do IBGE do município (Campinas: 3509502).')];
    } else if (f.tipo === 'arquivo') {
      return null; // a lista de arquivos tem seção própria
    } else if (f.id === 'moeda') {
      control = currencyField(value);
    } else {
      control = h('input', { class: 'input', type: f.tipo === 'numero' ? 'number' : 'text', value: value ?? '',
        onchange: (e) => setChoice(f.id, f.tipo === 'numero' ? Number(e.target.value) : e.target.value.trim()) });
    }
    return h('div', { class: 'pd-field' }, h('label', { class: 'field-label' }, f.rotulo), control);
  }

  function currencyField(value) {
    if (!st.currencies) {
      st.currencies = [];
      api.publicCurrencies().then((r) => { st.currencies = r.moedas; redraw(); }).catch(() => {});
    }
    const list = [{ simbolo: 'USD', nome: 'Dólar dos Estados Unidos' }, ...st.currencies.filter((m) => m.simbolo !== 'USD')];
    return h('select', { class: 'input', onchange: (e) => setChoice('moeda', e.target.value) },
      list.map((m) => h('option', { value: m.simbolo, selected: m.simbolo === (value || 'USD') }, `${m.simbolo} · ${m.nome}`)));
  }

  function filesSection() {
    const files = st.info.arquivos || [];
    if (!files.length) return null;
    return h('section', { class: 'pd-section' },
      h('h3', {}, `Arquivos do conjunto (${files.length})`),
      h('ul', { class: 'pd-files' }, files.map((a) => {
        const [label, tone] = SITUATIONS[a.situacao];
        const chosen = st.resource?.id === a.id;
        const action = a.situacao === 'so_link'
          ? button({ icon: 'link', label: 'Abrir no navegador', size: 'sm', onClick: () => openLink(a.url) })
          : a.situacao === 'grande'
            ? button({ icon: 'download', label: 'Baixar…', size: 'sm', disabled: true, title: 'O download com pasta escolhida chega na etapa do CNPJ' })
            : button({ label: chosen ? 'Escolhido' : 'Usar este', size: 'sm', variant: chosen ? 'primary' : '', onClick: () => chooseFile(a) });
        return h('li', { class: `pd-file${chosen ? ' is-chosen' : ''}` },
          h('div', { class: 'pd-file-main' },
            h('strong', {}, a.nome),
            h('span', { class: 'pd-file-meta' }, [a.formato.toUpperCase(), size(a.tamanho), a.atualizado ? dateText(a.atualizado) : ''].filter(Boolean).join(' · ')),
            a.motivo ? h('span', { class: `pd-file-why tone-${tone}` }, a.motivo) : null),
          h('span', { class: `pd-chip tone-${tone}` }, label), action);
      })));
  }

  function filePreviewSection() {
    if (!st.resource || st.resource.situacao !== 'legivel') return null;
    const opts = st.options;
    const select = (key, list, label) => h('label', { class: 'pd-inline' }, label,
      h('select', { class: 'input', onchange: (e) => { st.options = { ...st.options, [key]: e.target.value }; } },
        list.map(([v, l]) => h('option', { value: v, selected: (opts[key] ?? 'auto') === v }, l))));
    const p = st.filePreview;
    return h('section', { class: 'pd-section pd-must' },
      h('h3', {}, 'Prévia obrigatória'),
      h('p', { class: 'field-help' }, 'Confira se as colunas e os valores saíram certos. O formato que você aceitar fica gravado: se o órgão mudar o arquivo, a caixa avisa em vez de ler errado.'),
      h('div', { class: 'pd-read-opts' },
        select('delimiter', DELIMITERS, 'Separador'),
        select('encoding', ENCODINGS, 'Codificação'),
        h('label', { class: 'pd-inline' }, 'Pular linhas', h('input', { class: 'input', type: 'number', min: 0, value: opts.skip_rows ?? 0,
          onchange: (e) => { st.options = { ...st.options, skip_rows: Number(e.target.value) || 0 }; } })),
        p?.membros?.length > 1 ? h('label', { class: 'pd-inline' }, 'Arquivo do ZIP',
          h('select', { class: 'input', onchange: (e) => { st.member = e.target.value; } },
            p.membros.map((m) => h('option', { value: m, selected: m === st.member }, m)))) : null,
        button({ icon: 'refresh', label: 'Ler de novo', size: 'sm', disabled: st.fileBusy, onClick: readFile })),
      st.fileBusy ? h('p', { class: 'pd-loading' }, 'Baixando e lendo o arquivo…') : null,
      st.fileError ? h('p', { class: 'pd-note pd-note-err' }, icon('alert', 13), ` ${st.fileError}`) : null,
      p ? [
        h('p', { class: 'pd-note' }, `${p.linhas_total != null ? `${Number(p.linhas_total).toLocaleString('pt-BR')} linhas · ` : ''}${size(p.tamanho)}${p.membro ? ` · ${p.membro}` : ''}`),
        p.numeros_convertidos?.length ? h('p', { class: 'pd-note' }, icon('info', 13), ` Lidas como número (padrão brasileiro ou o da coluna): ${p.numeros_convertidos.join(', ')}.`) : null,
        table(p.colunas, p.linhas),
      ] : null);
  }

  function odataSection() {
    if (!st.resource || st.resource.situacao !== 'odata') return null;
    if (st.odataError) return h('p', { class: 'pd-note pd-note-err' }, icon('alert', 13), ` ${st.odataError}`);
    if (!st.odata) return h('p', { class: 'pd-loading' }, 'Lendo a descrição do serviço…');
    const current = st.odata.consultas.find((c) => c.nome === st.entry);
    const params = current?.parametros || [];
    return h('section', { class: 'pd-section' },
      h('h3', {}, 'Consulta do serviço'),
      h('select', { class: 'input', onchange: (e) => { st.entry = e.target.value; st.params = {}; st.choices = { ...st.choices, consulta: st.entry, parametros: {} }; st.preview = null; redraw(); } },
        st.odata.consultas.map((c) => h('option', { value: c.nome, selected: c.nome === st.entry },
          `${c.titulo}${c.parametros.length ? '' : ' (sem parâmetros)'}${c.parametros.length && !c.conferida ? ' · parâmetros não conferidos' : ''}`))),
      current?.descricao ? h('p', { class: 'field-help' }, current.descricao) : null,
      params.some((p) => p.tipo === 'data' && p.conferido) ? h('div', { class: 'pd-field' }, h('label', { class: 'field-label' }, 'Período'), periodField({ padrao: { kind: 'ultimos_anos', anos: 1 } })) : null,
      params.filter((p) => !(p.tipo === 'data' && p.conferido)).map((p) => h('div', { class: 'pd-field' },
        h('label', { class: 'field-label' }, p.descricao || p.nome, p.conferido ? null : h('span', { class: 'pd-chip tone-warn' }, 'não conferido')),
        h('input', { class: 'input', value: st.params[p.nome] ?? p.exemplo ?? '', placeholder: p.exemplo || p.nome,
          onchange: (e) => { st.params = { ...st.params, [p.nome]: e.target.value }; st.choices = { ...st.choices, parametros: st.params }; st.preview = null; } }))),
      current && !current.conferida ? h('p', { class: 'pd-note' }, icon('alert', 13), ' O programa não conferiu o formato destes parâmetros: digite como o Banco Central pede e confira a prévia. ',
        h('a', { href: st.odata.documentacao, class: 'pd-link', onclick: (e) => { e.preventDefault(); openLink(st.odata.documentacao); } }, 'documentação do serviço')) : null);
  }

  function table(columns, rows) {
    if (!columns?.length) return null;
    return h('div', { class: 'pd-table-wrap' }, h('table', { class: 'pd-table' },
      h('thead', {}, h('tr', {}, columns.map((c) => h('th', { title: c.type }, c.name)))),
      h('tbody', {}, rows.map((r) => h('tr', {}, columns.map((c) => h('td', {}, r[c.name] == null ? '' : String(r[c.name]))))))));
  }

  function previewSection() {
    if ((st.info.arquivos && st.resource?.situacao !== 'odata') || entry.id === 'receita.cnpj/dados-abertos') return null;
    if (st.resource?.situacao === 'odata' && !st.odata) return null;
    const p = st.preview;
    return h('section', { class: 'pd-section' },
      h('div', { class: 'pd-section-head' }, h('h3', {}, 'Prévia'),
        button({ icon: 'eye', label: p ? 'Ler de novo' : 'Ver prévia', size: 'sm', disabled: st.previewing, onClick: runPreview })),
      st.previewing ? h('p', { class: 'pd-loading' }, 'Lendo direto do órgão…') : null,
      st.previewError ? h('p', { class: 'pd-note pd-note-err' }, icon('alert', 13), ` ${st.previewError}`) : null,
      p ? [h('p', { class: 'pd-note' }, `Últimas linhas de ${Number(p.linhas_lidas).toLocaleString('pt-BR')} lidas agora.`),
        p.avisos?.map((a) => h('p', { class: 'pd-note' }, icon('info', 13), ` ${a}`)), table(p.colunas, p.linhas)] : null);
  }

  function columnsSection() {
    const cols = st.info.colunas || [];
    if (!cols.length) return null;
    return h('details', { class: 'pd-section', open: st.info.leitura === 'pronta' },
      h('summary', {}, h('h3', {}, `Colunas (${cols.length})`)),
      h('dl', { class: 'pd-dictionary' }, cols.map((c) => [
        h('dt', {}, h('span', { class: 'mono' }, c.nome), h('small', {}, KIND_WORDS[c.tipo] || c.tipo)),
        h('dd', {}, c.descricao || '—')])));
  }

  function footer() {
    const urls = [...(st.info.urls_exemplo || []), ...(st.preview?.urls || [])];
    return [
      h('details', { class: 'pd-section' },
        h('summary', {}, h('h3', {}, 'Licença e citação')),
        h('p', {}, st.info.licenca || 'Conforme o órgão.'),
        st.info.citacao ? h('p', { class: 'pd-cite' }, `Fonte: ${st.info.citacao}.`) : null),
      urls.length ? h('details', { class: 'pd-section' },
        h('summary', {}, h('h3', {}, 'Avançado')),
        h('p', { class: 'field-help' }, 'Os endereços que o programa chama, sem nada escondido.'),
        urls.map((u) => h('code', { class: 'pd-url' }, u))) : null,
    ];
  }

  /** Por que ainda não dá para adicionar: a leitura automática exige a prévia conferida (RF-4938, RF-4939). */
  function blockedReason() {
    if (!st.info) return 'Carregando';
    if (entry.id === 'receita.cnpj/dados-abertos') return 'O CNPJ vem em arquivos grandes: o download chega na etapa do CNPJ';
    if (healthRow()?.situacao === 'fora') return `O órgão está fora do ar agora: ${healthRow().motivo || 'confira de novo em instantes'}`;
    if (st.info.leitura === 'pronta') return '';
    if (st.info.arquivos) {
      if (!st.resource) return 'Escolha um arquivo do conjunto';
      if (st.resource.situacao === 'legivel') return st.choices.formato_aceito ? '' : 'Confira a prévia do arquivo primeiro';
      if (st.resource.situacao === 'odata') return st.preview ? '' : 'Veja a prévia da consulta primeiro';
      return 'Este arquivo não é lido pelo programa';
    }
    return st.preview ? '' : 'Veja a prévia primeiro: é leitura automática';
  }

  function actions() {
    const why = blockedReason();
    const blocked = Boolean(why);
    return h('footer', { class: 'pd-actions' },
      why ? h('p', { class: 'pd-why' }, why) : null,
      h('div', { class: 'row' },
        button({ icon: 'plus', label: ctx.useLabel || 'Adicionar ao fluxo', variant: 'primary', disabled: blocked || !ctx.onUse,
          title: why || '', onClick: () => ctx.onUse?.(entry, st.choices, 'fluxo', st.info) }),
        ctx.canUseData ? button({ icon: 'database', label: 'À vista Dados', disabled: blocked,
          title: why || '', onClick: () => ctx.onUse?.(entry, st.choices, 'dados', st.info) }) : null));
  }

  function render() {
    if (st.error) return [header(), h('p', { class: 'pd-note pd-note-err' }, icon('alert', 13), ` ${st.error}`)];
    if (!st.info) return [header(), h('p', { class: 'pd-loading' }, 'Conferindo com o órgão…')];
    const i = st.info;
    return [
      header(), badge(),
      serviceId() && entry.id.split('/')[0] !== 'calendario' ? healthBlock(healthRow(), {
        busy: Boolean(ctx.checking?.()), offline: Boolean(ctx.offline?.()), onRecheck: () => ctx.recheck?.(serviceId()) }) : null,
      i.resumo ? h('p', {}, i.resumo) : null,
      i.descricao && i.descricao !== i.resumo ? h('details', { class: 'pd-more' }, h('summary', {}, 'Descrição do órgão'), h('p', {}, i.descricao)) : null,
      facts(),
      entry.id.startsWith('calendario/') ? h('div', { class: 'row' }, button({ icon: 'edit', label: 'Editar feriados…', onClick: () => openHolidayEditor({
        place: st.choices.local || 'BR', onChange: () => { st.preview = null; runPreview(); } }) }),
      h('small', { class: 'field-help' }, 'Inclua os do seu município, corrija ou marque o que não vale mais.')) : null,
      i.avisos.map((a) => h('p', { class: 'pd-note' }, icon('alert', 13), ` ${a}`)),
      i.escolhas.length && !i.arquivos ? h('section', { class: 'pd-section' }, h('h3', {}, 'Escolhas'), i.escolhas.map(field)) : null,
      filesSection(), odataSection(), filePreviewSection(), previewSection(), columnsSection(), footer(), actions(),
    ];
  }

  load();
  return root;
}
