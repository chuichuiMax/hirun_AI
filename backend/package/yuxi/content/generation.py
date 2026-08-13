from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from yuxi.agents import load_chat_model, resolve_chat_model_spec
from yuxi.content.schemas import GeneratedContent, ReviewReport, TitleCandidate

SKILLS_ROOT = Path(__file__).resolve().parents[1] / "agents" / "skills" / "buildin"
SKILL_VERSIONS = {
    "content-strategy-planner": "1.0.0",
    "content-title-generator": "1.0.0",
    "content-body-generator": "1.0.0",
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
) -> list[dict[str, Any]]:
    formula = next(
        item for item in rule_bundle["title_formulas"] if item["code"] == strategy["title_formula_code"]
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
            f"EvidenceBundle={json.dumps(evidence_bundle, ensure_ascii=False)}"
        ),
    )
    if isinstance(payload, dict):
        payload = payload.get("titles") or payload.get("items")
    if not isinstance(payload, list) or not 3 <= len(payload) <= 5:
        raise ValueError("标题生成必须返回 3～5 个候选")
    candidates = []
    for index, item in enumerate(payload, start=1):
        item = dict(item or {})
        item["id"] = str(item.get("id") or f"title_{index}")
        item["formula_code"] = strategy["title_formula_code"]
        candidates.append(TitleCandidate.model_validate(item).model_dump())
    return candidates


async def generate_body(
    *,
    model_spec: str | None,
    brief: dict[str, Any],
    strategy: dict[str, Any],
    evidence_bundle: dict[str, Any],
    selected_title: dict[str, Any],
    rule_bundle: dict[str, Any],
) -> dict[str, Any]:
    formula = next(
        item for item in rule_bundle["content_formulas"] if item["code"] == strategy["content_formula_code"]
    )
    payload = await _invoke_json(
        model_spec,
        skill_slug="content-body-generator",
        prompt=(
            "基于已锁定标题生成一篇平台无关、可直接编辑的中文正文和 3～8 个话题。"
            "不得添加证据包之外的价格、参数、数据或客户效果。只输出 JSON 对象：body、topics、evidence_ids。\n"
            f"SelectedTitle={json.dumps(selected_title, ensure_ascii=False)}\n"
            f"ContentBrief={json.dumps(brief, ensure_ascii=False)}\n"
            f"StrategyPlan={json.dumps(strategy, ensure_ascii=False)}\n"
            f"ContentFormula={json.dumps(formula, ensure_ascii=False)}\n"
            f"EvidenceBundle={json.dumps(evidence_bundle, ensure_ascii=False)}"
        ),
    )
    return GeneratedContent.model_validate(payload).model_dump()


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
    return ReviewReport.model_validate(payload).model_dump()
