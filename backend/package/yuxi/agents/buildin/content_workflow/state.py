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
    strategy_plan: dict[str, Any]
    slot_plan: dict[str, Any]
    content_outline: dict[str, Any]
    evidence_usage_plan: dict[str, Any]
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
