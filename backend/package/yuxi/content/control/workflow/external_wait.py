from __future__ import annotations

from datetime import timedelta
from typing import Any

from langgraph.types import interrupt
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.repositories.content_cover_repository import ContentCoverRepository
from yuxi.services.run_queue_service import append_run_stream_event
from yuxi.utils.datetime_utils import utc_now_naive

COVER_SKIP_REASON = "好评笔记跳过封面生成"
MISSING_VISUAL_COVER_SKIP_REASON = "未锁定图库图片，跳过封面生成"
RESEARCH_SKIP_REASON = "好评笔记沿用简报已锁定事实，跳过获客调研"
REVIEW_NOTES_SERVICE_ENTRY = "好评笔记"
REVIEW_NOTES_KNOWLEDGE_BASE_NAME = "好评知识库"
REVIEW_NOTES_KNOWLEDGE_BASE_ALIASES = frozenset({"好评知识库", "好评笔记知识库"})


def _brief_form_values(state: dict[str, Any]) -> dict[str, Any]:
    brief = state.get("content_brief") or {}
    values = brief.get("form_values") if isinstance(brief, dict) else {}
    return values if isinstance(values, dict) else {}


def _brief_service_entry(state: dict[str, Any]) -> str:
    return str(_brief_form_values(state).get("mp_service_entry") or "")


def skip_formula_lexicon_pipeline(state: dict[str, Any]) -> bool:
    return _brief_service_entry(state) == REVIEW_NOTES_SERVICE_ENTRY


def skip_formula_lexicon_for_node(state: dict[str, Any], node_id: str) -> bool:
    if skip_formula_lexicon_pipeline(state):
        return True
    if node_id != "generate_content":
        return False
    snapshot = state.get("runtime_config_snapshot")
    if not isinstance(snapshot, dict):
        return False
    from yuxi.content.v3.joint_workflow import PLATFORM_WORKFLOW_V5_ID

    return snapshot.get("workflow_version_id") == PLATFORM_WORKFLOW_V5_ID


def skip_research_pipeline(state: dict[str, Any]) -> bool:
    return skip_formula_lexicon_pipeline(state)


def skip_cover_pipeline(state: dict[str, Any]) -> bool:
    if skip_formula_lexicon_pipeline(state):
        return True
    snapshot = state.get("runtime_config_snapshot")
    if not isinstance(snapshot, dict):
        return False
    visual = snapshot.get("visual_material") or {}
    return not bool(visual.get("image_asset_id"))


def cover_skip_reason(state: dict[str, Any]) -> str:
    if skip_formula_lexicon_pipeline(state):
        return COVER_SKIP_REASON
    return MISSING_VISUAL_COVER_SKIP_REASON


def skip_content_correction_interrupt(state: dict[str, Any]) -> bool:
    return skip_formula_lexicon_pipeline(state)


def skip_content_approval_interrupt(state: dict[str, Any]) -> bool:
    """PC 终审自动通过；小程序带内容编码的任务仍由 getRun 自动续跑。"""
    if skip_formula_lexicon_pipeline(state):
        return True
    return not bool(str(_brief_form_values(state).get("mp_content_code") or "").strip())


def skip_cover_selection_interrupt(state: dict[str, Any]) -> bool:
    """小程序没有选封面 UI，有内容编码的任务在封面生成成功后自动选定。"""
    return bool(str(_brief_form_values(state).get("mp_content_code") or "").strip())


