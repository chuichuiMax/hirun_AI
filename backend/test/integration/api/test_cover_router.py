from __future__ import annotations

import uuid

import pytest


pytestmark = pytest.mark.asyncio


def _payload(**overrides):
    data = {
        "category": "chinese",
        "image_url": f"/public/covers/{uuid.uuid4().hex}.jpg",
        "image_name": f"cover-{uuid.uuid4().hex[:8]}.jpg",
        "title": "装修报价清单",
        "enabled": True,
    }
    data.update(overrides)
    return data


async def test_cover_crud_filter_and_toggle(test_client, admin_headers):
    created = await test_client.post("/api/covers", headers=admin_headers, json=_payload())
    assert created.status_code == 200, created.text
    cover = created.json()["cover"]
    cover_pk = cover["id"]

    try:
        listed = await test_client.get(
            "/api/covers",
            headers=admin_headers,
            params={"category": "chinese"},
        )
        assert listed.status_code == 200, listed.text
        ids = [item["id"] for item in listed.json()["covers"]]
        assert cover_pk in ids
        assert listed.json()["covers"][0]["generation_count"] == 0
        assert cover["image_name"] == created.json()["cover"]["image_name"]

        searched = await test_client.get(
            "/api/covers",
            headers=admin_headers,
            params={"category": "chinese", "keyword": cover["image_name"].split("-", 1)[-1].split(".")[0]},
        )
        assert searched.status_code == 200, searched.text
        assert cover_pk in [item["id"] for item in searched.json()["covers"]]

        missed = await test_client.get(
            "/api/covers",
            headers=admin_headers,
            params={"category": "chinese", "keyword": "not-this-cover-name"},
        )
        assert missed.status_code == 200, missed.text
        assert cover_pk not in [item["id"] for item in missed.json()["covers"]]

        duplicate = await test_client.post(
            "/api/covers",
            headers=admin_headers,
            json=_payload(image_name=cover["image_name"]),
        )
        assert duplicate.status_code == 409, duplicate.text
        assert duplicate.json()["detail"]["error"]["code"] == "COVER_IMAGE_NAME_EXISTS"

        other_category = await test_client.get(
            "/api/covers",
            headers=admin_headers,
            params={"category": "european"},
        )
        assert other_category.status_code == 200, other_category.text
        assert cover_pk not in [item["id"] for item in other_category.json()["covers"]]

        invalid = await test_client.get(
            "/api/covers",
            headers=admin_headers,
            params={"category": "unknown"},
        )
        assert invalid.status_code == 422, invalid.text

        toggled = await test_client.patch(
            f"/api/covers/{cover_pk}",
            headers=admin_headers,
            json={"enabled": False},
        )
        assert toggled.status_code == 200, toggled.text
        assert toggled.json()["cover"]["enabled"] is False
    finally:
        deleted = await test_client.delete(f"/api/covers/{cover_pk}", headers=admin_headers)
        assert deleted.status_code == 200, deleted.text

    gone = await test_client.patch(
        f"/api/covers/{cover_pk}",
        headers=admin_headers,
        json={"enabled": True},
    )
    assert gone.status_code == 404
    assert gone.json()["detail"]["error"]["code"] == "COVER_NOT_FOUND"
