import { apiDelete, apiGet, apiPatch, apiPost } from './base'

const encodeQuery = (params = {}) => {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') query.set(key, String(value))
  })
  const text = query.toString()
  return text ? `?${text}` : ''
}

export const coverApi = {
  listCovers: (params) => apiGet(`/api/covers${encodeQuery(params)}`),
  createCover: (payload) => apiPost('/api/covers', payload),
  updateCover: (coverPk, payload) => apiPatch(`/api/covers/${coverPk}`, payload),
  deleteCover: (coverPk) => apiDelete(`/api/covers/${coverPk}`)
}
