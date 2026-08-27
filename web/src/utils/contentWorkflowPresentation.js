export const CONTENT_WORKFLOW_NODE_LABELS = {
  compile_runtime_snapshot: '冻结运行配置',
  ingest_real_materials: '导入真实素材',
  normalize_evidence: '规范化证据',
  select_creation_strategy: 'Agent 匹配创作手法与公式',
  lock_creation_strategy: '固定规则校验并锁定策略',
  analyze_and_select_direction: 'Agent 分析价值并选择内容方向',
  analyze_content_value: 'Agent 分析内容价值',
  select_content_direction: 'Agent 确定内容方向',
  match_combination_group: '固定规则匹配组合组',
  explain_strategy: 'Agent 解释策略',
  resolve_formula_requirements: '解析公式所需事实',
  collect_missing_evidence: 'Agent 收集缺失证据',
  confirm_high_risk_facts: '人工确认高风险事实',
  freeze_evidence_bundle: '冻结证据包',
  prepare_formula_selection: '校验有效公式对',
  rank_formula_candidates: 'Agent 排序公式候选',
  lock_formula_selection: '锁定标题与正文公式',
  resolve_product_material_requirements: '解析产品资料需求',
  collect_strategy_product_evidence: '调研 Agent 定向检索产品资料',
  confirm_strategy_product_facts: '人工确认产品高风险事实',
  freeze_product_evidence_bundle: '冻结产品证据快照',
  generate_title_candidates: '标题 Agent 生成候选',
  validate_title_candidates: '校验标题候选',
  select_title: '标题 Agent 选择最终标题',
  build_outline: '正文 Agent 构建大纲',
  generate_body: '正文 Agent 生成正文',
  persona_style_polish: '按人设润色表达',
  generate_content: '内容 Agent 按公式生成标题与正文',
  adapt_to_channel: '适配发布渠道',
  deterministic_validate: '执行确定性校验',
  semantic_review: '审核 Agent 复核内容',
  revise_if_needed: '按失败原因定点回修',
  human_content_approval: '人工批准最终文案',
  save_artifact_snapshot: '保存统一内容版本'
}

const RUNTIME_EVENT_PRESENTATION = {
  'content.agent.started': { status: 'running', label: 'Agent 开始执行' },
  'content.agent.completed': { status: 'completed', label: 'Agent 执行完成' },
  'content.agent.failed': { status: 'failed', label: 'Agent 执行失败' },
  'content.skill.activated': { status: 'completed', label: 'Skill 已激活' },
  'content.tool.called': { status: 'running', label: '工具调用中' },
  'content.tool.completed': { status: 'completed', label: '工具调用完成' },
  'content.tool.failed': { status: 'failed', label: '工具调用失败' },
  'content.tool.rejected': { status: 'failed', label: '工具调用被拒绝' },
  'content.knowledge.retrieved': { status: 'completed', label: '知识库检索完成' }
}

const runtimeEventDetail = (eventType, payload) => {
  if (eventType.startsWith('content.agent.')) return payload.agent_slug || '内容 Agent'
  if (eventType === 'content.skill.activated') {
    return [payload.skill_slug, payload.skill_version].filter(Boolean).join(' · ')
  }
  if (eventType.startsWith('content.tool.')) {
    const detail = [payload.tool_name, payload.output_contract].filter(Boolean).join(' · ')
    return payload.error_type ? `${detail} · ${payload.error_type}` : detail
  }
  if (eventType === 'content.knowledge.retrieved') {
    return `${payload.knowledge_base_id || '知识库'} · 返回 ${payload.result_count || 0} 条结果`
  }
  return ''
}

export const buildContentRuntimeTimeline = (runEvents = [], auditEvents = []) => {
  const nodeEvents = runEvents.map((event, index) => ({
    id: `node-${event.run_id || 'run'}-${event.node_id}-${index}`,
    status: event.status || 'pending',
    label: CONTENT_WORKFLOW_NODE_LABELS[event.node_id] || event.node_id,
    detail:
      event.status === 'completed'
        ? '节点处理完成'
        : event.status === 'failed'
          ? event.error_message || event.error_type || '节点执行失败'
          : '节点正在处理',
    createdAt: event.created_at || null,
    order: event.created_at || `0-${String(index).padStart(6, '0')}`
  }))
  const runtimeEvents = auditEvents
    .filter((event) => RUNTIME_EVENT_PRESENTATION[event?.event_type])
    .map((event, index) => {
      const presentation = RUNTIME_EVENT_PRESENTATION[event.event_type]
      return {
        id: `runtime-${event.run_id || 'run'}-${event.seq || index}`,
        status: presentation.status,
        label: presentation.label,
        detail: runtimeEventDetail(event.event_type, event.payload || {}),
        nodeLabel: CONTENT_WORKFLOW_NODE_LABELS[event.payload?.node_id] || event.payload?.node_id || '',
        durationMs: event.payload?.duration_ms,
        createdAt: event.created_at || null,
        order: event.created_at || event.seq || `1-${String(index).padStart(6, '0')}`
      }
    })

  return [...nodeEvents, ...runtimeEvents].sort((left, right) => left.order.localeCompare(right.order))
}

export const buildFormulaPresentation = (strategy = {}, type) => {
  const formula = type === 'title' ? strategy.title_formula : strategy.body_formula
  if (!formula?.name) return { name: '-', detail: '' }
  const detail =
    type === 'title'
      ? formula.core_goal || ''
      : (formula.structure_schema || []).filter(Boolean).join(' → ')
  return { name: formula.name, detail }
}

