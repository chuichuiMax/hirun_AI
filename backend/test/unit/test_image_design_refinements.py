from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from yuxi.image_design.prompt_compiler import build_prompt_plan
from yuxi.image_design.schemas import StyleTransferRefinementCreate, WORKFLOW_PROFILE_VERSION


def refinement_fingerprint(*args):
    from yuxi.image_design.service import refinement_fingerprint as fingerprint

    return fingerprint(*args)


def validate_refinement_integrity(*args):
    from yuxi.image_design.service import validate_refinement_integrity as validate

    return validate(*args)


def _refinement(*, semantic: dict, materials: list[dict[str, str]], plan: dict):
    return SimpleNamespace(
        request_json={"semantic": semantic, "materials": materials},
        workflow_version=WORKFLOW_PROFILE_VERSION,
        input_fingerprint=refinement_fingerprint(semantic, materials),
        plan_json=plan,
    )


def test_refinement_integrity_accepts_matching_semantics_materials_and_roles() -> None:
    payload = StyleTransferRefinementCreate(
        workflow="style_transfer",
        source_material_id="mli_source",
        style_label="现代简约",
        user_prompt="暖色自然光",
    )
    plan = build_prompt_plan(
        payload,
        {"structure_source": {"room_type": "卧室", "preserve": ["窗户位置"]}},
    )
    materials = [{"role": "structure_source", "material_id": "mli_source", "asset_sha256": "a" * 64}]
    semantic = payload.model_dump(mode="json", exclude={"parent_refinement_id", "edited_prompt"})
    semantic["effective_prompt"] = payload.user_prompt
    row = _refinement(semantic=semantic, materials=materials, plan=plan.model_dump(mode="json"))

    assert validate_refinement_integrity(row, materials) == plan


def test_refinement_integrity_rejects_changed_asset_hash() -> None:
    payload = StyleTransferRefinementCreate(
        workflow="style_transfer",
        source_material_id="mli_source",
        style_label="现代简约",
        user_prompt="暖色自然光",
    )
    plan = build_prompt_plan(payload, {"structure_source": {"room_type": "卧室"}})
    original = [{"role": "structure_source", "material_id": "mli_source", "asset_sha256": "a" * 64}]
    changed = [{"role": "structure_source", "material_id": "mli_source", "asset_sha256": "b" * 64}]
    semantic = payload.model_dump(mode="json", exclude={"parent_refinement_id", "edited_prompt"})
    semantic["effective_prompt"] = payload.user_prompt
    row = _refinement(semantic=semantic, materials=original, plan=plan.model_dump(mode="json"))

    with pytest.raises(HTTPException) as exc_info:
        validate_refinement_integrity(row, changed)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error"]["code"] == "IMAGE_DESIGN_REFINEMENT_STALE"


def mp_payload(**changes):
    return {
        "workflow": "redesign",
        "images": [{"role": "source", "library_item_id": "input-source"}],
        "description": "暖色自然光",
        "style": "现代简约",
        "refinement_id": "idr_owned",
        "ratio": "portrait",
        "quality": "2k",
        "count": 2,
        "save_target": {"scope": "enterprise"},
        **changes,
    }


def test_mp_render_options_map_to_core_values():
    from yuxi.image_design.mp_service import map_quality, map_ratio

    assert map_ratio("portrait") == "3:4"
    assert map_ratio("landscape") == "4:3"
    assert map_ratio("square") == "1:1"
    assert map_quality("2k") == "2K"


@pytest.mark.parametrize("missing", ["refinement_id", "save_target"])
def test_mp_task_requires_server_refinement_and_canonical_target(missing):
    from pydantic import ValidationError
    from yuxi.image_design.mp_schemas import MpTaskCreate

    payload = mp_payload()
    payload.pop(missing)
    with pytest.raises(ValidationError):
        MpTaskCreate.model_validate(payload)


@pytest.mark.parametrize(
    "images",
    [
        [],
        [
            {"role": "source", "library_item_id": "one"},
            {"role": "source", "library_item_id": "two"},
        ],
        [{"role": "reference", "library_item_id": "one"}],
    ],
)
def test_mp_task_rejects_missing_duplicate_or_wrong_roles(images):
    from pydantic import ValidationError
    from yuxi.image_design.mp_schemas import MpTaskCreate

    with pytest.raises(ValidationError):
        MpTaskCreate.model_validate(mp_payload(images=images))


