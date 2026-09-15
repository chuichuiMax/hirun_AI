import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { imageDesignApi } from '@/apis/image_design_api'

export const useImageDesignStore = defineStore('imageDesign', () => {
  const bootstrap = ref(null)
  const clients = ref([])
  const materials = ref([])
  const jobs = ref([])
  const results = ref([])
  const activeJob = ref(null)
  const loading = ref(false)
  const image2Ready = computed(() => Boolean(bootstrap.value?.image2?.configured))

  async function loadBootstrap() {
    if (bootstrap.value) return bootstrap.value
    bootstrap.value = await imageDesignApi.getBootstrap()
    clients.value = bootstrap.value.clients || []
    return bootstrap.value
  }

  async function loadClients() {
    const response = await imageDesignApi.listClients()
    clients.value = response.clients || []
    return clients.value
  }

  async function createClient(name) {
    const response = await imageDesignApi.createClient({ name })
    clients.value = [...clients.value, response.client]
    return response.client
  }

  async function loadResults(clientId = null) {
    const response = await imageDesignApi.listResults(clientId)
    results.value = response.results || []
    return results.value
  }

  async function loadJobs(clientId = null) {
    const response = await imageDesignApi.listJobs(clientId)
    jobs.value = response.jobs || []
    return jobs.value
  }

  async function submit(payload) {
    loading.value = true
    try {
      const response = await imageDesignApi.generate(payload)
      activeJob.value = response.job
      const index = jobs.value.findIndex((item) => item.id === response.job.id)
      if (index >= 0) jobs.value.splice(index, 1, response.job)
      else jobs.value.unshift(response.job)
      return response.job
    } finally {
      loading.value = false
    }
  }

  async function poll(jobId) {
    const response = await imageDesignApi.getJob(jobId)
    activeJob.value = response.job
    const index = jobs.value.findIndex((item) => item.id === jobId)
    if (index >= 0) jobs.value.splice(index, 1, response.job)
    else jobs.value.unshift(response.job)
    return response.job
  }

  async function removeResult(assetId) {
    await imageDesignApi.deleteResult(assetId)
    results.value = results.value.filter((item) => item.id !== assetId)
  }

  return {
    bootstrap,
    clients,
    materials,
    jobs,
    results,
    activeJob,
    loading,
    image2Ready,
    loadBootstrap,
    loadClients,
    createClient,
    loadResults,
    loadJobs,
    submit,
    poll,
    removeResult
  }
})
