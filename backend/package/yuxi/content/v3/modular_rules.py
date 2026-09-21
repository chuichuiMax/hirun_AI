"""V5 模块规则：编译冻结 bundle、条件装配 Skill、回修路由与视觉意图。"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml

BUNDLE_VERSION = "content-rule-bundle-v5.0"
EXPRESSION_KB_NAMES = ("我的优势", "表达语气库", "具象表达")
EXPRESSION_MAX_CHUNKS = 2
EXPRESSION_RETRIEVE_CANDIDATES = 8
EXPRESSION_MAX_CHARS = 1200
_EXPRESSION_PART_SPLIT = re.compile(r"(?<=[。！？；\n|])")
_EXPRESSION_CITY_RE = re.compile(
    r"北京|上海|广州|深圳|杭州|成都|武汉|南京|苏州|重庆|西安|"
    r"[\u4e00-\u9fff]{2,8}(?:市|县|镇)|"
    r"[\u4e00-\u9fff]{2,8}区(?!域|别|分)"
)
ADVANTAGE_KB_NAME = "我的优势"

VIRAL_AUTHOR_CORE = "viral-author-core"
VIRAL_TITLE_AUTHOR = "viral-title-author"
VIRAL_BODY_AUTHOR = "viral-body-author"
VIRAL_PERSONA_AUTHOR = "viral-persona-author"
VIRAL_NATURAL_EXPRESSION = "viral-natural-expression"
VIRAL_LAYOUT_EXPRESSION = "viral-layout-expression"
VIRAL_PLATFORM_EXPRESSION = "viral-platform-expression"
VIRAL_PRICE_AUTHOR = "viral-price-author"
VIRAL_TOPIC_AUTHOR = "viral-topic-author"
VIRAL_MODULAR_REVIEWER = "viral-modular-reviewer"
VIRAL_COVER_MATCHER = "viral-cover-matcher"
VISUAL_PLANNER = "content-visual-planner"

GENERATE_ALWAYS_SKILLS = (
    VIRAL_AUTHOR_CORE,
    VIRAL_TITLE_AUTHOR,
    VIRAL_BODY_AUTHOR,
    VIRAL_PERSONA_AUTHOR,
    VIRAL_NATURAL_EXPRESSION,
    VIRAL_LAYOUT_EXPRESSION,
    VIRAL_PLATFORM_EXPRESSION,
    VIRAL_TOPIC_AUTHOR,
)
GENERATE_ALL_SKILLS = (*GENERATE_ALWAYS_SKILLS, VIRAL_PRICE_AUTHOR)
REVIEW_SKILLS = (VIRAL_MODULAR_REVIEWER,)
COVER_SKILLS = (VISUAL_PLANNER, VIRAL_COVER_MATCHER)

MODULE_SPECS: tuple[tuple[str, str], ...] = (
    (VIRAL_AUTHOR_CORE, "爆款创作核心"),
    (VIRAL_TITLE_AUTHOR, "爆款标题"),
    (VIRAL_BODY_AUTHOR, "爆款正文"),
    (VIRAL_PERSONA_AUTHOR, "爆款人设"),
    (VIRAL_NATURAL_EXPRESSION, "自然表达"),
    (VIRAL_LAYOUT_EXPRESSION, "排版表达"),
    (VIRAL_PLATFORM_EXPRESSION, "平台表达"),
    (VIRAL_PRICE_AUTHOR, "报价表达"),
    (VIRAL_TOPIC_AUTHOR, "话题表达"),
    (VIRAL_MODULAR_REVIEWER, "模块审核"),
    (VIRAL_COVER_MATCHER, "封面匹配"),
)

_REVISION_PREFIX_SKILLS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("TITLE_", (VIRAL_AUTHOR_CORE, VIRAL_TITLE_AUTHOR)),
    ("TOPIC_", (VIRAL_AUTHOR_CORE, VIRAL_TOPIC_AUTHOR)),
    ("PRICE_", (VIRAL_AUTHOR_CORE, VIRAL_PRICE_AUTHOR)),
    ("CTA_", (VIRAL_AUTHOR_CORE, VIRAL_PLATFORM_EXPRESSION)),
    ("LAYOUT_", (VIRAL_AUTHOR_CORE, VIRAL_LAYOUT_EXPRESSION)),
    ("PERSONA_", (VIRAL_AUTHOR_CORE, VIRAL_PERSONA_AUTHOR, VIRAL_NATURAL_EXPRESSION)),
    ("BODY_", (VIRAL_AUTHOR_CORE, VIRAL_BODY_AUTHOR, VIRAL_LAYOUT_EXPRESSION, VIRAL_NATURAL_EXPRESSION)),
)

DEFAULT_TOPIC_POOL = (
    "旧房翻新",
    "局部改造",
    "全屋装修",
    "装修避坑",
    "装修报价",
    "施工工艺",
    "水电改造",
    "泥瓦工程",
    "木工细节",
    "油漆验收",
    "收房验房",
    "装修日记",
    "家装设计",
    "装修预算",
    "装修工期",
    "装修材料",
    "装修效果",
    "装修经验",
    "装修建议",
    "装修案例",
)

_PRICE_KEYS = ("报价", "价格", "预算价", "单价", "总价", "quote", "price")
_PARTIAL_MARKERS = ("局改", "局部改造", "局部装修", "局部翻新")
_CRAFT_MARKERS = ("工艺", "工序", "施工细节", "水电", "泥瓦", "木工", "油漆", "防水")
_WHOLE_HOUSE_MARKERS = ("整装", "全屋", "整屋", "全屋装修")
_KEYCAP_NUMBER = re.compile(r"[0-9]\uFE0F?\u20E3|[\U0001F1E6-\U0001F1FF]|[\U0001F300-\U0001FAFF]")


def _skills_root() -> Path:
    return Path(__file__).resolve().parents[2] / "agents" / "skills" / "buildin"


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load_module_rule_file(slug: str) -> dict[str, Any]:
    path = _skills_root() / slug / "references" / "rules.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"模块规则文件缺失: {slug}")
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"模块规则文件必须是对象: {slug}")
    return loaded


def _module_snapshot(slug: str, display_name: str) -> dict[str, Any]:
    skill_md = (_skills_root() / slug / "SKILL.md").read_text(encoding="utf-8")
    rules = load_module_rule_file(slug)
    rule_items = list(rules.get("rules") or [])
    active_ids = [str(item["id"]) for item in rule_items if item.get("id") and item.get("enabled", True)]
    return {
        "slug": slug,
        "display_name": display_name,
        "version": str(rules.get("version") or "1.0.0"),
        "content_hash": _hash_text(skill_md),
        "rules_hash": _hash_text(_canonical(rules)),
        "active_rule_ids": active_ids,
        "runtime_rules": [
            {
                "id": str(item["id"]),
                "module": slug,
                "text": str(item.get("text") or "").strip(),
            }
            for item in rule_items
            if item.get("id") and item.get("enabled", True) and str(item.get("text") or "").strip()
        ],
    }


def topic_candidate_pool(*, brief: dict[str, Any] | None = None, extra: Iterable[str] = ()) -> list[str]:
    pool: list[str] = []
    seen: set[str] = set()
    for item in (*extra, *DEFAULT_TOPIC_POOL):
        text = str(item or "").strip().lstrip("#")
        if not text or text in seen:
            continue
        seen.add(text)
        pool.append(text)
    form_values = (brief or {}).get("form_values") if isinstance(brief, dict) else {}
    if isinstance(form_values, dict):
        for key in ("topic", "content_goal", "process_type", "project_stage"):
            value = str(form_values.get(key) or "").strip()
            if value and value not in seen:
                seen.add(value)
                pool.append(value)
    return pool[:40]


def compile_content_rule_bundle(
    *,
    brief: dict[str, Any] | None = None,
    strategy_snapshot: dict[str, Any] | None = None,
    extra_topics: Iterable[str] = (),
) -> dict[str, Any]:
    modules = [_module_snapshot(slug, name) for slug, name in MODULE_SPECS]
    topics = topic_candidate_pool(brief=brief, extra=extra_topics)
    runtime_rules = [rule for module in modules for rule in module["runtime_rules"]]
    payload = {
        "bundle_version": BUNDLE_VERSION,
        "modules": [
            {
                key: module[key]
                for key in ("slug", "display_name", "version", "content_hash", "rules_hash", "active_rule_ids")
            }
            for module in modules
        ],
        "active_rule_ids": [rule["id"] for rule in runtime_rules],
        "runtime_rules": runtime_rules,
        "topic_candidate_pool": topics,
        "locked_strategy": {
            "title_formula_code": ((strategy_snapshot or {}).get("title_formula") or {}).get("code"),
            "body_formula_code": ((strategy_snapshot or {}).get("body_formula") or {}).get("code"),
        },
    }
    payload["bundle_hash"] = _hash_text(_canonical(payload))
    return payload


def has_price_signal(
    *,
    evidence_bundle: dict[str, Any] | None = None,
    strategy_snapshot: dict[str, Any] | None = None,
    brief: dict[str, Any] | None = None,
) -> bool:
    strategy = strategy_snapshot or {}
    if strategy.get("quote_type") or (strategy.get("title_formula") or {}).get("requires_price"):
        return True
    formula_code = str((strategy.get("title_formula") or {}).get("code") or "")
    if formula_code in {"T02", "T04"} or "报价" in formula_code:
        return True
    for item in (evidence_bundle or {}).get("items") or []:
        if not isinstance(item, dict):
            continue
        metadata = item.get("metadata") or {}
        if metadata.get("material_type") == "price":
            return True
        blob = f"{item.get('key') or ''} {json.dumps(item.get('value'), ensure_ascii=False)}"
        if any(token in blob for token in _PRICE_KEYS):
            return True
    form_values = (brief or {}).get("form_values") if isinstance(brief, dict) else {}
    if isinstance(form_values, dict):
        joined = " ".join(str(value) for value in form_values.values())
        if any(token in joined for token in _PRICE_KEYS):
            return True
    return False


def revision_skill_slugs(block_codes: Iterable[str]) -> list[str]:
    slugs: list[str] = []
    seen: set[str] = set()
    codes = [str(code or "").upper() for code in block_codes if code]
    for prefix, mapped in _REVISION_PREFIX_SKILLS:
        if any(code.startswith(prefix) for code in codes):
            for slug in mapped:
                if slug not in seen:
                    seen.add(slug)
                    slugs.append(slug)
    return slugs


def assemble_required_skills(
    *,
    node_id: str,
    block_codes: Iterable[str] = (),
    has_price: bool = False,
) -> list[str]:
    if node_id == "semantic_review":
        return list(REVIEW_SKILLS)
    if node_id == "plan_visuals":
        return list(COVER_SKILLS)
    if node_id != "generate_content":
        return []
    revision = revision_skill_slugs(block_codes)
    if revision:
        if has_price and VIRAL_PRICE_AUTHOR not in revision and any(
            str(code).upper().startswith("PRICE_") for code in block_codes
        ):
            revision.append(VIRAL_PRICE_AUTHOR)
        return revision
    skills = list(GENERATE_ALWAYS_SKILLS)
    if has_price:
        skills.append(VIRAL_PRICE_AUTHOR)
    return skills


def strip_keycap_numbers(text: str) -> str:
    return _KEYCAP_NUMBER.sub("", text or "")


def _joined_text(*parts: Any) -> str:
    chunks: list[str] = []
    for part in parts:
        if isinstance(part, dict):
            chunks.append(json.dumps(part, ensure_ascii=False))
        elif isinstance(part, (list, tuple)):
            chunks.extend(str(item) for item in part)
        elif part:
            chunks.append(str(part))
    return " ".join(chunks)


def resolve_visual_intent(
    *,
    brief: dict[str, Any] | None = None,
    evidence_bundle: dict[str, Any] | None = None,
    has_price: bool | None = None,
) -> str:
    form_values = (brief or {}).get("form_values") if isinstance(brief, dict) else {}
    variables = (brief or {}).get("business_variables") if isinstance(brief, dict) else {}
    text = _joined_text(form_values, variables, brief or {}, *((evidence_bundle or {}).get("items") or []))
    priced = has_price if has_price is not None else has_price_signal(
        evidence_bundle=evidence_bundle, brief=brief
    )
    if any(marker in text for marker in _PARTIAL_MARKERS):
        return "partial_renovation"
    if any(marker in text for marker in _CRAFT_MARKERS):
        return "craft_detail"
    if priced and any(marker in text for marker in _WHOLE_HOUSE_MARKERS):
        return "whole_house_quote"
    return "scene_general"


def expression_guidance_forbidden(text: str) -> list[str]:
    hits: list[str] = []
    if re.search(r"[\u4e00-\u9fff]{2,4}(?:师傅|设计师|经理)", text):
        hits.append("person")
    if _EXPRESSION_CITY_RE.search(text):
        hits.append("city")
    if re.search(r"\d+(?:\.\d+)?", strip_keycap_numbers(text)):
        hits.append("number")
    if any(token in text for token in _PRICE_KEYS):
        hits.append("price")
    if any(token in text for token in ("经历", "业主反馈", "承诺", "保证", "包修")):
        hits.append("experience_or_promise")
    return hits


def _expression_parts(text: str) -> list[str]:
    return [part.strip(" |") for part in _EXPRESSION_PART_SPLIT.split(text) if part.strip(" |")]


def summarize_expression_sanitize(chunks: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for chunk in chunks:
        for part in _expression_parts(str(chunk or "")):
            for hit in expression_guidance_forbidden(part):
                counts[hit] = counts.get(hit, 0) + 1
    return counts


def sanitize_expression_chunks(chunks: list[str]) -> list[str]:
    cleaned: list[str] = []
    for chunk in chunks:
        kept = [
            part
            for part in _expression_parts(str(chunk or ""))
            if part and not expression_guidance_forbidden(part)
        ]
        if not kept:
            continue
        joined = "".join(part if part.endswith(("。", "！", "？", "；")) else f"{part}。" for part in kept)
        cleaned.append(joined[:EXPRESSION_MAX_CHARS])
        if len(cleaned) >= EXPRESSION_MAX_CHUNKS:
            break
    return cleaned


def freeze_expression_snapshot(
    *,
    libraries: dict[str, list[str]],
    advantage_chunks: list[str],
) -> dict[str, Any]:
    payload = {
        "kb_names": list(EXPRESSION_KB_NAMES),
        "advantage_chunks": [text[:EXPRESSION_MAX_CHARS] for text in advantage_chunks[:EXPRESSION_MAX_CHUNKS]],
        "expression_guidance": {
            "tone": [text[:EXPRESSION_MAX_CHARS] for text in libraries.get("表达语气库") or []][
                :EXPRESSION_MAX_CHUNKS
            ],
            "concrete": [text[:EXPRESSION_MAX_CHARS] for text in libraries.get("具象表达") or []][
                :EXPRESSION_MAX_CHUNKS
            ],
        },
    }
    payload["snapshot_hash"] = _hash_text(_canonical(payload))
    return payload


__all__ = [
    "ADVANTAGE_KB_NAME",
    "BUNDLE_VERSION",
    "COVER_SKILLS",
    "EXPRESSION_KB_NAMES",
    "EXPRESSION_MAX_CHARS",
    "EXPRESSION_MAX_CHUNKS",
    "EXPRESSION_RETRIEVE_CANDIDATES",
    "GENERATE_ALL_SKILLS",
    "GENERATE_ALWAYS_SKILLS",
    "MODULE_SPECS",
    "REVIEW_SKILLS",
    "VIRAL_PRICE_AUTHOR",
    "assemble_required_skills",
    "compile_content_rule_bundle",
    "expression_guidance_forbidden",
    "freeze_expression_snapshot",
    "has_price_signal",
    "resolve_visual_intent",
    "revision_skill_slugs",
    "sanitize_expression_chunks",
    "summarize_expression_sanitize",
    "strip_keycap_numbers",
    "topic_candidate_pool",
]
