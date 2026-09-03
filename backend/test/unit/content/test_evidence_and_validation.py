from yuxi.content.validators import merge_evidence, normalize_manual_evidence, validate_content


def test_normalize_evidence_is_stable_and_source_backed():
    brief = {
        "brand": {"name": "山野咖啡"},
        "audience": ["附近上班族"],
        "business_variables": {"product": "手冲咖啡", "result": "每天限量30杯"},
        "form_values": {},
    }

    first = normalize_manual_evidence("ct_1", brief)
    second = normalize_manual_evidence("ct_1", brief)

    assert first == second
    assert first["items"]
    assert all(item["source_type"] == "manual_input" for item in first["items"])
    assert all(item["allowed_usage"] == ["title", "body"] for item in first["items"])


def test_merge_evidence_deduplicates_and_preserves_source_counts():
    base = {"items": [{"id": "ev_1", "source_type": "manual_input"}], "summary": {}}
    result = merge_evidence(
        base,
        [
            {"id": "ev_1", "source_type": "manual_input"},
            {"id": "ev_2", "source_type": "knowledge_base"},
        ],
    )

    assert [item["id"] for item in result["items"]] == ["ev_1", "ev_2"]
    assert result["summary"] == {"manual": 1, "knowledge": 1, "business_api": 0}


def test_deterministic_review_blocks_unsupported_numbers_and_claims():
    report = validate_content(
        title="7天保证见效",
        body="第一套方案",
        topics=[],
        brief={"required_terms": [], "forbidden_terms": []},
        evidence_bundle={"items": []},
        strategy={"methods": ["M01"], "title_formula_code": "T01", "content_formula_code": "C01"},
    )

    codes = {item["code"] for item in report["checks"]}
    assert report["status"] == "blocked"
    assert "FACT_NUMBER_WITHOUT_SOURCE" in codes
    assert "CONTENT_HIGH_RISK_CLAIM" in codes


def test_deterministic_review_accepts_numbers_in_shared_evidence_bundle():
    report = validate_content(
        title="12周学习计划",
        body="每周2次练习",
        topics=["英语启蒙"],
        brief={"required_terms": ["英语启蒙"], "forbidden_terms": []},
        evidence_bundle={"items": [{"id": "ev_1", "value": "12周，每周2次"}]},
        strategy={"methods": ["M01"], "title_formula_code": "T01", "content_formula_code": "C01"},
    )

    assert report == {"status": "passed", "checks": []}


def test_compliance_engine_uses_shared_code_for_named_block_rules():
    from yuxi.content.validation import ComplianceEngine

    result = ComplianceEngine().validate_and_adapt(
        title="全屋百分百保证",
        body="联系方式见官网",
        topics=[],
        channel_profile={},
        policies=[
            {
                "rules": [
                    {
                        "id": "replacement-absolute_guarantee",
                        "rule_code": "ABSOLUTE_GUARANTEE",
                        "pattern": "百分百保证",
                        "match_type": "literal",
                        "action": "block",
                        "enabled": True,
                        "explanation": "禁止无证据的绝对承诺",
                    }
                ]
            }
        ],
    )

    assert result["status"] == "blocked"
    assert result["checks"][0]["code"] == "COMPLIANCE_RULE_MATCH"
    assert result["checks"][0]["rule_code"] == "ABSOLUTE_GUARANTEE"


def test_compliance_confirm_rule_does_not_block_generation():
    from yuxi.content.validation import ComplianceEngine

    result = ComplianceEngine().validate_and_adapt(
        title="全屋零增项落地",
        body="合同范围内零增项",
        topics=[],
        channel_profile={"title_constraints": {"min_length": 6, "max_length": 20}},
        policies=[
            {
                "rules": [
                    {
                        "id": "replacement-zero_addition",
                        "rule_code": "ZERO_ADDITION",
                        "pattern": "零增项",
                        "match_type": "literal",
                        "action": "confirm",
                        "enabled": True,
                        "human_confirmation_required": True,
                        "explanation": "零增项必须明确合同范围并人工确认",
                    }
                ]
            }
        ],
    )

    assert result["status"] == "warning"
    assert result["checks"][0]["code"] == "COMPLIANCE_RULE_MATCH"
    assert result["checks"][0]["level"] == "warning"
    assert result["checks"][0]["human_confirmation_required"] is True
