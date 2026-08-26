<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { ImagePlus, RefreshCw, Search, Trash2, Upload } from 'lucide-vue-next'

import { contentApi } from '@/apis/content_api'
import { materialLibraryApi } from '@/apis/material_library_api'
import PageHeader from '@/components/shared/PageHeader.vue'

const route = useRoute()
const tabs = [
  { key: 'image', label: '素材图片', path: '/materials/images' },
  { key: 'cover_template', label: '封面模板', path: '/materials/cover-templates' }
]
const materialType = computed(() => route.path.endsWith('/cover-templates') ? 'cover_template' : 'image')
const loading = ref(false)
const uploading = ref(false)
const items = ref([])
const total = ref(0)
const page = ref(1)
const queryInput = ref('')
const query = ref('')
const uploadOpen = ref(false)
const selectedFiles = ref([])
const category = ref('未分类')
const tagsText = ref('')
const fileInput = ref(null)
const previewUrls = new Map()

const releasePreviews = () => {
  previewUrls.forEach((url) => URL.revokeObjectURL(url))
  previewUrls.clear()
}

const loadItems = async () => {
  loading.value = true
  try {
    const response = await materialLibraryApi.listItems({
      material_type: materialType.value,
      query: query.value,
      page: page.value,
      page_size: 24
    })
    const next = response.items || []
    const loaded = await Promise.all(next.map(async (item) => {
      const response = await materialLibraryApi.getItemFile(item.id)
      return { ...item, previewUrl: URL.createObjectURL(await response.blob()) }
    }))
    releasePreviews()
    loaded.forEach((item) => previewUrls.set(item.id, item.previewUrl))
    items.value = loaded
    total.value = response.total || 0
  } catch (error) {
    message.error(error.message || '素材加载失败')
  } finally {
    loading.value = false
  }
}

const search = () => {
  query.value = queryInput.value.trim()
  page.value = 1
  void loadItems()
}

const resetUpload = () => {
  selectedFiles.value = []
  category.value = '未分类'
  tagsText.value = ''
  if (fileInput.value) fileInput.value.value = ''
}

const chooseFiles = () => fileInput.value?.click()
const onFiles = (event) => { selectedFiles.value = Array.from(event.target.files || []) }
const openPreview = (url) => window.open(url, '_blank', 'noopener,noreferrer')

const uploadFiles = async () => {
  if (!selectedFiles.value.length) return message.warning('请选择图片文件')
  uploading.value = true
  try {
    const tags = tagsText.value.split(',').map((tag) => tag.trim()).filter(Boolean)
    if (materialType.value === 'image') {
      await materialLibraryApi.importImages(selectedFiles.value, category.value, tags)
    } else {
      await contentApi.importCoverPosterTemplates(selectedFiles.value, category.value, tags)
    }
    message.success('素材上传成功')
    uploadOpen.value = false
    resetUpload()
    page.value = 1
    await loadItems()
  } catch (error) {
    message.error(error.message || '素材上传失败')
  } finally {
    uploading.value = false
  }
}

const removeItem = (item) => Modal.confirm({
  title: '删除素材',
  content: '文件会同时从 image 桶删除；正在被封面任务使用的素材需等待任务结束后再删除。',
  okText: '删除',
  okType: 'danger',
  cancelText: '取消',
  async onOk() {
    await materialLibraryApi.deleteItem(item.id)
    message.success('素材已删除')
    await loadItems()
  }
})

watch(materialType, () => { page.value = 1; query.value = ''; queryInput.value = ''; void loadItems() }, { immediate: true })
onBeforeUnmount(releasePreviews)
</script>

