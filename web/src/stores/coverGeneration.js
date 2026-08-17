import { computed, reactive, ref } from 'vue'
import { defineStore } from 'pinia'
import { contentApi } from '@/apis/content_api'

const terminalStatuses = new Set(['succeeded', 'failed', 'cancelled'])

const createRequestId = () => {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID()
  return `cover-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

const parseSse = async (response, onEvent) => {
  if (!response?.body) return
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let eventType = 'message'
  let eventId = null
  let dataLines = []
  const dispatch = async () => {
    if (!dataLines.length) return
    try {
      await onEvent(eventType, JSON.parse(dataLines.join('\n')), eventId)
    } catch (error) {
      console.warn('封面任务事件解析失败', error)
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
        await dispatch()
        eventType = 'message'
        eventId = null
        dataLines = []
      } else if (line.startsWith('event:')) eventType = line.slice(6).trim() || 'message'
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
      else if (line.startsWith('id:')) eventId = line.slice(3).trim()
    }
  }
  await dispatch()
}

export const useCoverGenerationStore = defineStore('coverGeneration', () => {
  const bootstrap = ref(null)
  const currentJob = ref(null)
  const jobs = ref([])
  const resultUrls = ref([])
  const lastError = ref(null)
  const loading = reactive({ bootstrap: false, upload: false, submit: false, history: false })
  let streamController = null
  let lastSeq = '0-0'

  const isRunning = computed(() => currentJob.value && !terminalStatuses.has(currentJob.value.status))

  function releaseResultUrls() {
    resultUrls.value.forEach((item) => URL.revokeObjectURL(item.url))
    resultUrls.value = []
  }

  async function loadBootstrap(force = false) {
    if (bootstrap.value && !force) return bootstrap.value
    loading.bootstrap = true
    try {
      bootstrap.value = await contentApi.getCoverBootstrap()
      return bootstrap.value
    } finally {
      loading.bootstrap = false
    }
  }

  async function upload(files, role, contentTaskId) {
    loading.upload = true
    const uploaded = []
    try {
      for (const file of Array.from(files)) {
        const response = await contentApi.uploadCoverAsset(file, role, contentTaskId)
        uploaded.push({ ...response.asset, localName: file.name })
      }
      return uploaded
    } catch (error) {
      await Promise.allSettled(uploaded.map((asset) => contentApi.deleteCoverAsset(asset.id)))
      throw error
    } finally {
      loading.upload = false
    }
  }

  async function deleteAsset(assetId) {
    return contentApi.deleteCoverAsset(assetId)
  }

  async function loadResults(job) {
    releaseResultUrls()
    if (job?.status !== 'succeeded') return
    const nextResults = []
    try {
      for (const asset of job.result_assets || []) {
        const response = await contentApi.getCoverAssetFile(asset.id)
        const blob = await response.blob()
        nextResults.push({ id: asset.id, url: URL.createObjectURL(blob), blob })
      }
      resultUrls.value = nextResults
    } catch (error) {
      nextResults.forEach((item) => URL.revokeObjectURL(item.url))
      throw error
    }
  }

  async function refreshJob(jobId) {
    const response = await contentApi.getCoverJob(jobId)
    currentJob.value = response.job
    if (terminalStatuses.has(response.job.status)) await loadResults(response.job)
    return response.job
  }

  async function subscribe(jobId) {
    streamController?.abort()
    const controller = new AbortController()
    streamController = controller
    lastSeq = '0-0'
    while (!controller.signal.aborted) {
      try {
        const response = await contentApi.streamCoverJobEvents(jobId, lastSeq, {
          signal: controller.signal,
          headers: lastSeq === '0-0' ? {} : { 'Last-Event-ID': lastSeq }
        })
        await parseSse(response, async (eventType, envelope, eventId) => {
          if (eventId) lastSeq = eventId
          const payload = envelope?.payload || envelope || {}
          if (eventType === 'progress' && currentJob.value?.id === jobId) {
            currentJob.value = {
              ...currentJob.value,
              status: payload.status || currentJob.value.status,
              progress: payload.progress ?? currentJob.value.progress
            }
          }
          if (eventType === 'end') {
            if (currentJob.value?.id === jobId) await refreshJob(jobId)
            await loadHistory(currentJob.value?.content_task_id || null)
          }
        })
      } catch (error) {
        if (error.name === 'AbortError') return
        lastError.value = error
      }
      if (controller.signal.aborted) return
      const job = await refreshJob(jobId)
      if (terminalStatuses.has(job.status)) {
        await loadHistory(job.content_task_id || null)
        return
      }
      await new Promise((resolve) => setTimeout(resolve, 1500))
    }
  }

  function startSubscription(jobId) {
    void subscribe(jobId).catch((error) => {
      lastError.value = error
    })
  }

  async function submit(kind, payload) {
    loading.submit = true
    lastError.value = null
    releaseResultUrls()
    try {
      const response = kind === 'compose'
        ? await contentApi.composeCover({ ...payload, idempotency_key: createRequestId() })
        : await contentApi.generateCover({ ...payload, idempotency_key: createRequestId() })
      currentJob.value = response.job
      startSubscription(response.job.id)
      return response.job
    } catch (error) {
      lastError.value = error
      throw error
    } finally {
      loading.submit = false
    }
  }

  async function loadHistory(contentTaskId = null) {
    loading.history = true
    try {
      const response = await contentApi.listCoverJobs({ content_task_id: contentTaskId, page_size: 30 })
      jobs.value = response.items || []
      return jobs.value
    } finally {
      loading.history = false
    }
  }

  async function restore(jobId) {
    streamController?.abort()
    const job = await refreshJob(jobId)
    if (!terminalStatuses.has(job.status)) startSubscription(job.id)
    return job
  }

  async function cancel() {
    if (!currentJob.value) return
    const response = await contentApi.cancelCoverJob(currentJob.value.id)
    currentJob.value = response.job
  }

  async function retry(job) {
    const response = await contentApi.retryCoverJob(job.id, { idempotency_key: createRequestId() })
    currentJob.value = response.job
    releaseResultUrls()
    startSubscription(response.job.id)
    return response.job
  }

  async function setCurrent(assetId = null) {
    if (!currentJob.value) return null
    return contentApi.setCurrentCover(currentJob.value.id, assetId)
  }

  function clearCurrent() {
    streamController?.abort()
    currentJob.value = null
    lastError.value = null
    releaseResultUrls()
  }

  function dispose() {
    streamController?.abort()
    releaseResultUrls()
  }

  return {
    bootstrap,
    currentJob,
    jobs,
    resultUrls,
    lastError,
    loading,
    isRunning,
    loadBootstrap,
    upload,
    deleteAsset,
    submit,
    loadHistory,
    restore,
    cancel,
    retry,
    setCurrent,
    clearCurrent,
    dispose
  }
})
