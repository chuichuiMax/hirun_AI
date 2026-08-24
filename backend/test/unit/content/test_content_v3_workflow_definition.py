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
    "strategy-product-researcher",
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
def test_v3_has_exactly_35_nodes_and_passes_full_catalog_validation():
    WorkflowDefinitionPolicy.validate(WORKFLOW_V3, catalog=CATALOG)

    assert len(WORKFLOW_V3["nodes"]) == 35
    assert len(WORKFLOW_V3["edges"]) == 33
    assert len(workflow_definition_hash(WORKFLOW_V3)) == 64
    assert workflow_definition_hash(deepcopy(WORKFLOW_V3)) == workflow_definition_hash(WORKFLOW_V3)


@pytest.mark.unit
def test_every_agent_node_declares_its_own_input_contract_and_upstream_state():
    expected = {
        "analyze_content_value": ("AnalyzeContentValueInputV1", {"content_brief", "evidence_bundle"}),
        "explain_strategy": ("ExplainStrategyInputV1", {"value_analysis", "match_decision_snapshot"}),
        "collect_missing_evidence": ("CollectMissingEvidenceInputV1", {"formula_candidate_pool", "evidence_bundle"}),
        "rank_formula_candidates": ("RankFormulaCandidatesInputV1", {"formula_candidate_pool", "evidence_bundle"}),
        "collect_strategy_product_evidence": (
            "CollectStrategyProductEvidenceInputV1",
            {"strategy_snapshot", "product_material_requirements", "evidence_bundle"},
        ),
        "generate_title_candidates": (
            "GenerateTitleCandidatesInputV1",
            {
                "strategy_snapshot",
                "product_evidence_pack",
                "title_evidence_requirements",
                "evidence_bundle",
            },
        ),
        "build_outline": ("BuildOutlineInputV1", {"selected_title", "strategy_snapshot", "product_evidence_pack"}),
        "generate_body": (
            "GenerateBodyInputV1",
            {"selected_title", "content_outline", "strategy_snapshot", "product_evidence_pack"},
        ),
        "persona_style_polish": (
            "PersonaStylePolishInputV1",
            {"content_draft", "persona_profile", "product_evidence_pack"},
        ),
        "semantic_review": ("SemanticReviewInputV1", {"content_draft", "validation_report", "strategy_snapshot"}),
        "plan_visuals": ("PlanVisualsInputV1", {"content_draft", "artifact_version", "strategy_snapshot"}),
        "submit_cover_job": ("SubmitCoverJobInputV1", {"visual_plan", "artifact_version"}),
        "visual_review": ("VisualReviewInputV1", {"visual_plan", "cover_assets", "content_draft"}),
    }

    agent_nodes = {item["id"]: item for item in WORKFLOW_V3["nodes"] if item["type"] == "agent"}
    assert set(agent_nodes) == set(expected)
    for node_id, (contract, upstream) in expected.items():
        assert agent_nodes[node_id]["input_contract"] == contract
        assert upstream <= set(agent_nodes[node_id]["state_inputs"])


@pytest.mark.unit
def test_knowledge_nodes_use_their_managed_agent_knowledge_scope():
    knowledge_nodes = {
        item["id"]: item["knowledge_policy"]
        for item in WORKFLOW_V3["nodes"]
        if item["type"] == "agent" and item["knowledge_policy"] == "agent_scope"
    }

    assert knowledge_nodes == {
        "collect_missing_evidence": "agent_scope",
        "collect_strategy_product_evidence": "agent_scope",
        "semantic_review": "agent_scope",
    }


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
    assert stale.version == 6
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
def test_research_nodes_reserve_enough_tokens_for_retrieval_and_final_submission():
    assert _node(WORKFLOW_V3, "collect_missing_evidence")["token_budget"] == 12000
    assert _node(WORKFLOW_V3, "collect_strategy_product_evidence")["token_budget"] == 12000
    assert _node(WORKFLOW_V3, "generate_title_candidates")["token_budget"] == 8000


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
def test_publication_rejects_shared_agent_input_and_review_gate_bypass():
    shared = deepcopy(WORKFLOW_V3)
    _node(shared, "build_outline")["input_contract"] = _node(shared, "generate_body")["input_contract"]
    with pytest.raises(ValueError, match="独立输入契约"):
        WorkflowDefinitionPolicy.validate(shared, catalog=CATALOG)

    bypass = deepcopy(WORKFLOW_V3)
    bypass["edges"].remove(["deterministic_validate", "revise_if_needed"])
    bypass["edges"].append(["deterministic_validate", "semantic_review"])
    with pytest.raises(ValueError, match="固定回修路由|不得绕过"):
        WorkflowDefinitionPolicy.validate(bypass, catalog=CATALOG)

    title_bypass = deepcopy(WORKFLOW_V3)
    title_bypass["edges"].remove(["validate_title_candidates", "revise_if_needed"])
    title_bypass["edges"].append(["validate_title_candidates", "select_title"])
    with pytest.raises(ValueError, match="固定回修路由|不得绕过"):
        WorkflowDefinitionPolicy.validate(title_bypass, catalog=CATALOG)


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
    with pytest.raises(ValueError, match="35 个节点|人工关口"):
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
    definition["edges"].append(["freeze_product_evidence_bundle", "compile_runtime_snapshot"])

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
    assert stopped.status == "limit_reached" and stopped.target_node_id is None
    assert unknown.status == "continue" and unknown.target_node_id is None
