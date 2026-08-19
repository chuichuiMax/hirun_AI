from __future__ import annotations

import pytest

from yuxi.content import generation
from yuxi.content.rules import BODY_FORMULAS, TITLE_FORMULAS


@pytest.mark.asyncio
async def test_generate_body_repairs_numbers_outside_evidence(monkeypatch):
    prompts: list[str] = []
    responses = [
        {
            "body": "预算从15万涨到20万，分3步解决。",
            "topics": ["装修预算"],
            "evidence_ids": ["ev_result"],
        },
        {
            "body": "测试案例采用26.8万元分项预算，报价和工期均以证据为准。",
            "topics": ["装修预算"],
            "evidence_ids": ["ev_result"],
        },
    ]

    async def fake_invoke_json(model_spec, *, skill_slug, prompt):
        prompts.append(prompt)
        return responses[len(prompts) - 1]

    monkeypatch.setattr(generation, "_invoke_json", fake_invoke_json)

    result = await generation.generate_body(
        model_spec=None,
        brief={"required_terms": [], "forbidden_terms": []},
        strategy={"content_formula_code": "C01"},
        evidence_bundle={"items": [{"id": "ev_result", "value": "测试预算26.8万元"}]},
        selected_title={"id": "title_1", "text": "杭州装修预算案例"},
        rule_bundle={"content_formulas": [BODY_FORMULAS[0]]},
    )

    assert len(prompts) == 2
    assert "数字白名单" in prompts[0]
    assert "15万" in prompts[1]
    assert "20万" in prompts[1]
    assert "3" in prompts[1]
    assert result["body"] == responses[1]["body"]
    assert result["topics"] == responses[1]["topics"]
    assert result["evidence_ids"] == responses[1]["evidence_ids"]
    assert result["paragraph_evidence"] == []


@pytest.mark.asyncio
async def test_generate_titles_repairs_candidates_that_exceed_channel_limit(monkeypatch):
    calls = []
    long_titles = [
        {
            "id": f"long_{index}",
            "text": f"杭州小户型刚需家庭：12㎡完成现场复尺确认增加12㎡收纳空间{index}",
            "formula_code": "T01",
            "variable_mapping": {},
            "evidence_ids": ["ev_result"],
            "risk_flags": [],
        }
        for index in range(4)
    ]
    short_titles = [
        {
            "id": f"short_{index}",
            "text": f"杭州刚需：12㎡收纳实测{index}",
            "formula_code": "T01",
            "variable_mapping": {},
            "evidence_ids": ["ev_result"],
            "risk_flags": [],
        }
        for index in range(4)
    ]

    async def fake_invoke_json(model_spec, *, skill_slug, prompt):
        calls.append(prompt)
        return long_titles if len(calls) == 1 else short_titles

    monkeypatch.setattr(generation, "_invoke_json", fake_invoke_json)
    result = await generation.generate_title_candidates(
        model_spec=None,
        brief={"audience": ["杭州小户型刚需家庭"]},
        strategy={"title_formula_code": "T01", "title_pattern_code": "T01-P01"},
        evidence_bundle={"items": [{"id": "ev_result", "value": "实测增加12㎡收纳空间"}]},
        rule_bundle={"title_formulas": [TITLE_FORMULAS[0]], "formula_patterns": []},
        channel_profile={"title_constraints": {"max_length": 20}},
    )

    assert len(calls) == 2
    assert "超过 20 字" in calls[1]
    assert all(len(item["text"]) <= 20 for item in result)


@pytest.mark.asyncio
async def test_semantic_review_normalizes_model_pass_levels(monkeypatch):
    async def fake_invoke_json(model_spec, *, skill_slug, prompt):
        return {
            "status": "success",
            "checks": [
                {
                    "code": "FACT_CHECK",
                    "level": "passed",
                    "message": "事实引用一致",
                }
            ],
        }

    monkeypatch.setattr(generation, "_invoke_json", fake_invoke_json)
    result = await generation.review_generated_content(
        model_spec=None,
        title="标题",
        body="正文",
        topics=[],
        brief={},
        strategy={},
        evidence_bundle={"items": []},
    )

    assert result["status"] == "passed"
    assert result["checks"][0]["level"] == "info"
    assert result["checks"][0]["location"] == "content"
