---
name: content-title-generator
description: 按已锁定的创作手法、标题公式、ContentBrief 和 EvidenceBundle 生成可追溯标题候选。仅在 Yuxi 内容工作流的标题生成节点使用。
version: 1.0.1
---

# 标题候选生成

只生成标题候选，不选择标题、不生成正文、不决定流程跳转。

1. 当前 Skill 全文已经注入，不调用 `read_file`。
2. 使用 `locked_versions.rule_version_id` 调用一次 `get_creation_rule_bundle`，读取锁定标题公式的原版定义；不得凭记忆补公式。
3. 业务事实已经完整提供在 `content_brief` 和 `evidence_bundle` 中，不调用 `get_business_facts`。
4. 严格使用 `formula_selection_snapshot.selected_title_formula_code` 锁定的唯一标题公式及其变量 Schema。
5. 只使用 EvidenceBundle 中 `allowed_usage` 包含 `title` 的事实。
6. 生成 3～5 个差异明确的候选，保持同一创作手法和同一锁定公式。
7. 严格提交 `TitleCandidatesResultV1`：顶层只包含 `candidates`、`selected_title_formula_code`、`evidence_ids`；每个候选只包含 `id`、`text`、`formula_code`、`evidence_ids`、`reason`。
8. 数字、价格、参数和效果必须关联证据 ID；证据不足时不生成该表达。

不得选择最终标题。选择权属于 LangGraph 的人工节点。
