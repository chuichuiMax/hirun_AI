---
name: content-body-generator
description: 使用人工锁定标题和同一份 ContentBrief、StrategyPlan、EvidenceBundle 生成正文与话题。仅在 Yuxi 内容工作流的正文生成或定向重写节点使用。
---

# 正文与话题生成

1. 使用人工选择的标题，不擅自改题。
2. 按 StrategyPlan 的正文公式逐段兑现结构，并让核心创作手法贯穿全文。
3. 只使用 EvidenceBundle 中允许用于正文的事实；不得补造客户、价格、参数、统计或效果。
4. 正文和话题中的每个阿拉伯数字都必须来自运行时提供的数字白名单。不得编造数字示例、对比数字或统计数字，也不得使用阿拉伯数字或数字 emoji 作为段落编号；改用项目符号。
5. 输出前逐项核对正文和话题里的数字；发现白名单外数字时，删除数字或把句子改为不含数字的事实表达。
6. 把引用过的证据 ID 放入 `evidence_ids`。
7. 返回 JSON：`body`、`topics`、`evidence_ids`。

保持平台无关正文；话题提供 3～8 个，不执行发布。
