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
  'content.knowledge.retrieved': { status: 'completed', label: '知识库检索完成' },
  'content.validation.completed': { status: 'completed', label: '规则校验完成' }
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
    return `${payload.knowledge_base_id || '知识库'} · ${payload.query_text || '执行检索'} · 返回 ${payload.result_count || 0} 条结果`
  }
  if (eventType === 'content.validation.completed') {
    return `${payload.status || '已完成'} · ${payload.check_count || 0} 项检查`
  }
  return ''
}

export const buildContentRuntimeTimeline = (runEvents = [], auditEvents = []) => {
  const nodeEvents = runEvents.map((event, index) => ({
    id: `node-${event.run_id || 'run'}-${event.node_id}-${index}`,
    nodeId: event.node_id,
    eventType: 'content.node.status',
    status: event.status || 'pending',
    label: CONTENT_WORKFLOW_NODE_LABELS[event.node_id] || event.node_id,
    detail:
      event.status === 'completed'
        ? '节点处理完成'
        : event.status === 'failed'
          ? event.error_message || event.error_type || '节点执行失败'
          : '节点正在处理',
    outputPreview: event.output_preview || event.output_snapshot || null,
    createdAt: event.created_at || null,
    order: event.created_at || `0-${String(index).padStart(6, '0')}`
  }))
  const runtimeEvents = auditEvents
    .filter((event) => RUNTIME_EVENT_PRESENTATION[event?.event_type])
    .map((event, index) => {
      const presentation = RUNTIME_EVENT_PRESENTATION[event.event_type]
      return {
        id: `runtime-${event.run_id || 'run'}-${event.seq || index}`,
        nodeId: event.payload?.node_id || '',
        eventType: event.event_type,
        status: presentation.status,
        label: presentation.label,
        detail: runtimeEventDetail(event.event_type, event.payload || {}),
        nodeLabel: CONTENT_WORKFLOW_NODE_LABELS[event.payload?.node_id] || event.payload?.node_id || '',
        durationMs: event.payload?.duration_ms,
        inputPreview: event.payload?.input_preview || null,
        outputPreview: event.payload?.output_preview || null,
        knowledgeResults: event.payload?.results || [],
        queryText: event.payload?.query_text || '',
        resultCount: Number(event.payload?.result_count || 0),
        checkCount: Number(event.payload?.check_count || 0),
        validationStatus: event.payload?.status || '',
        createdAt: event.created_at || null,
        order: event.created_at || event.seq || `1-${String(index).padStart(6, '0')}`
      }
    })

  const uniqueEvents = new Map()
  for (const event of [...nodeEvents, ...runtimeEvents]) uniqueEvents.set(event.id, event)
  return [...uniqueEvents.values()].sort((left, right) => left.order.localeCompare(right.order))
}

const NODE_PROGRESS_NARRATIVES = {
  compile_runtime_snapshot: '正在整理本次任务的渠道要求、内容目标和可用资源。',
  ingest_real_materials: '正在读取品牌资料、业务事实和用户提供的素材。',
  normalize_evidence: '正在核对事实来源，筛除重复或不能直接用于创作的信息。',
  select_creation_strategy: '正在结合目标受众、业务优势和现有证据，判断最值得表达的内容方向。',
  lock_creation_strategy: '正在核对所选方向与创作公式是否满足渠道和证据约束。',
  collect_missing_evidence: '正在检查创作所需事实，并补充影响内容可信度的资料。',
  confirm_high_risk_facts: '正在确认价格、效果和承诺类信息，避免使用未经确认的高风险表述。',
  freeze_evidence_bundle: '正在汇总本次可引用的事实，确保后续生成只使用已确认资料。',
  generate_content: '正在把已确认的策略和事实组织成标题、正文结构与发布话题。',
  adapt_to_channel: '正在调整内容长度、语气和排版，使其适合目标发布渠道。',
  deterministic_validate: '正在检查标题长度、正文结构、事实引用和发布规格。',
  semantic_review: '正在复核内容是否准确、有价值，并排查夸大或含糊表达。',
  revise_if_needed: '正在根据审核发现的问题定点修改内容。',
  human_content_approval: '内容已完成自动审核，正在等待最终确认。',
  save_artifact_snapshot: '正在保存最终内容和本次生成记录。',
  analyze_content_value: '正在从业务事实中识别最值得用户关注的价值点。',
  select_content_direction: '正在比较候选方向与目标受众、内容目标的匹配程度。',
  match_combination_group: '正在匹配适合当前内容方向的表达方式。',
  explain_strategy: '正在整理本次创作策略的选择依据和风险边界。',
  resolve_formula_requirements: '正在核对标题和正文公式需要哪些事实支撑。',
  rank_formula_candidates: '正在比较候选公式与现有证据的匹配程度。',
  lock_formula_selection: '正在锁定最适合本次内容的标题和正文结构。',
  generate_title_candidates: '正在根据已确认事实生成可发布的标题。',
  validate_title_candidates: '正在检查标题是否准确、清晰并符合发布限制。',
  select_title: '正在从合格候选中选择信息价值最高的标题。',
  build_outline: '正在根据正文公式组织内容层次和事实顺序。',
  generate_body: '正在把大纲和证据扩展为完整正文。',
  persona_style_polish: '正在保持事实不变的前提下统一表达语气。'
}