@pytest.mark.parametrize(
    "workflow,images,options,expected",
    [
        ("redesign", [{"role": "source", "library_item_id": "source"}], {}, "style_transfer"),
        (
            "adapt",
            [{"role": "rough", "library_item_id": "rough"}, {"role": "reference", "library_item_id": "reference"}],
            {},
            "room_adapt",
        ),
        (
            "transfer",
            [{"role": "reference", "library_item_id": "reference"}],
            {"target_space": "客厅", "layout_type": "一字型沙发墙", "extra_element": ["落地窗旁休闲躺椅"]},
            "cross_space",
        ),
    ],
)
def test_mp_workflow_conversion_preserves_semantics(workflow, images, options, expected):
    from yuxi.image_design.mp_schemas import MpPolishCreate
    from yuxi.image_design.mp_service import refinement_payload

    payload = MpPolishCreate(workflow=workflow, images=images, description="自然光", **options)
    converted = refinement_payload(payload)
    assert converted.workflow == expected
    assert converted.user_prompt == "自然光"
    if workflow == "redesign":
        assert converted.source_material_id == "source" and converted.use_prompt_as_style
    elif workflow == "adapt":
        assert converted.style_reference_material_id == "reference"
        assert converted.raw_structure_material_id == "rough"
    else:
        assert (converted.target_space, converted.layout, converted.addons) == (
            "living_room",
            "sofa_wall",
            ["lounge_chair"],
        )


def test_mp_transfer_default_options_compile_into_real_prompt():
    from yuxi.image_design.mp_schemas import MpPolishCreate
    from yuxi.image_design.mp_service import refinement_payload
    from yuxi.image_design.prompt_compiler import compile_prompt

    payload = MpPolishCreate(
        workflow="transfer",
        images=[{"role": "reference", "library_item_id": "reference"}],
        description="自然光",
        target_space="客厅",
        layout_type="一字型沙发墙",
        extra_element=["落地窗旁休闲躺椅"],
    )
    plan = build_prompt_plan(refinement_payload(payload), {"cross_space_style": {"style": "现代简约"}})
    prompt = compile_prompt(plan)
    assert plan.target_space == {"id": "living_room", "label": "客厅"}
    assert plan.layout == {"id": "sofa_wall", "label": "一字型沙发靠墙"}
    assert plan.addons == [{"id": "lounge_chair", "label": "落地窗旁休闲躺椅"}]
    assert "目标空间：客厅。" in prompt
    assert "布局要求：一字型沙发靠墙。" in prompt
    assert "附加元素：落地窗旁休闲躺椅。" in prompt
    assert payload.target_space == "客厅"  # conversion does not mutate public request labels


@pytest.mark.parametrize("field", ["target_space", "layout_type", "extra_element"])
def test_mp_transfer_rejects_unknown_options_with_422(field):
    from yuxi.image_design.mp_schemas import MpPolishCreate
    from yuxi.image_design.mp_service import refinement_payload

    options = {"target_space": "客厅", "layout_type": "一字型沙发墙", "extra_element": ["落地窗旁休闲躺椅"]}
    options[field] = ["未知选项"] if field == "extra_element" else "未知选项"
    payload = MpPolishCreate(
        workflow="transfer",
        images=[{"role": "reference", "library_item_id": "reference"}],
        **options,
    )
    with pytest.raises(HTTPException) as exc:
        refinement_payload(payload)
    assert exc.value.status_code == 422
    assert exc.value.detail["error"]["code"] == "IMAGE_DESIGN_TRANSFER_OPTION_INVALID"


