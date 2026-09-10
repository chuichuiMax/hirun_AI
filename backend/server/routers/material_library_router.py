from __future__ import annotations

from urllib.parse import quote
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from server.utils.auth_middleware import get_db, get_required_user
from yuxi.services.material_library_service import (
    MaterialCategoryCreate,
    MaterialCategoryDelete,
    MaterialCategoryUpdate,
    MaterialItemUpdate,
    MaterialShareCreate,
    create_material_share,
    create_material_category,
    delete_material_item,
    delete_material_category,
    get_material_file,
    get_material_thumbnail,
    get_public_material_share,
    get_public_material_share_image,
    get_material_categories,
    import_material_images,
    list_image_galleries,
    list_material_items,
    update_material_item,
    update_material_category,
    render_public_material_share_page,
    serialize_public_material_share,
)
from yuxi.storage.postgres.models_business import User

material_library = APIRouter(prefix="/material-library", tags=["material-library"])


@material_library.post("/images/import", status_code=status.HTTP_201_CREATED)
async def import_images(
    files: list[UploadFile] = File(...),
    category: str = Form(...),
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await import_material_images(
        db,
        current_user,
        files,
        category=category,
    )


@material_library.get("/categories")
async def material_categories(
    material_type: str = Query(...),
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_material_categories(db, current_user, material_type)


@material_library.post("/categories", status_code=status.HTTP_201_CREATED)
async def add_material_category(
    payload: MaterialCategoryCreate,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await create_material_category(db, current_user, payload)


@material_library.patch("/categories/{category_id}")
async def edit_material_category(
    category_id: str,
    payload: MaterialCategoryUpdate,
    material_type: str = Query(...),
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await update_material_category(db, current_user, material_type, category_id, payload)


@material_library.delete("/categories/{category_id}")
async def remove_material_category(
    category_id: str,
    payload: MaterialCategoryDelete,
    material_type: str = Query(...),
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await delete_material_category(db, current_user, material_type, category_id, payload)


@material_library.get("/galleries")
async def image_galleries(
    industry_slug: str | None = Query(None, max_length=80),
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await list_image_galleries(db, current_user, industry_slug=industry_slug)


@material_library.post("/shares", status_code=status.HTTP_201_CREATED)
async def create_share(
    payload: MaterialShareCreate,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await create_material_share(db, current_user, payload)


@material_library.get("/shares/{token}/page", response_class=HTMLResponse)
async def public_share_page(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    share, items = await get_public_material_share(db, token)
    return HTMLResponse(render_public_material_share_page(share, items, str(request.base_url)))


@material_library.get("/shares/{token}")
async def public_share_data(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    share, items = await get_public_material_share(db, token)
    return serialize_public_material_share(share, items)


@material_library.get("/shares/{token}/images/{display_order}")
async def public_share_image(
    token: str,
    display_order: int,
    db: AsyncSession = Depends(get_db),
):
    data, content_type, file_name = await get_public_material_share_image(db, token, display_order)
    encoded_name = quote(file_name, safe="")
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "Content-Disposition": f"inline; filename*=UTF-8''{encoded_name}",
        },
    )


@material_library.get("/items")
async def material_items(
    material_type: str = Query(...),
    category: str | None = Query(None),
    item_status: str | None = Query(None, alias="status"),
    query: str | None = Query(None, max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    sort: str = Query("newest"),
    scope: Literal["private", "enterprise"] | None = Query(None),
    exclude_task_id: str | None = Query(None),
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
        sort=sort,
        scope=scope,
        exclude_task_id=exclude_task_id,
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
            "Cache-Control": "private, no-cache",
            "Content-Disposition": f"inline; filename*=UTF-8''{encoded_name}",
        },
    )


@material_library.get("/items/{item_id}/thumbnail")
async def material_item_thumbnail(
    item_id: str,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    data, file_name = await get_material_thumbnail(db, current_user, item_id)
    encoded_name = quote(file_name, safe="")
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "private, no-cache",
            "Content-Disposition": f"inline; filename*=UTF-8''{encoded_name}.thumb.jpg",
        },
    )


@material_library.delete("/items/{item_id}")
async def remove_material_item(
    item_id: str,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await delete_material_item(db, current_user, item_id)
