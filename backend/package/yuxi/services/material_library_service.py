from __future__ import annotations

import hashlib
import io
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.repositories.content_cover_repository import ContentCoverRepository
from yuxi.repositories.material_library_repository import MaterialLibraryRepository
from yuxi.storage.minio import StorageError, get_minio_client
from yuxi.storage.postgres.models_business import User
from yuxi.storage.postgres.models_content import ContentCoverAsset, ContentMaterialLibraryItem
from yuxi.utils.datetime_utils import utc_now_naive
from yuxi.utils.upload_utils import read_upload_with_limit

MATERIAL_LIBRARY_BUCKET = "image"
MAX_MATERIAL_BYTES = 20 * 1024 * 1024
MAX_MATERIAL_DIMENSION = 8192
MAX_MATERIAL_PIXELS = 40_000_000


class MaterialItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    category: str | None = Field(default=None, min_length=1, max_length=80)
    tags: list[str] | None = Field(default=None, max_length=20)
    status: Literal["enabled", "disabled"] | None = None


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"error": {"code": code, "message": message}})


def _owner_uid(user: User) -> str:
    return str(user.uid)


def _tenant_id(user: User) -> str | None:
    return str(user.department_id) if user.department_id is not None else None


def _normalize_image(data: bytes) -> tuple[bytes, int, int, str]:
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.format not in {"JPEG", "PNG", "WEBP"}:
                raise _error(400, "MATERIAL_FORMAT_UNSUPPORTED", "仅支持 JPG、PNG 或 WebP 图片")
            image = ImageOps.exif_transpose(source)
            image.load()
            width, height = image.size
            if (
                width < 2
                or height < 2
                or max(width, height) > MAX_MATERIAL_DIMENSION
                or width * height > MAX_MATERIAL_PIXELS
            ):
                raise _error(400, "MATERIAL_DIMENSION_INVALID", "图片尺寸必须在 2–8192 像素且不超过 4000 万像素")
            output = io.BytesIO()
            image.convert("RGBA").save(output, format="PNG", optimize=True)
            return output.getvalue(), width, height, "image/png"
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise _error(400, "MATERIAL_IMAGE_INVALID", "上传文件不是有效图片") from exc


def serialize_item(item: ContentMaterialLibraryItem, asset: ContentCoverAsset) -> dict[str, Any]:
    result = item.to_dict()
    result.update(
        {
            "file_name": asset.original_file_name,
            "content_type": asset.content_type,
            "file_size": asset.file_size,
            "width": asset.image_width,
            "height": asset.image_height,
            "sha256": asset.sha256,
            "file_url": f"/api/material-library/items/{item.id}/file",
        }
    )
    return result


