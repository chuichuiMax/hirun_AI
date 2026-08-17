<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { Download, ImagePlus, RefreshCw, Sparkles, WandSparkles, X } from 'lucide-vue-next'
import { contentApi } from '@/apis/content_api'
import { useCoverGenerationStore } from '@/stores/coverGeneration'

const route = useRoute()
const router = useRouter()
const store = useCoverGenerationStore()
const tab = ref('compose')
const sourceAssets = ref([])
const templateAsset = ref(null)
const maskAsset = ref(null)
const previewUrls = new Map()
const form = reactive({
  contentTaskId: '',
  templateId: 'grid_3x3',
  themeId: 'editorial_ink',
  size: '1080x1440',
  title: '',
  prompt: '',
  negativePrompt: '',
  gap: 18,
  margin: 24,
  fit: 'cover',
  count: 1
})

const templates = computed(() => store.bootstrap?.templates || [])
const themes = computed(() => store.bootstrap?.themes || [])
const sizes = computed(() => store.bootstrap?.sizes || [])
const tasks = computed(() => store.bootstrap?.content_tasks || [])
const activeTemplate = computed(() => templates.value.find((item) => item.id === form.templateId))
const canCancel = computed(() => store.isRunning && !['saving', 'cancel_requested'].includes(store.currentJob?.status))
const canSubmit = computed(() => {
  if (store.isRunning || store.loading.upload || store.loading.submit) return false
  if (tab.value === 'compose') {
    const count = sourceAssets.value.length
    return count >= (activeTemplate.value?.min_assets || 2) && count <= (activeTemplate.value?.max_assets || 9)
  }
  if (!store.bootstrap?.image2?.configured) return false
  if (sourceAssets.value.length > 9) return false
  if (tab.value === 'template') return Boolean(templateAsset.value && sourceAssets.value.length)
  if (maskAsset.value) return sourceAssets.value.length === 1 && Boolean(form.prompt.trim() || form.contentTaskId)
  return Boolean(form.prompt.trim() || form.contentTaskId)
})

const statusText = computed(() => {
  const map = {
    queued: '等待执行',
    running: '处理中',
    submitting: '正在提交 image2',
    polling: 'image2 正在生成',
    downloading: '正在获取结果',
    saving: '正在保存',
    cancel_requested: '正在取消',
    succeeded: '生成完成',
    failed: '生成失败',
    cancelled: '已取消'
  }
  return map[store.currentJob?.status] || store.currentJob?.status || ''
})

const trackPreview = (asset, file) => {
  const url = URL.createObjectURL(file)
  previewUrls.set(asset.id, url)
  return { ...asset, previewUrl: url }
}

async function uploadSource(event) {
  const files = Array.from(event.target.files || [])
  event.target.value = ''
  if (!files.length) return
  try {
    const uploaded = await store.upload(files, 'source', form.contentTaskId || null)
    sourceAssets.value.push(...uploaded.map((asset, index) => trackPreview(asset, files[index])))
  } catch (error) {
    message.error(error.message || '原图上传失败')
  }
}

async function uploadSingle(event, role) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  try {
    const [asset] = await store.upload([file], role, form.contentTaskId || null)
    const item = trackPreview(asset, file)
    if (role === 'template') {
      if (templateAsset.value) await removeAsset(templateAsset.value, 'template')
      templateAsset.value = item
    } else {
      if (maskAsset.value) await removeAsset(maskAsset.value, 'mask')
      maskAsset.value = item
    }
  } catch (error) {
    message.error(error.message || '图片上传失败')
  }
}

async function removeAsset(asset, role = 'source') {
  if (!asset || store.isRunning) return
  try {
    await store.deleteAsset(asset.id)
  } catch (error) {
    message.error(error.message || '素材删除失败')
    return
  }
  const url = previewUrls.get(asset.id)
  if (url) URL.revokeObjectURL(url)
  previewUrls.delete(asset.id)
  if (role === 'source') sourceAssets.value = sourceAssets.value.filter((item) => item.id !== asset.id)
  else if (role === 'template') templateAsset.value = null
  else maskAsset.value = null
}

