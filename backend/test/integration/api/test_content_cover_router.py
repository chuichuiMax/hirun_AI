from __future__ import annotations

import io

import pytest
from PIL import Image

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


def _png() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (320, 420), "#D9473F").save(output, format="PNG")
    return output.getvalue()


async def test_cover_asset_upload_is_private_and_deletable(test_client, admin_headers, standard_user):
    bootstrap = await test_client.get("/api/content/covers/bootstrap", headers=admin_headers)
    assert bootstrap.status_code == 200, bootstrap.text
    body = bootstrap.json()
    assert {item["id"] for item in body["templates"]} >= {
        "grid_3x3",
        "split_vertical",
        "split_horizontal",
        "before_after",
        "card_stack",
        "hero_thumbs",
    }
    assert set(body["image2"]) == {
        "configured",
        "base_url",
        "api_key_configured",
        "model",
        "source",
        "can_manage",
        "quality",
        "modes",
    }
    assert body["image2"]["can_manage"] is True
    assert "api_key" not in body["image2"]

    image_bytes = _png()
    uploaded = await test_client.post(
        "/api/content/covers/assets",
        headers=admin_headers,
        data={"role": "source"},
        files={"file": ("source.png", image_bytes, "image/png")},
    )
    assert uploaded.status_code == 201, uploaded.text
    asset = uploaded.json()["asset"]
    assert asset["role"] == "source"
    assert asset["content_type"] == "image/png"
    assert (asset["width"], asset["height"]) == (320, 420)

    try:
        downloaded = await test_client.get(
            f"/api/content/covers/assets/{asset['id']}/file",
            headers=admin_headers,
        )
        assert downloaded.status_code == 200, downloaded.text
        with Image.open(io.BytesIO(downloaded.content)) as result:
            assert result.size == (320, 420)
            assert result.format == "PNG"

        forbidden = await test_client.get(
            f"/api/content/covers/assets/{asset['id']}/file",
            headers=standard_user["headers"],
        )
        assert forbidden.status_code == 404

        invalid = await test_client.post(
            "/api/content/covers/assets",
            headers=admin_headers,
            data={"role": "source"},
            files={"file": ("fake.png", b"not-an-image", "image/png")},
        )
        assert invalid.status_code == 400
        assert invalid.json()["detail"]["error"]["code"] == "COVER_IMAGE_INVALID"
    finally:
        deleted = await test_client.delete(
            f"/api/content/covers/assets/{asset['id']}",
            headers=admin_headers,
        )
        assert deleted.status_code == 200, deleted.text

    missing = await test_client.get(
        f"/api/content/covers/assets/{asset['id']}/file",
        headers=admin_headers,
    )
    assert missing.status_code == 404
