from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import re
import uuid
from collections.abc import AsyncIterator
from copy import deepcopy
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.content_cover import COVER_SIZES, COVER_TEMPLATES, COVER_THEMES
from yuxi.content_cover.image2_client import Image2Error
from yuxi.content_cover.image2_settings import (
    get_image2_config_state,
    resolve_image2_config,
    save_image2_config,
)
from yuxi.content_cover.schemas import (
    CoverComposeCreate,
    CoverGenerateCreate,
    CoverRetryCreate,
    Image2GlobalConfigUpdate,
)
from yuxi.repositories.content_cover_repository import ContentCoverRepository
from yuxi.repositories.content_repository import ContentRepository
from yuxi.services.run_queue_service import (
    get_arq_pool,
    get_last_run_stream_seq,
    list_run_stream_events,
    normalize_after_seq,
    publish_cancel_signal,
)
from yuxi.storage.minio.client import StorageError, get_minio_client
from yuxi.storage.postgres.models_business import User
from yuxi.storage.postgres.models_content import ContentArtifact, ContentCoverAsset, ContentCoverJob
from yuxi.utils.datetime_utils import utc_now_naive
from yuxi.utils.logging_config import logger
from yuxi.utils.upload_utils import read_upload_with_limit

COVER_BUCKET = os.getenv("CONTENT_COVER_BUCKET", "content-covers")
MAX_COVER_IMAGE_BYTES = 20 * 1024 * 1024
MAX_COVER_DIMENSION = 8192
MAX_COVER_PIXELS = 40_000_000
SUPPORTED_ROLES = {"source", "template", "mask"}
TERMINAL_COVER_STATUSES = {"succeeded", "failed", "cancelled"}


def _error(status_code: int, code: str, message: str, *, retryable: bool = False) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error": {"code": code, "message": message, "retryable": retryable}},
    )


def _owner_uid(user: User) -> str:
    return str(user.uid)


def _compact_cover_copy(value: str, *, limit: int) -> str:
    normalized = re.sub(r"https?://\S+", "", value or "")
    normalized = re.sub(r"[`#>*_\[\](){}]+", " ", normalized)
    normalized = re.sub(r"^[\s\-—–•·\d.、]+", "", normalized)
    normalized = re.sub(r"\s+", "", normalized).strip("，。！？；：,.!?;:—- ")
    if len(normalized) <= limit:
        return normalized
    clauses = [
        item.strip("，。！？；：,.!?;:—- ")
        for item in re.split(r"[，。！？；：,.!?;:—|｜]+", normalized)
        if item.strip()
    ]
    suitable = [item for item in clauses if 4 <= len(item) <= limit]
    return (suitable[0] if suitable else normalized[:limit]).strip("，。！？；：,.!?;:—- ")


def _template_texts(artifact: ContentArtifact | None, title: str) -> dict[str, Any]:
    summarized_title = _compact_cover_copy(title, limit=14)
    subtitle = ""
    tags: list[str] = []
    if artifact is not None:
        body = re.sub(r"[`#>*_\[\](){}]+", " ", artifact.body or "")
        sentences = [_compact_cover_copy(item, limit=24) for item in re.split(r"[。！？!?\n]+", body)]
        sentences = [item for item in sentences if 6 <= len(item) <= 24 and item != summarized_title]
        preferred = [
            item
            for item in sentences
            if any(keyword in item for keyword in ("帮助", "实现", "提升", "解决", "通过", "让", "适合"))
        ]
        subtitle = (preferred or sentences or [""])[0]
        tags = [_compact_cover_copy(str(topic).lstrip("#"), limit=10) for topic in (artifact.topics or [])]
        tags = [tag for tag in tags if tag][:3]
    return {
        "title": summarized_title,
        "subtitle": subtitle,
        "tags": tags,
        "preserve_fixed_copy": True,
        "source": "content_asset" if artifact is not None else "manual",
    }


def _linked_content_title(artifact: ContentArtifact | None, task: Any | None) -> str:
    artifact_title = str(getattr(artifact, "title", "") or "").strip()
    if artifact_title:
        return artifact_title
    selected = (getattr(task, "selected_title_json", None) or {}).get("title")
    return str(selected or getattr(task, "name", "") or "").strip()


def _tenant_id(user: User) -> str | None:
    return str(user.department_id) if user.department_id is not None else None


