from copy import deepcopy

import pytest

from test.unit.content.test_industry_strategy_decision import example
from yuxi.content.model.contracts.joint_strategy import validate_joint_strategy
from yuxi.content.model.workflows.definition import WorkflowDefinitionPolicy
from yuxi.content.v3.joint_workflow import WORKFLOW_JOINT
from yuxi.content.v3.workflow import WORKFLOW_V3


def joint_example(mode="viral_rewrite"):
    candidates, strategy = example()
    inputs = {
        "strategy_candidates": candidates,
        "content_brief": {"form_values": {"pain": "选方案困难", "budget": "10万元总预算"}},
        "evidence_bundle": {"items": []},
        "runtime_config_snapshot": {"creation_mode": mode},
        "reference_candidates": [
            {
                "id": code,
                "source_hash": code * 64,
                "reference_card": {"required_slots": [{"name": "pain", "required": True}]},
            }
            for code in ("a", "b")
        ],
    }
    reference = {
        "status": "selected",
        "selected_asset_id": "b",
        "source_hash": "b" * 64,
        "assessments": [
            {
                "candidate_id": code,
                "eligible": True,
                "dimensions": dict.fromkeys(candidates["scoring"]["reference"]["weights"], score),
                "total": score * 25,
                "input_paths": ["content_brief.form_values.pain"],
                "reason": "有真实痛点",
            }
            for code, score in (("a", 2), ("b", 4))
        ],
        "slot_mapping": {"pain": ["content_brief.form_values.pain"]},
        "reason": "结构能够填充",
        "unresolved_questions": [],
    }
    return inputs, {"strategy": strategy, "reference": reference}


def test_joint_decision_selects_highest_scored_card_without_blueprint():
    inputs, result = joint_example()
    validated = validate_joint_strategy(result, inputs)
    assert validated.reference.selected_asset_id == "b"
    assert "reference_blueprint" not in validated.model_dump()["reference"]


@pytest.mark.parametrize("section", ["strategy", "reference"])
def test_missing_material_is_a_rejection_reason_not_an_evidence_path(section):
    inputs, result = joint_example()
    assessment = (
        next(item for item in result["strategy"]["method_assessments"] if item["candidate_id"] != "M2")
        if section == "strategy"
        else result["reference"]["assessments"][0]
    )
    assessment.update(
        eligible=False,
        dimensions={},
        total=None,
        reason="未提供情绪素材，淘汰该候选",
        input_paths=["content_brief.business_variables.emotion"],
    )
    validated = validate_joint_strategy(result, inputs)
    cleared = (
        next(item for item in validated.strategy.method_assessments if item.candidate_id == assessment["candidate_id"])
        if section == "strategy"
        else next(item for item in validated.reference.assessments if item.candidate_id == assessment["candidate_id"])
    )
    assert cleared.input_paths == []
    assert validated.strategy.status == "selected"
    assert validated.reference.status == "selected"


def test_envelope_paths_are_normalized_and_scores_are_calculated():
    inputs, result = joint_example()
    for section in ("title_assessments", "body_assessments", "method_assessments"):
        for assessment in result["strategy"][section]:
            assessment["input_paths"] = ["payload." + path for path in assessment["input_paths"]]
            assessment.pop("total", None)
    for assessment in result["reference"]["assessments"]:
        assessment["input_paths"] = ["payload." + path for path in assessment["input_paths"]]
        assessment.pop("total", None)
    result["reference"]["slot_mapping"]["pain"] = ["payload.content_brief.form_values.pain"]
    validated = validate_joint_strategy(result, inputs)
    assert validated.reference.assessments[1].total == 100
    assert validated.reference.slot_mapping["pain"] == ["content_brief.form_values.pain"]
    assert validated.strategy.method_assessments[0].total is not None


@pytest.mark.parametrize(
    "problem",
    [
        "rank",
        "hash",
        "missing_slot",
        "fake_path",
        "original_fact",
        "score",
        "missing_candidate",
        "unexpected_blueprint",
    ],
)
def test_joint_decision_rejects_invalid_reference(problem):
    inputs, result = joint_example()
    ref = result["reference"]
    if problem == "rank":
        ref["selected_asset_id"] = "a"
    elif problem == "hash":
        ref["source_hash"] = "a" * 64
    elif problem == "missing_slot":
        ref["slot_mapping"] = {}
    elif problem == "fake_path":
        ref["slot_mapping"]["pain"] = ["content_brief.missing"]
    elif problem == "original_fact":
        ref["slot_mapping"]["pain"] = ["reference_candidates.0.reference_card"]
    elif problem == "score":
        ref["assessments"][1]["total"] = 99
    elif problem == "missing_candidate":
        ref["assessments"].pop(0)
    elif problem == "unexpected_blueprint":
        ref["reference_blueprint"] = {"title_pattern": "伪造"}
    with pytest.raises(ValueError) as exc:
        validate_joint_strategy(result, inputs)
    if problem == "missing_slot":
        assert "缺少必要槽位：pain" in str(exc.value)
        assert "选中卡必要槽位：pain" in str(exc.value)


def test_reference_shape_normalizes_ineligible_scores_and_partial_dimensions():
    inputs, result = joint_example()
    scale = inputs["strategy_candidates"]["scoring"]["reference"]
    rejected, selected = result["reference"]["assessments"]
    rejected.update(eligible=False, dimensions={"goal": 1}, total=10)
    selected.update(dimensions={"goal": 4, "persona": 4}, input_paths=[])
    validated = validate_joint_strategy(result, inputs)
    cleared = next(item for item in validated.reference.assessments if item.candidate_id == rejected["candidate_id"])
    filled = next(item for item in validated.reference.assessments if item.candidate_id == selected["candidate_id"])
    assert cleared.dimensions == {} and cleared.total is None
    assert "content_brief.form_values.pain" in filled.input_paths
    assert filled.dimensions == {key: (4 if key == "goal" else 0) for key in scale["weights"]}


