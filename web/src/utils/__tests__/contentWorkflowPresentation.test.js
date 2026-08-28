import assert from 'node:assert/strict'

import {
  CONTENT_WORKFLOW_GROUPS,
  CONTENT_WORKFLOW_NODE_LABELS,
  buildFormulaPresentation,
  buildContentRuntimeTimeline,
  buildContentWorkflowGroups
} from '../contentWorkflowPresentation.js'

const groupedNodeIds = CONTENT_WORKFLOW_GROUPS.flatMap((group) => group.nodes)
assert.equal(CONTENT_WORKFLOW_GROUPS.length, 4)
assert.equal(groupedNodeIds.length, 15)
assert.equal(new Set(groupedNodeIds).size, 15)
assert.ok(groupedNodeIds.every((nodeId) => CONTENT_WORKFLOW_NODE_LABELS[nodeId]))

const groups = buildContentWorkflowGroups([
  { node_id: 'compile_runtime_snapshot', status: 'completed' },
  { node_id: 'ingest_real_materials', status: 'completed' },
  { node_id: 'normalize_evidence', status: 'completed' },
  { node_id: 'select_creation_strategy', status: 'running' }
])

assert.equal(groups[0].status, 'completed')
assert.equal(groups[0].isOpen, false)
assert.equal(groups[0].currentText, '已完成 3 个内部节点')
assert.equal(groups[1].status, 'running')
assert.equal(groups[1].isOpen, true)
assert.equal(groups[1].currentNode.id, 'select_creation_strategy')
assert.equal(groups[1].currentText, '当前：Agent 匹配创作手法、标题公式和正文公式')
assert.equal(groups[1].completedCount, 0)
assert.equal(groups[1].totalCount, 3)

const failedGroups = buildContentWorkflowGroups([
  { node_id: 'compile_runtime_snapshot', status: 'completed' },
  { node_id: 'ingest_real_materials', status: 'failed' }
])
assert.equal(failedGroups[0].status, 'failed')
assert.equal(failedGroups[0].isOpen, true)
assert.equal(failedGroups[0].currentNode.id, 'ingest_real_materials')

const timeline = buildContentRuntimeTimeline(
  [{ run_id: 'run-1', node_id: 'select_creation_strategy', status: 'running', created_at: '2026-08-28T01:00:00Z' }],
  [
    {
      run_id: 'run-1',
      seq: '1-0',
      event_type: 'content.agent.started',
      created_at: '2026-08-28T01:00:01Z',
      payload: {
        node_id: 'select_creation_strategy',
        agent_slug: 'content-strategy-agent',
        input_preview: { content_brief: { content_goal: 'acquire' } }
      }
    },
    {
      run_id: 'run-1',
      seq: '2-0',
      event_type: 'content.knowledge.retrieved',
      created_at: '2026-08-28T01:00:02Z',
      payload: {
        node_id: 'select_creation_strategy',
        knowledge_base_id: 'products',
        query_text: '杭州装修案例',
        result_count: 3,
        results: [{ file_name: '案例库.md', content: '89㎡三居改造案例' }]
      }
    }
  ]
)
assert.equal(timeline.length, 3)
assert.equal(timeline[0].label, 'Agent 匹配创作手法与公式')
assert.equal(timeline[1].detail, 'content-strategy-agent')
assert.equal(timeline[1].nodeLabel, 'Agent 匹配创作手法与公式')
assert.deepEqual(timeline[1].inputPreview, { content_brief: { content_goal: 'acquire' } })
assert.equal(timeline[2].detail, 'products · 杭州装修案例 · 返回 3 条结果')
assert.equal(timeline[2].knowledgeResults[0].content, '89㎡三居改造案例')

assert.deepEqual(
  buildFormulaPresentation(
    { title_formula: { code: 'T01', name: '细分人群＋数字＋结果', core_goal: '精准圈定人群' } },
    'title'
  ),
  { name: '细分人群＋数字＋结果', detail: '精准圈定人群' }
)
assert.deepEqual(
  buildFormulaPresentation(
    { body_formula: { code: 'C02', name: '实景流量类', structure_schema: ['旧况或背景', '关键数据', '落地结果'] } },
    'body'
  ),
  { name: '实景流量类', detail: '旧况或背景 → 关键数据 → 落地结果' }
)
assert.deepEqual(buildFormulaPresentation({ title_formula_code: 'T01' }, 'title'), {
  name: '-',
  detail: ''
})

console.log('contentWorkflowPresentation: all assertions passed')
