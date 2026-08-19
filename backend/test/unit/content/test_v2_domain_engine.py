from yuxi.content.v2 import (
    CombinationEngineV2,
    ComplianceEngine,
    ContentValueAnalyzer,
    FormulaSlotResolver,
    LexiconResolver,
    NarrativeConsistencyChecker,
    validate_numeric_evidence_coverage,
)


def _title_pattern():
    return {
        "code": "T01-P01",
        "formula_kind": "title",
        "formula_code": "T01",
        "template_text": "{audience}：{number}完成{result}",
        "enabled": True,
        "slots": [
            {
                "slot_key": "audience",
                "source_type": "brief",
                "source_path": "audience",
                "required": True,
                "fallback_policy": "block",
                "sort_order": 1,
            },
            {
                "slot_key": "number",
                "source_type": "evidence",
                "required": True,
                "evidence_required": True,
                "fallback_policy": "block",
                "sort_order": 2,
            },
            {
                "slot_key": "result",
                "source_type": "evidence",
                "required": True,
                "evidence_required": True,
                "fallback_policy": "block",
                "sort_order": 3,
            },
        ],
    }


def _body_pattern():
    return {
        "code": "C02-P01",
        "formula_kind": "body",
        "formula_code": "C02",
        "template_text": "案例过程与结果",
        "enabled": True,
        "slots": [
            {
                "slot_key": "result",
                "source_type": "evidence",
                "required": True,
                "evidence_required": True,
                "fallback_policy": "block",
            }
        ],
    }


def _brief():
    return {
        "task_id": "ct_1",
        "content_goal": "acquire",
        "audience": ["杭州小户型业主"],
        "business_variables": {"result": "多出12㎡收纳空间", "number": "12㎡"},
    }


def _evidence():
    return {
        "items": [
            {
                "id": "ev_result",
                "verified_status": "confirmed",
                "variable_codes": ["number", "result"],
                "values": {"number": "12㎡", "result": "多出12㎡收纳空间"},
                "content": "现场测量确认多出12㎡收纳空间",
                "allowed_usage": ["title", "body"],
            }
        ]
    }


def test_slot_resolver_blocks_factual_slot_without_evidence():
    result = FormulaSlotResolver().resolve(
        _title_pattern(), brief=_brief(), evidence_bundle={"items": []}, content_goal="acquire"
    )
    assert result["compatibility"] == "blocked"
    assert set(result["missing_slots"]) == {"number", "result"}


def test_slot_resolver_preserves_value_and_evidence_mapping():
    result = FormulaSlotResolver().resolve(
        _title_pattern(), brief=_brief(), evidence_bundle=_evidence(), content_goal="acquire"
    )
    assert result["compatibility"] == "compatible"
    assert result["rendered_preview"] == "杭州小户型业主：12㎡完成多出12㎡收纳空间"
    assert result["slots"][1]["evidence_ids"] == ["ev_result"]


def test_combination_engine_uses_all_hard_dimensions_and_is_deterministic():
    bundle = {
        "formula_patterns": [_title_pattern(), _body_pattern()],
        "combination_rules": [
            {
                "id": "good",
                "content_goal": "acquire",
                "content_type_codes": ["CT01"],
                "industry_scope": ["decoration"],
                "channel_scope": ["xiaohongshu"],
                "narrative_axis_codes": ["before_after_result"],
                "methods": ["M01", "M04"],
                "title_formula_codes": ["T01"],
                "title_pattern_codes": ["T01-P01"],
                "content_formula_code": "C02",
                "body_pattern_codes": ["C02-P01"],
                "priority": 100,
                "recommendation_reason": "真实结果案例",
            },
            {
                "id": "wrong-channel",
                "content_goal": "acquire",
                "content_type_codes": ["CT01"],
                "channel_scope": ["wechat"],
                "methods": ["M01"],
                "title_formula_codes": ["T01"],
                "content_formula_code": "C02",
            },
        ],
    }
    kwargs = dict(
        brief=_brief(),
        evidence_bundle=_evidence(),
        content_goal="acquire",
        content_type_code="CT01",
        industry_slug="decoration",
        channel_code="xiaohongshu",
        primary_narrative_axis="before_after_result",
    )
    first = CombinationEngineV2().recommend(bundle, **kwargs)
    second = CombinationEngineV2().recommend(bundle, **kwargs)
    assert first == second
    assert first["compatibility"] == "auto_matched"
    assert first["selected"]["rule_id"] == "good"
    assert first["rejected"] == [{"rule_id": "wrong-channel", "reasons": ["渠道范围不匹配"]}]


def test_lexicon_resolver_explains_enterprise_override():
    result = LexiconResolver().resolve(
        [
            {
                "id": "lv_platform",
                "code": "emotion",
                "scope_type": "platform",
                "entries": [{"id": "p1", "text": "真不错", "normalized_text": "真不错"}],
            },
            {
                "id": "lv_enterprise",
                "code": "brand-tone",
                "scope_type": "enterprise",
                "entries": [{"id": "e1", "text": "真不错", "normalized_text": "真不错"}],
            },
        ]
    )
    assert result["entries"][0]["id"] == "e1"
    assert result["overrides"] == [{"normalized_text": "真不错", "replaced": "p1", "selected": "e1"}]


def test_content_value_analyzer_only_references_available_evidence():
    angles = ContentValueAnalyzer().analyze(
        brief=_brief(),
        evidence_bundle=_evidence(),
        preferred_content_type="CT01",
        content_types=[
            {
                "code": "CT01",
                "name": "案例/成果展示",
                "description": "用真实过程证明能力",
                "supported_goals": ["acquire"],
                "required_variable_codes": ["result"],
                "enabled": True,
            }
        ],
    )
    assert len(angles) == 1
    assert angles[0]["evidence_ids"] == ["ev_result"]
    assert angles[0]["primary_narrative_axis"] == "before_after_result"


def test_compliance_engine_applies_safe_replacement_but_blocks_length():
    result = ComplianceEngine().validate_and_adapt(
        title="绝对有效的方案",
        body="这是一段说明",
        topics=["方案"],
        channel_profile={
            "title_constraints": {"max_length": 6},
            "body_constraints": {"max_length": 100},
            "topic_constraints": {"max_count": 5},
        },
        policies=[
            {
                "rules": [
                    {
                        "id": "r1",
                        "rule_code": "ABSOLUTE",
                        "pattern": "绝对有效",
                        "match_type": "literal",
                        "action": "replace",
                        "replacement": "更稳妥",
                    }
                ]
            }
        ],
    )
    assert result["title"] == "更稳妥的方案"
    assert result["status"] == "blocked"
    assert result["replacement_diffs"][0]["rule_id"] == "r1"


def test_numeric_claims_are_one_hundred_percent_covered_or_blocked():
    passed = validate_numeric_evidence_coverage("现场确认多出12㎡收纳", _evidence())
    blocked = validate_numeric_evidence_coverage("现场确认多出20㎡收纳", _evidence())
    assert passed["status"] == "passed"
    assert blocked["status"] == "blocked"
    assert blocked["unsupported_claims"] == ["20㎡"]


def test_narrative_checker_rejects_competing_primary_axis():
    result = NarrativeConsistencyChecker().check(
        "before_after_result", ["before_after_result", "price_composition"]
    )
    assert result["status"] == "blocked"
    assert result["checks"][0]["code"] == "NARRATIVE_AXIS_CONFLICT"
