// Detalhe de uma fonte na vista Dados (spec 028, RF-2803..2804, RF-2810): visão geral, cadastro, uso e explicação.

import { jiraQueryEditor } from './jira_query.js';
import { addJiraNode, jiraConnectionEditor, removeJiraConnection, removeJiraQuery } from './jira_ui.js';
import { tableSkeleton } from './skeleton.js';
import { api } from './api.js';
import { addApiNode, apiEditor, removeApi } from './apis.js';
import { addQueryNode, connectionEditor, queryEditor, removeConnection, removeQuery } from './connections.js';
import { refreshConstants } from './constants.js';
import { constantEditor } from './constants_ui.js';
import { addFolderNode, folderEditor, folderOverview, removeFolderSource } from './folder_sources.js';
import { pdfEditor } from './pdf_editor.js';
import { pdfOverview } from './pdf_overview.js';
import { addPdfNode, confirmRemovePdf, deletePdfSource, duplicatePdfSource, pdfSourceForm, pdfUsable } from './pdf_sources.js';
import { KINDS, usageText, usesOf } from './data_sources.js';
import { usageMap } from './data_map.js';
import { aboutBlock, originalLine, orgChips, titleEditor } from './data_meta.js';
import { addInputNode, openPreview, previewTable, removeDataset, uploadFiles } from './datasets.js';
import { button, fmt, h } from './dom.js';
import { columnQuality, stat } from './data_stats.js';
import { icon } from './icons.js';
import { brand } from './brand.js';
import { shareButton } from './team_definitions.js';

const TONES = { ok: 'check', warn: 'alert', err: 'alert', info: 'link' };

/** Desenho do caminho de cada tipo de fonte: o "Como funciona" (RF-2810). */
const HOW = {
  file: [['Arquivo', 'vendas.xlsx'], ['Tabela', 'linhas e colunas']],
  folder: [['Pasta', 'D:\\Fechamento'], ['Arquivos', 'vendas_*.xlsx'], ['Tabela', 'um embaixo do outro']],
  pdf: [['PDF', 'relatorio_10.pdf'], ['Você marca', 'à direita de “Total”'], ['Tabelas', 'campos, itens, falhas']],
  query: [['Banco', 'conexão'], ['Consulta', 'SELECT …'], ['Tabela', 'linhas e colunas']],
  jira: [['Jira', 'projetos e filtros'], ['Consulta', 'sem escrever JQL'], ['Tabela', 'só o que mudou']],
  jiraconn: [['Token', 'só leitura, no cofre'], ['Consultas', 'uma ou mais'], ['Fluxos', 'Input Data']],
  api: [['Pedido', 'GET /estados'], ['Resposta', '[{"sigla":"SP"…'], ['Tabela', 'linhas e colunas']],
  conn: [['Conexão', 'servidor e senha'], ['Consultas', 'uma ou mais'], ['Fluxos', 'Input Data']],
  const: [['Constante', '[#mes_referencia]'], ['Caixas', 'Formula, Filter…'], ['Execução', 'usa o valor de agora']],
};
const HOW_TEXT = {
  jira: 'A consulta lê demandas, histórico ou comentários do Jira, sem alterar nada, e vira uma tabela no Input Data. A primeira carga traz tudo; as seguintes, só o que mudou. Se cair no meio, continua de onde parou.',
  jiraconn: `A conexão guarda o endereço do Jira e, no cofre do Windows, o e-mail e o token. O ${brand.nome} só faz leituras, e o Jira só mostra o que a sua conta pode ver.`,
  folder: 'Cada arquivo da pasta que casa com o padrão entra inteiro, um embaixo do outro, com as colunas alinhadas pelo nome. A coluna do nome do arquivo diz de onde veio cada linha. Entrou um arquivo novo no mês? A próxima execução já o inclui. A pasta é lida onde está: nada é copiado nem alterado.',
  pdf: `Você marca no próprio documento o que quer, como o total ou uma tabela, e o ${brand.nome} aprende onde achar: à direita de um rótulo, abaixo dele, ou dentro de uma seção. A mesma extração vale para os outros PDFs com o mesmo layout, mesmo que o conteúdo mude de altura. Quando há dúvida (dois totais, por exemplo), nenhum valor é escolhido sozinho: o campo fica Ambíguo. O PDF é lido no seu computador, num processo separado, e nunca é alterado.`,
  file: `Um arquivo enviado vira uma cópia guardada no ${brand.nome}. Um arquivo vinculado é lido onde está, sempre na versão mais nova.`,
  query: 'A consulta pergunta ao banco, só para ler, e a resposta vira uma tabela no Input Data. A senha fica no cofre do Windows.',
  api: `O ${brand.nome} faz o pedido, recebe a resposta e transforma a lista que ela traz numa tabela. Com uma variável, como {sigla}, entra no fluxo como API Loop.`,
  conn: 'A conexão guarda onde fica o banco e a senha, no cofre do Windows. As consultas usam a conexão; os fluxos usam as consultas.',
  const: `Na execução, o ${brand.nome} troca [#nome] pelo valor. Mudou o valor? Só as caixas que usam a constante são refeitas. Cada fluxo guarda o valor que usou, para rodar também num computador sem este cadastro.`,
};

