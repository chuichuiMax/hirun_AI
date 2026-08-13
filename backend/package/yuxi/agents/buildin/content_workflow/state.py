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
    content_brief: dict[str, Any]
    strategy_plan: dict[str, Any]
    evidence_bundle: dict[str, Any]
    title_candidates: list[dict[str, Any]]
    selected_title: dict[str, Any] | None
    content_draft: dict[str, Any] | None
    validation_report: dict[str, Any] | None
    review_report: dict[str, Any] | None
    artifact_id: str | None
    current_node: str
    retry_counts: dict[str, int]
