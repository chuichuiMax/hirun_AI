<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { Plus, Search, Trash2 } from 'lucide-vue-next'

import { coverApi } from '@/apis/cover_api'
import { userApi } from '@/apis/user_api'
import PageHeader from '@/components/shared/PageHeader.vue'
import { assetUrl } from '@/utils/assetUrl'

const COVER_TABS = [
  { key: 'chinese', label: '中国风骨' },
  { key: 'european', label: '欧洲经典' },
  { key: 'modern', label: '现代之源' }
]
const COVER_ACCEPT = '.png,.jpg,.jpeg'
const COVER_TYPES = ['image/png', 'image/jpeg']

const emptyForm = () => ({
  category: 'chinese',
  files: []
})

const loading = ref(false)
const saving = ref(false)
const togglingId = ref('')
const activeCategory = ref('chinese')
const covers = ref([])
const keywordInput = ref('')
const keyword = ref('')
const modalOpen = ref(false)
const form = reactive(emptyForm())
const fileInputRef = ref(null)
const emptySlotCount = computed(() => Math.max(2 - form.files.length, 1))
const emptyDescription = computed(() =>
  keyword.value ? '未找到匹配的封面' : '当前风格暂无封面，点击右上角新增封面'
)

const formatCreatedAt = (value) => {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const pad = (num) => String(num).padStart(2, '0')
  return `${date.getFullYear()}.${pad(date.getMonth() + 1)}.${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

const loadCovers = async () => {
  loading.value = true
  try {
    const response = await coverApi.listCovers({
      category: activeCategory.value,
      keyword: keyword.value
    })
    covers.value = response.covers || []
  } catch (error) {
    message.error(error.message || '加载封面失败')
  } finally {
    loading.value = false
  }
}

const resetForm = () => {
  form.files.forEach((item) => URL.revokeObjectURL(item.previewUrl))
  Object.assign(form, emptyForm())
}

const openCreate = () => {
  resetForm()
  form.category = activeCategory.value
  modalOpen.value = true
}

const openFilePicker = () => {
  fileInputRef.value?.click()
}

const isCoverFile = (file) => {
  if (COVER_TYPES.includes(file.type)) return true
  const name = file.name.toLowerCase()
  return name.endsWith('.png') || name.endsWith('.jpg') || name.endsWith('.jpeg')
}

const fileNameOf = (file) => file.name.replaceAll('\\', '/').split('/').pop().trim()

const hasDuplicateNames = (files) => {
  const names = files.map((file) => fileNameOf(file).toLowerCase()).filter(Boolean)
  return names.length !== new Set(names).size
}

const handleSearch = () => {
  keyword.value = keywordInput.value.trim()
  void loadCovers()
}

const handleFileChange = (event) => {
  const selected = Array.from(event.target.files || [])
  event.target.value = ''
  if (selected.length === 0) return
  const invalid = selected.find((file) => !isCoverFile(file))
  if (invalid) {
    message.warning('仅支持 png/JPG 格式')
    return
  }
  const nextFiles = [...form.files.map((item) => item.file), ...selected]
  if (hasDuplicateNames(nextFiles)) {
    message.warning('图片名不能重复')
    return
  }
  selected.forEach((file) => {
    form.files.push({ file, previewUrl: URL.createObjectURL(file) })
  })
}

const removeFile = (index) => {
  URL.revokeObjectURL(form.files[index].previewUrl)
  form.files.splice(index, 1)
}

const closeCreate = () => {
  modalOpen.value = false
  resetForm()
}

const saveCover = async () => {
  if (!form.files.length) {
    message.warning('请上传封面')
    return
  }
  if (hasDuplicateNames(form.files.map((item) => item.file))) {
    message.warning('图片名不能重复')
    return
  }
  saving.value = true
  try {
    const category = form.category
    for (const item of form.files) {
      const uploaded = await userApi.uploadImage(item.file)
      await coverApi.createCover({
        category,
        image_url: uploaded.image_url || uploaded.url,
        image_name: fileNameOf(item.file)
      })
    }
    const shouldReload = activeCategory.value === category
    message.success('封面已创建')
    closeCreate()
    activeCategory.value = category
    if (shouldReload) await loadCovers()
  } catch (error) {
    message.error(error.message || '保存封面失败')
  } finally {
    saving.value = false
  }
}

const toggleEnabled = async (cover, enabled) => {
  togglingId.value = cover.id
  try {
    await coverApi.updateCover(cover.id, { enabled })
    cover.enabled = enabled
  } catch (error) {
    message.error(error.message || '更新状态失败')
  } finally {
    togglingId.value = ''
  }
}

const removeCover = (cover) => {
  Modal.confirm({
    title: '删除封面',
    content: '删除后不可恢复。',
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      await coverApi.deleteCover(cover.id)
      message.success('封面已删除')
      await loadCovers()
    }
  })
}

watch(activeCategory, loadCovers, { immediate: true })
</script>

<template>
  <div class="cover-manage-view">
    <PageHeader
      v-model:active-key="activeCategory"
      title="封面管理"
      :tabs="COVER_TABS"
      :loading="loading"
      :show-border="true"
      aria-label="封面风格切换"
    >
      <template #actions>
        <a-button type="primary" class="lucide-icon-btn" @click="openCreate">
          <Plus :size="14" />
          新增封面
        </a-button>
      </template>
    </PageHeader>

    <div class="cover-manage-content">
      <div class="cover-toolbar">
        <a-input
          v-model:value="keywordInput"
          class="search-input"
          placeholder="图片名"
          allow-clear
          @pressEnter="handleSearch"
          @clear="handleSearch"
        >
          <template #prefix><Search :size="14" /></template>
        </a-input>
        <a-button type="primary" @click="handleSearch">查询</a-button>
      </div>
      <div v-if="covers.length === 0" class="cover-empty">
        <a-empty :image="false" :description="emptyDescription" />
      </div>
      <div v-else class="cover-grid">
        <article v-for="cover in covers" :key="cover.id" class="cover-card">
          <div class="cover-media">
            <img :src="assetUrl(cover.image_url)" :alt="cover.image_name || '封面'" />
            <p v-if="cover.title" class="cover-title">{{ cover.title }}</p>
            <div class="cover-actions">
              <a-switch
                size="small"
                :checked="cover.enabled"
                :loading="togglingId === cover.id"
                @change="(checked) => toggleEnabled(cover, checked)"
              />
              <button type="button" class="cover-delete" aria-label="删除封面" @click="removeCover(cover)">
                <Trash2 :size="16" />
              </button>
            </div>
          </div>
          <div class="cover-name" :title="cover.image_name">{{ cover.image_name }}</div>
          <div class="cover-meta">
            <span>生成量 ({{ cover.generation_count }})</span>
            <span>创建时间：{{ formatCreatedAt(cover.created_at) }}</span>
          </div>
        </article>
      </div>
    </div>

    <a-modal
      v-model:open="modalOpen"
      title="新增封面"
      :mask-closable="false"
      :footer="null"
      width="520px"
      @cancel="resetForm"
    >
      <a-form
        class="cover-form"
        :model="form"
        :label-col="{ style: { width: '92px' } }"
        :wrapper-col="{ style: { flex: 1 } }"
      >
        <a-form-item label="封面类型" required>
          <a-select v-model:value="form.category" placeholder="请选择封面类型">
            <a-select-option v-for="tab in COVER_TABS" :key="tab.key" :value="tab.key">
              {{ tab.label }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item required>
          <template #label>
            <div class="cover-upload-label">
              <span>上传封面</span>
              <span class="cover-format-hint">(格式: png/JPG)</span>
            </div>
          </template>
          <div class="cover-upload">
            <input
              ref="fileInputRef"
              type="file"
              :accept="COVER_ACCEPT"
              multiple
              hidden
              @change="handleFileChange"
            />
            <div
              v-for="(item, index) in form.files"
              :key="item.previewUrl"
              class="cover-upload-item"
            >
              <div class="cover-upload-slot is-filled">
                <img :src="item.previewUrl" :alt="item.file.name" />
                <button type="button" class="cover-upload-remove" aria-label="移除封面" @click="removeFile(index)">
                  <Trash2 :size="14" />
                </button>
              </div>
              <span class="cover-upload-name" :title="item.file.name">{{ item.file.name }}</span>
            </div>
            <button
              v-for="slot in emptySlotCount"
              :key="`empty-${slot}`"
              type="button"
              class="cover-upload-slot"
              aria-label="上传封面"
              @click="openFilePicker"
            >
              <Plus :size="22" />
            </button>
            <button type="button" class="cover-browse" @click="openFilePicker">浏览</button>
          </div>
        </a-form-item>
      </a-form>
      <div class="cover-form-footer">
        <a-button type="primary" @click="closeCreate">取消</a-button>
        <a-button type="primary" :loading="saving" @click="saveCover">确定</a-button>
      </div>
    </a-modal>
  </div>
</template>

<style scoped lang="less">
.cover-manage-view {
  display: flex;
  flex-direction: column;
  min-height: 100%;
  background: var(--gray-0);
  color: var(--gray-1000);
}

.cover-manage-content {
  padding: 20px var(--page-padding) 32px;
}

.cover-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;

  .search-input {
    width: 280px;
  }
}

.cover-empty {
  padding: 80px 0;
}

.cover-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 24px;
}

.cover-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.cover-media {
  position: relative;
  overflow: hidden;
  border-radius: 8px;
  background: var(--gray-25);
  aspect-ratio: 3 / 4;

  img {
    display: block;
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .cover-title {
    position: absolute;
    left: 14px;
    right: 14px;
    bottom: 48px;
    margin: 0;
    color: var(--gray-0);
    font-size: 16px;
    font-weight: 600;
    line-height: 1.4;
    text-shadow: 0 1px 8px rgba(0, 0, 0, 0.45);
  }

  .cover-actions {
    position: absolute;
    right: 10px;
    bottom: 10px;
    display: none;
    align-items: center;
    gap: 8px;
    padding: 6px 8px;
    border-radius: 8px;
    background: var(--gray-0);
  }

  &:hover .cover-actions,
  &:focus-within .cover-actions {
    display: inline-flex;
  }
}

.cover-delete {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--main-color);
  cursor: pointer;

  &:hover,
  &:focus-visible {
    background: var(--main-20);
    outline: none;
  }
}

.cover-name {
  overflow: hidden;
  color: var(--gray-900);
  font-size: 13px;
  line-height: 20px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cover-meta {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  color: var(--color-text-secondary);
  font-size: 12px;
  line-height: 18px;
}

.cover-form {
  padding: 8px 12px 0;

  :deep(.ant-form-item) {
    margin-bottom: 18px;
  }

  :deep(.ant-form-item-label > label) {
    height: auto;
    color: var(--color-text);
  }

  :deep(.ant-select) {
    width: 100%;
  }
}

.cover-upload-label {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  line-height: 20px;
}

.cover-format-hint {
  color: var(--color-text-tertiary);
  font-size: 12px;
  font-weight: 400;
  line-height: 18px;
}

.cover-upload {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 12px;
}

.cover-upload-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 72px;
}

.cover-upload-name {
  overflow: hidden;
  color: var(--color-text-secondary);
  font-size: 12px;
  line-height: 16px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cover-upload-slot {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 72px;
  height: 72px;
  padding: 0;
  border: 1px dashed var(--gray-200);
  border-radius: 8px;
  background: var(--gray-0);
  color: var(--gray-400);
  cursor: pointer;

  &:hover,
  &:focus-visible {
    border-color: var(--main-color);
    color: var(--main-color);
    outline: none;
  }

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    border-radius: 7px;
  }
}

.cover-upload-slot.is-filled {
  border-style: solid;
  cursor: default;
}

.cover-upload-remove {
  position: absolute;
  top: 2px;
  right: 2px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  padding: 0;
  border: 0;
  border-radius: 4px;
  background: var(--gray-0);
  color: var(--main-color);
  cursor: pointer;
}

.cover-browse {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--main-color);
  font-size: 14px;
  line-height: 22px;
  cursor: pointer;

  &:hover,
  &:focus-visible {
    text-decoration: underline;
    outline: none;
  }
}

.cover-form-footer {
  display: flex;
  justify-content: center;
  gap: 16px;
  padding: 8px 0 4px;
}
</style>