def serialize_asset(item: ContentCoverAsset) -> dict[str, Any]:
    data = item.to_dict()
    data["file_url"] = f"/api/content/covers/assets/{item.id}/file"
    return data


def serialize_job(item: ContentCoverJob) -> dict[str, Any]:
    data = item.to_dict()
    asset_ids = (item.result_json or {}).get("asset_ids") or []
    data["result_assets"] = [
        {"id": asset_id, "file_url": f"/api/content/covers/assets/{asset_id}/file"} for asset_id in asset_ids
    ]
    return data


async def get_cover_bootstrap(db: AsyncSession, user: User) -> dict[str, Any]:
    tasks, _ = await ContentRepository(db).list_tasks(user=user, page=1, page_size=30)
    image2_state = await get_image2_config_state(
        db,
        owner_uid=_owner_uid(user),
    )
    return {
        "templates": list(COVER_TEMPLATES.values()),
        "themes": list(COVER_THEMES.values()),
        "sizes": [{"id": key, **value} for key, value in COVER_SIZES.items()],
        "image2": {
            **image2_state,
            "modes": ["text_to_image", "image_to_image", "multi_reference", "mask"],
        },
        "content_tasks": [
            {"id": item.id, "name": item.name, "status": item.status, "updated_at": item.to_dict()["updated_at"]}
            for item in tasks
        ],
    }


def _normalize_upload(data: bytes, role: str) -> tuple[bytes, int, int, str]:
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.format not in {"JPEG", "PNG", "WEBP"}:
                raise _error(400, "COVER_IMAGE_FORMAT_UNSUPPORTED", "仅支持 JPG、PNG 或 WebP 图片")
            width, height = source.size
            if width < 2 or height < 2 or max(width, height) > MAX_COVER_DIMENSION or width * height > MAX_COVER_PIXELS:
                raise _error(400, "COVER_IMAGE_DIMENSION_INVALID", "图片尺寸必须在 2–8192 像素且不超过 4000 万像素")
            image = ImageOps.exif_transpose(source)
            image.load()
            width, height = image.size
            output = io.BytesIO()
            image.convert("RGBA").save(output, format="PNG", optimize=True)
            return output.getvalue(), width, height, "image/png"
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise _error(400, "COVER_IMAGE_INVALID", "上传文件不是有效图片") from exc


async def create_cover_asset(
    db: AsyncSession,
    user: User,
    file: UploadFile,
    *,
    role: str,
    content_task_id: str | None,
) -> dict[str, Any]:
    if role not in SUPPORTED_ROLES:
        raise _error(422, "COVER_ASSET_ROLE_INVALID", "素材角色必须是 source、template 或 mask")
    if not file.filename:
        raise _error(400, "COVER_FILE_NAME_REQUIRED", "无法识别上传文件名")
    if content_task_id:
        task = await ContentRepository(db).get_task_for_user(content_task_id, user)
        if task is None:
            raise _error(404, "CONTENT_TASK_NOT_FOUND", "内容任务不存在")
    try:
        raw = await read_upload_with_limit(
            file,
            max_size_bytes=MAX_COVER_IMAGE_BYTES,
            too_large_message="图片过大，当前仅支持 20 MB 以内的文件",
        )
    except ValueError as exc:
        raise _error(400, "COVER_IMAGE_TOO_LARGE", str(exc)) from exc
    if not raw:
        raise _error(400, "COVER_IMAGE_EMPTY", "上传图片不能为空")
    normalized, width, height, content_type = _normalize_upload(raw, role)
    if len(normalized) > MAX_COVER_IMAGE_BYTES:
        raise _error(400, "COVER_IMAGE_TOO_LARGE", "图片规范化后超过 20 MB，请降低分辨率后重试")
    owner_uid = _owner_uid(user)
    asset_id = f"cca_{uuid.uuid4().hex}"
    object_name = f"content-covers/{owner_uid}/{asset_id}/image.png"
    try:
        uploaded = await get_minio_client().aupload_file(
            bucket_name=COVER_BUCKET,
            object_name=object_name,
            data=normalized,
            content_type=content_type,
        )
    except StorageError as exc:
        raise _error(500, "COVER_STORAGE_FAILED", "封面素材保存失败", retryable=True) from exc
    try:
        item = await ContentCoverRepository(db).create_asset(
            id=asset_id,
            owner_uid=owner_uid,
            tenant_id=_tenant_id(user),
            content_task_id=content_task_id,
            role=role,
            original_file_name=Path(file.filename.replace("\\", "/")).name,
            content_type=content_type,
            file_size=len(normalized),
            image_width=width,
            image_height=height,
            sha256=hashlib.sha256(normalized).hexdigest(),
            bucket_name=uploaded.bucket_name,
            object_name=uploaded.object_name,
            metadata_json={"original_content_type": file.content_type or ""},
        )
        await db.commit()
    except Exception:
        await get_minio_client().adelete_file(uploaded.bucket_name, uploaded.object_name)
        raise
    return {"asset": serialize_asset(item)}


