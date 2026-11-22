// Juntar duas versões caixa por caixa (spec 048, RF-4821..4826): o que só um mudou entra sozinho; onde os dois mexeram
// na mesma caixa, a pessoa escolhe a dela ou a do colega, com a prévia do resultado. Aplicar entra como mudança não
// salva (Desfazer volta), e as duas versões de origem continuam em Versões anteriores.

import { api } from './api.js';
import { button, debounce, h } from './dom.js';
import { icon } from './icons.js';
import { store } from './store.js';
import { openDialog, toast, toastError } from './ui.js';
import { preview, restoreVersion } from './versions_dialog.js';

const CASES = {
  mudaram_os_dois: 'Vocês dois mudaram esta caixa.',
  minha_saiu: 'Você excluiu esta caixa, e o colega mudou.',
  dele_saiu: 'O colega excluiu esta caixa, e você mudou.',
  sem_base: 'Diferente nas duas versões (sem a versão de origem para comparar).',
};

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

/** ``outra``: "trabalho" (a versão do espaço agora) ou o id de uma versão anterior; ``nome``: de quem é a outra. */
export async function openMergeDialog({ outra = 'trabalho', nome = 'o colega' } = {}) {
  const { space, workflow } = store;
  if (!space || !workflow) return;
  const choices = {};
  const body = h('div', { class: 'mg-layout' }, h('p', { class: 'muted' }, 'Comparando as duas versões…'));
  const applyBtn = button({ icon: 'check', label: 'Aplicar', variant: 'primary', disabled: true });
  const { close } = openDialog({
    title: `Juntar com a versão de ${nome}`,
    size: 'xl',
    body,
    actions: [
      h('span', { class: 'muted small mg-foot' }, 'O resultado entra como mudança não salva: Desfazer volta, e as duas versões continuam em Versões anteriores.'),
      button({ label: 'Cancelar', onClick: () => close() }),
      applyBtn,
    ],
  });
  const request = () => ({ atual: store.workflow, outra, base: space.base || null, escolhas: { ...choices } });

  let plan = null;
  const sidePreview = h('div', { class: 'mg-preview' });
  const refreshPreview = debounce(async () => {
    try {
      const res = await api.mergePreview(space.id, workflow.id, request());
      sidePreview.replaceChildren(preview(res.previa));
    } catch (err) { toastError(err, 'Não foi possível atualizar a prévia'); }
  }, 150);

  const conflictCard = (c) => {
    const option = (side, label, text) => h('button', {
      type: 'button', class: ['mg-option', (choices[c.id] || 'minha') === side && 'on'], 'aria-pressed': String((choices[c.id] || 'minha') === side),
      onclick: () => { choices[c.id] = side; draw(); refreshPreview(); },
    }, h('strong', {}, label), h('span', { class: 'mg-option-text' }, text === null ? 'Excluída' : text || 'Igual à de origem'));
    return h('section', { class: 'mg-conflict' },
      h('div', { class: 'mg-conflict-head' }, icon('alert', 14), h('strong', {}, c.rotulo), h('span', { class: 'muted small' }, CASES[c.caso] || '')),
      h('div', { class: 'mg-options' }, option('minha', 'A minha', c.minha), option('dele', `A de ${nome}`, c.dele)));
  };

  const draw = () => {
    if (!plan) return;
    const mineCount = plan.auto.filter((a) => a.de === 'minha').length;
    const theirCount = plan.auto.length - mineCount;
    body.replaceChildren(
      h('div', { class: 'mg-side' },
        h('div', { class: 'mg-summary' }, icon('check', 16),
          h('div', {}, h('strong', {}, plan.auto.length ? `${plural(plan.auto.length, 'mudança juntada', 'mudanças juntadas')} sozinha${plan.auto.length === 1 ? '' : 's'}` : 'Nada para juntar sozinho'),
            plan.auto.length ? h('p', { class: 'muted small' }, `${theirCount} de ${nome}, ${mineCount} sua${mineCount === 1 ? '' : 's'}.`) : null)),
        plan.sem_base ? h('p', { class: 'hint-box small' }, icon('info', 13), ' Não deu para achar a versão de onde as duas partiram: toda caixa diferente vira uma escolha.') : null,
        plan.conflitos.length
          ? h('div', { class: 'mg-conflicts' }, h('div', { class: 'panel-subtitle' }, `Escolha (${plan.conflitos.length})`), plan.conflitos.map(conflictCard))
          : h('p', { class: 'muted' }, 'Nenhuma caixa foi mexida pelos dois: é só aplicar.'),
        plan.fios_descartados ? h('p', { class: 'field-help' }, `${plural(plan.fios_descartados, 'fio sai', 'fios saem')} por ligar uma caixa que foi excluída.`) : null),
      h('div', { class: 'mg-right' }, h('div', { class: 'panel-subtitle' }, 'Resultado'), sidePreview));
    applyBtn.disabled = false;
  };

  try {
    plan = await api.mergePreview(space.id, workflow.id, request());
  } catch (err) {
    toastError(err, 'Não foi possível comparar as versões');
    close();
    return;
  }
  sidePreview.replaceChildren(preview(plan.previa));
  draw();

  applyBtn.addEventListener('click', async () => {
    applyBtn.disabled = true;
    try {
      const res = await api.mergeApply(space.id, workflow.id, request());
      restoreVersion(res.fluxo);
      if (res.base && store.space) store.space = { ...store.space, base: res.base, nova: null };
      close();
      toast('Versões juntadas', { kind: 'success', detail: 'Ainda não salvo: confira e use Salvar. Ctrl+Z desfaz.' });
    } catch (err) {
      toastError(err, 'Não foi possível juntar');
      applyBtn.disabled = false;
    }
  });
}
