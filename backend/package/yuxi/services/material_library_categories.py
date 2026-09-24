from __future__ import annotations

from typing import Literal

MaterialType = Literal["image", "cover_template"]

AI_GENERATED_GALLERY_ID = "product"
MY_LIBRARY_GALLERY_ID = "uncategorized"
RETIRED_PRIVATE_IMAGE_CATEGORY_IDS = frozenset({"people", "scene", "background", "decoration", "brand"})

MATERIAL_CATEGORIES: dict[MaterialType, tuple[dict[str, str], ...]] = {
    "image": (
        {"code": AI_GENERATED_GALLERY_ID, "name": "AI生图图库", "description": "小程序生图工作流保存的图片"},
        {"code": MY_LIBRARY_GALLERY_ID, "name": "我的图库", "description": "保留的个人图库图片"},
    ),
    "cover_template": (
        {"code": "product_promotion", "name": "产品推广", "description": "新品发布、卖点介绍和商品主视觉"},
        {"code": "marketing", "name": "营销促销", "description": "折扣、限时、优惠券和转化活动"},
        {"code": "knowledge", "name": "知识科普", "description": "知识分享、教程要点和专业解读"},
        {"code": "guide", "name": "攻略清单", "description": "步骤指南、方法清单和实用建议"},
        {"code": "comparison", "name": "测评对比", "description": "产品测评、方案对比和前后效果"},
        {"code": "event", "name": "活动招募", "description": "会议、直播、课程和线下活动"},
        {"code": "festival", "name": "节日节气", "description": "节日营销、节气和纪念日内容"},
        {"code": "brand", "name": "品牌宣传", "description": "品牌故事、企业形象和价值主张"},
        {"code": "lifestyle", "name": "生活方式", "description": "穿搭、美食、旅行、家居和日常分享"},
        {"code": "other", "name": "其他", "description": "明确用途但不属于以上标准分类的模板"},
        {"code": "uncategorized", "name": "未分类", "description": "待整理或无法判断用途的历史模板"},
    ),
}

DEFAULT_IMAGE_CATEGORY_IDS = frozenset(item["code"] for item in MATERIAL_CATEGORIES["image"])


def _aliases(material_type: MaterialType) -> dict[str, str]:
    aliases = {item["name"]: item["code"] for item in MATERIAL_CATEGORIES[material_type]}
    aliases.update({item["code"]: item["code"] for item in MATERIAL_CATEGORIES[material_type]})
    if material_type == "image":
        aliases.update({
            "商品": AI_GENERATED_GALLERY_ID,
            "产品": AI_GENERATED_GALLERY_ID,
            "产品商品": AI_GENERATED_GALLERY_ID,
            "未分类": MY_LIBRARY_GALLERY_ID,
            "封面素材": MY_LIBRARY_GALLERY_ID,
        })
    else:
        aliases.update({"产品": "product_promotion", "促销": "marketing", "封面素材": "uncategorized"})
    return aliases


def normalize_material_category(material_type: MaterialType, value: str | None) -> str:
    normalized = (value or "").strip()
    if not normalized:
        return "uncategorized"
    return _aliases(material_type).get(normalized, "uncategorized")


def resolve_legacy_category(material_type: MaterialType, value: str | None) -> str | None:
    return _aliases(material_type).get((value or "").strip())


def validate_material_category(material_type: MaterialType, value: str | None) -> str:
    normalized = (value or "").strip()
    code = _aliases(material_type).get(normalized)
    if code is None or code == "uncategorized":
        raise ValueError("请选择一个有效的素材分类")
    return code


def category_definition(material_type: MaterialType, value: str | None) -> dict[str, str]:
    code = normalize_material_category(material_type, value)
    return next(item for item in MATERIAL_CATEGORIES[material_type] if item["code"] == code)


def list_material_categories(material_type: MaterialType) -> list[dict[str, str]]:
    return [dict(item) for item in MATERIAL_CATEGORIES[material_type]]


def category_filter_values(material_type: MaterialType, code: str) -> tuple[str, ...]:
    return tuple(value for value, mapped in _aliases(material_type).items() if mapped == code)


def known_category_values(material_type: MaterialType) -> tuple[str, ...]:
    return tuple(_aliases(material_type))
