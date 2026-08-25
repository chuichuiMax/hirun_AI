<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { Search } from 'lucide-vue-next'

import { variableApi } from '@/apis/variable_api'
import PageHeader from '@/components/shared/PageHeader.vue'

const SERVICE_ENTRIES = ['装修家居', '好评笔记']

const emptyForm = () => ({
  name: '',
  service_entry: undefined,
  enabled: true
})

const loading = ref(false)
const saving = ref(false)
const togglingId = ref('')
const keywordInput = ref('')
const keyword = ref('')
const variables = ref([])
const modalOpen = ref(false)
const editingId = ref('')
const form = reactive(emptyForm())

const modalTitle = computed(() => (editingId.value ? '编辑变量' : '新增变量'))

const formatCreatedAt = (value) => {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const pad = (num) => String(num).padStart(2, '0')
  return `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

const loadVariables = async () => {
  loading.value = true
  try {
    const response = await variableApi.listVariables({ keyword: keyword.value })
    variables.value = response.variables || []
  } catch (error) {
    message.error(error.message || '加载变量失败')
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  keyword.value = keywordInput.value.trim()
  void loadVariables()
}

const openCreate = () => {
  editingId.value = ''
  Object.assign(form, emptyForm())
  modalOpen.value = true
}

const openEdit = (item) => {
  editingId.value = item.id
  Object.assign(form, {
    name: item.name,
    service_entry: item.service_entry,
    enabled: item.enabled
  })
  modalOpen.value = true
}

const closeModal = () => {
  modalOpen.value = false
  editingId.value = ''
  Object.assign(form, emptyForm())
}

const saveVariable = async () => {
  const name = form.name.trim()
  const serviceEntry = String(form.service_entry || '').trim()
  if (!name) {
    message.warning('请输入变量名称')
    return
  }
  if (!serviceEntry) {
    message.warning('请选择服务入口')
    return
  }
  saving.value = true
  try {
    const payload = { name, service_entry: serviceEntry, enabled: form.enabled }
    if (editingId.value) {
      await variableApi.updateVariable(editingId.value, payload)
      message.success('变量已更新')
    } else {
      await variableApi.createVariable(payload)
      message.success('变量已创建')
    }
    closeModal()
    await loadVariables()
  } catch (error) {
    message.error(error.message || '保存变量失败')
  } finally {
    saving.value = false
  }
}

const toggleEnabled = async (item, enabled) => {
  togglingId.value = item.id
  try {
    await variableApi.updateVariable(item.id, { enabled })
    item.enabled = enabled
  } catch (error) {
    message.error(error.message || '更新状态失败')
  } finally {
    togglingId.value = ''
  }
}

const removeVariable = (item) => {
  Modal.confirm({
    title: `删除变量「${item.name}」`,
    content: '删除后不可恢复。',
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      try {
        await variableApi.deleteVariable(item.id)
        message.success('变量已删除')
        await loadVariables()
      } catch (error) {
        message.error(error.message || '删除变量失败')
        return Promise.reject(error)
      }
    }
  })
}

onMounted(loadVariables)
</script>

<template>
  <div class="variable-config-view">
    <PageHeader title="服务类型配置" :show-border="true" />

    <div class="variable-config-content">
      <div class="variable-toolbar">
        <a-input
          v-model:value="keywordInput"
          class="search-input"
          placeholder="输入搜索关键词"
          allow-clear
          @pressEnter="handleSearch"
          @clear="handleSearch"
        >
          <template #suffix>
            <button type="button" class="search-btn" aria-label="查询" @click="handleSearch">
              <Search :size="16" />
            </button>
          </template>
        </a-input>
        <a-button type="primary" class="lucide-icon-btn" @click="openCreate">新增</a-button>
      </div>

      <a-table
        class="variable-table"
        :data-source="variables"
        :loading="loading"
        :pagination="false"
        row-key="id"
      >
        <a-table-column title="序号" key="index" :width="72">
          <template #default="{ index }">{{ index + 1 }}</template>
        </a-table-column>
        <a-table-column title="编码" data-index="variable_code" key="variable_code" />
        <a-table-column title="变量" data-index="name" key="name" />
        <a-table-column title="服务入口" data-index="service_entry" key="service_entry" />
        <a-table-column title="状态" key="enabled" :width="140">
          <template #default="{ record }">
            <div class="status-cell">
              <a-switch
                size="small"
                :checked="record.enabled"
                :loading="togglingId === record.id"
                @change="(checked) => toggleEnabled(record, checked)"
              />
              <span :class="record.enabled ? 'status-on' : 'status-off'">
                {{ record.enabled ? '启用' : '禁用' }}
              </span>
            </div>
          </template>
        </a-table-column>
        <a-table-column title="创建时间" key="created_at" :width="180">
          <template #default="{ record }">{{ formatCreatedAt(record.created_at) }}</template>
        </a-table-column>
        <a-table-column title="操作" key="actions" :width="180">
          <template #default="{ record }">
            <div class="row-actions">
              <a-button type="primary" size="small" @click="openEdit(record)">编辑</a-button>
              <a-button type="primary" size="small" @click="removeVariable(record)">删除</a-button>
            </div>
          </template>
        </a-table-column>
      </a-table>
    </div>

    <a-modal
      v-model:open="modalOpen"
      :title="modalTitle"
      :mask-closable="false"
      :footer="null"
      width="480px"
      @cancel="closeModal"
    >
      <a-form
        class="variable-form"
        :model="form"
        :label-col="{ style: { width: '92px' } }"
        :wrapper-col="{ style: { flex: 1 } }"
      >
        <a-form-item label="变量" required>
          <a-input v-model:value="form.name" placeholder="请输入变量名称" allow-clear />
        </a-form-item>
        <a-form-item label="服务入口" required>
          <a-select
            v-model:value="form.service_entry"
            placeholder="请选择服务入口"
            allow-clear
            :options="SERVICE_ENTRIES.map((name) => ({ value: name, label: name }))"
          />
        </a-form-item>
        <a-form-item label="状态" required>
          <a-radio-group v-model:value="form.enabled" class="status-radios">
            <a-radio :value="true">启用</a-radio>
            <a-radio :value="false">禁用</a-radio>
          </a-radio-group>
        </a-form-item>
      </a-form>
      <div class="variable-form-footer">
        <a-button type="primary" @click="closeModal">取消</a-button>
        <a-button type="primary" :loading="saving" @click="saveVariable">确定</a-button>
      </div>
    </a-modal>
  </div>
</template>

<style scoped lang="less">
.variable-config-view {
  display: flex;
  flex-direction: column;
  min-height: 100%;
  background: var(--gray-0);
  color: var(--gray-1000);
}

.variable-config-content {
  padding: 16px var(--page-padding) 32px;
}

.variable-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 16px;

  .search-input {
    width: 280px;
  }

  .search-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    border: none;
    background: transparent;
    color: var(--gray-500);
    cursor: pointer;
  }
}

.variable-table {
  :deep(.ant-table) {
    background: var(--gray-0);
  }

  :deep(.ant-table-thead > tr > th) {
    background: var(--gray-10);
    color: var(--gray-700);
    font-weight: 600;
  }
}

.status-cell {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.status-on {
  color: var(--color-success-700);
}

.status-off {
  color: var(--gray-500);
}

.row-actions {
  display: inline-flex;
  gap: 8px;
}

.variable-form {
  padding: 8px 12px 0;

  :deep(.ant-form-item) {
    margin-bottom: 18px;
  }

  :deep(.ant-form-item-label > label) {
    color: var(--color-text);
  }

  :deep(.ant-form-item-label > label.ant-form-item-required:not(.ant-form-item-required-mark-optional)::before) {
    margin-inline-end: 4px;
    color: var(--color-error-500);
  }

  :deep(.ant-input-affix-wrapper),
  :deep(.ant-input),
  :deep(.ant-select-selector) {
    border-radius: 20px;
  }

  .status-radios {
    display: flex;
    align-items: center;
    gap: 48px;
  }
}

.variable-form-footer {
  display: flex;
  justify-content: center;
  gap: 16px;
  padding: 8px 0 4px;

  :deep(.ant-btn) {
    min-width: 88px;
    height: 36px;
    border-radius: 8px;
  }
}
</style>
