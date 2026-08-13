---
name: content-strategy-planner
description: 为 Yuxi 内容生产任务规划或校验创作手法、标题公式和正文公式。仅在工作流的策略节点收到 ContentBrief、规则版本和内容目标时使用。
---

# 内容策略规划

只处理当前策略节点，不决定下一节点或修改工作流。

1. 使用 `get_creation_rule_bundle` 读取任务锁定的规则版本；不得凭记忆补充公式。
2. 先检查 ContentBrief 的事实变量，再按内容目标筛选组合规则。
3. 使用 `validate_formula_combination` 校验手法、标题公式和正文公式。
4. 缺少变量时输出明确字段，不得让后续生成节点猜测。
5. 返回 StrategyPlan：`methods`、`scene_enhancer`、`title_formula_code`、`content_formula_code`、`compatibility`、`required_variables`、`reason_summary`。

精确规则只来自 Tool；行业案例和写作知识可以来自 EvidenceBundle，但不能改变组合判定。
