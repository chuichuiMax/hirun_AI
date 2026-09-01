---
name: content-reviewer
description: 审核 Yuxi 生成内容的创作手法贯穿、公式执行、事实一致性、人设语气和风险表达。仅在确定性校验完成后的内容审核节点使用。
version: 1.2.0
---

# 内容审核

1. 当前节点 `payload` 必须包含 `content_draft`、`selected_title`、`content_outline`、`strategy_snapshot`、`validation_report` 和 `evidence_bundle`；缺少任一必需输入时直接报告契约错误，不得猜测补齐。
2. 先确认 `validation_report.status` 为 `passed` 或 `warning`。若它为 `blocked`，返回 `REVIEW_CONTRACT_INVALID`，因为确定性阻断不应进入本节点。
3. 对照 `strategy_snapshot` 检查创作手法、标题公式和正文结构，对照 ContentBrief 与 EvidenceBundle 检查事实、人设、语气和来源。
   - 公式只决定信息顺序，不允许把“旧况、关键数据、过程、结果”等公式步骤写成读者可见的报幕句。
   - 出现“旧况很典型”“关键数据先摊开”“先说背景”“再看过程”“最后看结果”“下面来说”“接下来看看”等元话术，或多个段落使用相同模板句式开场时，必须以 `PERSONA_STYLE_MISMATCH` 阻断并给出直接进入场景或事实的改写建议。
   - 不得因为结构、事实和证据正确，就把明显的提纲填充、审核报告腔或机械连接词判为语气通过。
4. 不调用 `validate_content_facts`，不重复实现敏感词、必填字段、数字来源等确定性校验；把 `validation_report` 作为已有事实合并考虑。
5. 返回 `status`、`checks` 和 `evidence_conflicts`。状态只能为 `passed`、`warning`、`blocked`。
6. 每项检查必须返回 `code`、`status`、`location`、`message`、`evidence_ids`、`suggestion`；不得使用 `level` 代替 `status`。
7. `evidence_ids` 可引用当前冻结 EvidenceBundle 中任何真实存在的证据，包括用于核对结构、节奏和 emoji 模式的 `style_reference`；不得引用未知 Evidence ID。
8. 顶层 `status` 必须与 `checks` 中最严重状态一致：存在 `blocked` 则为 `blocked`，否则存在 `warning` 则为 `warning`，其余为 `passed`。

允许用于定点回修的阻断 code 为 `TITLE_FORMULA_MISMATCH`、`BODY_FORMULA_MISMATCH`、`CONTENT_STRUCTURE_MISMATCH`、`PERSONA_TONE_MISMATCH`、`PERSONA_STYLE_MISMATCH`、`FACT_CHECK_FAILED`、`FACT_INCONSISTENT`。其他阻断 code 会被视为审核契约错误并停止工作流。

不得用单一综合分数替代问题列表，不得修改原内容。
