import assert from 'node:assert/strict'

import {
  CONTENT_WORKFLOW_GROUPS,
  CONTENT_WORKFLOW_NODE_LABELS,
  appendContentNarrativeText,
  buildContentCompletionSummary,
  buildContentNarrativeCodeLabels,
  buildContentNarrativeStream,
  buildFormulaPresentation,
  buildContentRuntimeTimeline,
  buildContentWorkflowGroups,
  formatElapsedDuration
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
assert.equal(timeline[0].nodeId, 'select_creation_strategy')
assert.equal(timeline[1].detail, 'content-strategy-agent')
assert.equal(timeline[1].nodeId, 'select_creation_strategy')
assert.equal(timeline[1].nodeLabel, 'Agent 匹配创作手法与公式')
assert.deepEqual(timeline[1].inputPreview, { content_brief: { content_goal: 'acquire' } })
assert.equal(timeline[2].detail, 'products · 杭州装修案例 · 返回 3 条结果')
assert.equal(timeline[2].knowledgeResults[0].content, '89㎡三居改造案例')

const deduplicatedTimeline = buildContentRuntimeTimeline([], [
  {
    run_id: 'run-1',
    seq: '2-0',
    event_type: 'content.knowledge.retrieved',
    created_at: '2026-08-28T01:00:02Z',
    payload: { node_id: 'select_creation_strategy', knowledge_base_id: 'products' }
  },
  {
    run_id: 'run-1',
    seq: '2-0',
    event_type: 'content.knowledge.retrieved',
    created_at: '2026-08-28T01:00:02Z',
    payload: { node_id: 'select_creation_strategy', knowledge_base_id: 'products' }
  }
])
assert.equal(deduplicatedTimeline.length, 1)

const narrative = buildContentNarrativeStream(timeline)
assert.equal(narrative.length, 2)
assert.match(narrative[0].text, /目标受众.*内容方向/)
assert.match(narrative[1].text, /杭州装修案例.*3 条相关资料.*89㎡三居改造案例/)
assert.ok(narrative.every((item) => !/Agent|Skill|工具调用|content-strategy-agent/.test(item.text)))

const generatedNarrative = buildContentNarrativeStream([
  {
    id: 'generated-result',
    nodeId: 'generate_content',
    eventType: 'content.agent.completed',
    status: 'completed',
    outputPreview: {
      title: { text: '89㎡三居这样改，多出12㎡收纳空间' },
      outline: { sections: [{ goal: '说明原户型痛点' }, { goal: '展示改造结果' }] },
      draft: { body: '入户与餐厅缺少集中收纳，通过玄关柜和餐边柜重新组织动线。', topics: ['杭州装修', '收纳设计'] }
    }
  }
])
assert.deepEqual(
  generatedNarrative.map((item) => item.text),
  [
    '标题已生成：89㎡三居这样改，多出12㎡收纳空间',
    '正文将依次说明：说明原户型痛点；展示改造结果。',
    '正文内容：入户与餐厅缺少集中收纳，通过玄关柜和餐边柜重新组织动线。',
    '建议话题：#杭州装修 #收纳设计'
  ]
)

const cumulativeNarrative = buildContentNarrativeStream([
  ...timeline,
  {
    id: 'strategy-result',
    nodeId: 'select_creation_strategy',
    eventType: 'content.agent.completed',
    status: 'completed',
    outputPreview: {
      value_points: ['用真实户型改造结果回应收纳焦虑'],
      selection_reason: '现有案例数据完整，能够支撑具体结果。'
    }
  },
  {
    id: 'generated-result',
    nodeId: 'generate_content',
    eventType: 'content.agent.completed',
    status: 'completed',
    outputPreview: {
      title: { text: '89㎡三居这样改，多出12㎡收纳空间' },
      outline: { sections: [{ goal: '说明原户型痛点' }, { goal: '展示改造结果' }] },
      draft: {
        body: '入户与餐厅缺少集中收纳，通过玄关柜和餐边柜重新组织动线。',
        topics: ['杭州装修', '收纳设计']
      }
    }
  },
  {
    id: 'review-result',
    nodeId: 'deterministic_validate',
    eventType: 'content.validation.completed',
    status: 'completed',
    validationStatus: 'passed',
    checkCount: 6
  }
])
const cumulativeNarrativeText = cumulativeNarrative.map((item) => item.text).join('\n')
assert.match(cumulativeNarrativeText, /杭州装修案例.*3 条相关资料/)
assert.match(cumulativeNarrativeText, /识别出的内容价值.*收纳焦虑/)
assert.match(cumulativeNarrativeText, /标题已生成：89㎡三居这样改/)
assert.match(cumulativeNarrativeText, /正文内容：入户与餐厅缺少集中收纳/)
assert.match(cumulativeNarrativeText, /已完成 6 项规则检查.*没有发现阻断问题/)
assert.ok(!/Skill|工具调用|content-strategy-agent/.test(cumulativeNarrativeText))

const runningSnapshot = buildContentNarrativeStream([
  {
    id: 'node-run-1-generate_content-0',
    nodeId: 'generate_content',
    eventType: 'content.node.status',
    status: 'running'
  }
])
const completedSnapshot = buildContentNarrativeStream([
  {
    id: 'node-run-1-generate_content-0',
    nodeId: 'generate_content',
    eventType: 'content.node.status',
    status: 'completed',
    outputPreview: { title: '最终标题' }
  }
])
const retainedNarrative = appendContentNarrativeText(
  appendContentNarrativeText([], runningSnapshot),
  completedSnapshot
)
assert.deepEqual(retainedNarrative, [
  '正在把已确认的策略和事实组织成标题、正文结构与发布话题。',
  '标题已生成：最终标题'
])

const codeLabels = buildContentNarrativeCodeLabels({
  content_types: [{ code: 'CT01', name: '案例/成果展示' }],
  methods: [
    { code: 'M01', name: '数字法' },
    { code: 'S01', name: '场景增强' },
    { code: 'M03', name: '价值法' }
  ],
  title_formulas: [{ code: 'T01', name: '细分人群＋数字＋结果' }],
  content_formulas: [{ code: 'C02', name: '实景流量类' }]
})
const explainedFormulaNarrative = buildContentNarrativeStream(
  [
    {
      id: 'strategy-with-codes',
      nodeId: 'select_creation_strategy',
      eventType: 'content.agent.completed',
      status: 'completed',
      outputPreview: {
        reason:
          'brief 锁定内容类型为 CT01 案例/成果展示；选择 CT01 下的 M01+S01+M03，标题公式 T01，正文公式 C02。'
      }
    }
  ],
  codeLabels
)
assert.equal(
  explainedFormulaNarrative[0].text,
  '判断依据：brief 锁定内容类型为 CT01 案例/成果展示；选择 CT01（案例/成果展示）下的 M01（数字法）+S01（场景增强）+M03（价值法），标题公式 T01（细分人群＋数字＋结果），正文公式 C02（实景流量类）。'
)

const groupsWithActivity = buildContentWorkflowGroups(
  [
    { node_id: 'compile_runtime_snapshot', status: 'completed' },
    { node_id: 'ingest_real_materials', status: 'completed' },
    { node_id: 'normalize_evidence', status: 'completed' },
    { node_id: 'select_creation_strategy', status: 'running' }
  ],
  [
    {
      run_id: 'run-1',
      seq: '1-0',
      event_type: 'content.agent.started',
      created_at: '2026-08-28T01:00:01Z',
      payload: { node_id: 'select_creation_strategy', agent_slug: 'content-strategy-agent' }
    },
    {
      run_id: 'run-1',
      seq: '2-0',
      event_type: 'content.skill.activated',
      created_at: '2026-08-28T01:00:02Z',
      payload: {
        node_id: 'select_creation_strategy',
        skill_slug: 'content-strategy',
        skill_version: '1.1.0'
      }
    }
  ]
)
const activeStrategyStep = groupsWithActivity[1].nodes[0]
assert.equal(activeStrategyStep.activities.length, 3)
assert.equal(activeStrategyStep.activity.label, 'Skill 已激活')
assert.equal(activeStrategyStep.activity.detail, 'content-strategy · 1.1.0')
assert.equal(activeStrategyStep.activity.nodeId, 'select_creation_strategy')

const groupsWithCompletedOutput = buildContentWorkflowGroups([
  {
    run_id: 'run-1',
    node_id: 'generate_content',
    status: 'completed',
    output_snapshot: { title: '长沙89㎡三室两厅逆袭美颜：腾出12㎡储物空间' }
  }
])
assert.deepEqual(groupsWithCompletedOutput[2].nodes[0].activity.outputPreview, {
  title: '长沙89㎡三室两厅逆袭美颜：腾出12㎡储物空间'
})

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

const completionSummary = buildContentCompletionSummary(
  [
    { node_id: 'compile_runtime_snapshot', status: 'completed' },
    { node_id: 'select_creation_strategy', status: 'completed' }
  ],
  [
    {
      event_type: 'content.agent.started',
      payload: { node_id: 'select_creation_strategy' }
    },
    {
      event_type: 'content.skill.activated',
      payload: {
        node_id: 'select_creation_strategy',
        skill_slug: 'content-strategy',
        skill_version: '1.1.0'
      }
    },
    {
      event_type: 'content.knowledge.retrieved',
      payload: {
        node_id: 'collect_missing_evidence',
        knowledge_base_id: 'kb-1',
        source_ids: ['file-1', 'file-2'],
        result_count: 3
      }
    }
  ]
)
assert.equal(completionSummary.completedNodes, 2)
assert.equal(completionSummary.totalNodes, 2)
assert.equal(completionSummary.agentRuns, 1)
assert.deepEqual(completionSummary.skills[0], {
  slug: 'content-strategy',
  version: '1.1.0',
  activations: 1,
  nodes: ['Agent 匹配创作手法与公式']
})
assert.deepEqual(completionSummary.knowledgeBases[0], {
  id: 'kb-1',
  retrievals: 1,
  resultCount: 3,
  sourceIds: ['file-1', 'file-2'],
  sourceCount: 2,
  nodes: ['Agent 收集缺失证据']
})

const persistedSkillSummary = buildContentCompletionSummary(
  [],
  [],
  [
    {
      node_id: 'select_creation_strategy',
      status: 'completed',
      runtime_config_snapshot: {
        skills: [
          { slug: 'content-value-analyzer', version: '1.3.0' },
          { slug: 'content-strategy-planner', version: '4.0.1' }
        ]
      }
    },
    {
      node_id: 'generate_content',
      status: 'completed',
      runtime_config_snapshot: {
        skills: [{ slug: 'content-title-generator', version: '2.0.0' }]
      }
    },
    {
      node_id: 'semantic_review',
      status: 'failed',
      runtime_config_snapshot: {
        skills: [{ slug: 'content-reviewer', version: '1.1.0' }]
      }
    }
  ]
)
assert.equal(persistedSkillSummary.skillCount, 3)
assert.deepEqual(persistedSkillSummary.skills[0], {
  slug: 'content-value-analyzer',
  version: '1.3.0',
  activations: 1,
  nodes: ['Agent 匹配创作手法与公式']
})
assert.equal(formatElapsedDuration(141000), '2分21秒')

console.log('contentWorkflowPresentation: all assertions passed')