def test_slot_mapping_must_use_selected_card_names():
    inputs, result = joint_example()
    result["reference"]["slot_mapping"] = {
        "痛点": ["content_brief.form_values.pain"],
        "品牌": ["content_brief.form_values.pain"],
    }
    with pytest.raises(ValueError, match="提交了卡上不存在的槽位：品牌、痛点") as exc:
        validate_joint_strategy(result, inputs)
    assert "缺少必要槽位：pain" in str(exc.value)


def test_no_card_is_explicit_and_original_needs_no_reference():
    inputs, result = joint_example()
    inputs["reference_candidates"] = []
    result["reference"] = {
        "status": "no_candidate",
        "reason": "未找到准备好的完整文章",
        "unresolved_questions": ["请补充完整参考"],
    }
    assert validate_joint_strategy(result, inputs).reference.status == "no_candidate"
    inputs["runtime_config_snapshot"]["creation_mode"] = "original"
    result["reference"] = {"status": "not_requested", "reason": "原创模式"}
    assert validate_joint_strategy(result, inputs).reference.status == "not_requested"


def test_joint_workflow_preserves_legacy_and_eliminates_online_parsing():
    legacy = deepcopy(WORKFLOW_V3)
    WorkflowDefinitionPolicy.validate(WORKFLOW_JOINT)
    assert WORKFLOW_V3 == legacy
    assert len(WORKFLOW_JOINT["nodes"]) == 25
    assert not {"collect_viral_candidates", "select_viral_reference"} & {node["id"] for node in WORKFLOW_JOINT["nodes"]}
    select = next(node for node in WORKFLOW_JOINT["nodes"] if node["id"] == "select_creation_strategy")
    assert select["type"] == "agent"
    assert select["max_tool_calls"] == 1


def test_joint_workflow_cannot_replace_agent_with_fixed_selector():
    workflow = deepcopy(WORKFLOW_JOINT)
    next(node for node in workflow["nodes"] if node["id"] == "select_creation_strategy")["type"] = "deterministic"
    with pytest.raises(ValueError, match="必须使用 Agent"):
        WorkflowDefinitionPolicy.validate(workflow)


@pytest.mark.asyncio
async def test_locked_prepared_reference_passes_existing_evidence_contract(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from test.unit.content.test_viral_asset_preparation import prepared, source
    from yuxi.content.control.workflow import joint_strategy
    from yuxi.content.control.workflow.deterministic_node import V3DeterministicNodeHandler

    inputs, result = joint_example()
    inputs["strategy_candidates"], result["strategy"] = example("education")
    asset = SimpleNamespace(
        id="b",
        article_id="article-b",
        kb_id="kb-test",
        file_id="file-test",
        status="ready",
        source_hash="b" * 64,
        preparation_skill_hash="skill-version",
        source_json={"locator": "record:1"},
        prepared_json=prepared(source()),
    )
    monkeypatch.setattr(joint_strategy, "require_asset", AsyncMock(return_value=asset))
    monkeypatch.setattr(joint_strategy, "check_asset_source", AsyncMock(return_value=True))
    monkeypatch.setattr(joint_strategy, "preparation_skill_hash", lambda: "skill-version")
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalar_one=lambda: SimpleNamespace(uid="u"))))
    state = {**inputs, "uid": "u", "strategy_catalog": inputs["strategy_candidates"], "joint_strategy_decision": result}
    state.update(await joint_strategy.lock_joint_strategy(db=db, state=state, node_run_id="node"))
    merged = await V3DeterministicNodeHandler._merge_research_evidence(db=db, state=state, node_run_id="node")
    reference = merged["evidence_collection"]["evidence_items"][0]
    assert reference["allowed_usage"] == ["style_reference"]
    assert reference["metadata"]["usage_mode"] == "structure_reference_only"
    assert reference["metadata"]["selection_basis"]["prepared_reference_decision"]["selected_asset_id"] == "b"
    assert reference["metadata"]["reference_blueprint"] == asset.prepared_json["reference_blueprint"]
    assert source().body not in str(merged)


def test_compact_keeps_viral_governance_metadata():
    from yuxi.content.control.workflow.generation_input import compact_evidence_items_for_bundle
    from yuxi.content.model.viral_assets import BLUEPRINT_FIELDS

    blueprint = {name: "结构" for name in BLUEPRINT_FIELDS}
    blueprint["title_slot_sequence"] = ["主题", "问题"]
    blueprint["content_block_sequence"] = ["习惯", "动线"]
    blueprint["list_pattern"] = {"type": "none"}
    compacted = compact_evidence_items_for_bundle(
        [
            {
                "id": "ev_viral_1",
                "value": "结构摘录",
                "allowed_usage": ["style_reference"],
                "metadata": {
                    "material_type": "viral_example",
                    "usage_mode": "structure_reference_only",
                    "selected_reference": True,
                    "selection_basis": {"prepared_reference_decision": {"selected_asset_id": "b"}},
                    "reference_blueprint": blueprint,
                },
            }
        ]
    )
    metadata = compacted[0]["metadata"]
    assert metadata["usage_mode"] == "structure_reference_only"
    assert metadata["selection_basis"]["prepared_reference_decision"]["selected_asset_id"] == "b"
    assert metadata["reference_blueprint"] == blueprint
