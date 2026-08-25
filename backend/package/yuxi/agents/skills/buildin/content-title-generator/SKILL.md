---
name: content-title-generator
description: 按已锁定的创作手法、标题公式、ContentBrief 和 EvidenceBundle 生成可追溯标题候选。仅在 Yuxi 内容工作流的标题生成节点使用。
version: 1.3.0
---

# 标题候选生成

只生成标题候选，不选择标题、不生成正文、不决定流程跳转。

1. 当前 Skill 全文已经注入，不调用 `read_file`。
2. 只读取当前节点 `payload`；锁定标题公式的完整原版定义位于 `payload.strategy_snapshot.title_formula`，不得再次读取可变规则库，也不得凭记忆补公式。
3. 业务事实已经完整提供在 `payload.content_brief` 和 `payload.evidence_bundle` 中，不调用业务事实或知识库工具。
4. 严格使用 `payload.strategy_snapshot.title_formula.code` 锁定的唯一标题公式及其变量 Schema。
5. 先读取 `payload.title_evidence_requirements`。每个候选都必须使用所有 `required=true` 的槽位，并把这些槽位列出的至少一个 Evidence ID 放入该候选的 `evidence_ids`；`required=false` 的槽位只有在标题实际使用对应资料时才引用。
6. `payload.product_evidence_pack.slot_mappings` 是完整资料映射，不能用可选槽位替代必填槽位，也不能只在顶层 `evidence_ids` 引用而遗漏候选自己的 `evidence_ids`。
7. 如果 `payload.title_validation_report.status=blocked`，逐条读取上一轮候选的 `missing_required_slots` 和 `checks`，重新生成候选并修正全部确定性错误，不得原样提交上一轮标题。
8. `style_reference` 证据只能借鉴结构和节奏，禁止复制原句、事实或数字，也不得放入标题的 `evidence_ids`。
9. 生成 3～5 个差异明确的候选，保持同一创作手法和同一锁定公式。
10. 严格提交 `TitleCandidatesResultV1`：顶层只包含 `candidates`、`selected_title_formula_code`、`evidence_ids`；每个候选只包含 `id`、`text`、`formula_code`、`evidence_ids`、`reason`。
11. 数字、价格、参数和效果必须关联证据 ID；证据不足时不生成该表达。

不得选择最终标题。选择权属于 LangGraph 的人工节点。
