from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from yuxi.content.model.workflows.definition import (
    DEFAULT_CONTRACTS,
    WorkflowCatalog,
    WorkflowDefinitionPolicy,
    workflow_definition_hash,
)
from yuxi.content.control.workflow.revision import RevisionRouteController
from yuxi.content.v3.seed import _upgrade_system_workflow_v3
from yuxi.content.v3.workflow import WORKFLOW_V3


AGENTS = {
    "content-strategy-agent",
    "content-research-agent",
    "content-title-agent",
    "content-body-agent",
    "content-review-agent",
    "content-visual-agent",
}
SKILLS = {
    "content-value-analyzer",
    "content-strategy-planner",
    "content-evidence-researcher",
    "content-title-generator",
    "content-outline-builder",
    "content-body-generator",
    "persona-style-polisher",
    "content-reviewer",
    "content-visual-planner",
    "content-cover-generator",
    "content-visual-reviewer",
}
CATALOG = WorkflowCatalog(
    agents=frozenset(AGENTS),
    skills=frozenset(SKILLS),
    contracts=frozenset(DEFAULT_CONTRACTS),
    backends=frozenset({"managed"}),
)


def _node(definition: dict, node_id: str) -> dict:
    return next(item for item in definition["nodes"] if item["id"] == node_id)


@pytest.mark.unit
def test_v3_has_exactly_31_nodes_and_passes_full_catalog_validation():
    WorkflowDefinitionPolicy.validate(WORKFLOW_V3, catalog=CATALOG)

    assert len(WORKFLOW_V3["nodes"]) == 31
    assert len(WORKFLOW_V3["edges"]) == 30
    assert len(workflow_definition_hash(WORKFLOW_V3)) == 64
    assert workflow_definition_hash(deepcopy(WORKFLOW_V3)) == workflow_definition_hash(WORKFLOW_V3)


@pytest.mark.unit
def test_system_v3_seed_upgrades_stale_workflow_definition_but_preserves_user_owned_definition():
    stale = SimpleNamespace(
        created_by="system",
        schema_version=3,
        definition_json={"schema_version": 3, "nodes": [], "edges": []},
        definition_hash="stale-hash",
        input_schema={},
        output_schema={},
    )
    user_owned = SimpleNamespace(
        created_by="operator",
        schema_version=3,
        definition_json={"schema_version": 3, "nodes": [], "edges": []},
        definition_hash="user-hash",
        input_schema={},
        output_schema={},
    )

    assert _upgrade_system_workflow_v3(stale) is True
    assert stale.definition_json == WORKFLOW_V3
    assert stale.definition_hash == workflow_definition_hash(WORKFLOW_V3)
    assert stale.input_schema == {"type": "ContentBrief", "version": 3}
    assert stale.output_schema == {"type": "ContentArtifact", "version": 3}
    assert _upgrade_system_workflow_v3(user_owned) is False
    assert user_owned.definition_hash == "user-hash"


@pytest.mark.unit
def test_schema_v2_definition_is_rejected():
    definition = deepcopy(WORKFLOW_V3)
    definition["schema_version"] = 2
    with pytest.raises(ValueError, match="只支持 V3"):
        WorkflowDefinitionPolicy.validate(definition)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("agent_slug", "缺少配置"),
        ("required_skills", "缺少配置"),
        ("input_contract", "缺少配置"),
        ("output_contract", "缺少配置"),
        ("backend", "缺少配置"),
        ("knowledge_policy", "缺少配置"),
        ("timeout_seconds", "缺少配置"),
        ("max_execution_steps", "缺少配置"),
        ("max_tool_calls", "缺少配置"),
        ("token_budget", "缺少配置"),
    ],
)
def test_agent_nodes_require_agent_skill_contract_backend_policy_and_budgets(field: str, message: str):
    definition = deepcopy(WORKFLOW_V3)
    _node(definition, "generate_title_candidates").pop(field)

    with pytest.raises(ValueError, match=message):
        WorkflowDefinitionPolicy.validate(definition, catalog=CATALOG)


