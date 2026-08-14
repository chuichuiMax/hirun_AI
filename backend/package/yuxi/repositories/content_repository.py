from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.storage.postgres.models_business import User
from yuxi.storage.postgres.models_content import (
    ContentAnalyticsEvent,
    ContentArtifact,
    ContentArtifactVersion,
    ContentCombinationRule,
    ContentFormula,
    ContentNodeRun,
    ContentReviewRecord,
    ContentRuleVersion,
    ContentTask,
    ContentWorkflowVersion,
    CreationMethod,
    IndustryTemplateVersion,
    TitleFormula,
)
from yuxi.utils.datetime_utils import format_utc_datetime, utc_now_naive


def _method_dict(item: CreationMethod) -> dict[str, Any]:
    return {
        "id": item.id,
        "code": item.code,
        "name": item.name,
        "method_type": item.method_type,
        "principle": item.principle,
        "suitable_scenes": item.suitable_scenes or [],
        "sentence_patterns": item.sentence_patterns or [],
        "tag_schema": item.tag_schema or {},
        "variable_schema": item.variable_schema or [],
        "risk_rules": item.risk_rules or [],
        "enabled": bool(item.enabled),
        "sort_order": item.sort_order,
    }


def _title_formula_dict(item: TitleFormula) -> dict[str, Any]:
    return {
        "id": item.id,
        "code": item.code,
        "name": item.name,
        "suitable_scenes": item.suitable_scenes or [],
        "core_goal": item.core_goal,
        "reference_examples": item.reference_examples or [],
        "variable_schema": item.variable_schema or [],
        "compatible_methods": item.compatible_methods or [],
        "risk_rules": item.risk_rules or [],
        "enabled": bool(item.enabled),
        "sort_order": item.sort_order,
    }


def _content_formula_dict(item: ContentFormula) -> dict[str, Any]:
    return {
        "id": item.id,
        "code": item.code,
        "name": item.name,
        "industry_aliases": item.industry_aliases or {},
        "compatible_methods": item.compatible_methods or [],
        "suitable_scenes": item.suitable_scenes or [],
        "business_pains": item.business_pains or [],
        "structure_schema": item.structure_schema or [],
        "reference_examples": item.reference_examples or [],
        "required_variables": item.required_variables or [],
        "output_schema": item.output_schema or {},
        "risk_rules": item.risk_rules or [],
        "enabled": bool(item.enabled),
        "sort_order": item.sort_order,
    }


def _combination_dict(item: ContentCombinationRule) -> dict[str, Any]:
    return {
        "id": item.id,
        "content_goal": item.content_goal,
        "methods": item.methods or [],
        "title_formula_codes": item.title_formula_codes or [],
        "content_formula_code": item.content_formula_code,
        "compatibility": item.compatibility,
        "priority": item.priority,
        "conditions": item.conditions or {},
        "recommendation_reason": item.recommendation_reason,
    }


def _template_dict(item: IndustryTemplateVersion) -> dict[str, Any]:
    return {
        "id": item.id,
        "slug": item.slug,
        "tenant_id": item.tenant_id,
        "version": item.version,
        "status": item.status,
        "name": item.name,
        "description": item.description,
        "icon": item.icon,
        "quick_form_schema": item.quick_form_schema or [],
        "pro_form_schema": item.pro_form_schema or [],
        "default_goal": item.default_goal,
        "default_strategy": item.default_strategy or {},
        "default_knowledge_scope": item.default_knowledge_scope or [],
        "default_workflow_version_id": item.default_workflow_version_id,
        "review_policy": item.review_policy or {},
        "published_at": format_utc_datetime(item.published_at),
    }


class ContentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_rule_version(self, version_id: str) -> ContentRuleVersion | None:
        result = await self.db.execute(select(ContentRuleVersion).where(ContentRuleVersion.id == version_id))
        return result.scalar_one_or_none()

    async def get_rule_version_for_update(self, version_id: str) -> ContentRuleVersion | None:
        result = await self.db.execute(
            select(ContentRuleVersion).where(ContentRuleVersion.id == version_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_published_rule_version(self) -> ContentRuleVersion | None:
        result = await self.db.execute(
            select(ContentRuleVersion)
            .where(ContentRuleVersion.status == "published", ContentRuleVersion.tenant_id.is_(None))
            .order_by(ContentRuleVersion.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_published_rule_version_for_update(self) -> ContentRuleVersion | None:
        result = await self.db.execute(
            select(ContentRuleVersion)
            .where(ContentRuleVersion.status == "published", ContentRuleVersion.tenant_id.is_(None))
            .order_by(ContentRuleVersion.version.desc())
            .limit(1)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_rule_bundle(self, version_id: str, *, include_disabled: bool = False) -> dict[str, Any] | None:
        version = await self.get_rule_version(version_id)
        if version is None:
            return None
        method_query = select(CreationMethod).where(CreationMethod.version_id == version_id)
        title_query = select(TitleFormula).where(TitleFormula.version_id == version_id)
        content_query = select(ContentFormula).where(ContentFormula.version_id == version_id)
        if not include_disabled:
            method_query = method_query.where(CreationMethod.enabled.is_(True))
            title_query = title_query.where(TitleFormula.enabled.is_(True))
            content_query = content_query.where(ContentFormula.enabled.is_(True))
        methods = (
            await self.db.execute(method_query.order_by(CreationMethod.sort_order))
        ).scalars()
        title_formulas = (
            await self.db.execute(title_query.order_by(TitleFormula.sort_order))
        ).scalars()
        content_formulas = (
            await self.db.execute(content_query.order_by(ContentFormula.sort_order))
        ).scalars()
        combinations = (
            await self.db.execute(
                select(ContentCombinationRule)
                .where(ContentCombinationRule.version_id == version_id)
                .order_by(ContentCombinationRule.priority.desc())
            )
        ).scalars()
        return {
            "version": {
                "id": version.id,
                "tenant_id": version.tenant_id,
                "version": version.version,
                "status": version.status,
                "changelog": version.changelog,
                "published_at": format_utc_datetime(version.published_at),
            },
            "methods": [_method_dict(item) for item in methods],
            "title_formulas": [_title_formula_dict(item) for item in title_formulas],
            "content_formulas": [_content_formula_dict(item) for item in content_formulas],
            "combination_rules": [_combination_dict(item) for item in combinations],
        }

    async def list_rule_versions(self) -> list[dict[str, Any]]:
        items = (
            await self.db.execute(select(ContentRuleVersion).order_by(ContentRuleVersion.version.desc()))
        ).scalars()
        return [
            {
                "id": item.id,
                "tenant_id": item.tenant_id,
                "version": item.version,
                "status": item.status,
                "changelog": item.changelog,
                "created_by": item.created_by,
                "created_at": format_utc_datetime(item.created_at),
                "published_at": format_utc_datetime(item.published_at),
            }
            for item in items
        ]

    async def get_platform_rule_draft(self) -> ContentRuleVersion | None:
        result = await self.db.execute(
            select(ContentRuleVersion)
            .where(ContentRuleVersion.status == "draft", ContentRuleVersion.tenant_id.is_(None))
            .order_by(ContentRuleVersion.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def next_platform_rule_version(self) -> int:
        current = await self.db.execute(
            select(func.coalesce(func.max(ContentRuleVersion.version), 0)).where(
                ContentRuleVersion.tenant_id.is_(None)
            )
        )
        return int(current.scalar_one()) + 1

    async def create_rule_version(
        self,
        *,
        version_id: str,
        version: int,
        changelog: str,
        created_by: str,
    ) -> ContentRuleVersion:
        item = ContentRuleVersion(
            id=version_id,
            tenant_id=None,
            version=version,
            status="draft",
            changelog=changelog,
            created_by=created_by,
        )
        self.db.add(item)
        await self.db.flush()
        return item

    async def replace_rule_bundle(self, version_id: str, bundle: dict[str, Any]) -> None:
        for model in (ContentCombinationRule, ContentFormula, TitleFormula, CreationMethod):
            await self.db.execute(delete(model).where(model.version_id == version_id))

        for sort_order, item in enumerate(bundle.get("methods") or []):
            self.db.add(
                CreationMethod(
                    id=f"crm_{uuid.uuid4().hex}",
                    version_id=version_id,
                    code=item["code"],
                    name=item["name"],
                    method_type=item["method_type"],
                    principle=item["principle"],
                    suitable_scenes=item.get("suitable_scenes") or [],
                    sentence_patterns=item.get("sentence_patterns") or [],
                    tag_schema=item.get("tag_schema") or {},
                    variable_schema=item.get("variable_schema") or [],
                    risk_rules=item.get("risk_rules") or [],
                    enabled=item.get("enabled", True),
                    sort_order=sort_order,
                )
            )
        for sort_order, item in enumerate(bundle.get("title_formulas") or []):
            self.db.add(
                TitleFormula(
                    id=f"ctf_{uuid.uuid4().hex}",
                    version_id=version_id,
                    code=item["code"],
                    name=item["name"],
                    suitable_scenes=item.get("suitable_scenes") or [],
                    core_goal=item["core_goal"],
                    reference_examples=item.get("reference_examples") or [],
                    variable_schema=item.get("variable_schema") or [],
                    compatible_methods=item.get("compatible_methods") or [],
                    risk_rules=item.get("risk_rules") or [],
                    enabled=item.get("enabled", True),
                    sort_order=sort_order,
                )
            )
        for sort_order, item in enumerate(bundle.get("content_formulas") or []):
            self.db.add(
                ContentFormula(
                    id=f"cbf_{uuid.uuid4().hex}",
                    version_id=version_id,
                    code=item["code"],
                    name=item["name"],
                    industry_aliases=item.get("industry_aliases") or {},
                    compatible_methods=item.get("compatible_methods") or [],
                    suitable_scenes=item.get("suitable_scenes") or [],
                    business_pains=item.get("business_pains") or [],
                    structure_schema=item.get("structure_schema") or [],
                    reference_examples=item.get("reference_examples") or [],
                    required_variables=item.get("required_variables") or [],
                    output_schema=item.get("output_schema") or {},
                    risk_rules=item.get("risk_rules") or [],
                    enabled=item.get("enabled", True),
                    sort_order=sort_order,
                )
            )
        for item in bundle.get("combination_rules") or []:
            self.db.add(
                ContentCombinationRule(
                    id=f"ccr_{uuid.uuid4().hex}",
                    version_id=version_id,
                    content_goal=item["content_goal"],
                    methods=item.get("methods") or [],
                    title_formula_codes=item.get("title_formula_codes") or [],
                    content_formula_code=item["content_formula_code"],
                    compatibility=item.get("compatibility", "compatible"),
                    priority=item.get("priority", 0),
                    conditions=item.get("conditions") or {},
                    recommendation_reason=item.get("recommendation_reason") or "",
                )
            )
        await self.db.flush()

    async def delete_rule_version(self, version_id: str) -> None:
        await self.db.execute(delete(ContentRuleVersion).where(ContentRuleVersion.id == version_id))
        await self.db.flush()

    async def get_template(self, template_id: str) -> IndustryTemplateVersion | None:
        result = await self.db.execute(
            select(IndustryTemplateVersion).where(IndustryTemplateVersion.id == template_id)
        )
        return result.scalar_one_or_none()

    async def list_templates(self, *, published_only: bool = True) -> list[dict[str, Any]]:
        query = select(IndustryTemplateVersion)
        if published_only:
            query = query.where(IndustryTemplateVersion.status == "published")
        items = (await self.db.execute(query.order_by(IndustryTemplateVersion.name))).scalars()
        return [_template_dict(item) for item in items]

    async def get_workflow(self, workflow_id: str) -> ContentWorkflowVersion | None:
        result = await self.db.execute(
            select(ContentWorkflowVersion).where(ContentWorkflowVersion.id == workflow_id)
        )
        return result.scalar_one_or_none()

    async def list_workflows(self, *, published_only: bool = False) -> list[dict[str, Any]]:
        query = select(ContentWorkflowVersion)
        if published_only:
            query = query.where(ContentWorkflowVersion.status == "published")
        items = (await self.db.execute(query.order_by(ContentWorkflowVersion.version.desc()))).scalars()
        return [
            {
                "id": item.id,
                "slug": item.slug,
                "tenant_id": item.tenant_id,
                "version": item.version,
                "status": item.status,
                "definition": item.definition_json or {},
                "published_at": format_utc_datetime(item.published_at),
            }
            for item in items
        ]

    async def create_task(
        self,
        *,
        task_id: str,
        user: User,
        name: str,
        template: IndustryTemplateVersion,
        rule_version_id: str,
        mode: str,
        content_goal: str,
        project_id: str | None,
    ) -> ContentTask:
        task = ContentTask(
            id=task_id,
            tenant_id=str(user.department_id) if user.department_id is not None else None,
            project_id=project_id,
            name=name,
            industry_template_version_id=template.id,
            workflow_version_id=template.default_workflow_version_id,
            rule_version_id=rule_version_id,
            mode=mode,
            content_goal=content_goal,
            status="draft",
            current_stage="brief",
            brief_json={},
            strategy_json={},
            evidence_json={"items": []},
            title_candidates_json=[],
            review_json={},
            created_by=str(user.uid),
            updated_by=str(user.uid),
        )
        self.db.add(task)
        await self.db.flush()
        return task

    async def get_task(self, task_id: str, *, for_update: bool = False) -> ContentTask | None:
        query = select(ContentTask).where(ContentTask.id == task_id, ContentTask.deleted_at.is_(None))
        if for_update:
            query = query.with_for_update()
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_task_for_user(self, task_id: str, user: User, *, for_update: bool = False) -> ContentTask | None:
        task = await self.get_task(task_id, for_update=for_update)
        if task is None:
            return None
        if user.role == "superadmin" or task.created_by == str(user.uid):
            return task
        if user.role == "admin" and task.tenant_id == str(user.department_id):
            return task
        return None

    async def list_tasks(
        self, *, user: User, page: int, page_size: int, status: str | None = None
    ) -> tuple[list[ContentTask], int]:
        filters = [ContentTask.deleted_at.is_(None)]
        if user.role == "admin":
            filters.append(ContentTask.tenant_id == str(user.department_id))
        elif user.role != "superadmin":
            filters.append(ContentTask.created_by == str(user.uid))
        if status:
            filters.append(ContentTask.status == status)
        total = (
            await self.db.execute(select(func.count(ContentTask.id)).where(*filters))
        ).scalar_one()
        items = (
            await self.db.execute(
                select(ContentTask)
                .where(*filters)
                .order_by(ContentTask.updated_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars()
        return list(items), int(total)

    async def get_artifact_for_task(self, task_id: str) -> ContentArtifact | None:
        result = await self.db.execute(select(ContentArtifact).where(ContentArtifact.task_id == task_id))
        return result.scalar_one_or_none()

    async def get_artifact(self, artifact_id: str) -> ContentArtifact | None:
        result = await self.db.execute(select(ContentArtifact).where(ContentArtifact.id == artifact_id))
        return result.scalar_one_or_none()

    async def get_artifact_for_user(self, artifact_id: str, user: User) -> ContentArtifact | None:
        artifact = await self.get_artifact(artifact_id)
        if artifact is None:
            return None
        task = await self.get_task_for_user(artifact.task_id, user)
        return artifact if task else None

    async def save_artifact_version(
        self,
        *,
        artifact: ContentArtifact,
        source_type: str,
        model_spec: str | None,
        skill_versions: dict[str, str],
        rule_version_id: str,
        knowledge_snapshot: dict[str, Any],
        review_snapshot: dict[str, Any],
        created_by: str,
    ) -> ContentArtifactVersion:
        version = ContentArtifactVersion(
            id=f"cav_{uuid.uuid4().hex}",
            artifact_id=artifact.id,
            version=artifact.current_version,
            title=artifact.title,
            body=artifact.body,
            topics=artifact.topics or [],
            source_type=source_type,
            model_spec=model_spec,
            skill_versions=skill_versions,
            rule_version_id=rule_version_id,
            knowledge_snapshot=knowledge_snapshot or {},
            review_snapshot=review_snapshot or {},
            created_by=created_by,
        )
        self.db.add(version)
        await self.db.flush()
        return version

    async def list_artifact_versions(self, artifact_id: str) -> list[dict[str, Any]]:
        items = (
            await self.db.execute(
                select(ContentArtifactVersion)
                .where(ContentArtifactVersion.artifact_id == artifact_id)
                .order_by(ContentArtifactVersion.version.desc())
            )
        ).scalars()
        return [
            {
                "id": item.id,
                "artifact_id": item.artifact_id,
                "version": item.version,
                "title": item.title,
                "body": item.body,
                "topics": item.topics or [],
                "source_type": item.source_type,
                "model_spec": item.model_spec,
                "skill_versions": item.skill_versions or {},
                "rule_version_id": item.rule_version_id,
                "knowledge_snapshot": item.knowledge_snapshot or {},
                "review_snapshot": item.review_snapshot or {},
                "created_by": item.created_by,
                "created_at": format_utc_datetime(item.created_at),
            }
            for item in items
        ]

    async def add_review_record(
        self,
        *,
        artifact_version_id: str,
        review_type: str,
        status: str,
        checks: list[dict[str, Any]],
        reviewer_uid: str | None,
    ) -> ContentReviewRecord:
        record = ContentReviewRecord(
            id=f"crr_{uuid.uuid4().hex}",
            artifact_version_id=artifact_version_id,
            review_type=review_type,
            status=status,
            checks=checks,
            reviewer_uid=reviewer_uid,
        )
        self.db.add(record)
        await self.db.flush()
        return record

    async def add_node_run(
        self,
        *,
        task_id: str,
        run_id: str,
        node_id: str,
        node_type: str,
        input_snapshot: dict[str, Any],
    ) -> ContentNodeRun:
        attempt_count = (
            await self.db.execute(
                select(func.count(ContentNodeRun.id)).where(
                    ContentNodeRun.task_id == task_id, ContentNodeRun.node_id == node_id
                )
            )
        ).scalar_one()
        item = ContentNodeRun(
            id=f"cnr_{uuid.uuid4().hex}",
            task_id=task_id,
            agent_run_id=run_id,
            node_id=node_id,
            node_type=node_type,
            status="running",
            attempt=int(attempt_count) + 1,
            input_snapshot=input_snapshot,
            started_at=utc_now_naive(),
        )
        self.db.add(item)
        await self.db.flush()
        return item

    async def finish_node_run(
        self,
        item: ContentNodeRun,
        *,
        status: str,
        output_snapshot: dict[str, Any] | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        item.status = status
        item.output_snapshot = output_snapshot or {}
        item.error_type = error_type
        item.error_message = error_message
        item.finished_at = utc_now_naive()
        await self.db.flush()

    async def track(
        self,
        event_name: str,
        *,
        uid: str,
        task_id: str | None = None,
        run_id: str | None = None,
        properties: dict[str, Any] | None = None,
    ) -> None:
        self.db.add(
            ContentAnalyticsEvent(
                id=f"cae_{uuid.uuid4().hex}",
                event_name=event_name,
                task_id=task_id,
                run_id=run_id,
                uid=uid,
                properties=properties or {},
            )
        )
        await self.db.flush()