const normalizeNarrativeText = (value, maxLength = 600) => {
  const text = String(value || '')
    .replace(/\s+/g, ' ')
    .trim()
  if (!text) return ''
  return text.length <= maxLength ? text : `${text.slice(0, maxLength)}…`
}

const asTextList = (value, maxItems = 4) =>
  (Array.isArray(value) ? value : [])
    .map((item) => normalizeNarrativeText(item, 160))
    .filter(Boolean)
    .slice(0, maxItems)

export const buildContentNarrativeCodeLabels = (ruleBundle = {}) => {
  const labels = {}
  if (!ruleBundle || typeof ruleBundle !== 'object' || Array.isArray(ruleBundle)) return labels
  for (const item of [
    ...(ruleBundle.content_types || []),
    ...(ruleBundle.methods || []),
    ...(ruleBundle.title_formulas || []),
    ...(ruleBundle.content_formulas || [])
  ]) {
    if (item?.code && item?.name) labels[String(item.code).toUpperCase()] = item.name
  }
  return labels
}

const explainNarrativeCodes = (value, codeLabels) =>
  String(value || '')
    .replace(/\b(?:CT|M|S|T|C)\d{2}\b/g, (code, offset, source) => {
      const label = codeLabels[code]
      if (!label) return code
      const followingText = source.slice(offset + code.length).trimStart().replace(/^[（(]/, '')
      return followingText.startsWith(label) ? code : `${code}（${label}）`
    })
    .replace(/）\s+(?=[\u3400-\u9fff])/g, '）')

const outputNarratives = (preview) => {
  if (!preview || typeof preview !== 'object' || Array.isArray(preview)) return []
  const lines = []
  const add = (text) => {
    const normalized = normalizeNarrativeText(text)
    if (normalized) lines.push(normalized)
  }

  const valuePoints = asTextList(preview.value_points)
  if (valuePoints.length) add(`识别出的内容价值：${valuePoints.join('；')}。`)

  const reason =
    preview.selection_reason || preview.reason || preview.reasoning || preview.explanation
  if (reason) add(`判断依据：${reason}`)

  const evidenceItems = Array.isArray(preview.evidence_items) ? preview.evidence_items : []
  if (evidenceItems.length) {
    const facts = evidenceItems
      .map((item) => normalizeNarrativeText(item?.value, 140))
      .filter(Boolean)
      .slice(0, 3)
    add(
      `补充了 ${evidenceItems.length} 条可用事实${facts.length ? `，包括：${facts.join('；')}` : ''}。`
    )
  }

  const unresolvedQuestions = asTextList(preview.unresolved_questions)
  if (unresolvedQuestions.length) add(`仍需确认：${unresolvedQuestions.join('；')}。`)

  const title =
    typeof preview.title === 'string'
      ? preview.title
      : preview.title?.text || preview.selected_title?.text
  if (title) add(`标题已生成：${title}`)

  const outline = preview.outline?.sections || preview.sections
  const outlineGoals = (Array.isArray(outline) ? outline : [])
    .map((item) => normalizeNarrativeText(item?.goal || item?.text || item, 120))
    .filter(Boolean)
    .slice(0, 5)
  if (outlineGoals.length) add(`正文将依次说明：${outlineGoals.join('；')}。`)

  const draft = preview.draft || preview.content_draft || {}
  const body =
    preview.polished_body || preview.body || (typeof draft === 'string' ? draft : draft.body)
  if (body) add(`正文内容：${normalizeNarrativeText(body, 1200)}`)

  const topics = asTextList(preview.topics || draft.topics, 10)
  if (topics.length) add(`建议话题：${topics.map((item) => (item.startsWith('#') ? item : `#${item}`)).join(' ')}`)

  const changeSummary = asTextList(preview.change_summary)
  if (changeSummary.length) add(`本轮修改：${changeSummary.join('；')}。`)

  const checks = Array.isArray(preview.checks) ? preview.checks : []
  const issues = checks
    .filter((item) => item?.status !== 'passed')
    .map((item) => normalizeNarrativeText(item?.message || item?.suggestion, 160))
    .filter(Boolean)
    .slice(0, 4)
  if (checks.length && !issues.length) add(`已完成 ${checks.length} 项内容检查，未发现阻断问题。`)
  if (issues.length) add(`审核发现：${issues.join('；')}。`)

  const risks = asTextList(preview.risks)
  if (risks.length) add(`需要注意：${risks.join('；')}。`)
  return lines
}

export const buildContentNarrativeStream = (activities = [], codeLabels = {}) => {
  const lines = []
  const seen = new Set()
  const add = (id, text, tone = 'normal') => {
    const normalized = explainNarrativeCodes(normalizeNarrativeText(text, 1400), codeLabels)
    if (!normalized || seen.has(normalized)) return
    seen.add(normalized)
    lines.push({ id, text: normalized, tone })
  }

  for (const activity of activities) {
    if (activity.status === 'failed') {
      add(activity.id, `执行遇到问题：${activity.detail || '当前内容未能继续生成。'}`, 'error')
      continue
    }
    if (activity.eventType === 'content.knowledge.retrieved') {
      const snippets = (activity.knowledgeResults || [])
        .map((item) => normalizeNarrativeText(item?.content, 180))
        .filter(Boolean)
        .slice(0, 2)
      const query = normalizeNarrativeText(activity.queryText, 120)
      add(
        activity.id,
        `${query ? `围绕“${query}”` : ''}检索到 ${activity.resultCount} 条相关资料${snippets.length ? `，其中有价值的信息是：${snippets.join('；')}` : ''}。`
      )
      continue
    }
    if (activity.eventType === 'content.validation.completed') {
      const passed = ['passed', 'completed'].includes(activity.validationStatus)
      add(
        activity.id,
        `已完成 ${activity.checkCount} 项规则检查，${passed ? '没有发现阻断问题' : '仍有需要处理的问题'}。`,
        passed ? 'success' : 'warning'
      )
      continue
    }
    if (
      activity.eventType === 'content.agent.started' ||
      (activity.eventType === 'content.node.status' && activity.status === 'running')
    ) {
      add(activity.id, NODE_PROGRESS_NARRATIVES[activity.nodeId])
    }
    if (activity.outputPreview) {
      outputNarratives(activity.outputPreview).forEach((text, index) =>
        add(`${activity.id}-output-${index}`, text, 'result')
      )
    }
  }
  return lines
}

export const appendContentNarrativeText = (currentLines = [], narrativeItems = []) => {
  const lines = [...currentLines]
  const seen = new Set(lines)
  for (const item of narrativeItems) {
    if (!item?.text || seen.has(item.text)) continue
    seen.add(item.text)
    lines.push(item.text)
  }
  return lines
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

export const buildContentWorkflowGroups = (runEvents = [], auditEvents = []) => {
  const eventByNode = new Map()
  runEvents.forEach((event) => {
    if (event?.node_id) eventByNode.set(event.node_id, event)
  })
  const runtimeTimeline = buildContentRuntimeTimeline(runEvents, auditEvents)

  const usesLegacyStrategy =
    !eventByNode.has('select_creation_strategy') &&
    ['analyze_content_value', 'select_content_direction', 'explain_strategy'].some((id) => eventByNode.has(id))
  const groups = CONTENT_WORKFLOW_GROUPS.map((group) => {
    const steps =
      group.id === 'strategy' && usesLegacyStrategy
        ? LEGACY_STRATEGY_STEPS
        : group.steps || group.nodes.map((id) => ({ id, label: CONTENT_WORKFLOW_NODE_LABELS[id], nodes: [id] }))
    const nodes = steps.map((step) => {
      const activities = runtimeTimeline.filter((item) => step.nodes.includes(item.nodeId))
      return {
        id: step.id,
        label: step.label,
        status: resolveStepStatus(step.nodes, eventByNode),
        activities,
        activity: activities.at(-1) || null
      }
    })
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

export const formatElapsedDuration = (durationMs) => {
  const value = Number(durationMs)
  if (!Number.isFinite(value) || value < 0) return '--'
  const totalSeconds = Math.floor(value / 1000)
  if (totalSeconds < 1) return '不到 1 秒'
  const seconds = totalSeconds % 60
  const totalMinutes = Math.floor(totalSeconds / 60)
  const minutes = totalMinutes % 60
  const hours = Math.floor(totalMinutes / 60)
  if (hours > 0) return `${hours}小时${minutes}分${seconds}秒`
  if (minutes > 0) return `${minutes}分${seconds}秒`
  return `${seconds}秒`
}

export const buildContentCompletionSummary = (
  nodeEvents = [],
  auditEvents = [],
  delegatedAgents = []
) => {
  const latestNodes = new Map()
  nodeEvents.forEach((item) => {
    if (item?.node_id) latestNodes.set(item.node_id, item)
  })

  const skills = new Map()
  const knowledgeBases = new Map()
  auditEvents.forEach((event) => {
    const payload = event?.payload || {}
    if (event?.event_type === 'content.skill.activated' && payload.skill_slug) {
      const key = `${payload.skill_slug}:${payload.skill_version || ''}`
      const item = skills.get(key) || {
        slug: payload.skill_slug,
        version: payload.skill_version || '',
        activations: 0,
        nodes: new Set()
      }
      item.activations += 1
      if (payload.node_id) {
        item.nodes.add(CONTENT_WORKFLOW_NODE_LABELS[payload.node_id] || payload.node_id)
      }
      skills.set(key, item)
    }

    if (event?.event_type === 'content.knowledge.retrieved' && payload.knowledge_base_id) {
      const id = String(payload.knowledge_base_id)
      const item = knowledgeBases.get(id) || {
        id,
        retrievals: 0,
        resultCount: 0,
        sourceIds: new Set(),
        nodes: new Set()
      }
      item.retrievals += 1
      item.resultCount += Number(payload.result_count || 0)
      for (const sourceId of payload.source_ids || []) item.sourceIds.add(sourceId)
      if (payload.node_id) {
        item.nodes.add(CONTENT_WORKFLOW_NODE_LABELS[payload.node_id] || payload.node_id)
      }
      knowledgeBases.set(id, item)
    }
  })

  delegatedAgents.forEach((agent) => {
    if (agent?.status !== 'completed') return
    for (const skill of agent.runtime_config_snapshot?.skills || []) {
      if (!skill?.slug) continue
      const key = `${skill.slug}:${skill.version || ''}`
      const item = skills.get(key) || {
        slug: skill.slug,
        version: skill.version || '',
        activations: 1,
        nodes: new Set()
      }
      if (agent.node_id) {
        item.nodes.add(CONTENT_WORKFLOW_NODE_LABELS[agent.node_id] || agent.node_id)
      }
      skills.set(key, item)
    }
  })

  const normalizedSkills = [...skills.values()].map((item) => ({
    ...item,
    nodes: [...item.nodes]
  }))
  const normalizedKnowledgeBases = [...knowledgeBases.values()].map((item) => ({
    ...item,
    sourceCount: item.sourceIds.size,
    sourceIds: [...item.sourceIds],
    nodes: [...item.nodes]
  }))

  return {
    completedNodes: [...latestNodes.values()].filter((item) => item.status === 'completed').length,
    totalNodes: latestNodes.size,
    agentRuns: auditEvents.filter((item) => item.event_type === 'content.agent.started').length,
    skillCount: normalizedSkills.length,
    knowledgeBaseCount: normalizedKnowledgeBases.length,
    knowledgeResultCount: normalizedKnowledgeBases.reduce(
      (total, item) => total + item.resultCount,
      0
    ),
    skills: normalizedSkills,
    knowledgeBases: normalizedKnowledgeBases
  }
}
