from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from yuxi.content.model.contracts import (
    CONTRACT_REGISTRY,
    ContentAgentNodeInputV1,
    ContentNodeResultCollector,
    ContractDomainContext,
    ContractDomainValidationError,
    build_content_result_tool,
    get_contract_model,
    validate_content_node_result,
)


DOMAIN_CONTEXT = ContractDomainContext(
    locked_group_id="group-1",
    title_formula_pool=frozenset({"T1", "T2"}),
    body_formula_pool=frozenset({"B1", "B2"}),
    locked_title_formula_code="T1",
    locked_body_formula_code="B1",
    allowed_evidence_by_usage={
        "any": frozenset({"e-any", "e-title", "e-body", "e-visual"}),
        "title": frozenset({"e-title"}),
        "body": frozenset({"e-body"}),
        "visual": frozenset({"e-visual"}),
    },
    allowed_asset_ids=frozenset({"asset-1", "asset-2"}),
    locked_title="locked title",
    artifact_version_id="artifact-v1",
    visual_plan_hash="plan-hash",
    allowed_numbers=frozenset({"88"}),
)


VALID_PAYLOADS = {
    "ContentValueResultV1": {
        "value_points": ["value"],
        "direction_candidates": [{"direction_code": "CT01", "reason": "reason", "evidence_ids": ["e-any"]}],
        "reasoning": "reasoning",
        "evidence_ids": ["e-any"],
    },
    "StrategyExplanationResultV1": {
        "locked_group_id": "group-1",
        "explanation": "explanation",
        "risks": [],
        "evidence_ids": ["e-any"],
    },
    "EvidenceCollectionResultV1": {
        "evidence_items": [
            {
                "id": "new-evidence",
                "variable_codes": ["price"],
                "value": "value",
                "source_type": "knowledge_base",
                "source_id": "source-1",
                "source_version": "1",
                "verified_status": "retrieved",
                "allowed_usage": ["body"],
                "risk_level": "normal",
                "source_hash": "hash",
            }
        ],
        "citations": ["source-1"],
        "unresolved_questions": [],
    },
    "FormulaRankingResultV1": {
        "title_rankings": [{"formula_code": "T1", "reason": "best"}],
        "body_rankings": [{"formula_code": "B1", "reason": "best"}],
    },
    "TitleCandidatesResultV1": {
        "candidates": [
            {"id": "title-1", "text": "first title", "formula_code": "T1", "evidence_ids": ["e-title"], "reason": "a"},
            {"id": "title-2", "text": "second title", "formula_code": "T1", "evidence_ids": ["e-title"], "reason": "b"},
        ],
        "selected_title_formula_code": "T1",
        "evidence_ids": ["e-title"],
    },
    "OutlineResultV1": {
        "body_formula_code": "B1",
        "sections": [{"section_id": "s1", "goal": "goal", "evidence_ids": ["e-body"]}],
    },
    "ContentDraftResultV1": {
        "body": "body text",
        "topics": ["topic"],
        "paragraph_evidence": [{"paragraph_id": "p1", "evidence_ids": ["e-body"]}],
        "body_formula_code": "B1",
    },
    "PersonaPolishResultV1": {
        "polished_body": "polished body",
        "change_summary": ["tone"],
        "preserved_fact_checks": [{"evidence_id": "e-body", "preserved": True}],
    },
    "ContentReviewResultV1": {
        "status": "passed",
        "checks": [{"code": "facts", "status": "passed", "message": "ok", "evidence_ids": ["e-body"]}],
        "evidence_conflicts": [],
    },
    "VisualPlanResultV1": {
        "size": {"width": 1080, "height": 1440},
        "safe_area": {"top": 20, "right": 20, "bottom": 20, "left": 20},
        "text": ["cover text"],
        "source_asset_ids": ["asset-1"],
        "mode": "template",
        "risks": [],
        "artifact_version_id": "artifact-v1",
        "evidence_ids": ["e-visual"],
    },
    "CoverJobSubmissionResultV1": {
        "cover_job_id": "job-1",
        "plan_hash": "plan-hash",
        "source_asset_ids": ["asset-1"],
    },
    "VisualReviewResultV1": {
        "assets": [{"asset_id": "asset-1", "status": "passed", "issues": []}],
        "status": "passed",
        "recommended_asset_id": "asset-1",
    },
}