function buildGeneratePayload() {
  let mode = 'text_to_image'
  if (tab.value === 'ai' && maskAsset.value) mode = 'mask'
  else if (tab.value === 'template' || sourceAssets.value.length > 1) mode = 'multi_reference'
  else if (sourceAssets.value.length === 1) mode = 'image_to_image'
  return {
    mode,
    content_task_id: form.contentTaskId || null,
    source_asset_ids: sourceAssets.value.map((item) => item.id),
    template_asset_id: tab.value === 'template' ? templateAsset.value?.id : null,
    mask_asset_id: mode === 'mask' ? maskAsset.value?.id : null,
    prompt: form.prompt,
    negative_prompt: form.negativePrompt || null,
    size: form.size,
    n: form.count,
    parameters: {}
  }
}

async function submit() {
  if (!canSubmit.value) return
  try {
    const payload = tab.value === 'compose'
      ? {
          asset_ids: sourceAssets.value.map((item) => item.id),
          template_id: form.templateId,
          theme_id: form.themeId,
          size: form.size,
          content_task_id: form.contentTaskId || null,
          layout: { title: form.title, gap: form.gap, margin: form.margin, fit: form.fit }
        }
      : buildGeneratePayload()
    const job = await store.submit(tab.value === 'compose' ? 'compose' : 'generate', payload)
    await router.replace({ query: { ...route.query, job: job.id } })
    message.success('封面任务已提交')
  } catch (error) {
    message.error(error.message || '任务提交失败')
  }
}

async function selectHistory(job) {
  try {
    await store.restore(job.id)
    await router.replace({ query: { ...route.query, job: job.id } })
  } catch (error) {
    message.error(error.message || '任务读取失败')
  }
}

async function retryJob(job) {
  try {
    const created = await store.retry(job)
    await router.replace({ query: { ...route.query, job: created.id } })
  } catch (error) {
    message.error(error.message || '重试失败')
  }
}

async function setCurrent(assetId) {
  try {
    await store.setCurrent(assetId)
    message.success('已设为内容资产当前封面')
  } catch (error) {
    message.error(error.message || '设置当前封面失败')
  }
}

function downloadResult(item, index) {
  const link = document.createElement('a')
  link.href = item.url
  link.download = `小红书封面-${index + 1}.png`
  link.click()
}

async function changeContentTask() {
  try {
    const query = { ...route.query }
    if (form.contentTaskId) query.task = form.contentTaskId
    else delete query.task
    delete query.job
    await router.replace({ query })
    store.clearCurrent()
    await store.loadHistory(form.contentTaskId || null)
  } catch (error) {
    message.error(error.message || '封面任务历史加载失败')
  }
}

async function ensureContentTask(taskId) {
  if (!taskId || tasks.value.some((item) => item.id === taskId)) return Boolean(taskId)
  try {
    const response = await contentApi.getTask(taskId)
    if (!response.task) return false
    store.bootstrap.content_tasks.unshift({
      id: response.task.id,
      name: response.task.name,
      status: response.task.status,
      updated_at: response.task.updated_at
    })
    return true
  } catch (error) {
    message.warning(error.message || '关联内容任务不存在或无权访问')
    return false
  }
}

watch(() => form.templateId, () => {
  const maximum = activeTemplate.value?.max_assets || 9
  if (sourceAssets.value.length > maximum) message.warning(`该版式最多使用 ${maximum} 张图片，请移除多余素材`)
})

