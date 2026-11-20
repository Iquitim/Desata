// Aviso de fim de execução (spec 044, RF-4441..4443): uma caixinha com as cores da marca quando termina a execução
// pedida pela pessoa. Com a janela em segundo plano, fica até a pessoa voltar e fechar. Exibir › liga e desliga.
// A mesma caixinha avisa quando uma execução agendada falhou (RF-4435).

import { emit } from './store.js';
import { button, fmt, h, persist, storage } from './dom.js';
import { icon } from './icons.js';

const KEY = 'prodata.view.runNotice';
const VISIBLE_MS = 6000;
let on = storage(KEY, true) !== false;
let current = null;

export const runNoticeOn = () => on;

export function setRunNotice(value) {
  on = Boolean(value);
  persist(KEY, on);
  if (!on) current?.close();
  emit('runNotice');
}

const plural = (n, one, many) => `${fmt.int(n)} ${n === 1 ? one : many}`;
const seconds = (ms) => (ms < 1000 ? `${Math.max(1, Math.round(ms))} ms` : ms < 60000 ? `${fmt.number(ms / 1000, 1)} s` : `${Math.floor(ms / 60000)} min ${Math.round((ms % 60000) / 1000)} s`);

/** O que dizer sobre a execução que acabou de terminar. */
export function summarize(report) {
  const results = Object.values(report?.node_results || {});
  const count = (fn) => results.filter(fn).length;
  return {
    executed: count((r) => r.status === 'executed'),
    cached: count((r) => r.status === 'cached'),
    errors: count((r) => r.status === 'error'),
    stopped: count((r) => r.extra?.stopped),
    files: count((r) => r.extra?.exported_path || r.extra?.exported_file),
    ms: report?.total_elapsed_ms || 0,
  };
}

/**
 * A caixinha com as cores da marca. `tone`: done, error ou stopped. `sticky`: só fecha pela pessoa.
 * Em primeiro plano, some sozinha; em segundo plano, espera a pessoa voltar e fechar.
 */
export function brandNotice({ tone = 'done', title, flow, time = '', detail = '', action = null, sticky = false }) {
  const close = () => {
    if (!el.isConnected) return;
    el.classList.add('leaving');
    setTimeout(() => el.remove(), 180);
    if (current?.el === el) current = null;
  };
  const el = h('div', { class: ['run-notice', `run-notice-${tone}`], role: tone === 'error' ? 'alert' : 'status', 'aria-live': 'polite' },
    h('div', { class: 'run-notice-band' },
      h('img', { class: 'run-notice-logo', src: '/marca/icone-escuro.png', alt: '', onerror: (e) => e.target.remove() }),
      h('span', { class: 'run-notice-icon' }, icon(tone === 'error' ? 'alert' : tone === 'stopped' ? 'pause' : 'check-circle', 16)),
      h('strong', { class: 'run-notice-title' }, title),
      button({ icon: 'x', title: 'Fechar', variant: 'ghost', size: 'sm', onClick: close })),
    h('div', { class: 'run-notice-body' },
      h('div', { class: 'run-notice-flow' }, flow, time ? h('span', { class: 'run-notice-time' }, ` · ${time}`) : null),
      detail ? h('div', { class: 'run-notice-detail' }, detail) : null,
      action ? h('div', { class: 'run-notice-actions' },
        button({ icon: action.icon, label: action.label, size: 'sm', onClick: () => { action.onClick(); close(); } })) : null));
  (document.getElementById('toasts') || document.body).append(el); // empilha com os outros avisos, sem se sobrepor
  let timer = null;
  const arm = () => { clearTimeout(timer); timer = setTimeout(close, tone === 'error' ? VISIBLE_MS * 2 : VISIBLE_MS); };
  if (!sticky && document.hasFocus() && !document.hidden) arm();
  el.addEventListener('mouseenter', () => clearTimeout(timer));
  el.addEventListener('mouseleave', () => { if (!sticky && document.hasFocus()) arm(); });
  return { el, close };
}

/** Fim da execução pedida pela pessoa. `onLog` abre o Log. Desligado em Exibir: não mostra (devolve null). */
export function showRunNotice(report, workflowName, { onLog } = {}) {
  if (!on || !report) return null;
  current?.close();
  const s = summarize(report);
  const parts = [];
  if (s.executed) parts.push(plural(s.executed, 'caixa executada', 'caixas executadas'));
  if (s.cached && !s.executed) parts.push('nada mudou: resultados guardados');
  else if (s.cached) parts.push(`${fmt.int(s.cached)} do cache`);
  if (s.stopped) parts.push(`${fmt.int(s.stopped)} ficaram de fora`);
  if (s.files) parts.push(plural(s.files, 'arquivo gravado', 'arquivos gravados'));
  current = brandNotice({
    tone: s.errors ? 'error' : s.stopped ? 'stopped' : 'done',
    title: s.errors ? `Terminou com ${plural(s.errors, 'erro', 'erros')}` : s.stopped ? 'Execução interrompida' : 'Fluxo executado',
    flow: workflowName || 'Fluxo',
    time: seconds(s.ms),
    detail: parts.join(' · '),
    action: onLog ? { icon: s.errors ? 'alert' : 'list', label: s.errors ? 'Ver os erros' : 'Ver o Log', onClick: onLog } : null,
  });
  return current;
}
