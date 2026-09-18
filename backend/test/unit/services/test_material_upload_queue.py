from __future__ import annotations

from types import SimpleNamespace

import pytest

import yuxi.services.material_upload_queue as material_upload_queue


class FakeBinaryRedis:
    def __init__(self):
        self.values: dict[str, bytes] = {}

    async def set(self, key: str, value: bytes, *, ex: int):
        self.values[key] = value

    async def get(self, key: str):
        return self.values.get(key)

    async def delete(self, *keys: str):
        for key in keys:
            self.values.pop(key, None)


@pytest.mark.asyncio
async def test_pending_material_reads_the_staged_bytes_before_minio(monkeypatch):
    redis = FakeBinaryRedis()

    async def get_redis():
        return redis

    monkeypatch.setattr(material_upload_queue, "get_binary_redis_client", get_redis)

    await material_upload_queue.stage_material_bytes("cca_pending", b"original")
    await material_upload_queue.stage_material_thumb("cca_pending", b"thumbnail")

    asset = SimpleNamespace(
        id="cca_pending",
        bucket_name="image",
        object_name="material-library/user/cca_pending.webp",
        metadata_json={
            "ingest_status": material_upload_queue.INGEST_PENDING,
            "redis_key": material_upload_queue.material_upload_redis_key("cca_pending"),
        },
    )

    assert await material_upload_queue.read_material_bytes(asset) == b"original"
    assert await material_upload_queue.read_staged_material_thumb("cca_pending") == b"thumbnail"
    assert material_upload_queue.material_thumb_object_name(asset.object_name).endswith(".thumb.webp")
