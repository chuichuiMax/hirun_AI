from __future__ import annotations

import io
import os
import uuid

import pytest
import pytest_asyncio
from PIL import Image
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test.integration.api import test_material_library_router as material_fixtures
from yuxi.services.employee_service import EmployeeCreate, create_employee, delete_employee
from yuxi.storage.postgres.models_business import User

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]
material_users = material_fixtures.material_users


@pytest_asyncio.fixture
async def admin_headers(material_users):
    # Provision an isolated administrator instead of requiring a developer's credentials.
    return material_users["owner"]


@pytest_asyncio.fixture
async def mp_accounts(test_client, material_users):
    accounts = []
    engine = create_async_engine(os.environ["POSTGRES_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        for _ in range(2):
            suffix = uuid.uuid4().hex[:10]
            phone = f"139{uuid.uuid4().int % 10**8:08d}"
            # Commit fixture setup before the next HTTP request opens its transaction.
            async with sessions() as db:
                created = await create_employee(
                    db,
                    User(uid=material_users["owner_uid"]),
                    EmployeeCreate(
                        employee_code=f"ID{suffix}",
                        name=f"图片设计测试_{suffix}",
                        login_account=phone,
                        gender="male",
                        login_port=["app"],
                        role="运营",
                        enabled=True,
                    ),
                )
                await db.commit()
            account = {"id": created["employee"]["id"]}
            accounts.append(account)
            sent = await test_client.post("/api/mp/auth/sms/send", json={"phone": phone})
            assert sent.status_code == 200, sent.text
            login = await test_client.post(
                "/api/mp/auth/sms/login",
                json={
                    "phone": phone,
                    "code": sent.json()["debug_code"],
                },
            )
            assert login.status_code == 200, login.text
            account["headers"] = {"Authorization": f"Bearer {login.json()['access_token']}"}
        yield accounts
    finally:
        try:
            async with sessions() as db:
                for account in accounts:
                    await delete_employee(db, account["id"])
                # Employee deletion is soft for platform users; release the temporary department FK.
                await db.execute(
                    update(User)
                    .where(
                        User.department_id == int(material_users["department_id"]),
                        User.is_deleted == 1,
                    )
                    .values(department_id=None)
                )
                await db.commit()
        finally:
            await engine.dispose()


async def test_image_design_routes_require_mp_authentication(test_client):
    for route in (
        "drafts",
        "library",
        "save-targets",
        "library/missing/file",
        "library/missing/thumbnail",
        "tasks/missing",
        "results",
        "results/missing/file",
        "tasks/missing/inputs/source/file",
    ):
        response = await test_client.get(f"/api/mp/image-design/{route}")
        assert response.status_code == 401, response.text
    for route in ("polish", "tasks", "tasks/missing/retry"):
        response = await test_client.post(f"/api/mp/image-design/{route}", json={})
        assert response.status_code == 401, response.text


async def test_mp_task_rejects_missing_refinement_and_legacy_target(test_client, mp_accounts):
    response = await test_client.post(
        "/api/mp/image-design/tasks",
        headers=mp_accounts[0]["headers"],
        json={
            "workflow": "redesign",
            "images": [{"role": "source", "library_item_id": "missing"}],
            "save_target_id": "folder",
            "polished_prompt": "forged",
        },
    )
    assert response.status_code == 422, response.text


async def test_mp_task_rejects_unowned_refinement(test_client, mp_accounts):
    response = await test_client.post(
        "/api/mp/image-design/tasks",
        headers=mp_accounts[0]["headers"],
        json={
            "workflow": "redesign",
            "images": [{"role": "source", "library_item_id": "missing"}],
            "refinement_id": "idr_unknown",
            "save_target": {"scope": "enterprise"},
        },
    )
    assert response.status_code == 404, response.text


async def test_mp_transfer_array_passes_validation_before_refinement_lookup(test_client, mp_accounts):
    payload = {
        "workflow": "transfer",
        "images": [{"role": "reference", "library_item_id": "missing"}],
        "target_space": "客厅",
        "layout_type": "一字型沙发墙",
        "extra_element": ["落地窗旁休闲躺椅", "壁炉居中"],
        "refinement_id": "idr_unknown",
        "save_target": {"scope": "private"},
    }
    response = await test_client.post("/api/mp/image-design/tasks", headers=mp_accounts[0]["headers"], json=payload)
    assert response.status_code == 404, response.text
    assert response.json()["detail"]["error"]["code"] == "IMAGE_DESIGN_REFINEMENT_INVALID"
    payload["extra_element"].append("开放式层板展示架")
    rejected = await test_client.post("/api/mp/image-design/tasks", headers=mp_accounts[0]["headers"], json=payload)
    assert rejected.status_code == 422, rejected.text


async def test_mp_results_and_task_files_remain_authenticated(test_client, mp_accounts):
    headers = mp_accounts[0]["headers"]
    result = await test_client.get("/api/mp/image-design/results", headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()["items"] == []
    for path in ("tasks/missing", "results/missing/file", "tasks/missing/inputs/source/file"):
        response = await test_client.get(f"/api/mp/image-design/{path}", headers=headers)
        assert response.status_code == 404, response.text
    retry = await test_client.post("/api/mp/image-design/tasks/missing/retry", headers=headers)
    assert retry.status_code == 404, retry.text


async def test_save_targets_offer_fixed_destinations_and_reject_pc_token(test_client, admin_headers, mp_accounts):
    pc = await test_client.get("/api/mp/image-design/save-targets", headers=admin_headers)
    assert pc.status_code == 401, pc.text
    response = await test_client.get("/api/mp/image-design/save-targets", headers=mp_accounts[0]["headers"])
    assert response.status_code == 200, response.text
    scopes = response.json()["scopes"]
    assert [item["scope"] for item in scopes] == ["private", "enterprise"]
    assert scopes[0]["can_write_root"] is True and scopes[0]["folders"] == []
    assert scopes[1]["can_write_root"] is False
    assert all(
        folder["name"] == "生图图库" and folder["parent_id"] is None for folder in scopes[1]["folders"]
    )
    assert all(
        folder["id"] not in {"private-root", "uncategorized", "enterprise-root"}
        for item in scopes for folder in item["folders"]
    )


async def test_drafts_are_normalized_and_account_isolated(test_client, mp_accounts):
    headers = mp_accounts[0]["headers"]
    saved = await test_client.put(
        "/api/mp/image-design/drafts",
        headers=headers,
        json={
            "drafts": {"adapt": {"reference": {"id": "draft-image"}, "save_target": {"scope": "private"}}},
        },
    )
    assert saved.status_code == 200, saved.text
    assert set(saved.json()["drafts"]) == {"redesign", "adapt", "transfer"}
    loaded = await test_client.get("/api/mp/image-design/drafts", headers=headers)
    assert loaded.json()["drafts"]["adapt"]["reference"]["id"] == "draft-image"
    other = await test_client.get("/api/mp/image-design/drafts", headers=mp_accounts[1]["headers"])
    assert other.json()["drafts"] == {"redesign": {}, "adapt": {}, "transfer": {}}
    forged = await test_client.put(
        "/api/mp/image-design/drafts",
        headers=headers,
        json={
            "owner_uid": "another-owner",
            "drafts": {},
        },
    )
    assert forged.status_code == 422, forged.text


async def test_upload_is_private_dedicated_input_with_authenticated_files(test_client, mp_accounts):
    raw = io.BytesIO()
    Image.new("RGB", (32, 24), "red").save(raw, format="PNG")
    headers = mp_accounts[0]["headers"]
    uploaded = await test_client.post(
        "/api/mp/image-design/uploads",
        headers=headers,
        files={"file": ("room.png", raw.getvalue(), "image/png")},
        data={"role": "source"},
    )
    assert uploaded.status_code == 200, uploaded.text
    item = uploaded.json()["item"]
    assert item["source_role"] == "upload"
    assert item["source_item_id"] is None
    listed = await test_client.get("/api/mp/image-design/library", headers=headers)
    assert item["id"] in {row["id"] for row in listed.json()["items"]}
    ordinary = await test_client.get(
        "/api/mp/content/gallery-items", headers=headers, params={"category": "uncategorized", "scope": "private"}
    )
    assert ordinary.status_code == 200, ordinary.text
    assert item["asset_id"] not in {row["asset_id"] for row in ordinary.json()["items"]}
    for url in (item["file_url"], item["thumbnail_file_url"]):
        own = await test_client.get(url, headers=headers)
        assert own.status_code == 200, own.text
        assert own.headers["content-type"].startswith("image/")
        foreign = await test_client.get(url, headers=mp_accounts[1]["headers"])
        assert foreign.status_code == 404, foreign.text


async def test_add_library_deduplicates_and_revokes_private_source(test_client, admin_headers, mp_accounts):
    category = await test_client.post(
        "/api/material-library/categories",
        headers=admin_headers,
        json={
            "material_type": "image",
            "name": f"MP design test {uuid.uuid4().hex[:8]}",
            "visibility": "enterprise",
        },
    )
    assert category.status_code == 201, category.text
    gallery_id = category.json()["category"]["id"]
    item_id = None
    try:
        raw = io.BytesIO()
        Image.new("RGB", (32, 24), "blue").save(raw, format="PNG")
        source = await test_client.post(
            "/api/material-library/images/import",
            headers=admin_headers,
            data={"category": gallery_id},
            files=[("files", ("shared.png", raw.getvalue(), "image/png"))],
        )
        assert source.status_code == 201, source.text
        item_id = source.json()["items"][0]["id"]
        payload = {"source_library_item_id": item_id, "source_gallery_id": gallery_id, "source_role": "source"}
        first = await test_client.post("/api/mp/image-design/library", headers=mp_accounts[0]["headers"], json=payload)
        again = await test_client.post("/api/mp/image-design/library", headers=mp_accounts[0]["headers"], json=payload)
        assert first.status_code == again.status_code == 200, (first.text, again.text)
        assert first.json()["item"]["id"] == again.json()["item"]["id"]
        assert first.json()["item"]["source_role"] == "source"
        changed = await test_client.patch(
            f"/api/material-library/categories/{gallery_id}",
            headers=admin_headers,
            params={"material_type": "image"},
            json={"visibility": "private"},
        )
        assert changed.status_code == 200, changed.text
        revoked = await test_client.get(first.json()["item"]["file_url"], headers=mp_accounts[0]["headers"])
        assert revoked.status_code == 404, revoked.text
        rejected = await test_client.post(
            "/api/mp/image-design/library", headers=mp_accounts[1]["headers"], json=payload
        )
        assert rejected.status_code == 404, rejected.text
    finally:
        if item_id:
            await test_client.delete(f"/api/material-library/items/{item_id}", headers=admin_headers)
        await test_client.request(
            "DELETE",
            f"/api/material-library/categories/{gallery_id}",
            headers=admin_headers,
            params={"material_type": "image"},
            json={},
        )
