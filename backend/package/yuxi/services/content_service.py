from __future__ import annotations

import os
import uuid
from copy import deepcopy
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.content.generation import SKILL_VERSIONS, review_generated_content
from yuxi.content.rules import CONTENT_GOALS, recommend_strategy, validate_strategy_bundle
from yuxi.content.schemas import (
    ContentArtifactUpdate,
    ContentArtifactRegenerate,
    ContentBriefPayload,
    ContentRunCreate,
    ContentRunResume,
    ContentTaskCreate,
    ContentTaskUpdate,
    RuleBundleUpdate,
    RuleDraftCreate,
    StrategySelection,
    StrategyValidateRequest,
)
from yuxi.content.validators import normalize_manual_evidence, validate_content
from yuxi.models.providers.cache import model_cache
from yuxi.repositories.agent_run_repository import AgentRunRepository
from yuxi.repositories.content_repository import ContentRepository
from yuxi.services.run_queue_service import get_arq_pool
from yuxi.storage.postgres.models_business import AgentRun, User
from yuxi.storage.postgres.models_content import ContentArtifactVersion, ContentTask
from yuxi.utils.datetime_utils import utc_now_naive


def _content_error(status_code: int, code: str, message: str, **extra: Any) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "error": {
                "code": code,
                "message": message,
                "retryable": bool(extra.pop("retryable", False)),
                **extra,
            }
        },
    )


def _validate_model_spec(model_spec: str | None) -> str | None:
    normalized = model_spec.strip() if isinstance(model_spec, str) else None
    if not normalized:
        return None
    info = model_cache.get_model_info(normalized)
    if not info or info.model_type != "chat":
        raise _content_error(422, "CONTENT_MODEL_UNAVAILABLE", f"未找到可用聊天模型：{normalized}")
    return normalized


def _clean_list(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value and value.strip()))


def normalize_rule_bundle(payload: RuleBundleUpdate) -> dict[str, Any]:
    bundle = payload.model_dump()
    bundle["changelog"] = bundle["changelog"].strip()
    list_fields = {
        "methods": ("suitable_scenes", "sentence_patterns", "variable_schema", "risk_rules"),
        "title_formulas": (
            "suitable_scenes",
            "reference_examples",
            "variable_schema",
            "compatible_methods",
            "risk_rules",
        ),
        "content_formulas": (
            "compatible_methods",
            "suitable_scenes",
            "business_pains",
            "structure_schema",
            "reference_examples",
            "required_variables",
            "risk_rules",
        ),
        "combination_rules": ("methods", "title_formula_codes"),
    }
    for section, fields in list_fields.items():
        for index, item in enumerate(bundle[section]):
            for field in fields:
                item[field] = _clean_list(item[field])
            if "code" in item:
                item["code"] = item["code"].strip().upper()
            if section == "combination_rules":
                item["content_goal"] = item["content_goal"].strip().lower()
                item["content_formula_code"] = item["content_formula_code"].strip().upper()
                item["methods"] = [code.upper() for code in item["methods"]]
                item["title_formula_codes"] = [code.upper() for code in item["title_formula_codes"]]
            elif "compatible_methods" in item:
                item["compatible_methods"] = [code.upper() for code in item["compatible_methods"]]
            item["sort_order"] = index

    for section in ("methods", "title_formulas", "content_formulas"):
        codes = [item["code"] for item in bundle[section]]
        duplicate_codes = sorted({code for code in codes if codes.count(code) > 1})
        if duplicate_codes:
            raise _content_error(
                422,
                "CONTENT_RULE_CODE_DUPLICATED",
                f"{section} 存在重复编码：{', '.join(duplicate_codes)}",
                section=section,
                codes=duplicate_codes,
            )
    return bundle