@pytest.mark.unit
def test_unknown_agent_skill_contract_and_backend_fail_publication_validation():
    cases = [
        ("agent_slug", "missing-agent", "未知 Agent"),
        ("required_skills", ["missing-skill"], "未知或未授权 Skill"),
        ("output_contract", "MissingResultV1", "未知输出契约"),
        ("backend", "unsupported", "运行后端不可用"),
    ]
    for field, value, message in cases:
        definition = deepcopy(WORKFLOW_V3)
        _node(definition, "generate_title_candidates")[field] = value
        with pytest.raises(ValueError, match=message):
            WorkflowDefinitionPolicy.validate(definition, catalog=CATALOG)


@pytest.mark.unit
def test_match_node_cannot_be_agent_and_required_human_gate_cannot_be_removed():
    agent_match = deepcopy(WORKFLOW_V3)
    match_node = _node(agent_match, "match_combination_group")
    match_node.update(deepcopy(_node(agent_match, "generate_title_candidates")))
    match_node["id"] = "match_combination_group"
    missing_gate = deepcopy(WORKFLOW_V3)
    missing_gate["nodes"] = [item for item in missing_gate["nodes"] if item["id"] != "select_title"]
    missing_gate["edges"] = [edge for edge in missing_gate["edges"] if "select_title" not in edge] + [
        ["validate_title_candidates", "build_outline"]
    ]

    with pytest.raises(ValueError, match="禁止 Agent 化"):
        WorkflowDefinitionPolicy.validate(agent_match)
    with pytest.raises(ValueError, match="31 个节点|人工关口"):
        WorkflowDefinitionPolicy.validate(missing_gate)


@pytest.mark.unit
def test_skill_slug_and_invalid_revision_routes_are_rejected():
    skill_slug = deepcopy(WORKFLOW_V3)
    _node(skill_slug, "generate_title_candidates")["skill_slug"] = "content-title-generator"
    with pytest.raises(ValueError, match="禁止使用单个 skill_slug"):
        WorkflowDefinitionPolicy.validate(skill_slug)

    mutations = [
        ({"from": "semantic_review"}, "只能由固定"),
        ({"to": "missing-node"}, "非法节点"),
        ({"reason_codes": []}, "reason_codes"),
        ({"max_attempts": 0}, "max_attempts"),
    ]
    for mutation, message in mutations:
        definition = deepcopy(WORKFLOW_V3)
        definition["revision_routes"][0].update(mutation)
        with pytest.raises(ValueError, match=message):
            WorkflowDefinitionPolicy.validate(definition)


@pytest.mark.unit
def test_normal_edges_remain_acyclic_even_when_revision_routes_exist():
    definition = deepcopy(WORKFLOW_V3)
    definition["edges"].append(["package_for_distribution", "compile_runtime_snapshot"])

    with pytest.raises(ValueError, match="正常连线不能包含循环"):
        WorkflowDefinitionPolicy.validate(definition)


@pytest.mark.unit
def test_revision_controller_routes_only_known_reasons_and_stops_at_limit():
    controller = RevisionRouteController()

    first = controller.decide(
        definition=WORKFLOW_V3,
        reason_code="BODY_EVIDENCE_FAILED",
        retry_counts={},
    )
    second = controller.decide(
        definition=WORKFLOW_V3,
        reason_code="BODY_EVIDENCE_FAILED",
        retry_counts=first.retry_counts,
    )
    stopped = controller.decide(
        definition=WORKFLOW_V3,
        reason_code="BODY_EVIDENCE_FAILED",
        retry_counts=second.retry_counts,
    )
    unknown = controller.decide(definition=WORKFLOW_V3, reason_code="AGENT_FREE_GOTO", retry_counts={})

    assert first.status == "route" and first.target_node_id == "generate_body"
    assert second.status == "route" and second.retry_counts["generate_body"] == 2
    assert stopped.status == "limit_reached" and stopped.target_node_id == "human_content_approval"
    assert unknown.status == "continue" and unknown.target_node_id is None
