<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  BookOpenCheck,
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  Clock3,
  FileClock,
  Folder,
  FolderOpen,
  History,
  Image,
  LayoutTemplate,
  LoaderCircle,
  Play,
  RefreshCw,
  Save,
  ScanText,
  Send,
  Settings2,
  ShieldCheck,
  Sparkles,
  UserRoundCog
} from 'lucide-vue-next'
import ContentStageStepper from '@/components/content/ContentStageStepper.vue'
import ContentOcrDrawer from '@/components/content/ContentOcrDrawer.vue'
import ContentExecutionPreview from '@/components/content/ContentExecutionPreview.vue'
import { contentApi } from '@/apis/content_api'
import { materialLibraryApi } from '@/apis/material_library_api'
import { useContentStudioStore } from '@/stores/contentStudio'
import { useUserStore } from '@/stores/user'
import { formatEvidenceReference } from '@/utils/contentEvidencePresentation'
import {
  buildContentRuntimeTimeline,
  buildContentWorkflowGroups
} from '@/utils/contentWorkflowPresentation'

const route = useRoute()
const router = useRouter()
const store = useContentStudioStore()
const userStore = useUserStore()

const stage = ref(1)
const creation = reactive({
  industry_template_id: '',
  mode: window.matchMedia('(max-width: 800px)').matches ? 'quick' : 'quick',
  content_goal: '',
  name: ''
})
const formValues = reactive({})
const selectedAngleId = ref('')
const selectedTitleId = ref('')
const selectedTitleFormulaCode = ref('')
const selectedBodyFormulaCode = ref('')
const selectedCoverAssetId = ref('')
const confirmedEvidenceIds = ref([])
const approvalNote = ref('')
const modelSpec = ref('')
const editor = reactive({ title: '', body: '', topics: [] })
const versionDrawerOpen = ref(false)
const ocrModalOpen = ref(false)
const coverUrl = ref('')
const coverLoading = ref(false)
const coverCandidateUrls = ref({})
const coverCandidatesLoading = ref(false)
const materialGalleries = ref([])
const activeGalleryId = ref('')
const galleryImages = ref([])
const galleryModalOpen = ref(false)
const pendingImageItemId = ref('')
const posterTemplates = ref([])
const selectedImageItemId = ref('')
const selectedImageGalleryId = ref('')
const selectedImageSummary = ref(null)
const selectedPosterTemplateId = ref('')
const materialImageUrls = ref({})
const posterTemplateUrls = ref({})
const materialSelectorLoading = ref(false)
const galleryImagesLoading = ref(false)
const posterTemplatesRefreshing = ref(false)
const runtimeTimelineElement = ref(null)
const posterTemplateSyncIntervalMs = 10_000
let draftSaveTimer = null
let posterTemplateSyncTimer = null
let coverLoadGeneration = 0
let coverCandidateLoadGeneration = 0
let materialPreviewGeneration = 0
let posterPreviewGeneration = 0
let posterTemplateSignature = ''

const testFormDefaults = {
  decoration: {
    brand_name: '杭州栖居空间设计',
    audience: ['杭州准备改善型装修的三口之家'],
    pain: ['89㎡空间收纳不足', '厨房动线拥挤', '担心预算失控'],
    advantage: ['设计施工一体化', '节点验收留档', '主材报价透明'],
    project_type: '三室两厅一卫',
    area: '89㎡',
    budget: '硬装预算18万元',
    duration: '预计工期90天',
    craft_and_materials:
      '全屋定制柜采用ENF级板材，水电管线分色布置，防水完成后进行48小时闭水试验，各节点验收后留存影像记录。',
    owner_pain:
      '入户和餐厅缺少集中收纳，厨房操作台不足，儿童房需要同时满足学习与储物。',
    project_result:
      '现场复尺后通过玄关柜、餐边柜和儿童房组合柜增加12㎡收纳空间，厨房动线调整为洗、切、炒顺序。'
  }
}

const taskId = computed(() => route.params.taskId)
const selectedTemplate = computed(() =>
  store.templates.find((item) => item.id === creation.industry_template_id)
)
const activeFields = computed(() => {
  if (!store.task) {
    if (!selectedTemplate.value) return []
    return creation.mode === 'quick'
      ? selectedTemplate.value.quick_form_schema
      : selectedTemplate.value.pro_form_schema
  }
  return store.task.mode === 'quick'
    ? store.template?.quick_form_schema || []
    : store.template?.pro_form_schema || []
})
const isQuickMode = computed(() => (store.task ? store.task.mode : creation.mode) === 'quick')
const titleOptions = computed(
  () => store.interrupt?.options || store.task?.title_candidates || []
)
const evidenceFieldLabels = computed(() =>
  Object.fromEntries(
    [...(store.template?.quick_form_schema || []), ...(store.template?.pro_form_schema || [])]
      .filter((field) => field.key && field.label)
      .map((field) => [field.key, field.label])
  )
)
const evidenceItemsById = computed(
  () =>
    new Map(
      [...(store.evidence?.items || []), ...(store.interrupt?.evidence_items || [])]
        .filter((item) => item?.id)
        .map((item) => [item.id, item])
    )
)
const evidenceReferenceText = (evidenceId, index = 0) =>
  formatEvidenceReference(
    evidenceItemsById.value.get(evidenceId),
    evidenceFieldLabels.value,
    index
  )
