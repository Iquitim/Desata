// Leitura que passa de 1/4 da memória (spec 049, RF-4957): a caixa para antes e a pessoa escolhe Parar ou Continuar
// assim mesmo. Acima disso o Windows usa o disco como memória e o computador inteiro fica lento. A resposta vale só
// para a execução seguinte: na próxima vez, o programa pergunta de novo.

import { button, h } from './dom.js';
import { icon } from './icons.js';
import { node } from './store.js';
import { openDialog } from './ui.js';

const gb = (n) => `${(n / 1024 ** 3).toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} GB`;

/** A barra: a memória do computador, a marca de 1/4 e quanto a leitura deve ocupar. */
function bar(estimate, memory) {
  const pct = Math.min(100, (estimate / memory) * 100);
  return h('div', { class: 'mem-bar', role: 'img', 'aria-label': `A leitura deve ocupar ${gb(estimate)} de ${gb(memory)} de memória` },
    h('div', { class: 'mem-track' },
      h('span', { class: ['mem-fill', pct > 50 && 'is-high'], style: { width: `${Math.max(2, pct)}%` } }),
      h('span', { class: 'mem-mark', style: { left: '25%' }, title: '1/4 da memória' })),
    h('div', { class: 'mem-legend' },
      h('span', {}, `Leitura: cerca de ${gb(estimate)}`),
      h('span', { class: 'mem-quarter' }, '1/4'),
      h('span', {}, `Memória do computador: ${gb(memory)}`)));
}

/**
 * Depois de executar: as caixas que pararam com a pergunta de memória. Devolve os ids liberados (Continuar assim
 * mesmo) ou ``[]`` (Parar). Uma pergunta por vez, com o nome da caixa.
 */
export async function askMemory(report) {
  const asks = Object.entries(report?.node_results || {}).filter(([, r]) => r.extra?.pergunta_memoria);
  if (!asks.length) return [];
  const [id, result] = asks[0];
  const { estimado, memoria } = result.extra.pergunta_memoria;
  const label = node(id)?.label || id;
  return new Promise((resolve) => {
    let answer = [];
    const { close } = openDialog({
      title: 'Esta leitura passa de 1/4 da memória',
      size: 'md',
      body: h('div', { class: 'stack-sm mem-ask' },
        h('p', {}, h('b', {}, label), ': ', result.error),
        bar(estimado, memoria),
        h('p', { class: 'field-help' }, icon('info', 12),
          ' Com um filtro na fonte (UF, município, CNAE, situação ou CNPJ), o programa lê os arquivos aos poucos e guarda só as linhas que passam.'),
        asks.length > 1 ? h('p', { class: 'field-help' }, `Outras ${asks.length - 1} caixa(s) também pararam: a resposta vale para todas.`) : null),
      actions: [
        button({ label: 'Parar', variant: 'primary', onClick: () => close() }),
        button({ label: 'Continuar assim mesmo', onClick: () => { answer = asks.map(([n]) => n); close(); } }),
      ],
      onClose: () => resolve(answer),
    });
  });
}