async def get_cover_asset_file(db: AsyncSession, user: User, asset_id: str) -> tuple[bytes, str, str]:
    item = await ContentCoverRepository(db).get_asset_for_user(asset_id, _owner_uid(user))
    if item is None:
        raise _error(404, "COVER_ASSET_NOT_FOUND", "封面素材不存在")
    try:
        data = await get_minio_client().adownload_file(item.bucket_name, item.object_name)
    except StorageError as exc:
        raise _error(500, "COVER_STORAGE_FAILED", "封面素材读取失败", retryable=True) from exc
    return data, item.content_type, item.original_file_name


async def delete_cover_asset(db: AsyncSession, user: User, asset_id: str) -> dict[str, bool]:
    repo = ContentCoverRepository(db)
    owner_uid = _owner_uid(user)
    item = await repo.get_asset_for_user(asset_id, owner_uid, for_update=True)
    if item is None:
        raise _error(404, "COVER_ASSET_NOT_FOUND", "封面素材不存在")
    if item.role == "output":
        raise _error(409, "COVER_OUTPUT_DELETE_FORBIDDEN", "生成结果需通过任务历史保留，不能单独删除")
    if await repo.asset_is_in_active_job(item.id, owner_uid):
        raise _error(409, "COVER_ASSET_IN_USE", "素材正在被封面任务使用，任务结束后再删除")
    try:
        await get_minio_client().adelete_file(item.bucket_name, item.object_name)
    except StorageError as exc:
        raise _error(500, "COVER_STORAGE_FAILED", "封面素材删除失败", retryable=True) from exc
    item.deleted_at = utc_now_naive()
    await db.commit()
    return {"success": True}


async def _resolve_artifact(db: AsyncSession, user: User, task_id: str | None) -> ContentArtifact | None:
    if not task_id:
        return None
    content_repo = ContentRepository(db)
    task = await content_repo.get_task_for_user(task_id, user)
    if task is None:
        raise _error(404, "CONTENT_TASK_NOT_FOUND", "内容任务不存在")
    return await content_repo.get_artifact_for_task(task.id)


async def _enqueue(db: AsyncSession, job: ContentCoverJob) -> None:
    await db.commit()
    try:
        queue = await get_arq_pool()
        queued = await queue.enqueue_job(
            "process_content_cover_job",
            job.id,
            _job_id=f"content-cover:{job.id}",
        )
    except Exception as exc:
        job.status = "failed"
        job.error_code = "COVER_QUEUE_UNAVAILABLE"
        job.error_message = "封面生成队列暂不可用"
        job.completed_at = utc_now_naive()
        await db.commit()
        raise _error(503, job.error_code, job.error_message, retryable=True) from exc
    if queued is None:
        job.status = "failed"
        job.error_code = "COVER_QUEUE_REJECTED"
        job.error_message = "封面任务未能进入执行队列"
        job.completed_at = utc_now_naive()
        await db.commit()
        raise _error(503, job.error_code, job.error_message, retryable=True)


