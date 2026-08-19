from __future__ import annotations

import asyncio
import hashlib
import io
import os
import uuid
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

from yuxi.content_cover.image2_client import Image2Client, Image2Error
from yuxi.content_cover.image2_settings import resolve_image2_config
from yuxi.content_cover.renderer import (
    CoverRenderError,
    apply_title_overlay,
    finalize_template_transfer,
    render_cover,
)
from yuxi.content_cover.schemas import Image2Input, Image2Request, Image2Submission
from yuxi.content_cover.templates import COVER_SIZES
from yuxi.repositories.content_cover_repository import ContentCoverRepository
from yuxi.services.run_queue_service import append_run_stream_event, clear_cancel_signal, has_cancel_signal
from yuxi.storage.minio.client import StorageError, get_minio_client
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_content import ContentCoverAsset, ContentCoverJob
from yuxi.utils.datetime_utils import utc_now_naive
from yuxi.utils.logging_config import logger

COVER_BUCKET = os.getenv("CONTENT_COVER_BUCKET", "content-covers")
POLL_INTERVAL_SECONDS = max(0.5, float(os.getenv("IMAGE2_POLL_INTERVAL_SECONDS", "2")))
POLL_TIMEOUT_SECONDS = max(30.0, float(os.getenv("IMAGE2_POLL_TIMEOUT_SECONDS", "900")))
IMAGE2_MAX_CONCURRENT = max(1, int(os.getenv("IMAGE2_MAX_CONCURRENT", "1")))
IMAGE2_SEMAPHORE = asyncio.Semaphore(IMAGE2_MAX_CONCURRENT)
MAX_OUTPUT_BYTES = 30 * 1024 * 1024
MAX_OUTPUT_PIXELS = 40_000_000


class CoverJobCancelled(Exception):
    pass


async def _emit(job_id: str, event_type: str, payload: dict[str, Any]) -> None:
    await append_run_stream_event(job_id, event_type, payload)


async def _set_job(job_id: str, **values: Any) -> ContentCoverJob | None:
    async with pg_manager.get_async_session_context() as db:
        job = await ContentCoverRepository(db).get_job(job_id, for_update=True)
        if job is None:
            return None
        if job.status in {"cancel_requested", "cancelled"} and values.get("status") != "cancelled":
            return job
        for key, value in values.items():
            setattr(job, key, value)
        await db.commit()
        return job


async def _record_provider_task(job: ContentCoverJob, index: int, task_id: str) -> None:
    result_json = dict(job.result_json or {})
    provider_task_ids = list(result_json.get("provider_task_ids") or [])
    while len(provider_task_ids) <= index:
        provider_task_ids.append(None)
    provider_task_ids[index] = task_id
    result_json["provider_task_ids"] = provider_task_ids
    job.provider_task_id = task_id
    job.result_json = result_json
    await _set_job(job.id, provider_task_id=task_id, result_json=result_json)


async def _check_cancelled(job_id: str) -> None:
    if await has_cancel_signal(job_id):
        raise CoverJobCancelled
    async with pg_manager.get_async_session_context() as db:
        job = await ContentCoverRepository(db).get_job(job_id)
        if job is None or job.status in {"cancel_requested", "cancelled"}:
            raise CoverJobCancelled


async def _finish_cancelled(job_id: str) -> None:
    await _set_job(
        job_id,
        status="cancelled",
        error_code="COVER_JOB_CANCELLED",
        error_message="用户已取消任务",
        completed_at=utc_now_naive(),
    )
    await _emit(job_id, "end", {"status": "cancelled"})


async def _download_asset(asset: ContentCoverAsset) -> bytes:
    try:
        return await get_minio_client().adownload_file(asset.bucket_name, asset.object_name)
    except StorageError as exc:
        raise RuntimeError(f"封面素材读取失败：{asset.id}") from exc


def _normalize_output(
    data: bytes,
    *,
    target_size: tuple[int, int] | None = None,
    title: str = "",
) -> tuple[bytes, int, int]:
    if len(data) > MAX_OUTPUT_BYTES:
        raise Image2Error("IMAGE2_IMAGE_TOO_LARGE", "image2 返回的图片超过 30 MB")
    try:
        with Image.open(io.BytesIO(data)) as source:
            source_width, source_height = source.size
            if (
                source_width < 2
                or source_height < 2
                or max(source_width, source_height) > 8192
                or source_width * source_height > MAX_OUTPUT_PIXELS
            ):
                raise Image2Error("IMAGE2_INVALID_IMAGE", "image2 返回的图片尺寸无效")
            image = ImageOps.exif_transpose(source).convert("RGBA")
            image.load()
            if target_size and image.size != target_size:
                image = ImageOps.fit(image, target_size, Image.Resampling.LANCZOS, centering=(0.5, 0.5))
            if title.strip():
                image = apply_title_overlay(image, title)
            image = image.convert("RGB")
            width, height = image.size
            output = io.BytesIO()
            image.save(output, format="PNG", optimize=True)
            return output.getvalue(), width, height
    except Image2Error:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise Image2Error("IMAGE2_INVALID_IMAGE", "image2 返回的内容不是有效图片") from exc


