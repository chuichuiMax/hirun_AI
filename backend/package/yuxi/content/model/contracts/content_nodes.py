"""V3 Agent 节点的版本化输入、输出契约与一次性提交器。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LockedVersionsV1(StrictContract):
    industry_pack_version_id: str
    channel_profile_version_id: str
    persona_profile_version_id: str | None
    rule_version_id: str
    title_formula_code: str | None
    body_formula_code: str | None
    artifact_version_id: str | None


class ContentAgentNodeInputV1(StrictContract):
    task_id: str
    parent_run_id: str
    node_id: str
    attempt: int = Field(ge=1)
    content_brief: dict[str, Any]
    runtime_config_snapshot: dict[str, Any]
    match_decision_snapshot: dict[str, Any]
    formula_selection_snapshot: dict[str, Any]
    evidence_bundle: dict[str, Any]
    evidence_bundle_hash: str
    locked_versions: LockedVersionsV1
    locked_values: dict[str, Any]
    node_responsibility: str
    prohibited_actions: list[str]
    output_json_schema: dict[str, Any]


class DirectionCandidateV1(StrictContract):
    direction_code: Literal["CT01", "CT02", "CT03", "CT04", "CT05", "CT06", "CT07"]
    reason: str
    evidence_ids: list[str]


class ContentValueResultV1(StrictContract):
    value_points: list[str] = Field(min_length=1)
    direction_candidates: list[DirectionCandidateV1] = Field(min_length=1)
    reasoning: str
    evidence_ids: list[str]


class StrategyExplanationResultV1(StrictContract):
    locked_group_id: str
    explanation: str
    risks: list[str]
    evidence_ids: list[str]


class EvidenceDraftV1(StrictContract):
    id: str
    variable_codes: list[str]
    value: Any
    source_type: Literal["manual_input", "business_record", "media", "knowledge_base", "human_confirmation"]
    source_id: str
    source_version: str
    verified_status: Literal["retrieved", "confirmed", "user_confirmed"]
    allowed_usage: list[Literal["title", "body", "visual"]]
    risk_level: Literal["normal", "sensitive", "high_risk"]
    source_hash: str


class EvidenceCollectionResultV1(StrictContract):
    evidence_items: list[EvidenceDraftV1]
    citations: list[str]
    unresolved_questions: list[str]


class RankedFormulaV1(StrictContract):
    formula_code: str
    reason: str


class FormulaRankingResultV1(StrictContract):
    title_rankings: list[RankedFormulaV1] = Field(min_length=1)
    body_rankings: list[RankedFormulaV1] = Field(min_length=1)


class TitleCandidateV1(StrictContract):
    id: str
    text: str
    formula_code: str
    evidence_ids: list[str]
    reason: str


class TitleCandidatesResultV1(StrictContract):
    candidates: list[TitleCandidateV1] = Field(min_length=2)
    selected_title_formula_code: str
    evidence_ids: list[str]


class OutlineSectionV1(StrictContract):
    section_id: str
    goal: str
    evidence_ids: list[str]


class OutlineResultV1(StrictContract):
    body_formula_code: str
    sections: list[OutlineSectionV1] = Field(min_length=1)


class ParagraphEvidenceV1(StrictContract):
    paragraph_id: str
    evidence_ids: list[str]


class ContentDraftResultV1(StrictContract):
    body: str
    topics: list[str]
    paragraph_evidence: list[ParagraphEvidenceV1]
    body_formula_code: str


class PreservedFactCheckV1(StrictContract):
    evidence_id: str
    preserved: bool


class PersonaPolishResultV1(StrictContract):
    polished_body: str
    change_summary: list[str]
    preserved_fact_checks: list[PreservedFactCheckV1]


class ReviewCheckV1(StrictContract):
    code: str
    status: Literal["passed", "warning", "blocked"]
    message: str
    evidence_ids: list[str]


class ContentReviewResultV1(StrictContract):
    status: Literal["passed", "warning", "blocked"]
    checks: list[ReviewCheckV1]
    evidence_conflicts: list[str]


class VisualSizeV1(StrictContract):
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class SafeAreaV1(StrictContract):
    top: int = Field(ge=0)
    right: int = Field(ge=0)
    bottom: int = Field(ge=0)
    left: int = Field(ge=0)


class VisualPlanResultV1(StrictContract):
    size: VisualSizeV1
    safe_area: SafeAreaV1
    text: list[str]
    source_asset_ids: list[str]
    mode: Literal["template", "generated", "mixed"]
    risks: list[str]
    artifact_version_id: str
    evidence_ids: list[str]


class CoverJobSubmissionResultV1(StrictContract):
    cover_job_id: str
    plan_hash: str
    source_asset_ids: list[str]


class AssetReviewV1(StrictContract):
    asset_id: str
    status: Literal["passed", "warning", "blocked"]
    issues: list[str]


class VisualReviewResultV1(StrictContract):
    assets: list[AssetReviewV1] = Field(min_length=1)
    status: Literal["passed", "warning", "blocked"]
    recommended_asset_id: str | None


CONTRACT_REGISTRY: dict[str, type[StrictContract]] = {
    model.__name__: model
    for model in (
        ContentValueResultV1,
        StrategyExplanationResultV1,
        EvidenceCollectionResultV1,
        FormulaRankingResultV1,
        TitleCandidatesResultV1,
        OutlineResultV1,
        ContentDraftResultV1,
        PersonaPolishResultV1,
        ContentReviewResultV1,
        VisualPlanResultV1,
        CoverJobSubmissionResultV1,
        VisualReviewResultV1,
    )
}


class ContractDomainValidationError(ValueError):
    def __init__(self, code: str, field_path: str, message: str):
        super().__init__(message)
        self.code = code
        self.field_path = field_path


def _extract_supported_numbers(value: Any) -> set[str]:
    if value is None or isinstance(value, bool):
        return set()
    if isinstance(value, (int, float)):
        return {str(value)}
    if isinstance(value, str):
        return set(re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?", value))
    if isinstance(value, dict):
        return set().union(*(_extract_supported_numbers(item) for item in value.values()))
    if isinstance(value, (list, tuple, set)):
        return set().union(*(_extract_supported_numbers(item) for item in value))
    return set()


@dataclass(frozen=True, slots=True)
class ContractDomainContext:
    locked_group_id: str | None = None
    title_formula_pool: frozenset[str] = frozenset()
    body_formula_pool: frozenset[str] = frozenset()
    locked_title_formula_code: str | None = None
    locked_body_formula_code: str | None = None
    allowed_evidence_by_usage: dict[str, frozenset[str]] = field(default_factory=dict)
    allowed_asset_ids: frozenset[str] = frozenset()
    locked_title: str | None = None
    artifact_version_id: str | None = None
    visual_plan_hash: str | None = None
    allowed_numbers: frozenset[str] = frozenset()

    @classmethod
    def from_node_input(cls, node_input: ContentAgentNodeInputV1) -> ContractDomainContext:
        evidence_by_usage: dict[str, set[str]] = {"title": set(), "body": set(), "visual": set(), "any": set()}
        allowed_numbers: set[str] = set()
        for item in node_input.evidence_bundle.get("items") or []:
            if not isinstance(item, dict) or not item.get("id") or item.get("verified_status") == "rejected":
                continue
            evidence_id = str(item["id"])
            evidence_by_usage["any"].add(evidence_id)
            for usage in item.get("allowed_usage") or []:
                if usage in evidence_by_usage:
                    evidence_by_usage[usage].add(evidence_id)
            allowed_numbers.update(_extract_supported_numbers(item.get("value")))
            for number in item.get("numbers") or []:
                allowed_numbers.add(str(number))
        formula = node_input.formula_selection_snapshot
        match = node_input.match_decision_snapshot
        locks = node_input.locked_values
        return cls(
            locked_group_id=match.get("selected_group_id") or formula.get("combination_group_id"),
            title_formula_pool=frozenset(
                match.get("eligible_title_formula_codes") or formula.get("eligible_title_formula_codes") or []
            ),
            body_formula_pool=frozenset(
                match.get("eligible_body_formula_codes") or formula.get("eligible_body_formula_codes") or []
            ),
            locked_title_formula_code=(
                formula.get("selected_title_formula_code") or node_input.locked_versions.title_formula_code
            ),
            locked_body_formula_code=(
                formula.get("selected_body_formula_code") or node_input.locked_versions.body_formula_code
            ),
            allowed_evidence_by_usage={key: frozenset(value) for key, value in evidence_by_usage.items()},
            allowed_asset_ids=frozenset(locks.get("source_asset_ids") or []),
            locked_title=locks.get("selected_title"),
            artifact_version_id=node_input.locked_versions.artifact_version_id,
            visual_plan_hash=locks.get("visual_plan_hash"),
            allowed_numbers=frozenset(allowed_numbers),
        )


def get_contract_model(name: str) -> type[StrictContract]:
    model = CONTRACT_REGISTRY.get(name)
    if model is None:
        raise ContractDomainValidationError("contract_unknown", "output_contract", f"未知输出契约: {name}")
    return model


def _require_member(value: str, allowed: frozenset[str], field_path: str) -> None:
    if value not in allowed:
        raise ContractDomainValidationError("unknown_id", field_path, f"{field_path} 不在锁定候选范围内: {value}")


def _require_equal(value: str | None, locked: str | None, field_path: str) -> None:
    if not locked or value != locked:
        raise ContractDomainValidationError("locked_value_changed", field_path, f"{field_path} 必须等于锁定值")


def _validate_evidence_ids(ids: list[str], usage: str, context: ContractDomainContext, field_path: str) -> None:
    allowed = context.allowed_evidence_by_usage.get(usage, frozenset())
    unknown = sorted(set(ids) - set(allowed))
    if unknown:
        raise ContractDomainValidationError(
            "evidence_forbidden",
            field_path,
            f"{field_path} 引用了未授权 Evidence ID: {', '.join(unknown)}",
        )


def _validate_numbers(text: str, context: ContractDomainContext, field_path: str) -> None:
    numbers = set(re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?", text))
    unknown = sorted(numbers - set(context.allowed_numbers))
    if unknown:
        raise ContractDomainValidationError(
            "unsupported_number", field_path, f"{field_path} 含有无证据数字: {', '.join(unknown)}"
        )


def validate_content_node_result(
    contract_name: str,
    payload: dict[str, Any],
    context: ContractDomainContext,
) -> StrictContract:
    result = get_contract_model(contract_name).model_validate(payload)
    if isinstance(result, ContentValueResultV1):
        _validate_evidence_ids(result.evidence_ids, "any", context, "evidence_ids")
        for index, item in enumerate(result.direction_candidates):
            _validate_evidence_ids(item.evidence_ids, "any", context, f"direction_candidates.{index}.evidence_ids")
    elif isinstance(result, StrategyExplanationResultV1):
        _require_equal(result.locked_group_id, context.locked_group_id, "locked_group_id")
        _validate_evidence_ids(result.evidence_ids, "any", context, "evidence_ids")
    elif isinstance(result, EvidenceCollectionResultV1):
        new_ids = [item.id for item in result.evidence_items]
        if len(new_ids) != len(set(new_ids)):
            raise ContractDomainValidationError("duplicate_id", "evidence_items", "新 Evidence ID 不能重复")
    elif isinstance(result, FormulaRankingResultV1):
        for index, item in enumerate(result.title_rankings):
            _require_member(item.formula_code, context.title_formula_pool, f"title_rankings.{index}.formula_code")
        for index, item in enumerate(result.body_rankings):
            _require_member(item.formula_code, context.body_formula_pool, f"body_rankings.{index}.formula_code")
    elif isinstance(result, TitleCandidatesResultV1):
        _require_equal(
            result.selected_title_formula_code,
            context.locked_title_formula_code,
            "selected_title_formula_code",
        )
        _validate_evidence_ids(result.evidence_ids, "title", context, "evidence_ids")
        for index, item in enumerate(result.candidates):
            _require_equal(item.formula_code, context.locked_title_formula_code, f"candidates.{index}.formula_code")
            _validate_evidence_ids(item.evidence_ids, "title", context, f"candidates.{index}.evidence_ids")
            _validate_numbers(item.text, context, f"candidates.{index}.text")
    elif isinstance(result, OutlineResultV1):
        _require_equal(result.body_formula_code, context.locked_body_formula_code, "body_formula_code")
        for index, item in enumerate(result.sections):
            _validate_evidence_ids(item.evidence_ids, "body", context, f"sections.{index}.evidence_ids")
    elif isinstance(result, ContentDraftResultV1):
        _require_equal(result.body_formula_code, context.locked_body_formula_code, "body_formula_code")
        for index, item in enumerate(result.paragraph_evidence):
            _validate_evidence_ids(item.evidence_ids, "body", context, f"paragraph_evidence.{index}.evidence_ids")
        _validate_numbers("\n".join([result.body, *result.topics]), context, "body")
    elif isinstance(result, PersonaPolishResultV1):
        for index, item in enumerate(result.preserved_fact_checks):
            _validate_evidence_ids([item.evidence_id], "body", context, f"preserved_fact_checks.{index}.evidence_id")
            if not item.preserved:
                raise ContractDomainValidationError(
                    "fact_changed", f"preserved_fact_checks.{index}.preserved", "人设润色不得改变事实"
                )
        _validate_numbers(result.polished_body, context, "polished_body")
    elif isinstance(result, ContentReviewResultV1):
        for index, item in enumerate(result.checks):
            _validate_evidence_ids(item.evidence_ids, "body", context, f"checks.{index}.evidence_ids")
    elif isinstance(result, VisualPlanResultV1):
        _require_equal(result.artifact_version_id, context.artifact_version_id, "artifact_version_id")
        for index, asset_id in enumerate(result.source_asset_ids):
            _require_member(asset_id, context.allowed_asset_ids, f"source_asset_ids.{index}")
        _validate_evidence_ids(result.evidence_ids, "visual", context, "evidence_ids")
        _validate_numbers("\n".join(result.text), context, "text")
    elif isinstance(result, CoverJobSubmissionResultV1):
        _require_equal(result.plan_hash, context.visual_plan_hash, "plan_hash")
        for index, asset_id in enumerate(result.source_asset_ids):
            _require_member(asset_id, context.allowed_asset_ids, f"source_asset_ids.{index}")
    elif isinstance(result, VisualReviewResultV1):
        for index, item in enumerate(result.assets):
            _require_member(item.asset_id, context.allowed_asset_ids, f"assets.{index}.asset_id")
        if result.recommended_asset_id is not None:
            _require_member(result.recommended_asset_id, context.allowed_asset_ids, "recommended_asset_id")
    return result


@dataclass(slots=True)
class ContentNodeResultCollector:
    contract_name: str
    domain_context: ContractDomainContext
    runtime_context: Any
    submission_count: int = 0
    result: dict[str, Any] | None = None

    async def submit(self, **payload: Any) -> dict[str, Any]:
        from yuxi.services.run_queue_service import append_content_runtime_event

        event_payload = {
            "tool_name": "submit_content_node_result",
            "output_contract": self.contract_name,
        }
        await append_content_runtime_event(
            self.runtime_context,
            "content.tool.called",
            event_payload,
        )
        try:
            if self.submission_count:
                raise ContractDomainValidationError(
                    "duplicate_submission", "submit_content_node_result", "Agent 节点结果只能提交一次"
                )
            required = set(getattr(self.runtime_context, "_required_skill_closure", []) or [])
            activated = set(getattr(self.runtime_context, "_activated_required_skills", []) or [])
            if not required.issubset(activated):
                raise ContractDomainValidationError(
                    "required_skill_not_activated", "required_skills", "未激活全部必需 Skills，禁止提交"
                )
            self.submission_count += 1
            validated = validate_content_node_result(self.contract_name, payload, self.domain_context)
            self.result = validated.model_dump(mode="json")
        except Exception as exc:
            await append_content_runtime_event(
                self.runtime_context,
                "content.tool.failed",
                {**event_payload, "error_type": type(exc).__name__},
            )
            raise
        await append_content_runtime_event(
            self.runtime_context,
            "content.tool.completed",
            event_payload,
        )
        return {"accepted": True, "contract": self.contract_name}

    def finalize(self) -> dict[str, Any]:
        if self.submission_count != 1 or self.result is None:
            raise ContractDomainValidationError(
                "result_not_submitted", "submit_content_node_result", "Agent 未通过结构化结果工具提交结果"
            )
        return self.result


def build_content_result_tool(collector: ContentNodeResultCollector) -> StructuredTool:
    async def submit_content_node_result(**payload: Any) -> dict[str, Any]:
        return await collector.submit(**payload)

    return StructuredTool.from_function(
        coroutine=submit_content_node_result,
        name="submit_content_node_result",
        description=f"仅用于提交当前节点的 {collector.contract_name} 结果，必须且只能调用一次。",
        args_schema=get_contract_model(collector.contract_name),
        infer_schema=False,
    )


__all__ = [
    "CONTRACT_REGISTRY",
    "ContentAgentNodeInputV1",
    "ContentNodeResultCollector",
    "ContractDomainContext",
    "ContractDomainValidationError",
    "build_content_result_tool",
    "get_contract_model",
    "validate_content_node_result",
]
