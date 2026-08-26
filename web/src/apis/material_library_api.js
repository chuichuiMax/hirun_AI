import { apiDelete, apiGet, apiPatch, apiPost } from './base'

const encodeQuery = (params = {}) => {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') query.set(key, String(value))
  })
  const text = query.toString()
  return text ? `?${text}` : ''
}

export const materialLibraryApi = {
  listItems: (params) => apiGet(`/api/material-library/items${encodeQuery(params)}`),
  importImages: (files, category = '未分类', tags = []) => {
    const form = new FormData()
    Array.from(files).forEach((file) => form.append('files', file))
    form.append('category', category)
    form.append('tags', tags.join(','))
    return apiPost('/api/material-library/images/import', form)
  },
  updateItem: (itemId, payload) => apiPatch(`/api/material-library/items/${itemId}`, payload),
  deleteItem: (itemId) => apiDelete(`/api/material-library/items/${itemId}`),
  getItemFile: (itemId) =>
    apiGet(`/api/material-library/items/${itemId}/file`, {}, true, 'blob')
}
