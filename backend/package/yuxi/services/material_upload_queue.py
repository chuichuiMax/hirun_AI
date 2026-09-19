"""素材图片先入 Redis，再由队列落到 OSS/MinIO。"""

from __future__ import annotations

import io

from PIL import Image, ImageOps
from yuxi.services.run_queue_service import get_arq_pool, get_binary_redis_client
from yuxi.storage.minio import StorageError, get_minio_client
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_content import ContentCoverAsset
from yuxi.utils.logging_config import logger

MATERIAL_UPLOAD_REDIS_TTL_SECONDS = 3600
MATERIAL_THUMB_REDIS_TTL_SECONDS = 7 * 24 * 3600
MATERIAL_THUMBNAIL_SIZE = (720, 720)
INGEST_PENDING = "pending"
INGEST_READY = "ready"


def material_upload_redis_key(asset_id: str) -> str:
    return f"material:upload:{asset_id}"


def material_thumb_redis_key(asset_id: str) -> str:
    return f"material:thumb:{asset_id}"


def material_thumb_object_name(object_name: str) -> str:
    prefix, sep, _name = object_name.rpartition("/")
    return f"{prefix}/thumb.webp" if sep else f"{object_name}.thumb.webp"


def encode_material_thumbnail(data: bytes) -> bytes:
    with Image.open(io.BytesIO(data)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        image.thumbnail(MATERIAL_THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, format="WEBP", quality=72, method=4)
        return output.getvalue()


async def stage_material_bytes(asset_id: str, data: bytes) -> None:
    redis = await get_binary_redis_client()
    await redis.set(material_upload_redis_key(asset_id), data, ex=MATERIAL_UPLOAD_REDIS_TTL_SECONDS)


async def load_staged_material_bytes(asset_id: str) -> bytes | None:
    redis = await get_binary_redis_client()
    data = await redis.get(material_upload_redis_key(asset_id))
    return bytes(data) if data else None


async def delete_staged_material_bytes(asset_id: str) -> None:
    redis = await get_binary_redis_client()
    await redis.delete(material_upload_redis_key(asset_id))


async def delete_material_display_cache(asset_id: str) -> None:
    redis = await get_binary_redis_client()
    await redis.delete(material_upload_redis_key(asset_id), material_thumb_redis_key(asset_id))


async def stage_material_thumb(asset_id: str, data: bytes) -> None:
    redis = await get_binary_redis_client()
    await redis.set(material_thumb_redis_key(asset_id), data, ex=MATERIAL_THUMB_REDIS_TTL_SECONDS)


async def load_staged_material_thumb(asset_id: str) -> bytes | None:
    redis = await get_binary_redis_client()
    data = await redis.get(material_thumb_redis_key(asset_id))
    return bytes(data) if data else None


def ingest_status_of(asset: ContentCoverAsset) -> str:
    return str((asset.metadata_json or {}).get("ingest_status") or INGEST_READY)


async def read_material_bytes(asset: ContentCoverAsset) -> bytes:
    if ingest_status_of(asset) == INGEST_PENDING:
        staged = await load_staged_material_bytes(asset.id)
        if staged:
            return staged
    return await get_minio_client().adownload_file(asset.bucket_name, asset.object_name)


async def persist_material_thumbnail(
    asset: ContentCoverAsset,
    original: bytes | None = None,
    *,
    force_oss: bool = False,
) -> bytes:
    thumbnail = await load_staged_material_thumb(asset.id)
    storage = get_minio_client()
    thumb_name = material_thumb_object_name(asset.object_name)
    ready = ingest_status_of(asset) != INGEST_PENDING
    generated = False
    if thumbnail is None and ready:
        try:
            thumbnail = await storage.adownload_file(asset.bucket_name, thumb_name)
            await stage_material_thumb(asset.id, thumbnail)
            return thumbnail
        except StorageError:
            pass
    if thumbnail is None:
        source = original if original is not None else await read_material_bytes(asset)
        thumbnail = encode_material_thumbnail(source)
        await stage_material_thumb(asset.id, thumbnail)
        generated = True
    if ready and (force_oss or generated):
        try:
            await storage.aupload_file(asset.bucket_name, thumb_name, thumbnail, "image/webp")
        except StorageError:
            logger.warning("material thumb oss persist failed: asset={}", asset.id)
    return thumbnail


async def enqueue_material_oss_upload(asset_id: str) -> None:
    queue = await get_arq_pool()
    await queue.enqueue_job("process_material_upload", asset_id, _job_id=f"material-upload:{asset_id}")


async def process_material_upload(_ctx, asset_id: str) -> str:
    data = await load_staged_material_bytes(asset_id)
    if not data:
        logger.warning("material upload redis miss: asset={}", asset_id)
        return "missing"

    async with pg_manager.get_async_session_context() as db:
        asset = await db.get(ContentCoverAsset, asset_id)
        if asset is None or asset.deleted_at is not None:
            await delete_material_display_cache(asset_id)
            return "gone"
        if ingest_status_of(asset) == INGEST_READY:
            await delete_staged_material_bytes(asset_id)
            return "ready"
        try:
            uploaded = await get_minio_client().aupload_file(
                bucket_name=asset.bucket_name,
                object_name=asset.object_name,
                data=data,
                content_type=asset.content_type,
            )
        except StorageError:
            logger.exception("material upload oss failed: asset={}", asset_id)
            raise
        metadata = dict(asset.metadata_json or {})
        metadata["ingest_status"] = INGEST_READY
        metadata.pop("redis_key", None)
        asset.bucket_name = uploaded.bucket_name
        asset.object_name = uploaded.object_name
        asset.metadata_json = metadata
        await db.commit()
        await persist_material_thumbnail(asset, original=data, force_oss=True)
    await delete_staged_material_bytes(asset_id)
    return "uploaded"