def _make_unknown(contract_name: str, payload: dict) -> dict:
    value = deepcopy(payload)
    if contract_name == "ContentValueResultV1":
        value["evidence_ids"] = ["unknown"]
    elif contract_name == "StrategyExplanationResultV1":
        value["locked_group_id"] = "unknown"
    elif contract_name == "EvidenceCollectionResultV1":
        value["evidence_items"].append(deepcopy(value["evidence_items"][0]))
    elif contract_name == "FormulaRankingResultV1":
        value["title_rankings"][0]["formula_code"] = "unknown"
    elif contract_name == "TitleCandidatesResultV1":
        value["candidates"][0]["formula_code"] = "unknown"
    elif contract_name in {"OutlineResultV1", "ContentDraftResultV1"}:
        value["body_formula_code"] = "unknown"
    elif contract_name == "PersonaPolishResultV1":
        value["preserved_fact_checks"][0]["evidence_id"] = "unknown"
    elif contract_name == "ContentReviewResultV1":
        value["checks"][0]["evidence_ids"] = ["unknown"]
    elif contract_name == "VisualPlanResultV1":
        value["source_asset_ids"] = ["unknown"]
    elif contract_name == "CoverJobSubmissionResultV1":
        value["plan_hash"] = "unknown"
    elif contract_name == "VisualReviewResultV1":
        value["assets"][0]["asset_id"] = "unknown"
    return value


@pytest.mark.parametrize("contract_name", sorted(VALID_PAYLOADS))
def test_each_contract_accepts_valid_payload(contract_name):
    result = validate_content_node_result(contract_name, VALID_PAYLOADS[contract_name], DOMAIN_CONTEXT)
    assert result.__class__.__name__ == contract_name


def test_formula_ranking_pool_comes_from_match_snapshot_before_selection_exists():
    node_input = ContentAgentNodeInputV1.model_validate(
        {
            "task_id": "task-1",
            "parent_run_id": "run-1",
            "node_id": "rank_formula_candidates",
            "attempt": 1,
            "content_brief": {},
            "runtime_config_snapshot": {},
            "match_decision_snapshot": {
                "selected_group_id": "group-1",
                "eligible_title_formula_codes": ["T02", "T06"],
                "eligible_body_formula_codes": ["C02"],
            },
            "formula_selection_snapshot": {},
            "evidence_bundle": {"items": []},
            "evidence_bundle_hash": "hash",
            "locked_versions": {
                "industry_pack_version_id": "industry-v1",
                "channel_profile_version_id": "channel-v1",
                "persona_profile_version_id": None,
                "rule_version_id": "rules-v1",
                "title_formula_code": None,
                "body_formula_code": None,
                "artifact_version_id": None,
            },
            "locked_values": {},
            "node_responsibility": "rank",
            "prohibited_actions": [],
            "output_json_schema": {},
        }
    )

    context = ContractDomainContext.from_node_input(node_input)
    result = validate_content_node_result(
        "FormulaRankingResultV1",
        {
            "title_rankings": [{"formula_code": "T06", "reason": "best"}],
            "body_rankings": [{"formula_code": "C02", "reason": "best"}],
        },
        context,
    )

    assert result.title_rankings[0].formula_code == "T06"


