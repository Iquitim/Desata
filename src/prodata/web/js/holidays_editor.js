// Editar feriados (spec 049, RF-4945..4948): a base do lugar escolhido, de onde veio cada feriado e as edições da
// pessoa por cima: incluir, corrigir, "não vale mais" e restaurar. A edição vence a revisão do programa; quando os
// dois mudaram o mesmo feriado, a linha mostra as duas versões e a pessoa escolhe.

import { api } from './api.js';
import { button, h } from './dom.js';
import { icon } from './icons.js';
import { canWrite, chooseSpace, teamConfigured, usableSpaces } from './team_spaces.js';
import { openDialog, toast, toastError } from './ui.js';

const TYPES = { nacional: 'Nacional', estadual: 'Estadual', municipal: 'Municipal', bancario: 'Bancário', ponto_facultativo: 'Ponto facultativo', meu: 'Seu' };
const ORIGINS = { calculado: 'Calculado', programa: 'Do programa', meu: 'Seu', anbima: 'ANBIMA' };

function dayText(iso) {
  if (!iso) return '';
  const d = new Date(`${iso}T12:00:00`);
  return d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
}

/** Abre o editor. ``place``: BR, a sigla da UF ou o código do município. */
export function openHolidayEditor({ place = 'BR', onChange } = {}) {
  const st = { place, year: new Date().getFullYear(), data: null, error: null, form: null, busy: false };
  const body = h('div', { class: 'hol-root' }, h('p', { class: 'pd-loading' }, 'Carregando os feriados…'));
  const dialog = openDialog({ title: 'Editar feriados', body, size: 'xl', onClose: () => onChange?.() });
  dialog.el.classList.add('hol-dialog');

  async function load() {
    try {
      st.data = await api.publicHolidays(st.place, st.year);
      st.error = null;
    } catch (err) {
      st.error = err.message || String(err);
    }
    draw();
  }

  async function act(action, payload, done) {
    st.busy = true; draw();
    try {
      st.data = await api.publicHolidayAction(action, payload, st.place, st.year);
      st.form = null;
      if (done) toast(done, { kind: 'success' });
    } catch (err) {
      toastError(err, 'Não foi possível salvar');
    }
    st.busy = false; draw();
  }

  // ---------------------------------------------------------------- formulário (incluir e corrigir)

  function ruleFields(f) {
    const kind = f.kind;
    const radio = (value, label) => h('label', { class: 'hol-radio' },
      h('input', { type: 'radio', name: 'hol-rule', checked: kind === value, onchange: () => { f.kind = value; draw(); } }), ` ${label}`);
    return h('div', { class: 'hol-rule' },
      h('div', { class: 'row' }, radio('fixo', 'Todo ano em'), radio('unico', 'Só uma vez em'), radio('pascoa', 'Dias depois da Páscoa')),
      kind === 'fixo' ? h('input', { class: 'input', placeholder: 'DD/MM', value: f.fixo || '', 'aria-label': 'Dia e mês',
        oninput: (e) => { f.fixo = e.target.value; } }) : null,
      kind === 'unico' ? h('input', { class: 'input', type: 'date', value: f.unico || '', 'aria-label': 'Data',
        oninput: (e) => { f.unico = e.target.value; } }) : null,
      kind === 'pascoa' ? h('input', { class: 'input', type: 'number', min: -100, max: 100, value: f.pascoa ?? 60,
        'aria-label': 'Dias depois da Páscoa', oninput: (e) => { f.pascoa = Number(e.target.value); } }) : null,
      kind === 'pascoa' ? h('small', { class: 'field-help' }, 'Corpus Christi: 60. Sexta-feira Santa: −2.') : null);
  }

  function rulePayload(f) {
    if (f.kind === 'unico') return f.unico ? { unico: f.unico } : null;
    if (f.kind === 'pascoa') return { pascoa: Number(f.pascoa ?? 60) };
    const m = /^(\d{1,2})\/(\d{1,2})$/.exec((f.fixo || '').trim());
    return m ? { fixo: `${m[2].padStart(2, '0')}-${m[1].padStart(2, '0')}` } : null;
  }

  function formCard() {
    const f = st.form;
    if (!f) return null;
    const save = () => {
      const rule = rulePayload(f);
      if (!f.nome?.trim()) { toast('Dê um nome ao feriado', { kind: 'error' }); return; }
      if (!rule) { toast('Confira a data: DD/MM, uma data ou os dias da Páscoa', { kind: 'error' }); return; }
      if (f.id) {
        act('corrigir', { id: f.id, campos: { nome: f.nome.trim(), ...rule, fixo: rule.fixo ?? null, pascoa: rule.pascoa ?? null,
          unico: rule.unico ?? null, lei: f.lei || '' } }, 'Correção salva');
      } else {
        act('incluir', { nome: f.nome.trim(), abrangencia: f.abrangencia, tipo: f.tipo, ...rule, lei: f.lei || '', nota: f.nota || '' }, 'Feriado incluído');
      }
    };
    return h('section', { class: 'hol-form' },
      h('h3', {}, f.id ? `Corrigir: ${f.original}` : 'Incluir feriado'),
      h('div', { class: 'hol-form-grid' },
        h('label', { class: 'pd-inline' }, 'Nome', h('input', { class: 'input', value: f.nome || '', placeholder: 'Ex.: Padroeira da cidade, Recesso da empresa',
          oninput: (e) => { f.nome = e.target.value; } })),
        f.id ? null : h('label', { class: 'pd-inline' }, 'Vale em', h('input', { class: 'input', value: f.abrangencia,
          placeholder: 'BR, SP ou 3509502', oninput: (e) => { f.abrangencia = e.target.value.trim().toUpperCase(); } })),
        f.id ? null : h('label', { class: 'pd-inline' }, 'Tipo', h('select', { class: 'input', onchange: (e) => { f.tipo = e.target.value; } },
          [['municipal', 'Feriado municipal'], ['estadual', 'Feriado estadual'], ['meu', 'Recesso, ponte ou da empresa']]
            .map(([v, l]) => h('option', { value: v, selected: f.tipo === v }, l)))),
        h('label', { class: 'pd-inline' }, 'Lei (opcional)', h('input', { class: 'input', value: f.lei || '', placeholder: 'Lei municipal 1.234/1990',
          oninput: (e) => { f.lei = e.target.value; } }))),
      ruleFields(f),
      h('div', { class: 'row' },
        button({ label: 'Cancelar', onClick: () => { st.form = null; draw(); } }),
        button({ label: f.id ? 'Salvar a correção' : 'Incluir', variant: 'primary', disabled: st.busy, onClick: save })));
  }

  function startCorrect(r) {
    st.form = {
      id: r.id, original: r.nome, nome: r.nome, lei: r.lei,
      kind: r.unico ? 'unico' : r.pascoa !== null && r.pascoa !== undefined ? 'pascoa' : 'fixo',
      fixo: r.fixo ? r.fixo.split('-').reverse().join('/') : '', unico: r.unico || '', pascoa: r.pascoa,
    };
    draw();
  }

  // ---------------------------------------------------------------- linhas

  function originChip(r) {
    if (r.programa_mudou) return h('span', { class: 'pd-chip tone-warn' }, 'O programa também mudou');
    if (r.origem === 'meu' || r.editado) return h('span', { class: 'pd-chip hol-mine' }, r.editado && r.origem !== 'meu' ? 'Editado por você' : 'Seu');
    if (r.confirmar) return h('span', { class: 'pd-chip tone-warn', title: r.nota || 'As fontes divergem: confira com a lei local' }, 'A confirmar');
    return h('span', { class: 'pd-chip tone-muted' }, r.origem === 'programa' ? `Do programa · revisado em ${dayText(r.revisado_em)}/${(r.revisado_em || '').slice(0, 4)}` : ORIGINS[r.origem] || r.origem);
  }

  function row(r) {
    const stopped = r.deixou_de_valer && r.deixou_de_valer <= st.year;
    const actions = [];
    if (!stopped) actions.push(button({ label: 'Corrigir', size: 'sm', variant: 'ghost', onClick: () => startCorrect(r) }));
    if (!stopped && r.origem !== 'meu') {
      actions.push(button({ label: 'Não vale mais', size: 'sm', variant: 'ghost', title: `Deixa de valer a partir de ${st.year}`,
        onClick: () => act('nao-vale-mais', { id: r.id, desde: st.year }, `Não vale mais a partir de ${st.year}`) }));
    }
    if (r.editado) {
      actions.push(button({ label: r.origem === 'meu' ? 'Apagar' : 'Restaurar o do programa', size: 'sm', variant: 'ghost',
        onClick: () => act('restaurar', { id: r.id }, r.origem === 'meu' ? 'Feriado apagado' : 'Voltou o do programa') }));
    }
    return h('li', { class: `hol-row${stopped ? ' is-stopped' : ''}${r.programa_mudou ? ' is-conflict' : ''}` },
      h('div', { class: 'hol-date' }, r.data ? [h('strong', {}, dayText(r.data)), h('small', {}, r.dia_semana)] : h('small', {}, 'não cai este ano')),
      h('div', { class: 'hol-main' },
        h('strong', {}, r.nome),
        h('small', {}, [r.regra, r.lei ? ` · ${r.lei}` : '', stopped ? ` · não vale mais desde ${r.deixou_de_valer}` : ''].join('')),
        r.confirmar && r.nota ? h('small', { class: 'hol-note' }, r.nota) : null,
        r.programa_mudou && r.original ? h('div', { class: 'hol-conflict' },
          h('p', {}, icon('alert', 13), ' Uma versão nova do programa também mudou este feriado. A sua continua valendo até você escolher.'),
          h('dl', {}, h('dt', {}, 'Programa agora'), h('dd', {}, `${r.original.nome} · ${r.original.regra}`),
            h('dt', {}, 'A sua'), h('dd', {}, `${r.nome} · ${r.regra}`)),
          h('div', { class: 'row' },
            button({ label: 'Manter o meu', size: 'sm', variant: 'primary', onClick: () => act('manter-o-meu', { id: r.id }, 'Mantida a sua versão') }),
            button({ label: 'Usar o do programa', size: 'sm', onClick: () => act('restaurar', { id: r.id }, 'Voltou o do programa') }))) : null),
      h('span', { class: `pd-chip hol-type-${r.tipo}` }, TYPES[r.tipo] || r.tipo),
      originChip(r),
      h('div', { class: 'hol-actions' }, actions));
  }

  function shareButton() {
    if (!teamConfigured() || !usableSpaces().some(canWrite)) return null;
    return button({ icon: 'folder', label: 'Compartilhar com a equipe…', onClick: async () => {
      const space = await chooseSpace('Compartilhar os feriados com a equipe');
      if (!space) return;
      try {
        await api.shareDefinition(space.id, 'feriados', 'calendario');
        toast('Feriados compartilhados com a equipe', { kind: 'success', detail: `Espaço "${space.nome}": os fluxos do espaço usam este calendário.` });
      } catch (err) { toastError(err, 'Não foi possível compartilhar'); }
    } });
  }

  function draw() {
    if (st.error) { body.replaceChildren(h('p', { class: 'pd-note pd-note-err' }, icon('alert', 13), ` ${st.error}`)); return; }
    if (!st.data) return;
    const rows = st.data.linhas;
    const edited = rows.filter((r) => r.editado).length;
    // replaceChildren escreveria null como texto: só os nós de verdade.
    const parts = [
      h('div', { class: 'hol-top' },
        h('label', { class: 'pd-inline' }, 'Local', h('input', { class: 'input', value: st.place, placeholder: 'BR, SP ou 3509502',
          onchange: (e) => { st.place = e.target.value.trim().toUpperCase() || 'BR'; load(); } })),
        h('label', { class: 'pd-inline' }, 'Ano', h('select', { class: 'input', onchange: (e) => { st.year = Number(e.target.value); load(); } },
          [...new Set([new Date().getFullYear() - 1, new Date().getFullYear(), new Date().getFullYear() + 1, new Date().getFullYear() + 2, st.year])]
            .sort().map((y) => h('option', { value: y, selected: y === st.year }, y)))),
        h('p', { class: 'hol-cover' }, icon('info', 13), ` ${st.data.cobertura} ${edited ? `Você mudou ${edited}.` : ''}`),
        h('div', { class: 'row' },
          shareButton(),
          button({ icon: 'plus', label: 'Incluir feriado', variant: 'primary', onClick: () => {
            st.form = { kind: 'fixo', abrangencia: st.place, tipo: /^\d{7}$/.test(st.place) ? 'municipal' : 'meu' }; draw();
          } }))),
      formCard(),
      h('ul', { class: 'hol-list', 'aria-busy': st.busy ? 'true' : 'false' }, rows.map(row)),
      h('p', { class: 'field-help' }, 'Suas edições ficam por cima da tabela do programa: nada do programa é apagado, e Restaurar desfaz. ',
        'Quando sair uma versão nova do programa com a tabela revisada, as suas continuam valendo.')];
    body.replaceChildren(...parts.filter(Boolean));
  }

  load();
  return dialog;
}