<template>
  <div class="material-library-view layout-container">
    <PageHeader title="素材库" :tabs="tabs" :active-key="materialType" :loading="loading" show-border>
      <template #actions>
        <a-button type="primary" class="lucide-icon-btn" @click="uploadOpen = true">
          <Upload :size="15" />上传{{ materialType === 'image' ? '图片' : '模板' }}
        </a-button>
      </template>
    </PageHeader>
    <main class="material-content">
      <div class="toolbar">
        <a-input v-model:value="queryInput" allow-clear placeholder="搜索名称、分类或标签" @pressEnter="search" @clear="search">
          <template #prefix><Search :size="15" /></template>
        </a-input>
        <a-button @click="search">查询</a-button>
        <a-button class="lucide-icon-btn" :loading="loading" @click="loadItems"><RefreshCw :size="15" />刷新</a-button>
      </div>
      <a-spin :spinning="loading">
        <div v-if="items.length" class="material-grid">
          <article v-for="item in items" :key="item.id" class="material-card">
            <button type="button" class="preview-button" @click="openPreview(item.previewUrl)">
              <img :src="item.previewUrl" :alt="item.name" />
            </button>
            <div class="material-info">
              <strong :title="item.name">{{ item.name }}</strong>
              <small>{{ item.category }} · {{ item.width }}×{{ item.height }}</small>
              <div class="tag-row"><a-tag v-for="tag in item.tags" :key="tag">{{ tag }}</a-tag></div>
            </div>
            <button type="button" class="delete-button" aria-label="删除素材" @click="removeItem(item)"><Trash2 :size="16" /></button>
          </article>
        </div>
        <a-empty v-else :image="false" :description="query ? '未找到匹配素材' : '当前素材库为空，上传第一批素材后即可使用'">
          <a-button type="primary" @click="uploadOpen = true"><ImagePlus :size="15" />上传素材</a-button>
        </a-empty>
      </a-spin>
      <a-pagination v-if="total > 24" v-model:current="page" :total="total" :page-size="24" show-less-items @change="loadItems" />
    </main>

    <a-modal v-model:open="uploadOpen" :title="`上传${materialType === 'image' ? '素材图片' : '封面模板'}`" :confirm-loading="uploading" @ok="uploadFiles" @cancel="resetUpload">
      <div class="upload-form">
        <input ref="fileInput" type="file" multiple accept=".png,.jpg,.jpeg,.webp" hidden @change="onFiles" />
        <button type="button" class="upload-drop" @click="chooseFiles">
          <Upload :size="22" /><span>{{ selectedFiles.length ? `已选择 ${selectedFiles.length} 个文件` : '选择 PNG、JPG 或 WebP 图片' }}</span>
        </button>
        <label>分类<a-input v-model:value="category" maxlength="80" /></label>
        <label>标签<a-input v-model:value="tagsText" placeholder="多个标签使用逗号分隔" /></label>
      </div>
    </a-modal>
  </div>
</template>

<style scoped lang="less">
.material-library-view { height: 100%; display: flex; flex-direction: column; background: var(--gray-0); }
.material-content { flex: 1; overflow: auto; padding: 20px var(--page-padding); }
.toolbar { display: flex; gap: 8px; width: min(680px, 100%); margin-bottom: 18px; }
.material-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 14px; }
.material-card { position: relative; overflow: hidden; border: 1px solid var(--gray-150); border-radius: 8px; background: var(--gray-0); }
.material-card:hover { border-color: var(--gray-300); }
.preview-button { display: block; width: 100%; height: 180px; padding: 0; border: 0; background: var(--gray-25); cursor: zoom-in; }
.preview-button img { width: 100%; height: 100%; object-fit: cover; }
.material-info { display: flex; flex-direction: column; gap: 4px; min-width: 0; padding: 12px; }
.material-info strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--color-text); }
.material-info small { color: var(--color-text-secondary); }
.tag-row { min-height: 22px; overflow: hidden; white-space: nowrap; }
.delete-button { position: absolute; top: 8px; right: 8px; display: grid; place-items: center; width: 32px; height: 32px; border: 1px solid var(--gray-150); border-radius: 6px; background: var(--gray-0); color: var(--color-error-700); cursor: pointer; }
.upload-form { display: flex; flex-direction: column; gap: 16px; }
.upload-form label { display: flex; flex-direction: column; gap: 6px; color: var(--color-text); }
.upload-drop { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 28px; border: 1px dashed var(--gray-300); border-radius: 8px; background: var(--gray-25); color: var(--color-text-secondary); cursor: pointer; }
:deep(.ant-pagination) { margin-top: 20px; text-align: right; }
@media (max-width: 720px) { .toolbar { flex-wrap: wrap; }.material-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }.preview-button { height: 140px; } }
</style>
