from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from yuxi.storage.postgres.models_content import (
    ContentCoverAsset,
    ContentMaterialCategory,
    ContentMaterialLibraryItem,
    ImageDesignLibraryItem,
    ImageDesignMpDraft,
)


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        for model in (
            ContentCoverAsset,
            ContentMaterialCategory,
            ContentMaterialLibraryItem,
            ImageDesignLibraryItem,
            ImageDesignMpDraft,
        ):
            await connection.run_sync(model.__table__.create)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


def user(uid="employee"):
    return SimpleNamespace(uid=uid, department_id=1)


async def seed_material(db, *, visibility="enterprise", status="enabled"):
    category = ContentMaterialCategory(
        owner_uid="other",
        material_type="image",
        id="folder",
        name="Folder",
        visibility=visibility,
    )
    asset = ContentCoverAsset(
        id="asset",
        owner_uid="other",
        role="library_image",
        original_file_name="room.png",
        content_type="image/png",
        file_size=10,
        image_width=32,
        image_height=32,
        sha256="a" * 64,
        bucket_name="test",
        object_name="room.png",
    )
    item = ContentMaterialLibraryItem(
        id="source",
        owner_uid="other",
        asset_id="asset",
        category="folder",
        category_owner_uid="other",
        material_type="image",
        display_name="Room",
        status=status,
    )
    db.add_all([category, asset, item])
    await db.commit()
    return category, asset, item


def test_draft_schema_normalizes_slots_and_preserves_image_ids():
    from yuxi.image_design.mp_schemas import MpDraftsUpdate

    payload = MpDraftsUpdate.model_validate({"drafts": {"adapt": {"reference": {"id": "design-1"}}}})
    assert payload.model_dump()["drafts"] == {
        "redesign": {},
        "adapt": {"reference": {"id": "design-1"}},
        "transfer": {},
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"owner_uid": "victim", "drafts": {}},
        {"drafts": {"unknown": {}}},
        {"drafts": {"adapt": []}},
    ],
)
def test_draft_schema_rejects_owner_and_malformed_workflows(payload):
    from yuxi.image_design.mp_schemas import MpDraftsUpdate

    with pytest.raises(ValidationError):
        MpDraftsUpdate.model_validate(payload)


@pytest.mark.parametrize("source_role", ["source", "reference", "rough"])
def test_library_schema_accepts_each_workflow_source_role(source_role):
    from yuxi.image_design.mp_schemas import MpLibraryCreate

    payload = MpLibraryCreate(source_library_item_id="source", source_role=source_role)
    assert payload.source_role == source_role


async def test_drafts_read_and_replace_only_current_owner(db):
    from yuxi.image_design.mp_schemas import MpDraftsUpdate
    from yuxi.image_design.mp_service import get_drafts, save_drafts

    db.add(ImageDesignMpDraft(owner_uid="victim", drafts_json={"adapt": {"description": "private"}}))
    await db.commit()
    assert (await get_drafts(db, user()))["drafts"] == {"redesign": {}, "adapt": {}, "transfer": {}}
    payload = MpDraftsUpdate(drafts={"adapt": {"reference": {"id": "input-1"}}})
    await save_drafts(db, user(), payload)
    await save_drafts(db, user(), payload)
    assert (await get_drafts(db, user()))["drafts"]["adapt"]["reference"]["id"] == "input-1"
    assert (await get_drafts(db, user("victim")))["drafts"]["adapt"] == {"description": "private"}
    assert await db.scalar(select(func.count()).select_from(ImageDesignMpDraft)) == 2


async def test_library_deduplicates_owner_asset_and_keeps_owners_separate(db):
    from yuxi.image_design.mp_schemas import MpLibraryCreate
    from yuxi.image_design.mp_service import add_library_item, list_library

    await seed_material(db)
    payload = MpLibraryCreate(source_library_item_id="source", source_gallery_id="folder", source_role="reference")
    first = (await add_library_item(db, user(), payload))["item"]
    again = (await add_library_item(db, user(), payload))["item"]
    other = (await add_library_item(db, user("other"), payload))["item"]
    assert first["id"] == again["id"] != other["id"]
    assert first["file_url"] == f"/api/mp/image-design/library/{first['id']}/file"
    assert first["thumbnail_file_url"] == f"/api/mp/image-design/library/{first['id']}/thumbnail"
    assert first["asset_id"] == "asset"
    assert first["source_item_id"] == "source"
    assert [item["id"] for item in (await list_library(db, user(), page=1, page_size=1))["items"]] == [first["id"]]
    assert (await list_library(db, user(), page=2, page_size=1))["items"] == []
    assert await db.scalar(select(func.count()).select_from(ImageDesignLibraryItem)) == 2


