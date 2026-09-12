---
name: content-reviewer
description: 审核 Yuxi 生成内容的创作手法贯穿、公式执行、事实一致性、人设语气和风险表达。仅在确定性校验完成后的内容审核节点使用。
version: 1.10.2
---

# 内容审核

1. 当前节点 `payload` 必须包含 `content_draft`、`selected_title`、`content_outline`、`strategy_snapshot`、`validation_report` 和 `evidence_bundle`；缺少任一必需输入时直接报告契约错误，不得猜测补齐。
2. 先确认 `validation_report.status` 为 `passed` 或 `warning`。若它为 `blocked`，返回 `REVIEW_CONTRACT_INVALID`，因为确定性阻断不应进入本节点。
3. 对照 `strategy_snapshot` 检查创作手法、标题公式和正文结构，对照 ContentBrief 与 EvidenceBundle 检查事实、人设、语气和来源。
   - 若 `content_brief.form_values.mp_service_entry` 为「好评笔记」，只审业主第一人称、项目成员评价、事实一致性和风险，不得用装修获客标题公式（如细分人群＋数字＋结果）或正文公式（如人设沉淀分段、body_calling）阻断。标题不得出现楼盘、小区或项目案名（含简报「楼盘信息」及同类案名）；若标题含上述案名，以 `TITLE_FACT_UNSUPPORTED` 阻断并要求去掉案名；赞美表扬所属店面/门店允许，不得因此阻断。
   - 若 `content_brief.form_values.mp_service_entry` 为「装修家居」：标题若呈「楼盘/面积/风格」说明书式平铺、缺少情绪/悬念/反差/利益吸引点，以 `TITLE_FACT_UNSUPPORTED` 或 `PERSONA_STYLE_MISMATCH` 阻断并要求改出钩子；正文若展开某套房旧况改造完工案例故事，以 `FACT_CHECK_FAILED` 阻断并要求改为信息卡点；正文应能看到简报已有的小区、面积、风格与「鸿扬家装」施工归属，以及品牌优势与引流点；布局仅在简报有填时要求出现，不得因缺失布局字段而编造后通过。若标题、正文、话题或封面文案把鸿扬写成「整装」「标准化整装」或「全屋整装」，以 `PERSONA_STYLE_MISMATCH` 阻断并要求改为「定制化家装」。若内容类型为「装修报价清单」/「报价清单」：标题语义不清、词库硬拼看不懂时阻断；正文若以低价/更便宜为主卖点而弱化鸿扬品牌优势，以 `PERSONA_STYLE_MISMATCH` 阻断并要求改为品牌与交付优势收束。若内容类型为「工艺施工展示」/「工艺展示」：标题未点明工艺主题或词库硬拼看不懂时阻断；正文若写成案例分享（旧况→改造→完工）而弱化工艺类型/工艺名称与标准讲解，以 `FACT_CHECK_FAILED` 或 `PERSONA_STYLE_MISMATCH` 阻断并要求改为工艺科普主线。
   - 标注为“标准单价参考”的知识库价格可以独立展示，或与项目总预算并列；核对具体价格、单位、适用范围及来源即可。不得仅因没有工程量、分项小计、未覆盖全部类别或不与项目总预算加总一致而阻断、降级或要求补实际成交价。若把标准价写成实际成交/结算费用，或虚构工程量、小计来凑总预算，才按事实不一致阻断并指出具体句子。
   - 公式只决定信息顺序，不允许把“旧况、关键数据、过程、结果”等公式步骤写成读者可见的报幕句。
   - 出现“旧况很典型”“关键数据先摊开”“先说背景”“再看过程”“最后看结果”“下面来说”“接下来看看”等元话术，或多个段落使用相同模板句式开场时，必须以 `PERSONA_STYLE_MISMATCH` 阻断并给出直接进入场景或事实的改写建议。
   - 不得因为结构、事实和证据正确，就把明显的提纲填充、审核报告腔或机械连接词判为语气通过。
   - EvidenceBundle 存在 `selected_reference=true` 的爆款结构参考时，必须完整读取其 `reference_blueprint.title_slot_sequence`、`content_block_sequence`、`paragraph_rhythm`、`list_pattern`、`emoji_pattern` 和 `interaction_style`，逐项对照，禁止用审核器自己的通用爆款模板替代冻结蓝图。
   - 逐个检查 `content_block_sequence` 是否在正文中按序可识别，并按 `paragraph_rhythm` 检查真实换行和信息密度；只有蓝图实际要求数据块或列表时才检查这些形式。多个独立信息块被压成一行或结构节点缺失时，以 `CONTENT_STRUCTURE_MISMATCH` 阻断。
   - 列表审核严格服从 `list_pattern`。只有 `type=numbered` 或包含编号的 `mixed` 才要求编号清单，并按蓝图的出现位置和条目节奏检查；`none`、`emoji`、`bulleted` 或不含编号的 `mixed` 不得强制改成 `1–4` 清单。不得设置固定段落数、双换行数或条目数。
   - 对照 `reference_blueprint.emoji_pattern` 判断叙事分散型、清单连续型或混合型。叙事参考在句中、句末或转折处使用 Emoji 时，逐个核对符号的相邻语义锨点和相对位置；若成稿把符号全部机械移到自然段开头、句号前或自然段末尾，必须以 `PERSONA_STYLE_MISMATCH` 阻断。费用、材料、步骤或改造清单参考连续使用行首 Emoji 时，应判定为合理的信息导航，不得因为符号连续就阻断。
   - 原创和仿写都按当前正文检查 Emoji 功能覆盖，不按总数或参考密度判定完成：已有痛点、情感变化或人设判断是否有贴切表达，面积/预算/时间等实际数据类别是否分别导航，已有事项列表是否逐项或按明确同类分组导航，提醒与互动是否落在相邻语义处。没有对应内容、渠道或用户明确禁用时不要求使用；专业人设、参考无表情不构成豁免。
   - 正文包含上述多类功能却只有场景、确认、互动三个装饰，或数据/事项全靠一个 Emoji 代表、情绪表达只用数据图标冒充时，以 `PERSONA_STYLE_MISMATCH` 阻断；`location` 指向遗漏的实际短语或条目，`suggestion` 给出适合该人设的功能与落点，不下达全篇固定数量要求。补齐只改符号和必要措辞，不改事实、数字、结构顺序或列表类型；不能因符号数量多而删除有用的逐项导航。
   - 对照 `content_brief` 和允许用于标题的 Evidence 逐项检查标题事实槽位。标题把预算扩大为已在预算内完成、把预计工期扩大为已完工、把方案效果扩大为最终结算或出现其他输入外事实时，以 `TITLE_FACT_UNSUPPORTED` 阻断，并精确指出应删除或改写的词；不得仅给出“标题不符合公式”的泛化建议。
   - EvidenceBundle 存在 `metadata.rule_kind=forbidden_replacement_map` 的平台规则时，从其结构化 `value` 读取完整“问题词—常用表达方式”映射，逐项复查最终标题、正文和话题，不得使用 Skill 内置词表或常识猜测替换关系。确定性校验已拦截的问题词仍须在建议中给出表内候选；若校验漏检而成品仍含问题词，必须以 `FACT_CHECK_FAILED` 阻断。
   - 最终内容仍含任一问题词时，以 `FACT_CHECK_FAILED` 阻断，并在建议中列出命中的问题词和表内可选表达；候选列表为空时只要求在不改变事实的前提下重写整句，不得建议删除后留下残句或编造表外替代词。
   - 已替换但出现候选堆叠、语法不通、语义错位或业务事实改变时，也以 `FACT_CHECK_FAILED` 阻断。替换用的 Emoji 仅承担敏感表达改写功能，不得误算为爆款蓝图要求的情绪或导航 Emoji。
