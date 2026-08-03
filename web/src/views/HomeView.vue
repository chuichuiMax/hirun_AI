<template>
  <div class="home-container">
    <div v-if="isLoading" class="loading-container">
      <a-spin size="large" />
      <p class="loading-text">正在连接服务...</p>
    </div>

    <div v-else-if="error" class="error-container">
      <a-result status="error" :title="error.title" :sub-title="error.message">
        <template #extra>
          <a-button type="primary" @click="retryLoad">重试</a-button>
        </template>
      </a-result>
    </div>

    <template v-else>
      <div class="home-bottom-bg" aria-hidden="true">
        <img
          :src="footerBgUrl"
          alt=""
          class="home-bottom-bg__image"
        />
      </div>

      <div class="ambient" aria-hidden="true">
        <div class="hero-glow"></div>
        <div class="grid-mesh"></div>
      </div>

      <header class="top-header">
        <div class="logo">
          <img
            :src="logoUrl"
            :alt="infoStore.organization.name"
            class="logo-img"
          />
        </div>
        <nav class="top-nav">
          <button
            v-for="item in navItems"
            :key="item.label"
            type="button"
            class="nav-link"
            @click="goTo(item.path)"
          >
            {{ item.label }}
          </button>
        </nav>
        <div class="header-actions">
          <UserInfoComponent :show-button="true" />
        </div>
      </header>

      <main class="hero-section">
        <div class="hero-center reveal-up">
          <h1 class="title">
            <span class="title-prefix">{{ titleParts.prefix }}</span>
            <span v-if="titleParts.accent" class="title-accent">{{ titleParts.accent }}</span>
          </h1>
          <p class="subtitle">{{ infoStore.branding.subtitle }}</p>
          <button class="cta-button" @click="goToChat">
            开始体验
          </button>
        </div>

        <section class="feature-section reveal-up delay-1">
          <div class="feature-grid">
            <div
              v-for="feature in knowledgeDomains"
              :key="feature.label"
              class="feature-card"
            >
              <span class="feature-icon">
                <component :is="feature.icon" :size="32" stroke-width="1.5" />
              </span>
              <span class="feature-label">{{ feature.label }}</span>
              <span class="feature-desc">{{ feature.desc }}</span>
            </div>
          </div>
        </section>
      </main>

      <footer class="footer">
        <p class="copyright">
          {{ infoStore.footer?.copyright || '© 湖南博云东方粉末冶金有限公司' }}
        </p>
      </footer>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useInfoStore } from '@/stores/info'
import { healthApi } from '@/apis/system_api'
import UserInfoComponent from '@/components/UserInfoComponent.vue'
import { assetUrl } from '@/utils/assetUrl'
import {
  Factory,
  ShieldCheck,
  FlaskConical,
  Cog
} from 'lucide-vue-next'

const router = useRouter()
const userStore = useUserStore()
const infoStore = useInfoStore()

const footerBgUrl = assetUrl('/boyun-home-footer.jpg')
const logoUrl = computed(() => assetUrl(infoStore.organization.logo))

const isLoading = ref(true)
const error = ref(null)

const navItems = computed(() => [
  { label: '智能体', path: '/agent' },
  { label: '知识图谱', path: '/extensions' },
  { label: infoStore.kbMenuLabel, path: '/knowledge' },
  { label: '设置', path: '/dashboard' }
])

const knowledgeDomains = [
  { label: '生产', desc: '产线工艺与制造知识', icon: Factory },
  { label: '质量', desc: '检测标准与质控体系', icon: ShieldCheck },
  { label: '研发', desc: '材料创新与科研成果', icon: FlaskConical },
  { label: '工艺', desc: '加工参数与流程规范', icon: Cog }
]