@pytest.mark.parametrize(
    "space,space_id",
    [
        ("客厅", "living_room"),
        ("餐厅", "dining_room"),
        ("厨房", "kitchen"),
        ("主卧", "master_bedroom"),
        ("次卧/儿童房", "children_room"),
        ("书房", "study"),
        ("主卫", "master_bathroom"),
        ("公卫", "bathroom"),
        ("阳台", "balcony"),
        ("玄关", "entrance"),
        ("衣帽间", "cloakroom"),
        ("茶室", "tea_room"),
        ("影音室", "audio_visual_room"),
        ("酒窖", "wine_cellar"),
        ("健身房", "gym"),
        ("长辈房", "elder_room"),
        ("客房", "guest_room"),
    ],
)
def test_mp_transfer_all_shared_options_compile_for_every_space(space, space_id):
    from itertools import product
    from yuxi.image_design.mp_schemas import MpPolishCreate
    from yuxi.image_design.mp_service import refinement_payload
    from yuxi.image_design.prompt_compiler import compile_prompt

    layouts = [
        ("一字型沙发墙", "一字型沙发靠墙"),
        ("L 型沙发 + 单人椅", "L 型沙发配单人椅"),
        ("沙发对坐式", "沙发对坐式"),
        ("无主沙发自由布局", "无主沙发自由布局"),
    ]
    elements = [
        ("落地窗旁休闲躺椅", "落地窗旁休闲躺椅"),
        ("沙发后长条书桌/吧台", "沙发后长条书桌或吧台"),
        ("电视墙满墙收纳柜", "电视墙满墙收纳柜"),
        ("开放式层板展示架", "开放式层板展示架"),
        ("地毯划分沙发区", "用地毯划分沙发区"),
        ("壁炉居中", "壁炉居中"),
    ]
    for (layout, layout_label), (element, element_label) in product(layouts, elements):
        payload = MpPolishCreate(
            workflow="transfer",
            images=[{"role": "reference", "library_item_id": "reference"}],
            description="自然光",
            target_space=space,
            layout_type=layout,
            extra_element=[element],
        )
        converted = refinement_payload(payload)
        plan = build_prompt_plan(converted, {"cross_space_style": {"style": "现代简约"}})
        assert plan.target_space == {"id": space_id, "label": space}
        assert plan.layout["label"] == layout_label
        assert [item["label"] for item in plan.addons] == [element_label]
        prompt = compile_prompt(plan)
        assert f"目标空间：{space}。" in prompt
        assert f"布局要求：{layout_label}。" in prompt
        assert f"附加元素：{element_label}。" in prompt


def test_mp_transfer_internal_options_do_not_change_public_pc_choices():
    from yuxi.image_design.workflow_profiles import public_profiles

    spaces = {item["id"]: item for item in public_profiles()["spaces"]}
    assert spaces["study"]["layouts"] == [
        {"id": "desk_window", "label": "书桌靠窗"},
        {"id": "desk_wall", "label": "书桌靠墙"},
        {"id": "dual_desk", "label": "双人书桌"},
    ]
    for space in spaces.values():
        assert all(not item["id"].startswith("mp_") for item in [*space["layouts"], *space["addons"]])


@pytest.fixture
async def mp_db():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from yuxi.storage.postgres.models_content import (
        ContentCoverAsset,
        ContentMaterialCategory,
        ContentMaterialLibraryItem,
        ImageDesignLibraryItem,
        ImageDesignJob,
        ImageDesignRefinement,
    )

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        for model in (
            ContentCoverAsset,
            ContentMaterialCategory,
            ContentMaterialLibraryItem,
            ImageDesignLibraryItem,
            ImageDesignJob,
            ImageDesignRefinement,
        ):
            await connection.run_sync(model.__table__.create)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "owner,changed,status,code",
    [
        ("other", {}, "completed", 404),
        ("employee", {"description": "changed"}, "completed", 409),
        ("employee", {"style": "新中式"}, "completed", 409),
        ("employee", {"images": [{"role": "source", "library_item_id": "changed"}]}, "completed", 409),
        ("employee", {}, "failed", 409),
    ],
)
async def test_mp_task_rejects_foreign_or_stale_refinement(mp_db, owner, changed, status, code):
    from yuxi.image_design.mp_schemas import MpTaskCreate
    from yuxi.image_design.mp_service import create_task, refinement_payload
    from yuxi.storage.postgres.models_content import ImageDesignRefinement

    semantic = refinement_payload(MpTaskCreate(**mp_payload())).model_dump(
        mode="json", exclude={"parent_refinement_id", "edited_prompt"}
    )
    semantic["effective_prompt"] = "暖色自然光"
    mp_db.add(
        ImageDesignRefinement(
            id="idr_owned",
            owner_uid=owner,
            workflow="style_transfer",
            workflow_version=1,
            input_fingerprint="a" * 64,
            request_json={"semantic": semantic},
            compiled_prompt="server prompt",
            model_spec="test",
            status=status,
        )
    )
    await mp_db.commit()
    with pytest.raises(HTTPException) as exc:
        await create_task(mp_db, SimpleNamespace(uid="employee"), MpTaskCreate(**mp_payload(**changed)))
    assert exc.value.status_code == code


