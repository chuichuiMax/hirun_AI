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
