from __future__ import annotations

import importlib.util
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "migrate_default_image_galleries.py"


def _load_migration_module():
    spec = importlib.util.spec_from_file_location("migrate_default_image_galleries", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeManager:
    def __init__(self):
        self.initialized = 0
        self.tables_created = 0
        self.closed = 0

    def initialize(self):
        self.initialized += 1

    async def create_business_tables(self):
        self.tables_created += 1

    @asynccontextmanager
    async def get_async_session_context(self):
        yield object()

    async def close(self):
        self.closed += 1


@pytest.mark.asyncio
async def test_default_gallery_migration_is_dry_run_until_apply(monkeypatch):
    migration = _load_migration_module()
    manager = _FakeManager()
    synced = 0

    async def active_users(_db, _owner_uid):
        return []

    async def ensure_names(_db, _users):
        nonlocal synced
        synced += 1

    from yuxi.storage import minio
    from yuxi.storage.postgres import manager as postgres_manager

    monkeypatch.setattr(postgres_manager, "pg_manager", manager)
    monkeypatch.setattr(minio, "get_minio_client", object)
    monkeypatch.setattr(migration, "_active_users", active_users)
    monkeypatch.setattr(migration, "_ensure_names", ensure_names)

    assert await migration.migrate(apply=False, owner_uid=None) == 0
    assert (manager.initialized, manager.tables_created, synced, manager.closed) == (1, 0, 0, 1)

    assert await migration.migrate(apply=True, owner_uid=None) == 0
    assert (manager.initialized, manager.tables_created, synced, manager.closed) == (2, 1, 0, 2)


def test_retired_category_pairs_include_nested_galleries_per_owner():
    migration = _load_migration_module()
    categories = [
        SimpleNamespace(owner_uid="owner-1", id="scene-child", parent_id="scene"),
        SimpleNamespace(owner_uid="owner-1", id="scene-grandchild", parent_id="scene-child"),
        SimpleNamespace(owner_uid="owner-2", id="custom", parent_id=None),
    ]

    pairs = migration._retired_category_pairs(categories, {"owner-1", "owner-2"}, {"scene"})

    assert pairs == {
        ("owner-1", "scene"),
        ("owner-1", "scene-child"),
        ("owner-1", "scene-grandchild"),
        ("owner-2", "scene"),
    }


@pytest.mark.asyncio
async def test_delete_share_snapshot_removes_original_and_display_copy():
    migration = _load_migration_module()

    class Storage:
        def __init__(self):
            self.deleted = []

        async def adelete_file(self, bucket_name, object_name):
            self.deleted.append((bucket_name, object_name))

    storage = Storage()
    snapshot = SimpleNamespace(bucket_name="materials", object_name="material-library-shares/share/1.png")

    await migration._delete_share_snapshot(storage, snapshot)

    assert storage.deleted == [
        ("materials", "material-library-shares/share/1.png"),
        ("materials", "material-library-shares/share/1.png.display.webp"),
    ]
