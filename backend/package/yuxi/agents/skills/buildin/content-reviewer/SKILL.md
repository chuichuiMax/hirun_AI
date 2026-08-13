---
name: content-reviewer
description: 审核 Yuxi 生成内容的创作手法贯穿、公式执行、事实一致性、人设语气和风险表达。仅在确定性校验完成后的内容审核节点使用。
---

# 内容审核

1. 对照 StrategyPlan 检查创作手法、标题公式和正文结构。
2. 对照 ContentBrief 与 EvidenceBundle 检查事实、人设、语气和来源。
3. 不重复实现敏感词、必填字段、数字来源等确定性校验；把其报告作为已有事实合并考虑。
4. 返回 `status` 和 `checks`。状态只能为 `passed`、`warning`、`blocked`。
5. 每项检查返回 `code`、`level`、`location`、`message`、`evidence_ids`、`suggestion`。

不得用单一综合分数替代问题列表，不得修改原内容。