async def seed_mp_job(db, *, status="failed", owner="employee", completed=1):
    from yuxi.storage.postgres.models_content import ImageDesignJob

    job = ImageDesignJob(
        id="idj_partial",
        owner_uid=owner,
        workflow="room_adapt",
        status=status,
        idempotency_key="test",
        progress=50,
        error_code="PROVIDER_FAILED",
        error_message="failed",
        request_json={
            "gen_count": 2,
            "requested_save_target": {"scope": "enterprise", "gallery_id": None},
            "image_roles": [
                {"role": "style_reference", "material_id": "ref"},
                {"role": "structure_source", "material_id": "rough"},
            ],
        },
        result_json={
            "asset_ids": [f"asset-{i}" for i in range(completed)],
            "library_item_ids": [f"item-{i}" for i in range(completed)],
            "resolved_save_target": {"scope": "enterprise", "gallery_id": None},
        },
    )
    db.add(job)
    await db.commit()
    return job


@pytest.mark.asyncio
async def test_mp_status_maps_success_and_enforces_ownership(mp_db):
    from yuxi.image_design.mp_service import get_task

    await seed_mp_job(mp_db, status="succeeded", completed=2)
    result = await get_task(mp_db, SimpleNamespace(uid="employee"), "idj_partial")
    assert result["task"]["status"] == "completed"
    assert result["task"]["failed_count"] == 0
    assert result["task"]["can_retry"] is False
    assert result["task"]["requested_save_target"] == {"scope": "enterprise", "gallery_id": None}
    with pytest.raises(HTTPException) as exc:
        await get_task(mp_db, SimpleNamespace(uid="other"), "idj_partial")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,owner,completed,code",
    [
        ("running", "employee", 1, 409),
        ("queued", "employee", 1, 409),
        ("succeeded", "employee", 2, 409),
        ("failed", "employee", 2, 409),
        ("failed", "other", 1, 404),
    ],
)
async def test_mp_retry_rejects_nonfailed_complete_and_foreign_jobs(mp_db, status, owner, completed, code):
    from yuxi.image_design.mp_service import retry_task

    await seed_mp_job(mp_db, status=status, owner=owner, completed=completed)
    with pytest.raises(HTTPException) as exc:
        await retry_task(mp_db, SimpleNamespace(uid="employee"), "idj_partial")
    assert exc.value.status_code == code


@pytest.mark.asyncio
@pytest.mark.parametrize("queue_result", [True, None, "error"])
async def test_mp_retry_preserves_outputs_and_handles_queue_failure(mp_db, monkeypatch, queue_result):
    from yuxi.image_design import mp_service

    job = await seed_mp_job(mp_db)
    before = dict(job.result_json)
    deliveries = []

    class Queue:
        async def enqueue_job(self, function, job_id, **kwargs):
            assert job.status == "queued" and job.error_code is None
            deliveries.append((function, job_id, kwargs["_job_id"]))
            if queue_result == "error":
                raise ConnectionError("offline")
            return queue_result

    async def pool():
        return Queue()

    monkeypatch.setattr(mp_service, "get_arq_pool", pool)
    if queue_result is True:
        response = await mp_service.retry_task(mp_db, SimpleNamespace(uid="employee"), job.id)
        assert response["task"]["status"] == "queued"
        assert response["task"]["can_retry"] is False
    else:
        with pytest.raises(HTTPException) as exc:
            await mp_service.retry_task(mp_db, SimpleNamespace(uid="employee"), job.id)
        assert exc.value.status_code == 503
        assert job.status == "failed" and job.error_code.startswith("IMAGE_DESIGN_QUEUE_")
    assert job.result_json == before
    assert len(deliveries) == 1 and deliveries[0][:2] == ("process_image_design_job", job.id)
    assert deliveries[0][2] != f"image-design:{job.id}"  # old ARQ result key must not suppress retry


