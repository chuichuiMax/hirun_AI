<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  ArrowLeft,
  BookOpenCheck,
  CheckCircle2,
  CircleAlert,
  Clock3,
  FileClock,
  History,
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
import { useContentStudioStore } from '@/stores/contentStudio'
import { useUserStore } from '@/stores/user'

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
const strategySelection = reactive({
  methods: [],
  scene_enhancer: 'S01',
  title_formula_code: '',
  content_formula_code: ''
})
const selectedAngleId = ref('')
const selectedTitleId = ref('')
const confirmedEvidenceIds = ref([])
const approvalNote = ref('')
const modelSpec = ref('')
const editor = reactive({ title: '', body: '', topics: [] })
const versionDrawerOpen = ref(false)
const ocrModalOpen = ref(false)
let draftSaveTimer = null

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
const methodOptions = computed(() =>
  (store.ruleBundle?.methods || []).filter((item) => item.method_type === 'core')
)
const titleFormulaOptions = computed(() => store.ruleBundle?.title_formulas || [])
const bodyFormulaOptions = computed(() => store.ruleBundle?.content_formulas || [])
const compatibilityClass = computed(() => {
  const value = store.strategy?.compatibility
  if (value === 'blocked') return 'blocked'
  if (value === 'warning') return 'warning'
  return 'compatible'
})
const titleOptions = computed(
  () => store.interrupt?.options || store.task?.title_candidates || []
)
const angleOptions = computed(() =>
  store.interrupt?.interrupt_type === 'select_content_angle' ? store.interrupt.options || [] : []
)
const nodeTimeline = computed(() => {
  const v1Labels = {
    compile_brief: '构建业务简报',
    plan_strategy: '规划创作策略',
    collect_evidence: '检索并冻结证据',
    confirm_facts: '确认关键事实',
    generate_titles: '生成标题候选',
    select_title: '人工选择标题',
    generate_body: '生成正文与话题',
    validate: '确定性校验',
    review: '内容质量审核',
    save: '保存内容版本'
  }
  const v2Labels = {
    compile_context: '编译运行上下文',
    ingest_materials: '导入真实素材',
    assemble_facts: '组装事实与证据',
    analyze_content_value: '分析内容价值',
    select_content_angle: '选择内容角度',
    match_strategy_v2: '匹配创作策略',
    resolve_formula_slots: '解析公式变量',
    collect_evidence: '检索并冻结证据',
    confirm_high_risk_facts: '确认高风险事实',
    generate_title_candidates: '生成标题候选',
    validate_title_candidates: '校验标题候选',
    select_title: '人工选择标题',
    build_content_outline: '构建内容大纲',
    generate_body_draft: '生成正文初稿',
    persona_style_polish: '调整人设语气',
    adapt_to_channel: '适配发布渠道',
    deterministic_validate: '执行确定性校验',
    semantic_review: '语义质量审核',
    human_approval: '人工审批',
    save_artifact_and_snapshots: '保存内容与快照'
  }
  const labels = Number(store.task?.runtime_config_snapshot?.schema_version || 1) >= 2
    ? v2Labels
    : v1Labels
  const byNode = new Map(store.runEvents.map((item) => [item.node_id, item]))
  return Object.entries(labels).map(([id, label]) => ({ id, label, status: byNode.get(id)?.status || 'pending' }))
})
const reviewChecks = computed(() => store.artifact?.review_snapshot?.checks || store.task?.review?.checks || [])
const canFinalize = computed(() => ['passed', 'warning'].includes(store.artifact?.review_snapshot?.status))
const runFailed = computed(() =>
  ['failed', 'cancelled'].includes(store.currentRun?.status) || store.task?.status === 'failed'
)
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
  if (task.current_stage === 'review') return 4
  if (task.current_stage === 'generation') return 3
  if (task.current_stage === 'strategy') return 2
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
    else if (field.type === 'tags' || field.type === 'knowledge') formValues[field.key] = []
    else formValues[field.key] = ''
  })
}

