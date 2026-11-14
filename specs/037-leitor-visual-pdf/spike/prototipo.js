// Protótipo do spike 037: marcar no PDF, ver o dado nascer e rastrear a origem.
// A camada de palavras é posicionada em porcentagem sobre a imagem da página: o alinhamento não depende de zoom,
// escala da tela nem resolução da imagem.

const $ = (sel) => document.querySelector(sel);

function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "style") Object.assign(el.style, v);
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "dataset") Object.assign(el.dataset, v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid);
  return el;
}

const ZOOMS = [0.5, 0.67, 0.8, 1, 1.25, 1.5, 2, 2.5, 3];
const S = {
  docs: [], tipos: {}, doc: null, info: null, zoom: 1,
  lines: [], order: [], pos: new Map(), lineOf: new Map(),
  sel: new Set(), anchor: null, cursor: null, suggestion: null, sugSeq: 0,
  recipe: { id: "prototipo", nome: "Relatório de vendas", campos: [], tabelas: [] },
  results: {}, colors: {}, nextColor: 0,
};

const api = async (url, body) => {
  const res = await fetch(url, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
  return res.json();
};

// Espaço de leitura: o texto corre da esquerda para a direita (o mesmo do motor, layout.py).
const angleOf = (p) => S.info?.pages?.[p]?.t || 0;
function toReading([x0, y0, x1, y1], t) {
  if (t === 90) return [y0, 1 - x1, y1, 1 - x0];
  if (t === 180) return [1 - x1, 1 - y1, 1 - x0, 1 - y0];
  if (t === 270) return [1 - y1, x0, 1 - y0, x1];
  return [x0, y0, x1, y1];
}
function toScreen([x0, y0, x1, y1], t) {
  if (t === 90) return [1 - y1, x0, 1 - y0, x1];
  if (t === 180) return [1 - x1, 1 - y1, 1 - x0, 1 - y0];
  if (t === 270) return [y0, 1 - x1, y1, 1 - x0];
  return [x0, y0, x1, y1];
}

const color = (name) => `var(--series-${(S.colors[name] ?? 0) % 8 + 1})`;
const mid = (w) => (w.b[1] + w.b[3]) / 2;

// ------------------------------------------------------------------ formatação

const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const num = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 6 });
function fmt(value, kind) {
  if (value == null) return "—";
  if (kind === "moeda") return brl.format(Number(value));
  if (kind === "inteiro" || kind === "decimal") return num.format(Number(value));
  if (kind === "data") { const [y, m, d] = value.split("-"); return `${d}/${m}/${y}`; }
  if (kind === "mes_ano") { const [y, m] = value.split("-"); return new Date(+y, +m - 1, 1).toLocaleDateString("pt-BR", { month: "short", year: "numeric" }).replace(". de ", "/").replace(" de ", "/"); }
  if (kind === "sim_nao") return value ? "Sim" : "Não";
  return String(value);
}
const STATE = {
  encontrado: ["ok", "Encontrado"], ausente: ["err", "Ausente"], ambiguo: ["warn", "Ambíguo"],
  invalido: ["err", "Inválido"], nao_suportado: ["err", "Não suportado"],
  aprovado: ["ok", "Aprovado"], revisar: ["warn", "Revisar"], falhou: ["err", "Falhou"],
};
const chip = (state, text) => { const [cls, label] = STATE[state] || ["idle", state]; return h("span", { class: `px-chip ${cls}` }, text || label); };

function howText(regra) {
  if (regra.tipo === "posicao") return [`posição fixa na página ${regra.pagina + 1} `, h("span", { class: "px-fragile", title: "Se o layout mudar, o valor some ou vem errado. Prefira marcar um rótulo." }, "· frágil")];
  const where = regra.direcao === "direita" ? "à direita de" : "abaixo de";
  const labels = regra.rotulos.map((r) => `“${r}”`).join(" ou ");
  return regra.tipo === "secao" ? `${where} ${labels}, dentro de “${regra.inicio[0]}”` : `${where} ${labels}`;
}

// ------------------------------------------------------------------ palavras em ordem de leitura

function buildOrder(words) {
  const idx = words.map((_, i) => i).sort((a, b) => words[a].p - words[b].p || mid(words[a]) - mid(words[b]));
  const lines = [];
  for (const i of idx) {
    const w = words[i], hgt = w.b[3] - w.b[1];
    const last = lines[lines.length - 1];
    if (last && last.p === w.p && Math.abs(mid(w) - last.mid) < 0.5 * Math.min(hgt, last.h)) last.items.push(i);
    else lines.push({ p: w.p, mid: mid(w), h: hgt, items: [i] });
  }
  for (const ln of lines) ln.items.sort((a, b) => words[a].b[0] - words[b].b[0]);
  S.lines = lines.map((l) => l.items);
  S.order = S.lines.flat();
  S.pos = new Map(S.order.map((i, k) => [i, k]));
  S.lineOf = new Map();
  S.lines.forEach((items, k) => items.forEach((i) => S.lineOf.set(i, k)));
}

// ------------------------------------------------------------------ páginas

const viewer = $("#viewer"), pagesEl = $("#pages");
function baseWidth() { return Math.min(Math.max(viewer.clientWidth - 48, 360), 920); }

