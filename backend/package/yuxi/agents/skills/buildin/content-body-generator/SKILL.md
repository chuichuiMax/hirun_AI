---
name: content-body-generator
description: 使用人工锁定标题和同一份 ContentBrief、StrategyPlan、EvidenceBundle 生成正文与话题。仅在 Yuxi 内容工作流的正文生成或定向重写节点使用。
version: 2.6.2
---

# 正文与话题生成

1. 只读取当前节点 `payload`；在简化工作流中与标题、大纲一次生成并保持一致。
   - 若 `payload.content_brief.form_values.mp_service_entry` 为「好评笔记」：必须先用授权清单中的 `kb_id` 调用 `query_kb` 检索「好评知识库」或「好评笔记知识库」，模仿已有好评的语气、段落节奏与用词；事实只来自简报与证据中的项目成员、地点与现场信息；忽略 `body_formula` / `body_calling` / `formula_lexicon_bundle`；业主第一人称评价，不要获客种草。然后按第 8 条及之后控制篇幅并提交。
   - 若 `payload.content_brief.form_values.mp_service_entry` 为「装修家居」：遵守 `writing_instruction`；**不要**展开某套房的案例故事（旧况→改造过程→完工效果）；信息卡点优先写出小区名称、房屋面积、房屋布局（仅简报有填时）、风格、项目施工鸿扬家装；必须写鸿扬家居/鸿扬家装品牌优势（**定制化家装**，禁止「整装」「标准化整装」），并带明确引流点（同城咨询、留言、评论区）；品牌或案例证明只作一句背书，不得编造户型缺陷与改造前后细节。
   - 若同时为「装修报价清单」/「报价清单」（`mp_content_type_name` 或 CT02）：费用数字只作参考卡点，**不以低价/性价比为正文主线**；正文重心落在鸿扬品牌优势（定制化家装、透明施工、规范工艺、售后与靠谱交付），再用咨询/留言引流；写清预算困扰可以，但结论应导向「选靠谱品牌与交付」，而不是「我们更便宜」；标题、正文、话题均不得写整装/标准化整装。
   - 若同时为「工艺施工展示」/「工艺展示」（`mp_content_type_name` 或 CT05）：正文主线是**工艺科普与标准讲解**，必须写清简报中的工艺类型、工艺名称（有填必写）及规范做法/关键细节；信息卡点可写小区/面积/风格/鸿扬家装施工，但**禁止**旧况→改造→完工的案例分享叙事，禁止虚构客户经历与前后对比故事；标题、正文、话题均不得写整装/标准化整装。
   - `payload.runtime_config_snapshot.creation_mode=original` 时，按锁定公式原创，不使用爆款结构参考。
   - `payload.runtime_config_snapshot.creation_mode=viral_rewrite` 时，必须使用冻结 EvidenceBundle 中唯一 `selected_reference=true` 的爆款结构蓝图组织标题、大纲和正文；只能仿写抽象结构、节奏、钩子和互动方式，业务事实仍只来自允许用于标题或正文的 Evidence。
2. 首次 `generate_content` 在同一次输出中生成大纲，并严格沿用该大纲；已有 `payload.content_outline` 且审核未要求调整结构时沿用已有大纲。按 `payload.strategy_snapshot.body_formula` 逐段兑现结构，并让 `creation_methods` 贯穿全文。
   - **装修家居（非好评笔记）**：首轮模型输出必须直接调用 `submit_content_node_result`；所需 Skill 已注入，禁止 `read_file`、禁止检索知识库、禁止先空转工具。
   - `payload.formula_lexicon_bundle.required=true` 时，必须读取 `formula_lexicon_bundle.body` 中全部指定词库，并按各段 `lexicon_calls` 只使用对应词库的表达词条；不得跳过、改用标题词库或凭记忆补词。词库原文若命中 `forbidden_replacement_map` 问题词，必须先按表内候选改写再写入成品，禁止原样粘贴问题词。
   - 当正文公式包含 `body_calling` 时，逐段执行其 `instruction` 和 `fill_rule`，只使用该段声明的 `lexicon_calls`；词库只决定表达，不得提供事实。
   - 若大纲选择了 `variant_key`，正文的反差段只能使用该维度，禁止混入其他反差逻辑。
   - 把正文实际采用的词库编码和原样词条写入 `draft.lexicon_usage`；必须覆盖各固定段落词库和所选 `variant_key` 对应词库，未实际使用的词条不得虚报。
