from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ContentMode = Literal["quick", "pro"]


class ContentTaskCreate(BaseModel):
    industry_template_id: str
    mode: ContentMode = "quick"
    content_goal: str | None = None
    name: str | None = None
    project_id: str | None = None


class ContentTaskUpdate(BaseModel):
    name: str | None = None
    content_goal: str | None = None
    mode: ContentMode | None = None


class ContentBriefPayload(BaseModel):
    brand: dict[str, Any] = Field(default_factory=dict)
    audience: list[str] = Field(default_factory=list)
    business_variables: dict[str, Any] = Field(default_factory=dict)
    persona: dict[str, Any] = Field(default_factory=dict)
    required_terms: list[str] = Field(default_factory=list)
    forbidden_terms: list[str] = Field(default_factory=list)
    knowledge_scope: list[str] = Field(default_factory=list)
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    locked_fields: list[str] = Field(default_factory=list)
    form_values: dict[str, Any] = Field(default_factory=dict)


class ContentBriefSave(BaseModel):
    brief: ContentBriefPayload


class StrategySelection(BaseModel):
    methods: list[str]
    scene_enhancer: str | None = None
    title_formula_code: str
    content_formula_code: str


class StrategyValidateRequest(StrategySelection):
    rule_version_id: str
    content_goal: str
    brief: ContentBriefPayload


class ContentRunCreate(BaseModel):
    request_id: str
    model_spec: str | None = None


class ContentRunResume(BaseModel):
    request_id: str
    resume: dict[str, Any]


class ContentNodeRetry(BaseModel):
    request_id: str
    node_id: str | None = None
    model_spec: str | None = None


class ContentArtifactUpdate(BaseModel):
    title: str
    body: str
    topics: list[str] = Field(default_factory=list)


class ContentArtifactReview(BaseModel):
    model_spec: str | None = None


class ContentArtifactRegenerate(BaseModel):
    request_id: str
    scope: Literal["titles", "body", "topics", "all"] = "body"
    model_spec: str | None = None


class ContentFinalizeRequest(BaseModel):
    note: str | None = None


class XiaohongshuAccountCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    display_name: str = Field(min_length=1, max_length=120)


class XiaohongshuAccountUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    enabled: bool | None = None


class XiaohongshuDistributionCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    request_id: str = Field(min_length=8, max_length=120)
    account_ids: list[str] = Field(min_length=1, max_length=20)
    mode: Literal["draft", "publish"] = "draft"
    title: str | None = Field(default=None, min_length=1, max_length=20)
    body: str | None = Field(default=None, min_length=1, max_length=1000)
    topics: list[str] | None = Field(default=None, max_length=10)
    confirm_publish: bool = False


class RuleVersionAction(BaseModel):
    note: str | None = None


class RuleInputBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)


class RuleDraftCreate(RuleInputBase):
    source_version_id: str
    changelog: str = Field(default="", max_length=1000)


class CreationMethodInput(RuleInputBase):
    code: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=80)
    method_type: Literal["core", "enhancer"] = "core"
    principle: str = Field(min_length=1, max_length=4000)
    suitable_scenes: list[str] = Field(default_factory=list)
    sentence_patterns: list[str] = Field(default_factory=list)
    tag_schema: dict[str, Any] = Field(default_factory=dict)
    variable_schema: list[str] = Field(default_factory=list)
    risk_rules: list[str] = Field(default_factory=list)
    enabled: bool = True
    sort_order: int = Field(default=0, ge=0)


class TitleFormulaInput(RuleInputBase):
    code: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=120)
    suitable_scenes: list[str] = Field(default_factory=list)
    core_goal: str = Field(min_length=1, max_length=4000)
    reference_examples: list[str] = Field(default_factory=list)
    variable_schema: list[str] = Field(default_factory=list)
    compatible_methods: list[str] = Field(default_factory=list)
    risk_rules: list[str] = Field(default_factory=list)
    enabled: bool = True
    sort_order: int = Field(default=0, ge=0)


class ContentFormulaInput(RuleInputBase):
    code: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=120)
    industry_aliases: dict[str, str] = Field(default_factory=dict)
    compatible_methods: list[str] = Field(default_factory=list)
    suitable_scenes: list[str] = Field(default_factory=list)
    business_pains: list[str] = Field(default_factory=list)
    structure_schema: list[str] = Field(default_factory=list)
    reference_examples: list[str] = Field(default_factory=list)
    required_variables: list[str] = Field(default_factory=list)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    risk_rules: list[str] = Field(default_factory=list)
    enabled: bool = True
    sort_order: int = Field(default=0, ge=0)


class CombinationRuleInput(RuleInputBase):
    content_goal: str = Field(min_length=1, max_length=64)
    methods: list[str] = Field(default_factory=list)
    title_formula_codes: list[str] = Field(default_factory=list)
    content_formula_code: str = Field(min_length=1, max_length=32)
    compatibility: Literal["compatible", "warning"] = "compatible"
    priority: int = Field(default=0, ge=0, le=10000)
    conditions: dict[str, Any] = Field(default_factory=dict)
    recommendation_reason: str = Field(default="", max_length=4000)


class RuleBundleUpdate(RuleInputBase):
    changelog: str = Field(default="", max_length=1000)
    methods: list[CreationMethodInput] = Field(default_factory=list, max_length=200)
    title_formulas: list[TitleFormulaInput] = Field(default_factory=list, max_length=500)
    content_formulas: list[ContentFormulaInput] = Field(default_factory=list, max_length=500)
    combination_rules: list[CombinationRuleInput] = Field(default_factory=list, max_length=1000)


class TitleCandidate(BaseModel):
    id: str
    text: str
    formula_code: str
    variable_mapping: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)


class GeneratedContent(BaseModel):
    body: str
    topics: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class ReviewCheck(BaseModel):
    code: str
    level: Literal["info", "warning", "error"]
    location: str
    message: str
    evidence_ids: list[str] = Field(default_factory=list)
    suggestion: str | None = None


class ReviewReport(BaseModel):
    status: Literal["passed", "warning", "blocked"]
    checks: list[ReviewCheck] = Field(default_factory=list)
