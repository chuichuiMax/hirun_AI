from __future__ import annotations

import hashlib
import re
import uuid
from typing import Any

from fastapi import HTTPException
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.content_cover.image2_settings import get_image2_config_state
from yuxi.agents import load_chat_model, resolve_chat_model_spec
from yuxi.repositories.material_library_repository import MaterialLibraryRepository
from yuxi.services.run_queue_service import get_arq_pool
from yuxi.storage.minio import get_minio_client
from yuxi.storage.postgres.models_business import User
from yuxi.storage.postgres.models_content import (
    ContentCoverAsset,
    ImageDesignClient,
    ImageDesignJob,
    ImageDesignShowcase,
)
from yuxi.utils.datetime_utils import utc_now_naive

from .schemas import (
    ASPECT_SIZES,
    DEFAULT_REFINE_MODEL_SPEC,
    ImageDesignClientCreate,
    ImageDesignGenerateCreate,
    ImageDesignShowcaseCreate,
)


def _owner_uid(user: User) -> str:
    return str(user.uid)


def _tenant_id(user: User) -> str | None:
    return str(user.department_id) if user.department_id is not None else None


def _error(code: str, message: str, code_status: int = 400, *, retryable: bool = False) -> HTTPException:
    return HTTPException(
        status_code=code_status,
        detail={"error": {"code": code, "message": message, "retryable": retryable}},
    )


def _serialize_job(job: ImageDesignJob) -> dict[str, Any]:
    data = job.to_dict()
    asset_ids = list((job.result_json or {}).get("asset_ids") or [])
    data["result_assets"] = [
        {"id": asset_id, "file_url": f"/api/image-design/results/{asset_id}/file"} for asset_id in asset_ids
    ]
    return data


def _serialize_result(asset: ContentCoverAsset) -> dict[str, Any]:
    metadata = asset.metadata_json or {}
    return {
        "id": asset.id,
        "file_url": f"/api/image-design/results/{asset.id}/file",
        "file_name": asset.original_file_name,
        "content_type": asset.content_type,
        "width": asset.image_width,
        "height": asset.image_height,
        "file_size": asset.file_size,
        "workflow": metadata.get("workflow"),
        "job_id": metadata.get("image_design_job_id"),
        "client_id": metadata.get("client_id"),
        "reference_material_id": metadata.get("reference_material_id"),
        "raw_room_material_id": metadata.get("raw_room_material_id"),
        "prompt": metadata.get("prompt", ""),
        "created_at": asset.created_at.isoformat() if asset.created_at else None,
    }


def _model_response_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return _clean_model_text(text)
    content = getattr(response, "content", None)
    if isinstance(content, str) and content.strip():
        return _clean_model_text(content)
    if isinstance(content, list):
        parts = [str(item.get("text", "")) for item in content if isinstance(item, dict)]
        text = "".join(parts).strip()
        if text:
            return _clean_model_text(text)
    raise ValueError("模型没有返回可用的润色结果")


