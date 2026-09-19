from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from yuxi.content.rules import brief_variable_map

NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?(?:%|元|万元|天|周|月|年|个|次|㎡|人)?")
HIGH_RISK_CLAIMS = ("保证", "百分百", "100%", "一定有效", "绝对", "零风险", "最便宜", "第一")


def _evidence_id(task_id: str, key: str, value: Any) -> str:
    digest = hashlib.sha256(
        f"{task_id}:{key}:{json.dumps(value, ensure_ascii=False, sort_keys=True)}".encode()
    ).hexdigest()[:16]
    return f"ev_{digest}"


def normalize_manual_evidence(task_id: str, brief: dict[str, Any]) -> dict[str, Any]:
    variables = brief_variable_map(brief)
    items = []
    for key, value in variables.items():
        if value in (None, "", []):
            continue
        items.append(
            {
                "id": _evidence_id(task_id, key, value),
                "type": "business_fact",
                "key": key,
                "value": value,
                "source_type": "manual_input",
                "source_id": f"field_{key}",
                "source_version": "brief-v1",
                "verified_status": "user_confirmed",
                "allowed_usage": ["title", "body"],
            }
        )
    return {"items": items, "summary": {"manual": len(items), "knowledge": 0, "business_api": 0}}


def merge_evidence(base: dict[str, Any], additions: list[dict[str, Any]]) -> dict[str, Any]:
    items = list(base.get("items") or [])
    known = {item.get("id") for item in items}
    for item in additions:
        if item.get("id") not in known:
            items.append(item)
            known.add(item.get("id"))
    summary = dict(base.get("summary") or {})
    summary["knowledge"] = sum(1 for item in items if item.get("source_type") == "knowledge_base")
    summary["manual"] = sum(1 for item in items if item.get("source_type") == "manual_input")
    summary["business_api"] = sum(1 for item in items if item.get("source_type") in {"business_api", "mcp"})
    return {"items": items, "summary": summary}


def evidence_number_tokens(evidence_bundle: dict[str, Any]) -> list[str]:
    evidence_text = " ".join(
        json.dumps(item.get("value"), ensure_ascii=False)
        for item in evidence_bundle.get("items") or []
        if item.get("value") is not None
    )
    return sorted(set(NUMBER_PATTERN.findall(evidence_text)))


def unsupported_number_tokens(content: str, evidence_bundle: dict[str, Any]) -> list[str]:
    evidence_text = " ".join(
        json.dumps(item.get("value"), ensure_ascii=False)
        for item in evidence_bundle.get("items") or []
        if item.get("value") is not None
    )
    return sorted({number for number in NUMBER_PATTERN.findall(content) if number not in evidence_text})


