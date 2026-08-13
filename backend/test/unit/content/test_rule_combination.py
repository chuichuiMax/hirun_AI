from __future__ import annotations

import pytest

from yuxi.content.rules import (
    BODY_FORMULAS,
    COMBINATION_RULES,
    METHODS,
    TITLE_FORMULAS,
    recommend_strategy,
    validate_strategy_bundle,
)


@pytest.fixture
def rule_bundle() -> dict:
    return {
        "version": {"id": "rules-v1"},
        "methods": METHODS,
        "title_formulas": TITLE_FORMULAS,
        "content_formulas": BODY_FORMULAS,
        "combination_rules": COMBINATION_RULES,
    }


@pytest.fixture
def complete_brief() -> dict:
    return {
        "brand": {"name": "青禾成长中心"},
        "audience": ["6-10岁孩子家长"],
        "business_variables": {
            "product": "少儿英语启蒙小班",
            "pain_points": ["孩子不敢开口"],
            "advantages": ["8人小班", "每周反馈"],
            "result": "12周，每周2次",
            "location": "杭州",
        },
        "form_values": {},
    }


@pytest.mark.parametrize(
    ("goal", "body_code"),
    [("traffic", "C02"), ("educate", "C03"), ("acquire", "C01"), ("brand", "C04")],
)
def test_recommend_strategy_uses_goal_matrix(rule_bundle, complete_brief, goal, body_code):
    strategy = recommend_strategy(rule_bundle, brief=complete_brief, content_goal=goal)

    assert strategy["content_formula_code"] == body_code
    assert strategy["rule_version_id"] == "rules-v1"
    assert strategy["scene_enhancer"] == "S01"


def test_validate_strategy_blocks_incompatible_methods(rule_bundle, complete_brief):
    result = validate_strategy_bundle(
        rule_bundle,
        brief=complete_brief,
        content_goal="acquire",
        methods=["M02"],
        title_formula_code="T01",
        content_formula_code="C01",
    )

    assert result["compatibility"] == "blocked"
    assert "标题公式与所选创作手法不兼容" in result["reasons"]
    assert "正文公式与所选创作手法不兼容" in result["reasons"]


def test_validate_strategy_reports_missing_formula_variables(rule_bundle):
    result = validate_strategy_bundle(
        rule_bundle,
        brief={"brand": {}, "audience": [], "business_variables": {}, "form_values": {}},
        content_goal="acquire",
        methods=["M01", "M04"],
        title_formula_code="T01",
        content_formula_code="C01",
    )

    assert result["compatibility"] == "blocked"
    assert {"audience", "number", "result", "product", "pain_points", "advantages"}.issubset(
        result["missing_variables"]
    )


def test_validate_strategy_warns_for_valid_non_default_goal_combination(rule_bundle, complete_brief):
    result = validate_strategy_bundle(
        rule_bundle,
        brief=complete_brief,
        content_goal="brand",
        methods=["M01", "M04"],
        title_formula_code="T01",
        content_formula_code="C01",
    )

    assert result["compatibility"] == "warning"
    assert result["missing_variables"] == []
    assert "该组合不是当前内容目标的推荐组合" in result["reasons"]