const titleParts = computed(() => {
  const title = (infoStore.branding.title || '博云东方 AI粉末冶金智汇中心').trim()
  if (title.endsWith('智汇中心')) {
    return { prefix: title.slice(0, -4), accent: '智汇中心' }
  }
  if (title.endsWith('智汇平台')) {
    return { prefix: title.slice(0, -4), accent: '智汇平台' }
  }
  if (title.endsWith('智汇')) {
    return { prefix: title, accent: '平台' }
  }
  return { prefix: title, accent: '' }
})

const checkHealth = async () => {
  const response = await healthApi.checkHealth()
  if (response.status !== 'ok') {
    throw new Error('服务不可用')
  }
}

const loadData = async () => {
  isLoading.value = true
  error.value = null

  try {
    await checkHealth()
    await infoStore.loadInfoConfig()
  } catch (e) {
    console.error('加载失败:', e)
    error.value = {
      title: '服务连接失败',
      message: '后端服务无法响应，请检查服务是否正常运行'
    }
  } finally {
    isLoading.value = false
  }
}

const retryLoad = () => {
  loadData()
}

const ensureLogin = (redirectPath) => {
  if (!userStore.isLoggedIn) {
    sessionStorage.setItem('redirect', redirectPath)
    router.push('/login')
    return false
  }
  return true
}

const goTo = (path) => {
  if (!ensureLogin(path)) return
  router.push(path)
}

const goToChat = () => {
  goTo('/agent')
}

onMounted(() => {
  loadData()
})
</script>

<style lang="less" scoped>
.home-container {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  color: var(--gray-800);
  background: var(--main-0);
  position: relative;
  overflow-x: hidden;
}

.loading-container,
.error-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  gap: 1rem;
  position: relative;
  z-index: 2;

  .loading-text {
    color: var(--gray-600);
    font-size: 0.95rem;
  }
}

.ambient {
  position: absolute;
  inset: 0;
  z-index: 1;
  pointer-events: none;
  overflow: hidden;
}

.hero-glow {
  position: absolute;
  top: 18%;
  left: 50%;
  width: 720px;
  height: 420px;
  transform: translateX(-50%);
  background: radial-gradient(ellipse, rgba(35, 78, 160, 0.12) 0%, transparent 68%);
}

