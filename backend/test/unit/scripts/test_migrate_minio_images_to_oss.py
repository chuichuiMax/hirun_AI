"""MinIO → OSS 图片迁移脚本单元测试。"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "migrate_minio_images_to_oss.py"
SPEC = importlib.util.spec_from_file_location("migrate_minio_images_to_oss", SCRIPT_PATH)
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class _Obj:
    def __init__(self, name: str, size: int):
        self.object_name = name
        self.size = size


class _FakeMinioSdk:
    def __init__(self, objects: dict[str, list[_Obj]]):
        self._objects = objects

    def bucket_exists(self, bucket_name: str) -> bool:
        return bucket_name in self._objects

    def list_objects(self, bucket_name: str, recursive: bool = False):
        return list(self._objects.get(bucket_name, []))


class _FakeMinio:
    def __init__(self, objects: dict[str, dict[str, bytes]]):
        self._data = objects
        listed = {bucket: [_Obj(name, len(data)) for name, data in items.items()] for bucket, items in objects.items()}
        self.client = _FakeMinioSdk(listed)

    def download_file(self, bucket_name: str, object_name: str) -> bytes:
        return self._data[bucket_name][object_name]

    def delete_file(self, bucket_name: str, object_name: str) -> bool:
        del self._data[bucket_name][object_name]
        return True

    def _guess_content_type(self, object_name: str) -> str:
        return "image/png"


class _FakeOss:
    def __init__(self):
        self.bucket = "hongyang01"
        self.store: dict[tuple[str, str], bytes] = {}

    def _object_key(self, bucket_name: str, object_name: str) -> str:
        return f"{bucket_name}/{object_name}"

    def file_exists(self, bucket_name: str, object_name: str) -> bool:
        return (bucket_name, object_name) in self.store

    def stat_file(self, bucket_name: str, object_name: str) -> int | None:
        data = self.store.get((bucket_name, object_name))
        return None if data is None else len(data)

    def upload_file(self, bucket_name: str, object_name: str, data: bytes, content_type=None):
        self.store[(bucket_name, object_name)] = data
        return SimpleNamespace(bucket_name=bucket_name, object_name=object_name, url=f"oss://{object_name}")

    def download_file(self, bucket_name: str, object_name: str) -> bytes:
        return self.store[(bucket_name, object_name)]


@pytest.mark.unit
def test_migrate_dry_run_does_not_write(tmp_path, monkeypatch):
    minio = _FakeMinio({"image": {"a.png": b"abc"}, "content-covers": {"b.png": b"dddd"}})
    oss = _FakeOss()
    monkeypatch.setattr("yuxi.storage.minio.client.MinIOClient", lambda: minio)
    monkeypatch.setattr("yuxi.storage.oss.client.OssStorageClient", lambda: oss)
    code = mod.migrate(
        buckets=["image", "content-covers"],
        apply=False,
        delete_source=False,
        limit=None,
        manifest_path=tmp_path / "m.jsonl",
    )
    assert code == 0
    assert oss.store == {}
    assert not (tmp_path / "m.jsonl").exists()


@pytest.mark.unit
def test_migrate_apply_copies_and_skips_existing(tmp_path, monkeypatch):
    minio = _FakeMinio({"image": {"a.png": b"abc", "b.png": b"zzzz"}})
    oss = _FakeOss()
    oss.store[("image", "a.png")] = b"abc"
    monkeypatch.setattr("yuxi.storage.minio.client.MinIOClient", lambda: minio)
    monkeypatch.setattr("yuxi.storage.oss.client.OssStorageClient", lambda: oss)
    code = mod.migrate(
        buckets=["image"],
        apply=True,
        delete_source=False,
        limit=None,
        manifest_path=tmp_path / "m.jsonl",
    )
    assert code == 0
    assert oss.store[("image", "b.png")] == b"zzzz"
    lines = (tmp_path / "m.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
