from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.content.schemas import (
    XiaohongshuAccountCreate,
    XiaohongshuAccountUpdate,
    XiaohongshuDistributionCreate,
)
from yuxi.integrations.xiaohongshu import XiaohongshuRuntime
from yuxi.repositories.content_repository import ContentRepository
from yuxi.repositories.xiaohongshu_repository import XiaohongshuRepository
from yuxi.services.run_queue_service import get_arq_pool, get_redis_client
from yuxi.storage.postgres.models_business import User
from yuxi.storage.postgres.models_content import ContentDistributionJob
from yuxi.utils.datetime_utils import utc_now_naive
from yuxi.utils.logging_config import logger

LOGIN_SESSION_SECONDS = 180


def _error(status_code: int, code: str, message: str, **extra: Any) -> HTTPException:
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


def _owner_uid(user: User) -> str:
    return str(user.uid)


def _login_state_key(session_id: str) -> str:
    return f"xhs:login:{session_id}"


def _serialize_job(job: ContentDistributionJob, results) -> dict[str, Any]:
    payload = job.to_dict()
    payload["results"] = [item.to_dict() for item in results]
    return payload


async def list_accounts(db: AsyncSession, user: User) -> dict[str, Any]:
    items = await XiaohongshuRepository(db).list_accounts(_owner_uid(user))
    return {"items": [item.to_dict() for item in items]}


