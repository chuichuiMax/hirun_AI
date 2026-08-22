from __future__ import annotations

from typing import Any, TypedDict


class ContentWorkflowState(TypedDict, total=False):
    task_id: str
    run_id: str
    uid: str
    model_spec: str | None
    workflow_version_id: str
    rule_version_id: str
    industry_template_version_id: str
    schema_version: int
    runtime_config_snapshot: dict[str, Any]
    content_type: dict[str, Any]
    industry_pack: dict[str, Any]
    persona_profile: dict[str, Any]
    channel_profile: dict[str, Any]
    compliance_policies: list[dict[str, Any]]
    lexicon_entries: list[dict[str, Any]]
    media_evidence_items: list[dict[str, Any]]
    content_brief: dict[str, Any]
    content_angles: list[dict[str, Any]]
    selected_angle: dict[str, Any] | None
    content_outline: dict[str, Any]
    evidence_bundle: dict[str, Any]
    title_candidates: list[dict[str, Any]]
    selected_title: dict[str, Any] | None
    content_draft: dict[str, Any] | None
    validation_report: dict[str, Any] | None
    title_validation_report: dict[str, Any] | None
    review_report: dict[str, Any] | None
    persona_diff: dict[str, Any] | None
    channel_result: dict[str, Any] | None
    approval_result: dict[str, Any] | None
    artifact_id: str | None
    current_node: str
    retry_counts: dict[str, int]
    state_version: int
    resume_parent_run_id: str | None
    task_mode: str
    value_analysis: dict[str, Any]
    match_decision_snapshot: dict[str, Any]
    strategy_explanation: dict[str, Any]
    evidence_collection: dict[str, Any]
    product_material_requirements: dict[str, Any]
    product_evidence_collection: dict[str, Any]
    product_evidence_pack: dict[str, Any]
    formula_rankings: dict[str, Any]
    formula_selection_snapshot: dict[str, Any]
    strategy_snapshot: dict[str, Any]
    delegated_agent_runs: dict[str, str]
    visual_plan: dict[str, Any]
    cover_job: dict[str, Any]
    cover_assets: list[dict[str, Any]]
    visual_review: dict[str, Any]
    selected_cover: dict[str, Any]
    artifact_version: dict[str, Any]
    formula_candidate_pool: dict[str, Any]
    revision_reason_code: str | None
    revision_target: str
    revision_status: str
    distribution_package: dict[str, Any]