function renderPages() {
  pagesEl.replaceChildren();
  const info = S.info;
  if (info.erro) {
    pagesEl.append(h("div", { class: "px-empty" }, h("b", {}, "Este PDF não pode ser lido"), info.mensagem,
      h("p", {}, info.erro === "sem_texto" ? "Ele parece ser uma imagem escaneada: não há texto para marcar. Leitura de imagem (OCR) fica para uma próxima versão." : "Os outros documentos continuam funcionando normalmente.")));
    return;
  }
  const byPage = info.pages.map(() => []);
  info.words.forEach((w, i) => byPage[w.p].push(i));
  info.pages.forEach((pg, p) => {
    const layer = h("div", { class: "px-layer" }, byPage[p].map((i) => {
      const [x0, y0, x1, y1] = info.words[i].b;
      return h("span", { class: "px-w", dataset: { i }, style: { left: `${x0 * 100}%`, top: `${y0 * 100}%`, width: `${(x1 - x0) * 100}%`, height: `${(y1 - y0) * 100}%` } });
    }));
    const page = h("div", { class: "px-page", dataset: { page: p } },
      h("img", { alt: `Página ${p + 1}`, draggable: "false" }), layer, h("div", { class: "px-marks" }),
      h("div", { class: "px-page-num" }, `Página ${p + 1} de ${info.pages.length}`));
    bindSelection(page, layer);
    pagesEl.append(page);
  });
  layoutPages();
}

let imgTimer = 0;
function layoutPages() {
  const width = baseWidth() * S.zoom;
  pagesEl.querySelectorAll(".px-page").forEach((el) => {
    const pg = S.info.pages[+el.dataset.page];
    el.style.width = `${width}px`;
    el.style.height = `${(width * pg.h) / pg.w}px`;
  });
  $("#zoom-reset").textContent = `${Math.round(S.zoom * 100)}%`;
  clearTimeout(imgTimer);
  imgTimer = setTimeout(loadImages, 120);
}

function loadImages() {
  const width = baseWidth() * S.zoom;
  pagesEl.querySelectorAll(".px-page").forEach((el) => {
    const p = +el.dataset.page, pg = S.info.pages[p];
    const scale = Math.min(4, Math.ceil(((width * devicePixelRatio) / pg.w) * 4) / 4);
    const src = `/api/docs/${S.doc}/pagina/${p}.png?escala=${scale}`;
    const img = el.querySelector("img");
    if (img.dataset.src === src) return;
    const pre = new Image();
    pre.onload = () => { img.src = src; img.dataset.src = src; };
    pre.src = src;
  });
}

function setZoom(z, anchor) {
  const old = S.zoom;
  S.zoom = Math.min(3, Math.max(0.5, z));
  if (old === S.zoom) return;
  const ax = anchor ? anchor.x : viewer.clientWidth / 2, ay = anchor ? anchor.y : viewer.clientHeight / 2;
  const rx = (viewer.scrollLeft + ax) / pagesEl.scrollWidth, ry = (viewer.scrollTop + ay) / pagesEl.scrollHeight;
  layoutPages();
  viewer.scrollLeft = rx * pagesEl.scrollWidth - ax;
  viewer.scrollTop = ry * pagesEl.scrollHeight - ay;
  renderAction();
}
const stepZoom = (dir) => setZoom(dir > 0 ? ZOOMS.find((z) => z > S.zoom + 1e-3) ?? 3 : [...ZOOMS].reverse().find((z) => z < S.zoom - 1e-3) ?? 0.5);

// ------------------------------------------------------------------ seleção

function pagePoint(pageEl, e) {
  const r = pageEl.getBoundingClientRect();
  return { x: (e.clientX - r.left) / r.width, y: (e.clientY - r.top) / r.height, px: e.clientX, py: e.clientY };
}

function bindSelection(pageEl, layer) {
  let drag = null, band = null;
  layer.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    viewer.focus({ preventScroll: true });
    const target = e.target.closest(".px-w");
    drag = { start: pagePoint(pageEl, e), moved: false, target: target ? +target.dataset.i : null, shift: e.shiftKey, add: e.ctrlKey || e.metaKey };
    layer.setPointerCapture(e.pointerId);
  });
  layer.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const cur = pagePoint(pageEl, e);
    if (!drag.moved && Math.hypot(cur.px - drag.start.px, cur.py - drag.start.py) < 5) return;
    drag.moved = true;
    const x0 = Math.min(drag.start.x, cur.x), y0 = Math.min(drag.start.y, cur.y), x1 = Math.max(drag.start.x, cur.x), y1 = Math.max(drag.start.y, cur.y);
    drag.rect = [x0, y0, x1, y1];
    if (!band) { band = h("div", { class: "px-band" }); pageEl.append(band); }
    Object.assign(band.style, { left: `${x0 * 100}%`, top: `${y0 * 100}%`, width: `${(x1 - x0) * 100}%`, height: `${(y1 - y0) * 100}%` });
    const p = +pageEl.dataset.page;
    const hit = S.info.words.map((w, i) => [w, i]).filter(([w]) => w.p === p && w.b[0] < x1 && w.b[2] > x0 && w.b[1] < y1 && w.b[3] > y0).map(([, i]) => i);
    setSelection(drag.add ? new Set([...S.sel, ...hit]) : new Set(hit), { live: true });
  });
  layer.addEventListener("pointerup", () => {
    if (!drag) return;
    band?.remove(); band = null;
    const d = drag; drag = null;
    if (d.moved) { const sorted = [...S.sel].sort((a, b) => S.pos.get(a) - S.pos.get(b)); S.anchor = sorted[0] ?? null; S.cursor = sorted.at(-1) ?? null; setSelection(S.sel); return; }
    if (d.target == null) { setSelection(new Set()); return; }
    if (d.shift && S.anchor != null) { S.cursor = d.target; selectRange(S.anchor, d.target); return; }
    if (d.add) { const next = new Set(S.sel); next.has(d.target) ? next.delete(d.target) : next.add(d.target); S.anchor = S.cursor = d.target; setSelection(next); return; }
    S.anchor = S.cursor = d.target;
    setSelection(new Set([d.target]));
    revealOwner(d.target);
  });
  layer.addEventListener("dblclick", (e) => {
    const t = e.target.closest(".px-w");
    if (!t) return;
    const group = valueGroup(+t.dataset.i);
    S.anchor = group[0]; S.cursor = group.at(-1);
    setSelection(new Set(group));
  });
}

