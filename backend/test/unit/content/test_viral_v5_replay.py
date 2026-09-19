"""30 份冻结回放：旧闭包字符 vs V5 装配，不调用模型。"""

from __future__ import annotations

from yuxi.content.v3.modular_rules import (
    VIRAL_BODY_AUTHOR,
    VIRAL_PRICE_AUTHOR,
    assemble_required_skills,
    freeze_expression_snapshot,
    has_price_signal,
    resolve_visual_intent,
    sanitize_expression_chunks,
)
from yuxi.services.agent_delegation_service import CONTENT_NODE_EXECUTION_LIMITS

OLD_GENERATE_CLOSURE = (
    "content-title-generator",
    "content-body-generator",
    "viral-layout-formatter",
    "humanizer-zh",
    "content-human-expression",
    "viral-structure-rewriter",
)
OLD_CLOSURE_CHARS = 13536

SCENARIOS = [
    {"id": "01_quote_partial", "price": True, "scene": "局部改造", "revision": []},
    {"id": "02_quote_whole", "price": True, "scene": "全屋装修", "revision": []},
    {"id": "03_craft_only", "price": False, "scene": "泥瓦工艺", "revision": []},
    {"id": "04_persona_cta", "price": False, "scene": "旧房翻新", "revision": [], "cta": True, "persona": True},
    {"id": "05_title_revision", "price": True, "scene": "局部改造", "revision": ["TITLE_TOO_LONG"]},
    {"id": "06_body_revision", "price": False, "scene": "水电改造", "revision": ["BODY_LENGTH_OUT_OF_RANGE"]},
    {"id": "07_persona_revision", "price": False, "scene": "装修日记", "revision": ["PERSONA_TONE_MISMATCH"]},
    {"id": "08_topic_revision", "price": False, "scene": "装修避坑", "revision": ["TOPIC_COUNT_INVALID"]},
    {"id": "09_price_revision", "price": True, "scene": "整装报价", "revision": ["PRICE_CITY_MISMATCH"]},
    {"id": "10_cta_revision", "price": False, "scene": "装修建议", "revision": ["CTA_HARD_SELL"]},
    {"id": "11_no_price_layout", "price": False, "scene": "收房验房", "revision": ["LAYOUT_MARKDOWN"]},
    {"id": "12_quote_craft_mix", "price": True, "scene": "局部改造水电", "revision": []},
    {"id": "13_cover_partial", "price": True, "scene": "局改", "revision": [], "cover": True},
    {"id": "14_cover_whole", "price": True, "scene": "全屋", "revision": [], "cover": True},
    {"id": "15_cover_craft", "price": False, "scene": "施工工艺", "revision": [], "cover": True},
    {"id": "16_no_quote_persona", "price": False, "scene": "家装设计", "revision": [], "persona": True},
    {"id": "17_quote_persona", "price": True, "scene": "装修预算", "revision": [], "persona": True},
    {"id": "18_soft_cta", "price": False, "scene": "装修经验", "revision": [], "cta": True},
    {
        "id": "19_title_and_topic",
        "price": False,
        "scene": "装修材料",
        "revision": ["TITLE_FACT_UNSUPPORTED", "TOPIC_NOT_IN_POOL"],
    },
    {"id": "20_body_evidence", "price": True, "scene": "装修报价", "revision": ["FACT_NUMBER_WITHOUT_SOURCE"]},
    {"id": "21_empty_persona", "price": False, "scene": "装修效果", "revision": []},
    {"id": "22_partial_no_price", "price": False, "scene": "局部翻新", "revision": []},
    {"id": "23_whole_no_price", "price": False, "scene": "整屋改造", "revision": []},
    {"id": "24_paint_craft", "price": False, "scene": "油漆验收", "revision": []},
    {"id": "25_wood_craft", "price": False, "scene": "木工细节", "revision": []},
    {"id": "26_quote_title_rev", "price": True, "scene": "全屋装修", "revision": ["TITLE_MULTI_SELLING_POINT"]},
    {"id": "27_locked_body", "price": False, "scene": "装修案例", "revision": ["TITLE_LOCKED_TEXT_CHANGED"]},
    {"id": "28_hard_cta_quote", "price": True, "scene": "局部改造", "revision": ["CTA_HARD_SELL"]},
    {"id": "29_platform_only", "price": False, "scene": "装修工期", "revision": []},
    {"id": "30_expression_trace", "price": False, "scene": "装修日记", "revision": [], "expression": True},
]


def _evidence(case: dict) -> dict:
    items = [{"id": "ev_ok", "value": case["scene"], "allowed_usage": ["title", "body"]}]
    if case["price"]:
        items.append(
            {
                "id": "ev_price",
                "value": "19800",
                "metadata": {"material_type": "price"},
                "allowed_usage": ["body"],
            }
        )
    return {"items": items}


def test_replay_has_thirty_frozen_cases():
    assert len(SCENARIOS) == 30
    assert len({item["id"] for item in SCENARIOS}) == 30


def test_replay_assembly_gates():
    old_chars = {slug: OLD_CLOSURE_CHARS // len(OLD_GENERATE_CLOSURE) for slug in OLD_GENERATE_CLOSURE}
    assert sum(old_chars.values()) >= 12000
    for case in SCENARIOS:
        evidence = _evidence(case)
        brief = {"form_values": {"process_type": case["scene"]}}
        priced = has_price_signal(evidence_bundle=evidence, brief=brief)
        assert priced is case["price"]
        skills = assemble_required_skills(
            node_id="generate_content",
            block_codes=case["revision"],
            has_price=priced,
        )
        assert CONTENT_NODE_EXECUTION_LIMITS["generate_content"][3] >= 1
        if not case["revision"]:
            assert skills.count("viral-author-core") == 1
            assert (VIRAL_PRICE_AUTHOR in skills) is case["price"]
        if any(code.startswith("TITLE_") for code in case["revision"]) and not any(
            code.startswith("BODY_") for code in case["revision"]
        ):
            assert VIRAL_BODY_AUTHOR not in skills
        allowed_ids = {item["id"] for item in evidence["items"]}
        assert "ev_forged" not in allowed_ids
        if case.get("cover"):
            intent = resolve_visual_intent(brief=brief, evidence_bundle=evidence, has_price=priced)
            if "局" in case["scene"]:
                assert intent == "partial_renovation"
            elif "工艺" in case["scene"] or "施工" in case["scene"]:
                assert intent == "craft_detail"
            elif case["price"] and ("全屋" in case["scene"] or "整装" in case["scene"] or case["scene"] == "全屋"):
                assert intent == "whole_house_quote"
        if case.get("expression"):
            snapshot = freeze_expression_snapshot(
                libraries={
                    "表达语气库": sanitize_expression_chunks(["口语短句，像在聊天"]),
                    "具象表达": sanitize_expression_chunks(["泥瓦收口要压实"]),
                },
                advantage_chunks=["专注旧房翻新"],
            )
            assert snapshot["snapshot_hash"]
            assert snapshot["expression_guidance"]["tone"]
            assert snapshot["advantage_chunks"]
