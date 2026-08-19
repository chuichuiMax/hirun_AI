---
name: content-outline-builder
description: 把已锁定的正文 Pattern、SlotPlan 和 EvidenceBundle 编译为段落大纲与证据使用计划，不生成新的业务事实。
version: 1.0.0
---

# 内容大纲编译

严格按照正文 Pattern 的段落顺序组织大纲。

- 每个段落必须保存段落目的、允许使用的 Slot 和 Evidence ID。
- 事实性段落只能使用 EvidenceBundle 中已有来源。
- 缺少必填事实时标记阻断或请求补充，不得自行构造示例数据。
- 主叙事轴贯穿所有段落，不能引入第二条竞争叙事。
- 不选择下一个节点，不修改工作流结构。