def _problem_term_from_row(row: Any) -> str:
    if isinstance(row, str):
        return row.strip()
    if not isinstance(row, dict):
        return ""
    for key in ("problem_term", "problem", "term", "问题词"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _alternatives_from_row(row: Any) -> list[str]:
    if not isinstance(row, dict):
        return []
    raw = row.get("alternatives")
    if raw is None:
        raw = row.get("常用表达方式")
    if isinstance(raw, str):
        return [part.strip() for part in re.split(r"[,/，、|;；]", raw) if part.strip()]
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []


def forbidden_replacement_entries(evidence_bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """从平台封禁词替换表 Evidence 提取问题词与候选表达，不固化具体词表。"""
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in evidence_bundle.get("items") or []:
        metadata = item.get("metadata") or {}
        if metadata.get("rule_kind") != "forbidden_replacement_map":
            continue
        value = item.get("value")
        rows: list[Any]
        if isinstance(value, list):
            rows = value
        elif isinstance(value, dict):
            nested = value.get("rows") or value.get("items") or value.get("mappings")
            if isinstance(nested, list):
                rows = nested
            else:
                rows = [{"problem_term": key, "alternatives": alt} for key, alt in value.items()]
        else:
            continue
        for row in rows:
            term = _problem_term_from_row(row)
            if not term or term in seen:
                continue
            seen.add(term)
            entries.append(
                {
                    "term": term,
                    "alternatives": _alternatives_from_row(row),
                    "evidence_id": item.get("id"),
                }
            )
    entries.sort(key=lambda entry: len(entry["term"]), reverse=True)
    return entries


def validate_content(
    *,
    title: str,
    body: str,
    topics: list[str],
    brief: dict[str, Any],
    evidence_bundle: dict[str, Any],
    strategy: dict[str, Any],
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    combined = f"{title}\n{body}\n{' '.join(topics)}"
    for number in unsupported_number_tokens(combined, evidence_bundle):
        checks.append(
            {
                "code": "FACT_NUMBER_WITHOUT_SOURCE",
                "level": "error",
                "location": "content",
                "message": f"数字“{number}”没有出现在证据包中",
                "evidence_ids": [],
                "suggestion": "删除该数字，或补充可追溯的业务事实/知识来源",
            }
        )

    forbidden_terms = brief.get("forbidden_terms") or []
    for term in forbidden_terms:
        if term and term in combined:
            checks.append(
                {
                    "code": "CONTENT_FORBIDDEN_TERM",
                    "level": "error",
                    "location": "content",
                    "message": f"包含明确禁止的表达“{term}”",
                    "evidence_ids": [],
                    "suggestion": "删除或改写该表达",
                }
            )

    for entry in forbidden_replacement_entries(evidence_bundle):
        term = entry["term"]
        if term not in combined:
            continue
        alternatives = entry["alternatives"]
        if alternatives:
            suggestion = f"按封禁词库替换为表内候选之一：{' / '.join(alternatives[:5])}"
        else:
            suggestion = "在不改变事实的前提下重写整句，使该概念不再需要出现；不得编造表外替代词"
        checks.append(
            {
                "code": "CONTENT_FORBIDDEN_TERM",
                "level": "error",
                "location": "content",
                "message": f"成品仍含平台封禁词“{term}”",
                "evidence_ids": [evidence_id] if (evidence_id := entry.get("evidence_id")) else [],
                "suggestion": suggestion,
                "matched_terms": [term],
            }
        )

    for term in brief.get("required_terms") or []:
        if term and term not in combined:
            checks.append(
                {
                    "code": "CONTENT_REQUIRED_TERM_MISSING",
                    "level": "warning",
                    "location": "content",
                    "message": f"缺少要求包含的表达“{term}”",
                    "evidence_ids": [],
                    "suggestion": "在不影响自然表达的前提下补充",
                }
            )

    for claim in HIGH_RISK_CLAIMS:
        # “第一次刷到”等明确时间/步骤序数不属于排名宣传，避免无效回修。
        matched = (
            re.search(
                r"第一(?!次|天|周|月|年|步|阶段|版|期|轮|页|张|个|条|段|件|套|层|集|批|遍|回|季度|部分)",
                combined,
            )
            if claim == "第一"
            else claim in combined
        )
        if matched:
            checks.append(
                {
                    "code": "CONTENT_HIGH_RISK_CLAIM",
                    "level": "error",
                    "location": "content",
                    "message": f"检测到高风险绝对化表达“{claim}”",
                    "evidence_ids": [],
                    "suggestion": "改为有边界、可验证的客观表达",
                }
            )

    if (
        not strategy.get("methods")
        or not strategy.get("title_formula_code")
        or not (strategy.get("body_formula_code") or strategy.get("content_formula_code"))
    ):
        checks.append(
            {
                "code": "CONTENT_STRATEGY_SNAPSHOT_MISSING",
                "level": "error",
                "location": "strategy",
                "message": "内容缺少完整策略快照",
                "evidence_ids": [],
                "suggestion": "重新完成策略阶段后生成",
            }
        )

    status = "blocked" if any(item["level"] == "error" for item in checks) else "warning" if checks else "passed"
    return {"status": status, "checks": checks}


HARD_CTA_TERMS = ("立即咨询", "马上预约", "点击下方", "私信下单")
MARKDOWN_PATTERN = re.compile(r"(?m)^#{1,6}\s|^\s*[-*]\s|\*\*")
_TITLE_SELL_GROUPS = (
    ("number", re.compile(r"\d")),
    ("price", re.compile(r"报价|预算|万元|元")),
    ("craft", re.compile(r"工艺|工序|验收")),
    ("result", re.compile(r"效果|翻新|改造")),
)


def _check(code: str, location: str, message: str, evidence_ids: list[str] | None = None) -> dict[str, Any]:
    return {
        "code": code,
        "level": "error",
        "location": location,
        "message": message,
        "evidence_ids": evidence_ids or [],
    }


def validate_viral_v5_content(
    *,
    title: str,
    body: str,
    topics: list[str],
    brief: dict[str, Any],
    evidence_bundle: dict[str, Any],
    strategy: dict[str, Any],
    rule_bundle: dict[str, Any] | None = None,
    revision_lock: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from yuxi.content.v3.modular_rules import strip_keycap_numbers

    report = validate_content(
        title=title,
        body=body,
        topics=topics,
        brief=brief,
        evidence_bundle=evidence_bundle,
        strategy=strategy,
    )
    checks = [item for item in report.get("checks") or [] if item.get("code") != "FACT_NUMBER_WITHOUT_SOURCE"]
    sell_hits = [name for name, pattern in _TITLE_SELL_GROUPS if pattern.search(title or "")]
    if len(sell_hits) >= 2:
        checks.append(_check("TITLE_MULTI_SELLING_POINT", "title", "标题只能有一个主卖点，不要叠加价格、工艺和结果"))
    combined = f"{title}\n{body}\n{' '.join(topics)}"
    for term in HARD_CTA_TERMS:
        if term in combined:
            checks.append(_check("CTA_HARD_SELL", "body", f"禁止硬推销 CTA「{term}」"))
    if MARKDOWN_PATTERN.search(body or ""):
        checks.append(_check("BODY_MARKDOWN_FORBIDDEN", "body", "正文禁止 Markdown 标题、列表或加粗标记"))
    if any(len(paragraph) > 180 for paragraph in re.split(r"\n+", body or "") if paragraph.strip()):
        checks.append(_check("BODY_PARAGRAPH_TOO_LONG", "body", "正文存在超过 180 字的长段，请拆成可扫读短段"))
    normalized_topics = [str(item or "").strip().lstrip("#") for item in topics]
    if len(normalized_topics) != 10:
        checks.append(_check("TOPIC_COUNT_INVALID", "topics", "话题必须正好 10 个"))
    pool = {str(item).strip().lstrip("#") for item in (rule_bundle or {}).get("topic_candidate_pool") or []}
    if pool:
        unknown = [item for item in normalized_topics if item and item not in pool]
        if unknown:
            checks.append(_check("TOPIC_NOT_IN_POOL", "topics", f"话题不在候选池: {'、'.join(unknown[:5])}"))
    scanned = strip_keycap_numbers(combined)
    for number in unsupported_number_tokens(scanned, evidence_bundle):
        already = any(
            item.get("code") == "FACT_NUMBER_WITHOUT_SOURCE" and number in item.get("message", "") for item in checks
        )
        if already:
            continue
        checks.append(_check("FACT_NUMBER_WITHOUT_SOURCE", "content", f"数字“{number}”没有出现在证据包中"))
    lock = revision_lock or {}
    if lock.get("title") and title != lock["title"]:
        checks.append(_check("TITLE_LOCKED_TEXT_CHANGED", "title", "回修不得改动已锁定标题"))
    for paragraph in lock.get("locked_paragraphs") or []:
        if paragraph and paragraph not in (body or ""):
            checks.append(_check("BODY_LOCKED_TEXT_CHANGED", "body", "回修不得改动已锁定段落"))
    city = None
    job = None
    for item in evidence_bundle.get("items") or []:
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        if metadata.get("material_type") != "price":
            continue
        value = item.get("value") if isinstance(item.get("value"), dict) else {}
        city = city or metadata.get("city") or value.get("city")
        job = job or metadata.get("job") or metadata.get("trade") or value.get("job")
    if isinstance(city, str) and city and city not in combined:
        price_ids = [
            str(item.get("id") or "")
            for item in evidence_bundle.get("items") or []
            if (item.get("metadata") or {}).get("material_type") == "price"
        ]
        checks.append(_check("PRICE_CITY_MISMATCH", "body", "正文城市必须与报价证据同源", price_ids))
    if isinstance(job, str) and job and job not in combined:
        checks.append(_check("PRICE_TRADE_MISMATCH", "body", "正文工种必须与报价证据同源"))
    status = "blocked" if any(item["level"] == "error" for item in checks) else "warning" if checks else "passed"
    return {"status": status, "checks": checks}
