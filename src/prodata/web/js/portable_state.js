// O que falta neste computador, por caixa (spec 040). Sem imports: o canvas lê daqui sem puxar a vista Dados.

const byNode = new Map(); // caixa → a fonte que falta (ou vem da amostra)

export function setSourceProblems(sources) {
  byNode.clear();
  for (const s of sources) if (s.state !== 'ok') s.nodes.forEach((n) => byNode.set(n, s));
}

export const sourceProblem = (nodeId) => byNode.get(nodeId) || null;
