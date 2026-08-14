from copy import deepcopy

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from yuxi.content.rules import BODY_FORMULAS, COMBINATION_RULES, METHODS, TITLE_FORMULAS
from yuxi.content.schemas import CreationMethodInput, RuleBundleUpdate
from yuxi.services.content_service import normalize_rule_bundle, validate_rule_bundle_for_publish


def _bundle() -> dict:
    return {
        "methods": deepcopy(METHODS),
        "title_formulas": deepcopy(TITLE_FORMULAS),
        "content_formulas": deepcopy(BODY_FORMULAS),
        "combination_rules": deepcopy(COMBINATION_RULES),
    }


def test_seed_rule_bundle_is_publishable():
    validation = validate_rule_bundle_for_publish(_bundle())

    assert validation == {"errors": [], "warnings": []}


def test_publish_validation_reports_disabled_references_and_uncovered_goal():
    bundle = _bundle()
    next(item for item in bundle["methods"] if item["code"] == "M01")["enabled"] = False
    bundle["combination_rules"] = [
        item for item in bundle["combination_rules"] if item["content_goal"] != "brand"
    ]

    validation = validate_rule_bundle_for_publish(bundle)
    error_codes = {item["code"] for item in validation["errors"]}

    assert "TITLE_METHOD_INVALID" in error_codes
    assert "COMBINATION_METHOD_INVALID" in error_codes
    assert "COMBINATION_GOAL_UNCOVERED" in error_codes


def test_rule_bundle_normalization_trims_deduplicates_and_orders_items():
    bundle = _bundle()
    bundle["methods"][0]["code"] = "m01"
    bundle["methods"][0]["suitable_scenes"] = [" 案例复盘 ", "案例复盘", ""]
    payload = RuleBundleUpdate(changelog="  调整规则  ", **bundle)

    normalized = normalize_rule_bundle(payload)

    assert normalized["changelog"] == "调整规则"
    assert normalized["methods"][0]["code"] == "M01"
    assert normalized["methods"][0]["suitable_scenes"] == ["案例复盘"]
    assert [item["sort_order"] for item in normalized["methods"]] == list(range(len(METHODS)))


def test_rule_bundle_normalization_rejects_duplicate_codes():
    bundle = _bundle()
    bundle["methods"][1]["code"] = bundle["methods"][0]["code"]
    payload = RuleBundleUpdate(changelog="重复编码", **bundle)

    with pytest.raises(HTTPException) as exc_info:
        normalize_rule_bundle(payload)

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error"]["code"] == "CONTENT_RULE_CODE_DUPLICATED"


def test_rule_inputs_reject_whitespace_only_required_text():
    with pytest.raises(ValidationError):
        CreationMethodInput(code="M99", name="   ", principle="有效原则")