.grid-mesh {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(to right, rgba(35, 78, 160, 0.06) 1px, transparent 1px),
    linear-gradient(to bottom, rgba(35, 78, 160, 0.06) 1px, transparent 1px);
  background-size: 56px 56px;
  opacity: 0.45;
  mask-image: radial-gradient(ellipse 70% 55% at 50% 35%, #000, transparent 75%);
}

.top-header {
  position: relative;
  z-index: 10;
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  padding: 1.35rem 2.5rem 1.25rem;
  border-bottom: 1px solid var(--gray-200);
  background: rgba(255, 255, 255, 0.96);
}

.logo {
  justify-self: start;

  .logo-img {
    height: 2.4rem;
    width: auto;
    object-fit: contain;
  }
}

.top-nav {
  display: flex;
  align-items: center;
  gap: 2.5rem;
  justify-self: center;
}

.nav-link {
  border: none;
  background: transparent;
  padding: 0;
  font-size: 0.95rem;
  font-weight: 500;
  color: var(--gray-800);
  cursor: pointer;
  transition: color 0.2s ease;

  &:hover {
    color: var(--main-color);
  }
}

.header-actions {
  justify-self: end;
}

.hero-section {
  position: relative;
  z-index: 2;
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  padding: clamp(5rem, 14vh, 9rem) 2rem min(30vh, 240px);
  gap: clamp(3rem, 8vh, 5rem);
}

.hero-center {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  max-width: 820px;
  gap: 1.5rem;
}

.reveal-up {
  opacity: 0;
  transform: translateY(16px);
  animation: revealUp 0.7s cubic-bezier(0.22, 1, 0.36, 1) forwards;
}

.reveal-up.delay-1 {
  animation-delay: 140ms;
}

.title {
  margin: 0;
  font-family: 'Microsoft YaHei', '微软雅黑', sans-serif;
  font-size: clamp(2.4rem, 5vw, 3.6rem);
  font-weight: 700;
  line-height: 1.15;
  letter-spacing: -0.02em;
}

.title-prefix,
.title-accent {
  font-family: inherit;
  font-weight: 700;
}

.title-prefix {
  color: var(--main-900);
}

.title-accent {
  background: linear-gradient(90deg, var(--main-700), var(--main-500));
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.subtitle {
  margin: 0;
  max-width: 640px;
  font-size: 1.05rem;
  line-height: 1.8;
  color: var(--gray-600);
  font-weight: 400;
}

.cta-button {
  margin-top: 0.5rem;
  padding: 0.75rem 2.5rem;
  border: 1.5px solid var(--main-color);
  border-radius: 999px;
  font-size: 1.05rem;
  font-weight: 600;
  color: var(--main-color);
  cursor: pointer;
  background: transparent;
  box-shadow: none;
  transition:
    transform 0.2s ease,
    background 0.2s ease,
    border-color 0.2s ease,
    color 0.2s ease;

  &:hover {
    transform: translateY(-1px);
    background: var(--main-50);
    border-color: var(--main-700);
    color: var(--main-700);
  }
}

.feature-section {
  position: relative;
  z-index: 2;
  width: 100%;
  max-width: 1000px;
  margin: 0 auto;
  padding: 0 1rem;
}

.feature-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1.25rem;
  margin: 0 auto;
}

.home-bottom-bg {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: min(50vh, 420px);
  z-index: 0;
  pointer-events: none;
  overflow: hidden;
}

.home-bottom-bg__image {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center bottom;
  -webkit-mask-image: linear-gradient(to top, rgba(0, 0, 0, 1) 0%, rgba(0, 0, 0, 0.1) 100%);
  mask-image: linear-gradient(to top, rgba(0, 0, 0, 1) 0%, rgba(0, 0, 0, 0.1) 100%);
}

.feature-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  gap: 0.75rem;
  min-height: 168px;
  padding: 1.75rem 1rem;
  border-radius: 16px;
  background: var(--main-0);
  border: 1px solid var(--gray-200);
  box-shadow: 0 4px 20px -8px rgba(30, 50, 110, 0.1);
  transition:
    box-shadow 0.2s ease,
    transform 0.2s ease,
    border-color 0.2s ease;

  &:hover {
    border-color: rgba(35, 78, 160, 0.35);
    box-shadow: 0 8px 28px -10px rgba(35, 78, 160, 0.18);
    transform: translateY(-2px);
  }
}

.feature-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--main-color);
}

.feature-label {
  font-size: 0.92rem;
  font-weight: 600;
  color: var(--main-900);
  line-height: 1.4;
}

.feature-desc {
  font-size: 0.75rem;
  color: var(--gray-600);
  line-height: 1.45;
  max-width: 11rem;
}

.footer {
  position: relative;
  z-index: 2;
  padding: 1.25rem 2rem;
  text-align: center;
  border-top: none;
  background: transparent;
}

.copyright {
  margin: 0;
  font-size: 0.82rem;
  color: var(--gray-500);
}

@keyframes revealUp {
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (max-width: 900px) {
  .top-header {
    grid-template-columns: 1fr;
    justify-items: center;
    gap: 1rem;
    padding: 1rem 1.25rem;
  }

  .logo,
  .header-actions {
    justify-self: center;
  }

  .top-nav {
    flex-wrap: wrap;
    justify-content: center;
    gap: 1.25rem 2rem;
  }

  .feature-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .feature-section {
    max-width: none;
    padding: 0 1.25rem;
  }

  .hero-section {
    gap: 2.5rem;
    padding-top: clamp(3.5rem, 10vh, 6rem);
  }
}

@media (max-width: 520px) {
  .feature-grid {
    grid-template-columns: 1fr;
  }

  .cta-button {
    width: 100%;
    max-width: 280px;
  }
}
</style>
