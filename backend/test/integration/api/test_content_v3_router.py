from __future__ import annotations

import uuid
import io

import pytest
from PIL import Image


pytestmark = pytest.mark.asyncio


def _png() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (48, 36), "#315EFB").save(output, format="PNG")
    return output.getvalue()


async def test_v3_strategy_preview_permissions_and_removed_v2_route(test_client, admin_headers, standard_user):
    hycanvas_template_id = "01c7f0bc-3ce5-431b-82e5-7390e9bc246e"
    material_response = await test_client.post(
        "/api/material-library/images/import",
        headers=admin_headers,
        data={"category": "product"},
        files=[("files", (f"content-v3-{uuid.uuid4().hex}.png", _png(), "image/png"))],
    )
    assert material_response.status_code == 201, material_response.text
    material = material_response.json()["items"][0]
    bootstrap_response = await test_client.get("/api/content/bootstrap", headers=admin_headers)
    assert bootstrap_response.status_code == 200, bootstrap_response.text
    template = next(item for item in bootstrap_response.json()["industry_templates"] if item["slug"] == "decoration")
    create_response = await test_client.post(
        "/api/content/tasks",
        headers=admin_headers,
        json={
            "industry_template_id": template["id"],
            "mode": "quick",
            "content_goal": "brand",
            "content_type_code": "CT05",
            "name": f"pytest_content_v3_{uuid.uuid4().hex[:8]}",
        },
    )
    assert create_response.status_code == 200, create_response.text
    task_id = create_response.json()["task"]["id"]
    assert create_response.json()["task"]["rule_version_id"] == "content-rules-platform-v3"
    assert create_response.json()["task"]["runtime_config_snapshot"]["schema_version"] == 3
    assert create_response.json()["task"]["latest_run_id"] is None

    try:
        compile_response = await test_client.post(
            f"/api/content/tasks/{task_id}/compile-brief",
            headers=admin_headers,
            json={
                "brief": {
                    "visual_material": {
                        "image_item_id": material["id"],
                        "hycanvas_template_id": hycanvas_template_id,
                    },
                    "audience": ["准备装修的业主"],
                    "form_values": {
                        "brand_name": "V3 测试品牌",
                        "process": ["水电定位", "隐蔽验收"],
                        "result": "施工节点可追溯",
                        "advantage": ["标准工序留档"],
                        "pain": ["隐蔽工程难追溯"],
                        "project_type": "三室两厅",
                        "craft_and_materials": "水电施工与隐蔽验收",
                    },
                }
            },
        )
        assert compile_response.status_code == 200, compile_response.text
        assert (
            compile_response.json()["task"]["runtime_config_snapshot"]["visual_material"]["hycanvas_template_id"]
            == hycanvas_template_id
        )

        denied_response = await test_client.post(
            f"/api/content/tasks/{task_id}/strategy/recommend-v3",
            headers=standard_user["headers"],
            json={"content_direction_code": "CT05"},
        )
        assert denied_response.status_code == 404
        assert denied_response.json()["detail"]["error"]["code"] == "CONTENT_TASK_NOT_FOUND"

        preview_response = await test_client.post(
            f"/api/content/tasks/{task_id}/strategy/recommend-v3",
            headers=admin_headers,
            json={"content_direction_code": "CT05"},
        )
        assert preview_response.status_code == 200, preview_response.text
        preview = preview_response.json()
        assert preview["preview"] is True
        assert preview["creates_run"] is False
        assert preview["rule_version_id"] == "content-rules-platform-v3"
        assert preview["industry_pack_version_id"] == "industry-pack-decoration-v3"
        assert preview["decision"]["status"] == "matched"
        assert len(preview["decision"]["eligible_groups"]) == 4

        task_response = await test_client.get(f"/api/content/tasks/{task_id}", headers=admin_headers)
        assert task_response.status_code == 200, task_response.text
        assert task_response.json()["task"]["latest_run_id"] is None
        assert task_response.json()["task"]["strategy"] == {}

        removed_response = await test_client.post(
            f"/api/content/tasks/{task_id}/strategy/recommend-v2",
            headers=admin_headers,
            json={"random_seed": 7, "limit": 5},
        )
        assert removed_response.status_code == 404
    finally:
        delete_response = await test_client.delete(f"/api/content/tasks/{task_id}", headers=admin_headers)
        assert delete_response.status_code == 200, delete_response.text
        material_delete = await test_client.delete(
            f"/api/material-library/items/{material['id']}", headers=admin_headers
        )
        assert material_delete.status_code == 200, material_delete.text


