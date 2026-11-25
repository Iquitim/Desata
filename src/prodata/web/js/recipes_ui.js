// Receitas prontas (spec 049, RF-4961): no menu da coluna do resultado, Corrigir valores pelo IPCA e Converter para
// dólar pela PTAX. O programa monta as caixas comuns (Dados públicos, Select, Join, Summarize, Append Fields,
// Formula) numa etapa nomeada, logo depois da caixa inspecionada; um Desfazer tira tudo de uma vez.

import { api } from './api.js';
import { button, h } from './dom.js';
import { icon } from './icons.js';
import { descendants, inspect, mutate, node, select, store } from './store.js';
import { openDialog, toast, toastError } from './ui.js';

const NUMERIC = new Set(['Int64', 'Float64']);
const DATES = new Set(['Date', 'Datetime']);
const CURRENCIES = ['USD', 'EUR', 'GBP', 'JPY', 'CHF', 'CAD', 'AUD', 'CNY', 'ARS'];

/** Coluna que parece município: pelo nome, ou por valores com 6 ou 7 dígitos ou "Nome/UF". */
const looksLikeCity = (c) => /munic|cidade|localidade|ibge|cod_?mun/i.test(c.name)
  || /^\d{6,7}$|[/(-]\s*[A-Za-z]{2}\)?$/.test(String(c.stats?.top ?? ''));

/** As receitas que cabem nesta coluna, para o menu do cabeçalho. */
export function recipeMenu(column, profile) {
  if (store.readonly) return [];
  const items = [];
  if (NUMERIC.has(column.type)) {
    items.push({ label: 'Corrigir valores pelo IPCA…', icon: 'percent', onSelect: () => openRecipe('ipca', column, profile) },
      { label: 'Converter para dólar pela PTAX…', icon: 'currency', onSelect: () => openRecipe('ptax', column, profile) });
  }
  if ((column.type === 'String' || column.type === 'Int64') && looksLikeCity(column)) {
    items.push({ label: 'Juntar com municípios do IBGE…', icon: 'map', onSelect: () => openCities(column, profile) });
  }
  return items.length ? ['separator', ...items] : [];
}

/** Juntar com municípios do IBGE (RF-4962): mostra antes quantas linhas casam e lista as que não casam. */
function openCities(column, profile) {
  const nodeId = store.inspect.nodeId;
  const port = store.inspect.anchor || 'out';
  const columns = profile?.columns || [];
  const cityCols = columns.filter((c) => c.type === 'String' || c.type === 'Int64');
  const citySel = h('select', { class: 'input', 'aria-label': 'Coluna do município', onchange: () => conferir() },
    cityCols.map((c) => h('option', { value: c.name, selected: c.name === column.name }, c.name)));
  const ufSel = h('select', { class: 'input', 'aria-label': 'Coluna da UF', onchange: () => conferir() },
    h('option', { value: '' }, 'No próprio texto (São Paulo/SP) ou sem UF'),
    columns.filter((c) => c.type === 'String' && c.name !== column.name).map((c) => h('option', { value: c.name, selected: /^(uf|estado|sigla_uf)$/i.test(c.name) }, c.name)));
  const result = h('div', { class: 'rc-check' }, h('p', { class: 'field-help' }, 'Conferindo com a lista do IBGE…'));
  let last = null;
  const conferir = async () => {
    result.replaceChildren(h('p', { class: 'field-help' }, 'Conferindo com a lista do IBGE…'));
    try {
      last = await api.publicCitiesCheck({ fluxo: store.workflow.id, caixa: nodeId, saida: port, coluna: citySel.value, coluna_uf: ufSel.value });
    } catch (err) {
      result.replaceChildren(h('p', { class: 'pd-note pd-note-err' }, icon('alert', 13), ` ${err.message}`));
      return;
    }
    const pct = last.linhas ? Math.round((last.casam / last.linhas) * 100) : 0;
    result.replaceChildren(...[
      h('div', { class: 'rc-match', role: 'img', 'aria-label': `${last.casam} de ${last.linhas} linhas casam` },
        h('span', { class: 'rc-match-ok', style: { width: `${pct}%` } })),
      h('p', {}, h('b', {}, `${last.casam.toLocaleString('pt-BR')} de ${last.linhas.toLocaleString('pt-BR')} linhas casam (${pct}%).`),
        last.nao_casam ? ` ${last.nao_casam.toLocaleString('pt-BR')} ficam com o código vazio: corrija na origem ou com uma caixa antes.` : ' Todas casaram.'),
      last.exemplos.length ? h('table', { class: 'rc-misses' },
        h('thead', {}, h('tr', {}, h('th', {}, 'Não casou'), h('th', { class: 'num' }, 'Linhas'), h('th', {}, 'Por quê'))),
        h('tbody', {}, last.exemplos.map((e) => h('tr', {}, h('td', { class: 'mono' }, e.valor || '(vazio)'), h('td', { class: 'num' }, e.linhas.toLocaleString('pt-BR')), h('td', {}, e.motivo))))) : null,
    ].filter(Boolean)); // null viraria o texto "null"
  };
  const go = async () => {
    const anchor = node(nodeId);
    let recipe;
    try {
      recipe = await api.publicCitiesRecipe({ coluna: citySel.value, coluna_uf: ufSel.value, colunas: columns.map((c) => c.name),
        x: (anchor?.x || 0) + 260, y: anchor?.y || 0 });
    } catch (err) {
      toastError(err, 'Não foi possível montar a junção');
      return;
    }
    insert(nodeId, port, recipe);
    dlg.close();
    toast(recipe.container.title, { kind: 'success', detail: 'A fonte do IBGE e a caixa SQL entraram numa etapa. Ctrl+Z desfaz.' });
  };
  const dlg = openDialog({
    title: 'Juntar com municípios do IBGE',
    size: 'lg',
    body: h('div', { class: 'stack-sm rc-dialog' },
      h('div', { class: 'rc-scheme' }, h('span', { class: 'rc-step' }, icon('landmark', 14), 'Municípios do IBGE'), h('span', { class: 'rc-arrow' }, '→'),
        h('span', { class: 'rc-step' }, icon('terminal', 14), 'Código de 7 ou 6 dígitos, ou nome com UF'), h('span', { class: 'rc-arrow' }, '→'),
        h('span', { class: 'rc-step' }, icon('map', 14), 'código, nome e UF do IBGE')),
      h('div', { class: 'row rc-cols' },
        h('div', { class: 'field' }, h('span', { class: 'field-label' }, 'Município'), citySel),
        h('div', { class: 'field' }, h('span', { class: 'field-label' }, 'UF'), ufSel)),
      result,
      h('p', { class: 'field-help' }, icon('info', 12), " Sem diferenciar acento, maiúsculas, hífen e d'. Nome sem UF só casa quando existe num estado só.")),
    actions: [button({ label: 'Cancelar', onClick: () => dlg.close() }), button({ icon: 'plus', label: 'Inserir no fluxo', variant: 'primary', onClick: go })],
  });
  conferir();
}