async def create_account(
    db: AsyncSession, user: User, payload: XiaohongshuAccountCreate
) -> dict[str, Any]:
    repo = XiaohongshuRepository(db)
    try:
        account = await repo.create_account(
            owner_uid=_owner_uid(user),
            display_name=payload.display_name,
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _error(409, "XHS_ACCOUNT_NAME_EXISTS", "账号备注名称已存在") from exc
    return {"account": account.to_dict()}


async def update_account(
    db: AsyncSession,
    user: User,
    account_id: str,
    payload: XiaohongshuAccountUpdate,
) -> dict[str, Any]:
    repo = XiaohongshuRepository(db)
    account = await repo.get_account(account_id, _owner_uid(user), for_update=True)
    if account is None:
        raise _error(404, "XHS_ACCOUNT_NOT_FOUND", "小红书账号不存在")
    changes = payload.model_dump(exclude_none=True)
    for key, value in changes.items():
        setattr(account, key, value)
    account.updated_at = utc_now_naive()
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _error(409, "XHS_ACCOUNT_NAME_EXISTS", "账号备注名称已存在") from exc
    return {"account": account.to_dict()}


async def delete_account(db: AsyncSession, user: User, account_id: str) -> dict[str, Any]:
    repo = XiaohongshuRepository(db)
    account = await repo.get_account(account_id, _owner_uid(user), for_update=True)
    if account is None:
        raise _error(404, "XHS_ACCOUNT_NOT_FOUND", "小红书账号不存在")
    await repo.delete_account(account)
    await db.commit()
    try:
        queue = await get_arq_pool()
        await queue.enqueue_job(
            "process_xiaohongshu_profile_cleanup",
            account.id,
            account.owner_uid,
            _job_id=f"xhs-cleanup:{account.id}",
        )
    except Exception as exc:
        logger.warning(f"Falling back to immediate Xiaohongshu profile cleanup for {account.id}: {exc}")
        try:
            XiaohongshuRuntime().remove_account_dir(account.owner_uid, account.id)
        except Exception as cleanup_exc:
            logger.error(f"Failed to clean Xiaohongshu profile for {account.id}: {cleanup_exc}")
            raise _error(
                503,
                "XHS_PROFILE_CLEANUP_PENDING",
                "账号已移除，但登录凭据清理失败，请联系管理员处理",
                retryable=True,
            ) from cleanup_exc
    return {"deleted": True, "account_id": account_id}


async def start_account_login(db: AsyncSession, user: User, account_id: str) -> dict[str, Any]:
    repo = XiaohongshuRepository(db)
    account = await repo.get_account(account_id, _owner_uid(user), for_update=True)
    if account is None:
        raise _error(404, "XHS_ACCOUNT_NOT_FOUND", "小红书账号不存在")
    if not account.enabled:
        raise _error(409, "XHS_ACCOUNT_DISABLED", "请先启用该账号")

    pending = await repo.get_pending_login_session(account.id, account.owner_uid, utc_now_naive())
    if pending is not None:
        return {"session": pending.to_dict(), "reused": True}

    await repo.delete_completed_login_sessions(account.id)
    session = await repo.create_login_session(
        account=account,
        expires_at=utc_now_naive() + timedelta(seconds=LOGIN_SESSION_SECONDS),
    )
    account.login_status = "pending"
    account.last_error_code = None
    account.last_error_message = None
    await db.commit()

    try:
        queue = await get_arq_pool()
        queued = await queue.enqueue_job(
            "process_xiaohongshu_login",
            session.id,
            _job_id=f"xhs-login:{session.id}",
        )
    except Exception as exc:
        session.status = "failed"
        session.error_code = "XHS_QUEUE_UNAVAILABLE"
        session.error_message = "登录队列暂不可用"
        session.completed_at = utc_now_naive()
        account.login_status = "error"
        account.last_error_code = session.error_code
        account.last_error_message = session.error_message
        await db.commit()
        raise _error(503, session.error_code, session.error_message, retryable=True) from exc
    if queued is None:
        raise _error(409, "XHS_LOGIN_ALREADY_QUEUED", "该登录任务已在处理中")
    return {"session": session.to_dict()}


async def get_login_session(db: AsyncSession, user: User, session_id: str) -> dict[str, Any]:
    repo = XiaohongshuRepository(db)
    owner_uid = _owner_uid(user)
    session = await repo.get_login_session(session_id, owner_uid, for_update=True)
    if session is None:
        raise _error(404, "XHS_LOGIN_SESSION_NOT_FOUND", "登录会话不存在")
    if session.status == "pending" and session.expires_at <= utc_now_naive():
        session.status = "expired"
        session.error_code = "XHS_LOGIN_EXPIRED"
        session.error_message = "二维码已过期，请重新扫码"
        session.completed_at = utc_now_naive()
        account = await repo.get_account(session.account_id, owner_uid, for_update=True)
        if account is not None and account.login_status == "pending":
            account.login_status = "expired"
            account.last_error_code = session.error_code
            account.last_error_message = session.error_message
        await db.commit()

    result = session.to_dict()
    if session.status != "pending":
        result["qr_code"] = None
        result["tip"] = session.error_message
        return {"session": result}

    state: dict[str, Any] = {}
    try:
        raw = await (await get_redis_client()).get(_login_state_key(session_id))
    except Exception as exc:
        raise _error(
            503,
            "XHS_LOGIN_STATE_UNAVAILABLE",
            "登录状态暂时不可用，请稍后重试",
            retryable=True,
        ) from exc
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                state = parsed
        except json.JSONDecodeError:
            state = {}
    result["qr_code"] = state.get("qr_code")
    result["tip"] = state.get("tip")
    return {"session": result}


async def check_account_login(db: AsyncSession, user: User, account_id: str) -> dict[str, Any]:
    account = await XiaohongshuRepository(db).get_account(account_id, _owner_uid(user))
    if account is None:
        raise _error(404, "XHS_ACCOUNT_NOT_FOUND", "小红书账号不存在")
    try:
        queue = await get_arq_pool()
        await queue.enqueue_job(
            "process_xiaohongshu_status_check",
            account.id,
            account.owner_uid,
            _job_id=f"xhs-check:{account.id}:{uuid.uuid4().hex}",
        )
    except Exception as exc:
        raise _error(
            503,
            "XHS_STATUS_QUEUE_UNAVAILABLE",
            "账号状态检查暂时不可用，请稍后重试",
            retryable=True,
        ) from exc
    return {"accepted": True, "account": account.to_dict()}


async def create_distribution(
    db: AsyncSession,
    user: User,
    artifact_id: str,
    payload: XiaohongshuDistributionCreate,
) -> dict[str, Any]:
    owner_uid = _owner_uid(user)
    content_repo = ContentRepository(db)
    artifact = await content_repo.get_artifact(artifact_id)
    if artifact is None or artifact.created_by != owner_uid:
        raise _error(404, "CONTENT_ARTIFACT_NOT_FOUND", "内容作品不存在")
    review_status = (artifact.review_snapshot or {}).get("status")
    if review_status not in {"passed", "warning"}:
        raise _error(409, "CONTENT_REVIEW_BLOCKED", "内容需通过审核后才能分发")
    if payload.mode == "publish" and not payload.confirm_publish:
        raise _error(422, "XHS_PUBLISH_CONFIRM_REQUIRED", "直接发布前需要明确确认")

    account_ids = list(dict.fromkeys(payload.account_ids))
    repo = XiaohongshuRepository(db)
    accounts = await repo.get_accounts(account_ids, owner_uid)
    if len(accounts) != len(account_ids):
        raise _error(404, "XHS_ACCOUNT_NOT_FOUND", "包含不存在或不属于当前用户的账号")
    unavailable = [item.id for item in accounts if not item.enabled or item.login_status != "logged_in"]
    if unavailable:
        raise _error(
            409,
            "XHS_ACCOUNT_NOT_READY",
            "存在未登录或已停用的账号",
            account_ids=unavailable,
        )

    title = payload.title if payload.title is not None else artifact.title.strip()
    body = payload.body if payload.body is not None else artifact.body.strip()
    topics = list(
        dict.fromkeys(
            item.strip().lstrip("#")
            for item in (payload.topics or artifact.topics or [])
            if item.strip()
        )
    )
    if not title or len(title) > 20:
        raise _error(422, "XHS_TITLE_INVALID", "小红书标题需为 1–20 个字符")
    if not body or len(body) > 1000:
        raise _error(422, "XHS_BODY_INVALID", "小红书正文需为 1–1000 个字符")
    if len(topics) > 10 or any(len(item) > 20 for item in topics):
        raise _error(422, "XHS_TOPICS_INVALID", "话题最多 10 个，单个话题不超过 20 个字符")

    artifact_version = await repo.get_artifact_version(artifact.id, artifact.current_version)
    if artifact_version is None:
        raise _error(409, "CONTENT_ARTIFACT_VERSION_MISSING", "当前内容版本不存在")

    request_key = hashlib.sha256(f"{owner_uid}:{payload.request_id}".encode()).hexdigest()
    existing = await repo.get_job_by_idempotency_key(request_key, owner_uid)
    if existing is not None:
        results = await repo.list_distribution_results(existing.id)
        return {"job": _serialize_job(existing, results), "deduplicated": True}

    snapshot = {
        "schema_version": 1,
        "account_ids": account_ids,
        "title": title,
        "body": body,
        "topics": topics,
        "cover": {"type": "generated", "template": "title-card-v1"},
    }
    dedupe_key = None
    if payload.mode == "publish":
        dedupe_source = json.dumps(
            {
                "owner_uid": owner_uid,
                "artifact_id": artifact.id,
                "artifact_version": artifact.current_version,
                **snapshot,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        dedupe_key = hashlib.sha256(dedupe_source.encode()).hexdigest()
        recent = await repo.get_recent_publish_job(
            dedupe_key,
            owner_uid,
            utc_now_naive() - timedelta(hours=24),
        )
        if recent is not None:
            results = await repo.list_distribution_results(recent.id)
            return {
                "job": _serialize_job(recent, results),
                "deduplicated": True,
                "dedupe_reason": "same_publish_within_24_hours",
            }
    job = await repo.create_distribution_job(
        owner_uid=owner_uid,
        artifact_id=artifact.id,
        artifact_version=artifact.current_version,
        mode=payload.mode,
        payload_snapshot=snapshot,
        idempotency_key=request_key,
        dedupe_key=dedupe_key,
        accounts=accounts,
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await repo.get_job_by_idempotency_key(request_key, owner_uid)
        if existing is None:
            raise
        results = await repo.list_distribution_results(existing.id)
        return {"job": _serialize_job(existing, results), "deduplicated": True}

    try:
        queue = await get_arq_pool()
        queued = await queue.enqueue_job(
            "process_xiaohongshu_distribution",
            job.id,
            _job_id=f"xhs-distribution:{job.id}",
        )
    except Exception as exc:
        job.status = "failed"
        job.error_code = "XHS_QUEUE_UNAVAILABLE"
        job.error_message = "分发队列暂不可用"
        job.completed_at = utc_now_naive()
        await db.commit()
        raise _error(503, job.error_code, job.error_message, job_id=job.id, retryable=True) from exc
    if queued is None:
        job.status = "failed"
        job.error_code = "XHS_QUEUE_REJECTED"
        job.error_message = "分发任务未能进入执行队列"
        job.completed_at = utc_now_naive()
        await db.commit()
        raise _error(503, "XHS_QUEUE_REJECTED", job.error_message, job_id=job.id, retryable=True)
    results = await repo.list_distribution_results(job.id)
    return {"job": _serialize_job(job, results), "deduplicated": False}


async def get_distribution_job(db: AsyncSession, user: User, job_id: str) -> dict[str, Any]:
    repo = XiaohongshuRepository(db)
    job = await repo.get_distribution_job(job_id, _owner_uid(user))
    if job is None:
        raise _error(404, "XHS_DISTRIBUTION_NOT_FOUND", "分发任务不存在")
    return {"job": _serialize_job(job, await repo.list_distribution_results(job.id))}


async def list_artifact_distributions(
    db: AsyncSession, user: User, artifact_id: str
) -> dict[str, Any]:
    owner_uid = _owner_uid(user)
    artifact = await ContentRepository(db).get_artifact(artifact_id)
    if artifact is None or artifact.created_by != owner_uid:
        raise _error(404, "CONTENT_ARTIFACT_NOT_FOUND", "内容作品不存在")
    repo = XiaohongshuRepository(db)
    jobs = await repo.list_artifact_jobs(artifact_id, owner_uid)
    items = []
    for job in jobs:
        items.append(_serialize_job(job, await repo.list_distribution_results(job.id)))
    return {"items": items}


async def get_result_screenshot(
    db: AsyncSession, user: User, result_id: str
) -> Path:
    result = await XiaohongshuRepository(db).get_result(result_id, _owner_uid(user))
    if result is None or not result.screenshot_path:
        raise _error(404, "XHS_SCREENSHOT_NOT_FOUND", "执行截图不存在")
    path = Path(result.screenshot_path).resolve()
    runtime_root = Path(os.getenv("XHS_RUNTIME_ROOT", "/app/saves/xiaohongshu")).resolve()
    if not path.is_relative_to(runtime_root) or not path.is_file():
        raise _error(404, "XHS_SCREENSHOT_NOT_FOUND", "执行截图不存在")
    return path
