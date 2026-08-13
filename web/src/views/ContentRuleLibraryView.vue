<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { ArrowLeft, Database, GitBranch, Layers3 } from 'lucide-vue-next'
import { contentApi } from '@/apis/content_api'
import { useContentStudioStore } from '@/stores/contentStudio'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const store = useContentStudioStore()
const userStore = useUserStore()
const ruleVersions = ref([])
const industries = ref([])
const workflows = ref([])
const activeTab = ref('methods')

const load = async (force = false) => {
  try {
    await store.loadBootstrap(force)
    const [rules, templates, flowList] = await Promise.all([
      contentApi.listRuleVersions(),
      contentApi.listIndustryTemplates(),
      contentApi.listWorkflowTemplates()
    ])
    ruleVersions.value = rules.items || []
    industries.value = templates.items || []
    workflows.value = flowList.items || []
  } catch (error) {
    message.error(error.message || '加载创作规则库失败')
  }
}

const activateVersion = (item, rollback = false) => {
  Modal.confirm({
    title: rollback ? `回滚到规则 v${item.version}` : `发布规则 v${item.version}`,
    content: '新任务会使用该版本；历史任务仍保留原规则快照。',
    okText: rollback ? '确认回滚' : '确认发布',
    cancelText: '取消',
    onOk: async () => {
      try {
        if (rollback) await contentApi.rollbackRuleVersion(item.id)
        else await contentApi.publishRuleVersion(item.id)
        await load(true)
        message.success(rollback ? '规则版本已回滚' : '规则版本已发布')
      } catch (error) {
        message.error(error.message || '规则版本操作失败')
      }
    }
  })
}

onMounted(() => load())
</script>

<template>
  <div class="rule-library-page">
    <header>
      <div><button type="button" @click="router.back()"><ArrowLeft :size="18" /></button><div><span>运营配置后台</span><h1>创作规则库</h1><p>精确规则进入 PostgreSQL；行业知识和案例进入 RAG。</p></div></div>
      <span class="published-badge">已发布 v{{ store.ruleBundle?.version?.version || 1 }}</span>
    </header>

    <div class="overview-grid">
      <div><Layers3 :size="20" /><strong>{{ store.ruleBundle?.methods?.length || 0 }}</strong><span>创作手法与增强器</span></div>
      <div><Database :size="20" /><strong>{{ store.ruleBundle?.title_formulas?.length || 0 }} / {{ store.ruleBundle?.content_formulas?.length || 0 }}</strong><span>标题公式 / 正文公式</span></div>
      <div><GitBranch :size="20" /><strong>{{ workflows.length }}</strong><span>可执行工作流版本</span></div>
    </div>

    <section class="rule-card">
      <a-tabs v-model:activeKey="activeTab">
        <a-tab-pane key="methods" tab="创作手法">
          <div class="rule-grid"><article v-for="item in store.ruleBundle?.methods || []" :key="item.code"><code>{{ item.code }}</code><h3>{{ item.name }}</h3><p>{{ item.principle }}</p><div><span v-for="scene in item.suitable_scenes" :key="scene">{{ scene }}</span></div></article></div>
        </a-tab-pane>
        <a-tab-pane key="titles" tab="标题公式">
          <a-table :data-source="store.ruleBundle?.title_formulas || []" row-key="code" :pagination="false"><a-table-column title="编码" data-index="code" width="80" /><a-table-column title="公式" data-index="name" /><a-table-column title="核心目标" data-index="core_goal" /><a-table-column title="变量"><template #default="{ record }">{{ record.variable_schema.join('、') }}</template></a-table-column></a-table>
        </a-tab-pane>
        <a-tab-pane key="bodies" tab="正文公式">
          <div class="rule-grid"><article v-for="item in store.ruleBundle?.content_formulas || []" :key="item.code"><code>{{ item.code }}</code><h3>{{ item.name }}</h3><ol><li v-for="section in item.structure_schema" :key="section">{{ section }}</li></ol></article></div>
        </a-tab-pane>
        <a-tab-pane key="combinations" tab="组合矩阵">
          <a-table :data-source="store.ruleBundle?.combination_rules || []" row-key="id" :pagination="false"><a-table-column title="内容目标" data-index="content_goal" /><a-table-column title="创作手法"><template #default="{ record }">{{ record.methods.join(' + ') }}</template></a-table-column><a-table-column title="标题候选"><template #default="{ record }">{{ record.title_formula_codes.join('、') }}</template></a-table-column><a-table-column title="正文" data-index="content_formula_code" /><a-table-column title="推荐原因" data-index="recommendation_reason" /></a-table>
        </a-tab-pane>
        <a-tab-pane key="industries" tab="行业模板">
          <div class="rule-grid"><article v-for="item in industries" :key="item.id"><code>{{ item.slug }} · v{{ item.version }}</code><h3>{{ item.name }}</h3><p>{{ item.description }}</p><small>{{ item.quick_form_schema.length }} 个简化字段 · {{ item.pro_form_schema.length }} 个专业字段</small></article></div>
        </a-tab-pane>
        <a-tab-pane key="workflows" tab="工作流版本">
          <div class="workflow-list"><article v-for="item in workflows" :key="item.id"><div><code>{{ item.id }}</code><h3>{{ item.slug }} · v{{ item.version }}</h3></div><span>{{ item.status }}</span><p>{{ item.definition.nodes?.length || 0 }} 个节点 · {{ item.definition.edges?.length || 0 }} 条连线</p></article></div>
        </a-tab-pane>
      </a-tabs>
    </section>

    <section class="version-list">
      <h2>规则版本</h2>
      <div v-for="item in ruleVersions" :key="item.id">
        <strong>v{{ item.version }} · {{ item.status }}</strong>
        <span>{{ item.changelog }}</span>
        <code>{{ item.id }}</code>
        <span class="version-actions">
          <a-button v-if="userStore.isSuperAdmin && item.status === 'draft'" size="small" type="primary" @click="activateVersion(item)">发布</a-button>
          <a-button v-else-if="userStore.isSuperAdmin && item.status === 'archived'" size="small" @click="activateVersion(item, true)">回滚</a-button>
        </span>
      </div>
    </section>
  </div>
