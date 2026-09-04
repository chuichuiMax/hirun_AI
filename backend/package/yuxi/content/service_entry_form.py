from __future__ import annotations

from typing import Any

BRAND_NAME = "鸿扬家居"
DECORATION_QUOTE_KEYS = ("基础", "木制品", "主材")
REVIEW_NOTE_ROLE_KEYS = ("设计师", "预算师", "项目经理", "客户经理", "工匠")
REVIEW_NOTES_WRITING_INSTRUCTION = (
    "以业主第一人称评价设计师、预算师、项目经理、客户经理等项目成员；"
    "检索并模仿「好评知识库」中已有文章的语气、结构和用词；"
    "写内部可归档的真实好评，不要写成获客种草、员工自荐或销售转化文案。"
)


def configured_form_fields(
    variables: list[dict[str, Any]],
    *,
    service_entry: str,
    port: str,
    edition: str,
) -> list[dict[str, Any]]:
    return [
        {
            "key": item["name"],
            "label": item["name"],
            "type": "textarea",
            "required": True,
            "variable_code": item.get("variable_code"),
        }
        for item in variables
        if item.get("enabled")
        and item.get("service_entry") == service_entry
        and port in (item.get("ports") or [])
        and edition in (item.get("editions") or [])
    ]


FIELD_SELECT_OPTIONS: dict[str, list[str]] = {
    "外框面积": [
        "50-70㎡",
        "90-110㎡",
        "110-130㎡",
        "130-150㎡",
        "150-200㎡",
        "200-300㎡",
        "300㎡以上",
    ],
    "设计风格": ["现代简约", "轻奢", "新中式", "北欧", "奶油风", "原木风"],
    "项目阶段": ["拆改阶段", "水电阶段", "泥木阶段", "油漆阶段", "竣工交付"],
}

FIELD_PLACEHOLDERS: dict[str, str] = {
    "目标人群": "示例：毛坯装修三口之家",
    "楼盘信息": "示例：洋湖天序",
    "项目阶段": "请选择工种",
}

REGION_FIELD_NAMES = frozenset({"所在区域"})


def configured_business_variable_fields(
    bindings: list[dict[str, Any]],
    *,
    service_entry: str,
    content_type_id: str | None,
    port: str,
) -> list[dict[str, Any]]:
    """Build studio/MP form fields from business-variable bindings."""
    wanted_type_id = (content_type_id or "").strip()
    fields: list[dict[str, Any]] = []
    for item in bindings:
        if not item.get("enabled"):
            continue
        if item.get("service_entry") != service_entry:
            continue
        if port not in (item.get("ports") or []):
            continue
        binding_type_id = (item.get("content_type_id") or "").strip()
        if service_entry == "好评笔记":
            if binding_type_id:
                continue
        elif binding_type_id != wanted_type_id:
            continue
        name = str(item.get("variable_name") or "").strip()
        if not name:
            continue
        options = FIELD_SELECT_OPTIONS.get(name)
        if name in REGION_FIELD_NAMES:
            field_type = "region"
            placeholder = "请选择所在区域"
        elif options:
            field_type = "select"
            placeholder = FIELD_PLACEHOLDERS.get(name) or f"请选择{name}"
        else:
            field_type = "text"
            placeholder = FIELD_PLACEHOLDERS.get(name) or f"请输入{name}"
        field: dict[str, Any] = {
            "key": name,
            "label": name,
            "name": name,
            "type": field_type,
            "required": bool(item.get("required")),
            "variable_code": item.get("variable_code") or name,
            "variable_id": item.get("variable_id"),
            "placeholder": placeholder,
            "content_type_id": binding_type_id or None,
            "service_entry": service_entry,
            "ports": [port],
            "enabled": True,
        }
        if options:
            field["options"] = options
        fields.append(field)
    return fields


def map_service_entry_form_values(service_entry: str, form_values: dict[str, Any]) -> dict[str, Any]:
    values = {str(key): value for key, value in form_values.items()}
    community = str(values.get("楼盘信息") or "").strip()
    frame_area = str(values.get("外框面积") or "").strip()
    style = str(values.get("设计风格") or "").strip()
    region = str(values.get("所在区域") or "").strip()
    budget_text = "；".join(
        f"{label} {values[label]}".strip() for label in DECORATION_QUOTE_KEYS if str(values.get(label) or "").strip()
    )
    persona_text = "，".join(
        f"{label} {values[label]}".strip() for label in REVIEW_NOTE_ROLE_KEYS if str(values.get(label) or "").strip()
    )

    if service_entry == "装修家居":
        product = community or "整装项目"
        process = budget_text or f"{style} {frame_area}".strip() or "整装交付"
        pain = f"{community or '业主'}关注{frame_area or '户型'}装修落地"
        advantage = style or "鸿扬整装标准化交付"
        audience = [region] if region else ["装修业主"]
        result = " ".join(part for part in (community, frame_area, style) if part)
    else:
        product = "业主好评笔记"
        process = persona_text or "项目成员服务"
        pain = "业主记录装修交付中项目成员的真实服务体验"
        advantage = persona_text or "项目成员服务"
        audience = ["业主"]
        result = persona_text
        values["voice"] = "业主第一人称"
        values["location"] = region
        values["writing_instruction"] = REVIEW_NOTES_WRITING_INSTRUCTION

    return {
        **values,
        "brand_name": BRAND_NAME,
        "audience": audience,
        "pain": pain,
        "advantage": advantage,
        "project_type": product,
        "area": frame_area,
        "budget": budget_text,
        "craft_and_materials": process,
        "owner_pain": pain,
        "project_result": result,
        "persona": persona_text,
    }
