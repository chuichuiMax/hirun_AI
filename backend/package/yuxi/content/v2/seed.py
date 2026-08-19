"""contentSwarm V2 平台规则、工作流、渠道与六行业完整种子。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.content.rules import BODY_FORMULAS, INDUSTRIES, METHODS, TITLE_FORMULAS
from yuxi.storage.postgres.models_content import (
    ChannelProfile,
    ChannelProfileVersion,
    CompliancePolicyVersion,
    ContentCombinationRule,
    ContentFormula,
    ContentRuleVersion,
    ContentTypeDefinition,
    ContentWorkflowVersion,
    CreationMethod,
    FormulaPattern,
    FormulaSlotBinding,
    IndustryContentPackVersion,
    IndustryTemplateVersion,
    IndustryVariableMapping,
    LexiconEntry,
    LexiconPack,
    LexiconVersion,
    ReplacementRule,
    TitleFormula,
    VariableDefinition,
)
from yuxi.utils.datetime_utils import utc_now_naive


PLATFORM_RULE_V2_ID = "content-rules-platform-v2"
PLATFORM_WORKFLOW_V2_ID = "content-workflow-enterprise-v2"
XHS_CHANNEL_PROFILE_ID = "channel-xiaohongshu"
XHS_CHANNEL_VERSION_ID = "channel-xiaohongshu-v1"


CONTENT_TYPES = [
    {
        "code": "CT01",
        "name": "案例/成果展示",
        "description": "通过真实背景、过程和结果证明能力",
        "supported_goals": ["traffic", "acquire", "brand"],
        "required_variable_codes": ["audience", "process", "result"],
        "evidence_policy": {"result": "required", "number": "required_if_used"},
        "default_narrative_axes": ["before_after_result", "process_to_result"],
        "default_body_formula_codes": ["C02"],
    },
    {
        "code": "CT02",
        "name": "价格/方案透明",
        "description": "解释价格构成、方案边界和选择依据",
        "supported_goals": ["educate", "acquire"],
        "required_variable_codes": ["product", "price", "advantages"],
        "evidence_policy": {"price": "required", "promise": "confirm"},
        "default_narrative_axes": ["price_composition", "option_tradeoff"],
        "default_body_formula_codes": ["C01"],
    },
    {
        "code": "CT03",
        "name": "避坑/风险提示",
        "description": "揭示常见误区、风险及正确做法",
        "supported_goals": ["traffic", "educate", "acquire"],
        "required_variable_codes": ["pain", "process", "result"],
        "evidence_policy": {"risk": "knowledge_or_manual", "number": "required_if_used"},
        "default_narrative_axes": ["mistake_vs_correct", "risk_consequence"],
        "default_body_formula_codes": ["C03"],
    },
    {
        "code": "CT04",
        "name": "攻略/效率优化",
        "description": "提供可执行步骤，降低成本或提升效率",
        "supported_goals": ["traffic", "educate"],
        "required_variable_codes": ["audience", "pain", "process"],
        "evidence_policy": {"result": "required_if_claim"},
        "default_narrative_axes": ["cost_vs_efficiency", "steps_to_result"],
        "default_body_formula_codes": ["C03"],
    },
    {
        "code": "CT05",
        "name": "过程/能力证明",
        "description": "展示标准流程、专业细节和交付能力",
        "supported_goals": ["acquire", "brand"],
        "required_variable_codes": ["process", "advantage", "result"],
        "evidence_policy": {"process": "required", "result": "required_if_used"},
        "default_narrative_axes": ["detail_proves_capability", "process_reduces_risk"],
        "default_body_formula_codes": ["C02"],
    },
    {
        "code": "CT06",
        "name": "知识/问题教育",
        "description": "解释概念、判断标准和专业正解",
        "supported_goals": ["educate", "brand"],
        "required_variable_codes": ["pain", "process"],
        "evidence_policy": {"professional_claim": "knowledge_or_manual"},
        "default_narrative_axes": ["misconception_vs_fact", "question_to_standard"],
        "default_body_formula_codes": ["C03"],
    },
    {
        "code": "CT07",
        "name": "人设/品牌主张",
        "description": "表达经历、立场、原则和服务边界",
        "supported_goals": ["brand", "acquire"],
        "required_variable_codes": ["persona_fact", "advantage"],
        "evidence_policy": {"persona_fact": "confirmed_or_evidence"},
        "default_narrative_axes": ["experience_to_principle", "boundary_builds_trust"],
        "default_body_formula_codes": ["C04"],
    },
]


VARIABLES = [
    ("audience", "目标人群", "list", "normal", False),
    ("location", "地域", "string", "normal", False),
    ("product", "产品或服务", "string", "normal", False),
    ("price", "价格", "money", "high_risk", True),
    ("duration", "周期", "duration", "sensitive", True),
    ("quantity", "数量", "number", "sensitive", True),
    ("number", "量化数字", "number", "high_risk", True),
    ("pain", "用户痛点", "list", "normal", False),
    ("pain_points", "用户痛点兼容字段", "list", "normal", False),
    ("result", "结果", "string", "high_risk", True),
    ("process", "过程", "list", "sensitive", True),
    ("advantage", "差异优势", "list", "normal", False),
    ("advantages", "差异优势兼容字段", "list", "normal", False),
    ("persona_fact", "人物经历", "string", "high_risk", True),
    ("scene", "场景", "string", "normal", False),
    ("brand_name", "品牌名称", "string", "normal", False),
    ("emotion", "情绪表达", "string", "normal", False),
    ("suspense", "悬念表达", "string", "normal", False),
    ("advice", "忠告表达", "string", "normal", False),
    ("call_to_action", "行动指令", "string", "normal", False),
]


TITLE_PATTERNS = [
    (
        "T01-P01",
        "T01",
        "人群数字结果",
        "{audience}：{number}完成{result}",
        [
            ("audience", "brief", "audience", True, False, "block"),
            ("number", "evidence", None, True, True, "ask_user"),
            ("result", "evidence", None, True, True, "ask_user"),
        ],
    ),
    (
        "T02-P01",
        "T02",
        "情绪数字结果",
        "{emotion}，{number}后得到{result}",
        [
            ("emotion", "lexicon", None, True, False, "use_lexicon"),
            ("number", "evidence", None, True, True, "ask_user"),
            ("result", "evidence", None, True, True, "ask_user"),
        ],
    ),
    (
        "T03-P01",
        "T03",
        "定位问题利好",
        "{audience}遇到{pain}，这样做更接近{result}",
        [
            ("audience", "brief", "audience", True, False, "block"),
            ("pain", "brief", "business_variables.pain", True, False, "block"),
            ("result", "evidence_or_goal", None, True, False, "use_goal"),
        ],
    ),
    (
        "T04-P01",
        "T04",
        "悬念数字痛点",
        "{suspense}：{number}个{pain}",
        [
            ("suspense", "lexicon", None, True, False, "use_lexicon"),
            ("number", "evidence", None, True, True, "ask_user"),
            ("pain", "brief", "business_variables.pain", True, False, "block"),
        ],
    ),
    (
        "T05-P01",
        "T05",
        "忠告人群方案",
        "{advice}，{audience}别再被{pain}困住",
        [
            ("advice", "lexicon", None, True, False, "use_lexicon"),
            ("audience", "brief", "audience", True, False, "block"),
            ("pain", "brief", "business_variables.pain", True, False, "block"),
        ],
    ),
    (
        "T06-P01",
        "T06",
        "地域品类数字反差",
        "{location}{product}，{number}带来的真实反差",
        [
            ("location", "brief", "business_variables.location", True, False, "block"),
            ("product", "brief", "business_variables.product", True, False, "block"),
            ("number", "evidence", None, True, True, "ask_user"),
        ],
    ),
    (
        "T07-P01",
        "T07",
        "指令数字价值",
        "{call_to_action}：{number}个方法帮你{result}",
        [
            ("call_to_action", "lexicon", None, True, False, "use_lexicon"),
            ("number", "evidence", None, True, True, "ask_user"),
            ("result", "evidence_or_goal", None, True, False, "use_goal"),
        ],
    ),
]


BODY_PATTERNS = [
    {
        "code": "C01-P01",
        "formula_code": "C01",
        "name": "方案转化六段式",
        "template_text": "痛点→事实/数据→方案→反差→背书→行动",
        "content_type_codes": ["CT02"],
        "paragraph_schema": [
            {"code": "pain", "purpose": "说明用户痛点", "slots": ["pain"], "evidence_required": False, "length": [40, 100]},
            {"code": "facts", "purpose": "给出价格或数据", "slots": ["price", "number"], "evidence_required": True, "length": [40, 120]},
            {"code": "solution", "purpose": "解释方案与边界", "slots": ["product", "process"], "evidence_required": True, "length": [80, 180]},
            {"code": "contrast", "purpose": "解释选项差异", "slots": ["advantage"], "evidence_required": False, "length": [40, 120]},
            {"code": "proof", "purpose": "可信背书", "slots": ["result"], "evidence_required": True, "length": [40, 100]},
            {"code": "cta", "purpose": "安全行动建议", "slots": [], "evidence_required": False, "length": [20, 60]},
        ],
        "slots": [
            ("pain", "brief", "business_variables.pain", True, False, "block"),
            ("price", "evidence", None, True, True, "ask_user"),
            ("product", "brief", "business_variables.product", True, False, "block"),
            ("process", "evidence", None, True, True, "ask_user"),
            ("advantage", "brief", "business_variables.advantage", True, False, "block"),
            ("result", "evidence", None, False, True, "omit"),
        ],
    },
    {
        "code": "C02-P01",
        "formula_code": "C02",
        "name": "案例成果六段式",
        "template_text": "背景/旧况→关键数据→过程→反差→结果→场景延伸",
        "content_type_codes": ["CT01", "CT05"],
        "paragraph_schema": [
            {"code": "background", "purpose": "交代真实背景", "slots": ["audience", "scene"], "evidence_required": False, "length": [40, 100]},
            {"code": "key_data", "purpose": "给出关键数据", "slots": ["number"], "evidence_required": True, "length": [30, 80]},
            {"code": "process", "purpose": "说明实施过程", "slots": ["process"], "evidence_required": True, "length": [80, 180]},
            {"code": "contrast", "purpose": "保持单一反差逻辑", "slots": [], "evidence_required": False, "length": [40, 100]},
            {"code": "result", "purpose": "交付真实结果", "slots": ["result"], "evidence_required": True, "length": [40, 100]},
            {"code": "extension", "purpose": "说明适用场景", "slots": ["scene"], "evidence_required": False, "length": [30, 80]},
        ],
        "slots": [
            ("audience", "brief", "audience", True, False, "block"),
            ("number", "evidence", None, True, True, "ask_user"),
            ("process", "evidence", None, True, True, "ask_user"),
            ("result", "evidence", None, True, True, "ask_user"),
            ("scene", "brief", "business_variables.scene", False, False, "omit"),
        ],
    },
    {
        "code": "C03-P01",
        "formula_code": "C03",
        "name": "干货教育五段式",
        "template_text": "问题/悬念→常见误区→专业正解→操作步骤→忠告",
        "content_type_codes": ["CT03", "CT04", "CT06"],
        "paragraph_schema": [
            {"code": "question", "purpose": "提出问题", "slots": ["pain"], "evidence_required": False, "length": [30, 70]},
            {"code": "mistake", "purpose": "说明常见误区", "slots": ["pain"], "evidence_required": False, "length": [50, 120]},
            {"code": "answer", "purpose": "给出专业正解", "slots": ["process"], "evidence_required": True, "length": [80, 180]},
            {"code": "steps", "purpose": "交付操作步骤", "slots": ["process"], "evidence_required": True, "length": [100, 220]},
            {"code": "advice", "purpose": "总结忠告", "slots": ["advice"], "evidence_required": False, "length": [20, 60]},
        ],
        "slots": [
            ("pain", "brief", "business_variables.pain", True, False, "block"),
            ("process", "evidence", None, True, True, "ask_user"),
            ("advice", "lexicon", None, True, False, "use_lexicon"),
        ],
    },
    {
        "code": "C04-P01",
        "formula_code": "C04",
        "name": "人设品牌五段式",
        "template_text": "人物经历→行业痛点→做事原则→差异优势→服务边界",
        "content_type_codes": ["CT07"],
        "paragraph_schema": [
            {"code": "experience", "purpose": "讲述真实人物经历", "slots": ["persona_fact"], "evidence_required": True, "length": [60, 140]},
            {"code": "pain", "purpose": "说明行业痛点", "slots": ["pain"], "evidence_required": False, "length": [40, 100]},
            {"code": "principle", "purpose": "表达做事原则", "slots": ["advantage"], "evidence_required": False, "length": [50, 120]},
            {"code": "difference", "purpose": "解释差异优势", "slots": ["advantage"], "evidence_required": False, "length": [50, 120]},
            {"code": "boundary", "purpose": "明确服务边界", "slots": ["process"], "evidence_required": True, "length": [30, 90]},
        ],
        "slots": [
            ("persona_fact", "persona", "experience_facts", True, True, "ask_user"),
            ("pain", "brief", "business_variables.pain", True, False, "block"),
            ("advantage", "brief", "business_variables.advantage", True, False, "block"),
            ("process", "evidence", None, True, True, "ask_user"),
        ],
    },
]


TYPE_STRATEGIES = {
    "CT01": {"methods": ["M01", "M04"], "titles": ["T01", "T06"], "body": "C02", "evidence": ["result", "process"]},
    "CT02": {"methods": ["M01", "M03"], "titles": ["T01", "T03"], "body": "C01", "evidence": ["price", "process"]},
    "CT03": {"methods": ["M02", "M03"], "titles": ["T04", "T05"], "body": "C03", "evidence": ["process"]},
    "CT04": {"methods": ["M01", "M03"], "titles": ["T07", "T05"], "body": "C03", "evidence": ["process"]},
    "CT05": {"methods": ["M01", "M04"], "titles": ["T01", "T06"], "body": "C02", "evidence": ["process", "result"]},
    "CT06": {"methods": ["M02", "M03"], "titles": ["T03", "T05"], "body": "C03", "evidence": ["process"]},
    "CT07": {"methods": ["M03", "M04"], "titles": ["T03", "T05"], "body": "C04", "evidence": ["persona_fact", "process"]},
}


WORKFLOW_V2 = {
    "slug": "enterprise-content-v2",
    "version": 2,
    "protocol_version": 2,
    "nodes": [
        {"id": "compile_context", "type": "compile_context"},
        {"id": "ingest_materials", "type": "ingest_materials", "skip_if": "materials_already_ingested"},
        {"id": "assemble_facts", "type": "assemble_facts"},
        {"id": "analyze_content_value", "type": "skill", "skill": "content-value-analyzer"},
        {"id": "select_content_angle", "type": "human_review", "interrupt_type": "select_content_angle", "optional": True},
        {"id": "match_strategy_v2", "type": "combination_engine_v2"},
        {"id": "resolve_formula_slots", "type": "formula_slot_resolver"},
        {"id": "collect_evidence", "type": "tool_group"},
        {"id": "confirm_high_risk_facts", "type": "human_review", "interrupt_type": "confirm_facts", "optional": True},
        {"id": "generate_title_candidates", "type": "skill", "skill": "content-title-generator"},
        {"id": "validate_title_candidates", "type": "deterministic_validator"},
        {"id": "select_title", "type": "human_review", "interrupt_type": "select_title"},
        {"id": "build_content_outline", "type": "skill", "skill": "content-outline-builder"},
        {"id": "generate_body_draft", "type": "skill", "skill": "content-body-generator"},
        {"id": "persona_style_polish", "type": "skill", "skill": "persona-style-polisher", "optional": True},
        {"id": "adapt_to_channel", "type": "channel_adapter"},
        {"id": "deterministic_validate", "type": "deterministic_validator"},
        {"id": "semantic_review", "type": "skill", "skill": "content-reviewer"},
        {"id": "human_approval", "type": "human_review", "interrupt_type": "human_approval", "optional": True},
        {"id": "save_artifact_and_snapshots", "type": "save_artifact"},
    ],
    "edges": [],
}
WORKFLOW_V2["edges"] = [
    [WORKFLOW_V2["nodes"][index]["id"], WORKFLOW_V2["nodes"][index + 1]["id"]]
    for index in range(len(WORKFLOW_V2["nodes"]) - 1)
]


INDUSTRY_CONFIG: dict[str, dict[str, Any]] = {
    "food": {
        "aliases": ["门店案例", "菜单价格透明", "到店避坑", "探店攻略", "后厨能力", "餐饮知识", "主理人故事"],
        "fields": [("signature_item", "招牌产品", "product"), ("average_spend", "客单价", "price"), ("service_process", "服务流程", "process"), ("customer_result", "顾客反馈", "result")],
        "terms": ["现点现做", "到店体验", "招牌风味", "后厨流程"],
        "persona": "门店主理人",
    },
    "education": {
        "aliases": ["学习案例", "课程方案透明", "选课避坑", "学习攻略", "教学能力", "知识讲解", "教师人设"],
        "fields": [("course", "课程", "product"), ("tuition", "课程价格", "price"), ("course_stage", "课程阶段", "audience"), ("teaching_process", "教学流程", "process"), ("learning_result", "学习结果", "result")],
        "terms": ["学习路径", "阶段目标", "课堂反馈", "因材施教"],
        "persona": "授课老师",
    },
    "beauty": {
        "aliases": ["护理案例", "项目价格透明", "护理避坑", "变美攻略", "服务能力", "护理知识", "手艺人人设"],
        "fields": [("service_item", "护理项目", "product"), ("service_price", "项目价格", "price"), ("service_process", "服务流程", "process"), ("care_result", "护理结果", "result"), ("skin_need", "护理需求", "pain")],
        "terms": ["肤质评估", "护理流程", "个体差异", "居家养护"],
        "persona": "护理师",
    },
    "retail": {
        "aliases": ["产品案例", "价格方案透明", "选购避坑", "使用攻略", "产品能力", "选购知识", "品牌人设"],
        "fields": [("product_name", "产品", "product"), ("sale_price", "销售价格", "price"), ("product_specs", "产品参数", "process"), ("usage_result", "使用结果", "result"), ("buyer_need", "购买需求", "pain")],
        "terms": ["规格参数", "使用场景", "选购标准", "售后边界"],
        "persona": "品牌选品人",
    },
    "professional-services": {
        "aliases": ["服务案例", "方案价格透明", "决策避坑", "办事攻略", "交付能力", "专业知识", "顾问人设"],
        "fields": [("service_name", "专业服务", "product"), ("service_fee", "服务费用", "price"), ("service_boundary", "服务边界", "process"), ("delivery_result", "交付结果", "result"), ("client_problem", "客户问题", "pain")],
        "terms": ["服务边界", "交付节点", "风险提示", "判断依据"],
        "persona": "专业顾问",
    },
    "decoration": {
        "aliases": ["装修案例分享", "装修报价清单", "装修避坑分享", "装修省钱攻略", "工艺施工展示", "装修知识科普", "装修人设自荐"],
        "fields": [("project_type", "户型", "product"), ("area", "面积", "quantity"), ("budget", "预算", "price"), ("duration", "工期", "duration"), ("craft_and_materials", "工艺材料", "process"), ("owner_pain", "居住痛点", "pain"), ("project_result", "完工结果", "result")],
        "terms": ["节点验收", "材料说明", "工艺标准", "预算边界"],
        "persona": "设计师或工长",
    },
}


DECORATION_LEXICON_CATEGORIES = [
    "户型", "面积", "装修风格", "空间", "房屋状态", "业主阶段", "家庭结构", "居住痛点", "装修需求",
    "预算区间", "报价构成", "费用项目", "材料品类", "材料品牌", "材料性能", "工艺节点", "施工流程",
    "拆改", "水电", "泥瓦", "木工", "油漆", "防水", "收口", "验收", "工期", "现场管理", "设计方案",
    "收纳", "采光", "动线", "色彩", "软装", "风险避坑",
]


def _slot_model(pattern_id: str, order: int, slot: tuple[str, str, str | None, bool, bool, str]) -> FormulaSlotBinding:
    key, source_type, source_path, required, evidence_required, fallback = slot
    lexicon_codes = []
    if source_type == "lexicon":
        lexicon_codes = [f"platform-{key}"]
    return FormulaSlotBinding(
        id=f"slot-{pattern_id.lower()}-{key}",
        pattern_id=pattern_id,
        slot_key=key,
        value_type="string",
        source_type=source_type,
        source_path=source_path,
        alternative_sources=[],
        lexicon_pack_codes=lexicon_codes,
        required=required,
        evidence_required=evidence_required,
        fallback_policy=fallback,
        validation_schema={},
        sort_order=order,
    )


def _form_fields(config: dict[str, Any], *, pro: bool) -> list[dict[str, Any]]:
    base = [
        {"key": "brand_name", "label": "品牌、门店或主理人", "type": "text", "required": True, "variable_code": "brand_name"},
        {"key": "audience", "label": "目标人群", "type": "tags", "required": True, "variable_code": "audience"},
        {"key": "pain", "label": "用户问题", "type": "tags", "required": True, "variable_code": "pain"},
        {"key": "advantage", "label": "差异化优势", "type": "tags", "required": True, "variable_code": "advantage"},
    ]
    industry = [
        {"key": key, "label": label, "type": "textarea", "required": variable in {"product", "process"}, "variable_code": variable, "evidence_required": variable in {"price", "duration", "quantity", "result", "process"}}
        for key, label, variable in config["fields"]
    ]
    if pro:
        base.extend(
            [
                {"key": "persona_profile_version_id", "label": "人设档案", "type": "persona", "required": False},
                {"key": "channel_profile_version_id", "label": "发布渠道", "type": "channel", "required": True},
                {"key": "knowledge_scope", "label": "知识库范围", "type": "knowledge", "required": False},
                {"key": "attachments", "label": "真实素材", "type": "materials", "required": False},
                {"key": "required_terms", "label": "必须包含", "type": "tags", "required": False},
                {"key": "forbidden_terms", "label": "禁止表达", "type": "tags", "required": False},
            ]
        )
    return base + industry


async def ensure_content_v2_seed_data(db: AsyncSession) -> None:
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
        {"lock_key": "yuxi_content_seed_v2"},
    )
    existing = await db.execute(select(ContentRuleVersion.id).where(ContentRuleVersion.id == PLATFORM_RULE_V2_ID))
    if existing.scalar_one_or_none():
        return

    now = utc_now_naive()
    db.add(
        ContentRuleVersion(
            id=PLATFORM_RULE_V2_ID,
            tenant_id=None,
            version=2,
            status="published",
            changelog="V2：七类内容类型、Pattern/Slot、变量、词库、行业包、渠道合规和确定性工作流",
            created_by="system",
            created_at=now,
            published_at=now,
        )
    )
    await db.flush()

    for order, item in enumerate(METHODS, 1):
        db.add(CreationMethod(id=f"method-{item['code'].lower()}-v2", version_id=PLATFORM_RULE_V2_ID, sort_order=order, enabled=True, **item))
    for order, item in enumerate(TITLE_FORMULAS, 1):
        db.add(TitleFormula(id=f"title-{item['code'].lower()}-v2", version_id=PLATFORM_RULE_V2_ID, sort_order=order, enabled=True, **item))
    for order, original in enumerate(BODY_FORMULAS, 1):
        item = deepcopy(original)
        item["industry_aliases"] = {}
        if item["code"] == "C02":
            item["name"] = "案例流量类"
        if item["code"] == "C03":
            item["name"] = "干货教育类"
        db.add(ContentFormula(id=f"body-{item['code'].lower()}-v2", version_id=PLATFORM_RULE_V2_ID, sort_order=order, enabled=True, **item))

    for order, item in enumerate(CONTENT_TYPES, 1):
        db.add(ContentTypeDefinition(id=f"content-type-{item['code'].lower()}-v2", version_id=PLATFORM_RULE_V2_ID, sort_order=order, enabled=True, **item))
    for order, (code, name, value_type, sensitivity, evidence_required) in enumerate(VARIABLES, 1):
        db.add(
            VariableDefinition(
                id=f"variable-{code}-v2",
                rule_version_id=PLATFORM_RULE_V2_ID,
                code=code,
                name=name,
                value_type=value_type,
                unit_schema={},
                evidence_policy={"required": evidence_required},
                sensitivity=sensitivity,
                allowed_usages=["title", "body", "topic", "media"],
                validation_schema={},
                enabled=True,
                sort_order=order,
            )
        )

    for order, (code, formula_code, name, template, slots) in enumerate(TITLE_PATTERNS, 1):
        db.add(
            FormulaPattern(
                id=code,
                rule_version_id=PLATFORM_RULE_V2_ID,
                formula_kind="title",
                formula_code=formula_code,
                code=code,
                name=name,
                template_text=template,
                paragraph_schema=[],
                content_type_codes=[item["code"] for item in CONTENT_TYPES],
                channel_scope=[],
                risk_policy={"unsupported_fact": "block"},
                enabled=True,
                sort_order=order,
            )
        )
        await db.flush()
        for slot_order, slot in enumerate(slots, 1):
            db.add(_slot_model(code, slot_order, slot))
    for order, item in enumerate(BODY_PATTERNS, 1):
        code = item["code"]
        db.add(
            FormulaPattern(
                id=code,
                rule_version_id=PLATFORM_RULE_V2_ID,
                formula_kind="body",
                formula_code=item["formula_code"],
                code=code,
                name=item["name"],
                template_text=item["template_text"],
                paragraph_schema=item["paragraph_schema"],
                content_type_codes=item["content_type_codes"],
                channel_scope=[],
                risk_policy={"unsupported_fact": "block", "paragraph_evidence_plan": True},
                enabled=True,
                sort_order=order,
            )
        )
        await db.flush()
        for slot_order, slot in enumerate(item["slots"], 1):
            db.add(_slot_model(code, slot_order, slot))

    title_pattern_by_formula = {formula: code for code, formula, *_ in TITLE_PATTERNS}
    body_pattern_by_formula = {item["formula_code"]: item["code"] for item in BODY_PATTERNS}
    for content_type in CONTENT_TYPES:
        type_code = content_type["code"]
        strategy = TYPE_STRATEGIES[type_code]
        for goal_order, goal in enumerate(content_type["supported_goals"], 1):
            db.add(
                ContentCombinationRule(
                    id=f"combination-{goal}-{type_code.lower()}-v2",
                    version_id=PLATFORM_RULE_V2_ID,
                    content_goal=goal,
                    content_type_codes=[type_code],
                    industry_scope=[],
                    channel_scope=[],
                    narrative_axis_codes=content_type["default_narrative_axes"],
                    methods=strategy["methods"],
                    title_formula_codes=strategy["titles"],
                    title_pattern_codes=[title_pattern_by_formula[code] for code in strategy["titles"]],
                    content_formula_code=strategy["body"],
                    body_pattern_codes=[body_pattern_by_formula[strategy["body"]]],
                    required_evidence_types=strategy["evidence"],
                    compatibility="compatible",
                    priority=100 - goal_order,
                    conditions={},
                    hard_conditions={"single_narrative_axis": True, "unsupported_numbers": "block"},
                    score_weights={"title_slot_complete": 12, "body_slot_complete": 15, "missing_slot_penalty": 30},
                    recommendation_reason=f"{content_type['name']}与{goal}目标的通用确定性组合",
                )
            )

    db.add(
        ContentWorkflowVersion(
            id=PLATFORM_WORKFLOW_V2_ID,
            slug="enterprise-content",
            tenant_id=None,
            version=2,
            status="published",
            definition_json=deepcopy(WORKFLOW_V2),
            input_schema={"type": "ContentBrief", "version": 2},
            output_schema={"type": "ContentArtifact", "version": 2},
            created_by="system",
            created_at=now,
            published_at=now,
        )
    )
    await db.flush()

    # 平台表达词库只包含跨行业语言，不含任何装修业务词。
    platform_lexicons = {
        "emotion": ["没想到", "真实体验", "终于讲清楚"],
        "suspense": ["很多人忽略了", "真正拉开差距的是", "先别急着决定"],
        "advice": ["建议先看清这一点", "做决定前先确认", "别只看表面"],
        "call_to_action": ["收藏备用", "按这份清单检查", "先记住这几步"],
    }
    for category, entries in platform_lexicons.items():
        pack_id = f"lexicon-platform-{category}"
        version_id = f"lexicon-platform-{category}-v1"
        db.add(LexiconPack(id=pack_id, code=f"platform-{category}", scope_type="platform", scope_id=None, tenant_id=None, name=f"平台{category}表达", semantic_category=category, description="跨行业固定表达", created_by="system", created_at=now))
        await db.flush()
        db.add(LexiconVersion(id=version_id, pack_id=pack_id, version=1, status="published", changelog="V2 平台初始词库", source_metadata={"source": "builtin"}, created_by="system", created_at=now, published_at=now))
        await db.flush()
        for order, value in enumerate(entries, 1):
            db.add(LexiconEntry(id=f"entry-platform-{category}-{order}", version_id=version_id, text=value, normalized_text=value.lower(), tags=[category], risk_level="safe", applicable_formula_codes=[], applicable_slot_keys=[category], enabled=True, sort_order=order))
        await db.flush()

    industry_rows = {item["slug"]: item for item in INDUSTRIES}
    for slug, config in INDUSTRY_CONFIG.items():
        source = industry_rows[slug]
        pack_id = f"industry-pack-{slug}-v2"
        lexicon_ids: list[str] = []
        if slug == "decoration":
            for order, category in enumerate(DECORATION_LEXICON_CATEGORIES, 1):
                lex_pack_id = f"lexicon-decoration-{order:02d}"
                lex_version_id = f"lexicon-decoration-{order:02d}-v1"
                lexicon_ids.append(lex_version_id)
                db.add(LexiconPack(id=lex_pack_id, code=f"decoration-{order:02d}", scope_type="industry", scope_id=slug, tenant_id=None, name=f"装修细分词库·{category}", semantic_category=category, description="装修与家居行业包专用，其他行业不可见", created_by="system", created_at=now))
                await db.flush()
                db.add(LexiconVersion(id=lex_version_id, pack_id=lex_pack_id, version=1, status="published", changelog="装修 34 个细分词库 V2 初始导入", source_metadata={"source": "decoration-v2", "source_pack_count": 34, "category_index": order}, created_by="system", created_at=now, published_at=now))
                await db.flush()
                db.add(LexiconEntry(id=f"entry-decoration-{order:02d}-1", version_id=lex_version_id, text=category, normalized_text=category, tags=["装修", category], risk_level="safe", applicable_formula_codes=[], applicable_slot_keys=[], enabled=True, sort_order=1))
                await db.flush()
        else:
            lex_pack_id = f"lexicon-{slug}-core"
            lex_version_id = f"lexicon-{slug}-core-v1"
            lexicon_ids.append(lex_version_id)
            db.add(LexiconPack(id=lex_pack_id, code=f"{slug}-core", scope_type="industry", scope_id=slug, tenant_id=None, name=f"{source['name']}核心表达", semantic_category="industry", description="行业专用表达", created_by="system", created_at=now))
            await db.flush()
            db.add(LexiconVersion(id=lex_version_id, pack_id=lex_pack_id, version=1, status="published", changelog="六行业 V2 初始词库", source_metadata={"source": "builtin"}, created_by="system", created_at=now, published_at=now))
            await db.flush()
            for order, value in enumerate(config["terms"], 1):
                db.add(LexiconEntry(id=f"entry-{slug}-{order}", version_id=lex_version_id, text=value, normalized_text=value.lower(), tags=[slug], risk_level="safe", applicable_formula_codes=[], applicable_slot_keys=[], enabled=True, sort_order=order))
            await db.flush()

        aliases = {item["code"]: alias for item, alias in zip(CONTENT_TYPES, config["aliases"], strict=True)}
        variable_schema = _form_fields(config, pro=True)
        db.add(
            IndustryContentPackVersion(
                id=pack_id,
                slug=slug,
                tenant_id=None,
                version=2,
                status="published",
                name=f"{source['name']} V2",
                description=source["description"],
                content_type_aliases=aliases,
                variable_schema=variable_schema,
                lexicon_version_ids=lexicon_ids,
                pattern_ids=[],
                combination_overrides=[],
                persona_templates=[{"name": config["persona"], "identity": config["persona"], "service_boundaries": []}],
                knowledge_scope=[],
                evidence_policy={"price": "confirm", "number": "confirm", "result": "confirm", "promise": "confirm"},
                review_policy={"unsupported_numbers": "block", "single_narrative_axis": True},
                created_by="system",
                created_at=now,
                published_at=now,
            )
        )
        await db.flush()
        for index, (field_key, _label, variable_code) in enumerate(config["fields"], 1):
            db.add(IndustryVariableMapping(id=f"mapping-{slug}-{field_key}", industry_pack_version_id=pack_id, field_key=field_key, variable_code=variable_code, transform_type="identity", transform_config={}, required_by_content_types=["CT01", "CT02", "CT03", "CT05"] if variable_code in {"product", "process"} else [],))

        # v1 模板只用于历史任务；新建任务使用指向 V2 工作流的完整行业模板。
        old_template = await db.get(IndustryTemplateVersion, f"industry-{slug}-v1")
        if old_template is not None:
            old_template.status = "superseded"
        db.add(
            IndustryTemplateVersion(
                id=f"industry-{slug}-v2",
                slug=slug,
                tenant_id=None,
                version=2,
                status="published",
                name=source["name"],
                description=source["description"],
                icon=source["icon"],
                quick_form_schema=_form_fields(config, pro=False),
                pro_form_schema=_form_fields(config, pro=True),
                default_goal=source["default_goal"],
                default_strategy={"content_type_code": "CT01", "channel_profile_version_id": XHS_CHANNEL_VERSION_ID},
                default_knowledge_scope=[],
                default_workflow_version_id=PLATFORM_WORKFLOW_V2_ID,
                review_policy={"require_sources_for_numbers": True, "block_unsupported_effect_claims": True, "human_title_selection": True, "single_narrative_axis": True},
                created_by="system",
                created_at=now,
                published_at=now,
            )
        )

    db.add(ChannelProfile(id=XHS_CHANNEL_PROFILE_ID, code="xiaohongshu", name="小红书", connector_type="xiaohongshu", created_at=now))
    await db.flush()
    db.add(ChannelProfileVersion(id=XHS_CHANNEL_VERSION_ID, profile_id=XHS_CHANNEL_PROFILE_ID, version=1, status="published", title_constraints={"min_length": 6, "max_length": 20, "emoji_allowed": True}, body_constraints={"min_length": 100, "max_length": 1000, "emoji_allowed": True}, topic_constraints={"min_count": 1, "max_count": 10}, media_constraints={"min_count": 1, "max_count": 18, "ratios": ["3:4", "1:1"]}, cta_policy={"allowed": ["收藏", "评论", "私信了解"], "forbidden": ["强制关注"]}, link_policy={"external_link": "blocked", "contact_info": "confirm"}, preview_schema={"type": "xiaohongshu-note"}, connector_config_ref="xiaohongshu", created_by="system", created_at=now, published_at=now))
    await db.flush()

    platform_policy_id = "compliance-platform-v1"
    channel_policy_id = "compliance-xiaohongshu-v1"
    decoration_policy_id = "compliance-decoration-v1"
    db.add(CompliancePolicyVersion(id=platform_policy_id, scope_type="platform", scope_id=None, tenant_id=None, version=1, status="published", name="平台基础事实合规", policy_config={"unsupported_numbers": "block", "unsupported_promises": "block"}, created_by="system", created_at=now, published_at=now))
    db.add(CompliancePolicyVersion(id=channel_policy_id, scope_type="channel", scope_id="xiaohongshu", tenant_id=None, version=1, status="published", name="小红书渠道合规", policy_config={"external_link": "block"}, created_by="system", created_at=now, published_at=now))
    db.add(CompliancePolicyVersion(id=decoration_policy_id, scope_type="industry", scope_id="decoration", tenant_id=None, version=1, status="published", name="装修与家居合规", policy_config={"price_promise": "confirm"}, created_by="system", created_at=now, published_at=now))
    await db.flush()
    replacement_rows = [
        (platform_policy_id, "ABSOLUTE_GUARANTEE", "百分百保证", "block", None, True, "禁止无证据的绝对承诺"),
        (platform_policy_id, "BEST_CLAIM", "全网最好", "replace", "更适合具体需求", False, "绝对化比较需要改为可验证表达"),
        (channel_policy_id, "EXTERNAL_LINK", r"https?://\\S+", "block", None, True, "小红书正文不允许外链"),
        (channel_policy_id, "CONTACT_INFO", r"(?:微信|VX|手机号)[:：]?\\s*[A-Za-z0-9_-]+", "confirm", None, True, "联系方式属于导流表达，需要人工确认"),
        (decoration_policy_id, "ZERO_ADDITION", "零增项", "confirm", None, True, "零增项必须明确合同范围并人工确认"),
        (decoration_policy_id, "GREEN_PROMISE", "百分百环保", "block", None, True, "环保绝对承诺不可发布"),
    ]
    for order, (policy_id, code, pattern, action, replacement, confirm, explanation) in enumerate(replacement_rows, 1):
        db.add(ReplacementRule(id=f"replacement-{code.lower()}", policy_version_id=policy_id, rule_code=code, pattern=pattern, match_type="regex" if pattern.startswith(("http", "(?:")) else "literal", risk_level="high" if action == "block" else "warning", action=action, replacement=replacement, human_confirmation_required=confirm, explanation=explanation, enabled=True, sort_order=order))

    await db.commit()