async def test_gallery_image_cannot_be_selected_by_a_second_task(test_client, admin_headers):
    material_response = await test_client.post(
        "/api/material-library/images/import",
        headers=admin_headers,
        data={"category": "product"},
        files=[("files", (f"content-image-in-use-{uuid.uuid4().hex}.png", _png(), "image/png"))],
    )
    assert material_response.status_code == 201, material_response.text
    material = material_response.json()["items"][0]
    bootstrap_response = await test_client.get("/api/content/bootstrap", headers=admin_headers)
    assert bootstrap_response.status_code == 200, bootstrap_response.text
    template = next(item for item in bootstrap_response.json()["industry_templates"] if item["slug"] == "decoration")
    task_ids = []
    try:
        for suffix in ("a", "b"):
            created = await test_client.post(
                "/api/content/tasks",
                headers=admin_headers,
                json={
                    "industry_template_id": template["id"],
                    "mode": "quick",
                    "content_goal": "brand",
                    "content_type_code": "CT05",
                    "name": f"pytest_image_in_use_{suffix}_{uuid.uuid4().hex[:8]}",
                },
            )
            assert created.status_code == 200, created.text
            task_ids.append(created.json()["task"]["id"])

        first = await test_client.put(
            f"/api/content/tasks/{task_ids[0]}/brief",
            headers=admin_headers,
            json={"brief": {"visual_material": {"image_item_id": material["id"]}}},
        )
        assert first.status_code == 200, first.text
        assert first.json()["task"]["selected_image_item_id"] == material["id"]

        listed = await test_client.get(
            f"/api/material-library/items?material_type=image&category={material['category']}&query={material['name']}",
            headers=admin_headers,
        )
        assert listed.status_code == 200, listed.text
        used_item = next(item for item in listed.json()["items"] if item["id"] == material["id"])
        assert used_item["in_use"] is True

        excluded = await test_client.get(
            "/api/material-library/items"
            f"?material_type=image&category={material['category']}&query={material['name']}"
            f"&exclude_task_id={task_ids[0]}",
            headers=admin_headers,
        )
        assert excluded.status_code == 200, excluded.text
        current_item = next(item for item in excluded.json()["items"] if item["id"] == material["id"])
        assert current_item["in_use"] is False

        second = await test_client.put(
            f"/api/content/tasks/{task_ids[1]}/brief",
            headers=admin_headers,
            json={"brief": {"visual_material": {"image_item_id": material["id"]}}},
        )
        assert second.status_code == 409, second.text
        assert second.json()["detail"]["error"]["code"] == "CONTENT_IMAGE_MATERIAL_IN_USE"
    finally:
        for task_id in task_ids:
            deleted = await test_client.delete(f"/api/content/tasks/{task_id}", headers=admin_headers)
            assert deleted.status_code == 200, deleted.text
        material_delete = await test_client.delete(
            f"/api/material-library/items/{material['id']}", headers=admin_headers
        )
        assert material_delete.status_code == 200, material_delete.text


async def test_failed_task_releases_gallery_image_for_reuse(test_client, admin_headers):
    material_response = await test_client.post(
        "/api/material-library/images/import",
        headers=admin_headers,
        data={"category": "product"},
        files=[("files", (f"content-image-failed-release-{uuid.uuid4().hex}.png", _png(), "image/png"))],
    )
    assert material_response.status_code == 201, material_response.text
    material = material_response.json()["items"][0]
    bootstrap_response = await test_client.get("/api/content/bootstrap", headers=admin_headers)
    assert bootstrap_response.status_code == 200, bootstrap_response.text
    template = next(item for item in bootstrap_response.json()["industry_templates"] if item["slug"] == "decoration")
    task_ids = []
    try:
        for suffix in ("failed", "reuse"):
            created = await test_client.post(
                "/api/content/tasks",
                headers=admin_headers,
                json={
                    "industry_template_id": template["id"],
                    "mode": "quick",
                    "content_goal": "brand",
                    "content_type_code": "CT05",
                    "name": f"pytest_image_failed_release_{suffix}_{uuid.uuid4().hex[:8]}",
                },
            )
            assert created.status_code == 200, created.text
            task_ids.append(created.json()["task"]["id"])

        first = await test_client.put(
            f"/api/content/tasks/{task_ids[0]}/brief",
            headers=admin_headers,
            json={"brief": {"visual_material": {"image_item_id": material["id"]}}},
        )
        assert first.status_code == 200, first.text
        assert first.json()["task"]["selected_image_item_id"] == material["id"]

        from sqlalchemy import update

        from yuxi.storage.postgres.manager import pg_manager
        from yuxi.storage.postgres.models_content import ContentTask

        async with pg_manager.get_async_session_context() as db:
            await db.execute(
                update(ContentTask).where(ContentTask.id == task_ids[0]).values(status="failed")
            )
            await db.commit()

        listed = await test_client.get(
            f"/api/material-library/items?material_type=image&category={material['category']}&query={material['name']}",
            headers=admin_headers,
        )
        assert listed.status_code == 200, listed.text
        released_item = next(item for item in listed.json()["items"] if item["id"] == material["id"])
        assert released_item["in_use"] is False

        second = await test_client.put(
            f"/api/content/tasks/{task_ids[1]}/brief",
            headers=admin_headers,
            json={"brief": {"visual_material": {"image_item_id": material["id"]}}},
        )
        assert second.status_code == 200, second.text
        assert second.json()["task"]["selected_image_item_id"] == material["id"]
    finally:
        for task_id in task_ids:
            deleted = await test_client.delete(f"/api/content/tasks/{task_id}", headers=admin_headers)
            assert deleted.status_code == 200, deleted.text
        material_delete = await test_client.delete(
            f"/api/material-library/items/{material['id']}", headers=admin_headers
        )
        assert material_delete.status_code == 200, material_delete.text
