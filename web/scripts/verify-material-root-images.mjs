import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import process from 'node:process'

const api = readFileSync(new URL('../src/apis/material_library_api.js', import.meta.url), 'utf8')
const view = readFileSync(new URL('../src/views/MaterialLibraryView.vue', import.meta.url), 'utf8')

assert.match(api, /root_only/)
assert.match(view, /async function loadRootItems\(\)/)
assert.match(view, /Promise\.all\(\[loadGalleries\(\), loadRootItems\(\)\]\)/)
assert.match(view, /我的素材图片/)
assert.match(view, /FolderPlus[^\n]*新建图库/)
assert.match(view, /privateRootCategoryId = 'private-root'/)
assert.match(view, /v-if="isGalleryRoot && rootTotal > 24"[^\n]*v-model:current="rootPage"/)
assert.match(view, /const editLocationOptions = computed/)
assert.match(view, /location: editForm\.location/)
assert.match(view, /target: \{ scope, gallery_id: null \}/)
assert.match(view, /watch\(materialScope,/)
assert(view.indexOf('v-for="group in galleryGroups"') < view.indexOf('我的素材图片'), 'custom gallery cards precede root images')

// Evaluate the card's actual location interpolation using stored backend root names.
const cardLocationExpression = view.match(/<small>上传者 \{\{ item\.uploaded_by_name \}\} · \{\{ (.*?) \}\}/)?.[1]
assert(cardLocationExpression, 'image card must include a location label')
const cardLocationLabel = new Function('isGalleryRoot', 'materialScope', 'item', `return (${cardLocationExpression})`)
for (const fixture of [
  { root: true, scope: 'private', item: { category: 'private-root', category_name: '我的素材（根目录）' }, label: '我的素材' },
  { root: true, scope: 'private', item: { category: 'uncategorized', category_name: '未分类' }, label: '我的素材' },
  { root: false, scope: 'private', item: { category: 'uncategorized', category_name: '未分类' }, label: '未分类' },
  { root: true, scope: 'enterprise', item: { category: 'enterprise-root', category_name: '企业素材' }, label: '企业共享' },
  { root: false, scope: 'private', item: { category: 'folder', category_name: '背景' }, label: '背景' },
  { root: false, scope: 'private', item: { material_type: 'cover_template', category_name: '活动海报' }, label: '活动海报' }
]) {
  assert.equal(cardLocationLabel(fixture.root, fixture.scope, fixture.item), fixture.label,
    `card location for ${fixture.item.category_name} must use the expected public label`)
}

const apiScript = api.replace(/^import .*\r?\n/, '').replace('export const materialLibraryApi', 'const materialLibraryApi')
const apiClient = new Function('apiGet', `${apiScript}\nreturn materialLibraryApi`)((url) => url)
const rootUrl = new URL(apiClient.listItems({ material_type: 'image', scope: 'enterprise', root_only: true, page: 2 }), 'https://example.test')
assert.equal(rootUrl.searchParams.get('scope'), 'enterprise')
assert.equal(rootUrl.searchParams.get('root_only'), 'true')
assert.equal(rootUrl.searchParams.get('page'), '2')
assert.equal(apiClient.listItems({ category: 'folder' }), '/api/material-library/items?category=folder')

console.log('material root static contract passed')

// Exercise the real setup functions; only network, browser URL and UI messages are replaced.
const script = view.match(/<script setup>([\s\S]*?)<\/script>/)[1]
  .replace(/^import [\s\S]*? from ['"][^'"]+['"]\r?\n/gm, '')
  .replace('import.meta.env.BASE_URL', "'/'")
const setup = new Function('computed', 'reactive', 'ref', 'watch', 'onBeforeUnmount', 'materialLibraryApi', 'URL', 'message', `${script}
return { loadRoot, loadItems, materialScope, activeGallery, categories, rootItems, rootTotal,
  rootPage, galleries, loading, search, queryInput, showEdit, saveEdit, editForm, editLocationOptions }
`)
// The planned static checker is dependency-free; opt in to Vue runtime checks after installation.
if (!process.argv.includes('--behavior')) process.exit(0)
const { computed, effectScope, nextTick, reactive, ref, watch } = await import('vue')
const deferred = () => {
  let resolve
  const promise = new Promise((done) => { resolve = done })
  return { promise, resolve }
}
const scope = effectScope()
let unmount
let serial = 0
const liveUrls = new Set()
const errors = []
const requests = []
const galleryRequests = []
const writes = []
const network = {
  listGalleries: () => {
    const pending = deferred()
    galleryRequests.push(pending)
    return pending.promise
  },
  listItems: (params) => {
    const pending = deferred()
    requests.push({ params, ...pending })
    return pending.promise
  },
  getItemThumbnail: async () => ({ blob: async () => ({}) }),
  updateItem: async (id, payload) => { writes.push({ id, payload }) }
}
const state = scope.run(() => setup(computed, reactive, ref,
  (source, callback) => watch(source, callback), (callback) => { unmount = callback }, network, {
    createObjectURL: () => { const url = `blob:test-${++serial}`; liveUrls.add(url); return url },
    revokeObjectURL: (url) => liveUrls.delete(url)
  }, { error: (error) => errors.push(error), warning: (error) => errors.push(error), success: () => {} }))
const settle = async () => { for (let i = 0; i < 12; i++) await Promise.resolve() }
const gallery = { id: 'folder', code: 'folder', name: '背景', visibility: 'private', cover_item_id: 'cover' }

try {
  const first = state.loadRoot()
  assert.equal(galleryRequests.length, 1, 'folder request starts immediately')
  assert.equal(requests.length, 1, 'root image request starts before folders resolve')
  assert.deepEqual(requests[0].params, {
    material_type: 'image', scope: 'private', root_only: true, query: '', sort: 'newest', page: 1, page_size: 24
  })
  requests[0].resolve({ items: [{ id: 'loose', name: '图片' }], total: 25 })
  await settle()
  assert.equal(state.loading.value, true, 'spinner waits for both requests')
  galleryRequests[0].resolve({ galleries: [gallery] })
  await first
  assert.equal(state.rootTotal.value, 25)
  assert(liveUrls.has(state.rootItems.value[0].previewUrl), 'folder completion must not revoke loose image URLs')
  assert(liveUrls.has(state.galleries.value[0].coverUrl))

  state.rootPage.value = 2
  const second = state.loadRoot()
  assert.equal(requests[1].params.page, 2)
  galleryRequests[1].resolve({ galleries: [gallery] })
  await settle()
  requests[1].resolve({ items: [{ id: 'second' }], total: 25 })
  await second
  assert.equal(liveUrls.size, 2, 'reload releases old URLs, keeping both current branches')
  assert(liveUrls.has(state.galleries.value[0].coverUrl), 'image completion must not revoke folder URLs')

  const stale = state.loadRoot()
  state.materialScope.value = 'enterprise'
  await nextTick()
  assert.equal(requests[3].params.scope, 'enterprise')
  assert.equal(requests[3].params.page, 1, 'scope switch resets root pagination')
  galleryRequests[3].resolve({ galleries: [] })
  requests[3].resolve({ items: [{ id: 'shared' }], total: 1 })
  await settle()
  galleryRequests[2].resolve({ galleries: [gallery] })
  requests[2].resolve({ items: [{ id: 'stale-private' }], total: 99 })
  await stale
  assert.equal(state.rootItems.value[0].id, 'shared', 'late private response cannot replace enterprise images')
  assert.equal(liveUrls.size, 1, 'stale response cannot leak object URLs')

  state.categories.value = [{ ...gallery, visibility: 'enterprise' }]
  state.showEdit({ id: 'shared', name: '图片', category: 'enterprise-root' })
  assert.deepEqual(state.editLocationOptions.value.map((option) => option.target), [
    { scope: 'enterprise', gallery_id: null }, { scope: 'enterprise', gallery_id: 'folder' }
  ])
  assert.deepEqual(state.editForm.location, { scope: 'enterprise', gallery_id: null })
  state.editForm.location = state.editLocationOptions.value[1].target
  const save = state.saveEdit()
  await settle()
  assert.deepEqual(writes[0], { id: 'shared', payload: { name: '图片', location: { scope: 'enterprise', gallery_id: 'folder' } } })
  galleryRequests[4].resolve({ galleries: [] })
  requests[4].resolve({ items: [], total: 0 })
  await save
  assert.equal(state.rootItems.value.length, 0, 'moving a loose image refreshes the root list')

  state.queryInput.value = '新名称'
  state.rootPage.value = 4
  state.search()
  assert.equal(requests[5].params.query, '新名称')
  assert.equal(requests[5].params.page, 1)
  unmount()
  requests[5].resolve({ items: [{ id: 'late' }], total: 1 })
  galleryRequests[5].resolve({ galleries: [gallery] })
  await settle()
  assert.equal(liveUrls.size, 0, 'unmount invalidates pending preview requests')
  assert.deepEqual(errors, [])
} finally {
  unmount()
  scope.stop()
}
console.log('material root behavior checks passed')