onMounted(async () => {
  try {
    await store.loadBootstrap()
    if (typeof route.query.task === 'string') {
      if (await ensureContentTask(route.query.task)) form.contentTaskId = route.query.task
    }
    const jobId = typeof route.query.job === 'string' ? route.query.job : ''
    if (jobId) {
      const restored = await store.restore(jobId)
      if (
        !form.contentTaskId
        && restored.content_task_id
        && await ensureContentTask(restored.content_task_id)
      ) {
        form.contentTaskId = restored.content_task_id
      }
    }
    await store.loadHistory(form.contentTaskId || null)
  } catch (error) {
    message.error(error.message || '封面工作台加载失败')
  }
})

onBeforeUnmount(() => {
  previewUrls.forEach((url) => URL.revokeObjectURL(url))
  store.dispose()
})
</script>

<template>
  <main class="cover-page">
    <header class="page-head">
      <div>
        <p class="eyebrow">CONTENT COVER STUDIO</p>
        <h1>封面生成</h1>
        <p>将多张素材排成稳定版式，或使用 image2 根据内容资产生成小红书封面。</p>
      </div>
      <span class="image2-state" :class="{ ready: store.bootstrap?.image2?.configured }">
        image2 {{ store.bootstrap?.image2?.configured ? '已配置' : '未配置' }}
      </span>
    </header>

    <div class="workspace-grid">
      <section class="editor-panel">
        <div class="mode-tabs" role="tablist" aria-label="封面生成方式">
          <button :class="{ active: tab === 'compose' }" @click="tab = 'compose'">智能排版</button>
          <button :class="{ active: tab === 'ai' }" @click="tab = 'ai'">AI 封面</button>
          <button :class="{ active: tab === 'template' }" @click="tab = 'template'">模板复刻</button>
        </div>

        <div class="form-grid">
          <label>
            <span>关联内容资产</span>
            <select v-model="form.contentTaskId" :disabled="store.isRunning" @change="changeContentTask">
              <option value="">不关联内容任务</option>
              <option v-for="task in tasks" :key="task.id" :value="task.id">{{ task.name }}</option>
            </select>
          </label>
          <label>
            <span>输出尺寸</span>
            <select v-model="form.size">
              <option v-for="size in sizes" :key="size.id" :value="size.id">{{ size.label }} · {{ size.id }}</option>
            </select>
          </label>
        </div>

        <div v-if="tab === 'compose'" class="section-block">
          <div class="section-title"><span>选择版式</span><small>版式配置由后端声明，后续可直接扩展</small></div>
          <div class="template-grid">
            <button
              v-for="item in templates"
              :key="item.id"
              class="template-card"
              :class="{ active: form.templateId === item.id }"
              @click="form.templateId = item.id"
            >
              <span class="layout-glyph" :data-layout="item.id"><i /><i /><i /><i /></span>
              <strong>{{ item.name }}</strong>
              <small>{{ item.min_assets }}–{{ item.max_assets }} 张</small>
            </button>
          </div>
          <div class="form-grid compact">
            <label><span>主题</span><select v-model="form.themeId"><option v-for="theme in themes" :key="theme.id" :value="theme.id">{{ theme.name }}</option></select></label>
            <label><span>裁切</span><select v-model="form.fit"><option value="cover">填满画面</option><option value="contain">完整显示</option></select></label>
            <label><span>间距 {{ form.gap }}px</span><input v-model.number="form.gap" type="range" min="0" max="80" /></label>
            <label><span>边距 {{ form.margin }}px</span><input v-model.number="form.margin" type="range" min="0" max="120" /></label>
          </div>
          <label class="wide-field"><span>可选标题</span><input v-model="form.title" maxlength="60" placeholder="排版封面上的简短标题" /></label>
          <div class="compose-preview">
            <div
              class="preview-stage"
              :data-layout="form.templateId"
              :style="{ '--preview-gap': `${Math.max(2, form.gap / 4)}px` }"
            >
              <img v-for="asset in sourceAssets" :key="asset.id" :src="asset.previewUrl" :alt="asset.localName" />
              <span v-if="!sourceAssets.length">上传图片后在这里预览版式</span>
              <strong v-if="form.title">{{ form.title }}</strong>
            </div>
            <small>版式预览仅用于确认图片顺序，最终导出由后端按 1080 像素画板渲染。</small>
          </div>
        </div>

        <div v-else class="section-block ai-fields">
          <div v-if="tab === 'template'" class="upload-group">
            <div class="section-title"><span>模板图</span><small>image2 将参考模板的构图和视觉语言</small></div>
            <label v-if="!templateAsset" class="upload-box compact-upload">
              <ImagePlus :size="22" /><span>上传一张模板图</span><input type="file" accept="image/*" :disabled="store.isRunning" @change="uploadSingle($event, 'template')" />
            </label>
            <div v-else class="single-preview"><img :src="templateAsset.previewUrl" alt="模板图" /><button :disabled="store.isRunning" aria-label="移除模板图" @click="removeAsset(templateAsset, 'template')"><X :size="16" /></button></div>
          </div>
          <label class="wide-field"><span>生成要求</span><textarea v-model="form.prompt" rows="5" maxlength="8000" placeholder="例如：轻复古生活方式封面，主体清晰，留出呼吸感；关联内容任务后会自动拼入标题、正文摘要与话题。" /></label>
          <label class="wide-field"><span>不希望出现</span><input v-model="form.negativePrompt" maxlength="4000" placeholder="例如：低清晰度、复杂水印、变形人物" /></label>
          <div class="form-grid compact">
            <label><span>生成数量</span><select v-model.number="form.count"><option :value="1">1 张</option><option :value="2">2 张</option><option :value="4">4 张</option></select></label>
            <label v-if="tab === 'ai'" class="mask-field"><span>可选蒙版</span><input type="file" accept="image/*" :disabled="store.isRunning" @change="uploadSingle($event, 'mask')" /><small v-if="maskAsset">已上传 {{ maskAsset.localName }}；尺寸需与单张原图一致</small></label>
          </div>
        </div>

        <div class="section-block">
          <div class="section-title">
            <span>{{ tab === 'template' ? '待优化原图' : '图片素材' }}</span>
            <small v-if="tab === 'compose'">当前 {{ sourceAssets.length }} 张 · {{ activeTemplate?.name }}需要 {{ activeTemplate?.min_assets }}–{{ activeTemplate?.max_assets }} 张</small>
            <small v-else>支持单图图生图与多图参考 · 当前 {{ sourceAssets.length }}/9 张</small>
          </div>
          <div class="asset-grid">
            <div v-for="asset in sourceAssets" :key="asset.id" class="asset-card">
              <img :src="asset.previewUrl" :alt="asset.localName" />
              <button :disabled="store.isRunning" aria-label="移除图片" @click="removeAsset(asset)"><X :size="15" /></button>
            </div>
            <label class="upload-box">
              <ImagePlus :size="24" /><strong>上传图片</strong><span>PNG / JPG / WebP，单张不超过 20 MB</span>
              <input type="file" accept="image/*" multiple :disabled="store.isRunning" @change="uploadSource" />
            </label>
          </div>
        </div>

        <div class="submit-row">
          <p v-if="tab !== 'compose' && !store.bootstrap?.image2?.configured">需先在服务环境配置 IMAGE2_BASE_URL、IMAGE2_API_KEY 和 IMAGE2_MODEL。</p>
          <button class="primary-button" :disabled="!canSubmit" @click="submit">
            <WandSparkles :size="18" />{{ store.loading.submit ? '正在提交…' : '开始生成' }}
          </button>
        </div>
      </section>

      <aside class="result-panel">
        <div class="result-head"><div><span>生成结果</span><small v-if="store.currentJob">{{ statusText }}</small></div><button v-if="canCancel" class="text-button" @click="store.cancel">取消任务</button></div>
        <div v-if="store.currentJob && store.isRunning" class="progress-card">
          <Sparkles :size="28" /><strong>{{ statusText }}</strong><span>{{ store.currentJob.progress || 0 }}%</span>
          <div class="progress-track"><i :style="{ width: `${store.currentJob.progress || 0}%` }" /></div>
        </div>
        <div v-else-if="store.resultUrls.length" class="result-list">
          <article v-for="(item, index) in store.resultUrls" :key="item.id">
            <img :src="item.url" :alt="`封面结果 ${index + 1}`" />
            <div class="result-actions">
              <button @click="downloadResult(item, index)"><Download :size="16" />下载 PNG</button>
              <button v-if="store.currentJob?.artifact_id || store.currentJob?.content_task_id" @click="setCurrent(item.id)">设为当前封面</button>
            </div>
          </article>
        </div>
        <div v-else-if="store.currentJob?.status === 'failed'" class="empty-result error-state">
          <strong>{{ store.currentJob.error_message || '生成失败' }}</strong>
          <button class="secondary-button" @click="retryJob(store.currentJob)"><RefreshCw :size="16" />重新生成</button>
        </div>
        <div v-else class="empty-result"><ImagePlus :size="36" /><strong>结果会显示在这里</strong><span>先上传素材，再选择排版或 AI 生成方式。</span></div>

        <div class="history">
          <div class="result-head"><span>最近任务</span><button class="text-button" @click="store.loadHistory(form.contentTaskId || null)">刷新</button></div>
          <button v-for="job in store.jobs" :key="job.id" class="history-row" @click="selectHistory(job)">
            <span><strong>{{ job.mode === 'compose' ? '智能排版' : 'AI 生成' }}</strong><small>{{ new Date(job.created_at).toLocaleString() }}</small></span>
            <em :data-status="job.status">{{ job.status }}</em>
          </button>
          <p v-if="!store.jobs.length" class="history-empty">还没有封面任务</p>
        </div>
      </aside>
    </div>
  </main>