const syncStrategy = (strategy = store.strategy) => {
  strategySelection.methods = [...(strategy?.methods || [])]
  strategySelection.scene_enhancer = strategy?.scene_enhancer || 'S01'
  strategySelection.title_formula_code = strategy?.title_formula_code || ''
  strategySelection.content_formula_code = strategy?.content_formula_code || ''
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
    syncStrategy(task.strategy)
    syncEditor()
  },
  { deep: true }
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
  try {
    await store.loadBootstrap()
    if (taskId.value) {
      await store.loadTask(taskId.value)
      initializeFormValues()
      syncStrategy()
      syncEditor()
      if (
        store.task?.latest_run_id &&
        [
          'queued',
          'running',
          'planning_strategy',
          'collecting_evidence',
          'waiting_title',
          'waiting_human',
          'generating_body',
          'reviewing',
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
        !['brand_name', 'audience', 'persona', 'required_terms', 'forbidden_terms', 'knowledge_scope'].includes(key)
    )
  ),
  persona: formValues.persona ? { description: formValues.persona } : {},
  required_terms: formValues.required_terms || [],
  forbidden_terms: formValues.forbidden_terms || [],
  knowledge_scope: formValues.knowledge_scope || [],
  attachments: [],
  locked_fields: [],
  form_values: { ...formValues }
})

watch(
  formValues,
  () => {
    if (!store.task || stage.value !== 1) return
    window.clearTimeout(draftSaveTimer)
    draftSaveTimer = window.setTimeout(() => {
      store.saveBrief(buildBrief()).catch(() => {})
    }, 800)
  },
  { deep: true }
)

onBeforeUnmount(() => window.clearTimeout(draftSaveTimer))

const compileBrief = async () => {
  try {
    window.clearTimeout(draftSaveTimer)
    await store.compileBrief(buildBrief())
    stage.value = 2
    const strategy = await store.recommendStrategy()
    syncStrategy(strategy)
    message.success('业务简报已形成，系统已匹配创作策略')
  } catch (error) {
    message.error(error.message || '请补充必填业务信息')
  }
}

const refreshRecommendation = async () => {
  try {
    const strategy = await store.recommendStrategy()
    syncStrategy(strategy)
  } catch (error) {
    message.error(error.message || '策略匹配失败')
  }
}

const confirmStrategy = async () => {
  try {
    const response = await store.saveStrategy({ ...strategySelection })
    if (response.validation.compatibility === 'blocked') {
      message.error('当前组合不兼容，请根据提示调整')
      return
    }
    stage.value = 3
    message.success('创作策略已锁定')
  } catch (error) {
    message.error(error.message || '保存策略失败')
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
    if (store.interrupt?.interrupt_type === 'select_content_angle') {
      const selected = angleOptions.value.find((item) => item.id === selectedAngleId.value)
      if (!selected) {
        message.warning('请选择一个内容角度')
        return
      }
      await store.resumeRun({
        interrupt_type: 'select_content_angle',
        angle_id: selected.id,
        primary_narrative_axis: selected.primary_narrative_axis
      })
      return
    }
    if (store.interrupt?.interrupt_type === 'confirm_facts') {
      await store.resumeRun({
        interrupt_type: 'confirm_facts',
        confirmed_evidence_ids: confirmedEvidenceIds.value
      })
      return
    }
    if (!selectedTitleId.value) {
      message.warning('请选择一个标题')
      return
    }
    await store.resumeRun({
      interrupt_type: 'select_title',
      selected_candidate_id: selectedTitleId.value
    })
  } catch (error) {
    message.error(error.message || '恢复工作流失败')
  }
}

