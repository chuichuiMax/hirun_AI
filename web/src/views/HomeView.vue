<template>
  <div class="home-page">
    <div v-if="isLoading" class="page-state">
      <a-spin size="large" />
      <p>正在连接内容生产平台...</p>
    </div>

    <div v-else-if="error" class="page-state">
      <a-result status="error" :title="error.title" :sub-title="error.message">
        <template #extra>
          <a-button type="primary" @click="loadData">重试</a-button>
        </template>
      </a-result>
    </div>

    <template v-else>
      <header class="site-header">
        <button class="brand" type="button" aria-label="ContentFlow 首页" @click="router.push('/')">
          <img src="/contentflow-logo.svg" alt="ContentFlow" />
          <span>内容生产平台</span>
        </button>

        <nav class="site-nav" aria-label="主要导航">
          <button v-for="item in navItems" :key="item.label" type="button" @click="goTo(item.path)">
            {{ item.label }}
          </button>
        </nav>

        <div class="header-actions">
          <button
            v-if="!userStore.isLoggedIn"
            class="login-link"
            type="button"
            @click="router.push('/login')"
          >
            登录
          </button>
          <UserInfoComponent v-else />
          <button class="header-cta" type="button" @click="goTo('/content/new')">
            开始创作
            <ArrowUpRight :size="16" />
          </button>
        </div>
      </header>

      <main>
        <section class="hero">
          <div class="hero-copy">
            <div class="eyebrow"><Sparkles :size="15" /> 企业级 AI 内容生产工作台</div>
            <h1>
              把企业真实业务，变成
              <span>持续增长的好内容</span>
            </h1>
            <p class="hero-description">
              用结构化创作规则、企业知识库和可控 AI
              工作流，稳定完成从业务素材、策略匹配到生成审核的全过程。
            </p>
            <div class="hero-actions">
              <button class="primary-cta" type="button" @click="goTo('/content/new')">
                创建第一篇内容
                <ArrowRight :size="18" />
              </button>
              <button class="secondary-cta" type="button" @click="goTo('/content/history')">
                <History :size="18" />
                查看生产历史
              </button>
            </div>
            <ul class="hero-trust" aria-label="平台保障">
              <li><CircleCheck :size="16" /> 规则可配置</li>
              <li><CircleCheck :size="16" /> 关键节点可审核</li>
              <li><CircleCheck :size="16" /> 全过程可追溯</li>
            </ul>
          </div>

          <div class="studio-preview" aria-label="内容生产工作流预览">
            <div class="preview-header">
              <div>
                <span class="preview-kicker">CONTENT WORKFLOW</span>
                <h2>本周内容生产</h2>
              </div>
              <span class="running-status"><span></span>工作流运行中</span>
            </div>

            <div class="preview-progress">
              <div class="progress-summary">
                <strong>12</strong>
                <span>篇内容进入生产流程</span>
              </div>
              <div class="progress-bar"><span></span></div>
              <div class="progress-meta"><span>已完成 8 篇</span><span>67%</span></div>
            </div>

            <div class="workflow-list">
              <div v-for="(step, index) in workflowSteps" :key="step.title" class="workflow-step">
                <span class="step-number" :class="step.state">{{ index + 1 }}</span>
                <div>
                  <strong>{{ step.title }}</strong>
                  <p>{{ step.desc }}</p>
                </div>
                <span class="step-state" :class="step.state">{{ step.label }}</span>
              </div>
            </div>

            <div class="evidence-card">
              <div class="evidence-icon"><ShieldCheck :size="19" /></div>
              <div><strong>事实与证据已锁定</strong><span>6 条企业资料 · 3 条知识引用</span></div>
              <Check :size="18" />
            </div>
          </div>
        </section>

        <section class="capability-section">
          <div class="section-heading">
            <span>ONE WORKSPACE</span>
            <h2>一套工作台，管好内容生产全流程</h2>
            <p>方法、事实、生成和审核不再散落在不同工具里。</p>
          </div>

          <div class="capability-grid">
            <button
              v-for="capability in capabilities"
              :key="capability.title"
              class="capability-card"
              type="button"
              @click="goTo(capability.path)"
            >
              <span class="capability-icon"><component :is="capability.icon" :size="22" /></span>
              <span class="capability-content">
                <strong>{{ capability.title }}</strong>
                <small>{{ capability.tag }}</small>
                <p>{{ capability.desc }}</p>
              </span>
              <ArrowUpRight class="card-arrow" :size="18" />
            </button>
          </div>
        </section>

        <section class="bottom-cta">
          <div>
            <span>从真实业务出发</span>
            <h2>让每一次创作都有方法、有依据、有结果</h2>
          </div>
          <button type="button" @click="goTo('/content/new')">
            立即开始内容生产 <ArrowRight :size="18" />
          </button>
        </section>
      </main>

      <footer class="site-footer">
        <div class="footer-brand">
          <img src="/contentflow-mark.svg" alt="" />ContentFlow 内容生产平台
        </div>
        <p>© {{ currentYear }} ContentFlow. 为企业构建可控、可复用的内容生产能力。</p>
      </footer>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useInfoStore } from '@/stores/info'