</template>

<style scoped lang="less">
.cover-page { min-height: 100%; padding: 32px; color: var(--gray-1000); background: var(--main-20); }
.page-head { max-width: 1500px; margin: 0 auto 24px; display: flex; justify-content: space-between; gap: 24px; align-items: flex-start; }
.eyebrow { margin: 0 0 6px; color: var(--main-700); font-size: 11px; font-weight: 700; letter-spacing: .16em; }
h1 { margin: 0; font-size: 30px; letter-spacing: -.04em; } .page-head p:last-child { margin: 8px 0 0; color: var(--gray-600); }
.image2-state { border: 1px solid var(--color-warning-100); border-radius: 999px; padding: 7px 12px; color: var(--color-warning-700); background: var(--color-warning-10); font-size: 12px; }
.image2-state.ready { color: var(--color-success-700); border-color: var(--color-success-100); background: var(--color-success-10); }
.workspace-grid { max-width: 1500px; margin: auto; display: grid; grid-template-columns: minmax(0, 1fr) 390px; gap: 20px; align-items: start; }
.editor-panel, .result-panel { border: 1px solid var(--gray-200); border-radius: 18px; background: var(--main-0); box-shadow: 0 10px 34px rgba(1, 21, 31, .06); }
.editor-panel { padding: 22px; } .result-panel { padding: 20px; position: sticky; top: 20px; }
.mode-tabs { display: grid; grid-template-columns: repeat(3, 1fr); padding: 4px; border-radius: 12px; background: var(--gray-100); }
.mode-tabs button { border: 0; border-radius: 9px; padding: 10px; color: var(--gray-600); background: transparent; cursor: pointer; }
.mode-tabs button.active { color: var(--main-900); background: white; box-shadow: 0 2px 8px rgba(0, 0, 0, .08); font-weight: 600; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 20px; } .form-grid.compact { margin-top: 16px; }
label { display: grid; gap: 7px; font-size: 13px; color: var(--gray-700); } input, select, textarea { width: 100%; box-sizing: border-box; border: 1px solid var(--gray-300); border-radius: 9px; padding: 10px 11px; color: var(--gray-1000); background: white; outline: none; } textarea { resize: vertical; line-height: 1.6; }
input:focus, select:focus, textarea:focus { border-color: var(--main-500); box-shadow: 0 0 0 3px var(--main-50); }
.section-block { margin-top: 24px; padding-top: 22px; border-top: 1px solid var(--gray-150); } .section-title, .result-head { display: flex; justify-content: space-between; gap: 16px; align-items: center; }
.section-title > span, .result-head > span, .result-head > div > span { font-weight: 700; } small { color: var(--gray-500); font-style: normal; }
.template-grid { display: grid; grid-template-columns: repeat(6, minmax(88px, 1fr)); gap: 10px; margin-top: 13px; }
.template-card { padding: 11px; border: 1px solid var(--gray-200); border-radius: 11px; background: white; display: grid; gap: 5px; justify-items: start; cursor: pointer; }
.template-card.active { border-color: var(--main-600); background: var(--main-30); box-shadow: 0 0 0 2px var(--main-100); }
.layout-glyph { width: 100%; aspect-ratio: 4/3; display: grid; grid-template-columns: 1fr 1fr; gap: 3px; } .layout-glyph i { background: var(--main-200); border-radius: 2px; }
.layout-glyph[data-layout='split_horizontal'] { grid-template-columns: 1fr; }.layout-glyph[data-layout='grid_3x3'] { grid-template-columns: repeat(3, 1fr); }
.wide-field { margin-top: 15px; }.asset-grid { margin-top: 13px; display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 12px; }
.asset-card, .single-preview { position: relative; overflow: hidden; border-radius: 11px; background: var(--gray-100); }.asset-card { aspect-ratio: 1; }.asset-card img, .single-preview img { width: 100%; height: 100%; display: block; object-fit: cover; }
.asset-card button, .single-preview button { position: absolute; top: 7px; right: 7px; width: 27px; height: 27px; border: 0; border-radius: 50%; display: grid; place-items: center; color: white; background: rgba(0,0,0,.65); cursor: pointer; }
.upload-box { min-height: 130px; border: 1px dashed var(--main-300); border-radius: 11px; display: grid; place-content: center; justify-items: center; gap: 7px; text-align: center; color: var(--main-700); background: var(--main-30); cursor: pointer; }.upload-box span { color: var(--gray-500); font-size: 11px; }.upload-box input { display: none; }
.compact-upload { min-height: 86px; margin-top: 12px; }.single-preview { width: 150px; height: 100px; margin-top: 12px; }.mask-field input { padding: 7px; }.mask-field small { display: block; }
.compose-preview { display: grid; justify-items: center; gap: 8px; margin-top: 18px; padding: 16px; border: 1px solid var(--gray-150); border-radius: 12px; background: var(--main-20); }
.compose-preview > small { color: var(--gray-500); text-align: center; }
.preview-stage { --preview-gap: 5px; position: relative; display: grid; width: min(100%, 270px); aspect-ratio: 3 / 4; gap: var(--preview-gap); overflow: hidden; border-radius: 10px; padding: 7px; background: var(--main-0); box-shadow: 0 5px 18px rgba(1, 21, 31, .1); }
.preview-stage img { width: 100%; height: 100%; min-width: 0; min-height: 0; object-fit: cover; overflow: hidden; border-radius: 4px; }
.preview-stage > span { place-self: center; align-self: center; color: var(--gray-500); font-size: 12px; text-align: center; }
.preview-stage > strong { position: absolute; z-index: 3; left: 14px; top: 14px; max-width: calc(100% - 28px); padding: 5px 8px; overflow: hidden; border-radius: 5px; color: var(--gray-1000); background: rgba(255, 255, 255, .9); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.preview-stage[data-layout='grid_3x3'] { grid-template-columns: repeat(3, 1fr); grid-template-rows: repeat(3, 1fr); }
.preview-stage[data-layout='split_vertical'], .preview-stage[data-layout='before_after'] { grid-template-columns: repeat(2, 1fr); }
.preview-stage[data-layout='split_horizontal'] { grid-template-rows: repeat(2, 1fr); }
.preview-stage[data-layout='card_stack'] { display: block; background: var(--gray-1000); }
.preview-stage[data-layout='card_stack'] img:first-of-type { position: absolute; inset: 7px; width: calc(100% - 14px); height: calc(100% - 14px); opacity: .72; }
.preview-stage[data-layout='card_stack'] img:not(:first-of-type) { position: relative; z-index: 2; width: 70%; height: 25%; margin: 7px 0 0 27%; border: 2px solid var(--main-0); }
.preview-stage[data-layout='hero_thumbs'] { grid-template-columns: repeat(4, 1fr); grid-template-rows: 3fr 1fr; }
.preview-stage[data-layout='hero_thumbs'] img:first-of-type { grid-column: 1 / -1; }
.submit-row { margin-top: 24px; display: flex; justify-content: flex-end; gap: 16px; align-items: center; }.submit-row p { margin: 0 auto 0 0; color: var(--color-warning-700); font-size: 12px; }
.primary-button, .secondary-button, .result-list article button { border: 0; border-radius: 10px; display: inline-flex; gap: 7px; align-items: center; justify-content: center; cursor: pointer; }
.primary-button { padding: 11px 20px; color: white; background: var(--main-700); font-weight: 650; }.primary-button:disabled { opacity: .4; cursor: not-allowed; }.secondary-button { padding: 9px 13px; color: var(--main-800); background: var(--main-50); }
.result-head small { display: block; margin-top: 2px; }.text-button { border: 0; padding: 4px; color: var(--main-700); background: transparent; cursor: pointer; }
.progress-card, .empty-result { min-height: 250px; margin-top: 16px; border-radius: 13px; display: grid; place-content: center; justify-items: center; gap: 10px; color: var(--gray-500); background: var(--gray-50); text-align: center; }.progress-card strong, .empty-result strong { color: var(--gray-800); }
.progress-track { width: 220px; height: 7px; overflow: hidden; border-radius: 999px; background: var(--gray-200); }.progress-track i { display: block; height: 100%; border-radius: inherit; background: var(--main-600); transition: width .3s; }
.result-list { display: grid; gap: 13px; margin-top: 16px; }.result-list article { position: relative; overflow: hidden; border-radius: 13px; background: var(--gray-100); }.result-list img { width: 100%; max-height: 520px; object-fit: contain; display: block; }.result-actions { position: absolute; right: 10px; bottom: 10px; display: flex; gap: 7px; }.result-list article button { padding: 8px 11px; background: rgba(255,255,255,.92); color: var(--main-900); }
.error-state strong { color: var(--color-error-700); }.history { margin-top: 25px; padding-top: 20px; border-top: 1px solid var(--gray-150); }.history-row { width: 100%; padding: 11px 0; border: 0; border-bottom: 1px solid var(--gray-100); display: flex; justify-content: space-between; align-items: center; text-align: left; background: transparent; cursor: pointer; }.history-row span { display: grid; gap: 3px; }.history-row em { color: var(--gray-500); font-size: 11px; font-style: normal; }.history-row em[data-status='succeeded'] { color: var(--color-success-700); }.history-row em[data-status='failed'] { color: var(--color-error-700); }.history-empty { color: var(--gray-500); font-size: 12px; }
@media (max-width: 1100px) { .workspace-grid { grid-template-columns: 1fr; }.result-panel { position: static; }.template-grid { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 680px) { .cover-page { padding: 18px; }.page-head { display: grid; }.form-grid, .asset-grid { grid-template-columns: 1fr 1fr; }.template-grid { grid-template-columns: repeat(2, 1fr); } }
</style>