export function howItWorks(kind) {
  const color = KINDS[kind].color;
  return h('div', { class: 'stack-sm' },
    h('div', { class: 'dv-how', role: 'img', 'aria-label': HOW[kind].map(([a]) => a).join(', depois ') },
      HOW[kind].map(([title, sample], i) => h('span', { class: 'dv-step-wrap' },
        i ? h('span', { class: 'dv-link', style: { '--line': color }, 'aria-hidden': 'true' }) : null,
        h('span', { class: 'dv-how-box' }, h('b', {}, title), h('small', { class: 'mono' }, sample))))),
    h('p', { class: 'dv-how-text' }, HOW_TEXT[kind]));
}

function fileOverview(source) {
  const box = h('div', { class: 'stack-md' }, tableSkeleton(8));
  if (source.raw.missing) {
    box.replaceChildren(h('p', { class: 'api-warn' }, icon('alert', 14), ` O arquivo vinculado não foi encontrado em ${source.raw.linked_path}.`));
    return box;
  }
  api.previewDataset(source.id, {}, 100).then((preview) => {
    box.replaceChildren(
      h('div', { class: 'dv-stats' },
        stat('Linhas', preview.row_count === null ? '—' : fmt.int(preview.row_count)),
        stat('Colunas', fmt.int(preview.columns.length)),
        stat('Tamanho', fmt.bytes(preview.info.size_bytes)),
        stat('Atualizado', preview.info.modified_at ? new Date(preview.info.modified_at).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' }) : '—',
          source.raw.linked_path ? 'lido onde está' : `cópia no ${brand.nome}`)),
      h('div', { class: 'dv-split' },
        h('section', { class: 'dv-card dv-grow stack-sm' },
          h('div', { class: 'row space-between' }, h('h3', {}, 'Prévia: primeiras linhas'),
            button({ icon: 'settings', label: 'Opções de leitura', size: 'sm', variant: 'ghost', onClick: () => openPreview(source.id) })),
          previewTable(preview.columns, preview.rows.slice(0, 12))),
        columnQuality(preview)));
  }).catch((err) => box.replaceChildren(h('p', { class: 'text-error' }, icon('alert', 14), ` ${err.message}`)));
  return box;
}

/** Cadastro dentro da vista: o mesmo formulário dos atalhos, com os botões no rodapé. */
function editorPane(source, ctx) {
  const host = { close: () => ctx.refresh(), reopen: (opts) => ctx.mountEditor(source.kind, opts) };
  const done = (saved) => ctx.afterSave(source.kind, saved);
  const editor = source.kind === 'api' ? apiEditor({ source: source.raw, onSaved: done }, host)
    : source.kind === 'jira' ? jiraQueryEditor({ query: source.raw, onSaved: done }, host)
    : source.kind === 'folder' ? folderEditor(source.raw, { onSaved: done }, host)
    : source.kind === 'pdf' ? pdfSourceForm(source.raw, { onSaved: done }, host)
    : source.kind === 'jiraconn' ? jiraConnectionEditor(source.raw, { onSaved: done }, host)
    : source.kind === 'query' ? queryEditor({ query: source.raw, onSaved: done }, host)
      : source.kind === 'const' ? constantEditor(source.raw, { uses: usesOf(source), onSaved: done }, host)
        : connectionEditor(source.raw, { onSaved: done }, host);
  return h('div', { class: 'dv-editor' }, editor.body, h('footer', { class: 'dv-editor-actions' }, editor.actions));
}

