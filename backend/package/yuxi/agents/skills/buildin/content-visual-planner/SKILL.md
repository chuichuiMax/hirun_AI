---
name: content-visual-planner
description: 使用已审批内容、已冻结证据和渠道规范制定结构化视觉方案。
version: 1.2.0
---

# 视觉方案规划

- 只读取当前节点 `payload`，仅使用其中已审批的标题、正文、锁定策略、证据、品牌素材和渠道规范，不调用业务事实或知识库工具。
- 严格提交 `VisualPlanResultV1`：`size`、`safe_area`、`text`、`source_asset_ids`、`mode`、`risks`、`artifact_version_id`、`evidence_ids`。
- `media_evidence_items` 中 `selected_for_cover=true` 的图片是用户在素材库中锁定的唯一封面原图；`source_asset_ids` 必须且只能填写该图片的 `id`，不得省略或替换。
- 图片文件名、素材显示名不是图片内容证据，不得据此识别城市、项目、品牌、人物或场景，也不得由此新增 `risks`。
- 素材有效性、权限和用户确认状态已在内容生成前完成；本节点只制定版式与封面文案，不重复做素材语义一致性判断。
- 文字不得新增未经证据支持的价格、参数、效果或承诺。
- 缺少必要素材时明确阻断，不得用未授权资产替代。
