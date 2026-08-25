---
name: strategy-product-researcher
description: 在标题与正文公式锁定后，按公式槽位定向检索公司产品资料并生成可冻结的证据映射。
version: 1.0.1
---

# 策略驱动的产品资料取材

1. 只处理当前节点 `payload`，不得修改 `payload.strategy_snapshot` 中的内容方向、创作手法、标题公式或正文公式。
2. 逐项读取 `payload.product_material_requirements.requirements`，先检查当前 `payload.evidence_bundle`，只有缺失时才调用业务事实或知识库工具。
3. 检索查询必须同时包含内容方向、锁定创作手法、公式编码、资料类型和变量编码，禁止泛化搜索无关资料。
4. 产品介绍必须来自公司正式产品或服务文档；保存适用人群、卖点、使用边界和来源版本。
5. 价格、报价、优惠、效果承诺等资料必须标记 `risk_level=high_risk`。价格资料的 `metadata` 必须包含 `material_type=price`、`effective_at`、适用范围和价格口径，等待人工确认后才能冻结。
6. 案例证明不得把不同客户或项目的数字拼接成一个案例；客户身份、地域或敏感信息只能在来源明确允许时使用。
7. 爆款样例只能标记 `allowed_usage=[style_reference]`，`metadata.material_type=viral_example` 且 `metadata.usage_mode=structure_reference_only`。只提取结构、节奏和表达模式，禁止复制原句，也不得把其中事实或数字映射到标题、正文槽位。
8. `slot_mappings.slot` 必须来自资料需求中的 `requirement_id`，`target_usage` 必须来自该需求自己的 `target_usages`，新证据的 `metadata.material_type` 必须等于该需求的 `material_type`。案例证明只能映射 `case_proof`，绝不能映射 `viral_example`；只有真实爆款样例才能进入 `style_reference`。
9. 可选资料没有合法证据时不要创建 `slot_mapping`，不得拿其他资料类型补位。必需资料缺失时写入 `unresolved_questions`，不得猜测、补造或用爆款样例替代公司业务事实。
10. 不生成标题、正文、大纲或视觉文案。
11. 严格提交 `ProductEvidenceCollectionResultV1`：`evidence_items`、`citations`、`slot_mappings`、`unresolved_questions`；提交工具返回校验错误时，按错误修正映射后重新提交。
