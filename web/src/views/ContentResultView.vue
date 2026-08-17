<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  ArrowLeft,
  CheckCircle2,
  CircleAlert,
  FilePenLine,
  ImagePlus,
  Send,
  ShieldCheck,
  UserRoundCog
} from 'lucide-vue-next'
import { contentApi } from '@/apis/content_api'
import XiaohongshuDistributionDrawer from '@/components/content/XiaohongshuDistributionDrawer.vue'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const task = ref(null)
const artifact = ref(null)
const distributionOpen = ref(false)
const coverUrl = ref('')

const reviewStatus = computed(() => artifact.value?.review_snapshot?.status || 'pending')
const canDistribute = computed(() =>
  artifact.value && ['passed', 'warning'].includes(reviewStatus.value)
)

const load = async () => {
  loading.value = true
  try {
    const response = await contentApi.getTask(route.params.taskId)
    task.value = response.task
    artifact.value = response.artifact
    if (!artifact.value) {
      const artifactResponse = await contentApi.getTaskArtifact(route.params.taskId)
      artifact.value = artifactResponse.artifact
    }
    if (artifact.value?.cover_asset_id) {
      try {
        const coverResponse = await contentApi.getCoverAssetFile(artifact.value.cover_asset_id)
        coverUrl.value = URL.createObjectURL(await coverResponse.blob())
      } catch (error) {
        message.warning(error.message || '当前封面暂时无法预览')
      }
    }
  } catch (error) {
    message.error(error.message || '内容结果加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(load)
onBeforeUnmount(() => {
  if (coverUrl.value) URL.revokeObjectURL(coverUrl.value)
})
</script>

<template>
  <div class="result-page">
    <header class="result-header">
      <div>
        <button type="button" class="back-link" @click="router.push('/content/history')"><ArrowLeft :size="16" />返回生产历史</button>
        <span>Content Result</span>
        <h1>{{ task?.name || '内容生产结果' }}</h1>
      </div>
      <div class="header-actions">
        <a-button @click="router.push('/content/accounts')"><UserRoundCog :size="16" />账号管理</a-button>
        <a-button @click="router.push(`/content/tasks/${route.params.taskId}`)"><FilePenLine :size="16" />继续编辑</a-button>
        <a-tooltip v-if="!canDistribute" title="内容审核未通过，修订并重新审核后才能分发">
          <a-button type="primary" disabled><Send :size="16" />分发到小红书</a-button>
        </a-tooltip>
        <a-button v-else type="primary" size="large" @click="distributionOpen = true"><Send :size="17" />分发到小红书</a-button>
      </div>
    </header>

    <a-skeleton v-if="loading" class="loading-card" active :paragraph="{ rows: 12 }" />
    <main v-else-if="artifact" class="result-layout">
      <article class="content-card">
        <div class="review-strip" :class="reviewStatus">
          <CheckCircle2 v-if="reviewStatus === 'passed'" :size="18" />
          <CircleAlert v-else :size="18" />
          <span>{{ reviewStatus === 'passed' ? '内容审核已通过，可进行平台分发' : reviewStatus === 'warning' ? '内容存在提醒，分发前请再次检查' : '内容审核未通过，暂不能分发' }}</span>
        </div>
        <div v-if="coverUrl" class="selected-cover">
          <img :src="coverUrl" alt="当前内容封面" />
          <div><strong>当前分发封面</strong><span>小红书分发将优先使用这张封面</span></div>
          <button @click="router.push({ path: '/content/covers', query: { task: route.params.taskId } })">重新生成</button>
        </div>
        <h2>{{ artifact.title }}</h2>
        <div v-if="artifact.topics?.length" class="topics"><span v-for="topic in artifact.topics" :key="topic">#{{ topic }}</span></div>
        <div class="body-text">{{ artifact.body }}</div>
      </article>

      <aside class="result-sidebar">
        <section>
          <h3><ShieldCheck :size="17" />分发准备</h3>
          <dl><div><dt>内容版本</dt><dd>v{{ artifact.current_version }}</dd></div><div><dt>审核状态</dt><dd>{{ reviewStatus }}</dd></div><div><dt>默认方式</dt><dd>保存草稿</dd></div></dl>
          <p>提交分发后会锁定当前版本、标题、正文、话题和目标账号，后续编辑不会改变已排队任务。</p>
        </section>
        <section class="action-guide">
          <strong>一键分发包含什么？</strong>
          <ol><li>{{ artifact.cover_asset_id ? '使用当前选定的小红书封面' : '自动生成默认 3:4 小红书封面' }}</li><li>写入标题、正文和全部话题</li><li>按账号分别保存草稿或发布</li><li>记录每个账号的执行结果</li></ol>
          <button class="cover-link" @click="router.push({ path: '/content/covers', query: { task: route.params.taskId } })"><ImagePlus :size="15" />{{ artifact.cover_asset_id ? '管理封面' : '生成专属封面' }}</button>
        </section>
      </aside>
    </main>
    <a-empty v-else description="该任务还没有生成内容结果" />

    <XiaohongshuDistributionDrawer v-model:open="distributionOpen" :artifact="artifact" />
  </div>
</template>

<style scoped lang="less">
.result-page { min-height: 100vh; padding: 24px var(--page-padding) 56px; background: var(--gray-25); color: var(--color-text); }
.result-header, .result-layout, .loading-card { max-width: 1180px; margin-left: auto; margin-right: auto; }
.result-header { display: flex; justify-content: space-between; align-items: flex-end; gap: 24px; margin-bottom: 18px; }
.result-header > div:first-child > span { color: var(--main-700); font-size: 12px; font-weight: 600; }
.result-header h1 { margin: 5px 0 0; font-size: 26px; }
.back-link { display: flex; align-items: center; gap: 5px; margin: 0 0 18px; padding: 0; border: 0; background: transparent; color: var(--color-text-secondary); cursor: pointer; }
.header-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
.header-actions :deep(.ant-btn) { display: inline-flex; align-items: center; gap: 6px; }
.loading-card, .content-card, .result-sidebar section { border: 1px solid var(--gray-150); border-radius: 10px; background: var(--gray-0); }
.loading-card { padding: 24px; }
.result-layout { display: grid; grid-template-columns: minmax(0, 1fr) 310px; gap: 18px; align-items: start; }
.content-card { min-height: 680px; padding: 32px 38px; }
.review-strip { display: flex; align-items: center; gap: 8px; margin: -8px 0 24px; padding: 10px 12px; border-radius: 8px; background: var(--color-warning-50); color: var(--color-warning-900); font-size: 13px; }
.review-strip.passed { background: var(--color-success-50); color: var(--color-success-700); }
.review-strip.blocked { background: var(--color-error-50); color: var(--color-error-700); }
.selected-cover { display: grid; grid-template-columns: 90px 1fr auto; gap: 13px; align-items: center; margin-bottom: 24px; padding: 11px; border: 1px solid var(--main-100); border-radius: 10px; background: var(--main-30); }
.selected-cover img { width: 90px; height: 112px; border-radius: 7px; object-fit: cover; }.selected-cover div { display: grid; gap: 4px; }.selected-cover span { color: var(--color-text-secondary); font-size: 12px; }.selected-cover button, .cover-link { border: 0; color: var(--main-700); background: transparent; cursor: pointer; }
.cover-link { display: inline-flex; align-items: center; gap: 5px; padding: 0; }
.content-card h2 { max-width: 780px; margin: 0 0 14px; font-size: 30px; line-height: 1.35; }
.topics { display: flex; flex-wrap: wrap; gap: 7px; margin-bottom: 26px; }
.topics span { padding: 3px 9px; border-radius: 999px; background: var(--main-30); color: var(--main-700); font-size: 12px; }
.body-text { white-space: pre-wrap; color: var(--gray-800); font-size: 16px; line-height: 1.9; }
.result-sidebar { display: flex; flex-direction: column; gap: 12px; }
.result-sidebar section { padding: 17px; }
.result-sidebar h3 { display: flex; align-items: center; gap: 7px; margin: 0 0 12px; font-size: 16px; }
.result-sidebar dl { margin: 0; }
.result-sidebar dl > div { display: flex; justify-content: space-between; gap: 12px; padding: 8px 0; border-bottom: 1px solid var(--gray-150); }
.result-sidebar dt { color: var(--color-text-secondary); }
.result-sidebar dd { margin: 0; font-weight: 600; }
.result-sidebar p, .action-guide li { color: var(--color-text-secondary); font-size: 12px; line-height: 1.7; }
.action-guide ol { margin: 10px 0 0; padding-left: 19px; }
@media (max-width: 900px) { .result-layout { grid-template-columns: 1fr; } .result-sidebar { display: grid; grid-template-columns: 1fr 1fr; } }
@media (max-width: 700px) { .result-header { align-items: flex-start; flex-direction: column; } .header-actions { justify-content: flex-start; } .content-card { padding: 24px 20px; } .result-sidebar { grid-template-columns: 1fr; } }
</style>
