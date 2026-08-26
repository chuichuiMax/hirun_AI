from __future__ import annotations

from typing import Any

from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.storage.postgres.models_content import (
    ContentCoverAsset,
    ContentCoverPosterTemplate,
    ContentMaterialLibraryItem,
)


class MaterialLibraryRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_item(self, **values: Any) -> ContentMaterialLibraryItem:
        item = ContentMaterialLibraryItem(**values)
        self.db.add(item)
        await self.db.flush()
        return item

    async def get_item_for_user(
        self, item_id: str, owner_uid: str, *, for_update: bool = False
    ) -> ContentMaterialLibraryItem | None:
        query = select(ContentMaterialLibraryItem).where(
            ContentMaterialLibraryItem.id == item_id,
            ContentMaterialLibraryItem.owner_uid == owner_uid,
            ContentMaterialLibraryItem.deleted_at.is_(None),
        )
        if for_update:
            query = query.with_for_update()
        return (await self.db.execute(query)).scalar_one_or_none()

    async def get_item_by_asset(self, asset_id: str) -> ContentMaterialLibraryItem | None:
        return (
            await self.db.execute(
                select(ContentMaterialLibraryItem).where(
                    ContentMaterialLibraryItem.asset_id == asset_id,
                    ContentMaterialLibraryItem.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()

    async def list_items(
        self,
        owner_uid: str,
        *,
        material_type: str,
        category: str | None,
        status: str | None,
        query_text: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[tuple[ContentMaterialLibraryItem, ContentCoverAsset]], int]:
        filters = [
            ContentMaterialLibraryItem.owner_uid == owner_uid,
            ContentMaterialLibraryItem.material_type == material_type,
            ContentMaterialLibraryItem.deleted_at.is_(None),
            ContentCoverAsset.deleted_at.is_(None),
        ]
        if category:
            filters.append(ContentMaterialLibraryItem.category == category)
        if status:
            filters.append(ContentMaterialLibraryItem.status == status)
        if query_text:
            pattern = f"%{query_text.strip()}%"
            filters.append(
                or_(
                    ContentMaterialLibraryItem.display_name.ilike(pattern),
                    ContentMaterialLibraryItem.category.ilike(pattern),
                    cast(ContentMaterialLibraryItem.tags_json, Text).ilike(pattern),
                )
            )
        join = ContentMaterialLibraryItem.__table__.join(
            ContentCoverAsset, ContentCoverAsset.id == ContentMaterialLibraryItem.asset_id
        )
        total = int(
            (
                await self.db.execute(
                    select(func.count(ContentMaterialLibraryItem.id)).select_from(join).where(*filters)
                )
            ).scalar_one()
        )
        rows = (
            await self.db.execute(
                select(ContentMaterialLibraryItem, ContentCoverAsset)
                .select_from(join)
                .where(*filters)
                .order_by(ContentMaterialLibraryItem.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return list(rows), total

    async def get_asset(self, asset_id: str, owner_uid: str, *, for_update: bool = False) -> ContentCoverAsset | None:
        query = select(ContentCoverAsset).where(
            ContentCoverAsset.id == asset_id,
            ContentCoverAsset.owner_uid == owner_uid,
            ContentCoverAsset.deleted_at.is_(None),
        )
        if for_update:
            query = query.with_for_update()
        return (await self.db.execute(query)).scalar_one_or_none()

    async def get_poster_template_by_asset(self, asset_id: str) -> ContentCoverPosterTemplate | None:
        return (
            await self.db.execute(
                select(ContentCoverPosterTemplate).where(
                    ContentCoverPosterTemplate.asset_id == asset_id,
                    ContentCoverPosterTemplate.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