import { healthApi } from '@/apis/system_api'
import UserInfoComponent from '@/components/UserInfoComponent.vue'
import {
  ArrowRight,
  ArrowUpRight,
  BookOpenCheck,
  Check,
  CircleCheck,
  FileClock,
  FilePenLine,
  History,
  LibraryBig,
  ShieldCheck,
  Sparkles
} from 'lucide-vue-next'

const router = useRouter()
const userStore = useUserStore()
const infoStore = useInfoStore()
const isLoading = ref(true)
const error = ref(null)
const currentYear = new Date().getFullYear()

const navItems = [
  { label: '内容创作', path: '/content/new' },
  { label: '创作规则', path: '/content/admin/rules' },
  { label: '企业知识库', path: '/knowledge' },
  { label: '生产历史', path: '/content/history' }
]

const workflowSteps = [
  { title: '业务素材', desc: '形成统一事实简报', label: '已完成', state: 'done' },
  { title: '创作策略', desc: '匹配方法与内容公式', label: '已完成', state: 'done' },
  { title: '内容生成', desc: '标题、正文同源生成', label: '进行中', state: 'active' },
  { title: '审核交付', desc: '质量检查与版本保存', label: '待处理', state: 'pending' }
]

const capabilities = [
  {
    title: '内容创作工作台',
    tag: '四阶段生产',
    desc: '从业务素材到审核交付，以确定性工作流完成一篇高质量内容。',
    icon: FilePenLine,
    path: '/content/new'
  },
  {
    title: '结构化创作规则',
    tag: '方法可配置',
    desc: '管理创作手法、标题公式、正文公式与组合关系，不依赖大 Prompt。',
    icon: BookOpenCheck,
    path: '/content/admin/rules'
  },
  {
    title: '企业知识资产',
    tag: '事实有来源',
    desc: '连接企业产品、案例和业务资料，为生成内容提供可靠证据。',
    icon: LibraryBig,
    path: '/knowledge'
  },
  {
    title: '生产管理与追溯',
    tag: '过程可恢复',
    desc: '统一管理任务状态、审核结论、人工修改和历史内容版本。',
    icon: FileClock,
    path: '/content/history'
  }
]

const loadData = async () => {
  isLoading.value = true
  error.value = null
  try {
    const response = await healthApi.checkHealth()
    if (response.status !== 'ok') throw new Error('服务不可用')
    await infoStore.loadInfoConfig()
  } catch (loadError) {
    console.error('首页加载失败:', loadError)
    error.value = { title: '服务连接失败', message: '后端服务暂时无法响应，请稍后重试。' }
  } finally {
    isLoading.value = false
  }
}

const goTo = (path) => {
  if (!userStore.isLoggedIn) {
    sessionStorage.setItem('redirect', path)
    router.push({ path: '/login', query: { redirect: path } })
    return
  }
  router.push(path)
}

onMounted(loadData)
</script>