function valueGroup(i) {
  // Palavras grudadas na mesma linha (o mesmo critério do motor para "um valor").
  const words = S.info.words, line = S.lines[S.lineOf.get(i)], k = line.indexOf(i);
  const gap = (a, b) => (words[b].b[0] - words[a].b[2]) / Math.max(words[a].b[3] - words[a].b[1], 1e-4) / (S.info.pages[words[a].p].h / S.info.pages[words[a].p].w);
  let a = k, b = k;
  while (a > 0 && gap(line[a - 1], line[a]) <= 1.5 && !words[line[a - 1]].t.endsWith(":")) a--;
  while (b < line.length - 1 && gap(line[b], line[b + 1]) <= 1.5) b++;
  return line.slice(a, b + 1);
}

function selectRange(a, b) {
  const [lo, hi] = [S.pos.get(a), S.pos.get(b)].sort((x, y) => x - y);
  setSelection(new Set(S.order.slice(lo, hi + 1)));
}

function setSelection(sel, { live = false } = {}) {
  pagesEl.querySelectorAll(".px-w.sel, .px-w.cursor").forEach((el) => el.classList.remove("sel", "cursor"));
  S.sel = sel;
  for (const i of sel) pagesEl.querySelector(`.px-w[data-i="${i}"]`)?.classList.add("sel");
  if (S.cursor != null) pagesEl.querySelector(`.px-w[data-i="${S.cursor}"]`)?.classList.add("cursor");
  S.suggestion = null;
  renderAction();
  if (live) return;
  const text = selectedWords().map((w) => w.t).join(" ");
  $("#anuncio").textContent = sel.size ? `Marcado: ${text}. Enter cria o campo.` : "";
  if (sel.size) fetchSuggestion();
}

const selectedWords = () => [...S.sel].sort((a, b) => S.pos.get(a) - S.pos.get(b)).map((i) => S.info.words[i]);
const selectedLines = () => new Set([...S.sel].map((i) => S.lineOf.get(i))).size;

let sugTimer = 0;
function fetchSuggestion() {
  clearTimeout(sugTimer);
  const seq = ++S.sugSeq;
  return new Promise((resolve) => {
    sugTimer = setTimeout(async () => {
      try {
        const sug = await api("/api/campo", { doc: S.doc, palavras: selectedWords() });
        if (seq === S.sugSeq) { S.suggestion = sug; renderAction(); }
        resolve(sug);
      } catch { resolve(null); }
    }, 90);
  });
}

// ------------------------------------------------------------------ barra de ação

function renderAction() {
  const old = pagesEl.querySelector(".px-action");
  if (!S.sel.size) { old?.remove(); return; }
  const words = selectedWords();
  const page = words[0].p;
  const on = words.filter((w) => w.p === page);
  const x0 = Math.min(...on.map((w) => w.b[0])), y0 = Math.min(...on.map((w) => w.b[1]));
  const pageEl = pagesEl.querySelector(`.px-page[data-page="${page}"]`);
  const text = words.map((w) => w.t).join(" ");
  const sug = S.suggestion, many = selectedLines() >= 3;
  const res = sug?.resultado;
  const value = res && res.estado === "encontrado" ? fmt(res.valor, sug.campo.tipo) : text;
  const sub = sug ? [`${S.tipos[sug.campo.tipo]} · ${sug.explicacao.split(":")[0]}`, sug.fragil ? h("span", { class: "px-fragile" }, " · frágil") : null] : "lendo…";
  const fieldBtn = h("button", { class: `px-btn ${many ? "" : "primary"}`, onclick: createField, onpointerdown: (e) => e.stopPropagation() }, "Criar campo", h("kbd", {}, "Enter"));
  const tableBtn = selectedLines() >= 2 ? h("button", { class: `px-btn ${many ? "primary" : ""}`, onclick: createTable, onpointerdown: (e) => e.stopPropagation() }, "Criar tabela", h("kbd", {}, "T")) : null;
  const bar = h("div", { class: "px-action", role: "toolbar", "aria-label": "Ações da seleção", style: { left: `${x0 * 100}%`, top: `${y0 * 100}%` } },
    many ? h("div", { class: "px-action-val" }, h("b", {}, `${selectedLines()} linhas marcadas`), h("small", {}, "Tabela: colunas pelos espaços em branco"))
      : h("div", { class: "px-action-val" }, h("b", {}, value.length > 42 ? value.slice(0, 40) + "…" : value), h("small", {}, sub)),
    many ? [tableBtn, fieldBtn] : [fieldBtn, tableBtn]);
  if (old && old.parentElement === pageEl && old.style.left === bar.style.left && old.style.top === bar.style.top) {
    bar.style.animation = "none";  // mesma seleção: só atualiza, sem piscar
  }
  old?.remove();
  pageEl.append(bar);
  // Não deixa a barra sair pela direita da página.
  const pr = pageEl.getBoundingClientRect(), br = bar.getBoundingClientRect();
  if (br.right > pr.right) bar.style.left = `${Math.max(0, (pr.width - br.width) / pr.width) * 100}%`;
}