function scheme(kind) {
  const steps = kind === 'ipca'
    ? [['landmark', 'IPCA do IBGE'], ['join', 'Junta pelo mês'], ['function', 'valor × referência ÷ índice do mês']]
    : [['landmark', 'PTAX do Banco Central'], ['join', 'Dia ou dia útil anterior'], ['function', 'valor ÷ cotação']];
  return h('div', { class: 'rc-scheme', role: 'img', 'aria-label': steps.map(([, t]) => t).join(', depois ') },
    steps.map(([name, text], i) => [i ? h('span', { class: 'rc-arrow', 'aria-hidden': 'true' }, '→') : null,
      h('span', { class: 'rc-step' }, icon(name, 14), text)]).flat().filter(Boolean));
}

/** O diálogo: a coluna de valor, a de data e o mês de referência (IPCA) ou a moeda (PTAX). */
function openRecipe(kind, column, profile) {
  const nodeId = store.inspect.nodeId;
  const port = store.inspect.anchor || 'out';
  const columns = profile?.columns || [];
  const numbers = columns.filter((c) => NUMERIC.has(c.type));
  const dates = [...columns.filter((c) => DATES.has(c.type)), ...columns.filter((c) => c.type === 'String' && /data|dia|date|m[eê]s|compet/i.test(c.name))];
  const valueSel = h('select', { class: 'input', 'aria-label': 'Coluna de valor' }, numbers.map((c) => h('option', { value: c.name, selected: c.name === column.name }, c.name)));
  const dateSel = h('select', { class: 'input', 'aria-label': 'Coluna de data' }, dates.map((c) => h('option', { value: c.name }, c.name)));
  const latest = h('input', { type: 'radio', name: 'rc-ref', checked: true });
  const chosen = h('input', { type: 'radio', name: 'rc-ref' });
  const month = h('input', { type: 'month', class: 'input', 'aria-label': 'Mês de referência', onfocus: () => { chosen.checked = true; } });
  const currency = h('input', { class: 'input mono', value: 'USD', maxlength: 3, list: 'rc-moedas', 'aria-label': 'Moeda' });
  const fields = kind === 'ipca' ? [
    h('div', { class: 'field' }, h('span', { class: 'field-label' }, 'Mês de referência'),
      h('label', { class: 'fd-check' }, latest, ' O mais recente publicado (atualiza sozinho a cada execução)'),
      h('label', { class: 'fd-check' }, chosen, ' Um mês escolhido: ', month)),
  ] : [
    h('div', { class: 'field' }, h('span', { class: 'field-label' }, 'Moeda'), currency,
      h('datalist', { id: 'rc-moedas' }, CURRENCIES.map((c) => h('option', { value: c }))),
      h('p', { class: 'field-help' }, 'PTAX de venda, boletim de fechamento. Sem cotação no dia (fim de semana, feriado), vale a do último dia útil anterior: o Join avisa quantas linhas usaram.')),
  ];
  const dateMin = (name) => columns.find((c) => c.name === name)?.stats?.min;
  const go = async () => {
    const date = dateSel.value;
    if (!date) return;
    if (kind === 'ipca' && chosen.checked && !month.value) { month.focus(); return; }
    const anchor = node(nodeId);
    const min = dateMin(date);
    const body = {
      receita: kind, valor: valueSel.value, data: date, x: (anchor?.x || 0) + 260, y: anchor?.y || 0,
      referencia: kind === 'ipca' && chosen.checked ? month.value : '',
      moeda: (currency.value || 'USD').toUpperCase(),
      desde: typeof min === 'string' && /^\d{4}-\d{2}-\d{2}/.test(min) ? min.slice(0, 10) : null,
    };
    let recipe;
    try {
      recipe = await api.publicRecipe(body);
    } catch (err) {
      toastError(err, 'Não foi possível montar a receita');
      return;
    }
    insert(nodeId, port, recipe);
    dlg.close();
    toast(recipe.container.title, { kind: 'success', detail: 'As caixas entraram numa etapa, logo depois desta. Execute para ler; Ctrl+Z desfaz.' });
  };
  const dlg = openDialog({
    title: kind === 'ipca' ? 'Corrigir valores pelo IPCA' : 'Converter para dólar pela PTAX',
    size: 'md',
    body: h('div', { class: 'stack-sm rc-dialog' },
      scheme(kind),
      h('div', { class: 'field' }, h('span', { class: 'field-label' }, 'Valor'), valueSel),
      dates.length ? h('div', { class: 'field' }, h('span', { class: 'field-label' }, 'Data de cada valor'), dateSel)
        : h('p', { class: 'pd-note pd-note-err' }, icon('alert', 13), ' Esta tabela não tem coluna de data. A receita precisa da data de cada valor.'),
      ...fields,
      h('p', { class: 'field-help' }, icon('info', 12), ' As caixas inseridas são comuns: dá para abrir e mudar cada uma. A citação da fonte entra no dashboard.')),
    actions: [button({ label: 'Cancelar', onClick: () => dlg.close() }),
      button({ icon: 'plus', label: 'Inserir no fluxo', variant: 'primary', disabled: !dates.length || !numbers.length, onClick: go })],
  });
}

