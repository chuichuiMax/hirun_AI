from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


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


class RuleVersionAction(BaseModel):
    note: str | None = None


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
