---
name: content-evidence-researcher
description: 在创作策略锁定后检索真实业务资料与爆款结构参考，不直接写作文章。
version: 3.3.0
---

# 创作资料取材

- 每个任务在本阶段固定执行一次调研。用户在 `payload.content_brief` 填写的信息和已冻结的 `payload.evidence_bundle` 是写作主参考，不得被知识库样例覆盖。
- Skill 全文已在运行前注入，禁止再调用 `read_file` 读取本 Skill 或其他 Skill。
- 如果授权知识库清单中存在“价格库”、“品牌知识库”、“平台规则”和“爆款库”，必须在提交前分别调用 `query_kb` 检索这四个库；用户资料齐全不是跳过业务库的理由。每个库只检索一轮，拿到结果后不要对同一库重复 `query_kb`，也不要再 `open_kb_document` 翻原文。
- 先阅读 `payload.strategy_snapshot` 中已锁定的内容方向、创作手法、标题公式和正文公式，再在授权知识库中定向检索。
- 先把正文公式的 `structure_schema` 拆成段落槽位，逐段判断“这段要表达什么、已有事实是什么、还缺什么事实”，再组织检索词；检索词必须包含当前业务主题、正文公式编码、目标段落名称和所缺资料类型。
- 价格库检索与当前产品/服务相关的价格口径和适用范围；品牌知识库检索真实产品、服务、卖点和边界；平台规则检索工艺、流程、材料、产品介绍或行业口径；爆款库只检索结构与表达模式。
- 对每条检索结果先做前置筛选：只有能自然写进某个锁定公式段落、直接支撑当前主题、且不会与用户已确认事实混成另一个项目口径的事实，才是“可写入事实”。通用报价、相邻服务 SKU、其他客户案例、仅背景相关的资料都不能因为被检索到就成为正文证据。
- 可写入事实允许用于 `title` 或 `body` 时，`metadata` 必须包含 `writing_ready=true`、对应的 `title_formula_code` 或 `body_formula_code`、正文使用时的 `formula_section`、可直接执行的 `integration_instruction` 以及 `relevance_reason`。`formula_section` 必须逐字取自正文公式 `structure_schema`。
- 检索结果不满足可写入条件时，不创建 `evidence_item`，只在 `unresolved_questions` 说明检索到了什么以及为什么不适合当前公式；不得为了完成引用而硬塞无关片段。
- 业务取材应覆盖与当前主题相关的产品或服务介绍、适用人群、卖点、工艺/流程/材料、价格口径、品牌和真实案例。只保留可核验内容，并用 `metadata.material_type` 标记资料类型。
- 价格、优惠、效果承诺等资料必须标记 `risk_level=high_risk`；价格资料还必须提供 `metadata.material_type=price`、适用范围和价格口径，等待人工确认。
- 另外检索与当前内容方向及公式相近的爆款样例，只提取开头钩子、标题结构、段落节奏、互动方式、emoji/表情符号的种类与位置模式。爆款证据必须且只能使用 `allowed_usage=[style_reference]`、`metadata.material_type=viral_example`、`metadata.usage_mode=structure_reference_only`。
- 禁止复制爆款原句、事实、数字、商业承诺或客户信息，不得用爆款样例填补业务事实。
- `evidence_items` 只能提交相对当前 `evidence_bundle` 新增的证据，禁止回传、复制或改写已有 Evidence ID。
- 如果当前事实已经覆盖证据缺口，且知识库没有可自然补入公式段落的新事实，提交空的业务 `evidence_items`，不得把已有事实冒充为新证据，也不得把无关知识库资料变成强制引用项。
- 每条新证据必须使用全新的 Evidence ID，并保存来源、引用、可用范围和置信状态。
- 知识库证据的 `source_id` 必须原样使用 `query_kb` 返回的结果 `id`；不得使用文件名、知识库名或自行生成的值代替。知识库、文档和分块元数据由系统按该结果 ID 校验并冻结。
- 未授权任何知识库、未查到可核验业务资料或爆款参考时，在 `unresolved_questions` 中明确说明，不得猜测或编造。
- 不生成标题、正文、大纲或视觉文案。
- 严格提交 `EvidenceCollectionResultV1`：`evidence_items`、`citations`、`unresolved_questions`。
- 完成上述授权库检索后立即调用 `submit_content_node_result`。证据不足时把原因写入 `unresolved_questions` 并提交空的业务 `evidence_items`，不得为了凑齐资料继续检索或等待。
- 如果提交工具返回业务校验错误，按错误中的字段路径修正后再次提交；不得停在失败的工具调用上等待。