function actionsFor(source, ctx) {
  const add = (fn) => () => { fn(); ctx.showDesigner(); };
  const replace = h('input', { type: 'file', hidden: true,
    onchange: (e) => { uploadFiles([...e.target.files], { overwrite: true }).then(ctx.refresh); e.target.value = ''; } });
  const list = {
    file: [
      button({ icon: 'plus', label: 'Adicionar ao fluxo', disabled: source.raw.missing, onClick: add(() => addInputNode(source.id)) }),
      source.raw.linked_path ? null : button({ icon: 'upload', label: 'Enviar nova versão', onClick: () => replace.click() }),
      button({ icon: 'trash', label: source.raw.linked_path ? 'Remover vínculo' : 'Excluir', variant: 'ghost', onClick: () => ctx.remove(source, () => removeDataset(source.raw)) }),
      replace,
    ],
    query: [
      button({ icon: 'plus', label: 'Adicionar ao fluxo', onClick: add(() => addQueryNode(source.raw)) }),
      button({ icon: 'trash', label: 'Excluir', variant: 'ghost', onClick: () => ctx.remove(source, () => removeQuery(source.raw)) }),
    ],
    api: [
      button({ icon: 'plus', label: source.loop ? 'Adicionar API Loop ao fluxo' : 'Adicionar ao fluxo', onClick: add(() => addApiNode(source.raw)) }),
      button({ icon: 'trash', label: 'Excluir', variant: 'ghost', onClick: () => ctx.remove(source, () => removeApi(source.raw)) }),
    ],
    folder: [
      button({ icon: 'plus', label: 'Adicionar ao fluxo', disabled: source.state.tone === 'err', onClick: add(() => addFolderNode(source.raw)) }),
      button({ icon: 'trash', label: 'Esquecer a pasta', variant: 'ghost', onClick: () => ctx.remove(source, () => removeFolderSource(source.raw)) }),
    ],
    pdf: [
      button({ icon: 'plus', label: 'Adicionar ao fluxo', disabled: !pdfUsable(source.raw), title: source.raw.status?.draft ? 'Marque ao menos um campo antes' : 'Adicionar ao fluxo', onClick: add(() => addPdfNode(source.raw)) }),
      ctx.tab === 'extract' ? null : button({ icon: 'target', label: 'Preparar extração', onClick: () => ctx.openPdf() }),
      button({ icon: 'copy', label: 'Duplicar', variant: 'ghost', onClick: async () => { const copy = await duplicatePdfSource(source.raw); if (copy) ctx.afterSave('pdf', copy, 'edit'); } }),
      button({ icon: 'trash', label: 'Excluir', variant: 'ghost', onClick: async () => { if (await confirmRemovePdf(source.raw)) ctx.remove(source, () => deletePdfSource(source.raw)); } }),
    ],
    const: [
      button({ icon: 'trash', label: 'Excluir', variant: 'ghost',
        onClick: () => ctx.remove(source, async () => { await api.deleteConstant(source.id); await refreshConstants(); }) }),
    ],
    jira: [
      button({ icon: 'plus', label: 'Adicionar ao fluxo', onClick: add(() => addJiraNode(source.raw)) }),
      button({ icon: 'trash', label: 'Excluir', variant: 'ghost', onClick: () => ctx.remove(source, () => removeJiraQuery(source.raw)) }),
    ],
    jiraconn: [
      button({ icon: 'plus', label: 'Nova consulta', onClick: () => ctx.newSource('jira', { connectionId: source.id }) }),
      button({ icon: 'trash', label: 'Excluir', variant: 'ghost', onClick: () => ctx.remove(source, () => removeJiraConnection(source.raw)) }),
    ],
    conn: [
      button({ icon: 'plus', label: 'Nova consulta', onClick: () => ctx.newSource('query', { connectionId: source.id }) }),
      button({ icon: 'trash', label: 'Excluir', variant: 'ghost', onClick: () => ctx.remove(source, () => removeConnection(source.raw)) }),
    ],
  };
  return list[source.kind].filter(Boolean);
}

