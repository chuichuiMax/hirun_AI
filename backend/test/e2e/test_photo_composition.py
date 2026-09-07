"""真实图库、组合预览、草稿恢复及 HyCanvas Worker 成图；不调用模型。"""

import asyncio
import json
import os
import socket
import uuid
from pathlib import Path

import httpx
import pytest
from patchright.async_api import async_playwright, expect
from sqlalchemy import select

from yuxi.services.content_cover_service import create_hycanvas_cover_job
from yuxi.services.hycanvas_service import HyCanvasClient
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import User
from yuxi.storage.postgres.models_content import ContentTask
from yuxi.utils.auth_utils import AuthUtils


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_photo_composition_preview_persistence_and_worker():
    uid = os.getenv("RULE_EDITOR_TEST_UID")
    if not uid:
        pytest.skip("需要测试管理员")
    pg_manager.initialize()
    async with pg_manager.AsyncSession() as db:
        user = (await db.execute(select(User).where(User.uid == uid))).scalar_one()
        token = AuthUtils.create_access_token({"sub": str(user.id)})
    headers = {"Authorization": f"Bearer {token}"}
    task_id = design_id = None
    async with httpx.AsyncClient(base_url="http://localhost:5050", headers=headers, timeout=60) as client:
        try:
            items = (
                await client.get(
                    "/api/material-library/items",
                    params={
                        "material_type": "image",
                        "status": "enabled",
                        "page_size": 100,
                    },
                )
            ).json()["items"]
            assert len(items) >= 2, "测试图库需要至少两张图片"
            primary, secondary = items[:2]
            galleries = (
                await client.get("/api/material-library/galleries", params={"industry_slug": "decoration"})
            ).json()
            gallery_list = galleries.get("items", galleries.get("galleries", []))
            secondary_gallery = next(item for item in gallery_list if item["id"] == secondary["category"])
            templates = (await client.get("/api/content/covers/hycanvas/templates")).json()["templates"]
            template = templates[0]
            response = await client.post(
                "/api/content/tasks",
                json={
                    "industry_template_id": "industry-decoration-v3",
                    "content_goal": "acquire",
                    "name": "pytest 图片组合 " + uuid.uuid4().hex[:8],
                },
            )
            response.raise_for_status()
            task_id = response.json()["task"]["id"]
            brief = {
                "topic": "厨房动线规划服务",
                "audience": ["准备装修厨房的新手业主"],
                "content_goal": "educate",
                "channel": "小红书",
                "persona": {"style": "亲切、具体、专业"},
                "form_values": {
                    "brand_name": "隔离测试品牌",
                    "product": "厨房动线规划服务",
                    "audience": "准备装修厨房的新手业主",
                    "pain": "收纳位置不顺手",
                    "project_name": "仅用于自动化验证的合成案例",
                    "city": "长沙",
                    "proof": "未提供效果数据，不得编造已发生结果",
                    "cta": "分享问题",
                },
            }
            brief["form_values"].update(
                advantage="报价清楚、节点留档",
                project_type="三室两厅",
                craft_and_materials="防水与节点验收留档",
            )
            brief["visual_material"] = {"image_item_id": primary["id"], "hycanvas_template_id": template["id"]}
            response = await client.put(f"/api/content/tasks/{task_id}/brief", json={"brief": brief})
            response.raise_for_status()
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", f"--host-resolver-rules=MAP localhost {socket.gethostbyname('web')}"],
                )
                try:
                    page = await browser.new_page(viewport={"width": 1440, "height": 1100})
                    await page.add_init_script(f'localStorage.setItem("user_token", {json.dumps(token)})')
                    await page.goto(f"http://localhost:5173/content/tasks/{task_id}")
                    component = page.locator(".photo-composition")
                    await expect(component).to_be_visible(timeout=30000)
                    await component.get_by_text("图片组合", exact=True).click()
                    await expect(component.locator(".composition-slot")).to_have_count(2)
                    await expect(component).to_contain_text("还需插入 1 张图片")
                    await component.get_by_role("button", name="选择组合图片 2", exact=True).click()
                    modal = page.locator(".gallery-modal-content")
                    if secondary_gallery.get("parent_id"):
                        parent = next(item for item in gallery_list if item["id"] == secondary_gallery["parent_id"])
                        await modal.get_by_role("button").filter(has_text=parent["name"]).click()
                    await modal.get_by_role("button").filter(has_text=secondary_gallery["name"]).click()
                    await modal.locator(".image-choice").filter(has_text=secondary["name"]).click()
                    await modal.get_by_role("button", name="确认选择", exact=True).click()
                    preview = page.locator('.selected-gallery-preview-card img[alt$="合成效果"]')
                    await expect(preview).to_be_visible(timeout=30000)
                    await expect(preview).to_have_js_property("naturalWidth", 270)
                    await component.get_by_role("button", name="设为首图", exact=True).click()
                    await component.get_by_role("button", name="调整裁切", exact=True).first.click()
                    await component.get_by_role("slider").first.focus()
                    await page.keyboard.press("ArrowRight")

                    def crop_saved(response):
                        if response.request.method != "PUT" or not response.url.endswith("/brief"):
                            return False
                        visual = response.request.post_data_json["brief"]["visual_material"]
                        composition = visual.get("photo_composition")
                        return composition and composition["slots"][0]["focal_x"] == 0.52

                    async with page.expect_response(crop_saved) as save_response:
                        await component.get_by_role("slider").first.press("ArrowRight")
                    saved_response = await save_response.value
                    assert saved_response.status == 200, await saved_response.text()
                    assert (await saved_response.json())["task"]["brief"]["visual_material"]["photo_composition"]
                    await page.reload()
                    await expect(component.locator(".composition-slot img")).to_have_count(2, timeout=30000)
                    await expect(preview).to_be_visible(timeout=30000)
                    await component.screenshot(path="/tmp/photo-composition-ui.png")
                    await page.locator(".selected-gallery-preview-grid").screenshot(
                        path="/tmp/photo-composition-preview.png"
                    )
                    await page.set_viewport_size({"width": 720, "height": 1000})
                    assert await component.evaluate("el => el.scrollWidth <= el.clientWidth")
                    # Changing layouts preserves the chosen primary and shows missing slots.
                    await component.get_by_role("button", name="焦点居左", exact=True).click()
                    await expect(component.locator(".composition-slot")).to_have_count(3)
                    await expect(component).to_contain_text("还需插入 1 张图片")
                    await component.get_by_role("button", name="2 张图片", exact=True).click()
                    await page.wait_for_timeout(1200)
                finally:
                    await browser.close()
            saved = (await client.get(f"/api/content/tasks/{task_id}")).json()["task"]["brief"]
            value = saved["visual_material"]
            assert value["image_item_id"] == secondary["id"]
            assert value["photo_composition"]["slots"][0]["focal_x"] == 0.52
            # Use the same preview path before generation and verify bad selections are rejected.
            payload = {"image_item_id": value["image_item_id"], "photo_composition": value["photo_composition"]}
            response = await client.post(
                f"/api/content/covers/hycanvas/templates/{template['id']}/preview.png", json=payload
            )
            assert response.status_code == 200, response.text[:1000]
            Path("/tmp/photo-composition-preview.png").write_bytes(response.content)
            bad = json.loads(json.dumps(payload))
            bad["photo_composition"]["slots"][1]["image_item_id"] = "unowned-image"
            assert (
                await client.post(f"/api/content/covers/hycanvas/templates/{template['id']}/preview.png", json=bad)
            ).status_code == 422
            # Compile the UI's saved form, freezing selected source assets for the worker.
            brief["visual_material"] = {
                key: value.get(key) for key in ["image_item_id", "hycanvas_template_id", "photo_composition"]
            }
            response = await client.post(f"/api/content/tasks/{task_id}/compile-brief", json={"brief": brief})
            assert response.status_code == 200, response.text[:1000]
            changed = json.loads(json.dumps(brief))
            changed["visual_material"]["photo_composition"]["slots"][0]["focal_x"] = 0.1
            assert (await client.put(f"/api/content/tasks/{task_id}/brief", json={"brief": changed})).status_code == 409
            async with pg_manager.AsyncSession() as db:
                task = await db.get(ContentTask, task_id)
                visual = task.runtime_config_snapshot_json["visual_material"]
                user = (await db.execute(select(User).where(User.uid == uid))).scalar_one()
                fields = {
                    field.get("key") or field["label"]: "案例"
                    for field in visual["hycanvas_fillable_fields"]
                    if field.get("kind") == "text" and field.get("semanticRole") != "label"
                }
                result = await create_hycanvas_cover_job(
                    db,
                    user,
                    content_task_id=task_id,
                    source_asset_id=visual["image_asset_id"],
                    template_id=template["id"],
                    title="图片组合验证",
                    fields=fields,
                    image_field_label=None,
                    idempotency_key=uuid.uuid4().hex,
                    parameters={},
                    photo_composition=visual["photo_composition"],
                )
                job_id = result["job"]["id"]
            for _ in range(60):
                job = (await client.get(f"/api/content/covers/jobs/{job_id}")).json()["job"]
                if job["status"] in {"succeeded", "failed"}:
                    break
                await asyncio.sleep(1)
            assert job["status"] == "succeeded", json.dumps(job, ensure_ascii=False)
            asset_id = job["result"]["asset_ids"][0]
            final = await client.get(f"/api/content/covers/assets/{asset_id}/file")
            assert final.status_code == 200
            Path("/tmp/photo-composition-final.png").write_bytes(final.content)
            design_id = job["result"]["hycanvas_design_snapshot"]["design_id"]
            hycanvas = HyCanvasClient.from_env()
            document = await hycanvas._request("GET", f"/api/v1/designs/{design_id}/file")
            Path("/tmp/photo-composition-design.json").write_text(json.dumps(document))
            grid = document["pages"][0]["children"][0]
            assert grid["type"] == "grid" and len(grid["children"]) == 2
            assert grid["locked"] is False
            assert grid["children"][0]["children"][0]["focalPoint"]["x"] == 0.52
        finally:
            try:
                if design_id:
                    await delete_test_design(design_id)
            finally:
                if task_id:
                    await client.delete(f"/api/content/tasks/{task_id}")
                await pg_manager.async_engine.dispose()


async def delete_test_design(design_id):
    """Use the supported editor session to delete only this test's design."""
    hycanvas = HyCanvasClient.from_env()
    issued = await hycanvas._request("POST", f"/api/v1/auth/integration-ticket/{design_id}")
    async with httpx.AsyncClient(base_url=hycanvas.base_url, timeout=30) as editor:
        response = await editor.get(
            "/api/v1/auth/integration",
            params={
                "ticket": issued["ticket"],
                "designId": design_id,
                "next": f"/editor/?id={design_id}",
            },
        )
        assert response.status_code == 302
        response = await editor.delete(f"/api/v1/designs/{design_id}")
        response.raise_for_status()
