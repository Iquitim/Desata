// Cartões "Quando empatar" do Rank (spec 044, RF-4402): cada jeito mostra o próprio exemplo, sem precisar ler.

import { h } from './dom.js';

export const RANK_METHODS = [
  { id: 'row', name: 'Posição única', example: ['1', '2', '3', '4'], tie: [], hint: 'No empate, quem chegou antes fica na frente', sql: 'ROW_NUMBER' },
  { id: 'rank', name: 'Empate divide e pula', example: ['1', '1', '3', '4'], tie: [0, 1], hint: 'Dois em 1º; o próximo é o 3º', sql: 'RANK' },
  { id: 'dense', name: 'Empate divide sem pular', example: ['1', '1', '2', '3'], tie: [0, 1], hint: 'Dois em 1º; o próximo é o 2º', sql: 'DENSE_RANK' },
];

export function rankMethod(field, value, set) {
  const current = value || 'rank';
  return h('div', { class: 'rk-cards', role: 'radiogroup', 'aria-label': field.title }, RANK_METHODS.map((m) => h('button', {
    type: 'button', role: 'radio', class: ['rk-card', current === m.id && 'active'], 'aria-checked': String(current === m.id),
    dataset: { method: m.id }, onclick: () => set(m.id),
  },
  h('span', { class: 'rk-example', 'aria-hidden': 'true' }, m.example.map((n, i) => h('span', { class: ['rk-pos', m.tie.includes(i) && 'tie'] }, n))),
  h('b', {}, m.name),
  h('small', {}, m.hint),
  h('small', { class: 'rk-sql mono' }, m.sql))));
}
