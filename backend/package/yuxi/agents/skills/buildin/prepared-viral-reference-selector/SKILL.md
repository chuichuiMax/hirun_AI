---
name: prepared-viral-reference-selector
description: 按本次输入为已核验的文章级参考卡评分，选中后复用已有蓝图，不进行全文解析。
---

# 已准备参考选择

只在仿写模式执行。候选仅来自本次 `reference_candidates`；不得使用知识库段落、文件名或自行搜索到的片段替代完整文章资产。

先对照当前简报与证据中的已有事实检查参考卡与 structure_preview。可跨同一行业的不同项目主题借鉴抽象叙述结构，但不能把报价清单改称案例过程就视为完成仿写，也不能复制原文价格、从业年限或效果。只有当前资料能填充其必要事实槽位的参考才合格，不因为用户原选方向而排除适配实际资料的参考。

1. 检查行业、渠道、受众、场景、目标和事实槽位。依赖分项价格但只有总预算，依赖真实前后对比但只有计划，均淘汰；不能用不相干案例或原文事实填补。
   - 已有适用的知识库标准单价时，可以填充报价明细、分项价格、工价清单等价格槽位，并以“标准单价参考”表达。可与项目总预算独立展示，无需提供工程量、小计或与总预算加总一致；不得把“报价明细”一律理解成实际成交明细，也不要求覆盖全部装修类别。仅明确依赖真实成交、结算或实际节省结果的核心槽位仍需实际项目证据。
2. 全部合格卡片按 `strategy_candidates.scoring.reference` 的权重及 0—4 锚点评分；`dimensions` 键必须恰好复制 `scoring.reference.required_dimension_keys`（material、audience_scene、goal、strategy、channel），不要写成手法的 persona。适配策略维度以刚选择的公式和手法为依据，但 input_paths 仍指向本次简报或真实业务证据。淘汰卡不得带分数。
3. 按总分、指定同分维度、最后稳定 ID 选择唯一参考。每项保留一句理由及实际非空输入路径，不输出整篇候选复述。
4. 选中后，`reference.slot_mapping` 的键必须逐字复制该卡 `required_slot_names` / `reference_card.required_slots[].name`，禁止改写、缩写、合并或另起槽名。每个 required=true 槽位都必须出现，值是本次 `content_brief.*` 或 `evidence_bundle.items.*.value` 路径列表。引用原文、空字段或其他案例不能证明当前项目事实。required=false 仅在有本次证据时映射。校验若列出缺少或多余槽名，按列出的原名重交，不要发明新键。
5. 只复制 selected_asset_id 和 source_hash，不提供 reference_blueprint。已准备蓝图在锁定步骤直接读取。
6. 无合格候选返回 no_candidate/needs_input 及缺口；不触发在线补建资产，也不自动改为原创。
