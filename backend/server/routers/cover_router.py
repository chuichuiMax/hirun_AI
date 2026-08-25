from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from server.utils.auth_middleware import get_db, get_required_user
from yuxi.services.cover_service import (
    CoverCreate,
    CoverUpdate,
    create_cover,
    delete_cover,
    list_covers,
    update_cover,
)
from yuxi.storage.postgres.models_business import User

covers = APIRouter(prefix="/covers", tags=["covers"])


@covers.get("")
async def list_content_covers(
    category: str = Query(...),
    keyword: str | None = Query(default=None),
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await list_covers(db, category, keyword)


@covers.post("")
async def create_content_cover(
    payload: CoverCreate,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await create_cover(db, current_user, payload)


@covers.patch("/{cover_pk}")
async def update_content_cover(
    cover_pk: str,
    payload: CoverUpdate,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await update_cover(db, cover_pk, payload)


@covers.delete("/{cover_pk}")
async def delete_content_cover(
    cover_pk: str,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await delete_cover(db, cover_pk)