@pytest.mark.asyncio
async def test_mp_results_return_owned_outputs_and_immutable_comparison_sources(mp_db):
    from yuxi.image_design.mp_service import list_results
    from yuxi.storage.postgres.models_content import ContentCoverAsset

    await seed_mp_job(mp_db)
    for owner in ("employee", "other"):
        mp_db.add(
            ContentCoverAsset(
                id=f"result-{owner}",
                owner_uid=owner,
                role="output",
                original_file_name="result.png",
                content_type="image/png",
                file_size=4,
                image_width=32,
                image_height=32,
                sha256="a" * 64,
                bucket_name="test",
                object_name="out.png",
                metadata_json={"domain": "image_design", "image_design_job_id": "idj_partial"},
            )
        )
    await mp_db.commit()
    result = await list_results(mp_db, SimpleNamespace(uid="employee"), page=1, page_size=100)
    assert result["total"] == 1
    item = result["items"][0]
    assert item["id"] == "result-employee" and item["workflow"] == "adapt"
    assert item["file_url"] == "/api/mp/image-design/results/result-employee/file"
    assert item["reference_image"]["library_item_id"] == "ref"
    assert item["rough_image"]["library_item_id"] == "rough"
    assert item["can_retry"] and item["failed_count"] == 1


@pytest.mark.asyncio
async def test_core_resolver_accepts_only_owned_dedicated_inputs(mp_db):
    from yuxi.image_design.service import resolve_image_input
    from yuxi.storage.postgres.models_content import ContentCoverAsset, ImageDesignLibraryItem

    mp_db.add(
        ContentCoverAsset(
            id="upload",
            owner_uid="employee",
            role="image_design_input",
            original_file_name="in.png",
            content_type="image/png",
            file_size=4,
            image_width=32,
            image_height=32,
            sha256="a" * 64,
            bucket_name="test",
            object_name="in.png",
        )
    )
    mp_db.add(ImageDesignLibraryItem(id="input-owned", owner_uid="employee", asset_id="upload", source_role="upload"))
    await mp_db.commit()
    image = await resolve_image_input(mp_db, "employee", "input-owned")
    assert image.input_id == "input-owned" and image.asset.id == "upload"
    assert image.asset_sha256 == "a" * 64
    with pytest.raises(HTTPException) as exc:
        await resolve_image_input(mp_db, "other", "input-owned")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_worker_retry_resumes_legacy_job_after_existing_outputs(monkeypatch):
    from test.unit.test_image_design_worker_save_target import MemorySession, run_worker
    from yuxi.image_design import worker

    db = MemorySession()
    db.job.request_json.pop("requested_save_target")
    db.job.result_json = {"asset_ids": ["already-generated"]}
    db.job.status = "queued"
    client = run_worker.__wrapped__(db, monkeypatch)
    await worker.process_image_design_job({}, db.job.id)
    assert db.job.status == "succeeded"
    assert client.calls == 1
    assert db.job.result_json["asset_ids"][0] == "already-generated"
    assert len(db.job.result_json["asset_ids"]) == 2


def test_refinement_integrity_rejects_plan_role_tampering() -> None:
    payload = StyleTransferRefinementCreate(
        workflow="style_transfer",
        source_material_id="mli_source",
        style_label="现代简约",
        user_prompt="暖色自然光",
    )
    plan = build_prompt_plan(payload, {"structure_source": {"room_type": "卧室"}})
    plan.image_roles[0]["material_id"] = "mli_other"
    materials = [{"role": "structure_source", "material_id": "mli_source", "asset_sha256": "a" * 64}]
    semantic = payload.model_dump(mode="json", exclude={"parent_refinement_id", "edited_prompt"})
    semantic["effective_prompt"] = payload.user_prompt
    row = _refinement(semantic=semantic, materials=materials, plan=plan.model_dump(mode="json"))

    with pytest.raises(HTTPException) as exc_info:
        validate_refinement_integrity(row, materials)

    assert exc_info.value.detail["error"]["code"] == "IMAGE_DESIGN_REFINEMENT_STALE"