async def create_library_item_for_asset(
    db: AsyncSession,
    *,
    asset: ContentCoverAsset,
    material_type: Literal["image", "cover_template"],
    name: str,
    category: str = "未分类",
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> ContentMaterialLibraryItem:
    repo = MaterialLibraryRepository(db)
    existing = await repo.get_item_by_asset(asset.id)
    if existing is not None:
        return existing
    return await repo.create_item(
        id=f"mli_{uuid.uuid4().hex}",
        owner_uid=asset.owner_uid,
        tenant_id=asset.tenant_id,
        asset_id=asset.id,
        material_type=material_type,
        display_name=name.strip()[:255] or Path(asset.original_file_name).stem[:255],
        category=category.strip()[:80] or "未分类",
        tags_json=list(dict.fromkeys(tag.strip()[:40] for tag in tags or [] if tag.strip()))[:20],
        status="enabled",
        metadata_json=metadata or {},
    )


async def import_material_images(
    db: AsyncSession,
    user: User,
    files: list[UploadFile],
    *,
    category: str,
    tags: list[str],
) -> dict[str, Any]:
    if not files or len(files) > 50:
        raise _error(422, "MATERIAL_FILE_COUNT_INVALID", "每次必须上传 1–50 张图片")
    owner_uid = _owner_uid(user)
    normalized_category = category.strip()[:80] or "未分类"
    results: list[dict[str, Any]] = []
    for index, file in enumerate(files):
        if not file.filename:
            raise _error(400, "MATERIAL_FILE_NAME_REQUIRED", "无法识别上传文件名")
        try:
            raw = await read_upload_with_limit(
                file,
                max_size_bytes=MAX_MATERIAL_BYTES,
                too_large_message="图片过大，当前仅支持 20 MB 以内的文件",
            )
        except ValueError as exc:
            raise _error(400, "MATERIAL_IMAGE_TOO_LARGE", str(exc)) from exc
        normalized, width, height, content_type = _normalize_image(raw)
        if len(normalized) > MAX_MATERIAL_BYTES:
            raise _error(400, "MATERIAL_IMAGE_TOO_LARGE", "图片规范化后超过 20 MB")
        asset_id = f"cca_{uuid.uuid4().hex}"
        object_name = f"material-library/{owner_uid}/images/{asset_id}/image.png"
        try:
            uploaded = await get_minio_client().aupload_file(
                bucket_name=MATERIAL_LIBRARY_BUCKET,
                object_name=object_name,
                data=normalized,
                content_type=content_type,
            )
        except StorageError as exc:
            raise _error(500, "MATERIAL_STORAGE_FAILED", "素材保存失败") from exc
        try:
            asset = await ContentCoverRepository(db).create_asset(
                id=asset_id,
                owner_uid=owner_uid,
                tenant_id=_tenant_id(user),
                content_task_id=None,
                role="library_image",
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
            item = await create_library_item_for_asset(
                db,
                asset=asset,
                material_type="image",
                name=Path(file.filename).stem,
                category=normalized_category,
                tags=tags,
            )
            await db.commit()
        except Exception:
            await db.rollback()
            await get_minio_client().adelete_file(uploaded.bucket_name, uploaded.object_name)
            raise
        results.append(serialize_item(item, asset))
    return {"items": results, "summary": {"total": len(results), "created": len(results)}}


async def list_material_items(
    db: AsyncSession,
    user: User,
    *,
    material_type: str,
    category: str | None,
    status: str | None,
    query: str | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    if material_type not in {"image", "cover_template"}:
        raise _error(422, "MATERIAL_TYPE_INVALID", "素材类型不存在")
    rows, total = await MaterialLibraryRepository(db).list_items(
        _owner_uid(user),
        material_type=material_type,
        category=category,
        status=status,
        query_text=query,
        page=page,
        page_size=page_size,
    )
    return {
        "items": [serialize_item(item, asset) for item, asset in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def update_material_item(
    db: AsyncSession, user: User, item_id: str, payload: MaterialItemUpdate
) -> dict[str, Any]:
    repo = MaterialLibraryRepository(db)
    item = await repo.get_item_for_user(item_id, _owner_uid(user), for_update=True)
    if item is None:
        raise _error(404, "MATERIAL_NOT_FOUND", "素材不存在")
    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes:
        item.display_name = changes["name"].strip()
    if "category" in changes:
        item.category = changes["category"].strip()
    if "tags" in changes:
        item.tags_json = list(dict.fromkeys(tag.strip()[:40] for tag in changes["tags"] if tag.strip()))[:20]
    if "status" in changes:
        item.status = changes["status"]
    item.updated_at = utc_now_naive()
    asset = await repo.get_asset(item.asset_id, _owner_uid(user))
    if asset is None:
        raise _error(409, "MATERIAL_ASSET_MISSING", "素材文件记录不存在")
    poster = await repo.get_poster_template_by_asset(asset.id)
    if poster is not None:
        poster.name = item.display_name
        poster.category = item.category
        poster.tags_json = item.tags_json
    await db.commit()
    return {"item": serialize_item(item, asset)}


async def get_material_file(db: AsyncSession, user: User, item_id: str) -> tuple[bytes, str, str]:
    repo = MaterialLibraryRepository(db)
    item = await repo.get_item_for_user(item_id, _owner_uid(user))
    if item is None:
        raise _error(404, "MATERIAL_NOT_FOUND", "素材不存在")
    asset = await repo.get_asset(item.asset_id, _owner_uid(user))
    if asset is None:
        raise _error(404, "MATERIAL_ASSET_MISSING", "素材文件不存在")
    try:
        data = await get_minio_client().adownload_file(asset.bucket_name, asset.object_name)
    except StorageError as exc:
        raise _error(500, "MATERIAL_STORAGE_FAILED", "素材文件读取失败") from exc
    return data, asset.content_type, asset.original_file_name


async def delete_material_item(db: AsyncSession, user: User, item_id: str) -> dict[str, Any]:
    owner_uid = _owner_uid(user)
    repo = MaterialLibraryRepository(db)
    item = await repo.get_item_for_user(item_id, owner_uid, for_update=True)
    if item is None:
        raise _error(404, "MATERIAL_NOT_FOUND", "素材不存在")
    asset = await repo.get_asset(item.asset_id, owner_uid, for_update=True)
    if asset is None:
        raise _error(404, "MATERIAL_ASSET_MISSING", "素材文件不存在")
    cover_repo = ContentCoverRepository(db)
    referenced = await cover_repo.asset_is_in_active_job(asset.id, owner_uid)
    poster = await repo.get_poster_template_by_asset(asset.id)
    poster_referenced = poster is not None and await cover_repo.poster_template_is_in_active_job(poster.id, owner_uid)
    if referenced or poster_referenced:
        raise _error(409, "MATERIAL_IN_USE", "素材正在被封面任务使用，任务结束后再删除")
    try:
        await get_minio_client().adelete_file(asset.bucket_name, asset.object_name)
    except StorageError as exc:
        raise _error(500, "MATERIAL_STORAGE_FAILED", "素材文件删除失败") from exc
    deleted_at = utc_now_naive()
    item.deleted_at = deleted_at
    asset.deleted_at = deleted_at
    if poster is not None:
        poster.deleted_at = deleted_at
    await db.commit()
    return {"success": True, "id": item_id, "object_deleted": True}