def validate_rule_bundle_for_publish(bundle: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    methods = {item["code"]: item for item in bundle.get("methods") or [] if item.get("enabled", True)}
    core_methods = {code for code, item in methods.items() if item.get("method_type") == "core"}
    titles = {item["code"]: item for item in bundle.get("title_formulas") or [] if item.get("enabled", True)}
    bodies = {item["code"]: item for item in bundle.get("content_formulas") or [] if item.get("enabled", True)}

    def add_error(code: str, message: str, path: str) -> None:
        errors.append({"code": code, "message": message, "path": path})

    if not core_methods:
        add_error("METHOD_REQUIRED", "至少保留一个已启用的核心创作手法", "methods")
    if "S01" not in methods:
        add_error("SCENE_ENHANCER_REQUIRED", "系统工作流依赖已启用的 S01 场景增强", "methods.S01")
    if not titles:
        add_error("TITLE_FORMULA_REQUIRED", "至少保留一个已启用的标题公式", "title_formulas")
    if not bodies:
        add_error("CONTENT_FORMULA_REQUIRED", "至少保留一个已启用的正文公式", "content_formulas")

    for code, item in titles.items():
        compatible = set(item.get("compatible_methods") or [])
        missing = compatible - core_methods
        if not compatible:
            add_error("TITLE_METHOD_REQUIRED", f"标题公式 {code} 至少关联一个核心手法", f"title_formulas.{code}")
        elif missing:
            add_error(
                "TITLE_METHOD_INVALID",
                f"标题公式 {code} 引用了不可用手法：{', '.join(sorted(missing))}",
                f"title_formulas.{code}.compatible_methods",
            )

    for code, item in bodies.items():
        compatible = set(item.get("compatible_methods") or [])
        missing = compatible - core_methods
        if not item.get("structure_schema"):
            add_error("CONTENT_STRUCTURE_REQUIRED", f"正文公式 {code} 至少包含一个结构段落", f"content_formulas.{code}")
        if not compatible:
            add_error("CONTENT_METHOD_REQUIRED", f"正文公式 {code} 至少关联一个核心手法", f"content_formulas.{code}")
        elif missing:
            add_error(
                "CONTENT_METHOD_INVALID",
                f"正文公式 {code} 引用了不可用手法：{', '.join(sorted(missing))}",
                f"content_formulas.{code}.compatible_methods",
            )

    covered_goals: set[str] = set()
    valid_goals = {item["code"] for item in CONTENT_GOALS}
    for index, item in enumerate(bundle.get("combination_rules") or []):
        path = f"combination_rules.{index}"
        goal = item.get("content_goal")
        if goal not in valid_goals:
            add_error("COMBINATION_GOAL_INVALID", f"组合规则使用了无效内容目标：{goal}", f"{path}.content_goal")
        else:
            covered_goals.add(goal)
        missing_methods = set(item.get("methods") or []) - core_methods
        missing_titles = set(item.get("title_formula_codes") or []) - set(titles)
        body_code = item.get("content_formula_code")
        if not item.get("methods"):
            add_error("COMBINATION_METHOD_REQUIRED", "组合规则至少选择一个核心手法", f"{path}.methods")
        elif missing_methods:
            add_error(
                "COMBINATION_METHOD_INVALID",
                f"组合规则引用了不可用手法：{', '.join(sorted(missing_methods))}",
                f"{path}.methods",
            )
        if not item.get("title_formula_codes"):
            add_error("COMBINATION_TITLE_REQUIRED", "组合规则至少选择一个标题公式", f"{path}.title_formula_codes")
        elif missing_titles:
            add_error(
                "COMBINATION_TITLE_INVALID",
                f"组合规则引用了不可用标题公式：{', '.join(sorted(missing_titles))}",
                f"{path}.title_formula_codes",
            )
        if body_code not in bodies:
            add_error(
                "COMBINATION_CONTENT_INVALID",
                f"组合规则引用了不可用正文公式：{body_code}",
                f"{path}.content_formula_code",
            )
        selected_methods = set(item.get("methods") or [])
        for title_code in item.get("title_formula_codes") or []:
            title = titles.get(title_code)
            if title and not selected_methods.intersection(title.get("compatible_methods") or []):
                add_error(
                    "COMBINATION_TITLE_METHOD_MISMATCH",
                    f"组合规则的手法与标题公式 {title_code} 不兼容",
                    f"{path}.title_formula_codes",
                )
        body = bodies.get(body_code)
        if body and not selected_methods.intersection(body.get("compatible_methods") or []):
            add_error(
                "COMBINATION_CONTENT_METHOD_MISMATCH",
                f"组合规则的手法与正文公式 {body_code} 不兼容",
                f"{path}.content_formula_code",
            )

    for goal in CONTENT_GOALS:
        if goal["code"] not in covered_goals:
            add_error(
                "COMBINATION_GOAL_UNCOVERED",
                f"内容目标“{goal['name']}”至少需要一条组合规则",
                "combination_rules",
            )

    if not bundle.get("combination_rules"):
        warnings.append({"code": "COMBINATION_EMPTY", "message": "尚未配置组合矩阵", "path": "combination_rules"})
    return {"errors": errors, "warnings": warnings}


def _task_name(template_name: str, content_goal: str) -> str:
    goal_name = next((item["name"] for item in CONTENT_GOALS if item["code"] == content_goal), content_goal)
    return f"{template_name} · {goal_name}"


def _brief_field_value(brief: dict[str, Any], key: str) -> Any:
    form_values = brief.get("form_values") or {}
    if key in form_values:
        return form_values[key]
    if key == "brand_name":
        return (brief.get("brand") or {}).get("name")
    if key == "audience":
        return brief.get("audience")
    if key in {"required_terms", "forbidden_terms", "knowledge_scope"}:
        return brief.get(key)
    return (brief.get("business_variables") or {}).get(key)


def compile_content_brief(
    *, task: ContentTask, template: Any, brief: ContentBriefPayload
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    raw = brief.model_dump()
    form_values = dict(raw.get("form_values") or {})
    business_variables = dict(raw.get("business_variables") or {})
    reserved = {"brand_name", "audience", "persona", "required_terms", "forbidden_terms", "knowledge_scope"}
    business_variables.update(
        {key: value for key, value in form_values.items() if key not in reserved and value not in (None, "", [])}
    )
    brand = dict(raw.get("brand") or {})
    if form_values.get("brand_name"):
        brand["name"] = form_values["brand_name"]
    audience = raw.get("audience") or form_values.get("audience") or []
    if isinstance(audience, str):
        audience = [item.strip() for item in audience.split(",") if item.strip()]
    persona = dict(raw.get("persona") or {})
    if form_values.get("persona"):
        persona.setdefault("description", form_values["persona"])

    compiled = {
        "task_id": task.id,
        "industry": template.slug,
        "content_goal": task.content_goal,
        "mode": task.mode,
        "brand": brand,
        "audience": audience,
        "business_variables": business_variables,
        "persona": persona,
        "required_terms": raw.get("required_terms") or form_values.get("required_terms") or [],
        "forbidden_terms": raw.get("forbidden_terms") or form_values.get("forbidden_terms") or [],
        "knowledge_scope": raw.get("knowledge_scope") or form_values.get("knowledge_scope") or [],
        "attachments": raw.get("attachments") or [],
        "locked_fields": raw.get("locked_fields") or [],
        "form_values": form_values,
    }
    fields = template.quick_form_schema if task.mode == "quick" else template.pro_form_schema
    missing = []
    for field in fields or []:
        if not field.get("required"):
            continue
        value = _brief_field_value(compiled, field["key"])
        if value in (None, "", []):
            missing.append({"field": field["key"], "label": field.get("label") or field["key"]})
    return compiled, missing


async def get_content_bootstrap(db: AsyncSession, user: User) -> dict[str, Any]:
    repo = ContentRepository(db)
    version = await repo.get_published_rule_version()
    if version is None:
        raise _content_error(503, "CONTENT_RULES_NOT_INITIALIZED", "创作规则库尚未初始化")
    knowledge_options: list[dict[str, Any]] = []
    if os.environ.get("LITE_MODE", "").lower() not in {"true", "1"}:
        from yuxi.knowledge import knowledge_base

        knowledge_options = (await knowledge_base.get_databases_by_user(user)).get("databases") or []
    return {
        "industry_templates": await repo.list_templates(),
        "content_goals": CONTENT_GOALS,
        "rule_bundle": await repo.get_rule_bundle(version.id),
        "knowledge_options": [
            {"id": item.get("kb_id"), "name": item.get("name"), "description": item.get("description")}
            for item in knowledge_options
            if item.get("kb_id")
        ],
    }


async def create_content_task(db: AsyncSession, user: User, payload: ContentTaskCreate) -> dict[str, Any]:
    repo = ContentRepository(db)
    template = await repo.get_template(payload.industry_template_id)
    if template is None or template.status != "published":
        raise _content_error(404, "CONTENT_INDUSTRY_TEMPLATE_NOT_FOUND", "行业模板不存在或未发布")
    rule_version = await repo.get_published_rule_version()
    if rule_version is None:
        raise _content_error(503, "CONTENT_RULES_NOT_INITIALIZED", "创作规则库尚未初始化")
    goal = payload.content_goal or template.default_goal
    if goal not in {item["code"] for item in CONTENT_GOALS}:
        raise _content_error(422, "CONTENT_GOAL_INVALID", "内容目标无效")
    task = await repo.create_task(
        task_id=f"ct_{uuid.uuid4().hex}",
        user=user,
        name=payload.name or _task_name(template.name, goal),
        template=template,
        rule_version_id=rule_version.id,
        mode=payload.mode,
        content_goal=goal,
        project_id=payload.project_id,
    )
    await repo.track(
        "content_task_created",
        uid=str(user.uid),
        task_id=task.id,
        properties={"industry": template.slug, "mode": task.mode, "content_goal": goal},
    )
    await db.commit()
    return {"task": task.to_dict(), "template": {"id": template.id, "name": template.name, "slug": template.slug}}


async def list_content_tasks(
    db: AsyncSession, user: User, *, page: int, page_size: int, status: str | None
) -> dict[str, Any]:
    repo = ContentRepository(db)
    items, total = await repo.list_tasks(user=user, page=page, page_size=page_size, status=status)
    return {"items": [item.to_dict() for item in items], "total": total, "page": page, "page_size": page_size}


async def get_content_task(db: AsyncSession, user: User, task_id: str) -> dict[str, Any]:
    repo = ContentRepository(db)
    task = await repo.get_task_for_user(task_id, user)
    if task is None:
        raise _content_error(404, "CONTENT_TASK_NOT_FOUND", "内容任务不存在")
    template = await repo.get_template(task.industry_template_version_id)
    artifact = await repo.get_artifact_for_task(task.id)
    return {
        "task": task.to_dict(),
        "template": None
        if template is None
        else {
            "id": template.id,
            "slug": template.slug,
            "name": template.name,
            "quick_form_schema": template.quick_form_schema or [],
            "pro_form_schema": template.pro_form_schema or [],
            "review_policy": template.review_policy or {},
        },
        "artifact": artifact.to_dict() if artifact else None,
    }


async def update_content_task(
    db: AsyncSession, user: User, task_id: str, payload: ContentTaskUpdate
) -> dict[str, Any]:
    repo = ContentRepository(db)
    task = await repo.get_task_for_user(task_id, user, for_update=True)
    if task is None:
        raise _content_error(404, "CONTENT_TASK_NOT_FOUND", "内容任务不存在")
    changes = payload.model_dump(exclude_none=True)
    if "content_goal" in changes and changes["content_goal"] not in {item["code"] for item in CONTENT_GOALS}:
        raise _content_error(422, "CONTENT_GOAL_INVALID", "内容目标无效")
    for key, value in changes.items():
        setattr(task, key, value)
    task.updated_by = str(user.uid)
    task.updated_at = utc_now_naive()
    if {"content_goal", "mode"} & changes.keys():
        task.strategy_json = {}
        task.current_stage = "brief"
    await db.commit()
    return {"task": task.to_dict()}


async def delete_content_task(db: AsyncSession, user: User, task_id: str) -> dict[str, Any]:
    repo = ContentRepository(db)
    task = await repo.get_task_for_user(task_id, user, for_update=True)
    if task is None:
        raise _content_error(404, "CONTENT_TASK_NOT_FOUND", "内容任务不存在")
    task.deleted_at = utc_now_naive()
    task.status = "deleted"
    task.updated_by = str(user.uid)
    await db.commit()
    return {"deleted": True, "task_id": task.id}


async def duplicate_content_task(db: AsyncSession, user: User, task_id: str) -> dict[str, Any]:
    repo = ContentRepository(db)
    source = await repo.get_task_for_user(task_id, user)
    if source is None:
        raise _content_error(404, "CONTENT_TASK_NOT_FOUND", "内容任务不存在")
    template = await repo.get_template(source.industry_template_version_id)
    if template is None:
        raise _content_error(409, "CONTENT_TEMPLATE_VERSION_MISSING", "原任务的行业模板版本不存在")
    copy_task = await repo.create_task(
        task_id=f"ct_{uuid.uuid4().hex}",
        user=user,
        name=f"{source.name}（副本）",
        template=template,
        rule_version_id=source.rule_version_id,
        mode=source.mode,
        content_goal=source.content_goal,
        project_id=source.project_id,
    )
    copy_task.brief_json = deepcopy(source.brief_json or {})
    copy_task.strategy_json = deepcopy(source.strategy_json or {})
    copy_task.evidence_json = deepcopy(source.evidence_json or {})
    copy_task.current_stage = "strategy" if copy_task.brief_json else "brief"
    await db.commit()
    return {"task": copy_task.to_dict()}


async def save_content_brief(
    db: AsyncSession, user: User, task_id: str, brief: ContentBriefPayload, *, compile_now: bool
) -> dict[str, Any]:
    repo = ContentRepository(db)
    task = await repo.get_task_for_user(task_id, user, for_update=True)
    if task is None:
        raise _content_error(404, "CONTENT_TASK_NOT_FOUND", "内容任务不存在")
    template = await repo.get_template(task.industry_template_version_id)
    if template is None:
        raise _content_error(409, "CONTENT_TEMPLATE_VERSION_MISSING", "任务绑定的行业模板版本不存在")
    compiled, missing = compile_content_brief(task=task, template=template, brief=brief)
    task.brief_json = compiled
    task.updated_by = str(user.uid)
    task.updated_at = utc_now_naive()
    if compile_now and missing:
        await db.commit()
        raise _content_error(
            422,
            "CONTENT_REQUIRED_VARIABLE_MISSING",
            "业务简报缺少必填变量",
            fields=missing,
            suggested_action="补充缺失字段后重新编译",
        )
    if compile_now:
        task.evidence_json = normalize_manual_evidence(task.id, compiled)
        task.status = "brief_ready"
        task.current_stage = "strategy"
        task.strategy_json = {}
        await repo.track("content_brief_completed", uid=str(user.uid), task_id=task.id)
    await db.commit()
    return {"task": task.to_dict(), "missing_fields": missing, "compiled": compile_now and not missing}


async def recommend_content_strategy(db: AsyncSession, user: User, task_id: str) -> dict[str, Any]:
    repo = ContentRepository(db)
    task = await repo.get_task_for_user(task_id, user, for_update=True)
    if task is None:
        raise _content_error(404, "CONTENT_TASK_NOT_FOUND", "内容任务不存在")
    if not task.brief_json:
        raise _content_error(409, "CONTENT_BRIEF_NOT_COMPILED", "请先完成业务简报")
    bundle = await repo.get_rule_bundle(task.rule_version_id)
    if bundle is None:
        raise _content_error(409, "CONTENT_RULE_VERSION_MISSING", "任务绑定的规则版本不存在")
    strategy = recommend_strategy(bundle, brief=task.brief_json, content_goal=task.content_goal)
    task.strategy_json = strategy
    task.status = "strategy_ready" if strategy["compatibility"] != "blocked" else "brief_ready"
    task.current_stage = "strategy"
    task.updated_by = str(user.uid)
    await repo.track(
        "strategy_auto_matched",
        uid=str(user.uid),
        task_id=task.id,
        properties={"compatibility": strategy["compatibility"]},
    )
    await db.commit()
    return {"strategy": strategy, "task": task.to_dict()}


async def validate_content_strategy(db: AsyncSession, payload: StrategyValidateRequest) -> dict[str, Any]:
    repo = ContentRepository(db)
    bundle = await repo.get_rule_bundle(payload.rule_version_id)
    if bundle is None:
        raise _content_error(404, "CONTENT_RULE_VERSION_MISSING", "规则版本不存在")
    return validate_strategy_bundle(
        bundle,
        brief=payload.brief.model_dump(),
        content_goal=payload.content_goal,
        methods=payload.methods,
        title_formula_code=payload.title_formula_code,
        content_formula_code=payload.content_formula_code,
    )


async def save_content_strategy(
    db: AsyncSession, user: User, task_id: str, payload: StrategySelection
) -> dict[str, Any]:
    repo = ContentRepository(db)
    task = await repo.get_task_for_user(task_id, user, for_update=True)
    if task is None:
        raise _content_error(404, "CONTENT_TASK_NOT_FOUND", "内容任务不存在")
    bundle = await repo.get_rule_bundle(task.rule_version_id)
    if bundle is None:
        raise _content_error(409, "CONTENT_RULE_VERSION_MISSING", "任务绑定的规则版本不存在")
    validation = validate_strategy_bundle(
        bundle,
        brief=task.brief_json or {},
        content_goal=task.content_goal,
        methods=payload.methods,
        title_formula_code=payload.title_formula_code,
        content_formula_code=payload.content_formula_code,
    )
    strategy = {
        "content_goal": task.content_goal,
        **payload.model_dump(),
        "compatibility": validation["compatibility"],
        "required_variables": validation["missing_variables"],
        "rule_version_id": task.rule_version_id,
        "reason_summary": "用户在专业模式中确认的创作组合",
        "warnings": validation["reasons"],
    }
    task.strategy_json = strategy
    task.updated_by = str(user.uid)
    if validation["compatibility"] == "blocked":
        task.status = "brief_ready"
    else:
        task.status = "strategy_ready"
        task.current_stage = "generation"
    await repo.track(
        "strategy_manually_changed",
        uid=str(user.uid),
        task_id=task.id,
        properties={"compatibility": validation["compatibility"]},
    )
    await db.commit()
    return {"strategy": strategy, "validation": validation, "task": task.to_dict()}


def _run_response(run: AgentRun) -> dict[str, Any]:
    return {
        "run_id": run.id,
        "task_id": run.thread_id,
        "status": run.status,
        "request_id": run.request_id,
        "stream_url": f"/api/content/runs/{run.id}/events",
    }


async def _enqueue_content_run(
    db: AsyncSession,
    *,
    user: User,
    task: ContentTask,
    request_id: str,
    action: str,
    model_spec: str | None,
    parent_run_id: str | None = None,
    resume: dict[str, Any] | None = None,
    node_id: str | None = None,
) -> dict[str, Any]:
    run_repo = AgentRunRepository(db)
    existing = await run_repo.get_run_by_request_id(request_id)
    if existing:
        if existing.uid != str(user.uid):
            raise _content_error(409, "CONTENT_REQUEST_ID_CONFLICT", "request_id 已被其他用户使用")
        return _run_response(existing)
    run_id = str(uuid.uuid4())
    input_payload = {
        "run_type": "content_resume" if action == "resume" else "content",
        "task_id": task.id,
        "action": action,
        "model_spec": model_spec,
        "uid": str(user.uid),
        "request_id": request_id,
        "resume": resume,
        "node_id": node_id,
        "parent_run_id": parent_run_id,
        "workflow_version_id": task.workflow_version_id,
        "rule_version_id": task.rule_version_id,
    }
    try:
        checkpoint_thread_id = f"content:{task.id}"
        if action in {"resume", "retry"} and parent_run_id:
            parent = await run_repo.get_run(parent_run_id)
            if parent and parent.checkpoint_thread_id:
                checkpoint_thread_id = parent.checkpoint_thread_id
        run = await run_repo.create_run(
            run_id=run_id,
            thread_id=task.id,
            agent_id="content-studio",
            uid=str(user.uid),
            request_id=request_id,
            input_payload=input_payload,
            parent_run_id=parent_run_id,
            run_type=input_payload["run_type"],
            resume_request_id=request_id if action == "resume" else None,
            checkpoint_thread_id=checkpoint_thread_id,
        )
        task.latest_run_id = run.id
        task.status = "queued"
        task.current_stage = "generation"
        task.error_json = None
        run_event = {
            "start": "content_run_started",
            "resume": "content_run_resumed",
            "retry": "content_run_retried",
        }[action]
        await ContentRepository(db).track(
            run_event,
            uid=str(user.uid),
            task_id=task.id,
            run_id=run.id,
            properties={"parent_run_id": parent_run_id, "node_id": node_id},
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await run_repo.get_run_by_request_id(request_id)
        if existing and existing.uid == str(user.uid):
            return _run_response(existing)
        raise _content_error(409, "CONTENT_REQUEST_ID_CONFLICT", "request_id 冲突")
    queue = await get_arq_pool()
    await queue.enqueue_job("process_content_run", run.id, _job_id=f"content-run:{run.id}")
    return _run_response(run)


async def create_content_run(
    db: AsyncSession, user: User, task_id: str, payload: ContentRunCreate
) -> dict[str, Any]:
    repo = ContentRepository(db)
    task = await repo.get_task_for_user(task_id, user, for_update=True)
    if task is None:
        raise _content_error(404, "CONTENT_TASK_NOT_FOUND", "内容任务不存在")
    if not task.brief_json or not task.strategy_json:
        raise _content_error(409, "CONTENT_TASK_NOT_READY", "请先完成业务简报和创作策略")
    if task.strategy_json.get("compatibility") == "blocked":
        raise _content_error(409, "CONTENT_STRATEGY_BLOCKED", "当前创作组合不兼容，不能开始生成")
    model_spec = _validate_model_spec(payload.model_spec)
    result = await _enqueue_content_run(
        db,
        user=user,
        task=task,
        request_id=payload.request_id,
        action="start",
        model_spec=model_spec,
    )
    return result


async def resume_content_run(
    db: AsyncSession, user: User, run_id: str, payload: ContentRunResume
) -> dict[str, Any]:
    run_repo = AgentRunRepository(db)
    parent = await run_repo.get_run_for_user(run_id, str(user.uid))
    if parent is None or parent.run_type not in {"content", "content_resume"}:
        raise _content_error(404, "CONTENT_RUN_NOT_FOUND", "内容运行不存在")
    if parent.status != "interrupted":
        raise _content_error(409, "CONTENT_RUN_NOT_INTERRUPTED", "只有等待人工处理的运行可以恢复")
    task = await ContentRepository(db).get_task_for_user(parent.thread_id, user, for_update=True)
    if task is None:
        raise _content_error(404, "CONTENT_TASK_NOT_FOUND", "内容任务不存在")
    model_spec = (parent.input_payload or {}).get("model_spec")
    return await _enqueue_content_run(
        db,
        user=user,
        task=task,
        request_id=payload.request_id,
        action="resume",
        model_spec=model_spec,
        parent_run_id=parent.id,
        resume=payload.resume,
    )


async def retry_content_node(
    db: AsyncSession,
    user: User,
    run_id: str,
    *,
    request_id: str,
    node_id: str | None,
    model_spec: str | None,
) -> dict[str, Any]:
    run_repo = AgentRunRepository(db)
    parent = await run_repo.get_run_for_user(run_id, str(user.uid))
    if parent is None:
        raise _content_error(404, "CONTENT_RUN_NOT_FOUND", "内容运行不存在")
    if parent.status != "failed":
        raise _content_error(409, "CONTENT_RUN_NOT_RETRYABLE", "只有失败的运行可以从失败节点重试")
    task = await ContentRepository(db).get_task_for_user(parent.thread_id, user, for_update=True)
    if task is None:
        raise _content_error(404, "CONTENT_TASK_NOT_FOUND", "内容任务不存在")
    return await _enqueue_content_run(
        db,
        user=user,
        task=task,
        request_id=request_id,
        action="retry",
        model_spec=_validate_model_spec(model_spec) or (parent.input_payload or {}).get("model_spec"),
        parent_run_id=parent.id,
        node_id=node_id,
    )


async def get_content_run(db: AsyncSession, user: User, run_id: str) -> dict[str, Any]:
    run = await AgentRunRepository(db).get_run_for_user(run_id, str(user.uid))
    if run is None or run.run_type not in {"content", "content_resume"}:
        raise _content_error(404, "CONTENT_RUN_NOT_FOUND", "内容运行不存在")
    return {"run": run.to_dict()}


async def get_task_artifact(db: AsyncSession, user: User, task_id: str) -> dict[str, Any]:
    repo = ContentRepository(db)
    task = await repo.get_task_for_user(task_id, user)
    if task is None:
        raise _content_error(404, "CONTENT_TASK_NOT_FOUND", "内容任务不存在")
    artifact = await repo.get_artifact_for_task(task.id)
    return {"artifact": artifact.to_dict() if artifact else None}


async def regenerate_content_artifact(
    db: AsyncSession,
    user: User,
    artifact_id: str,
    payload: ContentArtifactRegenerate,
) -> dict[str, Any]:
    repo = ContentRepository(db)
    artifact = await repo.get_artifact_for_user(artifact_id, user)
    if artifact is None:
        raise _content_error(404, "CONTENT_ARTIFACT_NOT_FOUND", "内容资产不存在")
    task = await repo.get_task_for_user(artifact.task_id, user, for_update=True)
    if task is None:
        raise _content_error(404, "CONTENT_TASK_NOT_FOUND", "内容任务不存在")
    return await create_content_run(
        db,
        user,
        task.id,
        ContentRunCreate(request_id=payload.request_id, model_spec=payload.model_spec),
    )


async def create_content_rule_draft(
    db: AsyncSession,
    user: User,
    payload: RuleDraftCreate,
) -> dict[str, Any]:
    repo = ContentRepository(db)
    current = await repo.get_published_rule_version_for_update()
    existing = await repo.get_platform_rule_draft()
    if existing:
        raise _content_error(
            409,
            "CONTENT_RULE_DRAFT_EXISTS",
            f"已有规则草稿 v{existing.version}，请继续编辑或先放弃该草稿",
            version_id=existing.id,
        )
    if current is None or current.id != payload.source_version_id:
        raise _content_error(409, "CONTENT_RULE_SOURCE_INVALID", "只能基于当前已发布的平台规则创建草稿")
    source = current
    source_bundle = await repo.get_rule_bundle(source.id, include_disabled=True)
    if source_bundle is None:
        raise _content_error(404, "CONTENT_RULE_VERSION_MISSING", "源规则版本不存在")

    version = await repo.next_platform_rule_version()
    version_id = f"content-rules-platform-v{version}"
    changelog = payload.changelog.strip() or f"基于 v{source.version} 创建运营编辑草稿"
    await repo.create_rule_version(
        version_id=version_id,
        version=version,
        changelog=changelog,
        created_by=str(user.uid),
    )
    await repo.replace_rule_bundle(version_id, source_bundle)
    await repo.track(
        "content_rule_draft_created",
        uid=str(user.uid),
        properties={"version_id": version_id, "version": version, "source_version_id": source.id},
    )
    await db.commit()
    bundle = await repo.get_rule_bundle(version_id, include_disabled=True)
    return {"bundle": bundle, "validation": validate_rule_bundle_for_publish(bundle or {})}


async def save_content_rule_draft(
    db: AsyncSession,
    user: User,
    version_id: str,
    payload: RuleBundleUpdate,
) -> dict[str, Any]:
    repo = ContentRepository(db)
    version = await repo.get_rule_version_for_update(version_id)
    if version is None or version.tenant_id is not None:
        raise _content_error(404, "CONTENT_RULE_VERSION_MISSING", "平台规则版本不存在")
    if version.status != "draft":
        raise _content_error(409, "CONTENT_RULE_VERSION_IMMUTABLE", "已发布或已归档规则不可直接修改，请创建新草稿")

    bundle = normalize_rule_bundle(payload)
    await repo.replace_rule_bundle(version.id, bundle)
    version.changelog = bundle["changelog"] or version.changelog
    validation = validate_rule_bundle_for_publish(bundle)
    await repo.track(
        "content_rule_draft_saved",
        uid=str(user.uid),
        properties={
            "version_id": version.id,
            "version": version.version,
            "method_count": len(bundle["methods"]),
            "title_formula_count": len(bundle["title_formulas"]),
            "content_formula_count": len(bundle["content_formulas"]),
            "combination_count": len(bundle["combination_rules"]),
            "validation_error_count": len(validation["errors"]),
        },
    )
    await db.commit()
    saved = await repo.get_rule_bundle(version.id, include_disabled=True)
    return {"bundle": saved, "validation": validation}


async def discard_content_rule_draft(db: AsyncSession, user: User, version_id: str) -> dict[str, bool]:
    repo = ContentRepository(db)
    version = await repo.get_rule_version_for_update(version_id)
    if version is None or version.tenant_id is not None:
        raise _content_error(404, "CONTENT_RULE_VERSION_MISSING", "平台规则版本不存在")
    if version.status != "draft":
        raise _content_error(409, "CONTENT_RULE_VERSION_IMMUTABLE", "只能放弃尚未发布的规则草稿")
    await repo.track(
        "content_rule_draft_discarded",
        uid=str(user.uid),
        properties={"version_id": version.id, "version": version.version},
    )
    await repo.delete_rule_version(version.id)
    await db.commit()
    return {"discarded": True}


async def activate_content_rule_version(
    db: AsyncSession,
    user: User,
    version_id: str,
    *,
    rollback: bool,
    note: str | None,
) -> dict[str, Any]:
    repo = ContentRepository(db)
    target = await repo.get_rule_version_for_update(version_id)
    if target is None or target.tenant_id is not None:
        raise _content_error(404, "CONTENT_RULE_VERSION_MISSING", "平台规则版本不存在")
    if rollback and target.status not in {"archived", "published"}:
        raise _content_error(409, "CONTENT_RULE_VERSION_NOT_ROLLBACKABLE", "只能回滚到已发布过的规则版本")
    if not rollback and target.status not in {"draft", "archived", "published"}:
        raise _content_error(409, "CONTENT_RULE_VERSION_NOT_PUBLISHABLE", "当前规则版本不可发布")

    bundle = await repo.get_rule_bundle(target.id, include_disabled=True)
    validation = validate_rule_bundle_for_publish(bundle or {})
    if validation["errors"]:
        raise _content_error(
            409,
            "CONTENT_RULE_VERSION_INVALID",
            "规则校验未通过，请修正后再发布",
            validation=validation,
        )

    current = await repo.get_published_rule_version_for_update()
    if current and current.id != target.id:
        current.status = "archived"
    target.status = "published"
    target.published_at = utc_now_naive()
    await repo.track(
        "content_rule_version_rolled_back" if rollback else "content_rule_version_published",
        uid=str(user.uid),
        properties={
            "version_id": target.id,
            "version": target.version,
            "previous_version_id": current.id if current else None,
            "note": note,
        },
    )
    await db.commit()
    return {
        "version": {
            "id": target.id,
            "version": target.version,
            "status": target.status,
            "published_at": target.published_at.isoformat() if target.published_at else None,
        },
        "previous_version_id": current.id if current and current.id != target.id else None,
    }


async def update_content_artifact(
    db: AsyncSession, user: User, artifact_id: str, payload: ContentArtifactUpdate
) -> dict[str, Any]:
    repo = ContentRepository(db)
    artifact = await repo.get_artifact_for_user(artifact_id, user)
    if artifact is None:
        raise _content_error(404, "CONTENT_ARTIFACT_NOT_FOUND", "内容资产不存在")
    task = await repo.get_task_for_user(artifact.task_id, user, for_update=True)
    artifact.title = payload.title.strip()
    artifact.body = payload.body.strip()
    artifact.topics = payload.topics
    artifact.current_version += 1
    artifact.status = "draft"
    artifact.review_snapshot = {"status": "pending", "checks": []}
    artifact.updated_at = utc_now_naive()
    task.status = "review_required"
    task.current_stage = "review"
    task.review_json = artifact.review_snapshot
    await repo.save_artifact_version(
        artifact=artifact,
        source_type="manual_edit",
        model_spec=None,
        skill_versions=SKILL_VERSIONS,
        rule_version_id=task.rule_version_id,
        knowledge_snapshot=task.evidence_json or {},
        review_snapshot=artifact.review_snapshot,
        created_by=str(user.uid),
    )
    await db.commit()
    return {"artifact": artifact.to_dict()}


def _merge_reviews(deterministic: dict[str, Any], llm: dict[str, Any]) -> dict[str, Any]:
    checks = list(deterministic.get("checks") or []) + list(llm.get("checks") or [])
    status = "blocked" if any(item.get("level") == "error" for item in checks) else "warning" if checks else "passed"
    return {"status": status, "checks": checks}


async def review_content_artifact(
    db: AsyncSession, user: User, artifact_id: str, *, model_spec: str | None
) -> dict[str, Any]:
    repo = ContentRepository(db)
    artifact = await repo.get_artifact_for_user(artifact_id, user)
    if artifact is None:
        raise _content_error(404, "CONTENT_ARTIFACT_NOT_FOUND", "内容资产不存在")
    task = await repo.get_task_for_user(artifact.task_id, user, for_update=True)
    deterministic = validate_content(
        title=artifact.title,
        body=artifact.body,
        topics=artifact.topics or [],
        brief=task.brief_json or {},
        evidence_bundle=task.evidence_json or {},
        strategy=task.strategy_json or {},
    )
    llm = await review_generated_content(
        model_spec=_validate_model_spec(model_spec),
        title=artifact.title,
        body=artifact.body,
        topics=artifact.topics or [],
        brief=task.brief_json or {},
        strategy=task.strategy_json or {},
        evidence_bundle=task.evidence_json or {},
    )
    review = _merge_reviews(deterministic, llm)
    artifact.review_snapshot = review
    artifact.status = "reviewed" if review["status"] != "blocked" else "blocked"
    task.review_json = review
    task.status = "reviewed" if review["status"] != "blocked" else "review_blocked"
    version_result = await db.execute(
        select(ContentArtifactVersion).where(
            ContentArtifactVersion.artifact_id == artifact.id,
            ContentArtifactVersion.version == artifact.current_version,
        )
    )
    version = version_result.scalar_one_or_none()
    if version:
        version.review_snapshot = review
        await repo.add_review_record(
            artifact_version_id=version.id,
            review_type="combined",
            status=review["status"],
            checks=review["checks"],
            reviewer_uid=str(user.uid),
        )
    await db.commit()
    return {"artifact": artifact.to_dict(), "review": review}


async def finalize_content_artifact(db: AsyncSession, user: User, artifact_id: str) -> dict[str, Any]:
    repo = ContentRepository(db)
    artifact = await repo.get_artifact_for_user(artifact_id, user)
    if artifact is None:
        raise _content_error(404, "CONTENT_ARTIFACT_NOT_FOUND", "内容资产不存在")
    if (artifact.review_snapshot or {}).get("status") == "blocked":
        raise _content_error(409, "CONTENT_REVIEW_BLOCKED", "内容存在阻断问题，不能保存为正式版本")
    if (artifact.review_snapshot or {}).get("status") not in {"passed", "warning"}:
        raise _content_error(409, "CONTENT_REVIEW_REQUIRED", "请先完成内容审核")
    task = await repo.get_task_for_user(artifact.task_id, user, for_update=True)
    artifact.status = "final"
    artifact.updated_at = utc_now_naive()
    task.status = "completed"
    task.current_stage = "review"
    await repo.track(
        "content_artifact_finalized",
        uid=str(user.uid),
        task_id=task.id,
        properties={"artifact_id": artifact.id, "version": artifact.current_version},
    )
    await db.commit()
    return {"artifact": artifact.to_dict(), "task": task.to_dict()}


async def list_content_artifact_versions(
    db: AsyncSession, user: User, artifact_id: str
) -> dict[str, Any]:
    repo = ContentRepository(db)
    artifact = await repo.get_artifact_for_user(artifact_id, user)
    if artifact is None:
        raise _content_error(404, "CONTENT_ARTIFACT_NOT_FOUND", "内容资产不存在")
    return {"items": await repo.list_artifact_versions(artifact.id)}
