// Parar (spec 041): enquanto o fluxo executa, o botão Executar do topo vira Parar. A caixa que está rodando termina;
// as seguintes ficam como "não executado". Num laço, ele para na próxima volta.

import { api } from './api.js';
import { emit, on, store } from './store.js';
import { toast } from './ui.js';

let stopping = false;

export const isStopping = () => stopping;

export function stopRun() {
  if (!store.running || stopping) return;
  stopping = true;
  emit('running'); // o botão mostra "Parando…"
  api.cancelRun(store.workflow.id).catch(() => {});
}

on('running', () => { if (!store.running) stopping = false; });

// Depois de parar: avisa quantas caixas ficaram de fora.
on('execution', () => {
  const stopped = Object.values(store.execution?.node_results || {}).filter((r) => r.extra?.stopped).length;
  if (stopped) toast('Execução interrompida', { detail: `${stopped} caixa(s) não executaram. Clique em Executar para continuar.` });
});