const angleOptions = computed(() =>
  store.interrupt?.interrupt_type === 'content_direction' ? store.interrupt.options || [] : []
)
const workflowGroups = computed(() => buildContentWorkflowGroups(store.runEvents))
const runtimeTimeline = computed(() =>
  buildContentRuntimeTimeline(store.runEvents, store.runAudit?.events || [])
)
const formatRuntimeTime = (value) => {
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? ''
    : date.toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
const formatRuntimeDuration = (durationMs) => {
  if (durationMs === undefined || durationMs === null) return ''
  return durationMs < 1000 ? `${durationMs}ms` : `${(durationMs / 1000).toFixed(1)}s`
}
const reviewChecks = computed(() => store.artifact?.review_snapshot?.checks || store.task?.review?.checks || [])
const canFinalize = computed(() => ['passed', 'warning'].includes(store.artifact?.review_snapshot?.status))
const approvalAllowed = computed(() => {
  if (store.interrupt?.interrupt_type !== 'content_approval') return false
  return (
    store.interrupt.approval_allowed === true &&
    ['passed', 'warning'].includes(store.interrupt.validation_report?.status) &&
    ['passed', 'warning'].includes(store.interrupt.review_report?.status)
  )
})
const correctionChecks = computed(() => [
  ...(store.interrupt?.title_validation_report?.items || []).flatMap((item) => item.checks || []),
  ...(store.interrupt?.validation_report?.checks || []),
  ...(store.interrupt?.review_report?.checks || [])
].filter((item) => item.status === 'blocked' || item.level === 'error'))
const latestTitleValidationReport = computed(() => {
  const nodes = [...(store.runAudit?.nodes || [])].reverse()
  return nodes.find((item) => item.node_id === 'validate_title_candidates')
    ?.output_snapshot?.title_validation_report || null
})
const blockedTitleCandidates = computed(() =>
  (latestTitleValidationReport.value?.items || []).filter((item) => item.status === 'blocked')
)
const runFailed = computed(() =>
  ['failed', 'cancelled'].includes(store.currentRun?.status) || store.task?.status === 'failed'
)
const externalWaitProgress = computed(() =>
  Math.min(100, Math.max(0, Number(store.interrupt?.progress || 0)))
)
const externalWaitStatusLabel = computed(() => {
  const labels = {
    queued: '封面任务已进入队列',
    running: '封面服务正在生成图片',
    submitting: '正在提交封面生成请求',
    polling: '正在等待封面生成结果',
    downloading: '正在下载封面结果',
    saving: '正在保存封面资产',
    succeeded: '封面生成完成，正在自动继续工作流',
    failed: '封面生成失败，正在同步失败结果',
    cancelled: '封面任务已取消，正在同步任务状态'
  }
  return labels[store.interrupt?.status] || '正在等待封面服务'
})
const failedNodeId = computed(
  () => [...store.runEvents].reverse().find((item) => item.status === 'failed')?.node_id || null
)
const saveStatusLabel = computed(() => {
  if (store.saveStatus === 'saving') return '正在自动保存…'
  if (store.saveStatus === 'saved') return '草稿已自动保存'
  if (store.saveStatus === 'error') return '自动保存失败'
  return ''
})

const stageFromTask = (task) => {
  if (!task) return 1
  if (task.current_stage === 'review') return 3
  if (['generation', 'strategy'].includes(task.current_stage)) return 2
  return 1
}

const initializeFormValues = () => {
  Object.keys(formValues).forEach((key) => delete formValues[key])
  const saved = store.task?.brief?.form_values || {}
  const hasSavedValues = Object.values(saved).some(
    (value) => value !== undefined && value !== null && value !== '' && (!Array.isArray(value) || value.length)
  )
  const defaults = hasSavedValues
    ? {}
    : testFormDefaults[store.template?.slug || selectedTemplate.value?.slug] || {}
  activeFields.value.forEach((field) => {
    if (hasSavedValues && saved[field.key] !== undefined) formValues[field.key] = saved[field.key]
    else if (defaults[field.key] !== undefined) formValues[field.key] = defaults[field.key]
    else if (field.type === 'tags') formValues[field.key] = []
    else formValues[field.key] = ''
  })
}

const revokePreviewUrls = (urls) => {
  Object.values(urls || {}).forEach((url) => {
    if (url) URL.revokeObjectURL(url)
  })
}

const initializeVisualSelection = () => {
  const saved = store.task?.brief?.visual_material || {}
  selectedImageItemId.value = store.task?.selected_image_item_id || saved.image_item_id || ''
  selectedPosterTemplateId.value =
    store.task?.selected_poster_template_id || saved.poster_template_id || ''
}

const loadGalleryImages = async () => {
  const generation = ++materialPreviewGeneration
  revokePreviewUrls(materialImageUrls.value)
  materialImageUrls.value = {}
  galleryImages.value = []
  if (!activeGalleryId.value) return
  galleryImagesLoading.value = true
  try {
    const response = await materialLibraryApi.listItems({
      material_type: 'image',
      category: activeGalleryId.value,
      status: 'enabled',
      page: 1,
      page_size: 100,
      sort: 'newest'
    })
    if (generation !== materialPreviewGeneration) return
    galleryImages.value = response.items || []
    const selectedItem = galleryImages.value.find((item) => item.id === selectedImageItemId.value)
    if (selectedItem) {
      selectedImageGalleryId.value = activeGalleryId.value
      selectedImageSummary.value = selectedItem
    }
    const nextUrls = {}
    await Promise.all(
      galleryImages.value.map(async (item) => {
        try {
          const file = await materialLibraryApi.getItemFile(item.id)
          nextUrls[item.id] = URL.createObjectURL(await file.blob())
        } catch {
          nextUrls[item.id] = ''
        }
      })
    )
    if (generation !== materialPreviewGeneration) {
      revokePreviewUrls(nextUrls)
      return
    }
    materialImageUrls.value = nextUrls
  } catch (error) {
    if (generation === materialPreviewGeneration) {
      message.warning(error.message || '图库图片加载失败')
    }
  } finally {
    if (generation === materialPreviewGeneration) galleryImagesLoading.value = false
  }
}

const openGallery = async (galleryId) => {
  activeGalleryId.value = galleryId
  pendingImageItemId.value = selectedImageItemId.value
  galleryModalOpen.value = true
  await loadGalleryImages()
}

const confirmGalleryImage = () => {
  selectedImageItemId.value = pendingImageItemId.value
  const selectedItem = galleryImages.value.find((item) => item.id === pendingImageItemId.value)
  if (selectedItem) {
    selectedImageGalleryId.value = activeGalleryId.value
    selectedImageSummary.value = selectedItem
  } else if (!pendingImageItemId.value) {
    selectedImageGalleryId.value = ''
    selectedImageSummary.value = null
  }
  galleryModalOpen.value = false
}

const clearSelectedGalleryImage = () => {
  selectedImageItemId.value = ''
  selectedImageGalleryId.value = ''
  selectedImageSummary.value = null
}

const listAllMaterialPosterTemplates = async () => {
  const templates = []
  let page = 1
  while (true) {
    const response = await materialLibraryApi.listItems({
      material_type: 'cover_template',
      page,
      page_size: 100,
      sort: 'newest'
    })
    const pageItems = response.items || []
    templates.push(...pageItems)
    if (!pageItems.length || templates.length >= (response.total || templates.length)) break
    page += 1
  }
  return templates
}

const refreshPosterTemplates = async ({ notifySelectionReset = true } = {}) => {
  if (!store.task || stage.value !== 1 || posterTemplatesRefreshing.value) return
  posterTemplatesRefreshing.value = true
  const generation = ++posterPreviewGeneration
  try {
    const nextTemplates = await listAllMaterialPosterTemplates()
    if (generation !== posterPreviewGeneration) return
    const nextSignature = JSON.stringify(
      nextTemplates.map((item) => [
        item.id,
        item.asset_id,
        item.poster_template_id,
        item.name,
        item.category,
        item.category_name,
        item.sha256,
        item.status,
        item.template_status,
        item.template_version,
        item.selectable
      ])
    )
    if (nextSignature !== posterTemplateSignature) {
      const previousById = new Map(posterTemplates.value.map((item) => [item.id, item]))
      const nextUrls = {}
      await Promise.all(
        nextTemplates.map(async (item) => {
          const previous = previousById.get(item.id)
          if (
            previous?.asset_id === item.asset_id &&
            previous?.sha256 === item.sha256 &&
            posterTemplateUrls.value[item.id]
          ) {
            nextUrls[item.id] = posterTemplateUrls.value[item.id]
            return
          }
          try {
            const file = await materialLibraryApi.getItemFile(item.id)
            nextUrls[item.id] = URL.createObjectURL(await file.blob())
          } catch {
            nextUrls[item.id] = ''
          }
        })
      )
      if (generation !== posterPreviewGeneration) {
        const retainedUrls = new Set(Object.values(posterTemplateUrls.value))
        Object.values(nextUrls).forEach((url) => {
          if (url && !retainedUrls.has(url)) URL.revokeObjectURL(url)
        })
        return
      }
      const nextUrlSet = new Set(Object.values(nextUrls))
      Object.values(posterTemplateUrls.value).forEach((url) => {
        if (url && !nextUrlSet.has(url)) URL.revokeObjectURL(url)
      })
      posterTemplates.value = nextTemplates
      posterTemplateUrls.value = nextUrls
      posterTemplateSignature = nextSignature
    }
    if (
      selectedPosterTemplateId.value &&
      !nextTemplates.some(
        (item) => item.poster_template_id === selectedPosterTemplateId.value && item.selectable
      )
    ) {
      selectedPosterTemplateId.value = ''
      if (notifySelectionReset) message.warning('原封面模板已停用、移除或尚未完成标注，已切换为系统自动生成')
    }
  } catch (error) {
    if (generation === posterPreviewGeneration) {
      message.warning(error.message || '封面模板同步失败')
    }
  } finally {
    if (generation === posterPreviewGeneration) posterTemplatesRefreshing.value = false
  }
}

const syncPosterTemplatesWhenVisible = () => {
  if (document.visibilityState === 'visible') void refreshPosterTemplates()
}

const loadVisualMaterials = async () => {
  if (!store.task) return
  materialSelectorLoading.value = true
  try {
    const [galleryResponse] = await Promise.all([
      materialLibraryApi.listGalleries(),
      refreshPosterTemplates({ notifySelectionReset: false })
    ])
    materialGalleries.value = galleryResponse.galleries || []
    const savedCategoryId =
      store.task?.runtime_config_snapshot?.visual_material?.image_category_id ||
      store.task?.brief?.visual_material?.image_category_id
    activeGalleryId.value =
      (savedCategoryId && materialGalleries.value.some((item) => item.id === savedCategoryId)
        ? savedCategoryId
        : activeGalleryId.value) || materialGalleries.value[0]?.id || ''
    selectedImageGalleryId.value = selectedImageItemId.value ? savedCategoryId || '' : ''
    if (selectedImageItemId.value && activeGalleryId.value) await loadGalleryImages()
  } catch (error) {
    message.warning(error.message || '视觉素材加载失败')
  } finally {
    materialSelectorLoading.value = false
  }
}

const syncEditor = () => {
  editor.title = store.artifact?.title || ''
  editor.body = store.artifact?.body || ''
  editor.topics = [...(store.artifact?.topics || [])]
}

watch(
  () => store.task,
  (task) => {
    if (!task) return
    stage.value = stageFromTask(task)
    syncEditor()
  },
  { deep: true }
)

watch(
  () => store.interrupt,
  (interrupt) => {
    selectedAngleId.value = ''
    selectedTitleId.value = ''
    selectedTitleFormulaCode.value = ''
    selectedBodyFormulaCode.value = ''
    selectedCoverAssetId.value = ''
    confirmedEvidenceIds.value = ['high_risk_facts', 'strategy_product_facts'].includes(
      interrupt?.interrupt_type
    )
      ? [...(interrupt.evidence_ids || [])]
      : []
    approvalNote.value = ''
  },
  { deep: true }
)

watch(
  () => store.artifact?.cover_asset_id,
  async (assetId) => {
    const generation = ++coverLoadGeneration
    if (coverUrl.value) {
      URL.revokeObjectURL(coverUrl.value)
      coverUrl.value = ''
    }
    if (!assetId) return
    coverLoading.value = true
    try {
      const response = await contentApi.getCoverAssetFile(assetId)
      const nextUrl = URL.createObjectURL(await response.blob())
      if (generation !== coverLoadGeneration) {
        URL.revokeObjectURL(nextUrl)
        return
      }
      coverUrl.value = nextUrl
    } catch (error) {
      if (generation === coverLoadGeneration) {
        message.warning(error.message || '当前封面暂时无法预览')
      }
    } finally {
      if (generation === coverLoadGeneration) coverLoading.value = false
    }
  },
  { immediate: true }
)

watch(
  () =>
    store.interrupt?.interrupt_type === 'cover_selection'
      ? (store.interrupt.asset_ids || []).join('|')
      : '',
  async (assetKey) => {
    const generation = ++coverCandidateLoadGeneration
    Object.values(coverCandidateUrls.value).forEach((url) => URL.revokeObjectURL(url))
    coverCandidateUrls.value = {}
    if (!assetKey) return

    coverCandidatesLoading.value = true
    const nextUrls = {}
    await Promise.all(
      assetKey.split('|').map(async (assetId) => {
        try {
          const response = await contentApi.getCoverAssetFile(assetId)
          nextUrls[assetId] = URL.createObjectURL(await response.blob())
        } catch {
          nextUrls[assetId] = ''
        }
      })
    )
    if (generation !== coverCandidateLoadGeneration) {
      Object.values(nextUrls).forEach((url) => {
        if (url) URL.revokeObjectURL(url)
      })
      return
    }
    coverCandidateUrls.value = nextUrls
    coverCandidatesLoading.value = false
  },
  { immediate: true }
)

watch(
  () => creation.industry_template_id,
  () => {
    const template = selectedTemplate.value
    if (template && !creation.content_goal) creation.content_goal = template.default_goal
    if (!store.task) initializeFormValues()
  }
)

onMounted(async () => {
  window.addEventListener('focus', syncPosterTemplatesWhenVisible)
  document.addEventListener('visibilitychange', syncPosterTemplatesWhenVisible)
  posterTemplateSyncTimer = window.setInterval(syncPosterTemplatesWhenVisible, posterTemplateSyncIntervalMs)
  try {
    await store.loadBootstrap()
    if (taskId.value) {
      await store.loadTask(taskId.value)
      initializeFormValues()
      initializeVisualSelection()
      syncEditor()
      if (stage.value === 1) await loadVisualMaterials()
      if (
        store.task?.latest_run_id &&
        [
          'queued',
          'running',
          'waiting_human',
          'waiting_external',
          'failed',
          'cancelled'
        ].includes(store.task.status)
      ) {
        void store.recoverRun(store.task.latest_run_id)
      }
    } else {
      store.resetCurrentTask()
      creation.industry_template_id = store.templates[0]?.id || ''
      creation.content_goal = selectedTemplate.value?.default_goal || 'acquire'
      initializeFormValues()
    }
  } catch (error) {
    message.error(error.message || '内容工作台加载失败')
  }
})

const createTask = async () => {
  if (!creation.industry_template_id || !creation.content_goal) {
    message.warning('请选择行业模板和内容目标')
    return
  }
  try {
    const task = await store.createTask({ ...creation })
    await router.replace(`/content/tasks/${task.id}`)
    initializeFormValues()
    initializeVisualSelection()
    await loadVisualMaterials()
    message.success('内容任务已创建')
  } catch (error) {
    message.error(error.message || '创建任务失败')
  }
}

const buildBrief = () => ({
  brand: { name: formValues.brand_name || '' },
  audience: formValues.audience || [],
  business_variables: Object.fromEntries(
    Object.entries(formValues).filter(
      ([key]) =>
        !['brand_name', 'audience', 'persona', 'required_terms', 'forbidden_terms'].includes(key)
    )
  ),
  persona: formValues.persona ? { description: formValues.persona } : {},
  required_terms: formValues.required_terms || [],
  forbidden_terms: formValues.forbidden_terms || [],
  attachments: [],
  locked_fields: [],
  form_values: { ...formValues },
  visual_material: selectedImageItemId.value
    ? {
        image_item_id: selectedImageItemId.value,
        poster_template_id: selectedPosterTemplateId.value || null
      }
    : null
})

const scheduleBriefSave = () => {
  if (!store.task || stage.value !== 1) return
  window.clearTimeout(draftSaveTimer)
  draftSaveTimer = window.setTimeout(() => {
    store.saveBrief(buildBrief()).catch(() => {})
  }, 800)
}

watch(formValues, scheduleBriefSave, { deep: true })
watch([selectedImageItemId, selectedPosterTemplateId], scheduleBriefSave)
watch(
  () => runtimeTimeline.value.length,
  async () => {
    await nextTick()
    if (runtimeTimelineElement.value) {
      runtimeTimelineElement.value.scrollTop = runtimeTimelineElement.value.scrollHeight
    }
  }
)

onBeforeUnmount(() => {
  window.clearTimeout(draftSaveTimer)
  window.clearInterval(posterTemplateSyncTimer)
  window.removeEventListener('focus', syncPosterTemplatesWhenVisible)
  document.removeEventListener('visibilitychange', syncPosterTemplatesWhenVisible)
  coverLoadGeneration += 1
  coverCandidateLoadGeneration += 1
  materialPreviewGeneration += 1
  posterPreviewGeneration += 1
  if (coverUrl.value) URL.revokeObjectURL(coverUrl.value)
  Object.values(coverCandidateUrls.value).forEach((url) => URL.revokeObjectURL(url))
  revokePreviewUrls(materialImageUrls.value)
  revokePreviewUrls(posterTemplateUrls.value)
})

const compileBrief = async () => {
  try {
    window.clearTimeout(draftSaveTimer)
    await store.compileBrief(buildBrief())
    stage.value = 2
    message.success('业务简报已形成，可启动 V3 内容工作流')
  } catch (error) {
    message.error(error.message || '请补充必填业务信息')
  }
}

const startGeneration = async () => {
  try {
    await store.startRun(modelSpec.value)
  } catch (error) {
    message.error(error.message || '启动内容生成失败')
  }
}

const retryFailedRun = async () => {
  try {
    await store.retryNode(failedNodeId.value, modelSpec.value)
    message.success('已从失败 checkpoint 继续执行')
  } catch (error) {
    message.error(error.message || '失败节点重试失败')
  }
}

const submitHumanReview = async () => {
  try {
    const metadata = {
      run_id: store.interrupt?.run_id,
      node_id: store.interrupt?.node_id,
      expected_state_version: store.interrupt?.expected_state_version
    }
    if (store.interrupt?.interrupt_type === 'content_direction') {
      const selected = angleOptions.value.find((item) => item.direction_code === selectedAngleId.value)
      if (!selected) {
        message.warning('请选择一个内容方向')
        return
      }
      await store.resumeRun({
        ...metadata,
        direction_code: selected.direction_code
      })
      return
    }
    if (['high_risk_facts', 'strategy_product_facts'].includes(store.interrupt?.interrupt_type)) {
      await store.resumeRun({
        ...metadata,
        confirmed_evidence_ids: confirmedEvidenceIds.value
      })
      return
    }
    if (store.interrupt?.interrupt_type === 'formula_selection') {
      if (!selectedTitleFormulaCode.value || !selectedBodyFormulaCode.value) {
        message.warning('请各选择一个标题公式和正文公式')
        return
      }
      await store.resumeRun({
        ...metadata,
        title_formula_code: selectedTitleFormulaCode.value,
        body_formula_code: selectedBodyFormulaCode.value
      })
      return
    }
    if (store.interrupt?.interrupt_type === 'content_correction') {
      await store.resumeRun({ ...metadata, decision: 'revise' })
      return
    }
    if (store.interrupt?.interrupt_type === 'cover_selection') {
      if (!selectedCoverAssetId.value) {
        message.warning('请选择一张封面')
        return
      }
      await store.resumeRun({ ...metadata, asset_id: selectedCoverAssetId.value })
      return
    }
    if (!selectedTitleId.value) {
      message.warning('请选择一个标题')
      return
    }
    await store.resumeRun({
      ...metadata,
      title_id: selectedTitleId.value
    })
  } catch (error) {
    message.error(error.message || '恢复工作流失败')
  }
}

const submitHumanApproval = async (approved) => {
  try {
    await store.resumeRun({
      run_id: store.interrupt?.run_id,
      node_id: store.interrupt?.node_id,
      expected_state_version: store.interrupt?.expected_state_version,
      decision: approved ? 'approved' : 'rejected',
      note: approvalNote.value.trim() || null
    })
  } catch (error) {
    message.error(error.message || '提交人工审批失败')
  }
}

const saveArtifact = async () => {
  try {
    await store.saveArtifact({ ...editor })
    syncEditor()
    message.success('已保存新的内容版本')
  } catch (error) {
    message.error(error.message || '保存内容失败')
  }
}

const reviewArtifact = async () => {
  try {
    await store.reviewArtifact(modelSpec.value)
    syncEditor()
    message.success('内容审核完成')
  } catch (error) {
    message.error(error.message || '内容审核失败')
  }
}

const finalizeArtifact = async () => {
  try {
    await store.finalizeArtifact()
    await router.push(`/content/results/${store.task.id}`)
    message.success('已保存为正式内容资产')
  } catch (error) {
    message.error(error.message || '保存正式版本失败')
  }
}

const openVersions = async () => {
  await store.loadVersions()
  versionDrawerOpen.value = true
}
</script>

<template>
  <div class="content-studio-page">
    <header class="studio-header">
      <div>
        <div class="header-kicker">Yuxi Content Strategy Studio</div>
        <h1>{{ store.task?.name || '新建内容任务' }}</h1>
        <p>规则、事实和知识同源，关键节点由人确认。</p>
      </div>
      <div class="header-actions">
        <a-button @click="router.push('/content/accounts')"><UserRoundCog :size="16" />账号管理</a-button>
        <a-button
          :disabled="!store.task"
          :title="store.task ? '上传图片并使用 RapidOCR 识别' : '请先创建内容任务'"
          @click="ocrModalOpen = true"
        ><ScanText :size="16" />图片识别</a-button>
        <a-button @click="router.push('/content/history')"><History :size="16" />生产历史</a-button>
        <a-button v-if="userStore.isAdmin" @click="router.push('/content/admin/rules')">
          <Settings2 :size="16" />创作规则库
        </a-button>
      </div>
    </header>

    <ContentStageStepper :current="stage" @select="stage = $event" />

    <main v-if="!store.loading.bootstrap" class="studio-main">
      <section v-if="stage === 1" class="stage-panel">
        <div class="panel-heading">
          <div><span>阶段 1</span><h2>业务素材与事实简报</h2></div>
          <p>先确定企业真实业务资料，后续标题与正文共享同一份事实。</p>
        </div>

        <template v-if="!store.task">
          <div class="setup-grid">
            <label class="field-block">
              <span>使用模式</span>
              <a-segmented v-model:value="creation.mode" :options="[{ label: '简化版', value: 'quick' }, { label: '专业版', value: 'pro' }]" />
              <small>简化版由 V3 自动锁定公式；专业版会在人工节点确认公式对。</small>
            </label>
            <label class="field-block">
              <span>内容目标</span>
              <a-select v-model:value="creation.content_goal" placeholder="请选择内容目标">
                <a-select-option v-for="goal in store.contentGoals" :key="goal.code" :value="goal.code">
                  {{ goal.name }} · {{ goal.description }}
                </a-select-option>
              </a-select>
            </label>
          </div>

          <div class="template-grid">
            <button
              v-for="item in store.templates"
              :key="item.id"
              type="button"
              class="template-card"
              :class="{ selected: creation.industry_template_id === item.id }"
              @click="creation.industry_template_id = item.id; creation.content_goal = item.default_goal"
            >
              <strong>{{ item.name }}</strong>
              <span>{{ item.description }}</span>
              <small>默认目标：{{ store.contentGoals.find((goal) => goal.code === item.default_goal)?.name }}</small>
            </button>
          </div>

          <div class="stage-actions">
            <a-button type="primary" :loading="store.loading.saving" @click="createTask">
              创建任务并填写素材
            </a-button>
          </div>
        </template>

        <template v-else>
          <div class="brief-layout">
            <div class="form-card">
              <div class="mode-row">
                <span class="mode-badge">{{ isQuickMode ? '简化版' : '专业版' }}</span>
                <span>{{ store.template?.name }}</span>
                <small v-if="saveStatusLabel" :class="{ 'save-error': store.saveStatus === 'error' }">{{ saveStatusLabel }}</small>
              </div>
              <div class="dynamic-form">
                <label v-for="field in activeFields" :key="field.key" class="field-block">
                  <span>{{ field.label }}<em v-if="field.required">*</em></span>
                  <a-input
                    v-if="field.type === 'text'"
                    v-model:value="formValues[field.key]"
                    :placeholder="field.placeholder || `请输入${field.label}`"
                  />
                  <a-textarea
                    v-else-if="field.type === 'textarea'"
                    v-model:value="formValues[field.key]"
                    :rows="3"
                    :placeholder="field.placeholder || `请输入${field.label}`"
                  />
                  <a-select
                    v-else-if="field.type === 'tags'"
                    v-model:value="formValues[field.key]"
                    mode="tags"
                    :token-separators="[',', '，']"
                    :placeholder="`输入${field.label}后回车`"
                  />
                </label>
              </div>
            </div>
            <aside class="facts-preview">
              <BookOpenCheck :size="22" />
              <h3>事实优先</h3>
              <p>提交后系统会形成 ContentBrief，并把人工输入标准化为带来源的 EvidenceBundle。</p>
              <ul>
                <li>数字和结果必须可验证</li>
                <li>知识库由内容调研 Agent 统一配置</li>
                <li>规则组合不通过 RAG 判断</li>
              </ul>
            </aside>
          </div>
          <section class="visual-material-card">
            <div class="visual-material-heading">
              <div>
                <span class="section-kicker">视觉素材</span>
                <h3>选择图库与封面模板</h3>
                <p>可提前保存图库图片和封面模板；当前 V3.4 暂不执行封面生成与交付，不影响标题和正文生产。</p>
              </div>
              <a-button @click="router.push('/materials/images')">
                <FolderOpen :size="15" />管理素材库
              </a-button>
            </div>

            <a-spin :spinning="materialSelectorLoading">
              <div class="material-selector-block">
                <div class="material-selector-title">
                  <div><Image :size="18" /><strong>选择图库图片</strong><em>可选 · 单选</em></div>
                  <small>可从当前账号的图库中选择一张已启用图片；不选择也可以进入内容生产。</small>
                </div>
                <div v-if="materialGalleries.length" class="gallery-folder-grid" aria-label="素材图库">
                  <button
                    v-for="gallery in materialGalleries"
                    :key="gallery.id"
                    type="button"
                    class="gallery-folder-card"
                    :class="{ selected: selectedImageItemId && selectedImageGalleryId === gallery.id }"
                    @click="openGallery(gallery.id)"
                  >
                    <span class="gallery-folder-icon"><Folder :size="30" /></span>
                    <span class="gallery-folder-copy">
                      <strong>{{ gallery.name }}</strong>
                      <small>{{ gallery.count }} 张图片素材</small>
                    </span>
                    <span v-if="selectedImageItemId && selectedImageGalleryId === gallery.id" class="gallery-selected-badge">
                      已选择
                    </span>
                  </button>
                </div>
                <a-empty v-else description="素材库中还没有图库" />
                <div v-if="selectedImageItemId" class="selected-gallery-image">
                  <span><CheckCircle2 :size="18" /></span>
                  <div>
                    <small>当前已选图片</small>
                    <strong>{{ selectedImageSummary?.name || '已选择 1 张图库图片' }}</strong>
                    <em>{{ materialGalleries.find((item) => item.id === selectedImageGalleryId)?.name || '素材图库' }}</em>
                  </div>
                  <a-button
                    v-if="selectedImageGalleryId"
                    type="link"
                    @click="openGallery(selectedImageGalleryId)"
                  >
                    更换
                  </a-button>
                  <a-button type="link" danger @click="clearSelectedGalleryImage">清除</a-button>
                </div>
              </div>

              <div class="material-selector-block template-selector-block">
                <div class="material-selector-title">
                  <div>
                    <LayoutTemplate :size="18" /><strong>选择封面模板</strong><em>可选 · 单选</em>
                    <span class="template-sync-status">
                      <RefreshCw :class="{ spin: posterTemplatesRefreshing }" :size="13" />与素材库实时同步
                    </span>
                  </div>
                  <small>选择结果随业务简报保存，后续恢复视觉流程时可直接沿用。</small>
                </div>
                <div class="poster-choice-grid">
                  <button
                    type="button"
                    class="poster-choice automatic"
                    :class="{ selected: !selectedPosterTemplateId }"
                    :aria-pressed="!selectedPosterTemplateId"
                    @click="selectedPosterTemplateId = ''"
                  >
                    <span class="poster-auto-preview"><Sparkles :size="24" /></span>
                    <strong>暂不指定模板</strong>
                    <small>仅生产标题与正文</small>
                    <CheckCircle2 v-if="!selectedPosterTemplateId" class="choice-check" :size="20" />
                  </button>
                  <button
                    v-for="item in posterTemplates"
                    :key="item.id"
                    type="button"
                    class="poster-choice"
                    :class="{
                      selected: selectedPosterTemplateId === item.poster_template_id,
                      unavailable: !item.selectable
                    }"
                    :aria-pressed="selectedPosterTemplateId === item.poster_template_id"
                    :aria-disabled="!item.selectable"
                    :disabled="!item.selectable"
                    @click="selectedPosterTemplateId = item.poster_template_id"
                  >
                    <span class="poster-preview">
                      <img v-if="posterTemplateUrls[item.id]" :src="posterTemplateUrls[item.id]" :alt="item.name" />
                      <LayoutTemplate v-else :size="24" />
                    </span>
                    <strong>{{ item.name }}</strong>
                    <small>
                      {{ item.category_name || '未分类' }}
                      <template v-if="!item.selectable">
                        · {{ item.status === 'disabled' ? '已停用' : item.template_status === 'needs_annotation' ? '待标注' : '不可用' }}
                      </template>
                    </small>
                    <CheckCircle2
                      v-if="selectedPosterTemplateId === item.poster_template_id"
                      class="choice-check"
                      :size="20"
                    />
                  </button>
                </div>
                <a-button type="link" class="template-manage-link" @click="router.push('/materials/cover-templates')">
                  管理封面模板
                </a-button>
              </div>
            </a-spin>
          </section>
          <div class="stage-actions">
            <a-button type="primary" :loading="store.loading.saving" @click="compileBrief">
              形成事实简报并进入 V3 生产
            </a-button>
          </div>
        </template>
      </section>

      <section v-else-if="stage === 2" class="stage-panel">
        <div class="panel-heading">
          <div><span>阶段 2</span><h2>V3 内容工作流</h2></div>
          <span v-if="store.currentRun" class="run-id">Run {{ store.currentRun.run_id }}</span>
        </div>

        <div v-if="!store.currentRun && !store.interrupt" class="generation-start">
          <Sparkles :size="30" />
          <h3>事实简报已锁定</h3>
          <p>固定工作流会在动态节点调用 Agent，Agent 再使用 Skill、知识库和工具，关键选择会暂停等待人工确认。</p>
          <a-input v-if="!isQuickMode" v-model:value="modelSpec" placeholder="可选：指定模型 spec；留空使用系统默认模型" />
          <a-button type="primary" size="large" @click="startGeneration"><Play :size="17" />开始生成</a-button>
        </div>

        <div v-else class="run-layout">
          <div class="workflow-groups">
            <details v-for="group in workflowGroups" :key="group.id" class="workflow-group" :class="group.status" :open="group.isOpen">
              <summary>
                <span class="workflow-group-status">
                  <LoaderCircle v-if="group.status === 'running'" class="spin" :size="19" />
                  <CheckCircle2 v-else-if="group.status === 'completed'" :size="19" />
                  <CircleAlert v-else-if="group.status === 'failed'" :size="19" />
                  <Clock3 v-else :size="19" />
                </span>
                <span class="workflow-group-copy">
                  <strong>{{ group.label }}</strong>
                  <small>{{ group.description }}</small>
                </span>
                <span class="workflow-group-progress">{{ group.completedCount }}/{{ group.totalCount }}</span>
                <ChevronDown class="workflow-group-chevron" :size="17" />
              </summary>
              <div class="workflow-group-current">{{ group.currentText }}</div>
              <div class="run-timeline">
                <div v-for="node in group.nodes" :key="node.id" class="run-node" :class="node.status">
                  <LoaderCircle v-if="node.status === 'running'" class="spin" :size="16" />
                  <CheckCircle2 v-else-if="node.status === 'completed'" :size="16" />
                  <CircleAlert v-else-if="node.status === 'failed'" :size="16" />
                  <Clock3 v-else :size="16" />
                  <span>{{ node.label }}</span>
                </div>
              </div>
            </details>
          </div>

          <aside class="run-sidebar">
            <section class="runtime-panel">
              <div class="runtime-panel-heading">
                <div>
                  <span class="runtime-live-dot" :class="{ active: store.loading.running }"></span>
                  <h3>运行详情</h3>
                </div>
                <small>{{ store.loading.running ? '实时更新' : `${runtimeTimeline.length} 条记录` }}</small>
              </div>
              <div ref="runtimeTimelineElement" class="runtime-event-list" aria-live="polite">
                <div v-if="!runtimeTimeline.length" class="runtime-empty">
                  <LoaderCircle v-if="store.loading.running" class="spin" :size="18" />
                  <Clock3 v-else :size="18" />
                  <span>{{ store.loading.running ? '正在等待第一条运行事件…' : '暂无运行详情' }}</span>
                </div>
                <article v-for="item in runtimeTimeline" :key="item.id" class="runtime-event" :class="item.status">
                  <span class="runtime-event-status">
                    <LoaderCircle v-if="item.status === 'running'" class="spin" :size="14" />
                    <CheckCircle2 v-else-if="item.status === 'completed'" :size="14" />
                    <CircleAlert v-else-if="item.status === 'failed'" :size="14" />
                    <Clock3 v-else :size="14" />
                  </span>
                  <div class="runtime-event-copy">
                    <strong>{{ item.label }}</strong>
                    <span v-if="item.detail">{{ item.detail }}</span>
                    <small v-if="item.nodeLabel">{{ item.nodeLabel }}</small>
                  </div>
                  <div class="runtime-event-meta">
                    <time v-if="item.createdAt">{{ formatRuntimeTime(item.createdAt) }}</time>
                    <span v-if="item.durationMs !== undefined">{{ formatRuntimeDuration(item.durationMs) }}</span>
                  </div>
                  <div
                    v-if="item.inputPreview || item.outputPreview || item.knowledgeResults?.length"
                    class="runtime-event-details"
                  >
                    <details v-if="item.inputPreview">
                      <summary>查看本步骤使用的信息</summary>
                      <div class="runtime-preview-content">
                        <ContentExecutionPreview :value="item.inputPreview" />
                      </div>
                    </details>
                    <details v-if="item.knowledgeResults?.length" open>
                      <summary>查看命中的知识内容</summary>
                      <ol class="runtime-knowledge-results">
                        <li v-for="(result, resultIndex) in item.knowledgeResults" :key="result.source_id || resultIndex">
                          <strong>{{ result.file_name || result.file_id || `命中片段 ${resultIndex + 1}` }}</strong>
                          <p>{{ result.content }}</p>
                          <small v-if="result.score !== null && result.score !== undefined">相关度：{{ Number(result.score).toFixed(3) }}</small>
                        </li>
                      </ol>
                    </details>
                    <details v-if="item.outputPreview" :open="item.status === 'failed'">
                      <summary>查看决策依据与产出内容</summary>
                      <div class="runtime-preview-content">
                        <ContentExecutionPreview :value="item.outputPreview" />
                      </div>
                    </details>
                  </div>
                </article>
              </div>
            </section>

          <div v-if="store.interrupt?.interrupt_type === 'content_direction'" class="human-review-card">
            <div class="human-heading"><Sparkles :size="20" /><div><h3>选择本次内容方向</h3><p>Agent 已根据目标、事实和证据生成候选方向，选择后将由固定规则匹配组合组。</p></div></div>
            <a-radio-group v-model:value="selectedAngleId" class="title-options angle-options">
              <a-radio v-for="item in angleOptions" :key="item.direction_code" :value="item.direction_code">
                <strong>{{ item.direction_code }}</strong>
                <span>{{ item.reason }}</span>
                <div v-if="item.evidence_ids?.length" class="evidence-references">
                  <div class="evidence-references-title">引用证据</div>
                  <ol>
                    <li v-for="(evidenceId, index) in item.evidence_ids" :key="evidenceId">
                      {{ evidenceReferenceText(evidenceId, index) }}
                    </li>
                  </ol>
                </div>
              </a-radio>
            </a-radio-group>
            <a-button type="primary" :disabled="!selectedAngleId" @click="submitHumanReview">确认方向并继续</a-button>
          </div>

          <div v-else-if="store.interrupt?.interrupt_type === 'title_selection'" class="human-review-card">
            <div class="human-heading"><Send :size="20" /><div><h3>请选择最终标题</h3><p>选择后 LangGraph 从 checkpoint 恢复，无需重新检索证据。</p></div></div>
            <a-radio-group v-model:value="selectedTitleId" class="title-options">
              <a-radio v-for="item in titleOptions" :key="item.id" :value="item.id">
                <strong>{{ item.text }}</strong>
                <span>{{ item.formula_code }} · 引用 {{ item.evidence_ids?.length || 0 }} 条证据</span>
              </a-radio>
            </a-radio-group>
            <a-button type="primary" @click="submitHumanReview">确认标题并继续生成</a-button>
          </div>

          <div v-else-if="['high_risk_facts', 'strategy_product_facts'].includes(store.interrupt?.interrupt_type)" class="human-review-card">
            <div class="human-heading"><ShieldCheck :size="20" /><div><h3>确认关键事实</h3><p>价格、优惠、效果或高风险表达必须逐项确认后才能进入冻结证据并用于生成。</p></div></div>
            <a-checkbox-group v-model:value="confirmedEvidenceIds" class="fact-options">
              <a-checkbox v-for="item in store.interrupt.evidence_ids" :key="item" :value="item">
                <strong>{{ evidenceReferenceText(item) }}</strong>
              </a-checkbox>
            </a-checkbox-group>
            <a-button type="primary" @click="submitHumanReview">确认选中事实并继续</a-button>
          </div>

          <div v-else-if="store.interrupt?.interrupt_type === 'formula_selection'" class="human-review-card">
            <div class="human-heading"><Sparkles :size="20" /><div><h3>选择公式对</h3><p>专业模式下，从当前组合组的合法候选池中各选一个标题公式和正文公式。</p></div></div>
            <label class="field-block"><span>标题公式</span>
              <a-select v-model:value="selectedTitleFormulaCode">
                <a-select-option v-for="code in store.interrupt.title_formula_codes" :key="code" :value="code">{{ code }}</a-select-option>
              </a-select>
            </label>
            <label class="field-block"><span>正文公式</span>
              <a-select v-model:value="selectedBodyFormulaCode">
                <a-select-option v-for="code in store.interrupt.body_formula_codes" :key="code" :value="code">{{ code }}</a-select-option>
              </a-select>
            </label>
            <a-button type="primary" @click="submitHumanReview">锁定公式并继续</a-button>
          </div>

          <div v-else-if="store.interrupt?.interrupt_type === 'content_approval'" class="human-review-card">
            <div class="human-heading"><ShieldCheck :size="20" /><div><h3>最终人工审批</h3><p>请根据审核结果确认是否允许保存内容资产。</p></div></div>
            <div v-if="store.interrupt.review_report?.checks?.length" class="approval-checks">
              <div v-for="check in store.interrupt.review_report.checks" :key="`${check.code}-${check.message}`">
                <strong>{{ check.message }}</strong>
                <span v-if="check.suggestion">{{ check.suggestion }}</span>
              </div>
            </div>
            <a-textarea v-model:value="approvalNote" :rows="3" placeholder="可选：填写审批备注" />
            <div class="approval-actions">
              <a-button danger @click="submitHumanApproval(false)">驳回</a-button>
              <a-button type="primary" :disabled="!approvalAllowed" @click="submitHumanApproval(true)">通过并继续</a-button>
            </div>
          </div>

          <div v-else-if="store.interrupt?.interrupt_type === 'content_correction'" class="human-review-card">
            <div class="human-heading"><CircleAlert :size="20" /><div><h3>内容需要定点回修</h3><p>确定性校验或语义审核发现阻断问题。确认后只重跑建议节点及其下游。</p></div></div>
            <div class="approval-checks">
              <div v-for="check in correctionChecks" :key="`${check.code}-${check.location || 'content'}`">
                <strong>{{ check.message || check.code }}</strong>
                <span v-if="check.suggestion">{{ check.suggestion }}</span>
              </div>
            </div>
            <p class="correction-target">回修原因：{{ store.interrupt.reason_code }} · 目标节点：{{ store.interrupt.suggested_target }}</p>
            <div class="approval-actions">
              <a-button type="primary" @click="submitHumanReview">确认并按建议重新生成</a-button>
            </div>
          </div>

          <div v-else-if="store.interrupt?.interrupt_type === 'cover_selection'" class="human-review-card">
            <div class="human-heading"><Send :size="20" /><div><h3>选择最终封面</h3><p>只可从通过视觉审核的资产中选择。</p></div></div>
            <a-radio-group v-model:value="selectedCoverAssetId" class="title-options cover-options">
              <a-radio v-for="(assetId, index) in store.interrupt.asset_ids" :key="assetId" :value="assetId">
                <div class="cover-option">
                  <div class="cover-candidate-preview">
                    <img v-if="coverCandidateUrls[assetId]" :src="coverCandidateUrls[assetId]" :alt="`封面候选 ${index + 1}`" />
                    <div v-else class="cover-candidate-placeholder">
                      <LoaderCircle v-if="coverCandidatesLoading" class="spin" :size="22" />
                      <span v-else>封面暂时无法预览</span>
                    </div>
                  </div>
                  <strong>封面候选 {{ index + 1 }}</strong>
                  <span>{{ assetId }}</span>
                </div>
              </a-radio>
            </a-radio-group>
            <a-button type="primary" @click="submitHumanReview">确认封面并保存</a-button>
          </div>

          <div v-else-if="store.interrupt?.interrupt_type === 'external_wait'" class="running-card external-wait-card">
            <LoaderCircle class="spin" :size="26" />
            <h3>封面正在生成</h3>
            <p>这是系统等待节点，无需人工操作；封面服务完成后会自动继续后续审核。</p>
            <a-progress :percent="externalWaitProgress" :show-info="externalWaitProgress > 0" status="active" />
            <small>{{ externalWaitStatusLabel }}</small>
          </div>

          <div v-else-if="runFailed" class="running-card failure-card">
            <CircleAlert :size="26" />
            <h3>工作流执行失败</h3>
            <p>{{ store.task?.error?.message || store.lastError?.message || '已保留完成节点和 checkpoint，可从失败节点恢复。' }}</p>
            <section v-if="blockedTitleCandidates.length" class="title-validation-failures">
              <h4>标题候选校验明细</h4>
              <ol>
                <li v-for="item in blockedTitleCandidates" :key="item.id">
                  <strong>{{ item.text || item.id }}</strong>
                  <ul>
                    <li v-for="check in item.checks" :key="`${item.id}-${check.code}-${check.message}`">
                      <span>{{ check.message }}</span>
                      <small v-if="check.suggestion">{{ check.suggestion }}</small>
                    </li>
                  </ul>
                </li>
              </ol>
            </section>
            <a-button type="primary" @click="retryFailedRun"><RefreshCw :size="15" />从失败节点重试</a-button>
          </div>

          <div v-else-if="store.interrupt" class="running-card failure-card">
            <CircleAlert :size="26" />
            <h3>遇到未支持的人工节点</h3>
            <p>节点类型：{{ store.interrupt.interrupt_type || '未知' }}。请联系管理员检查工作流版本。</p>
          </div>

          <div v-else-if="!store.loading.running" class="running-card">
            <LoaderCircle class="spin" :size="26" />
            <h3>工作流正在执行</h3>
            <p>可以离开页面，任务状态与节点结果会持续保存。</p>
          </div>
          </aside>
        </div>
      </section>

      <section v-else class="stage-panel">
        <div class="panel-heading">
          <div><span>阶段 3</span><h2>审核、编辑与正式版本</h2></div>
          <div class="status-badge" :class="store.artifact?.review_snapshot?.status || 'pending'">
            {{ store.artifact?.review_snapshot?.status || '待审核' }}
          </div>
        </div>

        <div v-if="store.artifact" class="review-layout">
          <div class="content-editor-card">
            <section v-if="store.artifact.cover_asset_id" class="artifact-cover-preview">
              <div class="artifact-cover-heading">
                <div><strong>本次生成封面</strong><span>已与当前内容版本绑定</span></div>
                <small>{{ store.artifact.cover_asset_id }}</small>
              </div>
              <div v-if="coverLoading" class="cover-preview-loading">
                <LoaderCircle class="spin" :size="24" />正在加载封面
              </div>
              <img v-else-if="coverUrl" :src="coverUrl" alt="本次生成封面" />
              <a-empty v-else description="封面暂时无法预览" />
            </section>
            <label class="field-block"><span>标题</span><a-input v-model:value="editor.title" /></label>
            <label class="field-block"><span>正文</span><a-textarea v-model:value="editor.body" :rows="18" /></label>
            <label class="field-block">
              <span>话题</span>
              <a-select v-model:value="editor.topics" mode="tags" :token-separators="[',', '，']" />
            </label>
            <div class="editor-actions">
              <a-button :loading="store.loading.saving" @click="saveArtifact"><Save :size="15" />保存编辑版本</a-button>
              <a-button type="primary" :loading="store.loading.reviewing" @click="reviewArtifact"><ShieldCheck :size="15" />重新审核</a-button>
            </div>
          </div>

          <aside class="review-sidebar">
            <section>
              <h3>质量检查</h3>
              <div v-if="!reviewChecks.length" class="empty-checks"><CheckCircle2 :size="20" />暂无阻断问题</div>
              <div v-for="check in reviewChecks" :key="`${check.code}-${check.location}`" class="review-check" :class="check.level">
                <strong>{{ check.message }}</strong><span>{{ check.suggestion }}</span>
              </div>
            </section>
            <section>
              <h3>来源追溯</h3>
              <div class="evidence-list">
                <div v-for="item in store.artifact.evidence_snapshot?.items || []" :key="item.id">
                  <strong>{{ item.key }}</strong>
                  <span>{{ item.source_type }} · {{ item.verified_status }}</span>
                </div>
              </div>
            </section>
            <a-button block @click="openVersions"><FileClock :size="15" />查看版本记录</a-button>
            <a-button type="primary" block :disabled="!canFinalize" @click="finalizeArtifact">保存为正式内容资产</a-button>
          </aside>
        </div>
        <a-empty v-else description="内容资产尚未生成完成" />
      </section>
    </main>

    <div v-else class="page-loading"><LoaderCircle class="spin" :size="28" />正在加载内容工作台</div>

    <a-drawer v-model:open="versionDrawerOpen" title="内容版本记录" width="520">
      <a-timeline>
        <a-timeline-item v-for="item in store.versions" :key="item.id">
          <strong>v{{ item.version }} · {{ item.source_type }}</strong>
          <p>{{ item.title }}</p>
          <small>
            {{ item.created_at }} ·
            {{ item.model_spec || (item.source_type === 'generated' ? '系统默认模型' : '人工编辑') }}
          </small>
        </a-timeline-item>
      </a-timeline>
    </a-drawer>
    <a-modal
      v-model:open="galleryModalOpen"
      :title="`选择图片 · ${materialGalleries.find((item) => item.id === activeGalleryId)?.name || '图库'}`"
      width="920px"
      :footer="null"
    >
      <div class="gallery-modal-content">
        <div class="gallery-modal-heading">
          <p>从当前文件夹中选择一张图片；选择将在点击“确认选择”后保存到业务简报。</p>
          <span>{{ galleryImages.length }} 张图片</span>
        </div>
        <div v-if="galleryImagesLoading" class="material-loading-row">
          <LoaderCircle class="spin" :size="20" />正在加载当前图库
        </div>
        <div v-else-if="galleryImages.length" class="gallery-modal-grid">
          <button
            v-for="item in galleryImages"
            :key="item.id"
            type="button"
            class="image-choice"
            :class="{ selected: pendingImageItemId === item.id }"
            :aria-pressed="pendingImageItemId === item.id"
            @click="pendingImageItemId = item.id"
          >
            <span class="choice-preview">
              <img v-if="materialImageUrls[item.id]" :src="materialImageUrls[item.id]" :alt="item.name" />
              <Image v-else :size="22" />
              <CheckCircle2 v-if="pendingImageItemId === item.id" class="choice-check" :size="20" />
            </span>
            <strong :title="item.name">{{ item.name }}</strong>
          </button>
        </div>
        <a-empty v-else description="当前文件夹暂无可用图片" />
        <div class="gallery-modal-actions">
          <a-button v-if="pendingImageItemId" type="link" danger @click="pendingImageItemId = ''">
            清除选择
          </a-button>
          <span />
          <a-button @click="galleryModalOpen = false">取消</a-button>
          <a-button type="primary" :loading="galleryImagesLoading" @click="confirmGalleryImage">
            确认选择
          </a-button>
        </div>
      </div>
    </a-modal>
    <ContentOcrDrawer v-if="store.task" v-model:open="ocrModalOpen" :task-id="store.task.id" />
  </div>
