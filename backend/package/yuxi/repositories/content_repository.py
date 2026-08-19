from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.storage.postgres.models_business import User
from yuxi.storage.postgres.models_content import (
    ChannelProfile,
    ChannelProfileVersion,
    CompliancePolicyVersion,
    ContentAnalyticsEvent,
    ContentArtifact,
    ContentArtifactVersion,
    ContentCombinationRule,
    ContentFormula,
    ContentNodeRun,
    ContentOCRResult,
    ContentReviewRecord,
    ContentRuleVersion,
    ContentTask,
    ContentTypeDefinition,
    ContentWorkflowVersion,
    CreationMethod,
    FormulaPattern,
    FormulaSlotBinding,
    IndustryContentPackVersion,
    IndustryTemplateVersion,
    LexiconEntry,
    LexiconPack,
    LexiconVersion,
    MediaEvidenceItem,
    PersonaProfile,
    PersonaProfileVersion,
    ReplacementRule,
    TitleFormula,
    VariableDefinition,
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
        "content_type_codes": item.content_type_codes or [],
        "industry_scope": item.industry_scope or [],
        "channel_scope": item.channel_scope or [],
        "narrative_axis_codes": item.narrative_axis_codes or [],
        "methods": item.methods or [],
        "title_formula_codes": item.title_formula_codes or [],
        "title_pattern_codes": item.title_pattern_codes or [],
        "content_formula_code": item.content_formula_code,
        "body_pattern_codes": item.body_pattern_codes or [],
        "required_evidence_types": item.required_evidence_types or [],
        "compatibility": item.compatibility,
        "priority": item.priority,
        "conditions": item.conditions or {},
        "hard_conditions": item.hard_conditions or {},
        "score_weights": item.score_weights or {},
        "fallback_rule_id": item.fallback_rule_id,
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


def _content_type_dict(item: ContentTypeDefinition) -> dict[str, Any]:
    return {
        "id": item.id,
        "code": item.code,
        "name": item.name,
        "description": item.description,
        "supported_goals": item.supported_goals or [],
        "required_variable_codes": item.required_variable_codes or [],
        "evidence_policy": item.evidence_policy or {},
        "default_narrative_axes": item.default_narrative_axes or [],
        "default_body_formula_codes": item.default_body_formula_codes or [],
        "enabled": bool(item.enabled),
        "sort_order": item.sort_order,
    }


def _slot_dict(item: FormulaSlotBinding) -> dict[str, Any]:
    return {
        "id": item.id,
        "slot_key": item.slot_key,
        "value_type": item.value_type,
        "source_type": item.source_type,
        "source_path": item.source_path,
        "alternative_sources": item.alternative_sources or [],
        "lexicon_pack_codes": item.lexicon_pack_codes or [],
        "required": bool(item.required),
        "evidence_required": bool(item.evidence_required),
        "fallback_policy": item.fallback_policy,
        "validation_schema": item.validation_schema or {},
        "max_length": item.max_length,
        "sort_order": item.sort_order,
    }


def _pattern_dict(item: FormulaPattern, slots: list[FormulaSlotBinding]) -> dict[str, Any]:
    return {
        "id": item.id,
        "formula_kind": item.formula_kind,
        "formula_code": item.formula_code,
        "code": item.code,
        "name": item.name,
        "template_text": item.template_text,
        "paragraph_schema": item.paragraph_schema or [],
        "content_type_codes": item.content_type_codes or [],
        "channel_scope": item.channel_scope or [],
        "risk_policy": item.risk_policy or {},
        "enabled": bool(item.enabled),
        "sort_order": item.sort_order,
        "slots": [_slot_dict(slot) for slot in sorted(slots, key=lambda value: value.sort_order)],
    }


def _variable_dict(item: VariableDefinition) -> dict[str, Any]:
    return {
        "id": item.id,
        "code": item.code,
        "name": item.name,
        "value_type": item.value_type,
        "unit_schema": item.unit_schema or {},
        "evidence_policy": item.evidence_policy or {},
        "sensitivity": item.sensitivity,
        "allowed_usages": item.allowed_usages or [],
        "validation_schema": item.validation_schema or {},
        "enabled": bool(item.enabled),
        "sort_order": item.sort_order,
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
        type_query = select(ContentTypeDefinition).where(ContentTypeDefinition.version_id == version_id)
        pattern_query = select(FormulaPattern).where(FormulaPattern.rule_version_id == version_id)
        variable_query = select(VariableDefinition).where(VariableDefinition.rule_version_id == version_id)
        if not include_disabled:
            method_query = method_query.where(CreationMethod.enabled.is_(True))
            title_query = title_query.where(TitleFormula.enabled.is_(True))
            content_query = content_query.where(ContentFormula.enabled.is_(True))
            type_query = type_query.where(ContentTypeDefinition.enabled.is_(True))
            pattern_query = pattern_query.where(FormulaPattern.enabled.is_(True))
            variable_query = variable_query.where(VariableDefinition.enabled.is_(True))
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
        content_types = (await self.db.execute(type_query.order_by(ContentTypeDefinition.sort_order))).scalars()
        patterns = list((await self.db.execute(pattern_query.order_by(FormulaPattern.sort_order))).scalars())
        variables = (await self.db.execute(variable_query.order_by(VariableDefinition.sort_order))).scalars()
        pattern_ids = [item.id for item in patterns]
        slots = []
        if pattern_ids:
            slots = list(
                (
                    await self.db.execute(
                        select(FormulaSlotBinding)
                        .where(FormulaSlotBinding.pattern_id.in_(pattern_ids))
                        .order_by(FormulaSlotBinding.sort_order)
                    )
                ).scalars()
            )
        slots_by_pattern: dict[str, list[FormulaSlotBinding]] = {}
        for slot in slots:
            slots_by_pattern.setdefault(slot.pattern_id, []).append(slot)
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
            "content_types": [_content_type_dict(item) for item in content_types],
            "formula_patterns": [_pattern_dict(item, slots_by_pattern.get(item.id, [])) for item in patterns],
            "variables": [_variable_dict(item) for item in variables],
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
            select(func.coalesce(func.max(ContentRuleVersion.version), 0)).where(ContentRuleVersion.tenant_id.is_(None))
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
                    content_type_codes=item.get("content_type_codes") or [],
                    industry_scope=item.get("industry_scope") or [],
                    channel_scope=item.get("channel_scope") or [],
                    narrative_axis_codes=item.get("narrative_axis_codes") or [],
                    methods=item.get("methods") or [],
                    title_formula_codes=item.get("title_formula_codes") or [],
                    title_pattern_codes=item.get("title_pattern_codes") or [],
                    content_formula_code=item["content_formula_code"],
                    body_pattern_codes=item.get("body_pattern_codes") or [],
                    required_evidence_types=item.get("required_evidence_types") or [],
                    compatibility=item.get("compatibility", "compatible"),
                    priority=item.get("priority", 0),
                    conditions=item.get("conditions") or {},
                    hard_conditions=item.get("hard_conditions") or {},
                    score_weights=item.get("score_weights") or {},
                    fallback_rule_id=item.get("fallback_rule_id"),
                    recommendation_reason=item.get("recommendation_reason") or "",
                )
            )
        await self.db.flush()

    async def delete_rule_version(self, version_id: str) -> None:
        await self.db.execute(delete(ContentRuleVersion).where(ContentRuleVersion.id == version_id))
        await self.db.flush()

    async def get_template(self, template_id: str) -> IndustryTemplateVersion | None:
        result = await self.db.execute(select(IndustryTemplateVersion).where(IndustryTemplateVersion.id == template_id))
        return result.scalar_one_or_none()

    async def list_templates(self, *, published_only: bool = True) -> list[dict[str, Any]]:
        query = select(IndustryTemplateVersion)
        if published_only:
            query = query.where(IndustryTemplateVersion.status == "published")
        items = (await self.db.execute(query.order_by(IndustryTemplateVersion.name))).scalars()
        return [_template_dict(item) for item in items]

    async def get_workflow(self, workflow_id: str) -> ContentWorkflowVersion | None:
        result = await self.db.execute(select(ContentWorkflowVersion).where(ContentWorkflowVersion.id == workflow_id))
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
        content_type_code: str | None = None,
        industry_pack_version_id: str | None = None,
        persona_profile_version_id: str | None = None,
        channel_profile_version_id: str | None = None,
        runtime_config_snapshot: dict[str, Any] | None = None,
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
            content_type_code=content_type_code,
            industry_pack_version_id=industry_pack_version_id,
            persona_profile_version_id=persona_profile_version_id,
            channel_profile_version_id=channel_profile_version_id,
            runtime_config_snapshot_json=runtime_config_snapshot or {},
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
        total = (await self.db.execute(select(func.count(ContentTask.id)).where(*filters))).scalar_one()
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

    async def create_ocr_result(
        self,
        *,
        result_id: str,
        task: ContentTask,
        original_file_name: str,
        content_type: str,
        file_size: int,
        image_width: int,
        image_height: int,
        bucket_name: str,
        object_name: str,
        created_by: str,
    ) -> ContentOCRResult:
        item = ContentOCRResult(
            id=result_id,
            task_id=task.id,
            tenant_id=task.tenant_id,
            original_file_name=original_file_name,
            content_type=content_type,
            file_size=file_size,
            image_width=image_width,
            image_height=image_height,
            bucket_name=bucket_name,
            object_name=object_name,
            status="processing",
            created_by=created_by,
        )
        self.db.add(item)
        await self.db.flush()
        return item

    async def get_ocr_result(self, result_id: str, *, for_update: bool = False) -> ContentOCRResult | None:
        query = select(ContentOCRResult).where(ContentOCRResult.id == result_id)
        if for_update:
            query = query.with_for_update()
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_ocr_result_for_user(
        self, result_id: str, user: User, *, for_update: bool = False
    ) -> ContentOCRResult | None:
        item = await self.get_ocr_result(result_id, for_update=for_update)
        if item is None:
            return None
        task = await self.get_task_for_user(item.task_id, user)
        return item if task is not None else None

    async def list_ocr_results(self, task_id: str) -> list[ContentOCRResult]:
        items = (
            await self.db.execute(
                select(ContentOCRResult)
                .where(ContentOCRResult.task_id == task_id)
                .order_by(ContentOCRResult.created_at.desc())
            )
        ).scalars()
        return list(items)

    async def get_artifact_for_task(self, task_id: str) -> ContentArtifact | None:
        result = await self.db.execute(select(ContentArtifact).where(ContentArtifact.task_id == task_id))
        return result.scalar_one_or_none()

    async def get_artifact(self, artifact_id: str) -> ContentArtifact | None:
        result = await self.db.execute(select(ContentArtifact).where(ContentArtifact.id == artifact_id))
        return result.scalar_one_or_none()

    async def get_artifact_for_user(
        self,
        artifact_id: str,
        user: User,
        *,
        for_update: bool = False,
    ) -> ContentArtifact | None:
        query = select(ContentArtifact).where(ContentArtifact.id == artifact_id)
        if for_update:
            query = query.with_for_update()
        artifact = (await self.db.execute(query)).scalar_one_or_none()
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
            cover_asset_id=artifact.cover_asset_id,
            cover_job_id=artifact.cover_job_id,
            content_type_snapshot=artifact.content_type_snapshot or {},
            angle_snapshot=artifact.angle_snapshot or {},
            pattern_slot_snapshot=artifact.pattern_slot_snapshot or {},
            persona_snapshot=artifact.persona_snapshot or {},
            channel_snapshot=artifact.channel_snapshot or {},
            compliance_snapshot=artifact.compliance_snapshot or {},
            runtime_config_snapshot=artifact.runtime_config_snapshot or {},
            edit_diff_snapshot=artifact.edit_diff_snapshot or [],
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
                "cover_asset_id": item.cover_asset_id,
                "cover_job_id": item.cover_job_id,
                "content_type_snapshot": item.content_type_snapshot or {},
                "angle_snapshot": item.angle_snapshot or {},
                "pattern_slot_snapshot": item.pattern_slot_snapshot or {},
                "persona_snapshot": item.persona_snapshot or {},
                "channel_snapshot": item.channel_snapshot or {},
                "compliance_snapshot": item.compliance_snapshot or {},
                "runtime_config_snapshot": item.runtime_config_snapshot or {},
                "edit_diff_snapshot": item.edit_diff_snapshot or [],
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

    async def get_content_type(self, version_id: str, code: str) -> ContentTypeDefinition | None:
        result = await self.db.execute(
            select(ContentTypeDefinition).where(
                ContentTypeDefinition.version_id == version_id,
                ContentTypeDefinition.code == code,
                ContentTypeDefinition.enabled.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def get_industry_pack(self, version_id: str) -> IndustryContentPackVersion | None:
        result = await self.db.execute(
            select(IndustryContentPackVersion).where(IndustryContentPackVersion.id == version_id)
        )
        return result.scalar_one_or_none()

    async def get_published_industry_pack(self, slug: str) -> IndustryContentPackVersion | None:
        result = await self.db.execute(
            select(IndustryContentPackVersion)
            .where(
                IndustryContentPackVersion.slug == slug,
                IndustryContentPackVersion.status == "published",
                IndustryContentPackVersion.tenant_id.is_(None),
            )
            .order_by(IndustryContentPackVersion.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_industry_packs(self, *, published_only: bool = True) -> list[dict[str, Any]]:
        query = select(IndustryContentPackVersion)
        if published_only:
            query = query.where(IndustryContentPackVersion.status == "published")
        items = (
            await self.db.execute(query.order_by(IndustryContentPackVersion.name, IndustryContentPackVersion.version.desc()))
        ).scalars()
        return [
            {
                "id": item.id,
                "slug": item.slug,
                "tenant_id": item.tenant_id,
                "version": item.version,
                "status": item.status,
                "name": item.name,
                "description": item.description,
                "content_type_aliases": item.content_type_aliases or {},
                "variable_schema": item.variable_schema or [],
                "lexicon_version_ids": item.lexicon_version_ids or [],
                "pattern_ids": item.pattern_ids or [],
                "combination_overrides": item.combination_overrides or [],
                "persona_templates": item.persona_templates or [],
                "knowledge_scope": item.knowledge_scope or [],
                "evidence_policy": item.evidence_policy or {},
                "review_policy": item.review_policy or {},
                "published_at": format_utc_datetime(item.published_at),
            }
            for item in items
        ]

    async def get_channel_version(self, version_id: str) -> ChannelProfileVersion | None:
        result = await self.db.execute(
            select(ChannelProfileVersion).where(ChannelProfileVersion.id == version_id)
        )
        return result.scalar_one_or_none()

    async def list_channel_profiles(self, *, published_only: bool = True) -> list[dict[str, Any]]:
        query = select(ChannelProfileVersion, ChannelProfile).join(
            ChannelProfile, ChannelProfile.id == ChannelProfileVersion.profile_id
        )
        if published_only:
            query = query.where(ChannelProfileVersion.status == "published")
        rows = (
            await self.db.execute(query.order_by(ChannelProfile.name, ChannelProfileVersion.version.desc()))
        ).all()
        return [
            {
                "id": version.id,
                "profile_id": profile.id,
                "code": profile.code,
                "name": profile.name,
                "connector_type": profile.connector_type,
                "version": version.version,
                "status": version.status,
                "title_constraints": version.title_constraints or {},
                "body_constraints": version.body_constraints or {},
                "topic_constraints": version.topic_constraints or {},
                "media_constraints": version.media_constraints or {},
                "cta_policy": version.cta_policy or {},
                "link_policy": version.link_policy or {},
                "preview_schema": version.preview_schema or {},
                "published_at": format_utc_datetime(version.published_at),
            }
            for version, profile in rows
        ]

    async def get_persona_version_for_user(
        self, version_id: str, user: User
    ) -> tuple[PersonaProfileVersion, PersonaProfile] | None:
        result = await self.db.execute(
            select(PersonaProfileVersion, PersonaProfile)
            .join(PersonaProfile, PersonaProfile.id == PersonaProfileVersion.profile_id)
            .where(PersonaProfileVersion.id == version_id, PersonaProfile.deleted_at.is_(None))
        )
        row = result.one_or_none()
        if row is None:
            return None
        version, profile = row
        if user.role == "superadmin" or profile.created_by == str(user.uid):
            return version, profile
        if user.role == "admin" and profile.tenant_id == str(user.department_id):
            return version, profile
        return None

    async def get_persona_version(
        self, version_id: str
    ) -> tuple[PersonaProfileVersion, PersonaProfile] | None:
        """读取任务已锁定的人设版本，供受信任的后台工作流重放。"""

        result = await self.db.execute(
            select(PersonaProfileVersion, PersonaProfile)
            .join(PersonaProfile, PersonaProfile.id == PersonaProfileVersion.profile_id)
            .where(PersonaProfileVersion.id == version_id, PersonaProfile.deleted_at.is_(None))
        )
        return result.one_or_none()

    async def list_personas(self, user: User) -> list[dict[str, Any]]:
        filters = [PersonaProfile.deleted_at.is_(None), PersonaProfileVersion.status == "published"]
        if user.role == "admin":
            filters.append(PersonaProfile.tenant_id == str(user.department_id))
        elif user.role != "superadmin":
            filters.append(PersonaProfile.created_by == str(user.uid))
        rows = (
            await self.db.execute(
                select(PersonaProfileVersion, PersonaProfile)
                .join(PersonaProfile, PersonaProfile.id == PersonaProfileVersion.profile_id)
                .where(*filters)
                .order_by(PersonaProfile.updated_at.desc(), PersonaProfileVersion.version.desc())
            )
        ).all()
        return [
            {
                "id": version.id,
                "profile_id": profile.id,
                "name": profile.name,
                "version": version.version,
                "identity": version.identity or {},
                "experience_facts": version.experience_facts or [],
                "professional_background": version.professional_background or {},
                "tone": version.tone or {},
                "values": version.values or [],
                "positions": version.positions or [],
                "service_boundaries": version.service_boundaries or [],
                "preferred_phrases": version.preferred_phrases or [],
                "forbidden_phrases": version.forbidden_phrases or [],
                "evidence_ids": version.evidence_ids or [],
            }
            for version, profile in rows
        ]

    async def list_compliance_policies(self, *, published_only: bool = True) -> list[dict[str, Any]]:
        query = select(CompliancePolicyVersion)
        if published_only:
            query = query.where(CompliancePolicyVersion.status == "published")
        policies = list((await self.db.execute(query.order_by(CompliancePolicyVersion.scope_type))).scalars())
        policy_ids = [item.id for item in policies]
        rules: list[ReplacementRule] = []
        if policy_ids:
            rules = list(
                (
                    await self.db.execute(
                        select(ReplacementRule)
                        .where(ReplacementRule.policy_version_id.in_(policy_ids), ReplacementRule.enabled.is_(True))
                        .order_by(ReplacementRule.sort_order)
                    )
                ).scalars()
            )
        rules_by_policy: dict[str, list[ReplacementRule]] = {}
        for rule in rules:
            rules_by_policy.setdefault(rule.policy_version_id, []).append(rule)
        return [
            {
                "id": item.id,
                "scope_type": item.scope_type,
                "scope_id": item.scope_id,
                "tenant_id": item.tenant_id,
                "version": item.version,
                "status": item.status,
                "name": item.name,
                "policy_config": item.policy_config or {},
                "rules": [
                    {
                        "id": rule.id,
                        "rule_code": rule.rule_code,
                        "pattern": rule.pattern,
                        "match_type": rule.match_type,
                        "risk_level": rule.risk_level,
                        "action": rule.action,
                        "replacement": rule.replacement,
                        "human_confirmation_required": bool(rule.human_confirmation_required),
                        "explanation": rule.explanation,
                    }
                    for rule in rules_by_policy.get(item.id, [])
                ],
            }
            for item in policies
        ]

    async def list_lexicon_packs(self, *, published_only: bool = True) -> list[dict[str, Any]]:
        query = (
            select(LexiconVersion, LexiconPack)
            .join(LexiconPack, LexiconPack.id == LexiconVersion.pack_id)
        )
        if published_only:
            query = query.where(LexiconVersion.status == "published")
        rows = (await self.db.execute(query.order_by(LexiconPack.scope_type, LexiconPack.name))).all()
        return [
            {
                "id": version.id,
                "pack_id": pack.id,
                "code": pack.code,
                "scope_type": pack.scope_type,
                "scope_id": pack.scope_id,
                "tenant_id": pack.tenant_id,
                "name": pack.name,
                "semantic_category": pack.semantic_category,
                "version": version.version,
                "status": version.status,
                "published_at": format_utc_datetime(version.published_at),
            }
            for version, pack in rows
        ]

    async def list_lexicon_entries(self, version_id: str) -> list[dict[str, Any]]:
        items = (
            await self.db.execute(
                select(LexiconEntry)
                .where(LexiconEntry.version_id == version_id, LexiconEntry.enabled.is_(True))
                .order_by(LexiconEntry.sort_order)
            )
        ).scalars()
        return [
            {
                "id": item.id,
                "text": item.text,
                "normalized_text": item.normalized_text,
                "tags": item.tags or [],
                "risk_level": item.risk_level,
                "applicable_formula_codes": item.applicable_formula_codes or [],
                "applicable_slot_keys": item.applicable_slot_keys or [],
                "replacement_text": item.replacement_text,
            }
            for item in items
        ]

    async def create_media_evidence(
        self,
        *,
        task_id: str,
        attachment_id: str,
        object_uri: str,
        media_type: str,
        original_filename: str | None,
        extracted_text: str,
        metadata: dict[str, Any],
        source_hash: str,
        allowed_usage: list[str],
    ) -> MediaEvidenceItem:
        item = MediaEvidenceItem(
            id=f"mei_{uuid.uuid4().hex}",
            task_id=task_id,
            attachment_id=attachment_id,
            object_uri=object_uri,
            media_type=media_type,
            original_filename=original_filename,
            extracted_text=extracted_text,
            metadata_json=metadata,
            source_hash=source_hash,
            allowed_usage=allowed_usage,
        )
        self.db.add(item)
        await self.db.flush()
        return item

    async def get_media_evidence(self, evidence_id: str) -> MediaEvidenceItem | None:
        result = await self.db.execute(select(MediaEvidenceItem).where(MediaEvidenceItem.id == evidence_id))
        return result.scalar_one_or_none()

    async def list_media_evidence(self, task_id: str) -> list[MediaEvidenceItem]:
        items = (
            await self.db.execute(
                select(MediaEvidenceItem)
                .where(MediaEvidenceItem.task_id == task_id)
                .order_by(MediaEvidenceItem.created_at)
            )
        ).scalars()
        return list(items)

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
