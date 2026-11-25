// Dados públicos guardados na vista Dados e o aviso Dados novos (spec 049, RF-4915, RF-4935).
// A conferência com os órgãos acontece só junto com a situação, ao abrir o catálogo (constituição 1.8.1, RF-4921):
// aqui a vista Dados e o canvas só comparam o que o órgão informou da última vez com a leitura guardada.

import { api } from './api.js';
import { emit, on, store } from './store.js';

let saved = []; // fontes guardadas na vista Dados, com a novidade e a situação do órgão
let byNode = {}; // caixa Dados públicos do fluxo aberto → { novo, texto, ... }

export const savedSources = () => saved;
export const newsOf = (nodeId) => byNode[nodeId] || null;

const publicNodes = () => (store.workflow?.nodes || []).filter((n) => n.type === 'io.public_data' && n.config?.fonte?.id);

/** A pasta Dados públicos da vista Dados (sem rede). */
export async function refreshSaved() {
  try {
    saved = (await api.publicSaved()).fontes;
  } catch {
    saved = [];
  }
  emit('public-saved');
  return saved;
}

/** O aviso nas caixas do fluxo aberto (sem rede). */
export async function refreshNodeNews() {
  const wf = store.workflow;
  const nodes = publicNodes();
  if (!nodes.length) {
    byNode = {};
    emit('public-news');
    return;
  }
  try {
    const answer = await api.publicNews(nodes.map((n) => ({ id: n.config.fonte.id, escolhas: n.config.fonte.escolhas || {} })));
    if (store.workflow !== wf) return;
    byNode = Object.fromEntries(nodes.map((n, i) => [n.id, answer.novidades[i]]));
  } catch {
    byNode = {};
  }
  emit('public-news');
}

/** Junto com a situação, ao abrir o catálogo: pergunta a cada órgão a última atualização das fontes em uso. */
const extraIds = []; // outras fontes que pedem a conferência (o CNPJ baixado, para o mês novo)
export const addNewsIds = (fn) => extraIds.push(fn);

export async function checkNews() {
  const ids = [...publicNodes().map((n) => n.config.fonte.id), ...saved.map((s) => s.fonte.id), ...extraIds.flatMap((fn) => fn())];
  if (!ids.length) return;
  try {
    await api.publicNewsCheck([...new Set(ids)].slice(0, 60));
  } catch {
    return; // sem conexão: o aviso fica como estava
  }
  await Promise.all([refreshNodeNews(), refreshSaved()]);
}

export function initPublicNews() {
  on('workflow:loaded', () => { refreshNodeNews().catch(() => {}); });
  on('execution', () => { refreshNodeNews().catch(() => {}); }); // depois de ler de novo, o aviso some
  refreshSaved().catch(() => {});
}