</template>

<style scoped lang="less">
.content-studio-page {
  min-width: 0;
  min-height: 100vh;
  padding: 24px var(--page-padding) 48px;
  background: var(--gray-25);
  color: var(--color-text);
  overflow-x: hidden;
}

.studio-header {
  max-width: 1180px;
  margin: 0 auto 18px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;

  h1 { margin: 3px 0 4px; font-size: 24px; }
  p { margin: 0; color: var(--color-text-secondary); }
}

.header-kicker { color: var(--main-700); font-size: 12px; font-weight: 600; }
.header-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.header-actions :deep(.ant-btn), .panel-heading :deep(.ant-btn), .stage-actions :deep(.ant-btn), .editor-actions :deep(.ant-btn) { display: inline-flex; align-items: center; gap: 6px; }

:deep(.content-stage-stepper), .studio-main { max-width: 1180px; margin-left: auto; margin-right: auto; }
.studio-main { margin-top: 18px; }
.stage-panel { background: var(--gray-0); border: 1px solid var(--gray-150); border-radius: 8px; padding: 24px; }
.panel-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; margin-bottom: 22px; }
.panel-heading span { color: var(--main-700); font-size: 12px; font-weight: 600; }
.panel-heading h2 { margin: 2px 0 0; font-size: 20px; }
.panel-heading p { max-width: 460px; margin: 0; color: var(--color-text-secondary); }