async def test_generated_material_entry_is_visible_in_image_design_library(db):
    from yuxi.image_design.mp_service import list_library

    category = ContentMaterialCategory(
        owner_uid="employee",
        material_type="image",
        id="uncategorized",
        name="未分类",
        visibility="private",
        is_system=True,
    )
    asset = ContentCoverAsset(
        id="generated-asset",
        owner_uid="employee",
        role="output",
        original_file_name="generated.png",
        content_type="image/png",
        file_size=10,
        image_width=32,
        image_height=32,
        sha256="b" * 64,
        bucket_name="test",
        object_name="generated.png",
        metadata_json={"domain": "image_design"},
    )
    material = ContentMaterialLibraryItem(
        id="generated-material",
        owner_uid="employee",
        asset_id=asset.id,
        category=category.id,
        category_owner_uid=category.owner_uid,
        material_type="image",
        display_name="Generated",
        status="enabled",
    )
    entry = ImageDesignLibraryItem(
        id="generated-library-entry",
        owner_uid="employee",
        tenant_id="1",
        asset_id=asset.id,
        source_material_item_id=material.id,
        source_gallery_id=category.id,
        source_role="generated",
    )
    db.add_all([category, asset, material, entry])
    await db.commit()

    items = (await list_library(db, user(), page=1, page_size=100))["items"]
    assert [(item["id"], item["source_role"], item["source_item_id"]) for item in items] == [
        (entry.id, "generated", material.id)
    ]


@pytest.mark.parametrize(("visibility", "status"), [("private", "enabled"), ("enterprise", "disabled")])
async def test_library_rejects_inaccessible_or_disabled_source(db, visibility, status):
    from yuxi.image_design.mp_schemas import MpLibraryCreate
    from yuxi.image_design.mp_service import add_library_item

    await seed_material(db, visibility=visibility, status=status)
    with pytest.raises(HTTPException) as error:
        await add_library_item(db, user(), MpLibraryCreate(source_library_item_id="source", source_role="rough"))
    assert error.value.status_code == 404
    assert await db.scalar(select(func.count()).select_from(ImageDesignLibraryItem)) == 0


async def test_library_rejects_forged_gallery_and_owner(db):
    from yuxi.image_design.mp_schemas import MpLibraryCreate
    from yuxi.image_design.mp_service import add_library_item

    await seed_material(db)
    with pytest.raises(ValidationError):
        MpLibraryCreate(source_library_item_id="source", source_role="reference", owner_uid="victim")
    with pytest.raises(HTTPException) as error:
        await add_library_item(
            db,
            user(),
            MpLibraryCreate(
                source_library_item_id="source",
                source_gallery_id="forged",
                source_role="reference",
            ),
        )
    assert error.value.status_code == 422


async def test_existing_reference_rechecks_source_visibility_and_owner_on_read(db):
    from yuxi.image_design.mp_schemas import MpLibraryCreate
    from yuxi.image_design.mp_service import add_library_item, get_library_item_and_asset, list_library

    category, _, _ = await seed_material(db)
    item = (
        await add_library_item(
            db,
            user(),
            MpLibraryCreate(
                source_library_item_id="source",
                source_role="reference",
            ),
        )
    )["item"]
    with pytest.raises(HTTPException) as error:
        await get_library_item_and_asset(db, user("stranger"), item["id"])
    assert error.value.status_code == 404
    category.visibility = "private"
    await db.commit()
    with pytest.raises(HTTPException) as error:
        await get_library_item_and_asset(db, user(), item["id"])
    assert error.value.status_code == 404
    assert (await list_library(db, user(), page=1, page_size=100))["items"] == []


async def test_upload_creates_input_asset_and_dedicated_reference_only(db, monkeypatch):
    import io
    from fastapi import UploadFile
    from PIL import Image
    from yuxi.image_design.mp_service import upload_image
    from yuxi.storage import minio

    class Storage:
        async def aupload_file(self, *, bucket_name, object_name, data, content_type):
            assert Image.open(io.BytesIO(data)).size == (32, 24)
            return SimpleNamespace(bucket_name=bucket_name, object_name=object_name)

    monkeypatch.setattr(minio, "get_minio_client", lambda: Storage())
    raw = io.BytesIO()
    Image.new("RGB", (32, 24), "red").save(raw, format="PNG")
    raw.seek(0)
    result = await upload_image(db, user(), UploadFile(file=raw, filename="room.png"), role="source")
    asset = await db.get(ContentCoverAsset, result["item"]["asset_id"])
    assert asset.role == "image_design_input"
    assert asset.owner_uid == "employee"
    assert result["item"]["source_role"] == "upload"
    assert await db.scalar(select(func.count()).select_from(ImageDesignLibraryItem)) == 1
    assert await db.scalar(select(func.count()).select_from(ContentMaterialLibraryItem)) == 0
