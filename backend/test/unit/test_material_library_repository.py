from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from yuxi.repositories.material_library_repository import MaterialLibraryRepository
from yuxi.storage.postgres.models_content import ContentMaterialCategory


@pytest.mark.asyncio
async def test_sync_system_categories_preserves_a_conflicting_custom_gallery_name():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(ContentMaterialCategory.__table__.create)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as db:
            db.add_all(
                [
                    ContentMaterialCategory(
                        owner_uid="owner-1",
                        material_type="image",
                        id="product",
                        name="产品商品",
                        is_system=True,
                    ),
                    ContentMaterialCategory(
                        owner_uid="owner-1",
                        material_type="image",
                        id="mlc_custom",
                        name="AI生图图库",
                    ),
                ]
            )
            await db.commit()

            await MaterialLibraryRepository(db).sync_system_categories(
                [
                    {
                        "owner_uid": "owner-1",
                        "id": "product",
                        "tenant_id": None,
                        "material_type": "image",
                        "visibility": "private",
                        "parent_id": None,
                        "industry_slug": "uncategorized",
                        "name": "AI生图图库",
                        "description": "小程序生图工作流保存的图片",
                        "sort_order": 0,
                        "is_system": True,
                    }
                ]
            )
            await db.commit()

            category = await db.get(ContentMaterialCategory, ("owner-1", "image", "product"))
            assert category is not None
            assert category.name == "产品商品"
            assert category.is_system is True
    finally:
        await engine.dispose()
