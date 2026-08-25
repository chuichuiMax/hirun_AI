---
name: content-outline-builder
description: 把已锁定的正文 Pattern、SlotPlan 和 EvidenceBundle 编译为段落大纲与证据使用计划，不生成新的业务事实。
version: 1.2.0
---

# 内容大纲编译

只读取当前节点 `payload`，严格按照 `payload.strategy_snapshot.body_formula` 的原版正文结构，为人工锁定的 `payload.selected_title` 组织大纲。

- 每个段落必须保存段落目的、允许使用的 Slot 和 Evidence ID。
- 使用 `payload.product_evidence_pack.slot_mappings` 把产品介绍、案例证明、价格和品牌资料分配到对应段落；只使用 `target_usage=body` 的映射。
- 爆款样例只能影响结构节奏，不能成为段落事实或 Evidence ID。
- 事实性段落只能使用 EvidenceBundle 中已有来源。
- 缺少必填事实时标记阻断或请求补充，不得自行构造示例数据。
- 主叙事轴贯穿所有段落，不能引入第二条竞争叙事。
- 不选择下一个节点，不修改工作流结构。
- 严格提交 `OutlineResultV1`：`body_formula_code` 与 `sections`；每个 section 只包含 `section_id`、`goal`、`evidence_ids`。
