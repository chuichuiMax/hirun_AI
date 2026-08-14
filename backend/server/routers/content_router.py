from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from server.utils.auth_middleware import get_admin_user, get_db, get_required_user, get_superadmin_user
from yuxi.content.schemas import (
    ContentArtifactRegenerate,
    ContentArtifactReview,
    ContentArtifactUpdate,
    ContentBriefSave,
    ContentFinalizeRequest,
    ContentNodeRetry,
    ContentRunCreate,
    ContentRunResume,
    ContentTaskCreate,
    ContentTaskUpdate,
    RuleBundleUpdate,
    RuleDraftCreate,
    StrategySelection,
    StrategyValidateRequest,
    RuleVersionAction,
)
from yuxi.repositories.content_repository import ContentRepository
from yuxi.services.agent_run_service import cancel_agent_run_view, stream_agent_run_events
from yuxi.services.content_service import (
    create_content_run,
    create_content_task,
    delete_content_task,
    duplicate_content_task,
    finalize_content_artifact,
    get_content_bootstrap,
    get_content_run,
    get_content_task,
    get_task_artifact,
    list_content_artifact_versions,
    list_content_tasks,
    recommend_content_strategy,
    regenerate_content_artifact,
    resume_content_run,
    retry_content_node,
    review_content_artifact,
    save_content_brief,
    save_content_strategy,
    update_content_artifact,
    update_content_task,
    validate_content_strategy,
    activate_content_rule_version,
    create_content_rule_draft,
    discard_content_rule_draft,
    save_content_rule_draft,
    validate_rule_bundle_for_publish,
)
from yuxi.storage.postgres.models_business import User

content = APIRouter(prefix="/content", tags=["content"])


@content.get("/bootstrap")
async def content_bootstrap(
    current_user: User = Depends(get_required_user), db: AsyncSession = Depends(get_db)
):
    return await get_content_bootstrap(db, current_user)