function selectionRect() {
  const els = [...S.sel].map((i) => pagesEl.querySelector(`.px-w[data-i="${i}"]`)).filter(Boolean);
  if (!els.length) return null;
  const rs = els.map((e) => e.getBoundingClientRect());
  const left = Math.min(...rs.map((r) => r.left)), top = Math.min(...rs.map((r) => r.top));
  return { left, top, width: Math.max(...rs.map((r) => r.right)) - left, height: Math.max(...rs.map((r) => r.bottom)) - top };
}

function uniqueName(base) {
  const taken = new Set([...S.recipe.campos, ...S.recipe.tabelas].map((x) => x.nome));
  let name = base, n = 2;
  while (taken.has(name)) name = `${base}_${n++}`;
  return name;
}

async function createField() {
  if (!S.sel.size) return;
  const text = selectedWords().map((w) => w.t).join(" ");
  const sug = S.suggestion || (await fetchSuggestion());
  if (!sug) return;
  const campo = { ...sug.campo, nome: uniqueName(sug.campo.nome) };
  S.recipe.campos.push(campo);
  S.colors[campo.nome] = S.nextColor++;
  const from = selectionRect();
  S.anchor = S.cursor = null;
  setSelection(new Set());
  await runAll();
  fly(from, text, document.querySelector(`[data-field="${CSS.escape(campo.nome)}"]`));
  // Na página, o campo novo mostra o nome e pulsa por um instante (só as marcas de agora; redesenhos não herdam).
  pagesEl.querySelectorAll(`.px-mark[data-owner="${CSS.escape(campo.nome)}"]`).forEach((m) => {
    m.classList.add("born");
    setTimeout(() => m.classList.remove("born"), 2500);
  });
  $("#anuncio").textContent = `Campo ${campo.nome} criado: ${fmt(S.results[S.doc]?.campos.at(-1)?.valor, campo.tipo)}.`;
}

async function createTable() {
  const words = selectedWords();
  if (selectedLines() < 2) return;
  const page = words[0].p, on = words.filter((w) => w.p === page);
  const area = [Math.max(0, Math.min(...on.map((w) => w.b[0])) - 0.01), Math.max(0, Math.min(...on.map((w) => w.b[1])) - 0.003),
    Math.min(1, Math.max(...on.map((w) => w.b[2])) + 0.01), Math.min(1, Math.max(...on.map((w) => w.b[3])) + 0.003)];
  let sug;
  try { sug = await api("/api/tabela", { doc: S.doc, pagina: page, area, nome: "tabela" }); }
  catch (err) { $("#anuncio").textContent = err.message; return; }
  const tabela = { ...sug.tabela, nome: uniqueName(sug.tabela.nome) };
  S.recipe.tabelas.push(tabela);
  S.colors[tabela.nome] = S.nextColor++;
  const from = selectionRect();
  S.anchor = S.cursor = null;
  setSelection(new Set());
  await runAll();
  fly(from, `${on.length} palavras`, document.querySelector(`[data-table="${CSS.escape(tabela.nome)}"]`));
}