</template>

<style scoped lang="less">
.rule-library-page { min-height: 100vh; padding: 24px var(--page-padding) 48px; background: var(--gray-25); color: var(--color-text); }
header, .overview-grid, .rule-card, .version-list { max-width: 1180px; margin-left: auto; margin-right: auto; }
header { margin-bottom: 18px; display: flex; justify-content: space-between; gap: 20px; }
header > div { display: flex; gap: 10px; }
header button { width: 34px; height: 34px; display: inline-flex; align-items: center; justify-content: center; border: 1px solid var(--gray-150); border-radius: 6px; background: var(--gray-0); color: var(--color-text); cursor: pointer; }
header span { color: var(--main-700); font-size: 12px; }
header h1 { margin: 2px 0; font-size: 24px; }
header p { margin: 0; color: var(--color-text-secondary); }
.published-badge { align-self: flex-start; padding: 5px 10px; border-radius: 999px; background: var(--color-success-50); color: var(--color-success-700); }
.overview-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 16px; }
.overview-grid > div { display: grid; grid-template-columns: auto 1fr; gap: 3px 10px; padding: 16px; border: 1px solid var(--gray-150); border-radius: 8px; background: var(--gray-0); }
.overview-grid svg { grid-row: 1 / 3; color: var(--main-700); }
.overview-grid strong { font-size: 18px; }
.overview-grid span { color: var(--color-text-secondary); }
.rule-card, .version-list { padding: 20px; border: 1px solid var(--gray-150); border-radius: 8px; background: var(--gray-0); }
.rule-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.rule-grid article { padding: 16px; border: 1px solid var(--gray-150); border-radius: 8px; }
.rule-grid h3 { margin: 7px 0; }
.rule-grid p, .rule-grid small, .rule-grid li { color: var(--color-text-secondary); }
.rule-grid article > div { display: flex; flex-wrap: wrap; gap: 5px; }
.rule-grid article > div span { padding: 2px 6px; border-radius: 999px; background: var(--main-30); color: var(--main-700); font-size: 12px; }
.workflow-list { display: flex; flex-direction: column; gap: 10px; }
.workflow-list article { display: grid; grid-template-columns: 1fr auto; padding: 14px; border: 1px solid var(--gray-150); border-radius: 8px; }
.workflow-list h3, .workflow-list p { margin: 3px 0; }
.workflow-list p { grid-column: 1 / -1; color: var(--color-text-secondary); }
.version-list { margin-top: 16px; }
.version-list h2 { margin-top: 0; font-size: 17px; }
.version-list > div { display: grid; grid-template-columns: 140px 1fr auto auto; align-items: center; gap: 12px; padding: 10px 0; border-top: 1px solid var(--gray-100); }
.version-list span { color: var(--color-text-secondary); }
.version-actions { min-width: 58px; text-align: right; }
@media (max-width: 800px) { .overview-grid, .rule-grid { grid-template-columns: 1fr; } .version-list > div { grid-template-columns: 1fr; } }
</style>