def _clean_model_text(text: str) -> str:
    """去掉推理模型可能附带的思考段和 Markdown 包装，只保留最终提示词。"""
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()
    if "</think>" in cleaned:
        cleaned = cleaned.rsplit("</think>", 1)[-1].strip()
    cleaned = re.sub(r"^```(?:text|markdown)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = cleaned.strip('"“”')
    if not cleaned:
        raise ValueError("模型没有返回可用的润色结果")
    return cleaned


def _build_refine_messages(payload: Any) -> list[SystemMessage | HumanMessage]:
    workflow_labels = {
        "style_transfer": "原房换装",
        "room_adapt": "户型适配",
        "cross_space": "跨空间迁移",
    }
    workflow_rules = {
        "style_transfer": "保留参考图的墙体、门窗、层高、透视与镜头位置，只替换软装、家具、材质和灯光。",
        "room_adapt": "以毛坯实拍图的户型结构和镜头为准，将参考效果图的设计语言适配进去，不得照搬错误户型。",
        "cross_space": "只迁移参考图的风格、配色和材质语言，严格生成指定目标空间、布局及附加元素。",
    }
    return [
        SystemMessage(
            content=(
                "你是专业室内设计案例图提示词编辑。把用户想法改写成可直接用于 gpt-image-2 的中文提示词。"
                "必须保留用户明确要求，补足空间主体、材质、配色、自然或人工光线、镜头视角、景深和真实摄影质感；"
                "把约束写成肯定且可执行的画面描述。禁止输出解释、标题、编号、Markdown、文字水印或互相冲突的要求。"
                "最终只输出一段完整提示词，建议 180 至 500 个中文字符。"
            )
        ),
        HumanMessage(
            content=(
                f"工作流：{workflow_labels[payload.workflow]}\n"
                f"工作流硬约束：{workflow_rules[payload.workflow]}\n"
                f"风格：{payload.style_label or '以用户补充描述为准'}\n"
                f"风格补充：{payload.style_details or '无'}\n"
                f"目标空间：{payload.target_space_label or '沿用参考空间'}\n"
                f"布局：{payload.space_layout_desc or '沿用参考图布局'}\n"
                f"附加元素：{payload.space_addons_desc or '无'}\n"
                f"用户原始描述：{payload.user_prompt.strip()}"
            )
        ),
    ]


async def refine_prompt(payload: Any) -> str:
    model_spec = resolve_chat_model_spec(payload.model_spec, fallback=DEFAULT_REFINE_MODEL_SPEC)
    model = load_chat_model(fully_specified_name=model_spec)
    response = await model.ainvoke(_build_refine_messages(payload))
    result = _model_response_text(response)
    if result == payload.user_prompt.strip():
        raise ValueError("模型未产生有效的润色结果")
    if len(result) > 3000:
        result = result[:3000].rstrip()
    return result


async def _get_material_item_and_asset(db: AsyncSession, owner_uid: str, material_id: str):
    repo = MaterialLibraryRepository(db, include_shared=True)
    item = await repo.get_item_for_user(material_id, owner_uid)
    if item is None or item.material_type != "image" or item.status != "enabled":
        raise _error("IMAGE_DESIGN_MATERIAL_NOT_FOUND", "素材不存在、已下架或当前用户无权使用", 404)
    asset = await repo.get_asset(item.asset_id, item.owner_uid)
    if asset is None:
        raise _error("IMAGE_DESIGN_MATERIAL_FILE_MISSING", "素材文件不存在", 404)
    return item, asset


async def list_clients(db: AsyncSession, user: User) -> dict[str, Any]:
    owner_uid = _owner_uid(user)
    clients = list(
        (
            await db.execute(
                select(ImageDesignClient)
                .where(ImageDesignClient.owner_uid == owner_uid, ImageDesignClient.deleted_at.is_(None))
                .order_by(ImageDesignClient.created_at.asc())
            )
        ).scalars()
    )
    return {"clients": [client.to_dict() for client in clients], "general": {"id": None, "name": "通用素材库"}}


async def list_showcase(db: AsyncSession, user: User, category: str | None = None) -> dict[str, Any]:
    filters = [ImageDesignShowcase.enabled.is_(True)]
    if category:
        filters.append(ImageDesignShowcase.category == category)
    rows = list(
        (
            await db.execute(
                select(ImageDesignShowcase).where(*filters).order_by(desc(ImageDesignShowcase.created_at)).limit(100)
            )
        ).scalars()
    )
    # 查询时只返回当前用户有权读取的素材；失效案例不阻塞整页展示。
    items = []
    for row in rows:
        try:
            await _get_material_item_and_asset(db, _owner_uid(user), row.image_material_id)
        except HTTPException:
            continue
        item = row.to_dict()
        item["thumbnail_url"] = f"/api/material-library/items/{row.image_material_id}/thumbnail"
        items.append(item)
    categories = sorted({str(item["category"]) for item in items})
    return {"items": items, "categories": categories}


async def create_showcase(
    db: AsyncSession, user: User, payload: ImageDesignShowcaseCreate
) -> dict[str, Any]:
    await _get_material_item_and_asset(db, _owner_uid(user), payload.image_material_id)
    row = ImageDesignShowcase(
        id=f"ids_{uuid.uuid4().hex}",
        owner_uid=_owner_uid(user),
        title=payload.title,
        category=payload.category,
        style_text=payload.style_text,
        image_material_id=payload.image_material_id,
    )
    db.add(row)
    await db.commit()
    return {"item": row.to_dict()}


async def delete_showcase(db: AsyncSession, showcase_id: str) -> dict[str, Any]:
    row = await db.scalar(select(ImageDesignShowcase).where(ImageDesignShowcase.id == showcase_id))
    if row is None:
        raise _error("IMAGE_DESIGN_SHOWCASE_NOT_FOUND", "精选案例不存在", 404)
    row.enabled = False
    await db.commit()
    return {"success": True, "id": showcase_id}


async def create_client(db: AsyncSession, user: User, payload: ImageDesignClientCreate) -> dict[str, Any]:
    owner_uid = _owner_uid(user)
    client = ImageDesignClient(
        id=f"idc_{uuid.uuid4().hex}",
        owner_uid=owner_uid,
        tenant_id=_tenant_id(user),
        name=payload.name,
    )
    db.add(client)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _error("IMAGE_DESIGN_CLIENT_EXISTS", "客户名称已存在", 409) from exc
    return {"client": client.to_dict()}


async def get_bootstrap(db: AsyncSession, user: User) -> dict[str, Any]:
    image2 = await get_image2_config_state(db, owner_uid=_owner_uid(user))
    clients = await list_clients(db, user)
    return {
        "image2": image2,
        "clients": clients["clients"],
        "general_client": clients["general"],
        "aspect_sizes": ASPECT_SIZES,
        "refine_model_spec": DEFAULT_REFINE_MODEL_SPEC,
    }


async def validate_materials(db: AsyncSession, user: User, payload: ImageDesignGenerateCreate) -> dict[str, Any]:
    owner_uid = _owner_uid(user)
    reference_item, reference_asset = await _get_material_item_and_asset(db, owner_uid, payload.reference_material_id)
    raw_item = raw_asset = None
    if payload.workflow == "room_adapt":
        if not payload.raw_room_material_id:
            raise _error("IMAGE_DESIGN_RAW_ROOM_REQUIRED", "户型适配必须选择毛坯实拍图")
        raw_item, raw_asset = await _get_material_item_and_asset(db, owner_uid, payload.raw_room_material_id)
    if payload.workflow == "style_transfer" and not payload.style_label:
        if not payload.use_prompt_as_style or not payload.user_prompt.strip():
            raise _error("IMAGE_DESIGN_STYLE_REQUIRED", "原房换装请选择风格或使用补充描述作为风格提示词")
    if payload.workflow == "cross_space":
        if not payload.target_space or not payload.space_layout:
            raise _error("IMAGE_DESIGN_SPACE_REQUIRED", "跨空间迁移必须选择目标空间和布局")
        if not payload.user_prompt.strip():
            raise _error("IMAGE_DESIGN_PROMPT_REQUIRED", "跨空间迁移需要填写补充描述")
    if payload.client_id:
        client = await db.scalar(
            select(ImageDesignClient).where(
                ImageDesignClient.id == payload.client_id,
                ImageDesignClient.owner_uid == owner_uid,
                ImageDesignClient.deleted_at.is_(None),
            )
        )
        if client is None:
            raise _error("IMAGE_DESIGN_CLIENT_NOT_FOUND", "客户档案不存在", 404)
    return {
        "reference_item": reference_item,
        "reference_asset": reference_asset,
        "raw_item": raw_item,
        "raw_asset": raw_asset,
    }


async def create_generate_job(db: AsyncSession, user: User, payload: ImageDesignGenerateCreate) -> dict[str, Any]:
    image2 = await get_image2_config_state(db, owner_uid=_owner_uid(user))
    if not image2.get("configured"):
        raise _error("IMAGE_DESIGN_IMAGE2_NOT_CONFIGURED", "请先配置并验证 image2 中转站", 503, retryable=True)
    await validate_materials(db, user, payload)
    owner_uid = _owner_uid(user)
    prompt = payload.user_edited_preview or payload.user_prompt
    if not prompt.strip():
        raise _error("IMAGE_DESIGN_PROMPT_REQUIRED", "请填写补充描述")
    request = payload.model_dump(mode="json")
    request["prompt"] = prompt.strip()
    request["size"] = ASPECT_SIZES[payload.aspect_ratio][payload.clarity]
    request["material_ids"] = [payload.reference_material_id]
    if payload.raw_room_material_id:
        request["material_ids"].append(payload.raw_room_material_id)
    idempotency_key = payload.idempotency_key or hashlib.sha256(
        f"{owner_uid}:{uuid.uuid4().hex}".encode()
    ).hexdigest()
    existing = await db.scalar(
        select(ImageDesignJob).where(
            ImageDesignJob.owner_uid == owner_uid,
            ImageDesignJob.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        return {"job": _serialize_job(existing), "reused": True}
    job = ImageDesignJob(
        id=f"idj_{uuid.uuid4().hex}",
        owner_uid=owner_uid,
        tenant_id=_tenant_id(user),
        client_id=payload.client_id,
        workflow=payload.workflow,
        status="queued",
        request_json=request,
        result_json={"asset_ids": []},
        idempotency_key=idempotency_key,
        progress=0,
    )
    db.add(job)
    await db.flush()
    await db.commit()
    try:
        queue = await get_arq_pool()
        queued = await queue.enqueue_job("process_image_design_job", job.id, _job_id=f"image-design:{job.id}")
    except Exception as exc:
        job.status = "failed"
        job.error_code = "IMAGE_DESIGN_QUEUE_UNAVAILABLE"
        job.error_message = "图片设计生成队列暂不可用"
        job.completed_at = utc_now_naive()
        await db.commit()
        raise _error(job.error_code, job.error_message, 503, retryable=True) from exc
    if queued is None:
        job.status = "failed"
        job.error_code = "IMAGE_DESIGN_QUEUE_REJECTED"
        job.error_message = "图片设计任务未能进入执行队列"
        job.completed_at = utc_now_naive()
        await db.commit()
        raise _error(job.error_code, job.error_message, 503, retryable=True)
    return {"job": _serialize_job(job), "reused": False}


async def list_jobs(db: AsyncSession, user: User, *, client_id: str | None = None) -> dict[str, Any]:
    filters = [ImageDesignJob.owner_uid == _owner_uid(user)]
    if client_id:
        filters.append(ImageDesignJob.client_id == client_id)
    jobs = list(
        (
            await db.execute(
                select(ImageDesignJob).where(*filters).order_by(desc(ImageDesignJob.created_at)).limit(60)
            )
        ).scalars()
    )
    return {"jobs": [_serialize_job(job) for job in jobs], "total": len(jobs)}


async def get_job(db: AsyncSession, user: User, job_id: str) -> dict[str, Any]:
    job = await db.scalar(
        select(ImageDesignJob).where(ImageDesignJob.id == job_id, ImageDesignJob.owner_uid == _owner_uid(user))
    )
    if job is None:
        raise _error("IMAGE_DESIGN_JOB_NOT_FOUND", "图片设计任务不存在", 404)
    return {"job": _serialize_job(job)}


async def list_results(db: AsyncSession, user: User, *, client_id: str | None = None) -> dict[str, Any]:
    assets = list(
        (
            await db.execute(
                select(ContentCoverAsset)
                .where(
                    ContentCoverAsset.owner_uid == _owner_uid(user),
                    ContentCoverAsset.role == "output",
                    ContentCoverAsset.deleted_at.is_(None),
                )
                .order_by(desc(ContentCoverAsset.created_at))
                .limit(200)
            )
        ).scalars()
    )
    results = []
    for asset in assets:
        metadata = asset.metadata_json or {}
        if metadata.get("domain") != "image_design":
            continue
        if client_id and metadata.get("client_id") != client_id:
            continue
        results.append(_serialize_result(asset))
    return {"results": results[:60], "total": len(results)}


async def get_result_file(db: AsyncSession, user: User, asset_id: str) -> tuple[bytes, str, str]:
    asset = await db.scalar(
        select(ContentCoverAsset).where(
            ContentCoverAsset.id == asset_id,
            ContentCoverAsset.owner_uid == _owner_uid(user),
            ContentCoverAsset.role == "output",
            ContentCoverAsset.deleted_at.is_(None),
        )
    )
    if asset is None or (asset.metadata_json or {}).get("domain") != "image_design":
        raise _error("IMAGE_DESIGN_RESULT_NOT_FOUND", "图片设计结果不存在", 404)
    try:
        data = await get_minio_client().adownload_file(asset.bucket_name, asset.object_name)
    except Exception as exc:
        raise _error("IMAGE_DESIGN_STORAGE_FAILED", "图片设计结果读取失败", 500, retryable=True) from exc
    return data, asset.content_type, asset.original_file_name


async def delete_result(db: AsyncSession, user: User, asset_id: str) -> dict[str, Any]:
    asset = await db.scalar(
        select(ContentCoverAsset).where(
            ContentCoverAsset.id == asset_id,
            ContentCoverAsset.owner_uid == _owner_uid(user),
            ContentCoverAsset.role == "output",
            ContentCoverAsset.deleted_at.is_(None),
        )
    )
    if asset is None or (asset.metadata_json or {}).get("domain") != "image_design":
        raise _error("IMAGE_DESIGN_RESULT_NOT_FOUND", "图片设计结果不存在", 404)
    await get_minio_client().adelete_file(asset.bucket_name, asset.object_name)
    asset.deleted_at = utc_now_naive()
    await db.commit()
    return {"success": True, "id": asset_id}
