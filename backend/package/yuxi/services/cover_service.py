from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.repositories.cover_repository import CoverRepository
from yuxi.storage.postgres.models_business import User

CoverCategory = Literal["chinese", "european", "modern"]
COVER_CATEGORIES: tuple[CoverCategory, ...] = ("chinese", "european", "modern")


class CoverCreate(BaseModel):
    category: CoverCategory
    image_url: str = Field(min_length=1, max_length=1024)
    image_name: str = Field(min_length=1, max_length=255)
    title: str = Field(default="", max_length=120)
    enabled: bool = True


class CoverUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    enabled: bool | None = None


def _cover_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"error": {"code": code, "message": message}})


def _normalize_text(value: str, *, field: str, allow_empty: bool = False) -> str:
    normalized = value.strip()
    if not normalized and not allow_empty:
        raise _cover_error(422, "COVER_INVALID_FIELD", f"{field} 不能为空")
    return normalized


def _normalize_image_name(value: str) -> str:
    name = _normalize_text(value, field="图片名").replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not name or name in {".", ".."}:
        raise _cover_error(422, "COVER_INVALID_FIELD", "图片名不能为空")
    return name


async def list_covers(db: AsyncSession, category: str, keyword: str | None = None) -> dict[str, Any]:
    if category not in COVER_CATEGORIES:
        raise _cover_error(422, "COVER_INVALID_CATEGORY", "封面分类不存在")
    items = await CoverRepository(db).list_covers(
        category=category,
        keyword=keyword.strip() if keyword else None,
    )
    return {"covers": [item.to_dict() for item in items], "total": len(items)}


async def create_cover(db: AsyncSession, user: User, payload: CoverCreate) -> dict[str, Any]:
    repo = CoverRepository(db)
    image_name = _normalize_image_name(payload.image_name)
    if await repo.get_by_image_name(payload.category, image_name):
        raise _cover_error(409, "COVER_IMAGE_NAME_EXISTS", "图片名已存在")
    try:
        cover = await repo.create(
            {
                "id": str(uuid.uuid4()),
                "category": payload.category,
                "image_url": _normalize_text(payload.image_url, field="封面图片"),
                "image_name": image_name,
                "title": _normalize_text(payload.title, field="标题", allow_empty=True),
                "generation_count": 0,
                "enabled": payload.enabled,
                "created_by": str(user.uid),
            }
        )
    except IntegrityError as exc:
        raise _cover_error(409, "COVER_IMAGE_NAME_EXISTS", "图片名已存在") from exc
    return {"cover": cover.to_dict()}


async def update_cover(db: AsyncSession, cover_pk: str, payload: CoverUpdate) -> dict[str, Any]:
    repo = CoverRepository(db)
    cover = await repo.get(cover_pk)
    if cover is None:
        raise _cover_error(404, "COVER_NOT_FOUND", "封面不存在")
    data = payload.model_dump(exclude_unset=True)
    if "title" in data:
        data["title"] = _normalize_text(data["title"], field="标题", allow_empty=True)
    cover = await repo.update(cover, data)
    return {"cover": cover.to_dict()}


async def delete_cover(db: AsyncSession, cover_pk: str) -> dict[str, Any]:
    repo = CoverRepository(db)
    cover = await repo.get(cover_pk)
    if cover is None:
        raise _cover_error(404, "COVER_NOT_FOUND", "封面不存在")
    await repo.delete(cover)
    return {"success": True, "id": cover_pk}
