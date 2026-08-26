from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from server.utils.auth_middleware import get_db, get_required_user
from yuxi.services.material_library_service import (
    MaterialItemUpdate,
    delete_material_item,
    get_material_file,
    import_material_images,
    list_material_items,
    update_material_item,
)
from yuxi.storage.postgres.models_business import User

material_library = APIRouter(prefix="/material-library", tags=["material-library"])


@material_library.post("/images/import", status_code=status.HTTP_201_CREATED)
async def import_images(
    files: list[UploadFile] = File(...),
    category: str = Form("未分类"),
    tags: str = Form(""),
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await import_material_images(
        db,
        current_user,
        files,
        category=category,
        tags=[item for item in tags.split(",") if item.strip()],
    )


@material_library.get("/items")
async def material_items(
    material_type: str = Query(...),
    category: str | None = Query(None),
    item_status: str | None = Query(None, alias="status"),
    query: str | None = Query(None, max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await list_material_items(
        db,
        current_user,
        material_type=material_type,
        category=category,
        status=item_status,
        query=query,
        page=page,
        page_size=page_size,
    )


@material_library.patch("/items/{item_id}")
async def edit_material_item(
    item_id: str,
    payload: MaterialItemUpdate,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await update_material_item(db, current_user, item_id, payload)


@material_library.get("/items/{item_id}/file")
async def material_item_file(
    item_id: str,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    data, content_type, file_name = await get_material_file(db, current_user, item_id)
    encoded_name = quote(file_name, safe="")
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Cache-Control": "private, max-age=3600",
            "Content-Disposition": f"inline; filename*=UTF-8''{encoded_name}",
        },
    )


@material_library.delete("/items/{item_id}")
async def remove_material_item(
    item_id: str,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await delete_material_item(db, current_user, item_id)
