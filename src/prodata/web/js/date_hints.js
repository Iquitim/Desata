// Datas escritas de outro jeito (spec 040, RF-4003..4005): reconhece "07/08/2026", "2026-07-08", "jul/26"… numa
// fórmula e sugere a forma que o programa entende, ToDate('AAAA-MM-DD'). Nunca troca nada sozinho.

const MONTHS = {
  jan: 1, fev: 2, mar: 3, abr: 4, mai: 5, jun: 6, jul: 7, ago: 8, set: 9, out: 10, nov: 11, dez: 12,
  janeiro: 1, fevereiro: 2, marco: 3, abril: 4, maio: 5, junho: 6, julho: 7, agosto: 8, setembro: 9, outubro: 10, novembro: 11, dezembro: 12,
};
export const MONTH_NAMES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'];
const plain = (s) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
const pad = (n) => String(n).padStart(2, '0');

function valid(y, m, d) {
  if (m < 1 || m > 12 || d < 1) return false;
  const dt = new Date(Date.UTC(y, m - 1, d));
  return dt.getUTCFullYear() === y && dt.getUTCMonth() === m - 1 && dt.getUTCDate() === d;
}

/**
 * Um texto que é inteiro uma data: {iso, y, m, d, month} (month = só mês e ano, vira o dia 1), {invalid: true} para
 * uma data impossível (31/02/2026) ou null quando não parece data.
 */
export function parseDateText(raw) {
  // spec 040: hora opcional ("14:30" ou "14:30:00") depois da data, separada por espaço ou T
  const full = /^(.*?)(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?$/.exec(String(raw).trim());
  const s = full[1].trim();
  const time = full[2] !== undefined ? [+full[2], +full[3], +(full[4] || 0)] : null;
  if (time && (time[0] > 23 || time[1] > 59 || time[2] > 59)) return { invalid: true };
  let y; let m; let d = 1; let month = false; let m2;
  if ((m2 = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(s))) [y, m, d] = [+m2[1], +m2[2], +m2[3]];
  else if ((m2 = /^(\d{1,2})[/-](\d{1,2})[/-](\d{4}|\d{2})$/.exec(s))) { // dia/mês, como no Brasil; ano com 2 dígitos = 20xx
    [d, m] = [+m2[1], +m2[2]];
    y = m2[3].length === 2 ? 2000 + Number(m2[3]) : Number(m2[3]);
  }
  else if ((m2 = /^(\d{1,2})\/(\d{4})$/.exec(s))) { [m, y] = [+m2[1], +m2[2]]; month = true; }
  else if ((m2 = /^([a-zà-ÿ]{3,9})[/ -](\d{2}|\d{4})$/i.exec(s)) && MONTHS[plain(m2[1])]) {
    m = MONTHS[plain(m2[1])];
    y = m2[2].length === 2 ? 2000 + Number(m2[2]) : Number(m2[2]);
    month = true;
  } else return null;
  if (time && month) return null; // "jul/26 14:30" não é um formato
  if (!valid(y, m, d)) return { invalid: true };
  const day = `${y}-${pad(m)}-${pad(d)}`;
  if (time) return { iso: `${day} ${pad(time[0])}:${pad(time[1])}:${pad(time[2])}`, y, m, d, month, time };
  return { iso: day, y, m, d, month };
}

/** Data e hora do calendário: ("2026-07-08", "14:30") → "2026-07-08 14:30"; sem hora, só a data. */
export const joinDateTime = (day, time) => (day ? (time ? `${day} ${time}` : day) : '');

/** O valor gravado separado para o calendário: {day, time} (hora sem segundos quando zerados). */
export function splitDateTime(value) {
  const p = value ? parseDateText(value) : null;
  if (!p || p.invalid || p.month) return { day: '', time: '', parsed: p };
  const time = p.time ? `${pad(p.time[0])}:${pad(p.time[1])}${p.time[2] ? `:${pad(p.time[2])}` : ''}` : '';
  return { day: p.iso.slice(0, 10), time, parsed: p };
}

/** A data por extenso, para não haver dúvida entre dia e mês. */
export function sayDate(p) {
  if (p.month) return `${MONTH_NAMES[p.m - 1]} de ${p.y}`;
  const day = `${p.d} de ${MONTH_NAMES[p.m - 1]} de ${p.y}`;
  return p.time ? `${day}, às ${pad(p.time[0])}:${pad(p.time[1])}${p.time[2] ? `:${pad(p.time[2])}` : ''}` : day;
}

// colunas e textos entre aspas são lidos inteiros; fora deles, só os formatos de data
const TIME = '(?:[ T]\\d{1,2}:\\d{2}(?::\\d{2})?)?';
const SCAN = new RegExp(
  "\\[[^\\]]*\\]|'[^']*'|\"[^\"]*\""
  + `|\\b\\d{4}-\\d{1,2}-\\d{1,2}${TIME}(?![\\d:])`
  + `|\\b\\d{1,2}[/-]\\d{1,2}[/-](?:\\d{4}|\\d{2})${TIME}(?![\\d:/])`
  + '|\\b\\d{1,2}\\/\\d{4}\\b|\\b[A-Za-zÀ-ÿ]{3,9}\\/(?:\\d{4}|\\d{2})\\b',
  'g',
);

/**
 * As datas escritas de outro jeito numa fórmula: [{start, end, text, replacement, parsed}] ou, para uma data
 * impossível, [{start, end, text, invalid: true}]. Data já na forma certa (dentro de ToDate, em AAAA-MM-DD) fica fora.
 */
export function findDateHints(text) {
  const out = [];
  for (const m of String(text).matchAll(SCAN)) {
    const token = m[0];
    if (token.startsWith('[')) continue;
    const quoted = token[0] === "'" || token[0] === '"';
    const inner = quoted ? token.slice(1, -1) : token;
    const parsed = parseDateText(inner);
    if (!parsed) continue;
    let start = m.index;
    let end = start + token.length;
    if (parsed.invalid) { out.push({ start, end, text: token, invalid: true }); continue; }
    const before = text.slice(0, start);
    const call = quoted ? /(todate(?:time)?)\(\s*$/i.exec(before) : null;
    const fn = parsed.time ? 'ToDateTime' : 'ToDate';
    const sameFn = call && call[1].toLowerCase() === fn.toLowerCase();
    if (sameFn && inner.trim() === parsed.iso) continue; // já está certo
    const iso = `'${parsed.iso}'`;
    if (call && !sameFn) { // data com hora dentro de ToDate (ou o contrário): troca a chamada inteira, não só o texto
      start -= call[0].length;
      if (text[end] === ')') end += 1;
      out.push({ start, end, text: text.slice(start, end), parsed, replacement: `${fn}(${iso})` });
      continue;
    }
    out.push({ start, end, text: token, parsed, replacement: sameFn ? iso : `${fn}(${iso})` });
  }
  return out;
}