<style lang="less" scoped>
.home-page {
  min-height: 100vh;
  overflow-x: hidden;
  color: var(--color-text);
  background: var(--gray-0);
}

.page-state {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--color-text-secondary);
}

.site-header {
  position: sticky;
  top: 0;
  z-index: 20;
  height: 72px;
  display: grid;
  grid-template-columns: minmax(250px, 1fr) auto minmax(250px, 1fr);
  align-items: center;
  gap: 24px;
  padding: 0 clamp(24px, 4vw, 64px);
  border-bottom: 1px solid var(--gray-150);
  background: color-mix(in srgb, var(--gray-0) 94%, transparent);
  backdrop-filter: blur(16px);
}

.brand {
  display: flex;
  align-items: center;
  justify-self: start;
  gap: 12px;
  border: 0;
  padding: 0;
  background: transparent;
  cursor: pointer;

  img {
    width: 154px;
    height: auto;
  }
  span {
    padding-left: 12px;
    border-left: 1px solid var(--gray-200);
    color: var(--gray-600);
    font-size: 12px;
  }
}

.site-nav {
  display: flex;
  align-items: center;
  gap: 32px;
}
.site-nav button,
.login-link {
  border: 0;
  padding: 8px 0;
  background: transparent;
  color: var(--gray-700);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  &:hover,
  &:focus-visible {
    color: var(--main-color);
    outline: none;
  }
}

.header-actions {
  display: flex;
  align-items: center;
  justify-self: end;
  gap: 18px;
}
.header-cta,
.primary-cta,
.bottom-cta button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border: 1px solid var(--main-color);
  border-radius: 8px;
  color: #fff;
  background: var(--main-color);
  cursor: pointer;
  &:hover,
  &:focus-visible {
    border-color: var(--main-600);
    background: var(--main-600);
    outline: 3px solid var(--main-100);
  }
}
.header-cta {
  min-height: 40px;
  padding: 0 16px;
  font-size: 14px;
  font-weight: 600;
}

.hero {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1.02fr) minmax(430px, 0.98fr);
  align-items: center;
  gap: clamp(44px, 7vw, 96px);
  max-width: 1320px;
  min-height: 660px;
  margin: 0 auto;
  padding: 76px clamp(28px, 5vw, 72px) 84px;
}
.hero::before {
  content: '';
  position: absolute;
  inset: 0 auto auto 35%;
  width: 620px;
  height: 430px;
  pointer-events: none;
  background: radial-gradient(
    circle,
    color-mix(in srgb, var(--main-100) 65%, transparent),
    transparent 67%
  );
  opacity: 0.75;
}

.hero-copy {
  z-index: 1;
  max-width: 650px;
}
.eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 22px;
  padding: 7px 10px;
  border: 1px solid var(--main-100);
  border-radius: 6px;
  background: var(--main-30);
  color: var(--main-700);
  font-size: 12px;
  font-weight: 600;
}
.hero h1 {
  margin: 0;
  color: var(--gray-1000);
  font-size: clamp(42px, 5vw, 68px);
  font-weight: 700;
  line-height: 1.13;
  letter-spacing: -0.045em;
  span {
    display: block;
    color: var(--main-color);
    font-weight: inherit;
  }
}
.hero-description {
  max-width: 610px;
  margin: 26px 0 0;
  color: var(--gray-600);
  font-size: 17px;
  line-height: 1.9;
}
.hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 34px;
}
.primary-cta,
.secondary-cta {
  min-height: 48px;
  padding: 0 20px;
  font-size: 15px;
  font-weight: 600;
}
.secondary-cta {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--gray-200);
  border-radius: 8px;
  color: var(--gray-800);
  background: var(--gray-0);
  cursor: pointer;
  &:hover,
  &:focus-visible {
    border-color: var(--main-300);
    color: var(--main-color);
    background: var(--main-20);
    outline: none;
  }
}
.hero-trust {
  display: flex;
  flex-wrap: wrap;
  gap: 22px;
  margin: 24px 0 0;
  padding: 0;
  list-style: none;
}
.hero-trust li {
  display: flex;
  align-items: center;
  gap: 7px;
  color: var(--gray-600);
  font-size: 13px;
}
.hero-trust svg {
  color: var(--color-success-700);
}

