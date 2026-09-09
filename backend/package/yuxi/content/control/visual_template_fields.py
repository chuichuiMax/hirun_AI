from __future__ import annotations

import re
from typing import Any

# 保存模板时若用短样本文案会把 maxChars 设成 4～6，封面叙事无法成句。
# 生产侧按语义角色抬升下限；布局仍由模板约束上界决定。
VISUAL_TEXT_MAX_CHAR_FLOORS: dict[str, int] = {
    "title": 12,
    "subtitle": 16,
    "body_excerpt": 24,
}


def apply_visual_text_max_char_floor(role: str, max_chars: int | None) -> int | None:
    if not isinstance(max_chars, int) or max_chars <= 0:
        return max_chars
    floor = VISUAL_TEXT_MAX_CHAR_FLOORS.get(str(role or "").strip())
    if floor is None:
        return max_chars
    return max(max_chars, floor)


def resolve_visual_cover_title(
    *,
    visual_text: list[str] | None,
    template_fields: dict[str, str] | None,
    declarations: list[dict[str, Any]] | None = None,
) -> str:
    for item in visual_text or []:
        value = str(item or "").strip()
        if value:
            return value
    fields = template_fields or {}
    preferred_roles = ("title", "subtitle", "body_excerpt")
    for role in preferred_roles:
        for field in declarations or []:
            if str(field.get("semanticRole") or "") != role:
                continue
            key = str(field.get("key") or field.get("label") or "").strip()
            value = str(fields.get(key) or "").strip()
            if value:
                return value
    for value in fields.values():
        text = str(value or "").strip()
        if text:
            return text
    return ""


def template_fact_sources(brief: dict[str, Any]) -> dict[str, str]:
    form_values = brief.get("form_values") or {}
    brand = brief.get("brand") or {}
    return {
        "project_name": str(form_values.get("project_name") or form_values.get("community_name") or "").strip(),
        "project_name_en": str(
            form_values.get("project_name_en") or form_values.get("community_name_en") or ""
        ).strip(),
        "project_area": str(
            form_values.get("project_area") or form_values.get("area") or form_values.get("area_sqm") or ""
        ).strip(),
        "designer": str(form_values.get("designer") or form_values.get("designer_name") or "").strip(),
        "completion_year": str(form_values.get("completion_year") or form_values.get("year") or "").strip(),
        "brand_name": str(brand.get("name") or form_values.get("brand_name") or "").strip(),
    }


def missing_required_template_fields(
    declarations: list[dict[str, Any]], brief: dict[str, Any]
) -> dict[str, dict[str, int]]:
    sources = template_fact_sources(brief)
    missing: dict[str, dict[str, int]] = {}
    for field in declarations:
        label = str(field.get("label") or "").strip()
        field_key = str(field.get("key") or label).strip()
        role = str(field.get("semanticRole") or "").strip()
        constraints = field.get("constraints") or {}
        if field.get("kind") != "text" or not label or role in {"", "label", "title", "subtitle", "body_excerpt"}:
            continue
        value = sources.get(role, "")
        if role == "project_area" and not re.search(r"\d+(?:\.\d+)?", value):
            value = ""
        elif role == "completion_year" and not re.search(r"(?:19|20)\d{2}", value):
            value = ""
        if constraints.get("required") and not value:
            missing[field_key] = {
                key: int(constraints[key])
                for key in ("maxChars", "maxCharsPerLine", "maxLines")
                if isinstance(constraints.get(key), int) and constraints[key] > 0
            }
    return missing


__all__ = [
    "VISUAL_TEXT_MAX_CHAR_FLOORS",
    "apply_visual_text_max_char_floor",
    "missing_required_template_fields",
    "resolve_visual_cover_title",
    "template_fact_sources",
]
