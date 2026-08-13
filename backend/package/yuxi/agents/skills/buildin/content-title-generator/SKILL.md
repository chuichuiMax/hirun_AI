---
name: content-title-generator
description: 按已锁定的创作手法、标题公式、ContentBrief 和 EvidenceBundle 生成可追溯标题候选。仅在 Yuxi 内容工作流的标题生成节点使用。
---

# 标题候选生成

只生成标题候选，不选择标题、不生成正文、不决定流程跳转。

1. 严格使用 StrategyPlan 中锁定的标题公式及其变量 Schema。
2. 只使用 EvidenceBundle 中 `allowed_usage` 包含 `title` 的事实。
3. 生成 3～5 个差异明确的候选，保持同一创作手法。
4. 每个候选返回 `id`、`text`、`formula_code`、`variable_mapping`、`evidence_ids`、`risk_flags`。
5. 数字、价格、参数和效果必须关联证据 ID；证据不足时不生成该表达。

不得选择最终标题。选择权属于 LangGraph 的人工节点。