class ExternalWaitNodeHandler:
    """把外部 CoverJob 转成可恢复的工作流等待，不在 Agent 节点轮询。"""

    async def execute(
        self,
        *,
        db: AsyncSession,
        node: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        if node.get("external_job_type") != "content_cover":
            raise ValueError(f"不支持的外部任务类型: {node.get('external_job_type')}")
        if skip_cover_pipeline(state):
            return {
                "cover_job": {
                    **(state.get("cover_job") or {}),
                    "status": "skipped",
                    "skipped": True,
                    "skip_reason": cover_skip_reason(state),
                },
                "cover_assets": [],
                "resume_parent_run_id": None,
            }
        job_id = str((state.get("cover_job") or {}).get("cover_job_id") or "")
        if not job_id:
            raise ValueError("外部等待节点缺少 cover_job_id")
        repo = ContentCoverRepository(db)
        job = await repo.get_job(job_id)
        if job is None or job.content_task_id != state["task_id"] or job.owner_uid != state["uid"]:
            raise ValueError("CoverJob 不存在或不属于当前内容任务")

        timeout_seconds = int(node["timeout_seconds"])
        if (
            job.status not in {"succeeded", "failed", "cancelled"}
            and job.created_at
            and (utc_now_naive() - job.created_at > timedelta(seconds=timeout_seconds))
        ):
            raise TimeoutError("CoverJob 等待超时")

        while job.status not in {"succeeded", "failed", "cancelled"}:
            expected_run_id = state.get("resume_parent_run_id") or state["run_id"]
            answer = interrupt(
                {
                    "interrupt_type": "external_wait",
                    "task_id": state["task_id"],
                    "run_id": expected_run_id,
                    "node_id": node["id"],
                    "expected_state_version": int(state.get("state_version") or 0),
                    "cover_job_id": job.id,
                    "status": job.status,
                    "progress": job.progress,
                }
            )
            expected = {
                "run_id": expected_run_id,
                "node_id": node["id"],
                "expected_state_version": int(state.get("state_version") or 0),
                "cover_job_id": job.id,
            }
            if not isinstance(answer, dict) or any(answer.get(key) != value for key, value in expected.items()):
                raise ValueError("CoverJob 恢复请求已过期或目标不匹配")
            await db.refresh(job)

        if job.status != "succeeded":
            await append_run_stream_event(
                state["run_id"],
                "content.cover.failed",
                {
                    "task_id": state["task_id"],
                    "parent_run_id": state["run_id"],
                    "node_id": node["id"],
                    "cover_job_id": job.id,
                    "status": job.status,
                    "error_code": job.error_code,
                },
                thread_id=state["task_id"],
            )
            failure_detail = job.error_message or job.error_code or "COVER_JOB_FAILED"
            raise RuntimeError(f"CoverJob {job.status}: {failure_detail}")
        asset_ids = list((job.result_json or {}).get("asset_ids") or [])
        if not asset_ids:
            raise RuntimeError("CoverJob 成功但没有返回资产")
        assets = await repo.get_assets_for_user(asset_ids, state["uid"])
        if len(assets) != len(asset_ids) or any(item.role != "output" for item in assets):
            raise RuntimeError("CoverJob 返回了无效资产")
        await append_run_stream_event(
            state["run_id"],
            "content.cover.completed",
            {
                "task_id": state["task_id"],
                "parent_run_id": state["run_id"],
                "node_id": node["id"],
                "cover_job_id": job.id,
                "asset_count": len(asset_ids),
                "provider": job.model,
            },
            thread_id=state["task_id"],
        )
        return {
            "cover_job": {
                **(state.get("cover_job") or {}),
                "cover_job_id": job.id,
                "status": job.status,
                "provider": job.model,
                "provider_task_id": job.provider_task_id,
                "asset_ids": asset_ids,
            },
            "cover_assets": [item.to_dict() for item in assets],
            "resume_parent_run_id": None,
        }


__all__ = [
    "COVER_SKIP_REASON",
    "MISSING_VISUAL_COVER_SKIP_REASON",
    "RESEARCH_SKIP_REASON",
    "REVIEW_NOTES_KNOWLEDGE_BASE_ALIASES",
    "REVIEW_NOTES_KNOWLEDGE_BASE_NAME",
    "REVIEW_NOTES_SERVICE_ENTRY",
    "ExternalWaitNodeHandler",
    "cover_skip_reason",
    "skip_content_correction_interrupt",
    "skip_content_approval_interrupt",
    "skip_cover_selection_interrupt",
    "skip_cover_pipeline",
    "skip_formula_lexicon_pipeline",
    "skip_research_pipeline",
]
