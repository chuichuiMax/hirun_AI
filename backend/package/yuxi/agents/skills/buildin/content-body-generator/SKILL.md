---
name: content-body-generator
description: 使用人工锁定标题和同一份 ContentBrief、StrategyPlan、EvidenceBundle 生成正文与话题。仅在 Yuxi 内容工作流的正文生成或定向重写节点使用。
version: 1.2.0
---

# 正文与话题生成

1. 只读取当前节点 `payload`，使用 `payload.selected_title`，不擅自改题。
2. 严格沿用 `payload.content_outline`，按 `payload.strategy_snapshot.body_formula` 逐段兑现结构，并让 `creation_methods` 贯穿全文。
3. 按 `payload.product_evidence_pack.slot_mappings` 植入产品卖点、适用人群、价格、品牌或案例证明，只使用 `target_usage=body` 的映射。
4. `style_reference` 仅用于结构和节奏参考，禁止复制原句、事实或数字，禁止写入 `paragraph_evidence`。
5. 只使用 `payload.evidence_bundle` 中允许用于正文的事实；不得调用业务事实或知识库工具，不得补造客户、价格、参数、统计或效果。
6. 正文和话题中的每个阿拉伯数字都必须来自运行时提供的数字白名单。不得编造数字示例、对比数字或统计数字，也不得使用阿拉伯数字或数字 emoji 作为段落编号；改用项目符号。
7. 输出前逐项核对正文和话题里的数字；发现白名单外数字时，删除数字或把句子改为不含数字的事实表达。
8. 正文控制在 200～650 字；每个事实段落通过 `paragraph_evidence` 关联实际使用的 Evidence ID。
9. 严格提交 `ContentDraftResultV1`：`body`、`topics`、`paragraph_evidence`、`body_formula_code`。

保持平台无关正文；话题提供 3～8 个，不执行发布。
