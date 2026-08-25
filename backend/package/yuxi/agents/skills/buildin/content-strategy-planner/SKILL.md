---
name: content-strategy-planner
description: 解释 V3 固定规则已锁定的组合组，或在该组合组的合法候选池内排序标题公式和正文公式。
version: 3.1.0
---

# V3 内容策略解释与排序

只处理当前策略节点，不决定下一节点或修改工作流。

1. 使用 `payload.rule_version_id` 调用 `get_creation_rule_bundle`，读取任务锁定的 V3 规则版本；不得凭记忆补充公式。
2. 只读取当前节点 `payload`；其中 `match_decision_snapshot` 是固定规则节点的最终结果，不得改变内容方向、组合组或候选池。
3. 在 `explain_strategy` 节点，只解释已锁定手法组合、适用场景、风险和证据依据。
4. 在 `rank_formula_candidates` 节点，只能对 `payload.formula_candidate_pool` 中的标题和正文公式排序；不得提交池外公式。
5. 缺少变量或证据时明确说明，不得让后续节点猜测或编造。
6. 严格按当前 Agent 节点的输出契约返回，不输出 V2 `StrategyPlan`。

精确规则只来自 Tool；行业案例和写作知识可以来自 EvidenceBundle，但不能改变固定规则的组合判定。
