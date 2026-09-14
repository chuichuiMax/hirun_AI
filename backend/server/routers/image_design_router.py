from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from server.utils.auth_middleware import get_admin_user, get_db, get_required_user
from yuxi.image_design.schemas import (
    ImageDesignClientCreate,
    ImageDesignGenerateCreate,
    ImageDesignPromptRefineCreate,
    ImageDesignRecognizeCreate,
    ImageDesignShowcaseCreate,
)
from yuxi.image_design.service import (
    _error,
    _get_material_item_and_asset,
    create_client,
    create_generate_job,
    delete_result,
    get_bootstrap,
    get_job,
    get_result_file,
    list_clients,
    list_jobs,
    list_results,
    list_showcase,
    create_showcase,
    delete_showcase,
    refine_prompt,
)
from yuxi.storage.postgres.models_business import User

image_design = APIRouter(prefix="/image-design", tags=["image-design"])


@image_design.get("/bootstrap")
async def image_design_bootstrap(
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_bootstrap(db, current_user)


@image_design.get("/clients")
async def image_design_clients(
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await list_clients(db, current_user)


@image_design.post("/clients", status_code=status.HTTP_201_CREATED)
async def image_design_create_client(
    payload: ImageDesignClientCreate,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await create_client(db, current_user, payload)


@image_design.get("/showcase")
async def image_design_showcase(
    category: str | None = Query(None, max_length=80),
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await list_showcase(db, current_user, category=category)


@image_design.post("/showcase", status_code=status.HTTP_201_CREATED)
async def image_design_create_showcase(
    payload: ImageDesignShowcaseCreate,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    return await create_showcase(db, current_user, payload)


@image_design.delete("/showcase/{showcase_id}")
async def image_design_delete_showcase(
    showcase_id: str,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    del current_user
    return await delete_showcase(db, showcase_id)


@image_design.post("/refine-prompt")
async def image_design_refine_prompt(
    payload: ImageDesignPromptRefineCreate,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_material_item_and_asset(db, str(current_user.uid), payload.reference_material_id)
    if payload.workflow == "room_adapt" and not payload.raw_room_material_id:
        raise _error("IMAGE_DESIGN_RAW_ROOM_REQUIRED", "户型适配必须选择毛坯实拍图")
    if payload.raw_room_material_id:
        await _get_material_item_and_asset(db, str(current_user.uid), payload.raw_room_material_id)
    try:
        preview = await refine_prompt(payload)
    except Exception as exc:
        raise _error("IMAGE_DESIGN_REFINE_FAILED", "AI 润色暂时不可用，请稍后重试", 503, retryable=True) from exc
    return {
        "success": True,
        "data": {
            "preview": preview,
            "content": preview,
            "source": payload.user_prompt,
            "model_spec": payload.model_spec,
            "has_refined": True,
        },
    }


@image_design.post("/recognize")
async def image_design_recognize(
    payload: ImageDesignRecognizeCreate,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    item, asset = await _get_material_item_and_asset(db, str(current_user.uid), payload.material_item_id)
    metadata = dict(item.metadata_json or {})
    analysis = dict(metadata.get("image_design_recognition") or {})
    if not analysis:
        analysis = {
            "status": "completed",
            "width": asset.image_width,
            "height": asset.image_height,
            "file_name": asset.original_file_name,
            "message": "已完成基础图片信息识别",
        }
        metadata["image_design_recognition"] = analysis
        item.metadata_json = metadata
        await db.commit()
    return {"success": True, "data": {"material_item_id": item.id, "recognition": analysis}}


@image_design.get("/recognitions")
async def image_design_recognitions(
    material_item_id: str | None = Query(None, max_length=80),
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    if not material_item_id:
        return {"recognitions": []}
    item, _ = await _get_material_item_and_asset(db, str(current_user.uid), material_item_id)
    return {
        "recognitions": [
            {
                "material_item_id": item.id,
                "recognition": (item.metadata_json or {}).get("image_design_recognition"),
            }
        ]
    }


@image_design.post("/generate", status_code=status.HTTP_202_ACCEPTED)
async def image_design_generate(
    payload: ImageDesignGenerateCreate,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await create_generate_job(db, current_user, payload)


@image_design.get("/generate/status")
async def image_design_generate_status(
    job_id: str = Query(..., min_length=8, max_length=80),
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_job(db, current_user, job_id)


@image_design.get("/jobs")
async def image_design_jobs(
    client_id: str | None = Query(None, max_length=80),
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await list_jobs(db, current_user, client_id=client_id)


@image_design.get("/results")
async def image_design_results(
    client_id: str | None = Query(None, max_length=80),
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await list_results(db, current_user, client_id=client_id)


@image_design.get("/results/{asset_id}/file")
async def image_design_result_file(
    asset_id: str,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    data, content_type, file_name = await get_result_file(db, current_user, asset_id)
    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(file_name, safe='')}"},
    )


@image_design.delete("/results/{asset_id}")
async def image_design_delete_result(
    asset_id: str,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    return await delete_result(db, current_user, asset_id)