const submitHumanApproval = async (approved) => {
  try {
    await store.resumeRun({
      interrupt_type: 'human_approval',
      approved,
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
              <small>简化版由系统自动匹配公式；专业版可逐项确认策略。</small>
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
                  <a-select
                    v-else-if="field.type === 'knowledge'"
                    v-model:value="formValues[field.key]"
                    mode="multiple"
                    placeholder="选择本次允许检索的知识库"
                  >
                    <a-select-option v-for="kb in store.knowledgeOptions" :key="kb.id" :value="kb.id">
                      {{ kb.name }}
                    </a-select-option>
                  </a-select>
                </label>
              </div>
            </div>
            <aside class="facts-preview">
              <BookOpenCheck :size="22" />
              <h3>事实优先</h3>
              <p>提交后系统会形成 ContentBrief，并把人工输入标准化为带来源的 EvidenceBundle。</p>
              <ul>
                <li>数字和结果必须可验证</li>
                <li>知识库仅补充行业知识与案例</li>
                <li>规则组合不通过 RAG 判断</li>
              </ul>
            </aside>
          </div>
          <div class="stage-actions">
            <a-button type="primary" :loading="store.loading.saving" @click="compileBrief">
              形成事实简报并进入策略
            </a-button>
          </div>
        </template>
      </section>

      <section v-else-if="stage === 2" class="stage-panel">
        <div class="panel-heading">
          <div><span>阶段 2</span><h2>创作策略与组合校验</h2></div>
          <a-button :loading="store.loading.saving" @click="refreshRecommendation"><RefreshCw :size="15" />重新匹配</a-button>
        </div>

        <div class="strategy-grid">
          <div class="form-card">
            <label class="field-block">
              <span>核心创作手法</span>
              <a-select v-model:value="strategySelection.methods" mode="multiple" :disabled="isQuickMode">
                <a-select-option v-for="item in methodOptions" :key="item.code" :value="item.code">
                  {{ item.name }} · {{ item.principle }}
                </a-select-option>
              </a-select>
            </label>
            <label class="field-block">
              <span>标题公式</span>
              <a-select v-model:value="strategySelection.title_formula_code" :disabled="isQuickMode">
                <a-select-option v-for="item in titleFormulaOptions" :key="item.code" :value="item.code">
                  {{ item.code }} · {{ item.name }}
                </a-select-option>
              </a-select>
            </label>
            <label class="field-block">
              <span>正文公式</span>
              <a-select v-model:value="strategySelection.content_formula_code" :disabled="isQuickMode">
                <a-select-option v-for="item in bodyFormulaOptions" :key="item.code" :value="item.code">
                  {{ item.code }} · {{ item.name }}
                </a-select-option>
              </a-select>
            </label>
            <label class="field-check">
              <a-checkbox
                :checked="Boolean(strategySelection.scene_enhancer)"
                @change="strategySelection.scene_enhancer = $event.target.checked ? 'S01' : ''"
              >启用场景增强</a-checkbox>
            </label>
          </div>

          <aside class="compatibility-card" :class="compatibilityClass">
            <CheckCircle2 v-if="compatibilityClass === 'compatible'" :size="24" />
            <CircleAlert v-else :size="24" />
            <h3>{{ compatibilityClass === 'blocked' ? '组合被阻断' : compatibilityClass === 'warning' ? '组合可用但需注意' : '组合已匹配' }}</h3>
            <p>{{ store.strategy?.reason_summary || '系统会根据内容目标和规则矩阵给出组合原因。' }}</p>
            <ul v-if="store.strategy?.warnings?.length">
              <li v-for="warning in store.strategy.warnings" :key="warning">{{ warning }}</li>
            </ul>
            <div class="strategy-snapshot">
              <span>规则版本</span><code>{{ store.task?.rule_version_id }}</code>
              <span>证据条目</span><strong>{{ store.evidence?.items?.length || 0 }}</strong>
            </div>
          </aside>
        </div>

        <div class="stage-actions split">
          <a-button @click="stage = 1"><ArrowLeft :size="15" />返回素材</a-button>
          <a-button
            type="primary"
            :loading="store.loading.saving"
            :disabled="compatibilityClass === 'blocked'"
            @click="confirmStrategy"
          >锁定策略并进入生成</a-button>
        </div>
      </section>

      <section v-else-if="stage === 3" class="stage-panel">
        <div class="panel-heading">
          <div><span>阶段 3</span><h2>内容生成与人工选择</h2></div>
          <span v-if="store.currentRun" class="run-id">Run {{ store.currentRun.run_id }}</span>
        </div>

        <div v-if="!store.currentRun && !store.interrupt" class="generation-start">
          <Sparkles :size="30" />
          <h3>策略和证据已锁定</h3>
          <p>工作流会依次执行策略、证据、标题、正文和审核节点，并在标题候选处暂停。</p>
          <a-input v-if="!isQuickMode" v-model:value="modelSpec" placeholder="可选：指定模型 spec；留空使用系统默认模型" />
          <a-button type="primary" size="large" @click="startGeneration"><Play :size="17" />开始生成</a-button>
        </div>

        <div v-else class="run-layout">
          <div class="run-timeline">
            <div v-for="node in nodeTimeline" :key="node.id" class="run-node" :class="node.status">
              <LoaderCircle v-if="node.status === 'running'" class="spin" :size="17" />
              <CheckCircle2 v-else-if="node.status === 'completed'" :size="17" />
              <CircleAlert v-else-if="node.status === 'failed'" :size="17" />
              <Clock3 v-else :size="17" />
              <span>{{ node.label }}</span>
            </div>
          </div>

          <div v-if="store.interrupt?.interrupt_type === 'select_content_angle'" class="human-review-card">
            <div class="human-heading"><Sparkles :size="20" /><div><h3>选择本次内容角度</h3><p>系统已根据目标、事实和证据生成可执行方向，选择后将继续匹配公式。</p></div></div>
            <a-radio-group v-model:value="selectedAngleId" class="title-options angle-options">
              <a-radio v-for="item in angleOptions" :key="item.id" :value="item.id">
                <strong>{{ item.value_proposition }}</strong>
                <span>{{ item.recommendation_reason }}</span>
                <small v-if="item.target_audience?.length">目标人群：{{ item.target_audience.join('、') }}</small>
              </a-radio>
            </a-radio-group>
            <a-button type="primary" :disabled="!selectedAngleId" @click="submitHumanReview">确认角度并继续</a-button>
          </div>

          <div v-else-if="store.interrupt?.interrupt_type === 'select_title'" class="human-review-card">
            <div class="human-heading"><Send :size="20" /><div><h3>请选择最终标题</h3><p>选择后 LangGraph 从 checkpoint 恢复，无需重新检索证据。</p></div></div>
            <a-radio-group v-model:value="selectedTitleId" class="title-options">
              <a-radio v-for="item in titleOptions" :key="item.id" :value="item.id">
                <strong>{{ item.text }}</strong>
                <span>{{ item.formula_code }} · 引用 {{ item.evidence_ids?.length || 0 }} 条证据</span>
              </a-radio>
            </a-radio-group>
            <a-button type="primary" @click="submitHumanReview">确认标题并继续生成</a-button>
          </div>

          <div v-else-if="store.interrupt?.interrupt_type === 'confirm_facts'" class="human-review-card">
            <div class="human-heading"><ShieldCheck :size="20" /><div><h3>确认关键事实</h3><p>价格、效果或高风险表达必须确认后才能用于生成。</p></div></div>
            <a-checkbox-group v-model:value="confirmedEvidenceIds" class="fact-options">
              <a-checkbox v-for="item in store.interrupt.options" :key="item.id" :value="item.id">
                {{ item.key }}：{{ item.value }}
              </a-checkbox>
            </a-checkbox-group>
            <a-button type="primary" @click="submitHumanReview">确认选中事实并继续</a-button>
          </div>

          <div v-else-if="store.interrupt?.interrupt_type === 'human_approval'" class="human-review-card">
            <div class="human-heading"><ShieldCheck :size="20" /><div><h3>最终人工审批</h3><p>请根据审核结果确认是否允许保存内容资产。</p></div></div>
            <div v-if="store.interrupt.review?.checks?.length" class="approval-checks">
              <div v-for="check in store.interrupt.review.checks" :key="`${check.code}-${check.message}`">
                <strong>{{ check.message }}</strong>
                <span v-if="check.suggestion">{{ check.suggestion }}</span>
              </div>
            </div>
            <a-textarea v-model:value="approvalNote" :rows="3" placeholder="可选：填写审批备注" />
            <div class="approval-actions">
              <a-button danger @click="submitHumanApproval(false)">驳回</a-button>
              <a-button type="primary" @click="submitHumanApproval(true)">通过并继续</a-button>
            </div>
          </div>

          <div v-else-if="runFailed" class="running-card failure-card">
            <CircleAlert :size="26" />
            <h3>工作流执行失败</h3>
            <p>{{ store.task?.error?.message || store.lastError?.message || '已保留完成节点和 checkpoint，可从失败节点恢复。' }}</p>
            <a-button type="primary" @click="retryFailedRun"><RefreshCw :size="15" />从失败节点重试</a-button>
          </div>

          <div v-else-if="store.interrupt" class="running-card failure-card">
            <CircleAlert :size="26" />
            <h3>遇到未支持的人工节点</h3>
            <p>节点类型：{{ store.interrupt.interrupt_type || '未知' }}。请联系管理员检查工作流版本。</p>
          </div>

          <div v-else class="running-card">
            <LoaderCircle class="spin" :size="26" />
            <h3>工作流正在执行</h3>
            <p>可以离开页面，任务状态与节点结果会持续保存。</p>
          </div>
        </div>
      </section>

      <section v-else class="stage-panel">
        <div class="panel-heading">
          <div><span>阶段 4</span><h2>审核、编辑与正式版本</h2></div>
          <div class="status-badge" :class="store.artifact?.review_snapshot?.status || 'pending'">
            {{ store.artifact?.review_snapshot?.status || '待审核' }}
          </div>
        </div>

        <div v-if="store.artifact" class="review-layout">
          <div class="content-editor-card">
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

.setup-grid, .brief-layout, .strategy-grid, .run-layout, .review-layout { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(280px, 0.8fr); gap: 20px; }
.setup-grid { grid-template-columns: 1fr 1fr; margin-bottom: 20px; }
.template-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.template-card { min-height: 116px; padding: 16px; display: flex; flex-direction: column; gap: 7px; text-align: left; border: 1px solid var(--gray-150); border-radius: 8px; background: var(--gray-0); color: var(--color-text); cursor: pointer; }
.template-card:hover { border-color: var(--main-300); background: var(--main-10); }
.template-card.selected { border-color: var(--main-color); background: var(--main-30); }
.template-card strong { font-size: 15px; }
.template-card span, .template-card small { color: var(--color-text-secondary); }

.form-card, .facts-preview, .compatibility-card, .run-timeline, .human-review-card, .running-card, .content-editor-card, .review-sidebar { border: 1px solid var(--gray-150); border-radius: 8px; padding: 20px; background: var(--gray-0); }
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
.stage-actions { margin-top: 22px; display: flex; justify-content: flex-end; gap: 10px; }
.stage-actions.split { justify-content: space-between; }

.compatibility-card.compatible { background: var(--color-success-10); border-color: var(--color-success-100); }
.compatibility-card.warning { background: var(--color-warning-10); border-color: var(--color-warning-100); }
.compatibility-card.blocked { background: var(--color-error-10); border-color: var(--color-error-100); }
.compatibility-card h3 { margin: 10px 0 6px; }
.compatibility-card p, .compatibility-card li { color: var(--color-text-secondary); }
.strategy-snapshot { display: grid; grid-template-columns: auto 1fr; gap: 8px 12px; margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--gray-150); }
.strategy-snapshot span { color: var(--color-text-secondary); }
.strategy-snapshot code { overflow-wrap: anywhere; }
.field-check { color: var(--color-text-secondary); }

.generation-start { max-width: 560px; margin: 50px auto; display: flex; flex-direction: column; align-items: center; gap: 12px; text-align: center; }
.generation-start h3, .generation-start p { margin: 0; }
.generation-start p { color: var(--color-text-secondary); }
.generation-start :deep(.ant-input) { max-width: 500px; }
.run-id { max-width: 360px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--color-text-tertiary) !important; }
.run-timeline { display: flex; flex-direction: column; gap: 3px; }
.run-node { min-height: 40px; display: flex; align-items: center; gap: 10px; padding: 8px 10px; color: var(--color-text-tertiary); border-radius: 6px; }
.run-node.running { background: var(--color-info-50); color: var(--color-info-700); }
.run-node.completed { color: var(--color-success-700); }
.run-node.failed { background: var(--color-error-50); color: var(--color-error-700); }
.human-review-card, .running-card { align-self: start; }
.failure-card { color: var(--color-error-700); background: var(--color-error-50); }
.human-heading { display: flex; gap: 10px; margin-bottom: 16px; }
.human-heading h3, .human-heading p { margin: 0; }
.human-heading p { margin-top: 3px; color: var(--color-text-secondary); }
.title-options, .fact-options { width: 100%; display: flex; flex-direction: column; gap: 9px; margin-bottom: 16px; }
.title-options :deep(.ant-radio-wrapper), .fact-options :deep(.ant-checkbox-wrapper) { width: 100%; margin-inline-start: 0; padding: 12px; border: 1px solid var(--gray-150); border-radius: 6px; align-items: flex-start; }
.angle-options :deep(.ant-radio-wrapper-checked) { border-color: var(--main-color); background: var(--main-30); }
.angle-options strong, .angle-options span, .angle-options small { display: block; }
.angle-options span, .angle-options small { margin-top: 4px; color: var(--color-text-secondary); font-size: 12px; line-height: 1.5; }
.approval-checks { display: flex; flex-direction: column; gap: 8px; margin-bottom: 14px; }
.approval-checks > div { padding: 10px 12px; border-radius: 6px; background: var(--color-warning-50); color: var(--color-warning-900); }
.approval-checks strong, .approval-checks span { display: block; font-size: 12px; }
.approval-checks span { margin-top: 3px; opacity: 0.82; }
.approval-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 14px; }
.title-options strong, .title-options span { display: block; }
.title-options span { margin-top: 3px; color: var(--color-text-tertiary); font-size: 12px; }
.running-card { display: flex; flex-direction: column; align-items: center; text-align: center; }

.content-editor-card textarea { resize: vertical; }
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
  .setup-grid, .brief-layout, .strategy-grid, .run-layout, .review-layout { grid-template-columns: 1fr; }
  .template-grid { grid-template-columns: 1fr 1fr; }
}

@media (max-width: 600px) {
  .content-studio-page { padding-top: 14px; }
  .stage-panel { padding: 16px; }
  .template-grid, .dynamic-form { grid-template-columns: 1fr; }
  .dynamic-form .field-block { grid-column: auto; }
  .header-actions, .stage-actions, .stage-actions.split, .editor-actions { width: 100%; flex-direction: column; }
  .header-actions :deep(.ant-btn), .stage-actions :deep(.ant-btn), .editor-actions :deep(.ant-btn) { width: 100%; justify-content: center; }
}
</style>