async def _create_job(
    db: AsyncSession,
    user: User,
    *,
    mode: str,
    content_task_id: str | None,
    artifact_id: str | None,
    idempotency_key: str,
    request: dict[str, Any],
    parent_job_id: str | None = None,
    provider_task_id: str | None = None,
    initial_result_json: dict[str, Any] | None = None,
    model: str | None = None,
) -> tuple[ContentCoverJob, bool]:
    repo = ContentCoverRepository(db)
    owner_uid = _owner_uid(user)
    existing = await repo.get_job_by_idempotency(owner_uid, idempotency_key)
    if existing:
        return existing, True
    try:
        job = await repo.create_job(
            id=f"ccj_{uuid.uuid4().hex}",
            owner_uid=owner_uid,
            tenant_id=_tenant_id(user),
            content_task_id=content_task_id,
            artifact_id=artifact_id,
            parent_job_id=parent_job_id,
            mode=mode,
            status="queued",
            model=model or (os.getenv("IMAGE2_MODEL") or "").strip() or None,
            provider_task_id=provider_task_id,
            idempotency_key=idempotency_key,
            request_json=request,
            result_json=initial_result_json or {},
            progress=0,
        )
        await _enqueue(db, job)
        return job, False
    except IntegrityError:
        await db.rollback()
        existing = await repo.get_job_by_idempotency(owner_uid, idempotency_key)
        if existing:
            return existing, True
        raise


async def create_cover_compose_job(db: AsyncSession, user: User, payload: CoverComposeCreate) -> dict[str, Any]:
    template = COVER_TEMPLATES.get(payload.template_id)
    if template is None:
        raise _error(422, "COVER_TEMPLATE_INVALID", "封面版式不存在")
    if payload.theme_id not in COVER_THEMES:
        raise _error(422, "COVER_THEME_INVALID", "封面主题不存在")
    if not template["min_assets"] <= len(payload.asset_ids) <= template["max_assets"]:
        raise _error(
            422,
            "COVER_TEMPLATE_ASSET_COUNT_INVALID",
            f"{template['name']} 需要 {template['min_assets']}–{template['max_assets']} 张图片",
        )
    assets = await ContentCoverRepository(db).get_assets_for_user(
        payload.asset_ids,
        _owner_uid(user),
        for_update=True,
    )
    if len(assets) != len(payload.asset_ids) or any(item.role != "source" for item in assets):
        raise _error(422, "COVER_SOURCE_ASSET_INVALID", "拼图素材不存在或角色不正确")
    artifact = await _resolve_artifact(db, user, payload.content_task_id)
    request = payload.model_dump()
    job, deduplicated = await _create_job(
        db,
        user,
        mode="compose",
        content_task_id=payload.content_task_id,
        artifact_id=artifact.id if artifact else None,
        idempotency_key=payload.idempotency_key,
        request=request,
    )
    return {"job": serialize_job(job), "deduplicated": deduplicated}


async def _content_prompt(
    db: AsyncSession,
    user: User,
    task_id: str | None,
    prompt: str,
    *,
    allow_empty: bool = False,
) -> tuple[str, ContentArtifact | None, str]:
    artifact = await _resolve_artifact(db, user, task_id)
    sections = [prompt.strip()] if prompt.strip() else []
    linked_title = ""
    if task_id:
        task = await ContentRepository(db).get_task_for_user(task_id, user)
        linked_title = _linked_content_title(artifact, task)
        if task and artifact:
            sections.append(
                "根据以下内容资产生成小红书风格封面：\n"
                f"标题：{linked_title}\n"
                f"正文摘要：{artifact.body.strip()[:1500]}\n"
                f"话题：{'、'.join(artifact.topics or [])}"
            )
        elif task:
            sections.append(f"根据内容任务《{linked_title}》生成小红书风格封面。")
    if not sections:
        if not allow_empty:
            raise _error(422, "COVER_PROMPT_REQUIRED", "请填写封面生成提示词")
        sections.append("仅替换模板底图为原图，其余上层样式保持一致。")
    return "\n\n".join(sections), artifact, linked_title