def test_allowed_numbers_are_indexed_from_nested_evidence_values():
    payload = {
        "task_id": "task-1",
        "parent_run_id": "run-1",
        "node_id": "generate_title_candidates",
        "attempt": 1,
        "content_brief": {},
        "runtime_config_snapshot": {},
        "match_decision_snapshot": {},
        "formula_selection_snapshot": {"selected_title_formula_code": "T02"},
        "evidence_bundle": {
            "items": [
                {
                    "id": "ev-title",
                    "value": {"area": "89㎡", "results": ["收纳增加12㎡"]},
                    "verified_status": "user_confirmed",
                    "allowed_usage": ["title"],
                }
            ]
        },
        "evidence_bundle_hash": "hash",
        "locked_versions": {
            "industry_pack_version_id": "industry-v1",
            "channel_profile_version_id": "channel-v1",
            "persona_profile_version_id": None,
            "rule_version_id": "rules-v1",
            "title_formula_code": "T02",
            "body_formula_code": None,
            "artifact_version_id": None,
        },
        "locked_values": {},
        "node_responsibility": "title",
        "prohibited_actions": [],
        "output_json_schema": {},
    }
    context = ContractDomainContext.from_node_input(ContentAgentNodeInputV1.model_validate(payload))

    result = validate_content_node_result(
        "TitleCandidatesResultV1",
        {
            "candidates": [
                {
                    "id": "title-1",
                    "text": "89㎡多出12㎡收纳",
                    "formula_code": "T02",
                    "evidence_ids": ["ev-title"],
                    "reason": "facts",
                },
                {
                    "id": "title-2",
                    "text": "89㎡收纳改造",
                    "formula_code": "T02",
                    "evidence_ids": ["ev-title"],
                    "reason": "facts",
                },
            ],
            "selected_title_formula_code": "T02",
            "evidence_ids": ["ev-title"],
        },
        context,
    )

    assert context.allowed_numbers == frozenset({"89", "12"})
    assert result.candidates[0].text == "89㎡多出12㎡收纳"


@pytest.mark.parametrize("contract_name", sorted(VALID_PAYLOADS))
def test_each_contract_rejects_missing_required_field(contract_name):
    payload = deepcopy(VALID_PAYLOADS[contract_name])
    payload.pop(next(iter(payload)))
    with pytest.raises(ValidationError):
        validate_content_node_result(contract_name, payload, DOMAIN_CONTEXT)


@pytest.mark.parametrize("contract_name", sorted(VALID_PAYLOADS))
def test_each_contract_rejects_out_of_scope_field(contract_name):
    payload = {**deepcopy(VALID_PAYLOADS[contract_name]), "unauthorized_field": "value"}
    with pytest.raises(ValidationError) as exc_info:
        validate_content_node_result(contract_name, payload, DOMAIN_CONTEXT)
    assert exc_info.value.errors()[0]["type"] == "extra_forbidden"


@pytest.mark.parametrize("contract_name", sorted(VALID_PAYLOADS))
def test_each_contract_rejects_unknown_or_unlocked_id(contract_name):
    with pytest.raises(ContractDomainValidationError):
        invalid = _make_unknown(contract_name, VALID_PAYLOADS[contract_name])
        validate_content_node_result(contract_name, invalid, DOMAIN_CONTEXT)


def test_content_value_contract_rejects_temporary_direction_codes():
    payload = deepcopy(VALID_PAYLOADS["ContentValueResultV1"])
    payload["direction_candidates"][0]["direction_code"] = "D01"

    with pytest.raises(ValidationError) as exc_info:
        validate_content_node_result("ContentValueResultV1", payload, DOMAIN_CONTEXT)

    assert exc_info.value.errors()[0]["loc"] == ("direction_candidates", 0, "direction_code")


@pytest.mark.parametrize(
    ("contract_name", "forbidden_field"),
    [
        ("TitleCandidatesResultV1", "body"),
        ("ContentDraftResultV1", "title"),
        ("ContentReviewResultV1", "revised_body"),
        ("ContentValueResultV1", "locked_group_id"),
        ("EvidenceCollectionResultV1", "article"),
    ],
)
def test_role_contracts_cannot_cross_node_responsibilities(contract_name, forbidden_field):
    payload = {**deepcopy(VALID_PAYLOADS[contract_name]), forbidden_field: "forbidden"}
    with pytest.raises(ValidationError):
        validate_content_node_result(contract_name, payload, DOMAIN_CONTEXT)