export const CONTENT_WORKFLOW_GROUPS = [
  {
    id: 'prepare',
    label: '准备资料',
    description: '锁定运行配置并整理真实素材与证据',
    nodes: ['compile_runtime_snapshot', 'ingest_real_materials', 'normalize_evidence']
  },
  {
    id: 'strategy',
    label: '确定策略与公式',
    description: 'Agent 一次选择创作手法与公式，固定规则负责校验锁定',
    nodes: [
      'select_creation_strategy',
      'lock_creation_strategy',
      'collect_missing_evidence',
      'confirm_high_risk_facts',
      'freeze_evidence_bundle'
    ],
    steps: [
      {
        id: 'select_creation_strategy',
        label: 'Agent 匹配创作手法、标题公式和正文公式',
        nodes: ['select_creation_strategy']
      },
      {
        id: 'lock_creation_strategy',
        label: '固定规则校验并锁定策略',
        nodes: ['lock_creation_strategy']
      },
      {
        id: 'supplement_evidence',
        label: '按缺失情况补充证据',
        nodes: ['collect_missing_evidence', 'confirm_high_risk_facts', 'freeze_evidence_bundle']
      }
    ]
  },
  {
    id: 'creation',
    label: '生成标题与正文',
    description: '内容 Agent 按已锁定公式一次生成并完成渠道适配',
    nodes: ['generate_content', 'adapt_to_channel']
  },
  {
    id: 'review',
    label: '质量校验与保存',
    description: '执行硬性校验、语义审核、人工审批并保存内容版本',
    nodes: [
      'deterministic_validate',
      'semantic_review',
      'revise_if_needed',
      'human_content_approval',
      'save_artifact_snapshot'
    ]
  }
]

const resolveGroupStatus = (nodes) => {
  if (nodes.some((node) => node.status === 'failed')) return 'failed'
  if (nodes.some((node) => node.status === 'running')) return 'running'
  if (nodes.every((node) => node.status === 'completed')) return 'completed'
  if (nodes.some((node) => node.status === 'completed')) return 'active'
  return 'pending'
}

const LEGACY_STRATEGY_STEPS = [
  { id: 'analyze_content_value', label: 'Agent 分析内容价值', nodes: ['analyze_content_value'] },
  { id: 'select_content_direction', label: 'Agent 确定内容方向', nodes: ['select_content_direction'] },
  { id: 'match_combination_group', label: '固定规则匹配组合组', nodes: ['match_combination_group'] },
  { id: 'explain_strategy', label: 'Agent 解释策略', nodes: ['explain_strategy'] },
  { id: 'resolve_formula_requirements', label: '解析公式所需事实', nodes: ['resolve_formula_requirements'] },
  { id: 'collect_missing_evidence', label: 'Agent 收集缺失证据', nodes: ['collect_missing_evidence'] },
  { id: 'confirm_high_risk_facts', label: '人工确认高风险事实', nodes: ['confirm_high_risk_facts'] },
  { id: 'freeze_evidence_bundle', label: '冻结证据包', nodes: ['freeze_evidence_bundle'] },
  { id: 'rank_formula_candidates', label: 'Agent 排序公式候选', nodes: ['rank_formula_candidates'] },
  { id: 'lock_formula_selection', label: '锁定标题与正文公式', nodes: ['lock_formula_selection'] }
]

const resolveStepStatus = (nodeIds, eventByNode) => {
  const statuses = nodeIds.map((id) => eventByNode.get(id)?.status || 'pending')
  if (statuses.includes('failed')) return 'failed'
  if (statuses.includes('running')) return 'running'
  if (statuses.every((status) => status === 'completed')) return 'completed'
  if (statuses.includes('completed')) return 'running'
  return 'pending'
}

export const buildContentWorkflowGroups = (runEvents = []) => {
  const eventByNode = new Map()
  runEvents.forEach((event) => {
    if (event?.node_id) eventByNode.set(event.node_id, event)
  })

  const usesLegacyStrategy =
    !eventByNode.has('select_creation_strategy') &&
    ['analyze_content_value', 'select_content_direction', 'explain_strategy'].some((id) => eventByNode.has(id))
  const groups = CONTENT_WORKFLOW_GROUPS.map((group) => {
    const steps =
      group.id === 'strategy' && usesLegacyStrategy
        ? LEGACY_STRATEGY_STEPS
        : group.steps || group.nodes.map((id) => ({ id, label: CONTENT_WORKFLOW_NODE_LABELS[id], nodes: [id] }))
    const nodes = steps.map((step) => ({
      id: step.id,
      label: step.label,
      status: resolveStepStatus(step.nodes, eventByNode)
    }))
    const completedCount = nodes.filter((node) => node.status === 'completed').length
    const currentNode =
      nodes.find((node) => ['failed', 'running'].includes(node.status)) ||
      nodes.find((node) => node.status !== 'completed') ||
      nodes.at(-1)

    const status = resolveGroupStatus(nodes)
    const currentText =
      status === 'completed'
        ? `已完成 ${nodes.length} 个内部节点`
        : status === 'pending'
          ? `等待：${currentNode.label}`
          : `当前：${currentNode.label}`

    return {
      ...group,
      nodes,
      status,
      completedCount,
      totalCount: nodes.length,
      currentNode,
      currentText
    }
  })

  const openIndex = groups.findIndex((group) =>
    ['failed', 'running', 'active'].includes(group.status)
  )
  const firstPendingIndex = groups.findIndex((group) => group.status === 'pending')
  const defaultOpenIndex = openIndex >= 0 ? openIndex : firstPendingIndex

  return groups.map((group, index) => ({
    ...group,
    isOpen: index === defaultOpenIndex
  }))
}
