---
name: content-visual-planner
description: 使用已审批内容、已冻结证据和渠道规范制定结构化视觉方案。
version: 1.8.0
---

# 视觉方案规划

- 只读当前节点 `payload`。本节点只有一次模型调用，必须直接 `submit_content_node_result`，禁止 `read_file`、空转或依赖二次纠错。
- 提交 `VisualPlanResultV1`。`size`/`safe_area` 原样抄 `runtime_config_snapshot.canvas`；`source_asset_ids` 只能填 `media_evidence_items` 中 `selected_for_cover=true` 的 `id`；`artifact_version_id` 抄 `artifact_version.id`。
- 文件名不是图片内容证据。不新增无证据价格、效果或承诺。封面用词与正文一致：泥木写「泥瓦」、费用写「预算价」、工艺不写装修风格、不要写「口径」。
- `template_fields` 只填 `hycanvas_fillable_fields` 里 `title`/`subtitle`/`body_excerpt`，以及 `required_template_field_repairs`。键优先用 `key`。项目名、面积、设计师、年份、品牌由系统填，不要改。`label` 与序号角标（`01`/`1`、`maxChars≤2`）不要写入。
- 每个文字框信息点必须不同：忽略空白标点后不得相同，也不得只改语序复述。多个 `title` 不得都复制 `text[0]`。`text[0]` 至少 4 个有效汉字，不得只填 `1`/`01`。
- 只改文字，不改模板样式。必须一次写进该字段 `maxChars`/`maxCharsPerLine`/`maxLines`。超长或重复时由服务端按容量截断并改成不同信息点，不要指望二次提交。缺锁定素材则阻断，不得换图。
