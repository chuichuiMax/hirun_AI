from __future__ import annotations

from typing import Any

LEGACY_PLATFORM_WORKFLOW_V3_IDS = frozenset(
    {
        "content-workflow-enterprise-v3",
        "content-workflow-enterprise-v3.1",
        "content-workflow-enterprise-v3.2",
        "content-workflow-enterprise-v3.3",
        "content-workflow-enterprise-v3.4",
    }
)
LEGACY_PLATFORM_WORKFLOW_V3_ID = "content-workflow-enterprise-v3.4"
PLATFORM_WORKFLOW_V3_ID = "content-workflow-enterprise-v3.5"


def _fixed(node_id: str) -> dict[str, Any]:
    return {"id": node_id, "type": "deterministic", "handler": node_id}


def _human(node_id: str, interrupt_type: str) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": "human_review",
        "interrupt_type": interrupt_type,
        "expected_state_version_required": True,
    }


def _agent(
    node_id: str,
    agent_slug: str,
    skill_slugs: str | tuple[str, ...],
    input_contract: str,
    output_contract: str,
    *,
    state_inputs: tuple[str, ...],
    optional_state_inputs: tuple[str, ...] = (),
    knowledge_policy: str = "frozen_evidence_only",
    max_tool_calls: int = 4,
    max_retrieval_rounds: int = 0,
    max_knowledge_bases: int = 0,
    max_chunks_per_knowledge_base: int = 0,
    token_budget: int = 8000,
) -> dict[str, Any]:
    node = {
        "id": node_id,
        "type": "agent",
        "agent_slug": agent_slug,
        "required_skills": [skill_slugs] if isinstance(skill_slugs, str) else list(skill_slugs),
        "input_contract": input_contract,
        "state_inputs": list(state_inputs),
        "optional_state_inputs": list(optional_state_inputs),
        "output_contract": output_contract,
        "backend": "managed",
        "knowledge_policy": knowledge_policy,
        "timeout_seconds": 120,
        "max_execution_steps": 12,
        "max_tool_calls": max_tool_calls,
        "token_budget": token_budget,
        "result_tool_name": "submit_content_node_result",
    }
    if knowledge_policy == "agent_scope":
        node.update(
            {
                "max_retrieval_rounds": max_retrieval_rounds,
                "max_knowledge_bases": max_knowledge_bases,
                "max_chunks_per_knowledge_base": max_chunks_per_knowledge_base,
            }
        )
    return node


WORKFLOW_V3_NODES = [
    _fixed("compile_runtime_snapshot"),
    _fixed("ingest_real_materials"),
    _fixed("normalize_evidence"),
    _agent(
        "select_creation_strategy",
        "content-strategy-agent",
        ("content-value-analyzer", "content-strategy-planner"),
        "SelectCreationStrategyInputV1",
        "CreationStrategySelectionResultV1",
        state_inputs=(
            "rule_version_id",
            "content_brief",
            "evidence_bundle",
            "content_type",
            "industry_pack",
            "channel_profile",
        ),
    ),
    _fixed("lock_creation_strategy"),
    _agent(
        "collect_missing_evidence",
        "content-research-agent",
        "content-evidence-researcher",
        "CollectSelectedStrategyEvidenceInputV1",
        "EvidenceCollectionResultV1",
        state_inputs=(
            "rule_version_id",
            "content_brief",
            "strategy_selection",
            "evidence_gap_analysis",
            "evidence_bundle",
        ),
        knowledge_policy="agent_scope",
        max_tool_calls=4,
        max_retrieval_rounds=1,
        max_knowledge_bases=3,
        max_chunks_per_knowledge_base=5,
        token_budget=12000,
    ),
    _human("confirm_high_risk_facts", "high_risk_facts"),
    _fixed("freeze_evidence_bundle"),
    _agent(
        "generate_content",
        "content-generation-agent",
        ("content-title-generator", "content-outline-builder", "content-body-generator"),
        "GenerateContentInputV1",
        "GeneratedContentResultV1",
        state_inputs=(
            "content_brief",
            "strategy_snapshot",
            "evidence_bundle",
            "channel_profile",
            "persona_profile",
        ),
        optional_state_inputs=("validation_report",),
        token_budget=12000,
    ),
    _fixed("adapt_to_channel"),
    _fixed("deterministic_validate"),
    _agent(
        "semantic_review",
        "content-review-agent",
        "content-reviewer",
        "SemanticReviewInputV1",
        "ContentReviewResultV1",
        state_inputs=(
            "content_brief",
            "strategy_snapshot",
            "selected_title",
            "content_outline",
            "content_draft",
            "validation_report",
            "channel_result",
            "evidence_bundle",
        ),
        optional_state_inputs=("persona_diff",),
        knowledge_policy="frozen_evidence_only",
    ),
    {"id": "revise_if_needed", "type": "revision_router", "handler": "revise_if_needed"},
    _human("human_content_approval", "content_approval"),
    _fixed("save_artifact_snapshot"),
]

WORKFLOW_V3 = {
    "schema_version": 3,
    "runtime_limits": {"max_steps": 40, "max_revision_attempts": 3},
    "nodes": WORKFLOW_V3_NODES,
    "edges": [
        [WORKFLOW_V3_NODES[index]["id"], WORKFLOW_V3_NODES[index + 1]["id"]]
        for index in range(len(WORKFLOW_V3_NODES) - 1)
        if (WORKFLOW_V3_NODES[index]["id"], WORKFLOW_V3_NODES[index + 1]["id"])
        not in {("deterministic_validate", "semantic_review"), ("revise_if_needed", "human_content_approval")}
    ]
    + [
        ["deterministic_validate", "revise_if_needed"],
    ],
    "revision_routes": [
        {
            "from": "revise_if_needed",
            "to": "generate_content",
            "reason_codes": ["TITLE_VALIDATION_FAILED", "BODY_STRUCTURE_FAILED", "BODY_EVIDENCE_FAILED"],
            "max_attempts": 2,
        },
    ],
    "required_human_gates": sorted(
        {
            "confirm_high_risk_facts",
            "human_content_approval",
        }
    ),
}


__all__ = [
    "LEGACY_PLATFORM_WORKFLOW_V3_ID",
    "LEGACY_PLATFORM_WORKFLOW_V3_IDS",
    "PLATFORM_WORKFLOW_V3_ID",
    "WORKFLOW_V3",
    "WORKFLOW_V3_NODES",
]