/** O editor de PDF guarda estado (documento aberto, desfazer): sobrevive aos redesenhos da vista enquanto a fonte e a aba são as mesmas. */
let mounted = null;
function extractPane(source, ctx) {
  if (mounted?.id !== source.id) {
    mounted?.editor.destroy();
    mounted = { id: source.id, editor: pdfEditor(source.raw, { doc: ctx.pdfDoc }) };
  } else if (ctx.pdfDoc) {
    mounted.editor.open(ctx.pdfDoc);
  }
  return mounted.editor.el;
}

/** `ctx`: tab, setTab, refresh, mountEditor, afterSave, remove, newSource, openFlow, showDesigner. */
export function sourceDetail(source, ctx) {
  const kind = KINDS[source.kind];
  const uses = usesOf(source);
  const tabs = source.kind === 'file'
    ? [['overview', 'Visão geral'], ['usage', 'Onde é usada'], ['how', 'Como funciona']]
    : source.kind === 'folder' ? [['overview', 'Visão geral'], ['edit', 'Cadastro'], ['usage', 'Onde é usada'], ['how', 'Como funciona']]
    : source.kind === 'pdf' ? [['overview', 'Visão geral'], ['extract', 'Extração'], ['edit', 'Cadastro'], ['usage', 'Onde é usada'], ['how', 'Como funciona']]
    : [['overview', 'Cadastro'], ['usage', 'Onde é usada'], ['how', 'Como funciona']];
  const tab = tabs.some(([k]) => k === ctx.tab) ? ctx.tab : 'overview';
  if (mounted && !(source.kind === 'pdf' && tab === 'extract' && mounted.id === source.id)) { mounted.editor.destroy(); mounted = null; }
  const content = {
    overview: () => (source.kind === 'file' ? fileOverview(source) : source.kind === 'folder' ? folderOverview(source.raw)
      : source.kind === 'pdf' ? pdfOverview(source.raw, { openEditor: (doc) => ctx.openPdf(doc || null), refresh: ctx.refresh, showDesigner: ctx.showDesigner })
        : editorPane(source, ctx)),
    extract: () => extractPane(source, ctx),
    edit: () => editorPane(source, ctx),
    usage: () => usageMap(source, uses, ctx.openFlow),
    how: () => howItWorks(source.kind),
  }[tab]();
  return h('div', { class: ['dv-detail', tab === 'extract' && 'pe-active'] },
    h('header', { class: 'dv-head' },
      h('span', { class: 'dv-head-icon', style: { '--kind': kind.color } }, icon(kind.icon, 22)),
      h('div', { class: 'dv-head-text' }, titleEditor(source, { editing: ctx.rename }),
        h('p', {}, `${kind.one[0].toUpperCase()}${kind.one.slice(1)} · `, originalLine(source), source.info.label ? ' · ' : null, source.meta),
        h('div', { class: 'dv-head-chips' },
          h('span', { class: ['dv-chip', `tone-${source.state.tone}`] }, icon(TONES[source.state.tone], 12), source.state.label),
          h('button', { type: 'button', class: ['dv-chip', 'dv-chip-use', !uses.length && 'none'], onclick: () => ctx.setTab('usage') }, usageText(source)),
          orgChips(source))),
      h('div', { class: 'dv-head-actions' }, actionsFor(source, ctx), shareButton(source, ctx.refresh))),
    aboutBlock(source),
    h('nav', { class: 'dv-tabs', role: 'tablist', 'aria-label': 'Seções da fonte' }, tabs.map(([k, label]) => h('button', {
      type: 'button', role: 'tab', class: 'dv-tab', 'aria-selected': String(k === tab), dataset: { tab: k },
      onclick: () => ctx.setTab(k),
    }, label))),
    h('div', { class: 'dv-body' }, content));
}
