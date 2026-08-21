from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class RevisionDecision:
    status: Literal["route", "continue", "limit_reached"]
    target_node_id: str | None
    retry_counts: dict[str, int]


class RevisionRouteController:
    """只解释发布定义中的 revision_routes，不允许 Agent 自由 goto。"""

    def decide(
        self,
        *,
        definition: dict[str, Any],
        reason_code: str | None,
        retry_counts: dict[str, int],
    ) -> RevisionDecision:
        if not reason_code:
            return RevisionDecision("continue", None, dict(retry_counts))
        route = next(
            (
                item
                for item in definition.get("revision_routes") or []
                if reason_code in (item.get("reason_codes") or [])
            ),
            None,
        )
        if route is None:
            return RevisionDecision("continue", None, dict(retry_counts))
        target = route["to"]
        counts = dict(retry_counts)
        current = int(counts.get(target, 0))
        if current >= int(route["max_attempts"]):
            return RevisionDecision("limit_reached", "human_content_approval", counts)
        counts[target] = current + 1
        return RevisionDecision("route", target, counts)


def resolve_revision_reason(
    *,
    title_validation_report: dict[str, Any] | None,
    validation_report: dict[str, Any] | None,
    review_report: dict[str, Any] | None,
) -> str | None:
    """把校验结果收敛成发布工作流允许识别的固定 reason code。"""

    title_report = title_validation_report or {}
    if title_report.get("status") == "blocked" or any(
        item.get("status") == "blocked" for item in title_report.get("items") or []
    ):
        return "TITLE_VALIDATION_FAILED"

    checks = [
        *(validation_report or {}).get("checks", []),
        *(review_report or {}).get("checks", []),
    ]
    blocked_codes = {
        str(item.get("code") or "").upper()
        for item in checks
        if item.get("level") == "error" or item.get("status") == "blocked"
    }
    if (
        not blocked_codes
        and (validation_report or {}).get("status") != "blocked"
        and (review_report or {}).get("status") != "blocked"
    ):
        return None
    if any("TITLE" in code for code in blocked_codes):
        return "TITLE_VALIDATION_FAILED"
    if any("PERSONA" in code or "STYLE" in code for code in blocked_codes):
        return "PERSONA_STYLE_FAILED"
    evidence_markers = ("EVIDENCE", "FACT", "NUMBER", "NUMERIC", "CITATION", "SOURCE")
    if any(any(marker in code for marker in evidence_markers) for code in blocked_codes):
        return "BODY_EVIDENCE_FAILED"
    return "BODY_STRUCTURE_FAILED"


__all__ = ["RevisionDecision", "RevisionRouteController", "resolve_revision_reason"]