.studio-preview {
  z-index: 1;
  width: 100%;
  padding: 24px;
  border: 1px solid var(--gray-150);
  border-radius: 12px;
  background: var(--gray-0);
  box-shadow: 0 22px 60px color-mix(in srgb, var(--main-900) 11%, transparent);
}
.preview-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}
.preview-kicker {
  color: var(--main-600);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.14em;
}
.preview-header h2 {
  margin: 4px 0 0;
  color: var(--gray-1000);
  font-size: 20px;
  font-weight: 650;
}
.running-status {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 6px 9px;
  border-radius: 999px;
  background: var(--color-info-50);
  color: var(--color-info-700);
  font-size: 11px;
  font-weight: 600;
}
.running-status span {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--color-info-500);
}
.preview-progress {
  margin: 24px 0 20px;
  padding: 18px;
  border: 1px solid var(--gray-150);
  border-radius: 8px;
  background: var(--gray-10);
}
.progress-summary {
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.progress-summary strong {
  color: var(--gray-1000);
  font-size: 28px;
  font-weight: 700;
}
.progress-summary span,
.progress-meta {
  color: var(--gray-600);
  font-size: 12px;
}
.progress-bar {
  height: 6px;
  margin-top: 14px;
  overflow: hidden;
  border-radius: 3px;
  background: var(--gray-150);
}
.progress-bar span {
  display: block;
  width: 67%;
  height: 100%;
  background: var(--main-color);
}
.progress-meta {
  display: flex;
  justify-content: space-between;
  margin-top: 8px;
}
.workflow-list {
  display: grid;
  gap: 0;
}
.workflow-step {
  position: relative;
  display: grid;
  grid-template-columns: 30px 1fr auto;
  align-items: center;
  gap: 12px;
  min-height: 68px;
}
.workflow-step:not(:last-child)::after {
  content: '';
  position: absolute;
  top: 48px;
  bottom: -10px;
  left: 14px;
  width: 1px;
  background: var(--gray-200);
}
.step-number {
  z-index: 1;
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border: 1px solid var(--gray-200);
  border-radius: 50%;
  background: var(--gray-0);
  color: var(--gray-500);
  font-size: 11px;
  font-weight: 600;
}
.step-number.done {
  border-color: var(--main-200);
  color: var(--main-color);
  background: var(--main-50);
}
.step-number.active {
  border-color: var(--main-color);
  color: #fff;
  background: var(--main-color);
}
.workflow-step strong {
  color: var(--gray-900);
  font-size: 14px;
  font-weight: 600;
}
.workflow-step p {
  margin: 3px 0 0;
  color: var(--gray-500);
  font-size: 12px;
}
.step-state {
  padding: 4px 7px;
  border-radius: 4px;
  color: var(--gray-500);
  background: var(--gray-50);
  font-size: 10px;
  font-weight: 600;
}
.step-state.done {
  color: var(--color-success-700);
  background: var(--color-success-50);
}
.step-state.active {
  color: var(--main-700);
  background: var(--main-50);
}
.evidence-card {
  display: grid;
  grid-template-columns: 36px 1fr auto;
  align-items: center;
  gap: 11px;
  margin-top: 16px;
  padding: 12px;
  border: 1px solid var(--color-success-100);
  border-radius: 8px;
  background: var(--color-success-10);
  color: var(--color-success-700);
}
.evidence-icon {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: 6px;
  background: var(--color-success-50);
}
.evidence-card strong {
  display: block;
  color: var(--gray-900);
  font-size: 12px;
  font-weight: 600;
}
.evidence-card span {
  display: block;
  margin-top: 2px;
  color: var(--gray-500);
  font-size: 10px;
}

.capability-section {
  padding: 76px clamp(28px, 5vw, 72px) 88px;
  border-top: 1px solid var(--gray-150);
  background: var(--gray-10);
}
.section-heading {
  max-width: 1320px;
  margin: 0 auto 34px;
}
.section-heading > span,
.bottom-cta > div > span {
  color: var(--main-600);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.13em;
}
.section-heading h2 {
  margin: 8px 0 0;
  color: var(--gray-1000);
  font-size: clamp(28px, 3vw, 38px);
  font-weight: 650;
  letter-spacing: -0.02em;
}
.section-heading p {
  margin: 10px 0 0;
  color: var(--gray-600);
  font-size: 15px;
}
.capability-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
  max-width: 1320px;
  margin: 0 auto;
}
.capability-card {
  position: relative;
  min-height: 228px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  padding: 22px;
  border: 1px solid var(--gray-150);
  border-radius: 8px;
  text-align: left;
  background: var(--gray-0);
  cursor: pointer;
}
.capability-card:hover,
.capability-card:focus-visible {
  border-color: var(--main-300);
  background: var(--main-10);
  outline: none;
}
.capability-icon {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border-radius: 7px;
  background: var(--main-50);
  color: var(--main-color);
}
.capability-content {
  margin-top: 28px;
}
.capability-content strong {
  display: block;
  color: var(--gray-1000);
  font-size: 16px;
  font-weight: 650;
}
.capability-content small {
  display: inline-block;
  margin-top: 8px;
  color: var(--main-600);
  font-size: 11px;
  font-weight: 600;
}
.capability-content p {
  margin: 12px 0 0;
  color: var(--gray-600);
  font-size: 13px;
  line-height: 1.7;
}
.card-arrow {
  position: absolute;
  top: 22px;
  right: 22px;
  color: var(--gray-400);
}
.capability-card:hover .card-arrow {
  color: var(--main-color);
}

