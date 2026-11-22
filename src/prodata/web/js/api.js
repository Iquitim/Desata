import { brand } from './brand.js';
// Cliente da API REST. Erros viram ApiError com a mensagem enviada pelo servidor.

export class ApiError extends Error {
  constructor(message, status, code) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function request(method, url, body, signal) {
  const init = { method, headers: {}, signal };
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(url, init);
  } catch (err) {
    if (err?.name === 'AbortError') throw err; // pedido cancelado de propósito (prévia de impacto)
    throw new ApiError(`Servidor indisponível. Verifique se o ${brand.nome} está em execução.`, 0, 'network');
  }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    throw new ApiError(describe(data) || `Erro ${res.status}`, res.status, data?.code);
  }
  return data;
}

function describe(data) {
  if (!data) return '';
  if (typeof data.detail === 'string') return data.detail;
  if (Array.isArray(data.detail)) {
    return data.detail.map((d) => `${(d.loc || []).slice(1).join('.')}: ${d.msg}`).join('; ');
  }
  return '';
}

const enc = encodeURIComponent;

export const api = {
  catalog: () => request('GET', '/api/catalog'),

  datasets: () => request('GET', '/api/datasets'),
  previewDataset: (name, options = {}, rows = 100) =>
    request('POST', `/api/datasets/${enc(name)}/preview?rows=${rows}`, options),
  deleteDataset: (name) => request('DELETE', `/api/datasets/${enc(name)}`),
  linkDataset: (path, name = null) => request('POST', '/api/datasets/link', { path, name }),

  /** Upload com progresso (fetch não expõe progresso de envio). */
  uploadDataset(file, { overwrite = false, onProgress } = {}) {
    return new Promise((resolve, reject) => {
      const form = new FormData();
      form.append('file', file);
      form.append('overwrite', String(overwrite));
      const xhr = new XMLHttpRequest();
      xhr.open('POST', '/api/datasets');
      xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total);
      xhr.onload = () => {
        const data = JSON.parse(xhr.responseText || 'null');
        if (xhr.status >= 200 && xhr.status < 300) resolve(data);
        else reject(new ApiError(describe(data) || `Erro ${xhr.status}`, xhr.status, data?.code));
      };
      xhr.onerror = () => reject(new ApiError('Falha de rede durante o envio.', 0, 'network'));
      xhr.send(form);
    });
  },

  connections: () => request('GET', '/api/connections'),
  saveConnection: (connection, password) =>
    request('PUT', `/api/connections/${enc(connection.id)}`, { connection, password }),
  deleteConnection: (id) => request('DELETE', `/api/connections/${enc(id)}`),
  testConnection: (id) => request('POST', `/api/connections/${enc(id)}/test`),
  connectionTables: (id) => request('GET', `/api/connections/${enc(id)}/tables`),
  previewConnection: (id, body, rows = 100) => request('POST', `/api/connections/${enc(id)}/preview?rows=${rows}`, body),

  dashboardFiltered: (workflow) => request('POST', '/api/dashboard/filtered', { workflow }),
  dashboardFilterOptions: (workflow) => request('POST', '/api/dashboard/filter-options', { workflow }),
  dashboardExportLog: (entry) => request('POST', '/api/dashboard/export-log', entry),
  dashboardExportData: (workflow) => request('POST', '/api/dashboard/export-data', { workflow }),
  jiraConnections: () => request('GET', '/api/jira/connections'),
  jiraQueries: () => request('GET', '/api/jira/queries'),
  testJira: (body) => request('POST', '/api/jira/test', body),
  saveJiraConnection: (body) => request('PUT', `/api/jira/connections/${enc(body.connection.id)}`, body),
  deleteJiraConnection: (id) => request('DELETE', `/api/jira/connections/${enc(id)}`),
  jiraCatalog: (id) => request('GET', `/api/jira/connections/${enc(id)}/catalog`),
  jiraScope: (id, key) => request('GET', `/api/jira/connections/${enc(id)}/projects/${enc(key)}/scope`),
  saveJiraQuery: (body) => request('PUT', `/api/jira/queries/${enc(body.id)}`, body),
  deleteJiraQuery: (id) => request('DELETE', `/api/jira/queries/${enc(id)}`),
  previewJira: (body) => request('POST', '/api/jira/queries/preview', body),
  reloadJiraQuery: (id) => request('POST', `/api/jira/queries/${enc(id)}/reload`),
  forgetJiraQuery: (id) => request('DELETE', `/api/jira/queries/${enc(id)}/local`),

  apis: () => request('GET', '/api/apis'),
  apiExamples: () => request('GET', '/api/apis/examples'),
  saveApi: (body) => request('PUT', `/api/apis/${enc(body.source.id)}`, body),
  deleteApi: (id) => request('DELETE', `/api/apis/${enc(id)}`),
  previewApi: (body, rows = 100) => request('POST', `/api/apis/preview?rows=${rows}`, body),
  queries: () => request('GET', '/api/queries'),
  saveQuery: (query) => request('PUT', `/api/queries/${enc(query.id)}`, query),
  deleteQuery: (id) => request('DELETE', `/api/queries/${enc(id)}`),
  previewQuery: (definition, rows = 100) => request('POST', `/api/queries/preview?rows=${rows}`, definition),

  saveWorkflowFile: (path, workflow, origin = 'manual') => request('POST', '/api/files/workflow/save', { path, workflow, origin }),
  portableSources: (workflow, espaco = null) => request('POST', '/api/portable/sources', { workflow, espaco }),
  portablePreview: (workflow) => request('POST', '/api/portable/share/preview', { workflow }),
  portableShare: (workflow, path, sources) => request('POST', '/api/portable/share/save', { workflow, path, sources }),
  portableMaskPreview: (workflow, key, mask) => request('POST', '/api/portable/share/mask-preview', { workflow, key, mask }),
  openWorkflowFile: (path) => request('POST', '/api/files/workflow/open', { path }),

  refreshCache: (wfId, nodeId) => request('DELETE', `/api/cache/${enc(wfId)}/${enc(nodeId)}`),

  workflows: () => request('GET', '/api/workflows'),
  workflow: (id) => request('GET', `/api/workflows/${enc(id)}`),
  demoWorkflow: () => request('GET', '/api/workflows/demo'),
  saveWorkflow: (wf, origin = 'manual') => request('PUT', `/api/workflows/${enc(wf.id)}?origem=${origin}`, wf),
  versions: (id, current, path = null) => request('POST', `/api/workflows/${enc(id)}/versions/compare`, { current, path }),
  version: (id, version, path = null) => request('GET', `/api/workflows/${enc(id)}/versions/${enc(version)}${path ? `?arquivo=${enc(path)}` : ''}`),
  recordVersion: (id, workflow, origin, path = null) => request('POST', `/api/workflows/${enc(id)}/versions`, { workflow, origin, path }),
  schemaImpact: (workflow, source, columns) => request('POST', '/api/schema/impact', { workflow, source, columns }),
  schemaRename: (workflow, source, old, nw, onlyNode = false) => request('POST', '/api/schema/rename', { workflow, source, old, new: nw, only_node: onlyNode }),
  deleteWorkflow: (id) => request('DELETE', `/api/workflows/${enc(id)}`),

  // Espaço da equipe (spec 047)
  team: () => request('GET', '/api/equipe'),
  teamName: (nome) => request('POST', '/api/equipe/identidade', { nome }),
  addSpace: (acao, caminho, nome = '') => request('POST', '/api/equipe/espacos', { acao, caminho, nome }),
  leaveSpace: (id) => request('DELETE', `/api/equipe/espacos/${enc(id)}`),
  spaceFlows: (id) => request('GET', `/api/equipe/espacos/${enc(id)}/fluxos`),
  // abrir: { fluxo, sha256 (base do Salvar), autor, atualizado, conferir } (spec 047, RF-4732)
  spaceFlow: (id, wid) => request('GET', `/api/equipe/espacos/${enc(id)}/fluxos/${enc(wid)}/abrir`),
  // salvar: { fluxo, sha256, adiado }; 409 (code conflict) se outra pessoa salvou depois da base (RF-4761)
  saveSpaceFlow: (id, wf, { base = null, forcar = false, origem = 'manual' } = {}) => request('PUT',
    `/api/equipe/espacos/${enc(id)}/fluxos/${enc(wf.id)}?origem=${origem}${base ? `&base=${base}` : ''}${forcar ? '&forcar=true' : ''}`, wf),
  spaceVersions: (id, wid, current) => request('POST', `/api/equipe/espacos/${enc(id)}/fluxos/${enc(wid)}/versoes/comparar`, { current }),
  spaceVersion: (id, wid, version) => request('GET', `/api/equipe/espacos/${enc(id)}/fluxos/${enc(wid)}/versoes/${enc(version)}`),
  recordSpaceVersion: (id, wid, workflow) => request('POST', `/api/equipe/espacos/${enc(id)}/fluxos/${enc(wid)}/versoes`, { workflow, origin: 'restore' }),
  publishOfficial: (id, wid) => request('POST', `/api/equipe/espacos/${enc(id)}/fluxos/${enc(wid)}/oficial`),
  teamSchedules: (id) => request('GET', `/api/equipe/espacos/${enc(id)}/agendamentos`),
  assumeSchedule: (spaceId, scheduleId) => request('POST', '/api/schedules/assumir', { space_id: spaceId, schedule_id: scheduleId }),
  teamDefinitions: (id) => request('GET', `/api/equipe/espacos/${enc(id)}/definicoes`),
  shareDefinition: (id, tipo, key) => request('POST', `/api/equipe/espacos/${enc(id)}/definicoes/compartilhar`, { tipo, id: key }),
  deleteDefinition: (id, tipo, key) => request('DELETE', `/api/equipe/espacos/${enc(id)}/definicoes/${tipo}/${enc(key)}`),
  bringDefinition: (id, tipo, key) => request('POST', `/api/equipe/espacos/${enc(id)}/definicoes/${tipo}/${enc(key)}/trazer`),
  setDefinitionSecret: (id, tipo, key, valores) => request('POST', `/api/equipe/espacos/${enc(id)}/definicoes/${tipo}/${enc(key)}/segredo`, { valores }),
  missingSecrets: (id, workflow) => request('POST', `/api/equipe/espacos/${enc(id)}/segredos-faltando`, { workflow }),
  moveToSpace: (id, workflowId) => request('POST', `/api/equipe/espacos/${enc(id)}/mover`, { workflow_id: workflowId }),
  copyFromSpace: (id, wid) => request('POST', `/api/equipe/espacos/${enc(id)}/fluxos/${enc(wid)}/copia`),
  spaceMembers: (id) => request('GET', `/api/equipe/espacos/${enc(id)}/membros`),
  changeMembers: (id, acao, usuario, papel = 'leitor') => request('POST', `/api/equipe/espacos/${enc(id)}/membros`, { acao, usuario, papel }),
  spaceEditing: (id, wid, acao, forcar = false) => request('POST', `/api/equipe/espacos/${enc(id)}/fluxos/${enc(wid)}/edicao`, { acao, forcar }),

  // Agendamentos (spec 044)
  schedules: () => request('GET', '/api/schedules'),
  schedulePreview: (plan) => request('POST', '/api/schedules/preview', plan),
  createSchedule: (plan) => request('POST', '/api/schedules', plan),
  updateSchedule: (id, plan) => request('PUT', `/api/schedules/${enc(id)}`, plan),
  pauseSchedule: (id) => request('POST', `/api/schedules/${enc(id)}/pause`),
  resumeSchedule: (id) => request('POST', `/api/schedules/${enc(id)}/resume`),
  runSchedule: (id) => request('POST', `/api/schedules/${enc(id)}/run`),
  recreateSchedule: (id) => request('POST', `/api/schedules/${enc(id)}/recreate`),
  deleteSchedule: (id) => request('DELETE', `/api/schedules/${enc(id)}`),
  scheduleFailures: () => request('GET', '/api/schedules/failures/unseen'),
  scheduleFailuresSeen: () => request('POST', '/api/schedules/failures/seen'),

  sqlGenerate: (workflow, selection = [], temporaryNode = null, dialect = 'duckdb') =>
    request('POST', '/api/sql/generate', { workflow, selection, temporary_node: temporaryNode, dialect }),
  sqlVerify: (workflow) => request('POST', '/api/sql/verify', { workflow }),
  trustState: (workflow) => request('POST', '/api/trust/state', { workflow }),
  usage: () => request('GET', '/api/usage'),
  organization: () => request('GET', '/api/organization'),
  folderSources: () => request('GET', '/api/folders'),
  createFolderSource: (source) => request('POST', '/api/folders', source),
  updateFolderSource: (id, source) => request('PUT', `/api/folders/${enc(id)}`, source),
  deleteFolderSource: (id) => request('DELETE', `/api/folders/${enc(id)}`),
  linkEachFile: (folder, pattern) => request('POST', '/api/folders/link-each', { folder, pattern }),
  // Leitor de PDF (spec 037)
  pdfSources: () => request('GET', '/api/pdfs'),
  createPdf: (source) => request('POST', '/api/pdfs', source),
  createPdfExample: () => request('POST', '/api/pdfs/example'),
  pdfRecipes: () => request('GET', '/api/pdfs/recipes'),
  importPdfRecipe: (formData) => request('POST', '/api/pdfs/recipes/import', formData),
  deletePdfRecipe: (rid, force = false) => request('DELETE', `/api/pdfs/recipes/${enc(rid)}${force ? '?force=true' : ''}`),
  usePdfRecipe: (id, recipe) => request('POST', `/api/pdfs/${enc(id)}/recipe/use`, { recipe }),
  forkPdfRecipe: (id, name = '') => request('POST', `/api/pdfs/${enc(id)}/recipe/fork`, { name }),
  uploadPdf: (file, name = '', recipe = '') => { const fd = new FormData(); fd.append('file', file); fd.append('name', name); fd.append('recipe', recipe); return request('POST', '/api/pdfs/upload', fd); },
  updatePdf: (id, source) => request('PUT', `/api/pdfs/${enc(id)}`, source),
  deletePdf: (id) => request('DELETE', `/api/pdfs/${enc(id)}`),
  duplicatePdf: (id, name = '') => request('POST', `/api/pdfs/${enc(id)}/duplicate`, { name }),
  pdfDocs: (id) => request('GET', `/api/pdfs/${enc(id)}/docs`),
  addPdfDocs: (id, files) => { const fd = new FormData(); [...files].forEach((f) => fd.append('files', f)); return request('POST', `/api/pdfs/${enc(id)}/docs/add`, fd); },
  leavePdfDoc: (id, name) => request('POST', `/api/pdfs/${enc(id)}/docs/leave`, { name }),
  bringBackPdfDoc: (id, name) => request('POST', `/api/pdfs/${enc(id)}/docs/back`, { name }),
  pdfWords: (id, doc) => request('GET', `/api/pdfs/${enc(id)}/docs/words?doc=${enc(doc)}`),
  pdfPageUrl: (id, doc, page, scale) => `/api/pdfs/${enc(id)}/docs/page.png?doc=${enc(doc)}&page=${page}&escala=${scale}`,
  pdfRecipe: (id) => request('GET', `/api/pdfs/${enc(id)}/recipe`),
  savePdfRecipe: (id, recipe) => request('PUT', `/api/pdfs/${enc(id)}/recipe`, recipe),
  suggestPdfField: (id, doc, words) => request('POST', `/api/pdfs/${enc(id)}/suggest/field`, { doc, words }),
  suggestPdfTable: (id, doc, page, area, name) => request('POST', `/api/pdfs/${enc(id)}/suggest/table`, { doc, page, area, name }),
  adjustPdfTable: (id, body) => request('POST', `/api/pdfs/${enc(id)}/suggest/table_edge`, body),
  evaluatePdf: (id, recipe, { docs = [], limit = 12, signal } = {}) => request('POST', `/api/pdfs/${enc(id)}/evaluate`, { recipe, docs, limit }, signal),
  pdfOutput: (id, output, rows = 100) => request('GET', `/api/pdfs/${enc(id)}/outputs/${enc(output)}?rows=${rows}`),
  pdfCorrections: (id) => request('GET', `/api/pdfs/${enc(id)}/corrections`),
  addPdfCorrection: (id, doc, field, value) => request('POST', `/api/pdfs/${enc(id)}/corrections`, { doc, field, value }),
  removePdfCorrection: (id, cid) => request('DELETE', `/api/pdfs/${enc(id)}/corrections/${enc(cid)}`),
  previewFolder: (source, rows = 100) => {
    const { status, ...body } = source;
    return request('POST', `/api/folders/preview?rows=${rows}`, { source: body });
  },
  addFolder: (name, color) => request('POST', '/api/organization/folders', { name, color }),
  updateFolder: (id, name, color) => request('PUT', `/api/organization/folders/${enc(id)}`, { name, color }),
  moveFolder: (id, position) => request('POST', `/api/organization/folders/${enc(id)}/move`, { position }),
  deleteFolder: (id) => request('DELETE', `/api/organization/folders/${enc(id)}`),
  changeSources: (keys, changes) => request('PUT', '/api/organization/sources', { keys, changes }),
  forgetSources: (keys) => request('POST', '/api/organization/sources/forget', { keys }),
  models: () => request('GET', '/api/models'),
  modelVersions: (workflowId, nodeId) => request('GET', `/api/models/versions/${enc(workflowId)}/${enc(nodeId)}`),
  deleteModelVersion: (workflowId, nodeId, version, inUse) => request('DELETE', `/api/models/versions/${enc(workflowId)}/${enc(nodeId)}/${version}?in_use=${inUse}`),
  deleteModel: (name) => request('DELETE', `/api/models/${enc(name)}`),
  importModel: async (file, name = '') => {
    const body = new FormData();
    body.append('file', file);
    body.append('name', name);
    const res = await fetch('/api/models/import', { method: 'POST', body });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new ApiError(data.detail || `Erro ${res.status}`, res.status);
    return data;
  },
  exportModel: async (name) => {
    const res = await fetch(`/api/models/${enc(name)}/export`);
    if (!res.ok) throw new ApiError(`Erro ${res.status}`, res.status);
    return { blob: await res.blob(), name: `${name}.modelo` };
  },
  constants: () => request('GET', '/api/constants'),
  saveConstant: (constant, previous = null) => request('POST', '/api/constants', { constant, previous }),
  deleteConstant: (name) => request('DELETE', `/api/constants/${enc(name)}`),
  trustConfirm: (workflow) => request('POST', '/api/trust/confirm', { workflow }),
  sqlVerifyStatus: (workflowId) => request('GET', `/api/sql/verify/${encodeURIComponent(workflowId)}`),
  sqlDownload: async (workflow, selection, temporaryNode, mode, dialect = 'duckdb') => {
    const res = await fetch('/api/sql/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ workflow, selection, temporary_node: temporaryNode, mode, dialect }),
    });
    if (!res.ok) throw new ApiError(`Erro ${res.status}`, res.status);
    const name = /filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') || '')?.[1] || 'fluxo.sql';
    return { blob: await res.blob(), name };
  },
  progress: (workflowId) => request('GET', `/api/execute/${encodeURIComponent(workflowId)}/progress`),
  cancelRun: (workflowId) => request('POST', `/api/execute/${encodeURIComponent(workflowId)}/cancel`),
  // espaco (spec 048): fluxo do espaço da equipe, que usa as constantes, conexões, consultas e APIs da equipe
  execute: (workflow, targetNodeId = null, holdExports = false, espaco = null) =>
    request('POST', '/api/execute', { workflow, target_node_id: targetNodeId, hold_exports: holdExports, espaco }),
  pendingExports: (workflow, targetNodeId = null) =>
    request('POST', '/api/exports/pending', { workflow, target_node_id: targetNodeId }),
  columnValues: (wfId, nodeId, anchor, column, limit = 500, search = '') =>
    request('GET', `/api/results/${enc(wfId)}/${enc(nodeId)}/${enc(anchor)}/values?${new URLSearchParams({ column, limit, search })}`),
  results: (wfId, nodeId, anchor, params) =>
    request('GET', `/api/results/${enc(wfId)}/${enc(nodeId)}/${enc(anchor)}?${new URLSearchParams(params)}`),
  validateFormula: (expression, columns, multirow = false, constants = []) =>
    request('POST', '/api/formula/validate', { expression, columns, multirow, constants }),

  arrangeDashboard: (body) => request('POST', '/api/dashboard/arrange', body),
  placeDashboard: (body) => request('POST', '/api/dashboard/place', body),
  dashboardFormats: () => request('GET', '/api/dashboard/formats'),
};
