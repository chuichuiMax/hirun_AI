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
_VISUAL_UNSUPPORTED_CLAIM_TERMS = ("免费", "保证", "保价", "最低", "第一", "省钱", "零风险")


def apply_visual_text_max_char_floor(role: str, max_chars: int | None) -> int | None:
    if not isinstance(max_chars, int) or max_chars <= 0:
        return max_chars
    floor = VISUAL_TEXT_MAX_CHAR_FLOORS.get(str(role or "").strip())
    if floor is None:
        return max_chars
    return max(max_chars, floor)


def resolved_visual_text_max_chars(role: str, constraints: dict[str, Any]) -> int | None:
    """Keep every template's declared physical capacity authoritative."""
    del role
    max_chars = constraints.get("maxChars")
    return max_chars if isinstance(max_chars, int) and max_chars > 0 else None


def is_decorative_cover_label(value: object) -> bool:
    """序号角标（1 / 01）不是封面主标题，解析与校验时需跳过。"""
    text = str(value or "").strip()
    if not text:
        return True
    return bool(re.fullmatch(r"0?\d{1,2}", text))


def visual_text_char_count(value: str) -> int:
    return len(value.replace("\n", ""))


def clamp_visual_text(value: str, max_chars: int | None) -> str:
    """把封面文案压进框容量，优先在标点处收束，避免再打回模型。"""
    text = str(value or "").strip()
    if not isinstance(max_chars, int) or max_chars <= 0 or visual_text_char_count(text) <= max_chars:
        return text
    plain = text.replace("\n", "")
    cut = plain[:max_chars]
    for sep in ("，", "。", "、", "！", "？", "；", ",", ".", " "):
        idx = cut.rfind(sep)
        if idx >= max(4, max_chars // 2):
            cut = cut[:idx]
            break
    return cut.strip() or plain[:max_chars]


def normalize_visual_text(value: str) -> str:
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE).casefold()


def contains_unsupported_visual_claim(value: str) -> bool:
    return any(term in value for term in _VISUAL_UNSUPPORTED_CLAIM_TERMS)


def uniquify_visual_template_fields(
    fields: dict[str, str],
    *,
    limits: dict[str, dict[str, int]],
    extra_texts: list[str],
) -> dict[str, str]:
    """超长截入 maxChars；重复框改成不同信息点，避免 visual_text_duplicate 二次调用。"""
    repaired: dict[str, str] = {}
    used_norm: dict[str, str] = {}
    unused_extras = [str(item).strip() for item in extra_texts if str(item).strip()]

    def accept(label: str, raw: str, max_chars: int | None) -> tuple[str, str] | None:
        value = clamp_visual_text(raw, max_chars)
        if not value or is_decorative_cover_label(value) or contains_unsupported_visual_claim(value):
            return None
        norm = normalize_visual_text(value)
        if not norm or norm in used_norm:
            return None
        return value, norm

    for label, raw in fields.items():
        max_chars = (limits.get(label) or {}).get("maxChars")
        chosen = accept(label, raw, max_chars)
        if chosen is None:
            for extra in list(unused_extras):
                chosen = accept(label, extra, max_chars)
                if chosen is not None:
                    unused_extras.remove(extra)
                    break
        if chosen is None:
            plain = clamp_visual_text(raw, max_chars).replace("\n", "")
            for start in range(1, max(1, len(plain) - 3)):
                chosen = accept(label, plain[start:], max_chars)
                if chosen is not None:
                    break
        if chosen is None:
            repaired[label] = clamp_visual_text(raw, max_chars)
            continue
        value, norm = chosen
        repaired[label] = value
        used_norm[norm] = label
    return repaired


def is_ordinal_badge_template_field(field: dict[str, Any]) -> bool:
    """模板里的 01/1 短序号框不能当叙事标题：容量通常只有 1～2 字，会把整页 title 上限压坏。"""
    role = str(field.get("semanticRole") or "").strip()
    if role == "label":
        return True
    label = str(field.get("label") or "").strip()
    if is_decorative_cover_label(label):
        return True
    constraints = field.get("constraints") or {}
    max_chars = constraints.get("maxChars")
    if role in {"title", "subtitle", "body_excerpt"} and isinstance(max_chars, int) and 0 < max_chars <= 2:
        return True
    return False


def ordinal_badge_fill_value(field: dict[str, Any]) -> str:
    """给序号角标填一个不超过 maxChars 的装饰值，满足 HyCanvas required，又不挤占叙事标题。

    例：label=01 且 maxChars=1 → "1"；label=01 且 maxChars=2 → "01"。
    """
    label = str(field.get("label") or "").strip()
    value = label if is_decorative_cover_label(label) else "1"
    if not value:
        value = "1"
    constraints = field.get("constraints") or {}
    max_chars = constraints.get("maxChars")
    if isinstance(max_chars, int) and max_chars > 0:
        value = value[-max_chars:]
    return value


def resolve_visual_cover_title(
    *,
    visual_text: list[str] | None,
    template_fields: dict[str, str] | None,
    declarations: list[dict[str, Any]] | None = None,
) -> str:
    fields = template_fields or {}
    preferred_roles = ("title", "subtitle", "body_excerpt")
    pools: list[list[str]] = []

    role_values: list[str] = []
    for role in preferred_roles:
        for field in declarations or []:
            if str(field.get("semanticRole") or "") != role:
                continue
            key = str(field.get("key") or field.get("label") or "").strip()
            value = str(fields.get(key) or "").strip()
            if value:
                role_values.append(value)
        if role == "title" and role_values:
            break
    if role_values:
        pools.append(role_values)

    text_values = [str(item or "").strip() for item in (visual_text or []) if str(item or "").strip()]
    if text_values:
        pools.append(text_values)

    other_values = [str(value or "").strip() for value in fields.values() if str(value or "").strip()]
    if other_values:
        pools.append(other_values)

    for pool in pools:
        for value in pool:
            if not is_decorative_cover_label(value):
                return value
    for pool in pools:
        if pool:
            return max(pool, key=len)
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
    "resolved_visual_text_max_chars",
    "is_decorative_cover_label",
    "is_ordinal_badge_template_field",
    "missing_required_template_fields",
    "resolve_visual_cover_title",
    "template_fact_sources",
]