.setup-grid, .brief-layout, .run-layout, .review-layout { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(280px, 0.8fr); gap: 20px; }
.setup-grid { grid-template-columns: 1fr 1fr; margin-bottom: 20px; }
.template-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.template-card { min-height: 116px; padding: 16px; display: flex; flex-direction: column; gap: 7px; text-align: left; border: 1px solid var(--gray-150); border-radius: 8px; background: var(--gray-0); color: var(--color-text); cursor: pointer; }
.template-card:hover { border-color: var(--main-300); background: var(--main-10); }
.template-card.selected { border-color: var(--main-color); background: var(--main-30); }
.template-card strong { font-size: 15px; }
.template-card span, .template-card small { color: var(--color-text-secondary); }

.form-card, .facts-preview, .workflow-groups, .human-review-card, .running-card, .content-editor-card, .review-sidebar { border: 1px solid var(--gray-150); border-radius: 8px; padding: 20px; background: var(--gray-0); }
.form-card, .content-editor-card { display: flex; flex-direction: column; gap: 18px; }
.dynamic-form { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.dynamic-form .field-block:has(textarea), .dynamic-form .field-block:has(.ant-select-multiple) { grid-column: 1 / -1; }
.field-block { display: flex; flex-direction: column; gap: 7px; color: var(--color-text); }
.field-block > span { font-size: 13px; font-weight: 600; }
.field-block em { margin-left: 3px; color: var(--color-error-700); font-style: normal; }
.field-block small { color: var(--color-text-tertiary); }
.mode-row { display: flex; align-items: center; gap: 8px; color: var(--color-text-secondary); }
.mode-row small { margin-left: auto; }
.mode-row .save-error { color: var(--color-error-600); }
.mode-badge, .status-badge { display: inline-flex; align-items: center; padding: 3px 9px; border-radius: 999px; background: var(--main-50); color: var(--main-700); font-size: 12px; }
.facts-preview { background: var(--gray-10); }
.facts-preview h3 { margin: 10px 0 6px; }
.facts-preview p, .facts-preview li { color: var(--color-text-secondary); }
.facts-preview ul { padding-left: 18px; }
.visual-material-card { margin-top: 20px; padding: 20px; border: 1px solid var(--gray-150); border-radius: 8px; background: var(--gray-0); }
.visual-material-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; padding-bottom: 16px; border-bottom: 1px solid var(--gray-150); }
.visual-material-heading h3 { margin: 3px 0 5px; font-size: 17px; }
.visual-material-heading p { margin: 0; color: var(--color-text-secondary); font-size: 13px; }
.section-kicker { color: var(--main-700); font-size: 12px; font-weight: 600; }
.visual-material-heading :deep(.ant-btn), .template-manage-link { display: inline-flex; align-items: center; gap: 6px; }
.material-selector-block { padding-top: 18px; }
.template-selector-block { margin-top: 18px; border-top: 1px solid var(--gray-150); }
.material-selector-title { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 12px; }
.material-selector-title > div { display: flex; align-items: center; gap: 7px; }
.material-selector-title em { padding: 2px 7px; border-radius: 999px; color: var(--main-700); background: var(--main-30); font-size: 11px; font-style: normal; }
.material-selector-title small { color: var(--color-text-tertiary); text-align: right; }
.template-sync-status { display: inline-flex; align-items: center; gap: 4px; color: var(--color-success-700); font-size: 11px; white-space: nowrap; }
.gallery-folder-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 12px; }
.gallery-folder-card { position: relative; min-height: 92px; padding: 15px; display: flex; align-items: center; gap: 12px; border: 1px solid var(--gray-150); border-radius: 9px; color: var(--color-text); background: var(--gray-0); text-align: left; cursor: pointer; }
.gallery-folder-card:hover { border-color: var(--main-300); background: var(--main-10); transform: translateY(-1px); }
.gallery-folder-card.selected { border-color: var(--main-color); background: var(--main-30); box-shadow: 0 0 0 2px var(--main-10); }
.gallery-folder-icon { flex: 0 0 auto; display: grid; place-items: center; width: 52px; height: 46px; border-radius: 8px; color: var(--main-700); background: var(--main-30); }
.gallery-folder-copy { min-width: 0; display: grid; gap: 5px; }
.gallery-folder-copy strong, .gallery-folder-copy small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gallery-folder-copy strong { font-size: 14px; }
.gallery-folder-copy small { color: var(--color-text-tertiary); font-size: 12px; }
.gallery-selected-badge { position: absolute; top: 7px; right: 8px; padding: 2px 7px; border-radius: 999px; color: var(--main-700); background: var(--main-50); font-size: 10px; }
.selected-gallery-image { margin-top: 14px; padding: 11px 13px; display: flex; align-items: center; gap: 10px; border: 1px solid var(--main-100); border-radius: 8px; background: var(--main-10); }
.selected-gallery-image > span { color: var(--main-700); }
.selected-gallery-image > div { min-width: 0; flex: 1; display: grid; gap: 2px; }
.selected-gallery-image small, .selected-gallery-image em { color: var(--color-text-tertiary); font-size: 11px; font-style: normal; }
.selected-gallery-image strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
.poster-choice-grid { display: grid; grid-auto-flow: column; grid-auto-columns: 142px; gap: 12px; padding: 2px 2px 8px; overflow-x: auto; }
.gallery-modal-content { display: grid; gap: 16px; padding-top: 4px; }
.gallery-modal-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.gallery-modal-heading p { margin: 0; color: var(--color-text-secondary); }
.gallery-modal-heading span { flex: 0 0 auto; color: var(--color-text-tertiary); font-size: 12px; }
.gallery-modal-grid { max-height: min(58vh, 620px); padding: 2px; display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; overflow-y: auto; }
.gallery-modal-actions { padding-top: 14px; display: grid; grid-template-columns: auto 1fr auto auto; gap: 8px; border-top: 1px solid var(--gray-150); }
.image-choice, .poster-choice { position: relative; min-width: 0; padding: 7px; border: 1px solid var(--gray-150); border-radius: 8px; color: var(--color-text); background: var(--gray-0); text-align: left; cursor: pointer; }
.image-choice:hover, .poster-choice:hover { border-color: var(--main-300); transform: translateY(-1px); }
.image-choice.selected, .poster-choice.selected { border-color: var(--main-color); box-shadow: 0 0 0 2px var(--main-30); }
.poster-choice.unavailable { opacity: 0.64; cursor: not-allowed; }
.poster-choice.unavailable:hover { border-color: var(--gray-150); transform: none; }
.choice-preview, .poster-preview, .poster-auto-preview { position: relative; display: grid; place-items: center; width: 100%; overflow: hidden; border-radius: 6px; color: var(--color-text-tertiary); background: var(--gray-25); }
.choice-preview { aspect-ratio: 1 / 1; }
.poster-preview, .poster-auto-preview { aspect-ratio: 3 / 4; }
.choice-preview img, .poster-preview img { width: 100%; height: 100%; object-fit: cover; }
.image-choice > strong, .poster-choice > strong, .poster-choice > small { display: block; margin-top: 7px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.image-choice > strong, .poster-choice > strong { font-size: 13px; }
.poster-choice > small { margin-top: 2px; color: var(--color-text-tertiary); font-size: 11px; }
.choice-check { position: absolute; z-index: 1; top: 9px; right: 9px; padding: 2px; border-radius: 50%; color: var(--main-color); background: var(--gray-0); }
.poster-auto-preview { color: var(--main-700); background: linear-gradient(145deg, var(--main-10), var(--main-50)); }
.material-loading-row { min-height: 140px; display: flex; align-items: center; justify-content: center; gap: 8px; color: var(--color-text-secondary); }
.template-manage-link { margin-top: 8px; padding-left: 0; }
.stage-actions { margin-top: 22px; display: flex; justify-content: flex-end; gap: 10px; }
.stage-actions.split { justify-content: space-between; }


.generation-start { max-width: 560px; margin: 50px auto; display: flex; flex-direction: column; align-items: center; gap: 12px; text-align: center; }
.generation-start h3, .generation-start p { margin: 0; }
.generation-start p { color: var(--color-text-secondary); }
.generation-start :deep(.ant-input) { max-width: 500px; }
.run-id { max-width: 360px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--color-text-tertiary) !important; }
.workflow-groups { display: flex; flex-direction: column; gap: 10px; }
.workflow-group { overflow: hidden; border: 1px solid var(--gray-150); border-radius: 8px; background: var(--gray-0); }
.workflow-group summary { min-height: 68px; display: grid; grid-template-columns: auto minmax(0, 1fr) auto auto; align-items: center; gap: 12px; padding: 12px 14px; cursor: pointer; list-style: none; }
.workflow-group summary::-webkit-details-marker { display: none; }
.workflow-group-status { display: inline-flex; color: var(--color-text-tertiary); }
.workflow-group-copy { min-width: 0; display: flex; flex-direction: column; gap: 3px; }
.workflow-group-copy strong { color: var(--color-text); font-size: 15px; line-height: 1.4; }
.workflow-group-copy small, .workflow-group-current { color: var(--color-text-secondary); font-size: 12px; line-height: 1.5; }
.workflow-group-progress { min-width: 38px; color: var(--color-text-tertiary); font-size: 12px; font-variant-numeric: tabular-nums; text-align: right; }
.workflow-group-chevron { color: var(--color-text-tertiary); transition: transform 0.2s ease; }
.workflow-group[open] .workflow-group-chevron { transform: rotate(180deg); }
.workflow-group.running, .workflow-group.active { border-color: var(--color-info-200); background: var(--color-info-50); }
.workflow-group.running .workflow-group-status, .workflow-group.active .workflow-group-status { color: var(--color-info-700); }
.workflow-group.completed .workflow-group-status { color: var(--color-success-700); }
.workflow-group.failed { border-color: var(--color-error-200); background: var(--color-error-50); }
.workflow-group.failed .workflow-group-status { color: var(--color-error-700); }
.workflow-group-current { margin: 0 14px; padding: 9px 0; border-top: 1px solid var(--gray-150); }
.run-timeline { display: flex; flex-direction: column; gap: 3px; padding: 2px 10px 12px; }
.run-node { min-height: 40px; display: flex; align-items: center; gap: 10px; padding: 8px 10px; color: var(--color-text-tertiary); border-radius: 6px; }
.run-node.running { background: var(--color-info-50); color: var(--color-info-700); }
.run-node.completed { color: var(--color-success-700); }
.run-node.failed { background: var(--color-error-50); color: var(--color-error-700); }
.run-sidebar { min-width: 0; display: flex; flex-direction: column; gap: 12px; align-self: start; }
.runtime-panel { min-width: 0; overflow: hidden; border: 1px solid var(--gray-150); border-radius: 8px; background: var(--gray-0); }
.runtime-panel-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 16px; border-bottom: 1px solid var(--gray-150); }
.runtime-panel-heading > div { display: flex; align-items: center; gap: 8px; }
.runtime-panel-heading h3 { margin: 0; font-size: 15px; }
.runtime-panel-heading small { color: var(--color-text-tertiary); font-size: 12px; }
.runtime-live-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--gray-300); }
.runtime-live-dot.active { background: var(--color-info-600); box-shadow: 0 0 0 4px var(--color-info-50); }
.runtime-event-list { max-height: 520px; overflow-y: auto; overscroll-behavior: contain; }
.runtime-empty { min-height: 132px; display: flex; align-items: center; justify-content: center; gap: 8px; color: var(--color-text-tertiary); font-size: 13px; }
.runtime-event { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: 9px; padding: 12px 14px; border-bottom: 1px solid var(--gray-100); }
.runtime-event:last-child { border-bottom: 0; }
.runtime-event-status { display: inline-flex; margin-top: 2px; color: var(--color-text-tertiary); }
.runtime-event.running .runtime-event-status { color: var(--color-info-700); }
.runtime-event.completed .runtime-event-status { color: var(--color-success-700); }
.runtime-event.failed .runtime-event-status { color: var(--color-error-700); }
.runtime-event-copy { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.runtime-event-copy strong { overflow-wrap: anywhere; color: var(--color-text); font-size: 13px; line-height: 1.45; }
.runtime-event-copy span, .runtime-event-copy small { overflow-wrap: anywhere; color: var(--color-text-secondary); font-size: 12px; line-height: 1.45; }
.runtime-event-copy small { color: var(--color-text-tertiary); }
.runtime-event-meta { display: flex; flex-direction: column; align-items: flex-end; gap: 2px; color: var(--color-text-tertiary); font-size: 10px; font-variant-numeric: tabular-nums; white-space: nowrap; }
.runtime-event-details { grid-column: 2 / -1; min-width: 0; display: flex; flex-direction: column; gap: 7px; }
.runtime-event-details details { overflow: hidden; border: 1px solid var(--gray-150); border-radius: 6px; background: var(--gray-25); }
.runtime-event-details summary { padding: 7px 9px; color: var(--main-700); font-size: 11px; cursor: pointer; }
.runtime-preview-content { max-height: 360px; padding: 9px; overflow: auto; border-top: 1px solid var(--gray-150); }
.runtime-knowledge-results { display: flex; flex-direction: column; gap: 8px; margin: 0; padding: 0 9px 9px; list-style: none; }
.runtime-knowledge-results li { padding: 9px; border-radius: 6px; background: var(--gray-0); }
.runtime-knowledge-results strong, .runtime-knowledge-results p, .runtime-knowledge-results small { display: block; margin: 0; font-size: 11px; line-height: 1.55; }
.runtime-knowledge-results p { margin-top: 4px; color: var(--color-text-secondary); white-space: pre-wrap; }
.runtime-knowledge-results small { margin-top: 4px; color: var(--color-text-tertiary); }
.human-review-card, .running-card { align-self: start; }
.failure-card { color: var(--color-error-700); background: var(--color-error-50); }
.title-validation-failures { width: 100%; margin: 8px 0 4px; padding: 14px; text-align: left; color: var(--color-text); background: var(--gray-0); border: 1px solid var(--color-error-200); border-radius: 8px; }
.title-validation-failures h4 { margin: 0 0 10px; font-size: 14px; }
.title-validation-failures > ol { display: grid; gap: 12px; margin: 0; padding-left: 22px; }
.title-validation-failures > ol > li > strong { display: block; font-size: 14px; line-height: 1.6; }
.title-validation-failures ul { display: grid; gap: 5px; margin: 6px 0 0; padding-left: 18px; color: var(--color-error-700); }
.title-validation-failures ul span, .title-validation-failures ul small { display: block; font-size: 12px; line-height: 1.55; }
.title-validation-failures ul small { margin-top: 2px; color: var(--color-text-secondary); }
.external-wait-card { gap: 10px; background: var(--color-info-50); color: var(--color-info-700); }
.external-wait-card h3, .external-wait-card p { margin: 0; }
.external-wait-card p, .external-wait-card small { color: var(--color-text-secondary); }
.external-wait-card :deep(.ant-progress) { width: 100%; }
.human-heading { display: flex; gap: 10px; margin-bottom: 16px; }
.human-heading h3, .human-heading p { margin: 0; }
.human-heading p { margin-top: 3px; color: var(--color-text-secondary); }
.title-options, .fact-options { width: 100%; display: flex; flex-direction: column; gap: 9px; margin-bottom: 16px; }
.title-options :deep(.ant-radio-wrapper), .fact-options :deep(.ant-checkbox-wrapper) { width: 100%; margin-inline-start: 0; padding: 12px; border: 1px solid var(--gray-150); border-radius: 6px; align-items: flex-start; }
.angle-options :deep(.ant-radio-wrapper-checked) { border-color: var(--main-color); background: var(--main-30); }
.angle-options strong, .angle-options span { display: block; }
.angle-options span { margin-top: 4px; color: var(--color-text-secondary); font-size: 12px; line-height: 1.5; }
.evidence-references { margin-top: 10px; padding-top: 9px; border-top: 1px solid var(--gray-150); color: var(--color-text-secondary); }
.evidence-references-title { margin-bottom: 6px; font-size: 12px; font-weight: 600; line-height: 1.5; }
.evidence-references ol { display: flex; flex-direction: column; gap: 6px; margin: 0; padding: 0; list-style: none; counter-reset: evidence-reference; }
.evidence-references li { display: grid; grid-template-columns: 24px minmax(0, 1fr); margin: 0; font-size: 13px; line-height: 1.65; overflow-wrap: anywhere; counter-increment: evidence-reference; }
.evidence-references li::before { content: counter(evidence-reference) '、'; color: var(--main-color); font-weight: 600; }
.approval-checks { display: flex; flex-direction: column; gap: 8px; margin-bottom: 14px; }
.approval-checks > div { padding: 10px 12px; border-radius: 6px; background: var(--color-warning-50); color: var(--color-warning-900); }
.approval-checks strong, .approval-checks span { display: block; font-size: 12px; }
.approval-checks span { margin-top: 3px; opacity: 0.82; }
.correction-target { margin: 12px 0 0; color: var(--gray-600); font-size: 13px; }
.approval-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 14px; }
.title-options strong, .title-options span { display: block; }
.title-options span { margin-top: 3px; color: var(--color-text-tertiary); font-size: 12px; }
.cover-options :deep(.ant-radio-wrapper) { align-items: center; }
.cover-options :deep(.ant-radio + span) { min-width: 0; flex: 1; }
.cover-option { display: grid; gap: 4px; min-width: 0; }
.cover-candidate-preview { width: 100%; margin-bottom: 7px; overflow: hidden; border-radius: 8px; background: var(--gray-25); }
.cover-candidate-preview img { display: block; width: 100%; aspect-ratio: 3 / 4; object-fit: cover; }
.cover-candidate-placeholder { min-height: 220px; display: flex; align-items: center; justify-content: center; color: var(--color-text-tertiary); }
.cover-option > span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.running-card { display: flex; flex-direction: column; align-items: center; text-align: center; }

