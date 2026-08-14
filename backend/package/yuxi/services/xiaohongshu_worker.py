from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager

from yuxi.integrations.xiaohongshu import XiaohongshuRuntime, XiaohongshuRuntimeError
from yuxi.repositories.xiaohongshu_repository import XiaohongshuRepository
from yuxi.services.run_queue_service import get_redis_client
from yuxi.storage.postgres.manager import pg_manager
from yuxi.utils.datetime_utils import utc_now_naive
from yuxi.utils.logging_config import logger

ACCOUNT_LOCK_SECONDS = int(os.getenv("XHS_ACCOUNT_LOCK_SECONDS", "600"))
LOGIN_STATE_TTL_SECONDS = int(os.getenv("XHS_LOGIN_STATE_TTL_SECONDS", "300"))
_BROWSER_SEMAPHORE = asyncio.Semaphore(int(os.getenv("XHS_WORKER_MAX_JOBS", "1")))


def _login_key(session_id: str) -> str:
    return f"xhs:login:{session_id}"


def _account_lock_key(owner_uid: str, account_id: str) -> str:
    return f"xhs:account-lock:{owner_uid}:{account_id}"


async def _acquire_account_lock(owner_uid: str, account_id: str):
    redis = await get_redis_client()
    lock = redis.lock(
        _account_lock_key(owner_uid, account_id),
        timeout=ACCOUNT_LOCK_SECONDS,
        blocking_timeout=1,
    )
    if not await lock.acquire():
        raise XiaohongshuRuntimeError("XHS_ACCOUNT_BUSY", "该账号正在执行其他任务，请稍后再试")
    return lock


async def _release_lock(lock) -> None:
    try:
        await lock.release()
    except Exception as exc:
        logger.warning(f"Failed to release Xiaohongshu account lock: {exc}")


@asynccontextmanager
async def _browser_account_slot(owner_uid: str, account_id: str):
    async with _BROWSER_SEMAPHORE:
        lock = await _acquire_account_lock(owner_uid, account_id)
        try:
            yield
        finally:
            await _release_lock(lock)


async def process_xiaohongshu_login(ctx, session_id: str) -> None:
    del ctx
    redis = await get_redis_client()
    runtime = XiaohongshuRuntime()
    async with pg_manager.get_async_session_context() as db:
        repo = XiaohongshuRepository(db)
        session = await repo.get_login_session_for_worker(session_id)
        if session is None or session.status != "pending":
            return
        account = await repo.get_account_for_worker(session.account_id, session.owner_uid)
        if account is None or account.deleted_at is not None:
            session.status = "failed"
            session.error_code = "XHS_ACCOUNT_NOT_FOUND"
            session.error_message = "小红书账号不存在"
            session.completed_at = utc_now_naive()
            await db.commit()
            return

        try:
            async def publish_qr(qr_code: str) -> None:
                await redis.set(
                    _login_key(session.id),
                    json.dumps({"qr_code": qr_code, "tip": "请使用小红书 App 扫码登录"}, ensure_ascii=False),
                    ex=LOGIN_STATE_TTL_SECONDS,
                )

            async with _browser_account_slot(account.owner_uid, account.id):
                result = await asyncio.wait_for(
                    runtime.login(account.owner_uid, account.id, qr_callback=publish_qr),
                    timeout=180,
                )
            account.login_status = "logged_in"
            account.platform_nickname = str(result.get("nickname") or "") or None
            account.platform_account_id = str(result.get("account_id") or "") or None
            account.last_verified_at = utc_now_naive()
            account.last_error_code = None
            account.last_error_message = None
            session.status = "completed"
            session.completed_at = utc_now_naive()
            await redis.set(
                _login_key(session.id),
                json.dumps({"tip": "登录成功"}, ensure_ascii=False),
                ex=LOGIN_STATE_TTL_SECONDS,
            )
        except (XiaohongshuRuntimeError, TimeoutError) as exc:
            code = exc.code if isinstance(exc, XiaohongshuRuntimeError) else "XHS_LOGIN_EXPIRED"
            session.status = "expired" if code == "XHS_LOGIN_EXPIRED" else "failed"
            session.error_code = code
            session.error_message = str(exc) or "登录任务超时"
            session.completed_at = utc_now_naive()
            account.login_status = "expired" if session.status == "expired" else "error"
            account.last_error_code = code
            account.last_error_message = session.error_message
            await redis.set(
                _login_key(session.id),
                json.dumps({"tip": session.error_message}, ensure_ascii=False),
                ex=LOGIN_STATE_TTL_SECONDS,
            )
        finally:
            await db.commit()