/** Insere a receita depois da caixa: o que vinha depois passa a sair da receita (um passo de Desfazer). */
function insert(nodeId, port, recipe) {
  const after = new Set(descendants(nodeId));
  const shift = recipe.largura + 40;
  // Uma etapa com alguma caixa que vem depois anda inteira, com as caixas de dentro (as fontes de uma receita
  // anterior não estão "depois" no fio, mas estão dentro da etapa dela).
  const inside = (c, n) => n.x >= c.x && n.x <= c.x + c.width && n.y >= c.y && n.y <= c.y + c.height;
  const moving = (store.workflow.containers || []).filter((c) => store.workflow.nodes.some((n) => after.has(n.id) && inside(c, n)));
  for (const c of moving) for (const n of store.workflow.nodes) if (inside(c, n)) after.add(n.id);
  const movingIds = new Set(moving.map((c) => c.id));
  mutate((wf) => {
    for (const n of wf.nodes) if (after.has(n.id)) n.x += shift;
    for (const c of wf.containers || []) if (movingIds.has(c.id)) c.x += shift;
    wf.nodes.push(...recipe.nodes.map((n) => ({ ...n, x: Math.round(n.x / 10) * 10, y: Math.round(n.y / 10) * 10 })));
    for (const e of wf.edges) {
      if (e.source === nodeId && (e.sourceHandle || 'out') === port) { e.source = recipe.saida.node; e.sourceHandle = recipe.saida.port; }
    }
    wf.edges.push(...recipe.edges, { id: `e_${recipe.entrada.node}`, source: nodeId, sourceHandle: port, target: recipe.entrada.node, targetHandle: recipe.entrada.port });
    wf.containers = [...(wf.containers || []), recipe.container];
  }, { affects: recipe.nodes.map((n) => n.id), structural: true });
  select(recipe.saida.node);
  inspect(recipe.saida.node);
}
