from __future__ import annotations

import uuid
import io

import pytest
from PIL import Image


pytestmark = pytest.mark.asyncio


def _png() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (48, 36), "#4A7BF7").save(output, format="PNG")
    return output.getvalue()


async def test_content_bootstrap_and_v3_task_flow(test_client, admin_headers):
    material_response = await test_client.post(
        "/api/material-library/images/import",
        headers=admin_headers,
        data={"category": "product"},
        files=[("files", (f"content-{uuid.uuid4().hex}.png", _png(), "image/png"))],
    )
    assert material_response.status_code == 201, material_response.text
    material = material_response.json()["items"][0]
    bootstrap_response = await test_client.get("/api/content/bootstrap", headers=admin_headers)
    assert bootstrap_response.status_code == 200, bootstrap_response.text
    bootstrap = bootstrap_response.json()
    assert len(bootstrap["industry_templates"]) == 6
    assert len([item for item in bootstrap["rule_bundle"]["methods"] if item["method_type"] == "core"]) == 4
    assert len(bootstrap["rule_bundle"]["title_formulas"]) == 7
    assert len(bootstrap["rule_bundle"]["content_formulas"]) == 4

    template = next(item for item in bootstrap["industry_templates"] if item["slug"] == "decoration")
    create_response = await test_client.post(
        "/api/content/tasks",
        headers=admin_headers,
        json={
            "industry_template_id": template["id"],
            "mode": "quick",
            "content_goal": template["default_goal"],
            "name": f"pytest_content_{uuid.uuid4().hex[:8]}",
        },
    )
    assert create_response.status_code == 200, create_response.text
    task_id = create_response.json()["task"]["id"]
    assert create_response.json()["task"]["runtime_config_snapshot"]["schema_version"] == 3

    try:
        missing_image_response = await test_client.post(
            f"/api/content/tasks/{task_id}/compile-brief",
            headers=admin_headers,
            json={
                "brief": {
                    "form_values": {
                        "brand_name": "Pytest 品牌",
                        "audience": ["准备装修的业主"],
                        "pain": ["隐蔽工程难追溯"],
                        "advantage": ["标准工序留档"],
                        "project_type": "三室两厅",
                        "craft_and_materials": "水电施工与隐蔽验收",
                    }
                }
            },
        )
        assert missing_image_response.status_code == 422
        assert missing_image_response.json()["detail"]["error"]["code"] == "CONTENT_IMAGE_MATERIAL_REQUIRED"

        compile_response = await test_client.post(
            f"/api/content/tasks/{task_id}/compile-brief",
            headers=admin_headers,
            json={
                "brief": {
                    "visual_material": {"image_item_id": material["id"]},
                    "form_values": {
                        "brand_name": "Pytest 品牌",
                        "audience": ["准备装修的业主"],
                        "pain": ["隐蔽工程难追溯"],
                        "advantage": ["标准工序留档"],
                        "project_type": "三室两厅",
                        "craft_and_materials": "水电施工与隐蔽验收",
                    },
                }
            },
        )
        assert compile_response.status_code == 200, compile_response.text
        compiled = compile_response.json()
        assert compiled["compiled"] is True
        assert compiled["task"]["status"] == "brief_ready"
        assert compiled["task"]["evidence_bundle"]["items"]
        assert compiled["task"]["selected_image_item_id"] == material["id"]
        assert compiled["task"]["runtime_config_snapshot"]["visual_material"]["image_asset_id"] == material["asset_id"]

        protected_response = await test_client.delete(
            f"/api/material-library/items/{material['id']}", headers=admin_headers
        )
        assert protected_response.status_code == 409
        assert protected_response.json()["detail"]["error"]["code"] == "MATERIAL_IN_USE"

        removed_strategy_response = await test_client.post(
            f"/api/content/tasks/{task_id}/strategy/recommend",
            headers=admin_headers,
        )
        assert removed_strategy_response.status_code == 404

        missing_asset_response = await test_client.patch(
            "/api/content/artifacts/not-real",
            headers=admin_headers,
            json={"title": "标题", "body": "正文", "topics": []},
        )
        assert missing_asset_response.status_code == 404
        assert missing_asset_response.json()["detail"]["error"]["code"] == "CONTENT_ARTIFACT_NOT_FOUND"
    finally:
        delete_response = await test_client.delete(f"/api/content/tasks/{task_id}", headers=admin_headers)
        assert delete_response.status_code == 200, delete_response.text
        material_delete = await test_client.delete(
            f"/api/material-library/items/{material['id']}", headers=admin_headers
        )
        assert material_delete.status_code == 200, material_delete.text
