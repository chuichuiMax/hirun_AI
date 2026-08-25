from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Header, Query, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from server.utils.auth_middleware import get_db, get_required_user
from yuxi.content_cover.schemas import (
    CoverComposeCreate,
    CoverGenerateCreate,
    CoverRetryCreate,
    CoverSetCurrentCreate,
    Image2GlobalConfigUpdate,
)
from yuxi.services.content_cover_service import (
    cancel_cover_job,
    create_cover_asset,
    create_cover_compose_job,
    create_cover_generate_job,
    delete_cover_asset,
    get_cover_asset_file,
    get_cover_bootstrap,
    get_cover_job,
    list_cover_jobs,
    retry_cover_job,
    set_current_cover,
    stream_cover_job_events,
    update_image2_global_config,
)
from yuxi.storage.postgres.models_business import User

content_covers = APIRouter(prefix="/content/covers", tags=["content-covers"])


@content_covers.get("/bootstrap")
async def cover_bootstrap(
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_cover_bootstrap(db, current_user)


@content_covers.put("/image2-config")
async def update_cover_image2_config(
    payload: Image2GlobalConfigUpdate,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return {"image2": await update_image2_global_config(db, current_user, payload)}


@content_covers.post("/assets", status_code=status.HTTP_201_CREATED)
async def upload_cover_asset(
    file: UploadFile = File(...),
    role: str = Form("source"),
    content_task_id: str | None = Form(None),
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await create_cover_asset(db, current_user, file, role=role, content_task_id=content_task_id)


@content_covers.get("/assets/{asset_id}/file")
async def cover_asset_file(
    asset_id: str,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    data, content_type, file_name = await get_cover_asset_file(db, current_user, asset_id)
    encoded_name = quote(file_name, safe="")
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Cache-Control": "private, max-age=3600",
            "Content-Disposition": f"inline; filename*=UTF-8''{encoded_name}",
        },
    )


@content_covers.delete("/assets/{asset_id}")
async def remove_cover_asset(
    asset_id: str,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await delete_cover_asset(db, current_user, asset_id)


@content_covers.post("/compose", status_code=status.HTTP_202_ACCEPTED)
async def compose_cover(
    payload: CoverComposeCreate,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await create_cover_compose_job(db, current_user, payload)


@content_covers.post("/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_cover(
    payload: CoverGenerateCreate,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await create_cover_generate_job(db, current_user, payload)


@content_covers.get("/jobs")
async def cover_jobs(
    content_task_id: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await list_cover_jobs(
        db,
        current_user,
        content_task_id=content_task_id,
        page=page,
        page_size=page_size,
    )


@content_covers.get("/jobs/{job_id}")
async def cover_job(
    job_id: str,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_cover_job(db, current_user, job_id)


@content_covers.get("/jobs/{job_id}/events")
async def cover_job_events(
    job_id: str,
    after_seq: str = Query("0-0"),
    last_event_id: str | None = Header(None, alias="Last-Event-ID"),
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    await get_cover_job(db, current_user, job_id)
    return StreamingResponse(
        stream_cover_job_events(job_id, str(current_user.uid), last_event_id or after_seq),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@content_covers.post("/jobs/{job_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_cover(
    job_id: str,
    payload: CoverRetryCreate,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await retry_cover_job(db, current_user, job_id, payload)


@content_covers.post("/jobs/{job_id}/cancel")
async def cancel_cover(
    job_id: str,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await cancel_cover_job(db, current_user, job_id)


@content_covers.post("/jobs/{job_id}/set-current")
async def select_current_cover(
    job_id: str,
    payload: CoverSetCurrentCreate | None = None,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await set_current_cover(
        db,
        current_user,
        job_id,
        asset_id=payload.asset_id if payload else None,
    )
