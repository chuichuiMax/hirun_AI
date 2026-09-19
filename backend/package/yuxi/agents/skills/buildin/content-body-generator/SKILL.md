---
name: content-body-generator
description: 使用 ContentBrief、StrategyPlan、EvidenceBundle 一次生成正文与话题。
version: 2.10.4
---

# 正文与话题生成

入口：`payload.content_brief.business_variables.mp_service_entry`。

1. 只读当前 `payload`；与标题同轮一次直出，直接 `submit_content_node_result`（禁止 `read_file`/检索/空转）。
2. **好评笔记**：模仿 `style_excerpts` 语气；忽略公式/词库；业主第一人称；事实仅来自简报与证据。
3. **装修家居**：遵守 `writing_instruction`；不写旧况→改造→完工案例；卡点写小区/面积/布局（有填才写）/风格/鸿扬家装；品牌写**定制化家装**（禁整装/标准化整装）；费用称「预算价」不写「合同价」与「口径」；泥木对外写「泥瓦」。收尾必须独立成块（禁「在某地朋友，如果也在为某盘某㎡」一句墙字）：
   ```
   📍常德｜准备装修的朋友👋
   你家是不是也有这类困扰？

   ▫️共性痛点一
   ▫️共性痛点二
   ▫️共性痛点三

   💬你家最想问的是哪一点？
   欢迎在评论区聊聊～
   ```
   有城市写城市，没有写「同城」；▫️只写本文主题的共性困扰，禁止编造该套房缺陷。
   - CT02 报价清单：费用仅参考卡点，主线品牌与交付，不以低价为主卖点。
   - CT05 工艺展示：主线工艺科普；有工艺名按「定制化家装＋鸿扬家装＋工艺名＋类型＋关键环节」写；不写装修风格、不写案例叙事。
4. `creation_mode=original` 按锁定公式；`viral_rewrite` 只用 `selected_reference=true` 的结构蓝图（不抄事实）。
5. 按 `body_formula`/`body_calling` 逐段兑现；`formula_lexicon_bundle.required=true` 时只用对应词库 chunks，命中封禁表先改写。
6. Evidence：只用 `items` 里 `allowed_usage` 含 `body` 的短码 `id`（如 `E01`）；事实用 `value` 原文；面积只写锁定的具体㎡，禁止区间；知识证据至少挂一条；价格段须写出具体价。
7. 数字仅来自白名单；封禁表问题词必须替换；正文 200～650 字；`paragraph_evidence` 挂真实使用的 ID。
8. 表达：同轮执行 `viral-layout-formatter`（分段扫读）→ `humanizer-zh`（去机械腔）→ `content-human-expression`（拟人语气与语义 Emoji）。正文必须真实换行；`emoji_allowed=true` 时按痛点/数据/事项/互动放表情；话题 3～8 个。
9. 提交 `GeneratedContentResultV1`（正文在 `draft`）。
