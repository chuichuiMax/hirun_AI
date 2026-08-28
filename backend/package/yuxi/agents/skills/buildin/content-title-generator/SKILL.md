---
name: content-title-generator
description: 按锁定策略生成可追溯标题候选，或从已通过确定性校验的候选中选择最终标题。
version: 2.0.0
---

# 标题候选生成

根据当前节点输出契约执行标题候选生成或标题选择，不生成正文、不决定流程跳转。

1. 当前 Skill 全文已经注入，不调用 `read_file`。
2. 只读取当前节点 `payload`；锁定标题公式的完整原版定义位于 `payload.strategy_snapshot.title_formula`，不得再次读取可变规则库，也不得凭记忆补公式。
3. 业务事实已经完整提供在 `payload.content_brief` 和 `payload.evidence_bundle` 中，不调用业务事实或知识库工具。
4. 严格使用 `payload.strategy_snapshot.title_formula.code` 锁定的唯一标题公式及其变量 Schema。
5. 在 `generate_content` 节点只生成一个最终标题，并与大纲、正文一起提交 `GeneratedContentResultV1`。
6. 只从 `payload.evidence_bundle` 选择允许用于标题的 Evidence ID，并在标题实际使用相应事实时引用。
7. 如果 `payload.validation_report.status=blocked`，读取上一轮检查并修正全部确定性错误。
8. `style_reference` 证据只能借鉴结构和节奏，禁止复制原句、事实或数字，也不得放入标题的 `evidence_ids`。
9. 旧工作流生成候选时仍保持 3～5 个差异明确的候选；简化工作流不再生成候选池。
10. 旧生成节点仍按其输出契约提交 `TitleCandidatesResultV1`。
11. 在 `TitleSelectionResultV1` 节点，只能从 `payload.title_candidates` 中选择 `selectable=true` 的候选；综合公式契合度、证据完整度、渠道可读性和吸引力，提交 `selected_title_id` 与 `reason`。
12. 选择标题时不得改写候选文本、公式或 Evidence ID，也不得选择 `selectable=false` 的候选。
13. 数字、价格、参数和效果必须关联证据 ID；证据不足时不生成该表达。

标题选择结果必须完全对应上游候选快照。
