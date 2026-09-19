from __future__ import annotations

import io
from types import SimpleNamespace

import pytest
from PIL import Image

import yuxi.services.material_upload_queue as material_upload_queue


class FakeBinaryRedis:
class FakeRedis:
    def __init__(self):
        self.values: dict[str, bytes] = {}
        self.store: dict[str, bytes] = {}

    async def set(self, key: str, value: bytes, *, ex: int):
        self.values[key] = value
    async def set(self, key, data, ex=None):
        del ex
        self.store[key] = data

    async def get(self, key: str):
        return self.values.get(key)
    async def get(self, key):
        return self.store.get(key)

    async def delete(self, *keys: str):
    async def delete(self, *keys):
        for key in keys:
            self.values.pop(key, None)
            self.store.pop(key, None)


class FakeStorage:
    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}
        self.uploaded: list[tuple[str, str, bytes, str | None]] = []

    async def aupload_file(self, bucket_name, object_name, data, content_type=None):
        self.objects[(bucket_name, object_name)] = data
        self.uploaded.append((bucket_name, object_name, data, content_type))
        return SimpleNamespace(bucket_name=bucket_name, object_name=object_name)

    async def adownload_file(self, bucket_name, object_name):
        data = self.objects.get((bucket_name, object_name))
        if data is None:
            raise StorageError("missing")
        return data


def _webp(size=(32, 24)) -> bytes:
    source = io.BytesIO()
    Image.new("RGB", size, "red").save(source, format="WEBP")
    return source.getvalue()


@pytest.mark.asyncio
async def test_pending_material_reads_the_staged_bytes_before_minio(monkeypatch):
    redis = FakeBinaryRedis()
async def test_stage_load_and_delete_material_bytes(monkeypatch):
    redis = FakeRedis()

    async def get_redis():
    async def fake_client():
        return redis

    monkeypatch.setattr(material_upload_queue, "get_binary_redis_client", get_redis)
    monkeypatch.setattr("yuxi.services.material_upload_queue.get_binary_redis_client", fake_client)
    await stage_material_bytes("cca_1", b"RIFF....WEBP")
    assert await load_staged_material_bytes("cca_1") == b"RIFF....WEBP"
    assert material_upload_redis_key("cca_1") in redis.store
    await delete_staged_material_bytes("cca_1")
    assert await load_staged_material_bytes("cca_1") is None

    await material_upload_queue.stage_material_bytes("cca_pending", b"original")
    await material_upload_queue.stage_material_thumb("cca_pending", b"thumbnail")

@pytest.mark.asyncio
async def test_process_material_upload_moves_redis_bytes_to_storage(monkeypatch):
    redis = FakeRedis()
    storage = FakeStorage()
    original = _webp()
    asset = SimpleNamespace(
        id="cca_queued",
        deleted_at=None,
        bucket_name="image",
        metadata_json={
            "ingest_status": material_upload_queue.INGEST_PENDING,
            "redis_key": material_upload_queue.material_upload_redis_key("cca_pending"),
        },
        object_name="material-library/u1/images/cca_queued/image.webp",
        content_type="image/webp",
    )

    class FakeSession:
        async def get(self, model, asset_id):
            del model
            return asset if asset_id == asset.id else None

        async def commit(self):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class FakeManager:
        def get_async_session_context(self):
            return FakeSession()

    async def fake_client():
        return redis

    monkeypatch.setattr("yuxi.services.material_upload_queue.get_binary_redis_client", fake_client)
    monkeypatch.setattr("yuxi.services.material_upload_queue.pg_manager", FakeManager())
    monkeypatch.setattr("yuxi.services.material_upload_queue.get_minio_client", lambda: storage)

    await stage_material_bytes(asset.id, original)
    result = await process_material_upload({}, asset.id)
    assert result == "uploaded"
    assert storage.uploaded[0] == ("image", asset.object_name, original, "image/webp")
    assert storage.uploaded[1][1] == material_thumb_object_name(asset.object_name)
    assert storage.uploaded[1][3] == "image/webp"
    assert storage.uploaded[1][2][8:12] == b"WEBP"
    assert ingest_status_of(asset) == INGEST_READY
    assert await load_staged_material_bytes(asset.id) is None
    assert await load_staged_material_thumb(asset.id) == storage.uploaded[1][2]


@pytest.mark.asyncio
async def test_persist_thumbnail_reuses_redis_without_rereading_original(monkeypatch):
    redis = FakeRedis()
    storage = FakeStorage()
    original = _webp((900, 600))
    asset = SimpleNamespace(
        id="cca_ready",
        bucket_name="image",
        object_name="material-library/u1/images/cca_ready/image.webp",
        metadata_json={"ingest_status": INGEST_READY},
    )
    storage.objects[(asset.bucket_name, asset.object_name)] = original

    async def fake_client():
        return redis

    monkeypatch.setattr("yuxi.services.material_upload_queue.get_binary_redis_client", fake_client)
    monkeypatch.setattr("yuxi.services.material_upload_queue.get_minio_client", lambda: storage)

    first = await persist_material_thumbnail(asset)
    assert first[8:12] == b"WEBP"
    assert storage.uploaded[-1][1] == material_thumb_object_name(asset.object_name)
    uploads = len(storage.uploaded)
    second = await persist_material_thumbnail(asset)
    assert second == first
    assert len(storage.uploaded) == uploads


def test_material_thumb_object_name_sits_beside_original():
    assert (
        material_thumb_object_name("material-library/u1/images/cca_1/image.webp")
        == "material-library/u1/images/cca_1/thumb.webp"
    )

    assert await material_upload_queue.read_material_bytes(asset) == b"original"
    assert await material_upload_queue.read_staged_material_thumb("cca_pending") == b"thumbnail"
    assert material_upload_queue.material_thumb_object_name(asset.object_name).endswith(".thumb.webp")

def test_encode_material_thumbnail_is_webp():
    data = encode_material_thumbnail(_webp((64, 48)))
    assert data[8:12] == b"WEBP"


def test_worker_registers_material_upload_job():
    assert process_material_upload in WorkerSettings.functions