function fly(from, text, card) {
  if (!card) return;
  card.scrollIntoView({ block: "nearest", behavior: "smooth" });
  card.classList.remove("born"); void card.offsetWidth; card.classList.add("born");
  if (!from || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const target = card.querySelector(".px-value, .px-grid") || card;
  const to = target.getBoundingClientRect();
  const el = h("div", { class: "px-fly" }, text);
  document.body.append(el);
  el.animate([
    { left: `${from.left}px`, top: `${from.top}px`, width: `${from.width}px`, height: `${from.height}px`, opacity: 1 },
    { left: `${to.left}px`, top: `${to.top}px`, width: `${Math.min(to.width, 260)}px`, height: `${Math.min(to.height, 40)}px`, opacity: 0.15 },
  ], { duration: 560, easing: "cubic-bezier(.2,.7,.2,1)", fill: "forwards" }).onfinish = () => el.remove();
}

// ------------------------------------------------------------------ extração e impacto

let runSeq = 0;
async function runAll(only, { marks = true } = {}) {
  const seq = ++runSeq;
  const res = await api("/api/extrair", { receita: S.recipe, docs: only ? [only] : null });
  if (seq !== runSeq) return;
  Object.assign(S.results, res.resultados);
  renderDocs();
  renderData();
  if (marks) renderMarks();
}

function renderDocs() {
  const list = $("#docs");
  list.replaceChildren();
  const empty = !S.recipe.campos.length && !S.recipe.tabelas.length;
  const counts = { aprovado: 0, revisar: 0, falhou: 0 };
  for (const d of S.docs) {
    const r = S.results[d.id];
    let state = h("span", { class: "px-chip idle" }, "sem campos"), why = "";
    if (r?.erro) { state = chip("nao_suportado"); why = r.motivo; counts.falhou++; }
    else if (r && !empty) { state = chip(r.estado); why = r.motivo; counts[r.estado]++; }
    list.append(h("li", {}, h("button", { class: "px-doc", "aria-current": d.id === S.doc ? "true" : "false", onclick: () => openDoc(d.id) },
      h("span", { class: "px-doc-name", title: d.nome }, d.nome), state, why ? h("span", { class: "px-doc-why", title: why }, why) : null)));
  }
  const total = S.docs.length;
  $("#impacto").replaceChildren(...(empty
    ? ["Marque um valor no PDF para começar."]
    : ["Avaliado em ", h("b", {}, `${total} de ${total}`), " documentos: ", `${counts.aprovado} aprovados · ${counts.revisar} para revisar · ${counts.falhou} falharam`]));
}

// ------------------------------------------------------------------ painel de dados

function renderData() {
  const body = $("#data");
  body.replaceChildren();
  const r = S.results[S.doc];
  $("#doc-state").replaceChildren(r && (S.recipe.campos.length || S.recipe.tabelas.length) ? chip(r.erro ? "nao_suportado" : r.estado) : "");
  if (!S.recipe.campos.length && !S.recipe.tabelas.length) {
    body.append(h("div", { class: "px-onboard" }, h("b", {}, "Marque no PDF o dado que você quer"),
      h("ol", {}, h("li", {}, "Clique num valor (ou dê dois cliques para pegar o valor inteiro)."),
        h("li", {}, "Confira a prévia que aparece em cima da seleção."),
        h("li", {}, h("b", { style: { display: "inline" } }, "Enter"), " cria o campo. Arraste sobre uma tabela e tecle ", h("b", { style: { display: "inline" } }, "T"), "."),
        h("li", {}, "Clique em qualquer valor aqui para ver de onde ele veio."))));
    return;
  }
  S.recipe.campos.forEach((spec, k) => body.append(fieldCard(spec, r?.campos?.[k])));
  S.recipe.tabelas.forEach((spec, k) => body.append(tableCard(spec, r?.tabelas?.[k])));
}

function fieldCard(spec, f) {
  const c = color(spec.nome);
  const best = f?.candidatos?.[0];
  const card = h("article", { class: "px-field", dataset: { field: spec.nome }, style: { "--c": c },
    onmouseenter: () => focusMarks(spec.nome), onmouseleave: () => focusMarks(null) },
  h("input", { class: "px-field-name", value: spec.nome, "aria-label": "Nome do campo", spellcheck: "false",
    onchange: (e) => rename(spec, e.target.value) }),
  h("div", { style: { display: "flex", gap: "6px", alignItems: "center" } }, f ? chip(f.estado) : null,
    h("button", { class: "px-x", title: "Remover campo", "aria-label": `Remover ${spec.nome}`, onclick: () => remove("campos", spec) }, "×")),
  h("div", { class: "px-field-value" },
    f?.estado === "encontrado"
      ? h("button", { class: "px-value", title: "Ver de onde veio", onclick: () => reveal(best.origem, spec.nome) }, fmt(f.valor, spec.tipo))
      : h("span", { class: "px-value none" }, f?.estado === "ambiguo" ? "nenhum valor escolhido" : "sem valor"),
    f?.texto ? h("span", { class: "px-orig" }, `no PDF: “${f.texto}”`) : null),
  h("div", { class: "px-field-how" }, h("span", {}, "Como encontrar: ", howText(spec.regra)),
    h("select", { "aria-label": "Tipo", onchange: (e) => { spec.tipo = e.target.value; runAll(); } },
      Object.entries(S.tipos).map(([k, label]) => h("option", { value: k, selected: k === spec.tipo }, label))),
    h("label", {}, h("input", { type: "checkbox", checked: spec.obrigatorio, onchange: (e) => { spec.obrigatorio = e.target.checked; runAll(); } }), " obrigatório")));
  if (f && f.estado === "ambiguo") {
    card.append(h("div", { class: "px-why" }, `${f.motivo}: o Desata não escolhe sozinho. Use um rótulo mais preciso ou corrija só neste documento.`),
      h("div", { class: "px-cands" }, f.candidatos.map((cd, i) => h("button", { class: "px-cand", onclick: () => reveal(cd.origem, spec.nome) }, `${i + 1} · ${cd.texto}`))));
  } else if (f && f.estado !== "encontrado") {
    card.append(h("div", { class: "px-why err" }, f.motivo || ""));
  } else if (f?.motivo) {
    card.append(h("div", { class: "px-why", style: { color: "var(--text-3)" } }, f.motivo));
  }
  return card;
}

function tableCard(spec, t) {
  const c = color(spec.nome);
  const card = h("article", { class: "px-table", dataset: { table: spec.nome }, style: { "--c": c },
    onmouseenter: () => focusMarks(spec.nome), onmouseleave: () => focusMarks(null) });
  const rows = t?.linhas || [];
  card.append(h("div", { class: "px-table-head" },
    h("input", { class: "px-field-name", value: spec.nome, "aria-label": "Nome da tabela", onchange: (e) => rename(spec, e.target.value) }),
    h("div", { style: { display: "flex", gap: "6px", alignItems: "center" } },
      t?.problema ? chip("falhou", "Ajustar") : chip(rows.some((r) => r.duvida) ? "revisar" : "aprovado", `${rows.length} linhas`),
      h("button", { class: "px-x", title: "Remover tabela", onclick: () => remove("tabelas", spec) }, "×")),
    h("div", { class: "px-field-how" }, "Nova linha quando ",
      h("select", { "aria-label": "Coluna que inicia linha", onchange: (e) => { spec.coluna_inicio = e.target.value || null; runAll(); } },
        h("option", { value: "", selected: !spec.coluna_inicio }, "cada linha do PDF"),
        spec.colunas.map((col) => h("option", { value: col.nome, selected: col.nome === spec.coluna_inicio }, `“${col.nome}” tem valor`))),
      " · termina em ",
      h("input", { value: spec.fim.join(", "), placeholder: "fim do documento", size: 12, "aria-label": "Texto que encerra a tabela",
        style: { font: "inherit", border: "1px solid var(--border)", borderRadius: "6px", padding: "1px 6px", background: "var(--surface)", color: "var(--text)" },
        onchange: (e) => { spec.fim = e.target.value.split(",").map((s) => s.trim()).filter(Boolean); runAll(); } }))));
  if (t?.problema) card.append(h("div", { class: "px-why err", style: { padding: "0 12px 8px" } }, t.problema));
  const numeric = new Set(spec.colunas.filter((col) => col.tipo !== "texto").map((col) => col.nome));
  card.append(h("div", { class: "px-grid-wrap" }, h("table", { class: "px-grid" },
    h("thead", {}, h("tr", {}, h("th", { class: "rn" }, "#"), spec.colunas.map((col) => h("th", { title: S.tipos[col.tipo] }, col.nome)))),
    h("tbody", {}, rows.map((row, i) => h("tr", { class: row.duvida ? "doubt" : "", title: row.duvida || "" },
      h("td", { class: "rn" }, i + 1, row.linhas > 1 ? h("span", { class: "merged", title: `${row.linhas} linhas do PDF unidas` }, `↵${row.linhas}`) : null),
      spec.colunas.map((col) => {
        const cell = row.celulas[col.nome];
        const shown = cell.erro ? `⚠ ${cell.texto}` : cell.valor != null ? fmt(cell.valor, col.tipo) : "";
        return h("td", { class: numeric.has(col.nome) ? "num" : "" },
          h("button", { title: cell.texto ? `Ver no PDF: “${cell.texto}”` : "", onclick: () => cell.origem.length && reveal(cell.origem, spec.nome) }, shown));
      })))))));
  const ignored = t?.ignoradas || [];
  const reps = ignored.filter((x) => x.motivo === "cabeçalho repetido").length;
  card.append(h("div", { class: "px-table-foot" }, `Terminou em: ${t?.fim || "—"}`, reps ? ` · ${reps} cabeçalho repetido ignorado` : "",
    rows.filter((r) => r.linhas > 1).length ? ` · ${rows.filter((r) => r.linhas > 1).length} linhas com texto quebrado, unidas` : ""));
  return card;
}

function rename(spec, value) {
  const name = value.trim().replace(/\s+/g, "_");
  if (!name || name === spec.nome) return renderData();
  const fresh = uniqueName(name);
  S.colors[fresh] = S.colors[spec.nome];
  spec.nome = fresh;
  runAll();
}

function remove(kind, spec) {
  S.recipe[kind] = S.recipe[kind].filter((x) => x !== spec);
  runAll();
}

// ------------------------------------------------------------------ marcas na página e origem

function pageMarks(p) { return pagesEl.querySelector(`.px-page[data-page="${p}"] .px-marks`); }
const boxStyle = (b) => ({ left: `${b[0] * 100}%`, top: `${b[1] * 100}%`, width: `${(b[2] - b[0]) * 100}%`, height: `${(b[3] - b[1]) * 100}%` });

function renderMarks() {
  pagesEl.querySelectorAll(".px-marks").forEach((m) => m.replaceChildren());
  const r = S.results[S.doc];
  if (!r || S.info?.erro) return;
  S.recipe.campos.forEach((spec, k) => {
    const f = r.campos[k];
    if (!f) return;
    const c = color(spec.nome);
    f.candidatos.forEach((cd, n) => {
      for (const o of cd.origem) {
        const tag = f.estado === "ambiguo" ? `${spec.nome} · ${n + 1}?` : spec.nome;
        const cls = `px-mark${f.estado === "ambiguo" ? " show" : ""}`;
        pageMarks(o.p)?.append(h("div", { class: cls, dataset: { owner: spec.nome }, style: { ...boxStyle(o.b), "--c": c } }, h("span", { class: "px-mark-tag" }, tag)));
      }
      for (const o of cd.rotulo || []) pageMarks(o.p)?.append(h("div", { class: "px-mark label", dataset: { owner: spec.nome }, style: { ...boxStyle(o.b), "--c": c } }));
    });
  });
  S.recipe.tabelas.forEach((spec, k) => {
    const t = r.tabelas[k];
    if (!t) return;
    const c = color(spec.nome);
    const regions = {};  // por página, no espaço de leitura
    for (const row of t.linhas) for (const cell of Object.values(row.celulas)) for (const o of cell.origem) {
      const b = toReading(o.b, angleOf(o.p));
      const g = (regions[o.p] ||= [1, 1, 0, 0]);
      g[0] = Math.min(g[0], b[0]); g[1] = Math.min(g[1], b[1]); g[2] = Math.max(g[2], b[2]); g[3] = Math.max(g[3], b[3]);
    }
    for (const [p, g] of Object.entries(regions)) {
      const reading = [spec.limites[0], g[1] - 0.006, spec.limites[1], g[3] + 0.006];
      const marks = pageMarks(+p);
      marks?.append(h("div", { class: "px-region", dataset: { owner: spec.nome }, style: { ...boxStyle(toScreen(reading, angleOf(+p))), "--c": c } }, h("span", { class: "px-mark-tag right", style: { "--c": c } }, `${spec.nome} · ${t.linhas.length} linhas`)));
      spec.guias.forEach((x, gi) => marks?.append(guideHandle(spec, gi, +p, reading, c)));
    }
    for (const ig of t.ignoradas) for (const o of ig.origem) {
      const b = toReading(o.b, angleOf(o.p));
      pageMarks(o.p)?.append(h("div", { class: "px-ignored", style: boxStyle(toScreen([spec.limites[0], b[1] - 0.003, spec.limites[1], b[3] + 0.003], angleOf(o.p))) }, h("span", {}, ig.motivo)));
    }
  });
}

function guideHandle(spec, gi, p, reading, c) {
  const t = angleOf(p), across = t === 90 || t === 270;  // na tela, a guia fica deitada quando o texto está em pé
  const place = (el) => {
    const g = spec.guias[gi];
    const [x0, y0, x1, y1] = toScreen([g, reading[1], g, reading[3]], t);
    Object.assign(el.style, across
      ? { left: `${x0 * 100}%`, width: `${(x1 - x0) * 100}%`, top: `${y0 * 100}%`, height: "" }
      : { left: `${x0 * 100}%`, top: `${y0 * 100}%`, height: `${(y1 - y0) * 100}%`, width: "" });
  };
  const el = h("button", { class: `px-guide${across ? " across" : ""}`, "aria-label": `Guia ${gi + 1} da tabela ${spec.nome}. Setas movem.`, title: "Arraste para ajustar a coluna (ou use as setas)", style: { "--c": c } });
  place(el);
  const clamp = (x) => Math.min(Math.max(x, (spec.guias[gi - 1] ?? spec.limites[0]) + 0.01), (spec.guias[gi + 1] ?? spec.limites[1]) - 0.01);
  let busy = false, again = false;
  const live = () => {  // uma prévia por vez; a última posição sempre é avaliada
    if (busy) { again = true; return; }
    busy = true;
    runAll(S.doc, { marks: false }).finally(() => { busy = false; if (again) { again = false; live(); } });
  };
  el.addEventListener("pointerdown", (e) => {
    e.stopPropagation(); e.preventDefault();
    el.setPointerCapture(e.pointerId);
    const pageEl = el.closest(".px-page");
    const move = (ev) => {
      const pt = pagePoint(pageEl, ev);
      spec.guias[gi] = Math.round(clamp(toReading([pt.x, pt.y, pt.x, pt.y], t)[0]) * 10000) / 10000;
      place(el);
      live();
    };
    const up = () => { el.removeEventListener("pointermove", move); el.removeEventListener("pointerup", up); runAll(); };
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerup", up);
  });
  el.addEventListener("keydown", (e) => {
    const keys = across ? { ArrowDown: 1, ArrowUp: -1 } : { ArrowRight: 1, ArrowLeft: -1 };
    if (!(e.key in keys)) return;
    e.preventDefault(); e.stopPropagation();
    const sign = t === 180 || t === 270 ? -keys[e.key] : keys[e.key];  // a seta move a guia no sentido da tela
    spec.guias[gi] = Math.round(clamp(spec.guias[gi] + sign * (e.shiftKey ? 0.01 : 0.002)) * 10000) / 10000;
    runAll().then(() => pagesEl.querySelectorAll(".px-guide")[gi]?.focus());
  });
  return el;
}

function focusMarks(owner) {
  pagesEl.querySelectorAll(".px-mark, .px-region").forEach((m) => {
    m.classList.toggle("dim", owner != null && m.dataset.owner !== owner);
    m.classList.toggle("focus", owner != null && m.dataset.owner === owner);
  });
}

function reveal(origem, owner) {
  if (!origem?.length) return;
  const o = origem[0];
  const pageEl = pagesEl.querySelector(`.px-page[data-page="${o.p}"]`);
  if (!pageEl) return;
  const top = pageEl.offsetTop + o.b[1] * pageEl.offsetHeight - viewer.clientHeight / 2 + 40;
  const left = pageEl.offsetLeft + ((o.b[0] + o.b[2]) / 2) * pageEl.offsetWidth - viewer.clientWidth / 2;
  viewer.scrollTo({ top, left, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  for (const part of origem) {
    const pulse = h("div", { class: "px-mark pulse", style: { ...boxStyle(part.b), "--c": owner ? color(owner) : "var(--accent)" } });
    pageMarks(part.p)?.append(pulse);
    setTimeout(() => pulse.remove(), 2400);
  }
  $("#anuncio").textContent = `Origem: página ${o.p + 1}.`;
}

function revealOwner(i) {
  // Do PDF para o dado: clicar numa palavra que virou valor destaca o campo ou a célula.
  const w = S.info.words[i], cx = (w.b[0] + w.b[2]) / 2, cy = mid(w);
  const inside = (o) => o.p === w.p && cx >= o.b[0] && cx <= o.b[2] && cy >= o.b[1] && cy <= o.b[3];
  const r = S.results[S.doc];
  if (!r) return;
  document.querySelectorAll(".px-field.focus, .px-grid button.hit").forEach((el) => el.classList.remove("focus", "hit"));
  for (const [k, f] of (r.campos || []).entries()) {
    if (f.candidatos.some((cd) => cd.origem.some(inside))) {
      const card = document.querySelector(`[data-field="${CSS.escape(S.recipe.campos[k].nome)}"]`);
      card?.classList.add("focus"); card?.scrollIntoView({ block: "nearest", behavior: "smooth" });
      setTimeout(() => card?.classList.remove("focus"), 1600);
      return;
    }
  }
  for (const [k, t] of (r.tabelas || []).entries()) {
    for (const [ri, row] of t.linhas.entries()) {
      const ci = t.colunas.findIndex((col) => row.celulas[col].origem.some(inside));
      if (ci < 0) continue;
      const btn = document.querySelectorAll(`[data-table="${CSS.escape(S.recipe.tabelas[k].nome)}"] tbody tr`)[ri]?.querySelectorAll("td")[ci + 1]?.querySelector("button");
      if (btn) { btn.scrollIntoView({ block: "nearest", behavior: "smooth" }); btn.animate([{ background: "color-mix(in srgb, var(--accent) 30%, transparent)" }, { background: "transparent" }], { duration: 1400 }); }
      return;
    }
  }
}

// ------------------------------------------------------------------ teclado

viewer.addEventListener("keydown", (e) => {
  if (!S.info || S.info.erro) return;
  const k = e.key;
  if (k === "Enter") { e.preventDefault(); createField(); return; }
  if (k === "t" || k === "T") { e.preventDefault(); createTable(); return; }
  if (k === "Escape") { S.anchor = S.cursor = null; setSelection(new Set()); return; }
  if (k === "+" || k === "=") { e.preventDefault(); stepZoom(1); return; }
  if (k === "-") { e.preventDefault(); stepZoom(-1); return; }
  if (k === "0") { e.preventDefault(); setZoom(1); return; }
  if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(k)) return;
  e.preventDefault();
  if (S.cursor == null) S.cursor = firstVisibleWord();
  else {
    const pos = S.pos.get(S.cursor), line = S.lineOf.get(S.cursor), items = S.lines[line];
    if (k === "ArrowRight") S.cursor = S.order[Math.min(pos + 1, S.order.length - 1)];
    else if (k === "ArrowLeft") S.cursor = S.order[Math.max(pos - 1, 0)];
    else if (k === "Home") S.cursor = items[0];
    else if (k === "End") S.cursor = items.at(-1);
    else {
      const target = S.lines[Math.min(Math.max(line + (k === "ArrowDown" ? 1 : -1), 0), S.lines.length - 1)];
      const w = S.info.words[S.cursor], cx = (w.b[0] + w.b[2]) / 2;
      S.cursor = target.reduce((best, i) => { const b = S.info.words[i].b, d = Math.abs((b[0] + b[2]) / 2 - cx); return d < best[1] ? [i, d] : best; }, [target[0], Infinity])[0];
    }
  }
  if (e.shiftKey && S.anchor != null) selectRange(S.anchor, S.cursor);
  else { S.anchor = S.cursor; setSelection(new Set([S.cursor])); }
  pagesEl.querySelector(`.px-w[data-i="${S.cursor}"]`)?.scrollIntoView({ block: "nearest", inline: "nearest" });
});

function firstVisibleWord() {
  const top = viewer.getBoundingClientRect().top;
  for (const i of S.order) {
    const el = pagesEl.querySelector(`.px-w[data-i="${i}"]`);
    if (el && el.getBoundingClientRect().top >= top) return i;
  }
  return S.order[0];
}

viewer.addEventListener("wheel", (e) => {
  if (!e.ctrlKey) return;
  e.preventDefault();
  const r = viewer.getBoundingClientRect();
  setZoom(S.zoom * (e.deltaY < 0 ? 1.1 : 1 / 1.1), { x: e.clientX - r.left, y: e.clientY - r.top });
}, { passive: false });
$("#zoom-in").onclick = () => stepZoom(1);
$("#zoom-out").onclick = () => stepZoom(-1);
$("#zoom-reset").onclick = () => setZoom(1);
new ResizeObserver(() => S.info && !S.info.erro && layoutPages()).observe(viewer);

// ------------------------------------------------------------------ início

async function openDoc(id) {
  S.doc = id;
  S.sel = new Set(); S.anchor = S.cursor = null; S.suggestion = null;
  S.info = await api(`/api/docs/${id}`);
  buildOrder(S.info.words);
  $("#doc-title").textContent = S.docs.find((d) => d.id === id)?.nome || id;
  viewer.scrollTo(0, 0);
  renderPages();
  renderDocs();
  renderData();
  renderMarks();
}

(async () => {
  const meta = await api("/api/docs");
  S.docs = meta.docs; S.tipos = meta.tipos;
  const params = new URLSearchParams(location.search);
  if (params.get("zoom")) S.zoom = +params.get("zoom");
  await runAll();
  await openDoc(params.get("doc") || "outubro");
  window.__px = S; // para os testes de navegador do spike
})();
