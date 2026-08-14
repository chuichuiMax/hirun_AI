import { apiDelete, apiGet, apiPatch, apiPost, apiPut, apiRequest } from './base'

const encodeQuery = (params = {}) => {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') query.set(key, String(value))
  })
  const text = query.toString()
  return text ? `?${text}` : ''
}

export const contentApi = {
  getBootstrap: () => apiGet('/api/content/bootstrap'),
  createTask: (payload) => apiPost('/api/content/tasks', payload),
  listTasks: (params) => apiGet(`/api/content/tasks${encodeQuery(params)}`),
  getTask: (taskId) => apiGet(`/api/content/tasks/${taskId}`),
  updateTask: (taskId, payload) => apiPatch(`/api/content/tasks/${taskId}`, payload),
  deleteTask: (taskId) => apiDelete(`/api/content/tasks/${taskId}`),
  duplicateTask: (taskId) => apiPost(`/api/content/tasks/${taskId}/duplicate`),
  saveBrief: (taskId, brief) => apiPut(`/api/content/tasks/${taskId}/brief`, { brief }),
  compileBrief: (taskId, brief) =>
    apiPost(`/api/content/tasks/${taskId}/compile-brief`, { brief }),
  recommendStrategy: (taskId) => apiPost(`/api/content/tasks/${taskId}/strategy/recommend`),
  saveStrategy: (taskId, strategy) =>
    apiPut(`/api/content/tasks/${taskId}/strategy`, strategy),
  validateStrategy: (payload) => apiPost('/api/content/strategy/validate', payload),
  getRuleBundle: (versionId) =>
    apiGet(`/api/content/rule-versions/${versionId}/bundle`),
  createRun: (taskId, payload) => apiPost(`/api/content/tasks/${taskId}/runs`, payload),
  getRun: (runId) => apiGet(`/api/content/runs/${runId}`),
  resumeRun: (runId, payload) => apiPost(`/api/content/runs/${runId}/resume`, payload),
  cancelRun: (runId) => apiPost(`/api/content/runs/${runId}/cancel`),
  retryNode: (runId, payload) => apiPost(`/api/content/runs/${runId}/retry-node`, payload),
  streamRunEvents: (runId, afterSeq = '0-0', options = {}) =>
    apiRequest(
      `/api/content/runs/${runId}/events?after_seq=${encodeURIComponent(afterSeq)}`,
      { method: 'GET', ...options },
      true,
      'raw'
    ),
  getTaskArtifact: (taskId) => apiGet(`/api/content/tasks/${taskId}/artifact`),
  updateArtifact: (artifactId, payload) =>
    apiPatch(`/api/content/artifacts/${artifactId}`, payload),
  reviewArtifact: (artifactId, payload = {}) =>
    apiPost(`/api/content/artifacts/${artifactId}/review`, payload),
  finalizeArtifact: (artifactId, payload = {}) =>
    apiPost(`/api/content/artifacts/${artifactId}/finalize`, payload),
  regenerateArtifact: (artifactId, payload) =>
    apiPost(`/api/content/artifacts/${artifactId}/regenerate`, payload),
  listArtifactVersions: (artifactId) =>
    apiGet(`/api/content/artifacts/${artifactId}/versions`),
  listXiaohongshuAccounts: () => apiGet('/api/content/xiaohongshu/accounts'),
  createXiaohongshuAccount: (payload) =>
    apiPost('/api/content/xiaohongshu/accounts', payload),
  updateXiaohongshuAccount: (accountId, payload) =>
    apiPatch(`/api/content/xiaohongshu/accounts/${accountId}`, payload),
  deleteXiaohongshuAccount: (accountId) =>
    apiDelete(`/api/content/xiaohongshu/accounts/${accountId}`),
  loginXiaohongshuAccount: (accountId) =>
    apiPost(`/api/content/xiaohongshu/accounts/${accountId}/login`),
  checkXiaohongshuAccount: (accountId) =>
    apiPost(`/api/content/xiaohongshu/accounts/${accountId}/check`),
  getXiaohongshuLoginSession: (sessionId) =>
    apiGet(`/api/content/xiaohongshu/login-sessions/${sessionId}`),
  createDistribution: (artifactId, payload) =>
    apiPost(`/api/content/artifacts/${artifactId}/distributions`, payload),
  listDistributions: (artifactId) =>
    apiGet(`/api/content/artifacts/${artifactId}/distributions`),
  getDistribution: (jobId) => apiGet(`/api/content/distributions/${jobId}`),
  getDistributionScreenshot: (resultId) =>
    apiGet(`/api/content/distribution-results/${resultId}/screenshot`, {}, true, 'blob'),
  listRuleVersions: () => apiGet('/api/content/admin/rules'),
  getAdminRuleBundle: (versionId) =>
    apiGet(`/api/content/admin/rules/${versionId}/bundle`),
  createRuleDraft: (payload) => apiPost('/api/content/admin/rules/drafts', payload),
  saveRuleDraft: (versionId, payload) =>
    apiPut(`/api/content/admin/rules/${versionId}/bundle`, payload),
  discardRuleDraft: (versionId) => apiDelete(`/api/content/admin/rules/${versionId}`),
  publishRuleVersion: (versionId, payload = {}) =>
    apiPost(`/api/content/admin/rules/${versionId}/publish`, payload),
  rollbackRuleVersion: (versionId, payload = {}) =>
    apiPost(`/api/content/admin/rules/${versionId}/rollback`, payload),
  listIndustryTemplates: () => apiGet('/api/content/admin/industry-templates'),
  listWorkflowTemplates: () => apiGet('/api/content/admin/workflow-templates')
}