@pytest.mark.parametrize(
    ("contract_name", "field_path", "value"),
    [
        ("TitleCandidatesResultV1", ("candidates", 0, "text"), "unsupported 99"),
        ("ContentDraftResultV1", ("body",), "unsupported 99"),
        ("PersonaPolishResultV1", ("polished_body",), "unsupported 99"),
        ("VisualPlanResultV1", ("text", 0), "unsupported 99"),
    ],
)
def test_creative_contracts_block_unsupported_numbers(contract_name, field_path, value):
    payload = deepcopy(VALID_PAYLOADS[contract_name])
    target = payload
    for key in field_path[:-1]:
        target = target[key]
    target[field_path[-1]] = value
    with pytest.raises(ContractDomainValidationError) as exc_info:
        validate_content_node_result(contract_name, payload, DOMAIN_CONTEXT)
    assert exc_info.value.code == "unsupported_number"


def test_common_agent_input_requires_all_trace_and_lock_fields():
    payload = {
        "task_id": "task",
        "parent_run_id": "run",
        "node_id": "node",
        "attempt": 1,
        "content_brief": {},
        "runtime_config_snapshot": {},
        "match_decision_snapshot": {},
        "formula_selection_snapshot": {},
        "evidence_bundle": {"items": []},
        "evidence_bundle_hash": "hash",
        "locked_versions": {
            "industry_pack_version_id": "industry-v1",
            "channel_profile_version_id": "channel-v1",
            "persona_profile_version_id": None,
            "rule_version_id": "rules-v3",
            "title_formula_code": "T1",
            "body_formula_code": "B1",
            "artifact_version_id": None,
        },
        "locked_values": {},
        "node_responsibility": "do one thing",
        "prohibited_actions": ["do not write body"],
        "output_json_schema": get_contract_model("ContentValueResultV1").model_json_schema(),
    }
    assert ContentAgentNodeInputV1.model_validate(payload).task_id == "task"
    payload.pop("evidence_bundle_hash")
    with pytest.raises(ValidationError):
        ContentAgentNodeInputV1.model_validate(payload)


@pytest.mark.asyncio
async def test_result_collector_requires_activation_exactly_one_submission_and_no_defaulting():
    runtime = type("Runtime", (), {})()
    runtime._required_skill_closure = ["content-reviewer"]
    runtime._activated_required_skills = []
    collector = ContentNodeResultCollector("ContentReviewResultV1", DOMAIN_CONTEXT, runtime)

    with pytest.raises(ContractDomainValidationError, match="未激活"):
        await collector.submit(**VALID_PAYLOADS["ContentReviewResultV1"])
    assert collector.submission_count == 0

    runtime._activated_required_skills = ["content-reviewer"]
    invalid = _make_unknown("ContentReviewResultV1", VALID_PAYLOADS["ContentReviewResultV1"])
    with pytest.raises(ContractDomainValidationError, match="未授权"):
        await collector.submit(**invalid)
    assert collector.submission_count == 0

    await collector.submit(**VALID_PAYLOADS["ContentReviewResultV1"])
    assert collector.finalize()["status"] == "passed"
    with pytest.raises(ContractDomainValidationError, match="只能提交一次"):
        await collector.submit(**VALID_PAYLOADS["ContentReviewResultV1"])

    empty = ContentNodeResultCollector("ContentReviewResultV1", DOMAIN_CONTEXT, runtime)
    with pytest.raises(ContractDomainValidationError, match="未通过"):
        empty.finalize()


@pytest.mark.asyncio
async def test_structured_result_tool_uses_registered_pydantic_schema():
    runtime = type("Runtime", (), {})()
    runtime._required_skill_closure = ["content-reviewer"]
    runtime._activated_required_skills = ["content-reviewer"]
    collector = ContentNodeResultCollector("ContentReviewResultV1", DOMAIN_CONTEXT, runtime)
    tool = build_content_result_tool(collector)

    rejected = await tool.ainvoke(_make_unknown("ContentReviewResultV1", VALID_PAYLOADS["ContentReviewResultV1"]))
    assert "请修正后重新提交" in rejected
    assert collector.submission_count == 0

    await tool.ainvoke(VALID_PAYLOADS["ContentReviewResultV1"])

    assert tool.name == "submit_content_node_result"
    assert collector.submission_count == 1
    assert len(CONTRACT_REGISTRY) == 13
