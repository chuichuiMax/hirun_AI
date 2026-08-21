from __future__ import annotations

from typing import Any


PLATFORM_WORKFLOW_V3_ID = "content-workflow-enterprise-v3"


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
    skill_slug: str,
    output_contract: str,
    *,
    knowledge_policy: str = "frozen_evidence_only",
    max_tool_calls: int = 4,
    max_retrieval_rounds: int = 0,
    max_knowledge_bases: int = 0,
    max_chunks_per_knowledge_base: int = 0,
) -> dict[str, Any]:
    node = {
        "id": node_id,
        "type": "agent",
        "agent_slug": agent_slug,
        "required_skills": [skill_slug],
        "input_contract": "ContentAgentNodeInputV1",
        "output_contract": output_contract,
        "backend": "managed",
        "knowledge_policy": knowledge_policy,
        "timeout_seconds": 120,
        "max_execution_steps": 12,
        "max_tool_calls": max_tool_calls,
        "token_budget": 8000,
        "result_tool_name": "submit_content_node_result",
    }
    if knowledge_policy == "task_scope":
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
        "analyze_content_value",
        "content-strategy-agent",
        "content-value-analyzer",
        "ContentValueResultV1",
    ),
    _human("select_content_direction", "content_direction"),
    _fixed("match_combination_group"),
    _agent(
        "explain_strategy",
        "content-strategy-agent",
        "content-strategy-planner",
        "StrategyExplanationResultV1",
    ),
    _fixed("resolve_formula_requirements"),
    _agent(
        "collect_missing_evidence",
        "content-research-agent",
        "content-evidence-researcher",
        "EvidenceCollectionResultV1",
        knowledge_policy="task_scope",
        max_tool_calls=12,
        max_retrieval_rounds=4,
        max_knowledge_bases=3,
        max_chunks_per_knowledge_base=5,
    ),
    _human("confirm_high_risk_facts", "high_risk_facts"),
    _fixed("freeze_evidence_bundle"),
    _agent(
        "rank_formula_candidates",
        "content-strategy-agent",
        "content-strategy-planner",
        "FormulaRankingResultV1",
    ),
    {
        **_human("lock_formula_selection", "formula_selection"),
        "quick_mode_policy": "highest_valid_score",
    },
    _agent(
        "generate_title_candidates",
        "content-title-agent",
        "content-title-generator",
        "TitleCandidatesResultV1",
    ),
    _fixed("validate_title_candidates"),
    _human("select_title", "title_selection"),
    _agent("build_outline", "content-body-agent", "content-outline-builder", "OutlineResultV1"),
    _agent("generate_body", "content-body-agent", "content-body-generator", "ContentDraftResultV1"),
    {
        **_agent(
            "persona_style_polish",
            "content-body-agent",
            "persona-style-polisher",
            "PersonaPolishResultV1",
        ),
        "optional": True,
    },
    _fixed("adapt_to_channel"),
    _fixed("deterministic_validate"),
    _agent(
        "semantic_review",
        "content-review-agent",
        "content-reviewer",
        "ContentReviewResultV1",
        knowledge_policy="task_scope",
    ),
    {"id": "revise_if_needed", "type": "revision_router", "handler": "revise_if_needed"},
    _human("human_content_approval", "content_approval"),
    _agent("plan_visuals", "content-visual-agent", "content-visual-planner", "VisualPlanResultV1"),
    _agent(
        "submit_cover_job",
        "content-visual-agent",
        "content-cover-generator",
        "CoverJobSubmissionResultV1",
        max_tool_calls=2,
    ),
    {
        "id": "wait_cover_job",
        "type": "external_wait",
        "external_job_type": "content_cover",
        "timeout_seconds": 900,
        "state_version_required": True,
    },
    _agent("visual_review", "content-visual-agent", "content-visual-reviewer", "VisualReviewResultV1"),
    _human("select_cover", "cover_selection"),
    _fixed("save_artifact_snapshot"),
    _fixed("package_for_distribution"),
]

WORKFLOW_V3 = {
    "schema_version": 3,
    "runtime_limits": {"max_steps": 80, "max_revision_attempts": 5},
    "nodes": WORKFLOW_V3_NODES,
    "edges": [
        [WORKFLOW_V3_NODES[index]["id"], WORKFLOW_V3_NODES[index + 1]["id"]]
        for index in range(len(WORKFLOW_V3_NODES) - 1)
    ],
    "revision_routes": [
        {
            "from": "revise_if_needed",
            "to": "generate_title_candidates",
            "reason_codes": ["TITLE_VALIDATION_FAILED"],
            "max_attempts": 2,
        },
        {
            "from": "revise_if_needed",
            "to": "generate_body",
            "reason_codes": ["BODY_STRUCTURE_FAILED", "BODY_EVIDENCE_FAILED"],
            "max_attempts": 2,
        },
        {
            "from": "revise_if_needed",
            "to": "persona_style_polish",
            "reason_codes": ["PERSONA_STYLE_FAILED"],
            "max_attempts": 1,
        },
    ],
    "required_human_gates": sorted(
        {
            "select_content_direction",
            "confirm_high_risk_facts",
            "lock_formula_selection",
            "select_title",
            "human_content_approval",
            "select_cover",
        }
    ),
}


__all__ = ["PLATFORM_WORKFLOW_V3_ID", "WORKFLOW_V3", "WORKFLOW_V3_NODES"]