async def create_cover_generate_job(db: AsyncSession, user: User, payload: CoverGenerateCreate) -> dict[str, Any]:
    try:
        image2_config = await resolve_image2_config(db, owner_uid=_owner_uid(user))
    except Image2Error as exc:
        raise _error(503, "IMAGE2_NOT_CONFIGURED", "image2 中转站尚未配置") from exc
    repo = ContentCoverRepository(db)
    owner_uid = _owner_uid(user)
    source_assets = await repo.get_assets_for_user(payload.source_asset_ids, owner_uid, for_update=True)
    if len(source_assets) != len(payload.source_asset_ids) or any(item.role != "source" for item in source_assets):
        raise _error(422, "COVER_SOURCE_ASSET_INVALID", "原图不存在或角色不正确")
    template = None
    if payload.template_asset_id:
        template = await repo.get_asset_for_user(payload.template_asset_id, owner_uid, for_update=True)
        if template is None or template.role != "template":
            raise _error(422, "COVER_TEMPLATE_ASSET_INVALID", "模板图不存在或角色不正确")
    mask = None
    if payload.mask_asset_id:
        mask = await repo.get_asset_for_user(payload.mask_asset_id, owner_uid, for_update=True)
        if mask is None or mask.role != "mask":
            raise _error(422, "COVER_MASK_ASSET_INVALID", "蒙版图不存在或角色不正确")
        source = source_assets[0]
        if (mask.image_width, mask.image_height) != (source.image_width, source.image_height):
            raise _error(422, "COVER_MASK_SIZE_MISMATCH", "蒙版尺寸必须与原图一致")
    template_replicate = payload.mode == "multi_reference" and bool(payload.template_asset_id)
    prompt, artifact, linked_title = await _content_prompt(
        db,
        user,
        payload.content_task_id,
        payload.prompt,
        allow_empty=template_replicate,
    )
    title = payload.title.strip() or linked_title[:60]
    template_texts = _template_texts(artifact, title) if template_replicate else None
    mode_guidance = {
        "text_to_image": "生成高点击率的小红书封面底图，构图简洁、主体突出、层次清晰。",
        "image_to_image": "保留原图主体身份与关键细节，优化构图、光影和小红书封面氛围，不要凭空替换主体。",
        "multi_reference": "综合所有参考图；保留原图主体，借鉴模板的布局与视觉语言，但不要照搬其中的文字或品牌元素。",
        "mask": "只优化蒙版指定区域，未指定区域保持原图结构与主体一致。",
    }
    if template_replicate:
        mode_guidance["multi_reference"] = (
            "严格模板复刻模式。参考图1是用户原图，参考图2是样式模板。最终封面必须以参考图1完整铺满画布，"
            "保留其人物、商品、空间、视角和关键细节；参考图2只提供上层视觉系统，不得保留其中的"
            "房间、人物、商品或任何底图内容。从参考图2迁移上层元素：标题和副标题的位置与层级、字体粗细和颜色关系、贴纸、图标、"
            "色块、线条、边框及角标；这些元素的坐标、尺寸比例、间距和整体风格应尽量与模板一致。"
            "严禁把参考图1缩小后塞入矩形、圆角卡片、相框或局部区域，"
            "严禁形成模板旧底图加新图卡片的套图。"
        )
        output_guidance = (
            "输出必须是单张完整、不透明的封面图。把参考图2视为透明上层，把其中所有可见文字、"
            "字体粗细、描边、阴影、贴纸、图标、色块和圆角文字条按原坐标、原比例迁移到参考图1。"
            "模板原文也是必须保留的上层样式，不得擦除、改写、翻译、模糊或变成伪文字；不得新增模板中"
            "不存在的卡片或装饰。参考图1的底图内容、手写字、表格、商品和人物必须保持清晰。"
            "系统会在生成后按内容资产需要精确替换主标题，因此不要自行扩写新口号或新段落。"
        )
    else:
        output_guidance = (
            "输出完整的封面视觉底图，左上区域预留干净、低细节的标题安全区。"
            "画面内不要生成任何文字、数字、字母、水印、平台 Logo 或伪造品牌标识；"
            "系统会在生成后叠加准确的中文标题。"
        )
    prompt = f"{mode_guidance[payload.mode]}\n{output_guidance}\n\n{prompt}"
    default_negative_prompt = (
        "乱码文字、错误汉字、随机字母、数字、水印、平台 Logo、伪造品牌标识、低清晰度、主体变形、过度锐化、杂乱背景"
    )
    if template_replicate:
        default_negative_prompt += (
            "、透明棋盘格、马赛克、模板旧底图残留、双重背景、画中画、原图缩小、"
            "原图置于卡片、圆角相框、白色大面板、新增边框、左右分栏、参考板、深色分隔线"
        )
    request = payload.model_dump()
    request["prompt"] = prompt
    request["title"] = title
    request["template_texts"] = template_texts
    request["template_replicate"] = template_replicate
    request["parameters"] = {
        **payload.parameters,
        **(
            {
                "template_replicate": True,
                "quality": "high",
                "input_fidelity": "high",
                "output_format": "png",
            }
            if template_replicate
            else {}
        ),
    }
    request["negative_prompt"] = "，".join(
        item for item in ((payload.negative_prompt or "").strip(), default_negative_prompt) if item
    )
    job, deduplicated = await _create_job(
        db,
        user,
        mode=payload.mode,
        content_task_id=payload.content_task_id,
        artifact_id=artifact.id if artifact else None,
        idempotency_key=payload.idempotency_key,
        request=request,
        model=image2_config.model,
    )
    return {"job": serialize_job(job), "deduplicated": deduplicated}


