from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from yuxi.agents import load_chat_model, resolve_chat_model_spec
from yuxi.content.schemas import GeneratedContent, ReviewReport, TitleCandidate
from yuxi.content.validators import evidence_number_tokens, unsupported_number_tokens

SKILLS_ROOT = Path(__file__).resolve().parents[1] / "agents" / "skills" / "buildin"
SKILL_VERSIONS = {
    "content-value-analyzer": "1.0.0",
    "content-strategy-planner": "1.0.0",
    "content-title-generator": "1.0.0",
    "content-outline-builder": "1.0.0",
    "content-body-generator": "1.0.1",
    "persona-style-polisher": "1.0.0",
    "content-reviewer": "1.0.0",
}


def load_skill_instruction(slug: str) -> str:
    path = SKILLS_ROOT / slug / "SKILL.md"
    return path.read_text(encoding="utf-8")


def _response_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()
    content = getattr(response, "content", None)
    if isinstance(content, str):
        return content.strip()
    raise ValueError("模型没有返回可解析的文本")


def _parse_json(text: str) -> Any:
    normalized = text.strip()
    if normalized.startswith("```"):
        lines = normalized.splitlines()
        normalized = "\n".join(lines[1:-1]).strip()
    try:
        return json.loads(normalized)
    except json.JSONDecodeError:
        object_start = normalized.find("{")
        array_start = normalized.find("[")
        starts = [value for value in (object_start, array_start) if value >= 0]
        if not starts:
            raise ValueError("模型输出不包含 JSON")
        start = min(starts)
        closing = "}" if normalized[start] == "{" else "]"
        end = normalized.rfind(closing)
        if end < start:
            raise ValueError("模型输出 JSON 不完整")
        return json.loads(normalized[start : end + 1])


async def _invoke_json(model_spec: str | None, *, skill_slug: str, prompt: str) -> Any:
    resolved_model = resolve_chat_model_spec(model_spec)
    model = load_chat_model(fully_specified_name=resolved_model, temperature=0.5)
    response = await model.ainvoke(
        [
            SystemMessage(content=load_skill_instruction(skill_slug)),
            HumanMessage(content=prompt),
        ]
    )
    return _parse_json(_response_text(response))