3. **Evidence ID 协议（必须遵守，否则提交会被拒）：**
   - 优先读取 `payload.evidence_cite_index`（若有）：按 `allowed_usage` 含 `body` 的条目选用；没有索引时从 `payload.evidence_bundle.items` 自行筛选。
   - 只能把条目的 `id` 字段（形如 `ev_` + 十六进制）原样写入 `outline.sections[].evidence_ids` 与 `draft.paragraph_evidence[].evidence_ids`；禁止编造、缩写、拼接，禁止用 `source_id` / 字段名 / `source_hash` 当 ID。
   - 正文写到的每个事实数字或卡点（小区、面积区间、风格、预算、施工方等），必须挂载对应证据：用证据 `value` 原文或 `source_id`（如 `field_楼盘信息`、`field_外框面积`、`field_设计风格`）匹配后，复制该条 `id`。
   - 面积等字段必须**原样**使用证据/简报文本（如 `110-130㎡`），禁止改成中间值或另一写法（如 `130m²`、`120平`）。
   - `style_reference` / 爆款结构参考不得写入 `paragraph_evidence`。
   - 若存在可用于正文的业务知识证据（`source_type=knowledge_base` 且 `allowed_usage` 含 `body`，且 `material_type` 不是 viral/platform/compliance/forbidden），`paragraph_evidence` 中**至少引用其中一条**；价格知识证据所在段落还必须写出该证据中的具体价格值。
4. 按锁定公式需要，从 `payload.evidence_bundle` 植入产品卖点、适用人群、价格、品牌或短背书，只使用允许用于正文的证据。装修家居优先写简报已有字段与品牌优势、引流点，不以长篇案例证明替代信息卡点。引用知识库价格证据时，必须选择与当前内容相关的具体 SKU，并写出该 SKU 的明确价格和单位；不得只写“按元/平方米、元/项或元/间计价”“可参考价格表”“以实际为准”等空泛口径。若证据说明该价格不等同于本案总预算，应同时保留适用范围说明。
   - 标准单价可独立组成费用明细或工价清单，明确标注“标准单价参考”并保留项目、单位、范围。项目总预算可以另行展示，两者无需对应或加总一致；没有工程量、小计或某些类别的费用不影响展示已有单价。不得为了凑总预算倒推单价、工程量或小计，也不得称为本案实际成交/结算明细。适用范围说明写在价格清单附近，不要用索要实际成交价的提示替代正文中的具体单价。
5. `style_reference` 仅用于开头钩子、结构、节奏、互动方式和 emoji/表情符号位置模式参考；可沿用抽象模式，禁止复制原句、事实或数字，禁止写入 `paragraph_evidence`。
6. 只使用 `payload.evidence_bundle` 中允许用于正文的事实；不得调用业务事实或知识库工具，不得补造客户、价格、参数、统计或效果。好评笔记除外：允许检索「好评知识库」或「好评笔记知识库」作语气结构参考，但仍不得把知识库样例中的他人事实写成当前项目事实。
7. 正文和话题中的事实数字必须来自运行时提供的数字白名单，不得编造数字示例、对比数字或统计数字。只有冻结爆款蓝图的 `list_pattern.type=numbered` 或包含编号的 `mixed` 时，允许使用与参考一致的行首顺序编号；这些编号只承担结构导航，不得写进事实句或 Evidence。其他结构不得擅自添加阿拉伯数字或数字 Emoji 编号。
8. 输出前逐项核对正文和话题里的数字；发现白名单外数字时，删除数字或把句子改为不含数字的事实表达。
9. **平台封禁词（必须）：** 若 `evidence_bundle` 存在 `metadata.rule_kind=forbidden_replacement_map`，提交前按问题词长度从长到短扫描标题、正文和话题，命中则改用表内候选或重写整句；词库、写作说明中的示例词若与表冲突，以替换表为准。成品不得保留表内任一问题词。
10. 正文控制在 200～650 字；每个事实段落通过 `paragraph_evidence` 关联实际使用的 Evidence ID。关联价格知识证据的段落必须真实出现该证据中的至少一个具体价格值，不能只挂 Evidence ID。
   - 公式规定的是语义顺序，不要求把每个结构段写成单一长段。在 `generate_content` 节点中，原创正文内已有多个并列改造、材料或验收事项时，必须按已激活的 `viral-layout-formatter` 拆成逐项短行，并按 `content-human-expression` 给独立事项落实语义 Emoji；一组短行仍属于原结构段，证据引用保持对应，不能为了少换行或“平台无关”把条目重新合并。仿写继续保留冻结蓝图的列表类型。
11. 如果 `payload.validation_report.status=blocked` 或 `payload.review_report.status=blocked`，或提交工具返回未授权 Evidence ID 列表：一次修正**全部**错误位置；只从错误信息里的允许 ID 列表或 `evidence_cite_index` 逐字复制；保留仍然有效的知识库证据引用，不得清空后盲写。
12. 简化工作流严格提交 `GeneratedContentResultV1`，正文放入 `draft`；旧工作流仍提交 `ContentDraftResultV1`。

事实口径保持一致，呈现方式遵守当前 `channel_profile`：允许 Emoji 的社交渠道落实情绪与数据、事项导航，明确禁用时不用；不得用“平台无关”要求抹去渠道排版与人设表达。话题提供 3～8 个，不执行发布。
