"""通用内容策略工作台业务模型。"""

from typing import Any

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint

from yuxi.storage.postgres.models_business import Base
from yuxi.utils.datetime_utils import format_utc_datetime, utc_now_naive


class ContentRuleVersion(Base):
    __tablename__ = "content_rule_versions"

    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=True, index=True)
    version = Column(Integer, nullable=False)
    status = Column(String(32), nullable=False, default="draft", index=True)
    changelog = Column(Text, nullable=True)
    created_by = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=utc_now_naive)
    published_at = Column(DateTime, nullable=True)

    __table_args__ = (UniqueConstraint("tenant_id", "version", name="uq_content_rule_versions_tenant_version"),)


class CreationMethod(Base):
    __tablename__ = "content_creation_methods"

    id = Column(String(64), primary_key=True)
    version_id = Column(
        String(64), ForeignKey("content_rule_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code = Column(String(32), nullable=False)
    name = Column(String(80), nullable=False)
    method_type = Column(String(32), nullable=False, default="core")
    principle = Column(Text, nullable=False)
    suitable_scenes = Column(JSON, nullable=False, default=list)
    sentence_patterns = Column(JSON, nullable=False, default=list)
    tag_schema = Column(JSON, nullable=False, default=dict)
    variable_schema = Column(JSON, nullable=False, default=list)
    risk_rules = Column(JSON, nullable=False, default=list)
    enabled = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0)

    __table_args__ = (UniqueConstraint("version_id", "code", name="uq_content_creation_methods_version_code"),)


class TitleFormula(Base):
    __tablename__ = "content_title_formulas"

    id = Column(String(64), primary_key=True)
    version_id = Column(
        String(64), ForeignKey("content_rule_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code = Column(String(32), nullable=False)
    name = Column(String(120), nullable=False)
    suitable_scenes = Column(JSON, nullable=False, default=list)
    core_goal = Column(Text, nullable=False)
    reference_examples = Column(JSON, nullable=False, default=list)
    variable_schema = Column(JSON, nullable=False, default=list)
    compatible_methods = Column(JSON, nullable=False, default=list)
    risk_rules = Column(JSON, nullable=False, default=list)
    enabled = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0)

    __table_args__ = (UniqueConstraint("version_id", "code", name="uq_content_title_formulas_version_code"),)


class ContentFormula(Base):
    __tablename__ = "content_body_formulas"

    id = Column(String(64), primary_key=True)
    version_id = Column(
        String(64), ForeignKey("content_rule_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code = Column(String(32), nullable=False)
    name = Column(String(120), nullable=False)
    industry_aliases = Column(JSON, nullable=False, default=dict)
    compatible_methods = Column(JSON, nullable=False, default=list)
    suitable_scenes = Column(JSON, nullable=False, default=list)
    business_pains = Column(JSON, nullable=False, default=list)
    structure_schema = Column(JSON, nullable=False, default=list)
    reference_examples = Column(JSON, nullable=False, default=list)
    required_variables = Column(JSON, nullable=False, default=list)
    output_schema = Column(JSON, nullable=False, default=dict)
    risk_rules = Column(JSON, nullable=False, default=list)
    enabled = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0)

    __table_args__ = (UniqueConstraint("version_id", "code", name="uq_content_body_formulas_version_code"),)


class ContentCombinationRule(Base):
    __tablename__ = "content_combination_rules"

    id = Column(String(64), primary_key=True)
    version_id = Column(
        String(64), ForeignKey("content_rule_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content_goal = Column(String(64), nullable=False, index=True)
    methods = Column(JSON, nullable=False, default=list)
    title_formula_codes = Column(JSON, nullable=False, default=list)
    content_formula_code = Column(String(32), nullable=False)
    compatibility = Column(String(32), nullable=False, default="compatible")
    priority = Column(Integer, nullable=False, default=0)
    conditions = Column(JSON, nullable=False, default=dict)
    recommendation_reason = Column(Text, nullable=False, default="")


class ContentWorkflowVersion(Base):
    __tablename__ = "content_workflow_versions"

    id = Column(String(64), primary_key=True)
    slug = Column(String(80), nullable=False, index=True)
    tenant_id = Column(String(64), nullable=True, index=True)
    version = Column(Integer, nullable=False)
    status = Column(String(32), nullable=False, default="draft", index=True)
    definition_json = Column(JSON, nullable=False, default=dict)
    input_schema = Column(JSON, nullable=False, default=dict)
    output_schema = Column(JSON, nullable=False, default=dict)
    created_by = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=utc_now_naive)
    published_at = Column(DateTime, nullable=True)

    __table_args__ = (UniqueConstraint("tenant_id", "slug", "version", name="uq_content_workflow_version"),)


class IndustryTemplateVersion(Base):
    __tablename__ = "content_industry_template_versions"

    id = Column(String(64), primary_key=True)
    slug = Column(String(80), nullable=False, index=True)
    tenant_id = Column(String(64), nullable=True, index=True)
    version = Column(Integer, nullable=False)
    status = Column(String(32), nullable=False, default="draft", index=True)
    name = Column(String(120), nullable=False)
    description = Column(Text, nullable=False, default="")
    icon = Column(String(64), nullable=True)
    quick_form_schema = Column(JSON, nullable=False, default=list)
    pro_form_schema = Column(JSON, nullable=False, default=list)
    default_goal = Column(String(64), nullable=False, default="acquire")
    default_strategy = Column(JSON, nullable=False, default=dict)
    default_knowledge_scope = Column(JSON, nullable=False, default=list)
    default_workflow_version_id = Column(
        String(64), ForeignKey("content_workflow_versions.id", ondelete="RESTRICT"), nullable=False
    )
    review_policy = Column(JSON, nullable=False, default=dict)
    created_by = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=utc_now_naive)
    published_at = Column(DateTime, nullable=True)

    __table_args__ = (UniqueConstraint("tenant_id", "slug", "version", name="uq_content_industry_template_version"),)


class ContentTask(Base):
    __tablename__ = "content_tasks"

    id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=True, index=True)
    project_id = Column(String(64), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    industry_template_version_id = Column(
        String(64), ForeignKey("content_industry_template_versions.id", ondelete="RESTRICT"), nullable=False
    )
    workflow_version_id = Column(
        String(64), ForeignKey("content_workflow_versions.id", ondelete="RESTRICT"), nullable=False
    )
    rule_version_id = Column(String(64), ForeignKey("content_rule_versions.id", ondelete="RESTRICT"), nullable=False)
    mode = Column(String(32), nullable=False, default="quick")
    content_goal = Column(String(64), nullable=False, default="acquire")
    status = Column(String(32), nullable=False, default="draft", index=True)
    current_stage = Column(String(32), nullable=False, default="brief", index=True)
    brief_json = Column(JSON, nullable=False, default=dict)
    strategy_json = Column(JSON, nullable=False, default=dict)
    evidence_json = Column(JSON, nullable=False, default=dict)
    title_candidates_json = Column(JSON, nullable=False, default=list)
    selected_title_json = Column(JSON, nullable=True)
    review_json = Column(JSON, nullable=False, default=dict)
    latest_run_id = Column(String(64), nullable=True, index=True)
    error_json = Column(JSON, nullable=True)
    created_by = Column(String(64), nullable=False, index=True)
    updated_by = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=utc_now_naive, index=True)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)
    deleted_at = Column(DateTime, nullable=True, index=True)

    __table_args__ = (
        Index("idx_content_tasks_owner_updated", "created_by", "updated_at"),
        Index("idx_content_tasks_tenant_updated", "tenant_id", "updated_at"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "name": self.name,
            "industry_template_version_id": self.industry_template_version_id,
            "workflow_version_id": self.workflow_version_id,
            "rule_version_id": self.rule_version_id,
            "mode": self.mode,
            "content_goal": self.content_goal,
            "status": self.status,
            "current_stage": self.current_stage,
            "brief": self.brief_json or {},
            "strategy": self.strategy_json or {},
            "evidence_bundle": self.evidence_json or {},
            "title_candidates": self.title_candidates_json or [],
            "selected_title": self.selected_title_json,
            "review": self.review_json or {},
            "latest_run_id": self.latest_run_id,
            "error": self.error_json,
            "created_by": self.created_by,
            "updated_by": self.updated_by,
            "created_at": format_utc_datetime(self.created_at),
            "updated_at": format_utc_datetime(self.updated_at),
        }


class ContentNodeRun(Base):
    __tablename__ = "content_node_runs"

    id = Column(String(64), primary_key=True)
    task_id = Column(String(64), ForeignKey("content_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_run_id = Column(String(64), nullable=False, index=True)
    node_id = Column(String(80), nullable=False)
    node_type = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="pending", index=True)
    attempt = Column(Integer, nullable=False, default=1)
    input_snapshot = Column(JSON, nullable=False, default=dict)
    output_snapshot = Column(JSON, nullable=False, default=dict)
    error_type = Column(String(80), nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    __table_args__ = (Index("idx_content_node_runs_task_node", "task_id", "node_id", "attempt"),)


class ContentArtifact(Base):
    __tablename__ = "content_artifacts"

    id = Column(String(64), primary_key=True)
    task_id = Column(String(64), ForeignKey("content_tasks.id", ondelete="CASCADE"), nullable=False, unique=True)
    tenant_id = Column(String(64), nullable=True, index=True)
    status = Column(String(32), nullable=False, default="draft", index=True)
    current_version = Column(Integer, nullable=False, default=1)
    title = Column(Text, nullable=False)
    body = Column(Text, nullable=False)
    topics = Column(JSON, nullable=False, default=list)
    strategy_snapshot = Column(JSON, nullable=False, default=dict)
    evidence_snapshot = Column(JSON, nullable=False, default=dict)
    review_snapshot = Column(JSON, nullable=False, default=dict)
    created_by = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "tenant_id": self.tenant_id,
            "status": self.status,
            "current_version": self.current_version,
            "title": self.title,
            "body": self.body,
            "topics": self.topics or [],
            "strategy_snapshot": self.strategy_snapshot or {},
            "evidence_snapshot": self.evidence_snapshot or {},
            "review_snapshot": self.review_snapshot or {},
            "created_by": self.created_by,
            "created_at": format_utc_datetime(self.created_at),
            "updated_at": format_utc_datetime(self.updated_at),
        }


class ContentArtifactVersion(Base):
    __tablename__ = "content_artifact_versions"

    id = Column(String(64), primary_key=True)
    artifact_id = Column(String(64), ForeignKey("content_artifacts.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    title = Column(Text, nullable=False)
    body = Column(Text, nullable=False)
    topics = Column(JSON, nullable=False, default=list)
    source_type = Column(String(32), nullable=False, default="generated")
    model_spec = Column(String(255), nullable=True)
    skill_versions = Column(JSON, nullable=False, default=dict)
    rule_version_id = Column(String(64), nullable=False)
    knowledge_snapshot = Column(JSON, nullable=False, default=dict)
    review_snapshot = Column(JSON, nullable=False, default=dict)
    created_by = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=utc_now_naive)

    __table_args__ = (UniqueConstraint("artifact_id", "version", name="uq_content_artifact_version"),)


class ContentReviewRecord(Base):
    __tablename__ = "content_review_records"

    id = Column(String(64), primary_key=True)
    artifact_version_id = Column(
        String(64), ForeignKey("content_artifact_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    review_type = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False)
    checks = Column(JSON, nullable=False, default=list)
    reviewer_uid = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=utc_now_naive)


class ContentAnalyticsEvent(Base):
    __tablename__ = "content_analytics_events"

    id = Column(String(64), primary_key=True)
    event_name = Column(String(80), nullable=False, index=True)
    task_id = Column(String(64), nullable=True, index=True)
    run_id = Column(String(64), nullable=True, index=True)
    uid = Column(String(64), nullable=False, index=True)
    properties = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=utc_now_naive, index=True)
