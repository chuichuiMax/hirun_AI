import { computed, reactive, ref } from 'vue'
import { defineStore } from 'pinia'
import { contentApi } from '@/apis/content_api'

const parseSse = async (response, onEvent) => {
  if (!response?.body) return
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let eventType = 'message'
  let eventId = null
  let dataLines = []

  const dispatch = () => {
    if (!dataLines.length) return
    try {
      onEvent(eventType, JSON.parse(dataLines.join('\n')), eventId)
    } catch (error) {
      console.warn('内容运行事件解析失败', error)
    }
  }

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const raw of lines) {
      const line = raw.replace(/\r$/, '')
      if (!line) {
        dispatch()
        eventType = 'message'
        eventId = null
        dataLines = []
      } else if (line.startsWith('event:')) {
        eventType = line.slice(6).trim() || 'message'
      } else if (line.startsWith('data:')) {
        dataLines.push(line.slice(5).trimStart())
      } else if (line.startsWith('id:')) {
        eventId = line.slice(3).trim()
      }
    }
  }
  dispatch()
}

export const useContentStudioStore = defineStore('contentStudio', () => {
  const bootstrap = ref(null)
  const task = ref(null)
  const template = ref(null)
  const artifact = ref(null)
  const currentRun = ref(null)
  const interrupt = ref(null)
  const runEvents = ref([])
  const history = ref([])
  const historyTotal = ref(0)
  const versions = ref([])
  const saveStatus = ref('idle')
  const loading = reactive({
    bootstrap: false,
    task: false,
    saving: false,
    running: false,
    reviewing: false,
    history: false
  })
  const lastError = ref(null)
  let runAbortController = null
  let lastRunSeq = '0-0'

  const ruleBundle = computed(() => bootstrap.value?.rule_bundle || null)
  const templates = computed(() => bootstrap.value?.industry_templates || [])
  const contentGoals = computed(() => bootstrap.value?.content_goals || [])
  const knowledgeOptions = computed(() => bootstrap.value?.knowledge_options || [])
  const strategy = computed(() => task.value?.strategy || {})
  const evidence = computed(() => task.value?.evidence_bundle || { items: [] })

  async function loadBootstrap(force = false) {
    if (bootstrap.value && !force) return bootstrap.value
    loading.bootstrap = true
    try {
      bootstrap.value = await contentApi.getBootstrap()
      return bootstrap.value
    } finally {
      loading.bootstrap = false
    }
  }

  async function createTask(payload) {
    loading.saving = true
    try {
      const response = await contentApi.createTask(payload)
      task.value = response.task
      await loadTask(response.task.id)
      return task.value
    } finally {
      loading.saving = false
    }
  }

  async function loadTask(taskId) {
    if (!taskId) return null
    loading.task = true
    lastError.value = null
    try {
      const response = await contentApi.getTask(taskId)
      task.value = response.task
      template.value = response.template
      artifact.value = response.artifact
      return response
    } catch (error) {
      lastError.value = error
      throw error
    } finally {
      loading.task = false
    }
  }

  async function compileBrief(brief) {
    loading.saving = true
    try {
      const response = await contentApi.compileBrief(task.value.id, brief)
      task.value = response.task
      saveStatus.value = 'saved'
      return response
    } finally {
      loading.saving = false
    }
  }

  async function saveBrief(brief) {
    if (!task.value?.id) return null
    saveStatus.value = 'saving'
    try {
      const response = await contentApi.saveBrief(task.value.id, brief)
      saveStatus.value = 'saved'
      return response
    } catch (error) {
      saveStatus.value = 'error'
      throw error
    }
  }

  async function recommendStrategy() {
    loading.saving = true
    try {
      const response = await contentApi.recommendStrategy(task.value.id)
      task.value = response.task
      return response.strategy
    } finally {
      loading.saving = false
    }
  }

  async function saveStrategy(selection) {
    loading.saving = true
    try {
      const response = await contentApi.saveStrategy(task.value.id, selection)
      task.value = response.task
      return response
    } finally {
      loading.saving = false
    }
  }

  function handleRunEvent(eventType, envelope, eventId) {
    if (eventId) lastRunSeq = eventId
    const payload = envelope?.payload || envelope || {}
    if (eventType === 'custom' && payload.name === 'content.node') {
      const existing = runEvents.value.find(
        (item) => item.node_id === payload.node_id && item.run_id === envelope.run_id
      )
      if (existing) Object.assign(existing, payload)
      else runEvents.value.push({ ...payload, run_id: envelope.run_id })
    } else if (eventType === 'interrupt') {
      interrupt.value = payload
    } else if (eventType === 'error') {
      lastError.value = new Error(payload.message || '内容运行失败')
    }
  }

  async function subscribeRun(runId) {
    runAbortController?.abort()
    runAbortController = new AbortController()
    loading.running = true
    try {
      const response = await contentApi.streamRunEvents(runId, lastRunSeq, {
        signal: runAbortController.signal
      })
      if (!response.ok) throw new Error(`运行事件连接失败：${response.status}`)
      await parseSse(response, (eventType, data, eventId) => {
        handleRunEvent(eventType, data, eventId)
        if (eventType === 'end') {
          currentRun.value = { ...(currentRun.value || {}), status: data?.payload?.status }
        }
      })
      await loadTask(task.value.id)
    } catch (error) {
      if (error.name !== 'AbortError') {
        lastError.value = error
        throw error
      }
    } finally {
      loading.running = false
    }
  }

  async function startRun(modelSpec = null) {
    interrupt.value = null
    runEvents.value = []
    lastRunSeq = '0-0'
    const response = await contentApi.createRun(task.value.id, {
      request_id: crypto.randomUUID(),
      model_spec: modelSpec || null
    })
    currentRun.value = response
    void subscribeRun(response.run_id)
    return response
  }

  async function resumeRun(resume) {
    if (!currentRun.value?.run_id) return
    interrupt.value = null
    const response = await contentApi.resumeRun(currentRun.value.run_id, {
      request_id: crypto.randomUUID(),
      resume
    })
    currentRun.value = response
    lastRunSeq = '0-0'
    void subscribeRun(response.run_id)
    return response
  }

  async function recoverRun(runId) {
    if (!runId) return
    const response = await contentApi.getRun(runId)
    currentRun.value = {
      run_id: response.run.id,
      status: response.run.status,
      request_id: response.run.request_id
    }
    lastRunSeq = '0-0'
    await subscribeRun(runId)
  }

  async function retryNode(nodeId, modelSpec = null) {
    if (!currentRun.value?.run_id) return
    const response = await contentApi.retryNode(currentRun.value.run_id, {
      request_id: crypto.randomUUID(),
      node_id: nodeId,
      model_spec: modelSpec || null
    })
    currentRun.value = response
    runEvents.value = []
    lastRunSeq = '0-0'
    void subscribeRun(response.run_id)
    return response
  }

  async function saveArtifact(payload) {
    const response = await contentApi.updateArtifact(artifact.value.id, payload)
    artifact.value = response.artifact
    await loadTask(task.value.id)
    return artifact.value
  }

  async function reviewArtifact(modelSpec = null) {
    loading.reviewing = true
    try {
      const response = await contentApi.reviewArtifact(artifact.value.id, {
        model_spec: modelSpec || null
      })
      artifact.value = response.artifact
      task.value.review = response.review
      return response.review
    } finally {
      loading.reviewing = false
    }
  }

  async function finalizeArtifact() {
    const response = await contentApi.finalizeArtifact(artifact.value.id, {})
    artifact.value = response.artifact
    task.value = response.task
    return response
  }

  async function loadVersions() {
    if (!artifact.value?.id) return []
    const response = await contentApi.listArtifactVersions(artifact.value.id)
    versions.value = response.items || []
    return versions.value
  }

  async function loadHistory(params = {}) {
    loading.history = true
    try {
      const response = await contentApi.listTasks(params)
      history.value = response.items || []
      historyTotal.value = response.total || 0
      return response
    } finally {
      loading.history = false
    }
  }

  function resetCurrentTask() {
    runAbortController?.abort()
    task.value = null
    template.value = null
    artifact.value = null
    currentRun.value = null
    interrupt.value = null
    runEvents.value = []
    lastError.value = null
    versions.value = []
    saveStatus.value = 'idle'
  }

  return {
    bootstrap,
    task,
    template,
    artifact,
    currentRun,
    interrupt,
    runEvents,
    history,
    historyTotal,
    versions,
    saveStatus,
    loading,
    lastError,
    ruleBundle,
    templates,
    contentGoals,
    knowledgeOptions,
    strategy,
    evidence,
    loadBootstrap,
    createTask,
    loadTask,
    compileBrief,
    saveBrief,
    recommendStrategy,
    saveStrategy,
    startRun,
    resumeRun,
    recoverRun,
    retryNode,
    saveArtifact,
    reviewArtifact,
    finalizeArtifact,
    loadVersions,
    loadHistory,
    resetCurrentTask
  }
})
