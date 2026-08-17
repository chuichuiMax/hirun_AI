<script setup>
import { onBeforeUnmount, reactive, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { Keyboard, MousePointer2, RefreshCw, X } from 'lucide-vue-next'
import { contentApi } from '@/apis/content_api'

const props = defineProps({
  open: { type: Boolean, default: false },
  account: { type: Object, default: null }
})
const emit = defineEmits(['update:open', 'updated'])

const loading = ref(false)
const acting = ref(false)
const claiming = ref(false)
const controlClaimed = ref(false)
const session = ref(null)
const screenshotUrl = ref('')
const inputText = ref('')
const key = ref('Enter')
const errorMessage = ref('')
const lastUpdatedAt = ref('')
const form = reactive({ delta_y: 650 })
let screenshotTimer = null
let heartbeatTimer = null
let pollingEpoch = 0
let actionSequence = 0

const revokeScreenshot = () => {
  if (screenshotUrl.value) URL.revokeObjectURL(screenshotUrl.value)
  screenshotUrl.value = ''
}

const stopPolling = () => {
  pollingEpoch += 1
  actionSequence += 1
  loading.value = false
  acting.value = false
  claiming.value = false
  if (screenshotTimer) window.clearTimeout(screenshotTimer)
  if (heartbeatTimer) window.clearTimeout(heartbeatTimer)
  screenshotTimer = null
  heartbeatTimer = null
}

const refreshScreenshot = async (epoch = pollingEpoch, accountId = props.account?.id) => {
  if (!props.open || !accountId || epoch !== pollingEpoch) return
  if (screenshotTimer) window.clearTimeout(screenshotTimer)
  screenshotTimer = null
  try {
    const response = await contentApi.getXiaohongshuBrowserScreenshot(accountId)
    const blob = await response.blob()
    if (epoch !== pollingEpoch || !props.open || props.account?.id !== accountId) return
    const nextUrl = URL.createObjectURL(blob)
    const previousUrl = screenshotUrl.value
    screenshotUrl.value = nextUrl
    lastUpdatedAt.value = new Date().toLocaleTimeString()
    if (previousUrl) URL.revokeObjectURL(previousUrl)
  } catch (error) {
    if (epoch === pollingEpoch && props.open && props.account?.id === accountId) {
      errorMessage.value = error.message || '远程浏览器画面暂不可用'
    }
  } finally {
    if (epoch === pollingEpoch && props.open && props.account?.id === accountId) {
      screenshotTimer = window.setTimeout(() => refreshScreenshot(epoch, accountId), 1500)
    }
  }
}

const heartbeat = async (epoch = pollingEpoch, accountId = props.account?.id) => {
  if (!props.open || !accountId || epoch !== pollingEpoch) return
  if (heartbeatTimer) window.clearTimeout(heartbeatTimer)
  heartbeatTimer = null
  try {
    const response = await contentApi.heartbeatXiaohongshuBrowserSession(accountId)
    if (epoch !== pollingEpoch || !props.open || props.account?.id !== accountId) return
    session.value = response
    controlClaimed.value = Boolean(response.control_claimed)
    emit('updated')
  } catch (error) {
    if (epoch === pollingEpoch && props.open && props.account?.id === accountId) {
      errorMessage.value = error.message || '远程浏览器心跳失败'
    }
  } finally {
    if (epoch === pollingEpoch && props.open && props.account?.id === accountId) {
      heartbeatTimer = window.setTimeout(() => heartbeat(epoch, accountId), 20000)
    }
  }
}

const loadStatus = async () => {
  if (!props.account?.id) return
  const accountId = props.account.id
  const epoch = pollingEpoch
  try {
    const response = await contentApi.getXiaohongshuBrowserSession(accountId)
    if (epoch !== pollingEpoch || !props.open || props.account?.id !== accountId) return
    session.value = response
  } catch (error) {
    if (epoch === pollingEpoch && props.open && props.account?.id === accountId) {
      errorMessage.value = error.message || '获取浏览器状态失败'
    }
  }
}

const start = async () => {
  stopPolling()
  revokeScreenshot()
  session.value = null
  controlClaimed.value = false
  errorMessage.value = ''
  if (!props.account?.id) return
  const accountId = props.account.id
  const epoch = pollingEpoch
  loading.value = true
  try {
    const response = await contentApi.openXiaohongshuBrowserSession(accountId)
    if (epoch !== pollingEpoch || !props.open || props.account?.id !== accountId) return
    session.value = response
    await refreshScreenshot(epoch, accountId)
    if (epoch === pollingEpoch && props.open && props.account?.id === accountId) {
      heartbeatTimer = window.setTimeout(() => heartbeat(epoch, accountId), 20000)
    }
    emit('updated')
  } catch (error) {
    if (epoch === pollingEpoch && props.open && props.account?.id === accountId) {
      errorMessage.value = error.message || '远程浏览器启动失败'
    }
  } finally {
    if (epoch === pollingEpoch) loading.value = false
  }
}

const sendAction = async (payload) => {
  if (!props.account?.id || acting.value || !controlClaimed.value) return
  const accountId = props.account.id
  const epoch = pollingEpoch
  const sequence = ++actionSequence
  acting.value = true
  try {
    const response = await contentApi.actXiaohongshuBrowserSession(accountId, payload)
    if (sequence !== actionSequence || epoch !== pollingEpoch || props.account?.id !== accountId) return
    session.value = response
    errorMessage.value = ''
    await refreshScreenshot(epoch, accountId)
  } catch (error) {
    if (sequence === actionSequence && epoch === pollingEpoch && props.account?.id === accountId) {
      errorMessage.value = error.message || '浏览器操作失败'
      message.error(errorMessage.value)
    }
  } finally {
    if (sequence === actionSequence) acting.value = false
  }
}

const clickScreen = (event) => {
  if (!controlClaimed.value) return
  const image = event.currentTarget
  const rect = image.getBoundingClientRect()
  if (!rect.width || !image.naturalWidth) return
  void sendAction({
    action: 'click',
    x: Math.round(((event.clientX - rect.left) / rect.width) * image.naturalWidth),
    y: Math.round(((event.clientY - rect.top) / rect.height) * image.naturalHeight)
  })
}

const typeText = () => {
  if (!inputText.value) return
  void sendAction({ action: 'type', text: inputText.value })
  inputText.value = ''
}

const pressKey = () => void sendAction({ action: 'keypress', key: key.value })
const scroll = () => void sendAction({ action: 'scroll', delta_y: form.delta_y })

const claimControl = async () => {
  if (!props.account?.id || claiming.value) return
  const accountId = props.account.id
  const epoch = pollingEpoch
  const sequence = ++actionSequence
  claiming.value = true
  try {
    await contentApi.claimXiaohongshuBrowserSession(accountId)
    if (sequence !== actionSequence || epoch !== pollingEpoch || props.account?.id !== accountId) return
    controlClaimed.value = true
    errorMessage.value = ''
    message.success('已启用人工接管，操作权限会在无活动后自动释放')
  } catch (error) {
    if (sequence === actionSequence && epoch === pollingEpoch && props.account?.id === accountId) {
      errorMessage.value = error.message || '启用人工接管失败'
    }
  } finally {
    if (sequence === actionSequence) claiming.value = false
  }
}

const closeSession = async () => {
  stopPolling()
  const accountId = session.value?.session?.account_id || props.account?.id
  if (accountId && session.value?.session) {
    try {
      await contentApi.closeXiaohongshuBrowserSession(accountId)
    } catch (error) {
      message.error(error.message || '关闭浏览器会话失败')
    }
  }
  revokeScreenshot()
  emit('update:open', false)
  emit('updated')
}

watch(
  [() => props.open, () => props.account?.id],
  ([open, accountId], [previousOpen, previousAccountId]) => {
    if (open && accountId && (!previousOpen || accountId !== previousAccountId)) void start()
    else {
      stopPolling()
      revokeScreenshot()
    }
  }
)
onBeforeUnmount(() => {
  stopPolling()
  revokeScreenshot()
})
</script>

<template>
  <a-drawer
    :open="open"
    width="min(920px, 100vw)"
    :closable="false"
    :mask-closable="false"
    @close="closeSession"
  >
    <template #title>
      <div class="browser-title"><span>远程运营浏览器</span><small>{{ account?.display_name }}</small></div>
    </template>

    <a-spin :spinning="loading">
      <div class="browser-layout">
        <div class="screen-panel">
          <div class="screen-toolbar">
            <span :class="['state-dot', session?.browser?.logged_in ? 'ready' : 'login']" />
            <span>{{ session?.browser?.logged_in ? '已登录' : '请在画面中完成登录' }}</span>
            <small v-if="lastUpdatedAt">画面更新于 {{ lastUpdatedAt }}</small>
            <a-button type="text" size="small" :loading="loading" @click="loadStatus"><RefreshCw :size="14" />状态</a-button>
          </div>
          <div v-if="screenshotUrl" class="screen-wrap" :class="{ claimed: controlClaimed }">
            <img :src="screenshotUrl" alt="小红书远程浏览器画面" @click="clickScreen" />
          </div>
          <div v-else class="screen-empty">{{ errorMessage || '正在获取浏览器画面…' }}</div>
          <p class="screen-tip">点击画面可操作服务器上的小红书页面；登录二维码也显示在此画面中。草稿会保存到这个账号的远程浏览器草稿箱。</p>
        </div>

        <div class="control-panel">
          <div class="control-heading"><MousePointer2 :size="17" />人工接管</div>
          <p>默认仅查看。明确启用接管后，才允许点击、输入和滚动；权限会在无活动后自动释放。</p>
          <a-button v-if="!controlClaimed" type="primary" :loading="claiming" @click="claimControl"><MousePointer2 :size="15" />启用人工接管</a-button>
          <a-alert v-else type="success" message="人工接管已启用" show-icon />
          <label>输入文本<a-input v-model:value="inputText" :disabled="!controlClaimed" placeholder="先点击画面中的输入框" @press-enter="typeText" /><a-button type="primary" :disabled="!controlClaimed" :loading="acting" @click="typeText">输入</a-button></label>
          <label>键盘按键<a-select v-model:value="key" :disabled="!controlClaimed" :options="['Enter', 'Escape', 'Tab', 'Backspace', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].map((value) => ({ label: value, value }))" /><a-button :disabled="!controlClaimed" @click="pressKey"><Keyboard :size="15" />发送</a-button></label>
          <label>滚动画面<a-input-number v-model:value="form.delta_y" :disabled="!controlClaimed" :min="-2000" :max="2000" :step="100" /><a-button :disabled="!controlClaimed" @click="scroll">滚动</a-button></label>
          <a-alert v-if="errorMessage" type="warning" :message="errorMessage" show-icon />
          <a-button danger block @click="closeSession"><X :size="15" />关闭远程浏览器</a-button>
        </div>
      </div>
    </a-spin>
  </a-drawer>
</template>

<style scoped lang="less">
.browser-title, .screen-toolbar, .control-heading, label { display: flex; align-items: center; gap: 8px; }
.browser-title { gap: 10px; font-weight: 600; }
.browser-title small, .screen-toolbar small, .control-panel p, .screen-tip { color: var(--color-text-secondary); font-size: 12px; font-weight: 400; }
.browser-layout { display: grid; grid-template-columns: minmax(0, 1fr) 230px; gap: 14px; }
.screen-panel, .control-panel { padding: 12px; border: 1px solid var(--gray-150); border-radius: 10px; background: var(--gray-0); }
.screen-toolbar { margin-bottom: 9px; font-size: 12px; }
.screen-toolbar small { margin-left: auto; }
.screen-toolbar :deep(.ant-btn) { display: inline-flex; align-items: center; gap: 4px; }
.state-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--color-warning-500); }
.state-dot.ready { background: var(--color-success-500); }
.screen-wrap { overflow: auto; max-height: calc(100vh - 190px); border-radius: 6px; background: #202124; cursor: default; }
.screen-wrap.claimed { cursor: crosshair; }
.screen-wrap img { display: block; width: 100%; height: auto; }
.screen-empty { min-height: 520px; display: grid; place-items: center; color: var(--color-text-secondary); }
.screen-tip { margin: 8px 0 0; line-height: 1.6; }
.control-panel { display: flex; flex-direction: column; gap: 12px; }
.control-heading { color: var(--main-700); font-weight: 600; }
.control-panel p { margin: 0; line-height: 1.6; }
.control-panel label { align-items: stretch; flex-direction: column; color: var(--color-text-secondary); font-size: 12px; }
.control-panel label :deep(.ant-btn) { display: inline-flex; align-items: center; justify-content: center; gap: 4px; }
.control-panel > :deep(.ant-btn) { display: inline-flex; align-items: center; justify-content: center; gap: 5px; margin-top: auto; }
@media (max-width: 760px) { .browser-layout { grid-template-columns: 1fr; } .control-panel { order: -1; } .screen-empty { min-height: 280px; } }
</style>