async def generate_title_candidates(
    *,
    model_spec: str | None,
    brief: dict[str, Any],
    strategy: dict[str, Any],
    evidence_bundle: dict[str, Any],
    rule_bundle: dict[str, Any],
    channel_profile: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    formula = next(item for item in rule_bundle["title_formulas"] if item["code"] == strategy["title_formula_code"])
    pattern = next(
        (
            item
            for item in rule_bundle.get("formula_patterns") or []
            if item.get("code") == strategy.get("title_pattern_code")
        ),
        None,
    )
    payload = await _invoke_json(
        model_spec,
        skill_slug="content-title-generator",
        prompt=(
            "严格使用同一份 ContentBrief、EvidenceBundle 和选定公式生成 4 个标题候选。"
            "只输出 JSON 数组；每项字段必须是 id、text、formula_code、variable_mapping、evidence_ids、risk_flags。\n"
            f"ContentBrief={json.dumps(brief, ensure_ascii=False)}\n"
            f"StrategyPlan={json.dumps(strategy, ensure_ascii=False)}\n"
            f"TitleFormula={json.dumps(formula, ensure_ascii=False)}\n"
            f"TitlePattern={json.dumps(pattern, ensure_ascii=False)}\n"
            f"ResolvedSlotPlan={json.dumps(strategy.get('slot_plan', {}).get('title') or strategy.get('title_slot_plan') or {}, ensure_ascii=False)}\n"
            f"ChannelConstraints={json.dumps((channel_profile or {}).get('title_constraints') or {}, ensure_ascii=False)}\n"
            f"EvidenceBundle={json.dumps(evidence_bundle, ensure_ascii=False)}"
        ),
    )

    def normalize(value: Any) -> list[dict[str, Any]]:
        if isinstance(value, dict):
            value = value.get("titles") or value.get("items")
        if not isinstance(value, list) or not 3 <= len(value) <= 5:
            raise ValueError("标题生成必须返回 3～5 个候选")
        result = []
        for index, raw in enumerate(value, start=1):
            item = dict(raw or {})
            item["id"] = str(item.get("id") or f"title_{index}")
            item["formula_code"] = strategy["title_formula_code"]
            item["pattern_code"] = strategy.get("title_pattern_code")
            result.append(TitleCandidate.model_validate(item).model_dump())
        return result

    def constraint_errors(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        constraints = (channel_profile or {}).get("title_constraints") or {}
        minimum = constraints.get("min_length")
        maximum = constraints.get("max_length")
        errors = []
        for item in items:
            reasons = []
            text = item["text"]
            if minimum is not None and len(text) < int(minimum):
                reasons.append(f"少于 {minimum} 字")
            if maximum is not None and len(text) > int(maximum):
                reasons.append(f"超过 {maximum} 字")
            unsupported = unsupported_number_tokens(text, evidence_bundle)
            if unsupported:
                reasons.append(f"包含无证据数字：{', '.join(unsupported)}")
            if reasons:
                errors.append({"id": item["id"], "reasons": reasons})
        return errors

    candidates = normalize(payload)
    errors = constraint_errors(candidates)
    if len(candidates) - len(errors) < 3:
        repaired = await _invoke_json(
            model_spec,
            skill_slug="content-title-generator",
            prompt=(
                "上一组标题不足 3 个通过事实和渠道硬约束，请重新生成 4 个标题。"
                "必须保留已锁定 Pattern 的语义顺序，可以压缩人群和结果措辞，但不能改变事实；"
                "不得添加数字，且必须满足渠道标题长度。只输出 JSON 数组。\n"
                f"ConstraintErrors={json.dumps(errors, ensure_ascii=False)}\n"
                f"ChannelConstraints={json.dumps((channel_profile or {}).get('title_constraints') or {}, ensure_ascii=False)}\n"
                f"OriginalCandidates={json.dumps(candidates, ensure_ascii=False)}\n"
                f"ResolvedSlotPlan={json.dumps(strategy.get('slot_plan', {}).get('title') or strategy.get('title_slot_plan') or {}, ensure_ascii=False)}\n"
                f"EvidenceBundle={json.dumps(evidence_bundle, ensure_ascii=False)}"
            ),
        )
        candidates = normalize(repaired)
    return candidates


async def generate_body(
    *,
    model_spec: str | None,
    brief: dict[str, Any],
    strategy: dict[str, Any],
    evidence_bundle: dict[str, Any],
    selected_title: dict[str, Any],
    rule_bundle: dict[str, Any],
    channel_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body_formula_code = strategy.get("body_formula_code") or strategy.get("content_formula_code")
    formula = next(item for item in rule_bundle["content_formulas"] if item["code"] == body_formula_code)
    pattern = next(
        (
            item
            for item in rule_bundle.get("formula_patterns") or []
            if item.get("code") == strategy.get("body_pattern_code")
        ),
        None,
    )
    allowed_numbers = evidence_number_tokens(evidence_bundle)
    payload = await _invoke_json(
        model_spec,
        skill_slug="content-body-generator",
        prompt=(
            "基于已锁定标题生成一篇平台无关、可直接编辑的中文正文和 3～8 个话题。"
            "不得添加证据包之外的价格、参数、数据或客户效果。"
            "正文和话题中的每个阿拉伯数字都必须逐字来自数字白名单；"
            "不得编造对比例子、统计数字或效果数字，也不得用阿拉伯数字或数字 emoji 作为段落编号，请改用项目符号。"
            "输出前逐项自检全部数字。只输出 JSON 对象：body、topics、evidence_ids。\n"
            f"数字白名单={json.dumps(allowed_numbers, ensure_ascii=False)}\n"
            f"SelectedTitle={json.dumps(selected_title, ensure_ascii=False)}\n"
            f"ContentBrief={json.dumps(brief, ensure_ascii=False)}\n"
            f"StrategyPlan={json.dumps(strategy, ensure_ascii=False)}\n"
            f"ContentFormula={json.dumps(formula, ensure_ascii=False)}\n"
            f"BodyPattern={json.dumps(pattern, ensure_ascii=False)}\n"
            f"ContentOutline={json.dumps(strategy.get('content_outline') or {}, ensure_ascii=False)}\n"
            f"EvidenceUsagePlan={json.dumps(strategy.get('evidence_usage_plan') or {}, ensure_ascii=False)}\n"
            f"ChannelConstraints={json.dumps({'body': (channel_profile or {}).get('body_constraints') or {}, 'topics': (channel_profile or {}).get('topic_constraints') or {}}, ensure_ascii=False)}\n"
            f"EvidenceBundle={json.dumps(evidence_bundle, ensure_ascii=False)}"
        ),
    )
    draft = GeneratedContent.model_validate(payload).model_dump()
    unsupported_numbers = unsupported_number_tokens(
        f"{draft['body']}\n{' '.join(draft.get('topics') or [])}", evidence_bundle
    )
    if unsupported_numbers:
        repaired = await _invoke_json(
            model_spec,
            skill_slug="content-body-generator",
            prompt=(
                "上一版正文包含证据包之外的数字，必须重写后才能进入审核。"
                "删除或改写所有未获证据支持的数字，不得替换成新的数字；"
                "保留已锁定标题、正文公式、事实含义和话题意图。"
                "不得用阿拉伯数字或数字 emoji 作为段落编号。"
                "只输出 JSON 对象：body、topics、evidence_ids。\n"
                f"不支持的数字={json.dumps(unsupported_numbers, ensure_ascii=False)}\n"
                f"数字白名单={json.dumps(allowed_numbers, ensure_ascii=False)}\n"
                f"OriginalDraft={json.dumps(draft, ensure_ascii=False)}\n"
                f"SelectedTitle={json.dumps(selected_title, ensure_ascii=False)}\n"
                f"ContentBrief={json.dumps(brief, ensure_ascii=False)}\n"
                f"StrategyPlan={json.dumps(strategy, ensure_ascii=False)}\n"
                f"ContentFormula={json.dumps(formula, ensure_ascii=False)}\n"
                f"BodyPattern={json.dumps(pattern, ensure_ascii=False)}\n"
                f"ContentOutline={json.dumps(strategy.get('content_outline') or {}, ensure_ascii=False)}\n"
                f"EvidenceBundle={json.dumps(evidence_bundle, ensure_ascii=False)}"
            ),
        )
        draft = GeneratedContent.model_validate(repaired).model_dump()
    return draft


async def polish_persona_style(
    *,
    model_spec: str | None,
    draft: dict[str, Any],
    brief: dict[str, Any],
    strategy: dict[str, Any],
    evidence_bundle: dict[str, Any],
    persona: dict[str, Any],
) -> dict[str, Any]:
    """仅调整表达风格；事实、数字、证据引用和服务边界必须保持不变。"""

    allowed_numbers = evidence_number_tokens(evidence_bundle)
    evidence_ids = {
        str(item["id"])
        for item in evidence_bundle.get("items") or []
        if isinstance(item, dict) and item.get("id")
    }
    prompt = (
        "在不增加、删除或改变任何事实的前提下，按 Persona 调整正文语气。"
        "不得新增价格、参数、数字、效果、承诺、人物经历或服务范围；不得改变话题含义；"
        "evidence_ids 只能引用 EvidenceBundle 中已有 ID。只输出 JSON 对象：body、topics、evidence_ids、paragraph_evidence。\n"
        f"数字白名单={json.dumps(allowed_numbers, ensure_ascii=False)}\n"
        f"PersonaProfile={json.dumps(persona, ensure_ascii=False)}\n"
        f"OriginalDraft={json.dumps(draft, ensure_ascii=False)}\n"
        f"ContentBrief={json.dumps(brief, ensure_ascii=False)}\n"
        f"StrategyPlan={json.dumps(strategy, ensure_ascii=False)}\n"
        f"EvidenceBundle={json.dumps(evidence_bundle, ensure_ascii=False)}"
    )
    polished = GeneratedContent.model_validate(
        await _invoke_json(model_spec, skill_slug="persona-style-polisher", prompt=prompt)
    ).model_dump()
    unsupported = unsupported_number_tokens(
        f"{polished['body']}\n{' '.join(polished.get('topics') or [])}", evidence_bundle
    )
    invalid_evidence_ids = sorted(set(polished.get("evidence_ids") or []) - evidence_ids)
    if unsupported or invalid_evidence_ids:
        repaired = await _invoke_json(
            model_spec,
            skill_slug="persona-style-polisher",
            prompt=(
                "上一版 Persona 润色改变了事实边界，必须基于原稿重新润色。"
                "删除所有不在数字白名单中的数字，并删除不存在的 Evidence ID；不得增加任何新事实。"
                "只输出 JSON 对象：body、topics、evidence_ids、paragraph_evidence。\n"
                f"不支持的数字={json.dumps(unsupported, ensure_ascii=False)}\n"
                f"无效 Evidence ID={json.dumps(invalid_evidence_ids, ensure_ascii=False)}\n"
                f"数字白名单={json.dumps(allowed_numbers, ensure_ascii=False)}\n"
                f"允许的 Evidence ID={json.dumps(sorted(evidence_ids), ensure_ascii=False)}\n"
                f"OriginalDraft={json.dumps(draft, ensure_ascii=False)}\n"
                f"PersonaProfile={json.dumps(persona, ensure_ascii=False)}\n"
                f"EvidenceBundle={json.dumps(evidence_bundle, ensure_ascii=False)}"
            ),
        )
        polished = GeneratedContent.model_validate(repaired).model_dump()
    remaining_numbers = unsupported_number_tokens(
        f"{polished['body']}\n{' '.join(polished.get('topics') or [])}", evidence_bundle
    )
    remaining_ids = sorted(set(polished.get("evidence_ids") or []) - evidence_ids)
    if remaining_numbers or remaining_ids:
        raise ValueError("Persona 润色未通过事实保持校验")
    return polished


async def review_generated_content(
    *,
    model_spec: str | None,
    title: str,
    body: str,
    topics: list[str],
    brief: dict[str, Any],
    strategy: dict[str, Any],
    evidence_bundle: dict[str, Any],
) -> dict[str, Any]:
    payload = await _invoke_json(
        model_spec,
        skill_slug="content-reviewer",
        prompt=(
            "审核创作手法贯穿、标题公式、正文结构、事实来源、人设与语气。"
            "只输出 JSON 对象 status、checks；status 只能是 passed、warning、blocked。"
            "checks 每项包含 code、level、location、message、evidence_ids、suggestion。\n"
            f"Content={json.dumps({'title': title, 'body': body, 'topics': topics}, ensure_ascii=False)}\n"
            f"ContentBrief={json.dumps(brief, ensure_ascii=False)}\n"
            f"StrategyPlan={json.dumps(strategy, ensure_ascii=False)}\n"
            f"EvidenceBundle={json.dumps(evidence_bundle, ensure_ascii=False)}"
        ),
    )
    if not isinstance(payload, dict):
        raise ValueError("内容审核必须返回 JSON 对象")
    normalized = dict(payload)
    status_aliases = {
        "pass": "passed",
        "ok": "passed",
        "success": "passed",
        "warn": "warning",
        "failed": "blocked",
        "fail": "blocked",
        "error": "blocked",
    }
    normalized["status"] = status_aliases.get(str(normalized.get("status") or "").lower(), normalized.get("status"))
    level_aliases = {
        "pass": "info",
        "passed": "info",
        "ok": "info",
        "success": "info",
        "warn": "warning",
        "failed": "error",
        "fail": "error",
        "blocked": "error",
    }
    checks = []
    for raw in normalized.get("checks") or []:
        item = dict(raw or {})
        item["level"] = level_aliases.get(str(item.get("level") or "").lower(), item.get("level"))
        item.setdefault("location", "content")
        item.setdefault("evidence_ids", [])
        checks.append(item)
    normalized["checks"] = checks
    return ReviewReport.model_validate(normalized).model_dump()