async def _store_outputs(job: ContentCoverJob, outputs: list[bytes]) -> list[str]:
    asset_ids: list[str] = []
    uploaded_objects: list[tuple[str, str]] = []
    requested_size = COVER_SIZES.get((job.request_json or {}).get("size") or "")
    target_size = (requested_size["width"], requested_size["height"]) if requested_size is not None else None
    title = str((job.request_json or {}).get("title") or "").strip()
    template_replicate = bool((job.request_json or {}).get("template_replicate"))
    try:
        async with pg_manager.get_async_session_context() as db:
            repo = ContentCoverRepository(db)
            for index, raw in enumerate(outputs):
                normalized, width, height = _normalize_output(
                    raw,
                    target_size=target_size,
                    title="" if template_replicate else title,
                )
                asset_id = f"cca_{uuid.uuid4().hex}"
                object_name = f"content-covers/{job.owner_uid}/{job.id}/output-{index + 1}.png"
                uploaded = await get_minio_client().aupload_file(
                    bucket_name=COVER_BUCKET,
                    object_name=object_name,
                    data=normalized,
                    content_type="image/png",
                )
                uploaded_objects.append((uploaded.bucket_name, uploaded.object_name))
                await repo.create_asset(
                    id=asset_id,
                    owner_uid=job.owner_uid,
                    tenant_id=job.tenant_id,
                    content_task_id=job.content_task_id,
                    role="output",
                    original_file_name=f"cover-{index + 1}.png",
                    content_type="image/png",
                    file_size=len(normalized),
                    image_width=width,
                    image_height=height,
                    sha256=hashlib.sha256(normalized).hexdigest(),
                    bucket_name=uploaded.bucket_name,
                    object_name=uploaded.object_name,
                    metadata_json={
                        "job_id": job.id,
                        "mode": job.mode,
                        "template_replicate": template_replicate,
                        "generation_strategy": (
                            "image2_multi_reference_full_canvas" if template_replicate else "default"
                        ),
                    },
                )
                asset_ids.append(asset_id)
            await db.commit()
    except Exception:
        for bucket_name, object_name in uploaded_objects:
            try:
                await get_minio_client().adelete_file(bucket_name, object_name)
            except Exception:
                logger.warning("Failed to clean cover output object: %s/%s", bucket_name, object_name)
        raise
    return asset_ids


async def _load_job_assets(
    job: ContentCoverJob,
) -> tuple[list[ContentCoverAsset], ContentCoverAsset | None, ContentCoverAsset | None]:
    request = job.request_json or {}
    source_ids = request.get("asset_ids") if job.mode == "compose" else request.get("source_asset_ids")
    source_ids = list(source_ids or [])
    async with pg_manager.get_async_session_context() as db:
        repo = ContentCoverRepository(db)
        sources = await repo.get_assets_for_user(source_ids, job.owner_uid)
        if len(sources) != len(source_ids):
            raise RuntimeError("封面任务引用的原图已不存在")
        template = None
        if request.get("template_asset_id"):
            template = await repo.get_asset_for_user(request["template_asset_id"], job.owner_uid)
            if template is None:
                raise RuntimeError("封面任务引用的模板图已不存在")
        mask = None
        if request.get("mask_asset_id"):
            mask = await repo.get_asset_for_user(request["mask_asset_id"], job.owner_uid)
            if mask is None:
                raise RuntimeError("封面任务引用的蒙版图已不存在")
        return sources, template, mask


async def _run_compose(job: ContentCoverJob) -> list[bytes]:
    sources, _, _ = await _load_job_assets(job)
    await _check_cancelled(job.id)
    image_bytes = [await _download_asset(asset) for asset in sources]
    request = job.request_json or {}
    rendered = await asyncio.to_thread(
        render_cover,
        image_bytes,
        template_id=request["template_id"],
        theme_id=request["theme_id"],
        size=request["size"],
        layout=request.get("layout") or {},
    )
    return [rendered]


async def _as_image2_input(asset: ContentCoverAsset) -> Image2Input:
    return Image2Input(
        data=await _download_asset(asset),
        content_type=asset.content_type,
        file_name=asset.original_file_name,
    )