.content-editor-card textarea { resize: vertical; }
.artifact-cover-preview { display: flex; flex-direction: column; gap: 12px; padding-bottom: 18px; border-bottom: 1px solid var(--gray-150); }
.artifact-cover-heading { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }
.artifact-cover-heading div { display: grid; gap: 3px; }
.artifact-cover-heading span, .artifact-cover-heading small { color: var(--color-text-tertiary); font-size: 12px; }
.artifact-cover-heading small { max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.artifact-cover-preview img { width: min(100%, 320px); aspect-ratio: 3 / 4; align-self: center; border-radius: 8px; object-fit: cover; box-shadow: 0 8px 24px var(--shadow-3); }
.cover-preview-loading { min-height: 240px; display: flex; align-items: center; justify-content: center; gap: 8px; color: var(--color-text-secondary); background: var(--gray-25); border-radius: 8px; }
.editor-actions { display: flex; justify-content: flex-end; gap: 8px; flex-wrap: wrap; }
.review-sidebar { display: flex; flex-direction: column; gap: 16px; align-self: start; }
.review-sidebar section { border-bottom: 1px solid var(--gray-150); padding-bottom: 14px; }
.review-sidebar h3 { margin: 0 0 10px; }
.empty-checks { display: flex; align-items: center; gap: 8px; color: var(--color-success-700); }
.review-check { margin-bottom: 8px; padding: 10px; border-radius: 6px; background: var(--gray-25); }
.review-check strong, .review-check span { display: block; }
.review-check span { margin-top: 3px; color: var(--color-text-secondary); font-size: 12px; }
.review-check.error { background: var(--color-error-50); }
.review-check.warning { background: var(--color-warning-50); }
.evidence-list { display: flex; flex-direction: column; gap: 7px; max-height: 240px; overflow: auto; }
.evidence-list div { display: flex; justify-content: space-between; gap: 8px; padding: 7px 0; border-bottom: 1px solid var(--gray-100); }
.evidence-list span { color: var(--color-text-tertiary); font-size: 12px; }
.status-badge.passed { background: var(--color-success-50); color: var(--color-success-700); }
.status-badge.warning { background: var(--color-warning-50); color: var(--color-warning-900); }
.status-badge.blocked { background: var(--color-error-50); color: var(--color-error-700); }
.page-loading { min-height: 400px; display: flex; align-items: center; justify-content: center; gap: 10px; color: var(--color-text-secondary); }
.spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

@media (max-width: 900px) {
  .studio-header, .panel-heading { flex-direction: column; }
  .setup-grid, .brief-layout, .run-layout, .review-layout { grid-template-columns: 1fr; }
  .template-grid { grid-template-columns: 1fr 1fr; }
}

@media (max-width: 600px) {
  .content-studio-page { padding-top: 14px; }
  .stage-panel { padding: 16px; }
  .template-grid, .dynamic-form { grid-template-columns: 1fr; }
  .dynamic-form .field-block { grid-column: auto; }
  .header-actions, .stage-actions, .stage-actions.split, .editor-actions { width: 100%; flex-direction: column; }
  .visual-material-heading, .material-selector-title { flex-direction: column; }
  .material-selector-title small { text-align: left; }
  .gallery-folder-grid { grid-template-columns: 1fr 1fr; }
  .gallery-modal-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .gallery-modal-actions { grid-template-columns: 1fr 1fr; }
  .gallery-modal-actions > span { display: none; }
  .poster-choice-grid { grid-auto-columns: 124px; }
  .workflow-groups { padding: 12px; }
  .workflow-group summary { grid-template-columns: auto minmax(0, 1fr) auto; gap: 9px; padding: 11px; }
  .workflow-group-progress { display: none; }
  .workflow-group-copy small { white-space: normal; }
  .header-actions :deep(.ant-btn), .stage-actions :deep(.ant-btn), .editor-actions :deep(.ant-btn) { width: 100%; justify-content: center; }
}
</style>
