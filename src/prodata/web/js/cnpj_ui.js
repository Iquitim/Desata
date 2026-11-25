// CNPJ na tela (spec 049, RF-4951..4953, RF-4956, RF-4972): o diálogo Baixar o CNPJ (partes, tamanhos, pasta
// escolhida e espaço livre) e a faixa de downloads da vista Dados, com Pausar, Continuar e Cancelar.
// A faixa se atualiza sozinha, sem redesenhar a vista inteira (quem estiver editando uma fonte não perde o foco).

import { api } from './api.js';
import { chooseFolder } from './desktop.js';
import { button, h } from './dom.js';
import { refreshFolderSources } from './folder_sources.js';
import { refreshOrganization } from './organization.js';
import { addNewsIds } from './public_news.js';
import { icon } from './icons.js';
import { emit, on } from './store.js';
import { confirmDialog, openDialog, toast, toastError } from './ui.js';

export const CNPJ_ID = 'receita.cnpj/dados-abertos';
const ACTIVE = new Set(['baixando', 'descompactando']);
const state = { jobs: [], newest: null, timer: null, loaded: false };
let section = null; // o elemento da faixa na vista Dados

const size = (n) => {
  if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} GB`;
  if (n >= 1024 ** 2) return `${Math.round(n / 1024 ** 2).toLocaleString('pt-BR')} MB`;
  return `${Math.max(1, Math.round(n / 1024)).toLocaleString('pt-BR')} KB`;
};
const duration = (s) => (s >= 3600 ? `${Math.floor(s / 3600)} h ${Math.round((s % 3600) / 60)} min` : s >= 60 ? `${Math.round(s / 60)} min` : `${s} s`);

/** O CNPJ de um código de fonte do fluxo: ``folder:cnpj_2026_11_estabelecimentos`` → mês e grupo. */
export function cnpjOfKey(key) {
  const m = /^folder:cnpj_(\d{4})_(\d{2})_([a-z]+)$/.exec(key || '');
  return m ? { mes: `${m[1]}-${m[2]}`, grupo: m[3] } : null;
}

// ------------------------------------------------------------------ estado dos downloads

export const downloadJobs = () => state.jobs;
export const hasCnpjDownloads = () => state.jobs.some((j) => j.estado === 'concluido');

export async function refreshDownloads() {
  try {
    const answer = await api.downloads();
    state.jobs = answer.downloads;
    state.newest = answer.mes_mais_novo;
  } catch {
    state.jobs = [];
  }
  state.loaded = true;
  paint();
  schedule();
  return state.jobs;
}

function schedule() {
  clearTimeout(state.timer);
  if (state.jobs.some((j) => ACTIVE.has(j.estado))) state.timer = setTimeout(refreshDownloads, 1000);
  else if (state.wasActive) { // terminou: as fontes de pasta prontas entram na lista, na pasta CNPJ AAAA-MM
    Promise.all([refreshFolderSources(), refreshOrganization()]).catch(() => {});
  }
  state.wasActive = state.jobs.some((j) => ACTIVE.has(j.estado));
}

async function act(job, action) {
  if (action === 'cancelar') {
    const ok = await confirmDialog({
      title: `Cancelar o download do CNPJ ${job.mes}?`,
      message: 'O que já foi baixado deste download é apagado. O que você pôs na pasta continua lá.',
      confirm: 'Cancelar o download', danger: true,
    });
    if (!ok) return;
  }
  try {
    await api.downloadAction(job.id, action);
  } catch (err) {
    toastError(err, 'Não foi possível');
  }
  await refreshDownloads();
}

// ------------------------------------------------------------------ faixa na vista Dados

const LABELS = { baixando: 'Baixando', descompactando: 'Conferindo e descompactando', pausado: 'Pausado', erro: 'Parou', concluido: 'Pronto' };

function jobCard(job) {
  const pct = job.total ? Math.round((job.baixado / job.total) * 100) : 0;
  const active = ACTIVE.has(job.estado);
  const current = job.parte_atual || job.partes.find((p) => p.estado === 'descompactando')?.arquivo;
  const facts = job.estado === 'baixando'
    ? [`${size(job.baixado)} de ${size(job.total)}`, job.velocidade ? `${size(job.velocidade)}/s` : null,
      job.restante_s != null ? `faltam ${duration(job.restante_s)}` : null].filter(Boolean).join(' · ')
    : job.estado === 'descompactando'
      ? `${job.partes.filter((p) => p.estado === 'pronto').length} de ${job.partes.length} arquivos prontos`
      : job.estado === 'concluido' ? `${job.fontes?.length || 0} fonte(s) na pasta CNPJ ${job.mes} da lista` : `${size(job.baixado)} de ${size(job.total)}`;
  return h('article', { class: ['cnpj-job', `is-${job.estado}`], dataset: { id: job.id } },
    h('div', { class: 'cnpj-job-head' }, icon(job.estado === 'concluido' ? 'check-circle' : job.estado === 'erro' ? 'alert' : 'download', 14),
      h('b', {}, `CNPJ ${job.mes}`), h('span', { class: 'cnpj-job-state' }, LABELS[job.estado] || job.estado),
      current && active ? h('span', { class: 'muted ellipsis' }, current) : null),
    job.estado !== 'concluido' ? h('div', { class: 'cnpj-progress', role: 'progressbar', 'aria-valuenow': String(pct), 'aria-valuemin': '0', 'aria-valuemax': '100',
      'aria-label': `Download do CNPJ ${job.mes}` }, h('span', { style: { width: `${pct}%` } })) : null,
    h('small', { class: 'cnpj-job-facts' }, facts),
    job.motivo && !active ? h('p', { class: 'cnpj-job-why' }, job.motivo) : null,
    job.avisos?.length ? job.avisos.map((a) => h('p', { class: 'cnpj-job-why' }, icon('alert', 12), ` ${a}`)) : null,
    h('div', { class: 'row cnpj-job-actions' },
      job.estado === 'baixando' ? button({ icon: 'pause', label: 'Pausar', size: 'sm', onClick: () => act(job, 'pausar') }) : null,
      ['pausado', 'erro'].includes(job.estado) ? button({ icon: 'play', label: 'Continuar', size: 'sm', variant: 'primary', onClick: () => act(job, 'continuar') }) : null,
      ['baixando', 'pausado', 'erro'].includes(job.estado) ? button({ label: 'Cancelar', size: 'sm', variant: 'ghost', onClick: () => act(job, 'cancelar') }) : null));
}

function newMonthBanner() {
  const done = state.jobs.filter((j) => j.estado === 'concluido').map((j) => j.mes).sort();
  const latest = done[done.length - 1];
  if (!latest || !state.newest || state.newest <= latest || state.jobs.some((j) => j.mes === state.newest && j.estado !== 'cancelado')) return null;
  const last = state.jobs.find((j) => j.mes === latest && j.estado === 'concluido');
  const groups = [...new Set(last.partes.map((p) => p.grupo))];
  return h('div', { class: 'cnpj-new', role: 'status' }, icon('sparkles', 14),
    h('span', {}, h('b', {}, `Dados novos: ${state.newest} disponível. `), `Você tem o CNPJ ${latest}.`),
    button({ icon: 'download', label: 'Baixar…', size: 'sm', onClick: () => openCnpjDownload({ mes: state.newest, grupos: groups, pasta: last.pasta }) }));
}

function paint() {
  if (!section) return;
  const shown = state.jobs.filter((j) => j.estado !== 'cancelado').slice(0, 3);
  const pendingNote = shown.some((j) => j.estado === 'pausado' && j.motivo?.includes('fechado'))
    ? h('p', { class: 'field-help' }, 'O programa foi fechado no meio do download. Use Continuar para retomar do ponto em que parou.') : null;
  section.hidden = !shown.length && !newMonthBanner();
  section.replaceChildren(...[newMonthBanner(), pendingNote, ...shown.filter((j) => j.estado !== 'concluido' || recent(j)).map(jobCard)].filter(Boolean));
}

/** Um download pronto continua à vista por um dia: depois, a pasta CNPJ AAAA-MM da lista basta. */
const recent = (job) => Date.now() - new Date(job.criado_em).getTime() < 86_400_000;

/** A faixa no alto da lista da vista Dados (o mesmo elemento entre redesenhos). */
export function downloadsSection() {
  if (!section) section = h('section', { class: 'cnpj-jobs', 'aria-label': 'Downloads do CNPJ', hidden: true });
  paint();
  if (!state.loaded) refreshDownloads();
  return section;
}

// ------------------------------------------------------------------ diálogo Baixar o CNPJ

/**
 * Baixar o CNPJ (RF-4951, RF-4952): o mês (o mais recente, ou o pedido pelo fluxo de um colega), as partes com o
 * tamanho de cada uma, a pasta escolhida e o espaço livre. ``grupos``: já marcados; ``pasta``: a pasta-mãe de antes.
 */
export async function openCnpjDownload({ mes = null, grupos = null, pasta = '' } = {}) {
  const body = h('div', { class: 'cnpj-dialog' }, h('p', { class: 'pd-loading' }, 'Conferindo a pasta da Receita…'));
  const startBtn = button({ icon: 'download', label: 'Baixar', variant: 'primary', disabled: true, onClick: () => start() });
  const dlg = openDialog({ title: 'Baixar o cadastro de empresas (CNPJ)', body, size: 'lg', actions: [button({ label: 'Cancelar', onClick: () => dlg.close() }), startBtn] });
  let info;
  try {
    info = await api.publicCnpj(mes);
  } catch (err) {
    body.replaceChildren(h('p', { class: 'pd-note pd-note-err' }, icon('alert', 13), ` ${err.message}`));
    return;
  }
  const marked = new Set(info.grupos.filter((g) => (grupos ? grupos.includes(g.id) : g.padrao)).map((g) => g.id));
  const st = { folder: pasta, keep: false, plan: null, planning: false };
  const files = () => info.grupos.filter((g) => marked.has(g.id)).flatMap((g) => g.arquivos.map((a) => a.arquivo));
  const total = () => info.grupos.filter((g) => marked.has(g.id)).reduce((n, g) => n + g.tamanho, 0);

  const planBox = h('div', { class: 'cnpj-plan' });
  const folderInput = h('input', { class: 'input', readonly: true, value: st.folder, placeholder: 'Escolha a pasta: o CNPJ é grande e fica neste computador', 'aria-label': 'Pasta' });
  const totalEl = h('b', {});

  async function plan() {
    totalEl.textContent = size(total());
    st.plan = null;
    startBtn.disabled = true;
    if (!st.folder || !files().length) {
      planBox.replaceChildren(h('p', { class: 'field-help' }, files().length ? 'Escolha a pasta para conferir o espaço livre.' : 'Marque pelo menos uma parte.'));
      return;
    }
    planBox.replaceChildren(h('p', { class: 'field-help' }, 'Conferindo o espaço livre…'));
    try {
      st.plan = await api.downloadPlan({ mes: info.mes, arquivos: files(), pasta: st.folder, manter_zips: st.keep });
    } catch (err) {
      planBox.replaceChildren(h('p', { class: 'pd-note pd-note-err' }, icon('alert', 13), ` ${err.message}`));
      return;
    }
    const p = st.plan;
    const used = Math.min(100, (p.necessario / Math.max(1, p.livre)) * 100);
    planBox.replaceChildren(
      h('div', { class: 'cnpj-disk', role: 'img', 'aria-label': `Precisa de ${size(p.necessario)}; livres ${size(p.livre)}` },
        h('span', { class: ['cnpj-disk-fill', !p.cabe && 'is-short'], style: { width: `${Math.max(2, used)}%` } })),
      h('p', { class: p.cabe ? 'field-help' : 'pd-note pd-note-err' },
        p.cabe ? icon('check-circle', 12) : icon('alert', 12),
        ` Precisa de uns ${size(p.necessario)} (ZIPs e arquivos descompactados); há ${size(p.livre)} livres. `,
        p.cabe ? `Os arquivos vão para ${p.destino}.` : 'Escolha outra pasta ou menos partes.'));
    startBtn.disabled = !p.cabe;
  }

  const groupRow = (g) => h('label', { class: 'cnpj-group' },
    h('input', { type: 'checkbox', checked: marked.has(g.id), onchange: (e) => { if (e.target.checked) marked.add(g.id); else marked.delete(g.id); plan(); } }),
    h('span', { class: 'cnpj-group-text' }, h('b', {}, g.nome), h('small', { class: 'muted' }, g.descricao)),
    h('span', { class: 'cnpj-group-size' }, g.arquivos.length > 1 ? `${g.arquivos.length} arquivos · ${size(g.tamanho)}` : size(g.tamanho)));

  async function start() {
    startBtn.disabled = true;
    try {
      await api.downloadStart({ mes: info.mes, arquivos: files(), pasta: st.folder, manter_zips: st.keep });
    } catch (err) {
      toastError(err, 'Não foi possível começar o download');
      startBtn.disabled = false;
      return;
    }
    dlg.close();
    toast(`O download do CNPJ ${info.mes} começou`, { kind: 'success', detail: 'Acompanhe na vista Dados: dá para pausar e continuar depois, mesmo fechando o programa.' });
    emit('downloads');
    await refreshDownloads();
  }

  const older = info.mes !== info.mais_recente;
  body.replaceChildren(
    h('p', {}, `Mês ${info.mes} da Receita Federal`, older ? ` (o mais recente é ${info.mais_recente})` : ' (o mais recente)',
      '. Marque as partes: Estabelecimentos tem endereço, CNAE e situação; Empresas, a razão social e o capital.'),
    h('div', { class: 'cnpj-groups' }, info.grupos.map(groupRow)),
    h('p', { class: 'cnpj-total' }, 'Total marcado: ', totalEl),
    h('div', { class: 'field' }, h('span', { class: 'field-label' }, 'Onde salvar'),
      h('div', { class: 'row' }, folderInput,
        button({ icon: 'folder', label: 'Escolher pasta…', onClick: async () => {
          const chosen = await chooseFolder(st.folder, 'Onde salvar o CNPJ', 'D:\\Dados');
          if (chosen) { st.folder = chosen; folderInput.value = chosen; plan(); }
        } })),
      h('p', { class: 'field-help' }, 'O programa cria ali a subpasta CNPJ-', info.mes, '. Não vale a pasta de dados do programa nem a de um espaço da equipe.')),
    h('label', { class: 'toggle-row' },
      h('input', { type: 'checkbox', onchange: (e) => { st.keep = e.target.checked; plan(); } }),
      h('span', {}, 'Manter os ZIPs depois de descompactar (ocupa mais espaço)')),
    planBox);
  plan();
}

export function initCnpj() {
  on('downloads', () => paint());
  addNewsIds(() => (hasCnpjDownloads() ? [CNPJ_ID] : [])); // mês novo (RF-4956), junto com a conferência do catálogo
  refreshDownloads();
}
