import { apiDelete, apiGet, apiPost } from './base'

const encodeQuery = (params = {}) => {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') query.set(key, String(value))
  })
  const text = query.toString()
  return text ? `?${text}` : ''
}

export const imageDesignApi = {
  getBootstrap: () => apiGet('/api/image-design/bootstrap'),
  listClients: () => apiGet('/api/image-design/clients'),
  createClient: (payload) => apiPost('/api/image-design/clients', payload),
  listShowcase: (category) => apiGet(`/api/image-design/showcase${encodeQuery({ category })}`),
  createShowcase: (payload) => apiPost('/api/image-design/showcase', payload),
  deleteShowcase: (showcaseId) => apiDelete(`/api/image-design/showcase/${showcaseId}`),
  refinePrompt: (payload) => apiPost('/api/image-design/refine-prompt', payload),
  recognize: (materialItemId) => apiPost('/api/image-design/recognize', { material_item_id: materialItemId }),
  listRecognitions: (materialItemId) =>
    apiGet(`/api/image-design/recognitions${encodeQuery({ material_item_id: materialItemId })}`),
  generate: (payload) => {
    const controller = new AbortController()
    const timeoutId = globalThis.setTimeout(() => controller.abort(), 30000)
    return apiPost('/api/image-design/generate', payload, { signal: controller.signal })
      .finally(() => globalThis.clearTimeout(timeoutId))
  },
  getJob: (jobId) => apiGet(`/api/image-design/generate/status${encodeQuery({ job_id: jobId })}`),
  listJobs: (clientId) => apiGet(`/api/image-design/jobs${encodeQuery({ client_id: clientId })}`),
  listResults: (clientId) => apiGet(`/api/image-design/results${encodeQuery({ client_id: clientId })}`),
  getResultFile: (assetId) => apiGet(`/api/image-design/results/${assetId}/file`, {}, true, 'blob'),
  deleteResult: (assetId) => apiDelete(`/api/image-design/results/${assetId}`)
}
