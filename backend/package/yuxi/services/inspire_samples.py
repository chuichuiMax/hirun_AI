"""聚光内容灵感样本：受控浏览器直抓、规范化和参考绑定。"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import uuid
from datetime import timedelta
from typing import Any
from urllib.parse import urlparse

from fastapi import HTTPException
from sqlalchemy import select

from yuxi.integrations.xiaohongshu import XiaohongshuRuntime, XiaohongshuRuntimeError
from yuxi.services.run_queue_service import get_arq_pool, get_redis_client
from yuxi.services.xiaohongshu_service import (
    browser_session_action,
    claim_browser_session,
    close_browser_session,
    get_browser_screenshot,
    get_browser_session,
    heartbeat_browser_session,
    open_browser_session,
)
from yuxi.storage.minio import get_minio_client
from yuxi.storage.postgres.models_business import User
from yuxi.storage.postgres.models_content import (
    ContentInspireCrawlRun,
    ContentInspireMedia,
    ContentInspireSample,
    ContentInspireSampleSnapshot,
    ContentTask,
    XiaohongshuAccount,
)
from yuxi.storage.postgres.manager import pg_manager
from yuxi.utils.datetime_utils import utc_now_naive

MAX_COVER_BYTES = 5 * 1024 * 1024


async def _cache_cover(*, cover_url: str | None, owner_uid: str, sample_id: str, now):
    """下载并缓存封面到 MinIO；失败时返回 None，由调用方标记媒体不完整。"""
    if not cover_url or urlparse(cover_url).scheme not in {"http", "https"}:
        return None
    try:
        import httpx

        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            response = await client.get(cover_url)
            response.raise_for_status()
            data = response.content
            if not data or len(data) > MAX_COVER_BYTES:
                return None
            content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
            if not content_type.startswith("image/"):
                return None
        digest = hashlib.sha256(data).hexdigest()
        extension = mimetypes.guess_extension(content_type) or ".bin"
        object_name = f"inspire-covers/{owner_uid}/{digest}{extension}"
        uploaded = await get_minio_client().aupload_file(
            bucket_name="public", object_name=object_name, data=data, content_type=content_type
        )
        media = ContentInspireMedia(
            id=f"icm_{uuid.uuid4().hex}",
            sample_id=sample_id,
            object_key=uploaded.object_name,
            sha256=digest,
            mime_type=content_type,
            fetched_at=now,
            expires_at=now + timedelta(seconds=TTL_SECONDS),
        )
        return uploaded.url, media
    except Exception:
        return None


INSPIRE_URL = "https://ad.xiaohongshu.com/microapp/creativity/inspire"
INSPIRE_HOST = "ad.xiaohongshu.com"
TTL_SECONDS = max(60, int(os.getenv("INSPIRE_SAMPLE_TTL_SECONDS", "3600")))
ADAPTER_VERSION = "dom-v1"
INDUSTRY_MAPPINGS = {
    "professional-services": {"label": "专业服务", "platform_industry": "本地生活"},
    "education": {"label": "教育培训", "platform_industry": "教育培训"},
    "beauty": {"label": "美业与个人护理", "platform_industry": "美妆个护"},
    "decoration": {"label": "装修与家居", "platform_industry": "家居家装"},
    "retail": {"label": "零售与电商", "platform_industry": "互联网"},
    "food": {"label": "餐饮与本地生活", "platform_industry": "食品饮料"},
}
INSPIRE_ACCOUNT_PREFIX = "xhsi_"


def _inspire_account_id(owner_uid: str) -> str:
    return f"{INSPIRE_ACCOUNT_PREFIX}{hashlib.sha256(owner_uid.encode()).hexdigest()[:32]}"


async def _ensure_inspire_account(db, user: User) -> XiaohongshuAccount:
    """创建仅供聚光浏览器持久化登录态使用的隐藏系统账号。"""
    owner_uid = str(user.uid)
    account_id = _inspire_account_id(owner_uid)
    account = await db.get(XiaohongshuAccount, account_id)
    if account is None:
        account = XiaohongshuAccount(
            id=account_id,
            owner_uid=owner_uid,
            display_name="聚光平台（系统会话）",
            enabled=True,
            login_status="unbound",
        )
        db.add(account)
        await db.commit()
    return account


async def open_inspire_browser_session(db, user: User) -> dict[str, Any]:
    account = await _ensure_inspire_account(db, user)
    return await open_browser_session(db, user, account.id, target="inspire")


async def get_inspire_browser_session(db, user: User) -> dict[str, Any]:
    account = await _ensure_inspire_account(db, user)
    return await get_browser_session(db, user, account.id, target="inspire")


async def heartbeat_inspire_browser_session(db, user: User) -> dict[str, Any]:
    account = await _ensure_inspire_account(db, user)
    return await heartbeat_browser_session(db, user, account.id, target="inspire")


async def claim_inspire_browser_session(db, user: User) -> dict[str, Any]:
    account = await _ensure_inspire_account(db, user)
    return await claim_browser_session(db, user, account.id)


async def act_inspire_browser_session(db, user: User, payload: dict[str, Any]) -> dict[str, Any]:
    account = await _ensure_inspire_account(db, user)
    return await browser_session_action(db, user, account.id, payload, target="inspire")


async def get_inspire_browser_screenshot(db, user: User) -> bytes:
    account = await _ensure_inspire_account(db, user)
    return await get_browser_screenshot(db, user, account.id, target="inspire")


async def close_inspire_browser_session(db, user: User) -> dict[str, Any]:
    account = await _ensure_inspire_account(db, user)
    return await close_browser_session(db, user, account.id)


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, {"error": {"code": code, "message": message, "retryable": status >= 500}})


def _assert_industry(slug: str) -> None:
    if slug not in INDUSTRY_MAPPINGS:
        raise _error(422, "INSPIRE_INVALID_INDUSTRY", "不支持的聚光赛道")


def _source_hash(raw: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _metric_value(value: str) -> int | None:
    text = value.strip().lower().replace(",", "")
    multiplier = 1
    if text.endswith("w"):
        text, multiplier = text[:-1], 10_000
    elif text.endswith("k"):
        text, multiplier = text[:-1], 1_000
    try:
        return int(float(text) * multiplier)
    except ValueError:
        return None


def build_reference_blueprint(title: str, body: str) -> dict[str, Any]:
    """只保存抽象结构，不保存可被误当作事实的原文句子。"""
    paragraphs = [item.strip() for item in body.splitlines() if item.strip()]
    return {
        "title_pattern": "短标题 + 具体场景/结果",
        "title_slot_sequence": ["topic", "audience_or_scene", "benefit_or_action"],
        "opening_hook": "问题/场景切入",
        "content_block_sequence": ["hook", "context", "steps_or_points", "closing"],
        "narrative_structure": "problem_solution",
        "paragraph_rhythm": {"paragraph_count": min(max(len(paragraphs), 3), 8), "short_paragraphs": True},
        "list_pattern": {"type": "numbered" if any(p[:2].strip(".、").isdigit() for p in paragraphs) else "none"},
        "emoji_pattern": {"present": any(ch in body for ch in "✨🌟✅📌"), "max_per_paragraph": 1},
        "interaction_style": "question_or_call_to_action",
    }


def normalize_inspire_item(raw: dict[str, Any], industry_slug: str, rank: int) -> dict[str, Any]:
    _assert_industry(industry_slug)
    url = str(raw.get("canonical_url") or raw.get("url") or "").strip()
    if not url:
        raise ValueError("样本缺少来源 URL")
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != INSPIRE_HOST:
        raise ValueError("样本来源不在聚光允许域名")
    title = str(raw.get("title") or "").strip()
    if not title:
        raise ValueError("样本标题为空")
    body = str(raw.get("body") or raw.get("content") or "").strip()
    tags = raw.get("tags") or raw.get("topics") or []
    if isinstance(tags, str):
        tags = [item.strip().lstrip("#") for item in tags.split() if item.strip()]
    metrics = raw.get("metrics") if isinstance(raw.get("metrics"), dict) else {}
    normalized = {
        "note_id": str(raw.get("note_id") or raw.get("id") or "").strip() or None,
        "canonical_url": url,
        "title": title,
        "body": body,
        "tags": [str(item).strip() for item in tags if str(item).strip()][:30],
        "cover_url": str(raw.get("cover_url") or raw.get("cover") or "").strip() or None,
        "author_name": str(raw.get("author_name") or raw.get("author") or "").strip() or None,
        "metrics": {
            str(key): value
            for key, value in metrics.items()
            if key in {"likes", "comments", "collects", "shares", "views"}
        },
        "industry_slug": industry_slug,
        "rank": rank,
    }
    normalized["source_hash"] = _source_hash(
        {
            "canonical_url": normalized["canonical_url"],
            "title": normalized["title"],
            "body": normalized["body"],
            "tags": normalized["tags"],
            "cover_url": normalized["cover_url"],
        }
    )
    normalized["reference_blueprint"] = build_reference_blueprint(title, body)
    return normalized


class InspireDirectCrawler:
    """仅访问聚光灵感页及其同域详情页的只读浏览器适配器。"""

    async def collect(self, *, owner_uid: str, account_id: str, industry_slug: str, limit: int) -> list[dict[str, Any]]:
        _assert_industry(industry_slug)
        if limit > 10:
            raise ValueError("单赛道最多采集 10 条")
        from patchright.async_api import async_playwright

        runtime = XiaohongshuRuntime(headless=True)
        async with async_playwright() as playwright:
            context = await runtime._launch_context(playwright, owner_uid, account_id)
            try:
                page = context.pages[0] if context.pages else await context.new_page()
                await page.goto(INSPIRE_URL, wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(1200)
                if not await runtime._is_inspire_logged_in(page):
                    raise XiaohongshuRuntimeError("INSPIRE_LOGIN_REQUIRED", "聚光平台登录已失效，请重新登录")
                await page.get_by_text("所属行业", exact=True).click()
                industry = INDUSTRY_MAPPINGS[industry_slug]["platform_industry"]
                option = page.get_by_text(industry, exact=True).last
                await option.wait_for(state="visible", timeout=10000)
                await option.click()
                cards = page.locator(".note-card")
                await cards.first.wait_for(state="visible", timeout=15000)
                await page.wait_for_timeout(800)
                items = []
                seen = set()
                for index in range(await cards.count()):
                    card = cards.nth(index)
                    await card.scroll_into_view_if_needed(timeout=10000)
                    title = (await card.locator(".note-meta > span").first.inner_text()).strip()
                    track = await card.get_attribute("data-track-impression") or ""
                    try:
                        note_id = str(json.loads(track).get("attributes", {}).get("triggerValue") or "")
                    except (TypeError, ValueError):
                        note_id = ""
                    identity = note_id or title
                    if not title or identity in seen:
                        continue
                    seen.add(identity)
                    image = card.locator(".note-covers img").first
                    cover_url = await image.get_attribute("src") if await image.count() else None
                    if cover_url and cover_url.startswith("http://"):
                        cover_url = "https://" + cover_url.removeprefix("http://")
                    metrics: dict[str, int] = {}
                    for tag in await card.locator(".note-meta .d-tag").all():
                        icon = await tag.locator("use").first.get_attribute("xlink:href")
                        key = {"#icon-like": "likes", "#icon-star": "collects", "#icon-comment": "comments"}.get(icon)
                        value = _metric_value((await tag.inner_text()).strip())
                        if key and value is not None:
                            metrics[key] = value
                    item = {
                        "note_id": note_id or None,
                        "canonical_url": (
                            f"{INSPIRE_URL}?note_id={note_id}"
                            if note_id
                            else f"{INSPIRE_URL}#rank-{index + 1}"
                        ),
                        "title": title,
                        "body": "",
                        "cover_url": cover_url,
                        "metrics": metrics,
                    }
                    items.append(normalize_inspire_item(item, industry_slug, len(items) + 1))
                    if len(items) >= limit:
                        break
                return items
            finally:
                await context.close()


async def list_inspire_samples(db, user: User, *, industry_slug: str, limit: int = 10) -> list[dict[str, Any]]:
    _assert_industry(industry_slug)
    now = utc_now_naive()
    samples = (
        (
            await db.execute(
                select(ContentInspireSample)
                .where(
                    ContentInspireSample.owner_uid == str(user.uid), ContentInspireSample.industry_slug == industry_slug
                )
                .order_by(ContentInspireSample.current_rank.asc().nullslast(), ContentInspireSample.updated_at.desc())
                .limit(min(limit, 10))
            )
        )
        .scalars()
        .all()
    )
    result = []
    for sample in samples:
        snapshot = (
            await db.execute(
                select(ContentInspireSampleSnapshot)
                .where(ContentInspireSampleSnapshot.sample_id == sample.id)
                .order_by(ContentInspireSampleSnapshot.fetched_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if snapshot is not None:
            media = (
                await db.execute(
                    select(ContentInspireMedia)
                    .where(ContentInspireMedia.sample_id == sample.id)
                    .order_by(ContentInspireMedia.fetched_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            result.append(_present_sample(sample, snapshot, now=now, include_body=False, media=media))
    return result


async def get_inspire_sample(db, user: User, sample_id: str) -> dict[str, Any]:
    row = (
        await db.execute(
            select(ContentInspireSample, ContentInspireSampleSnapshot)
            .join(ContentInspireSampleSnapshot, ContentInspireSampleSnapshot.sample_id == ContentInspireSample.id)
            .where(ContentInspireSample.id == sample_id, ContentInspireSample.owner_uid == str(user.uid))
            .order_by(ContentInspireSampleSnapshot.fetched_at.desc())
        )
    ).first()
    if not row:
        raise _error(404, "INSPIRE_SAMPLE_NOT_FOUND", "聚光样本不存在或无权访问")
    media = (
        await db.execute(
            select(ContentInspireMedia)
            .where(ContentInspireMedia.sample_id == row[0].id)
            .order_by(ContentInspireMedia.fetched_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return _present_sample(row[0], row[1], now=utc_now_naive(), include_body=True, media=media)


def _present_sample(sample, snapshot, *, now, include_body: bool, media=None) -> dict[str, Any]:
    expired = bool(snapshot.body_expires_at and snapshot.body_expires_at <= now)
    return {
        "id": sample.id,
        "snapshot_id": snapshot.id,
        "industry_slug": sample.industry_slug,
        "title": sample.title,
        "body": None if expired or not include_body else snapshot.body_text,
        "body_expired": expired,
        "tags": sample.tags_json or [],
        "cover_url": f"/api/content/inspire/media/{media.id}" if media else None,
        "media_id": media.id if media else None,
        "author_name": sample.author_name,
        "metrics": sample.metrics_json or {},
        "rank": sample.current_rank,
        "source_url": sample.canonical_url,
        "source_hash": sample.source_hash,
        "fetched_at": snapshot.fetched_at.isoformat() if snapshot.fetched_at else None,
        "reference_ready": bool(snapshot.reference_ready),
        "blueprint_version": snapshot.blueprint_version,
    }


async def create_inspire_crawl_runs(db, user: User, industry_slugs: list[str], limit: int = 10) -> list[dict[str, Any]]:
    slugs = list(dict.fromkeys(industry_slugs or INDUSTRY_MAPPINGS.keys()))
    if len(slugs) > 6:
        raise _error(422, "INSPIRE_TOO_MANY_INDUSTRIES", "一次最多采集六个赛道")
    for slug in slugs:
        _assert_industry(slug)
    account = await _ensure_inspire_account(db, user)
    if not account.enabled or account.login_status != "logged_in":
        raise _error(409, "INSPIRE_LOGIN_REQUIRED", "请先打开聚光平台并完成登录")
    runs = []
    queue = await get_arq_pool()
    for slug in slugs:
        run = ContentInspireCrawlRun(
            id=f"icr_{uuid.uuid4().hex}",
            owner_uid=str(user.uid),
            account_id=account.id,
            industry_slug=slug,
            query_json={"limit": limit, "mapping": INDUSTRY_MAPPINGS[slug]},
        )
        db.add(run)
        runs.append(run)
    await db.commit()
    for run in runs:
        await queue.enqueue_job("process_inspire_crawl", run.id, _job_id=f"inspire-crawl:{run.id}")
    return [{"id": run.id, "industry_slug": run.industry_slug, "status": run.status, "limit": limit} for run in runs]


async def get_inspire_crawl_run(db, user: User, run_id: str) -> dict[str, Any]:
    run = (
        await db.execute(
            select(ContentInspireCrawlRun).where(
                ContentInspireCrawlRun.id == run_id, ContentInspireCrawlRun.owner_uid == str(user.uid)
            )
        )
    ).scalar_one_or_none()
    if run is None:
        raise _error(404, "INSPIRE_CRAWL_NOT_FOUND", "采集任务不存在或无权访问")
    return {
        "id": run.id,
        "industry_slug": run.industry_slug,
        "status": run.status,
        "item_count": run.item_count,
        "error_code": run.error_code,
        "error_message": run.error_message,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


async def process_inspire_crawl(ctx, run_id: str) -> None:
    del ctx
    async with pg_manager.get_async_session_context() as db:
        run = await db.get(ContentInspireCrawlRun, run_id)
        if run is None:
            return
        run.status, run.started_at = "running", utc_now_naive()
        redis = await get_redis_client()
        lock = redis.lock(
            f"xhs:account-lock:{run.owner_uid}:{run.account_id}",
            timeout=3600,
            blocking_timeout=1,
        )
        if not await lock.acquire():
            run.status, run.error_code, run.error_message, run.finished_at = (
                "failed",
                "INSPIRE_ACCOUNT_BUSY",
                "聚光采集会话正在执行其他操作",
                utc_now_naive(),
            )
            return
        account = None
        try:
            account = (
                await db.execute(
                    select(XiaohongshuAccount).where(
                        XiaohongshuAccount.id == run.account_id,
                        XiaohongshuAccount.enabled.is_(True),
                        XiaohongshuAccount.login_status == "logged_in",
                        XiaohongshuAccount.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if account is None:
                raise XiaohongshuRuntimeError("INSPIRE_ACCOUNT_NOT_CONFIGURED", "聚光平台授权会话不可用")
            items = await InspireDirectCrawler().collect(
                owner_uid=account.owner_uid,
                account_id=run.account_id,
                industry_slug=run.industry_slug,
                limit=int((run.query_json or {}).get("limit", 10)),
            )
            now = utc_now_naive()
            media_failed = False
            for item in items:
                existing = (
                    await db.execute(
                        select(ContentInspireSample).where(
                            ContentInspireSample.owner_uid == run.owner_uid,
                            ContentInspireSample.provider == "xiaohongshu_inspire",
                            ContentInspireSample.canonical_url == item["canonical_url"],
                        )
                    )
                ).scalar_one_or_none()
                if existing is None:
                    existing = ContentInspireSample(
                        id=f"ics_{uuid.uuid4().hex}",
                        owner_uid=run.owner_uid,
                        provider="xiaohongshu_inspire",
                        canonical_url=item["canonical_url"],
                        title=item["title"],
                        source_hash=item["source_hash"],
                    )
                    db.add(existing)
                existing.note_id, existing.industry_slug = item.get("note_id"), run.industry_slug
                existing.title, existing.cover_url, existing.source_hash = (
                    item["title"],
                    item.get("cover_url"),
                    item["source_hash"],
                )
                existing.tags_json, existing.author_name = item.get("tags", []), item.get("author_name")
                existing.metrics_json, existing.current_rank, existing.updated_at = (
                    item.get("metrics", {}),
                    item.get("rank"),
                    now,
                )
                cached_cover = await _cache_cover(
                    cover_url=item.get("cover_url"),
                    owner_uid=run.owner_uid,
                    sample_id=existing.id,
                    now=now,
                )
                if cached_cover:
                    existing.cover_url, media = cached_cover
                    db.add(media)
                elif item.get("cover_url"):
                    existing.cover_url = None
                    media_failed = True
                snapshot = ContentInspireSampleSnapshot(
                    id=f"icss_{uuid.uuid4().hex}",
                    sample_id=existing.id,
                    raw_json={"title": item["title"], "tags": item.get("tags", []), "source_hash": item["source_hash"]},
                    body_text=item.get("body") or None,
                    body_expires_at=now + timedelta(seconds=TTL_SECONDS),
                    fetched_at=now,
                    adapter_version=ADAPTER_VERSION,
                    raw_hash=item["source_hash"],
                    reference_blueprint_json=item["reference_blueprint"],
                    reference_ready=True,
                )
                db.add(snapshot)
            run.item_count, run.status, run.finished_at = (
                len(items),
                "media_failed" if media_failed else "succeeded" if items else "partial",
                now,
            )
        except XiaohongshuRuntimeError as exc:
            run.status = "login_required" if exc.code == "INSPIRE_LOGIN_REQUIRED" else "failed"
            run.error_code, run.error_message, run.finished_at = exc.code, str(exc), utc_now_naive()
            if exc.code == "INSPIRE_LOGIN_REQUIRED" and account is not None:
                account.login_status = "expired"
                account.last_error_code = "XHS_LOGIN_REQUIRED"
                account.last_error_message = "聚光平台需要重新登录"
        except Exception as exc:
            run.status, run.error_code, run.error_message, run.finished_at = (
                "failed",
                "INSPIRE_CRAWL_FAILED",
                str(exc)[:1000],
                utc_now_naive(),
            )
        finally:
            await lock.release()


async def bind_inspire_reference(db, user: User, task_id: str, snapshot_id: str) -> dict[str, Any]:
    task = (
        await db.execute(
            select(ContentTask).where(
                ContentTask.id == task_id,
                ContentTask.created_by == str(user.uid),
                ContentTask.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if task is None:
        raise _error(404, "CONTENT_TASK_NOT_FOUND", "任务不存在或无权访问")
    if (task.runtime_config_snapshot_json or {}).get("creation_mode") != "viral_rewrite":
        raise _error(409, "INSPIRE_REWRITE_REQUIRED", "只有爆款仿写任务可以设为参考")
    snapshot = (
        await db.execute(
            select(ContentInspireSampleSnapshot).where(
                ContentInspireSampleSnapshot.id == snapshot_id, ContentInspireSampleSnapshot.reference_ready.is_(True)
            )
        )
    ).scalar_one_or_none()
    if snapshot is None:
        raise _error(409, "INSPIRE_REFERENCE_NOT_READY", "样本结构蓝图尚未准备完成")
    sample = await db.get(ContentInspireSample, snapshot.sample_id)
    if sample is None or sample.owner_uid != str(user.uid):
        raise _error(404, "INSPIRE_SAMPLE_NOT_FOUND", "聚光样本不存在或无权访问")
    runtime = dict(task.runtime_config_snapshot_json or {})
    runtime["selected_inspire_snapshot_id"] = snapshot.id
    runtime["selected_inspire_sample_id"] = sample.id
    runtime["selected_inspire_source_hash"] = sample.source_hash
    runtime["selected_inspire_blueprint_version"] = snapshot.blueprint_version
    task.runtime_config_snapshot_json = runtime
    task.updated_by = str(user.uid)
    await db.flush()
    return {
        "task_id": task.id,
        "sample": _present_sample(sample, snapshot, now=utc_now_naive(), include_body=False),
        "forced": True,
    }


async def get_inspire_media_url(db, user: User, media_id: str) -> str:
    media = await db.get(ContentInspireMedia, media_id)
    if media is None:
        raise _error(404, "INSPIRE_MEDIA_NOT_FOUND", "聚光媒体不存在")
    sample = await db.get(ContentInspireSample, media.sample_id)
    if sample is None or sample.owner_uid != str(user.uid):
        raise _error(404, "INSPIRE_MEDIA_NOT_FOUND", "聚光媒体不存在或无权访问")
    if media.expires_at and media.expires_at <= utc_now_naive():
        raise _error(410, "INSPIRE_MEDIA_EXPIRED", "聚光封面缓存已过期")
    return get_minio_client().get_presigned_url("public", media.object_key, days=1)