4. 不调用 `validate_content_facts`，不重复实现敏感词、必填字段、数字来源等确定性校验；把 `validation_report` 作为已有事实合并考虑。
5. 返回 `status`、`checks` 和 `evidence_conflicts`。状态只能为 `passed`、`warning`、`blocked`。
6. 每项检查必须返回 `code`、`status`、`location`、`message`、`evidence_ids`、`suggestion`；不得使用 `level` 代替 `status`。
7. `evidence_ids` 可引用当前冻结 EvidenceBundle 中任何真实存在的证据，包括用于核对结构、节奏和 emoji 模式的 `style_reference`；不得引用未知 Evidence ID。
8. 顶层 `status` 必须与 `checks` 中最严重状态一致：存在 `blocked` 则为 `blocked`，否则存在 `warning` 则为 `warning`，其余为 `passed`。

允许用于定点回修的阻断 code 为 `TITLE_FORMULA_MISMATCH`、`BODY_FORMULA_MISMATCH`、`CONTENT_STRUCTURE_MISMATCH`、`PERSONA_TONE_MISMATCH`、`PERSONA_STYLE_MISMATCH`、`FACT_CHECK_FAILED`、`FACT_INCONSISTENT`、`TITLE_TOO_LONG`、`TITLE_TOO_SHORT`、`BODY_LENGTH_OUT_OF_RANGE`。标题超过渠道字数上限时使用 `TITLE_TOO_LONG`，禁止使用 `CHANNEL_TITLE_LONG` 等渠道内部码。其他阻断 code 会被视为审核契约错误并停止工作流。
允许用于定点回修的阻断 code 为 `TITLE_FORMULA_MISMATCH`、`TITLE_FACT_UNSUPPORTED`、`BODY_FORMULA_MISMATCH`、`CONTENT_STRUCTURE_MISMATCH`、`PERSONA_TONE_MISMATCH`、`PERSONA_STYLE_MISMATCH`、`FACT_CHECK_FAILED`、`FACT_INCONSISTENT`。其他阻断 code 会被视为审核契约错误并停止工作流。

不得用单一综合分数替代问题列表，不得修改原内容。