.bottom-cta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 32px;
  max-width: 1176px;
  margin: 84px auto;
  padding: 36px 40px;
  border: 1px solid var(--main-100);
  border-radius: 10px;
  background: var(--main-30);
}
.bottom-cta h2 {
  margin: 8px 0 0;
  color: var(--gray-1000);
  font-size: 26px;
  font-weight: 650;
}
.bottom-cta button {
  flex: 0 0 auto;
  min-height: 46px;
  padding: 0 20px;
  font-size: 14px;
  font-weight: 600;
}

.site-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 24px clamp(28px, 5vw, 72px);
  border-top: 1px solid var(--gray-150);
  color: var(--gray-500);
  font-size: 12px;
}
.footer-brand {
  display: flex;
  align-items: center;
  gap: 9px;
  color: var(--gray-800);
  font-weight: 600;
}
.footer-brand img {
  width: 28px;
  height: 28px;
}
.site-footer p {
  margin: 0;
}

@media (max-width: 1100px) {
  .site-header {
    grid-template-columns: 1fr auto;
  }
  .site-nav {
    display: none;
  }
  .hero {
    grid-template-columns: 1fr;
    max-width: 820px;
    padding-top: 64px;
  }
  .hero-copy {
    text-align: center;
    margin: 0 auto;
  }
  .hero-actions,
  .hero-trust {
    justify-content: center;
  }
  .capability-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 700px) {
  .site-header {
    height: 64px;
    padding: 0 16px;
  }
  .brand img {
    width: 132px;
  }
  .brand span,
  .login-link {
    display: none;
  }
  .header-cta {
    padding: 0 12px;
  }
  .hero {
    min-height: 0;
    grid-template-columns: 1fr;
    padding: 56px 20px 64px;
  }
  .hero h1 {
    font-size: 40px;
  }
  .hero-description {
    font-size: 15px;
  }
  .studio-preview {
    padding: 16px;
  }
  .capability-section {
    padding: 56px 20px 64px;
  }
  .capability-grid {
    grid-template-columns: 1fr;
  }
  .capability-card {
    min-height: 200px;
  }
  .bottom-cta {
    flex-direction: column;
    align-items: flex-start;
    margin: 56px 20px;
    padding: 28px 24px;
  }
  .bottom-cta h2 {
    font-size: 22px;
  }
  .site-footer {
    flex-direction: column;
    align-items: flex-start;
    padding: 24px 20px;
  }
}
</style>
