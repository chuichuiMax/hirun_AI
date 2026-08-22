---
name: content-reviewer
description: 审核 Yuxi 生成内容的创作手法贯穿、公式执行、事实一致性、人设语气和风险表达。仅在确定性校验完成后的内容审核节点使用。
version: 1.1.0
---

# 内容审核

1. 当前节点 `payload` 必须包含 `content_draft`、`selected_title`、`content_outline`、`strategy_snapshot`、`validation_report` 和 `evidence_bundle`；缺少任一必需输入时直接报告契约错误，不得猜测补齐。
2. 先确认 `validation_report.status` 为 `passed` 或 `warning`。若它为 `blocked`，返回 `REVIEW_CONTRACT_INVALID`，因为确定性阻断不应进入本节点。
3. 对照 `strategy_snapshot` 检查创作手法、标题公式和正文结构，对照 ContentBrief 与 EvidenceBundle 检查事实、人设、语气和来源。
4. 不调用 `validate_content_facts`，不重复实现敏感词、必填字段、数字来源等确定性校验；把 `validation_report` 作为已有事实合并考虑。
5. 返回 `status`、`checks` 和 `evidence_conflicts`。状态只能为 `passed`、`warning`、`blocked`。
6. 每项检查必须返回 `code`、`status`、`location`、`message`、`evidence_ids`、`suggestion`；不得使用 `level` 代替 `status`。

允许用于定点回修的阻断 code 为 `TITLE_FORMULA_MISMATCH`、`BODY_FORMULA_MISMATCH`、`CONTENT_STRUCTURE_MISMATCH`、`PERSONA_TONE_MISMATCH`、`PERSONA_STYLE_MISMATCH`、`FACT_CHECK_FAILED`、`FACT_INCONSISTENT`。其他阻断 code 会被视为审核契约错误并停止工作流。

不得用单一综合分数替代问题列表，不得修改原内容。
