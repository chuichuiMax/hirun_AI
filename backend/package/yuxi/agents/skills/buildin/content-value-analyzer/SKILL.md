---
name: content-value-analyzer
description: 基于 ContentBrief 与 EvidenceBundle 识别可创作价值、候选角度和唯一主叙事轴，不创造事实，也不决定工作流跳转。
version: 1.1.0
---

# 内容价值分析

只使用当前节点 `payload.content_brief`、`payload.evidence_bundle`、`payload.content_type`、`payload.industry_pack` 和 `payload.channel_profile` 中已存在的信息识别内容价值。

- 输出 1～3 个候选内容方向，每个方向只允许一条主要叙事轴。
- `direction_code` 只能使用平台一级方向正式编码，禁止创建 `D01` 等临时角度编号：
  - `CT01`：案例/成果分享。
  - `CT02`：价格/方案透明。
  - `CT03`：避坑/纠错提醒。
  - `CT04`：攻略/效率优化。
  - `CT05`：过程/能力证明。
  - `CT06`：知识/问题教育。
  - `CT07`：人设/品牌主张。
- 候选方向必须按当前行业理解上述平台语义；`reason` 说明该方向在当前行业中的具体创作角度，不得把创作角度当成新的方向编码。
- 优先选择变量完整、证据充分且符合内容目标的内容类型。
- 明确列出可用事实、证据 ID、缺失信息和风险。
- 不补写价格、数字、效果、人物经历或服务承诺。
- 不选择下一个节点，不修改工作流结构。
- 严格提交 `ContentValueResultV1`：`value_points`、`direction_candidates`、`reasoning`、`evidence_ids`。
