// Marca ativa (spec 036). O servidor escreve nome, organização e rodapé em data-marca-* no <html>,
// e serve os logos em /marca/. Nenhum outro módulo escreve o nome do produto ou da organização.

const data = document.documentElement.dataset;

export const brand = Object.freeze({
  nome: data.marcaNome || '',
  nomeCurto: data.marcaNomeCurto || '',
  organizacao: data.marcaOrganizacao || '',
  apoio: data.marcaApoio || '',
  site: data.marcaSite || '',
  rodape: data.marcaRodape || '',
});

export const LOGO_LIGHT = '/marca/logo-claro.svg';
export const LOGO_DARK = '/marca/logo-escuro.svg';

/** Quem assina o logo: a organização, ou o produto quando a marca não tem organização. */
export const logoOwner = () => brand.organizacao || brand.nome;

/**
 * Troca as marcações do guia ({{produto}}, {{nome_curto}}, {{organizacao}}) pelos dados da marca ativa.
 * `json`: o texto é um JSON inteiro, então os valores entram escapados como texto JSON.
 */
export function brandText(text, { json = false } = {}) {
  const put = (value) => (json ? JSON.stringify(value).slice(1, -1) : value);
  return String(text ?? '')
    .replaceAll('{{produto}}', put(brand.nome))
    .replaceAll('{{nome_curto}}', put(brand.nomeCurto))
    .replaceAll('{{organizacao_capa}}', put(brand.organizacao))
    .replaceAll('{{organizacao}}', put(logoOwner()));
}