async def process_xiaohongshu_status_check(ctx, account_id: str, owner_uid: str) -> None:
    del ctx
    runtime = XiaohongshuRuntime()
    async with pg_manager.get_async_session_context() as db:
        repo = XiaohongshuRepository(db)
        account = await repo.get_account_for_worker(account_id, owner_uid)
        if account is None or account.deleted_at is not None:
            return
        try:
            async with _browser_account_slot(owner_uid, account_id):
                result = await asyncio.wait_for(runtime.check_status(owner_uid, account_id), timeout=90)
            account.login_status = "logged_in" if result.get("logged_in") else "expired"
            account.platform_nickname = str(result.get("nickname") or "") or account.platform_nickname
            account.platform_account_id = str(result.get("account_id") or "") or account.platform_account_id
            account.last_verified_at = utc_now_naive()
            account.last_error_code = None if result.get("logged_in") else "XHS_LOGIN_REQUIRED"
            account.last_error_message = None if result.get("logged_in") else "账号登录已失效，请重新扫码"
        except Exception as exc:
            code = exc.code if isinstance(exc, XiaohongshuRuntimeError) else "XHS_STATUS_CHECK_FAILED"
            account.login_status = "error"
            account.last_error_code = code
            account.last_error_message = str(exc)
        finally:
            await db.commit()


async def process_xiaohongshu_profile_cleanup(ctx, account_id: str, owner_uid: str) -> None:
    del ctx
    lock = await _acquire_account_lock(owner_uid, account_id)
    try:
        XiaohongshuRuntime().remove_account_dir(owner_uid, account_id)
    finally:
        await _release_lock(lock)


async def process_xiaohongshu_distribution(ctx, job_id: str) -> None:
    del ctx
    runtime = XiaohongshuRuntime()
    async with pg_manager.get_async_session_context() as db:
        repo = XiaohongshuRepository(db)
        job = await repo.get_distribution_job_for_worker(job_id)
        if job is None or job.status not in {"queued", "running"}:
            return
        results = await repo.list_distribution_results(job.id)
        job.status = "running"
        job.started_at = job.started_at or utc_now_naive()
        await db.commit()

        succeeded = sum(result.status in {"draft_saved", "published"} for result in results)
        for result in results:
            if result.status in {"draft_saved", "published", "failed"}:
                continue
            if result.status == "running":
                result.status = "failed"
                result.error_code = "XHS_PREVIOUS_ATTEMPT_INTERRUPTED"
                result.error_message = (
                    "上次发布执行中断，无法确认平台结果，请先到小红书后台核对，系统不会自动重发"
                    if job.mode == "publish"
                    else "上次保存草稿时执行中断，无法确认平台结果，请先到小红书草稿箱核对"
                )
                result.completed_at = utc_now_naive()
                await db.commit()
                continue

            account = await repo.get_account_for_worker(result.account_id, job.owner_uid)
            if account is None or account.deleted_at is not None or not account.enabled:
                result.status = "failed"
                result.error_code = "XHS_ACCOUNT_NOT_READY"
                result.error_message = "账号不存在或已停用"
                result.completed_at = utc_now_naive()
                await db.commit()
                continue

            result.status = "running"
            result.started_at = utc_now_naive()
            await db.commit()
            try:
                payload = job.payload_snapshot or {}
                async with _browser_account_slot(job.owner_uid, account.id):
                    outcome = await asyncio.wait_for(
                        runtime.distribute(
                            job.owner_uid,
                            account.id,
                            job.id,
                            title=str(payload.get("title") or ""),
                            body=str(payload.get("body") or ""),
                            topics=[str(item) for item in payload.get("topics") or []],
                            mode=job.mode,
                        ),
                        timeout=360,
                    )
                result.status = "draft_saved" if job.mode == "draft" else "published"
                result.note_url = outcome.get("note_url") or None
                result.screenshot_path = outcome.get("screenshot_path") or None
                result.error_code = None
                result.error_message = None
                account.login_status = "logged_in"
                account.last_verified_at = utc_now_naive()
                succeeded += 1
            except Exception as exc:
                code = exc.code if isinstance(exc, XiaohongshuRuntimeError) else "XHS_DISTRIBUTION_TIMEOUT"
                result.status = "failed"
                result.error_code = code
                result.error_message = str(exc) or "分发任务超时"
                if code == "XHS_LOGIN_REQUIRED":
                    account.login_status = "expired"
                    account.last_error_code = code
                    account.last_error_message = result.error_message
            finally:
                result.completed_at = utc_now_naive()
                await db.commit()

        job.completed_at = utc_now_naive()
        if succeeded == len(results):
            job.status = "completed"
        elif succeeded:
            job.status = "partial_failed"
            job.error_code = "XHS_PARTIAL_FAILURE"
            job.error_message = "部分账号分发失败"
        else:
            job.status = "failed"
            job.error_code = "XHS_DISTRIBUTION_FAILED"
            job.error_message = "所有账号分发失败"
        await db.commit()