def _compact_template_reference(data: bytes, file_name: str) -> Image2Input:
    """Keep multipart references lossless while preserving their composition."""
    try:
        with Image.open(io.BytesIO(data)) as source:
            image = ImageOps.exif_transpose(source).convert("RGBA")
            image.thumbnail((1536, 1536), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.save(output, format="PNG", optimize=True)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise CoverRenderError("模板复刻素材不是有效图片") from exc
    stem = file_name.rsplit(".", 1)[0] or "reference"
    return Image2Input(
        data=output.getvalue(),
        content_type="image/png",
        file_name=f"{stem}-reference.png",
    )


async def _load_image2_config(owner_uid: str):
    async with pg_manager.get_async_session_context() as db:
        return await resolve_image2_config(db, owner_uid=owner_uid)


async def _poll_image2(
    job: ContentCoverJob,
    client: Image2Client,
    result: Image2Submission,
    *,
    progress_start: int,
    progress_end: int,
    deadline: float,
) -> Image2Submission:
    if result.status != "pending":
        return result
    if not result.provider_task_id:
        raise Image2Error("IMAGE2_INVALID_RESPONSE", "image2 异步响应缺少任务 ID")
    await _set_job(
        job.id,
        provider_task_id=result.provider_task_id,
        status="polling",
        progress=progress_start,
    )
    await _emit(job.id, "progress", {"status": "polling", "progress": progress_start})
    loop = asyncio.get_running_loop()
    progress = progress_start
    while loop.time() < deadline:
        await _check_cancelled(job.id)
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
        result = await client.poll(result.provider_task_id)
        if result.status == "completed":
            return result
        if result.status == "failed":
            raise Image2Error("IMAGE2_GENERATION_FAILED", result.error_message or "image2 生成失败")
        progress = min(progress_end, progress + 2)
        await _set_job(job.id, progress=progress)
        await _emit(job.id, "progress", {"status": "polling", "progress": progress})
    raise Image2Error("IMAGE2_POLL_TIMEOUT", "image2 异步任务等待超时", retryable=True)


async def _run_image2(job: ContentCoverJob) -> list[bytes]:
    sources, template, mask = await _load_job_assets(job)
    request_data = job.request_json or {}
    await _check_cancelled(job.id)
    requested_count = int(request_data.get("n") or 1)
    template_replicate = bool(request_data.get("template_replicate"))
    template_data = None
    source_data = None
    requested_size = COVER_SIZES.get(request_data.get("size") or "")
    if template_replicate:
        if template is None or len(sources) != 1:
            raise CoverRenderError("模板复刻需要一张模板图和一张原图")
        if requested_size is None:
            raise CoverRenderError("模板复刻输出尺寸不支持")
        template_data, source_data = await asyncio.gather(
            _download_asset(template),
            _download_asset(sources[0]),
        )
        image2_request = Image2Request(
            mode="multi_reference",
            prompt=request_data.get("prompt") or "",
            negative_prompt=request_data.get("negative_prompt"),
            size=request_data.get("size") or "1080x1440",
            n=1,
            source_images=[_compact_template_reference(source_data, sources[0].original_file_name)],
            template_image=_compact_template_reference(
                template_data,
                template.original_file_name,
            ),
            extra=request_data.get("parameters") or {},
        )
    else:
        image2_request = Image2Request(
            mode=job.mode,
            prompt=request_data.get("prompt") or "",
            negative_prompt=request_data.get("negative_prompt"),
            size=request_data.get("size") or "1080x1440",
            n=1,
            source_images=[await _as_image2_input(asset) for asset in sources],
            template_image=await _as_image2_input(template) if template else None,
            mask_image=await _as_image2_input(mask) if mask else None,
            extra=request_data.get("parameters") or {},
        )
    provider_task_ids = list((job.result_json or {}).get("provider_task_ids") or [])
    if not provider_task_ids and job.provider_task_id:
        provider_task_ids.append(job.provider_task_id)
    outputs: list[bytes] = []
    deadline = asyncio.get_running_loop().time() + POLL_TIMEOUT_SECONDS
    image2_config = await _load_image2_config(job.owner_uid)
    async with Image2Client(image2_config) as client:
        for index in range(requested_count):
            await _check_cancelled(job.id)
            progress_start = 20 + int(index * 60 / requested_count)
            progress_end = 20 + int((index + 1) * 60 / requested_count)
            if index < len(provider_task_ids) and provider_task_ids[index]:
                result = Image2Submission(provider_task_id=provider_task_ids[index], status="pending")
            else:
                await _emit(job.id, "progress", {"status": "submitting", "progress": progress_start})
                idempotency_key = job.id if requested_count == 1 else f"{job.id}:{index}"
                result = await client.submit(image2_request, idempotency_key=idempotency_key)
                if result.provider_task_id:
                    await _record_provider_task(job, index, result.provider_task_id)
            result = await _poll_image2(
                job,
                client,
                result,
                progress_start=progress_start,
                progress_end=progress_end,
                deadline=deadline,
            )
            if not result.images:
                raise Image2Error("IMAGE2_RESULT_EMPTY", "image2 任务完成但没有返回图片")
            download_progress = progress_end
            await _set_job(job.id, status="downloading", progress=download_progress)
            await _emit(
                job.id,
                "progress",
                {"status": "downloading", "progress": download_progress},
            )
            raw = (await client.read_output(result.images[0]))[0]
            if template_replicate:
                if template_data is None or source_data is None or requested_size is None:
                    raise CoverRenderError("模板复刻上下文缺失")
                template_texts = request_data.get("template_texts") or {}
                raw = await asyncio.to_thread(
                    finalize_template_transfer,
                    template_data,
                    source_data,
                    raw,
                    target_size=(requested_size["width"], requested_size["height"]),
                    title=str(template_texts.get("title") or request_data.get("title") or ""),
                    subtitle=str(template_texts.get("subtitle") or ""),
                    tags=list(template_texts.get("tags") or []),
                )
            outputs.append(raw)
    return outputs


async def process_content_cover_job(ctx: dict, job_id: str) -> None:
    del ctx
    cancelled_before_start = False
    async with pg_manager.get_async_session_context() as db:
        job = await ContentCoverRepository(db).get_job(job_id, for_update=True)
        if job is None:
            logger.warning("Cover job not found: %s", job_id)
            return
        if job.status in {"succeeded", "failed", "cancelled"}:
            return
        if job.status == "cancel_requested":
            job.status = "cancelled"
            job.error_code = "COVER_JOB_CANCELLED"
            job.error_message = "用户已取消任务"
            job.completed_at = utc_now_naive()
            cancelled_before_start = True
        else:
            job.status = "running"
            job.progress = 5
            job.started_at = job.started_at or utc_now_naive()
            job.error_code = None
            job.error_message = None
        await db.commit()

    if cancelled_before_start:
        await _emit(job_id, "end", {"status": "cancelled"})
        await clear_cancel_signal(job_id)
        return

    await _emit(job_id, "metadata", {"job_id": job_id, "mode": job.mode})
    await _emit(job_id, "progress", {"status": "running", "progress": 5})
    try:
        if job.mode == "compose":
            outputs = await _run_compose(job)
        else:
            async with IMAGE2_SEMAPHORE:
                outputs = await _run_image2(job)
        await _check_cancelled(job_id)
        await _set_job(job_id, status="saving", progress=92)
        await _check_cancelled(job_id)
        await _emit(job_id, "progress", {"status": "saving", "progress": 92})
        asset_ids = await _store_outputs(job, outputs)
        updated = await _set_job(
            job_id,
            status="succeeded",
            progress=100,
            result_json={**(job.result_json or {}), "asset_ids": asset_ids},
            completed_at=utc_now_naive(),
        )
        if updated is not None and updated.status in {"cancel_requested", "cancelled"}:
            raise CoverJobCancelled
        await _emit(job_id, "result", {"asset_ids": asset_ids})
        await _emit(job_id, "end", {"status": "succeeded", "progress": 100})
    except CoverJobCancelled:
        await _finish_cancelled(job_id)
    except (Image2Error, CoverRenderError) as exc:
        code = exc.code if isinstance(exc, Image2Error) else "COVER_RENDER_FAILED"
        retryable = exc.retryable if isinstance(exc, Image2Error) else False
        updated = await _set_job(
            job_id,
            status="failed",
            error_code=code,
            error_message=str(exc),
            completed_at=utc_now_naive(),
        )
        if updated is not None and updated.status in {"cancel_requested", "cancelled"}:
            await _finish_cancelled(job_id)
            return
        await _emit(job_id, "error", {"code": code, "message": str(exc), "retryable": retryable})
        await _emit(job_id, "end", {"status": "failed"})
    except Exception as exc:
        logger.exception("Cover job failed: %s", job_id)
        updated = await _set_job(
            job_id,
            status="failed",
            error_code="COVER_WORKER_FAILED",
            error_message=str(exc)[:1000],
            completed_at=utc_now_naive(),
        )
        if updated is not None and updated.status in {"cancel_requested", "cancelled"}:
            await _finish_cancelled(job_id)
            return
        await _emit(job_id, "error", {"code": "COVER_WORKER_FAILED", "message": "封面任务执行失败"})
        await _emit(job_id, "end", {"status": "failed"})
    finally:
        await clear_cancel_signal(job_id)
