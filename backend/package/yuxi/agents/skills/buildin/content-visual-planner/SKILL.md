---
name: content-visual-planner
description: 用已审批标题/短正文与模板框一次直出封面文案。
version: 1.9.0
---

# 视觉方案规划

1. 只读 `payload`；一次调用直接 `submit_content_node_result`，禁 `read_file`/空转。
2. 提交 `VisualPlanResultV1`：`size`/`safe_area` 抄 `runtime_config_snapshot.canvas`；`source_asset_ids` 只用 `media_evidence_items` 里 `selected_for_cover=true` 的 `id`；`artifact_version_id` 抄 `artifact_version.id`。
3. `template_fields` 只填 `hycanvas_fillable_fields` 的 `title`/`subtitle`/`body_excerpt`（及 `required_template_field_repairs`）；键用 `key`；不写 `label`/序号角标；项目名/面积/设计师/年份/品牌由系统填。
4. 各框信息点必须不同；`text[0]` ≥4 个有效汉字，不得只填 `1`/`01`。一次写进 `maxChars`/`maxLines`；超长或重复由服务端截断去重。
5. 用词与正文一致：泥木→泥瓦、费用→预算价、工艺不写装修风格、不写「口径」；不新增无证据价格/效果/承诺；缺锁定素材则阻断，不换图。