async def get_cover_job(db: AsyncSession, user: User, job_id: str) -> dict[str, Any]:
    job = await ContentCoverRepository(db).get_job_for_user(job_id, _owner_uid(user))
    if job is None:
        raise _error(404, "COVER_JOB_NOT_FOUND", "封面任务不存在")
    return {"job": serialize_job(job)}


async def list_cover_jobs(
    db: AsyncSession,
    user: User,
    *,
    content_task_id: str | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    items, total = await ContentCoverRepository(db).list_jobs(
        _owner_uid(user), content_task_id=content_task_id, page=page, page_size=page_size
    )
    return {"items": [serialize_job(item) for item in items], "total": total, "page": page, "page_size": page_size}


async def retry_cover_job(
    db: AsyncSession,
    user: User,
    job_id: str,
    payload: CoverRetryCreate,
    *,
    workflow_resume: dict[str, Any] | None = None,
) -> dict[str, Any]:
    old = await ContentCoverRepository(db).get_job_for_user(job_id, _owner_uid(user))
    if old is None:
        raise _error(404, "COVER_JOB_NOT_FOUND", "封面任务不存在")
    if old.status not in {"failed", "cancelled", "succeeded"}:
        raise _error(409, "COVER_JOB_NOT_RETRYABLE", "任务结束后才能重新生成")
    image2_config = None
    if old.mode != "compose":
        try:
            image2_config = await resolve_image2_config(db, owner_uid=_owner_uid(user))
        except Image2Error as exc:
            raise _error(503, "IMAGE2_NOT_CONFIGURED", "image2 中转站尚未配置") from exc
    recoverable_provider_task_id = None
    retry_result_json: dict[str, Any] = {}
    if old.provider_task_id and old.error_code in {
        "IMAGE2_POLL_TIMEOUT",
        "IMAGE2_NETWORK_ERROR",
        "IMAGE2_DOWNLOAD_FAILED",
        "IMAGE2_RESULT_EMPTY",
        "COVER_WORKER_FAILED",
    }:
        recoverable_provider_task_id = old.provider_task_id
        provider_task_ids = list((old.result_json or {}).get("provider_task_ids") or [])
        if provider_task_ids:
            retry_result_json["provider_task_ids"] = provider_task_ids
    request = deepcopy(old.request_json or {})
    if workflow_resume:
        resume_container = "layout" if old.mode == "compose" else "parameters"
        request[resume_container] = {
            **(request.get(resume_container) or {}),
            "workflow_resume": workflow_resume,
        }
    job, deduplicated = await _create_job(
        db,
        user,
        mode=old.mode,
        content_task_id=old.content_task_id,
        artifact_id=old.artifact_id,
        idempotency_key=payload.idempotency_key,
        request=request,
        parent_job_id=old.id,
        provider_task_id=recoverable_provider_task_id,
        initial_result_json=retry_result_json,
        model=image2_config.model if image2_config else None,
    )
    return {"job": serialize_job(job), "deduplicated": deduplicated}


async def update_image2_global_config(
    db: AsyncSession,
    user: User,
    payload: Image2GlobalConfigUpdate,
) -> dict[str, Any]:
    try:
        await save_image2_config(
            db,
            base_url=payload.base_url,
            api_key=payload.api_key,
            owner_uid=_owner_uid(user),
        )
    except Image2Error as exc:
        raise _error(422, exc.code, str(exc)) from exc
    return await get_image2_config_state(db, owner_uid=_owner_uid(user))


async def cancel_cover_job(db: AsyncSession, user: User, job_id: str) -> dict[str, Any]:
    job = await ContentCoverRepository(db).get_job_for_user(job_id, _owner_uid(user), for_update=True)
    if job is None:
        raise _error(404, "COVER_JOB_NOT_FOUND", "封面任务不存在")
    if job.status == "saving":
        raise _error(409, "COVER_JOB_TOO_LATE_TO_CANCEL", "封面结果正在保存，当前阶段不能取消")
    if job.status not in TERMINAL_COVER_STATUSES:
        job.status = "cancel_requested"
        await db.commit()
        try:
            await publish_cancel_signal(job.id)
        except Exception:
            logger.warning("Failed to publish cover cancellation signal: %s", job.id, exc_info=True)
    return {"job": serialize_job(job)}


async def set_current_cover(
    db: AsyncSession,
    user: User,
    job_id: str,
    *,
    asset_id: str | None = None,
) -> dict[str, Any]:
    repo = ContentCoverRepository(db)
    job = await repo.get_job_for_user(job_id, _owner_uid(user), for_update=True)
    if job is None:
        raise _error(404, "COVER_JOB_NOT_FOUND", "封面任务不存在")
    if job.status != "succeeded" or not (job.result_json or {}).get("asset_ids"):
        raise _error(409, "COVER_JOB_NOT_READY", "封面生成完成后才能设为当前封面")
    content_repo = ContentRepository(db)
    artifact_id = job.artifact_id
    if not artifact_id and job.content_task_id:
        current_artifact = await content_repo.get_artifact_for_task(job.content_task_id)
        artifact_id = current_artifact.id if current_artifact else None
    if not artifact_id:
        raise _error(409, "COVER_ARTIFACT_REQUIRED", "关联内容任务生成产物后才能设置当前封面")
    artifact = await content_repo.get_artifact_for_user(artifact_id, user, for_update=True)
    if artifact is None:
        raise _error(404, "CONTENT_ARTIFACT_NOT_FOUND", "内容产物不存在")
    if job.artifact_id is None:
        job.artifact_id = artifact.id
    result_asset_ids = list(job.result_json["asset_ids"])
    selected_asset_id = asset_id or result_asset_ids[0]
    if selected_asset_id not in result_asset_ids:
        raise _error(422, "COVER_RESULT_ASSET_INVALID", "所选图片不属于该封面任务")
    asset = await repo.get_asset_for_user(selected_asset_id, _owner_uid(user))
    if asset is None or asset.role != "output":
        raise _error(404, "COVER_ASSET_NOT_FOUND", "封面结果不存在")
    version = await repo.set_current_cover(artifact=artifact, asset=asset, job=job, owner_uid=_owner_uid(user))
    await db.commit()
    return {
        "artifact": artifact.to_dict(),
        "version": {"id": version.id, "version": version.version, "cover_asset_id": asset.id},
        "cover": serialize_asset(asset),
    }


def _format_sse(data: dict, *, event: str, event_id: str | None = None) -> str:
    lines = []
    if event_id:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    lines.append(f"data: {json.dumps(data, ensure_ascii=False)}")
    return "\n".join(lines) + "\n\n"


async def stream_cover_job_events(job_id: str, owner_uid: str, after_seq: str) -> AsyncIterator[str]:
    last_seq = normalize_after_seq(after_seq)
    heartbeat = 0
    while True:
        from yuxi.storage.postgres.manager import pg_manager

        async with pg_manager.get_async_session_context() as db:
            job = await ContentCoverRepository(db).get_job_for_user(job_id, owner_uid)
        if job is None:
            yield _format_sse({"message": "封面任务不存在"}, event="error")
            return
        events = await list_run_stream_events(job_id, after_seq=last_seq, limit=100)
        terminal_event = False
        for item in events:
            last_seq = str(item.get("seq") or last_seq)
            event_type = item.get("event_type") or "message"
            yield _format_sse(item.get("payload") or {}, event=event_type, event_id=last_seq)
            terminal_event = terminal_event or event_type == "end"
        if terminal_event:
            return
        if job.status in TERMINAL_COVER_STATUSES and not events:
            terminal_seq = await get_last_run_stream_seq(job_id)
            yield _format_sse(
                {"run_id": job_id, "event": "end", "payload": {"status": job.status}},
                event="end",
                event_id=terminal_seq if terminal_seq != "0-0" else None,
            )
            return
        heartbeat += 1
        if heartbeat % 15 == 0:
            yield ": heartbeat\n\n"
        await asyncio.sleep(1)
