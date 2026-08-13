---
name: content-body-generator
description: 使用人工锁定标题和同一份 ContentBrief、StrategyPlan、EvidenceBundle 生成正文与话题。仅在 Yuxi 内容工作流的正文生成或定向重写节点使用。
---

# 正文与话题生成

1. 使用人工选择的标题，不擅自改题。
2. 按 StrategyPlan 的正文公式逐段兑现结构，并让核心创作手法贯穿全文。
3. 只使用 EvidenceBundle 中允许用于正文的事实；不得补造客户、价格、参数、统计或效果。
4. 把引用过的证据 ID 放入 `evidence_ids`。
5. 返回 JSON：`body`、`topics`、`evidence_ids`。

保持平台无关正文；话题提供 3～8 个，不执行发布。