@content.post("/tasks")
async def create_task(
    payload: ContentTaskCreate,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await create_content_task(db, current_user, payload)


@content.get("/tasks")
async def list_tasks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = None,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await list_content_tasks(db, current_user, page=page, page_size=page_size, status=status)


@content.get("/tasks/{task_id}")
async def get_task(
    task_id: str,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_content_task(db, current_user, task_id)


@content.patch("/tasks/{task_id}")
async def update_task(
    task_id: str,
    payload: ContentTaskUpdate,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await update_content_task(db, current_user, task_id, payload)


@content.delete("/tasks/{task_id}")
async def delete_task(
    task_id: str,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await delete_content_task(db, current_user, task_id)


@content.post("/tasks/{task_id}/duplicate")
async def duplicate_task(
    task_id: str,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await duplicate_content_task(db, current_user, task_id)


@content.put("/tasks/{task_id}/brief")
async def save_brief(
    task_id: str,
    payload: ContentBriefSave,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await save_content_brief(db, current_user, task_id, payload.brief, compile_now=False)


@content.post("/tasks/{task_id}/compile-brief")
async def compile_brief(
    task_id: str,
    payload: ContentBriefSave,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await save_content_brief(db, current_user, task_id, payload.brief, compile_now=True)


@content.post("/tasks/{task_id}/strategy/recommend")
async def recommend_strategy(
    task_id: str,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await recommend_content_strategy(db, current_user, task_id)


@content.put("/tasks/{task_id}/strategy")
async def save_strategy(
    task_id: str,
    payload: StrategySelection,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await save_content_strategy(db, current_user, task_id, payload)


@content.post("/strategy/validate")
async def validate_strategy(
    payload: StrategyValidateRequest,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    del current_user
    return await validate_content_strategy(db, payload)


@content.get("/rule-versions/{version_id}/bundle")
async def get_rule_bundle(
    version_id: str,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    del current_user
    bundle = await ContentRepository(db).get_rule_bundle(version_id)
    return {"bundle": bundle}


@content.post("/tasks/{task_id}/runs")
async def create_run(
    task_id: str,
    payload: ContentRunCreate,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await create_content_run(db, current_user, task_id, payload)


@content.get("/runs/{run_id}")
async def get_run(
    run_id: str,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_content_run(db, current_user, run_id)


@content.get("/runs/{run_id}/events")
async def stream_run_events(
    run_id: str,
    after_seq: str = "0-0",
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    current_user: User = Depends(get_required_user),
):
    cursor = last_event_id or after_seq
    return StreamingResponse(
        stream_agent_run_events(run_id=run_id, after_seq=cursor, current_uid=str(current_user.uid), verbose=True),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@content.post("/runs/{run_id}/resume")
async def resume_run(
    run_id: str,
    payload: ContentRunResume,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await resume_content_run(db, current_user, run_id, payload)


@content.post("/runs/{run_id}/cancel")
async def cancel_run(
    run_id: str,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    await get_content_run(db, current_user, run_id)
    return await cancel_agent_run_view(run_id=run_id, current_uid=str(current_user.uid), db=db)


@content.post("/runs/{run_id}/retry-node")
async def retry_node(
    run_id: str,
    payload: ContentNodeRetry,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await retry_content_node(
        db,
        current_user,
        run_id,
        request_id=payload.request_id,
        node_id=payload.node_id,
        model_spec=payload.model_spec,
    )


@content.get("/tasks/{task_id}/artifact")
async def get_artifact_for_task(
    task_id: str,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_task_artifact(db, current_user, task_id)


@content.patch("/artifacts/{artifact_id}")
async def update_artifact(
    artifact_id: str,
    payload: ContentArtifactUpdate,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await update_content_artifact(db, current_user, artifact_id, payload)


@content.post("/artifacts/{artifact_id}/review")
async def review_artifact(
    artifact_id: str,
    payload: ContentArtifactReview,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await review_content_artifact(db, current_user, artifact_id, model_spec=payload.model_spec)


@content.post("/artifacts/{artifact_id}/finalize")
async def finalize_artifact(
    artifact_id: str,
    payload: ContentFinalizeRequest,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    del payload
    return await finalize_content_artifact(db, current_user, artifact_id)


@content.get("/artifacts/{artifact_id}/versions")
async def list_artifact_versions(
    artifact_id: str,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await list_content_artifact_versions(db, current_user, artifact_id)


@content.post("/artifacts/{artifact_id}/regenerate")
async def regenerate_artifact(
    artifact_id: str,
    payload: ContentArtifactRegenerate,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await regenerate_content_artifact(db, current_user, artifact_id, payload)


@content.get("/admin/rules")
async def list_rule_versions(
    current_user: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)
):
    del current_user
    return {"items": await ContentRepository(db).list_rule_versions()}


@content.get("/admin/rules/{version_id}/bundle")
async def get_admin_rule_bundle(
    version_id: str,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    del current_user
    bundle = await ContentRepository(db).get_rule_bundle(version_id, include_disabled=True)
    if bundle is None:
        raise HTTPException(status_code=404, detail="规则版本不存在")
    return {"bundle": bundle, "validation": validate_rule_bundle_for_publish(bundle)}


@content.post("/admin/rules/drafts")
async def create_rule_draft(
    payload: RuleDraftCreate,
    current_user: User = Depends(get_superadmin_user),
    db: AsyncSession = Depends(get_db),
):
    return await create_content_rule_draft(db, current_user, payload)


@content.put("/admin/rules/{version_id}/bundle")
async def save_rule_draft(
    version_id: str,
    payload: RuleBundleUpdate,
    current_user: User = Depends(get_superadmin_user),
    db: AsyncSession = Depends(get_db),
):
    return await save_content_rule_draft(db, current_user, version_id, payload)


@content.delete("/admin/rules/{version_id}")
async def discard_rule_draft(
    version_id: str,
    current_user: User = Depends(get_superadmin_user),
    db: AsyncSession = Depends(get_db),
):
    return await discard_content_rule_draft(db, current_user, version_id)


@content.post("/admin/rules/{version_id}/publish")
async def publish_rule_version(
    version_id: str,
    payload: RuleVersionAction,
    current_user: User = Depends(get_superadmin_user),
    db: AsyncSession = Depends(get_db),
):
    return await activate_content_rule_version(
        db,
        current_user,
        version_id,
        rollback=False,
        note=payload.note,
    )


@content.post("/admin/rules/{version_id}/rollback")
async def rollback_rule_version(
    version_id: str,
    payload: RuleVersionAction,
    current_user: User = Depends(get_superadmin_user),
    db: AsyncSession = Depends(get_db),
):
    return await activate_content_rule_version(
        db,
        current_user,
        version_id,
        rollback=True,
        note=payload.note,
    )


@content.get("/admin/industry-templates")
async def list_industry_templates(
    current_user: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)
):
    del current_user
    return {"items": await ContentRepository(db).list_templates(published_only=False)}


@content.get("/admin/workflow-templates")
async def list_workflow_templates(
    current_user: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)
):
    del current_user
    return {"items": await ContentRepository(db).list_workflows(published_only=False)}
