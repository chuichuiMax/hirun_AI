---
name: content-title-generator
description: 按锁定策略一次生成最终标题（与正文同轮提交）。
version: 2.8.2
---

# 标题生成

入口：`payload.content_brief.business_variables.mp_service_entry`。

0. **好评笔记**：模仿 `style_excerpts`；忽略标题公式/词库；事实仅简报与证据；业主第一人称；标题禁楼盘/小区案名，可赞美店面；然后按第 8 条。
0b. **装修家居**：遵守锁定公式与词库；标题须有情绪/悬念/反差/利益吸引点，禁「小区+面积+风格」平铺；面积写简报锁定的具体㎡，禁止130-150㎡这类区间。
   - CT02：口语句、可读（正例：142㎡旧房翻新，钱要花在哪？）；不以最低价为主卖点；不写「口径」。
   - CT05：点明工艺/工序或阶段，不写装修风格；泥木写「泥瓦」；词库化入句子，禁「听劝/远超预期」硬拼。
   - 品牌写定制化家装，禁整装；费用称预算价，禁合同价；命中封禁表须改写。
0c. Evidence：`evidence_ids` 只复制 `allowed_usage` 含 `title` 的短码 `id`（如 `E01`）。
1. Skill 已注入；`generate_content` 仅一次调用，直接 `submit_content_node_result`。
2. 只用 `title_formula.code` 与 schema；`title_formula.lexicon_codes` 全部写入 `title.lexicon_usage`；词库 `required=true` 时从 `formula_lexicon_bundle.title.chunks` 取材。
3. 只生成一个最终标题，与大纲正文一并提交 `GeneratedContentResultV1`。
4. 字数必须落在 `channel_profile.title_constraints` 内（小红书 6～20 字）。先写成完整一句再数字数；超限整句改短后提交。超过上限会校验失败，服务端不会截断。
5. 爆款仿写：只借 `reference_blueprint` 槽位顺序，内容用当前证据；无证据槽位删除或改非事实表述。
6. 变量不得扩大含义（预算≠已搞定、工期≠已完工）。
