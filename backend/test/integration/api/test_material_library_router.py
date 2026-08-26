from __future__ import annotations

import io
import os
import uuid

import pytest
import pytest_asyncio
from PIL import Image
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from yuxi.storage.postgres.models_business import Department, OperationLog, User
from yuxi.utils.auth_utils import AuthUtils

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


def _png() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (48, 36), "#4A7BF7").save(output, format="PNG")
    return output.getvalue()


@pytest_asyncio.fixture
async def material_users(test_client):
    suffix = uuid.uuid4().hex[:10]
    password = f"Pw!{uuid.uuid4().hex}"
    engine = create_async_engine(os.environ["POSTGRES_URL"])
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as db:
        department = Department(name=f"pytest-material-{suffix}", description="material library integration")
        db.add(department)
        await db.flush()
        users = [
            User(
                username=f"pytest_material_owner_{suffix}",
                uid=f"pytest_material_owner_{suffix}",
                password_hash=AuthUtils.hash_password(password),
                role="user",
                department_id=department.id,
            ),
            User(
                username=f"pytest_material_other_{suffix}",
                uid=f"pytest_material_other_{suffix}",
                password_hash=AuthUtils.hash_password(password),
                role="user",
                department_id=department.id,
            ),
        ]
        db.add_all(users)
        await db.flush()
        user_ids = [user.id for user in users]
        department_id = department.id
        credentials = [user.uid for user in users]
        await db.commit()

    headers = []
    for uid in credentials:
        login = await test_client.post("/api/auth/token", data={"username": uid, "password": password})
        assert login.status_code == 200, login.text
        headers.append({"Authorization": f"Bearer {login.json()['access_token']}"})
    try:
        yield {"owner": headers[0], "other": headers[1]}
    finally:
        async with session_factory() as db:
            await db.execute(delete(OperationLog).where(OperationLog.user_id.in_(user_ids)))
            await db.execute(delete(User).where(User.id.in_(user_ids)))
            await db.execute(delete(Department).where(Department.id == department_id))
            await db.commit()
        await engine.dispose()


async def test_material_image_round_trip_uses_private_image_bucket(test_client, material_users):
    owner_headers = material_users["owner"]
    uploaded = await test_client.post(
        "/api/material-library/images/import",
        headers=owner_headers,
        data={"category": "integration", "tags": "blue,sample"},
        files=[("files", ("fixture.png", _png(), "image/png"))],
    )
    assert uploaded.status_code == 201, uploaded.text
    item = uploaded.json()["items"][0]
    assert item["material_type"] == "image"
    assert item["category"] == "integration"

    from yuxi.storage.postgres.models_content import ContentCoverAsset

    engine = create_async_engine(os.environ["POSTGRES_URL"])
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as db:
        asset = await db.get(ContentCoverAsset, item["asset_id"])
        assert asset is not None
        assert asset.bucket_name == "image"
        assert asset.object_name == f"material-library/{asset.owner_uid}/images/{asset.id}/image.png"
    await engine.dispose()

    listed = await test_client.get(
        "/api/material-library/items?material_type=image&query=integration",
        headers=owner_headers,
    )
    assert listed.status_code == 200, listed.text
    assert item["id"] in {entry["id"] for entry in listed.json()["items"]}

    downloaded = await test_client.get(item["file_url"], headers=owner_headers)
    assert downloaded.status_code == 200, downloaded.text
    with Image.open(io.BytesIO(downloaded.content)) as image:
        assert image.size == (48, 36)

    private = await test_client.get(item["file_url"], headers=material_users["other"])
    assert private.status_code == 404

    deleted = await test_client.delete(f"/api/material-library/items/{item['id']}", headers=owner_headers)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["object_deleted"] is True
    missing = await test_client.get(item["file_url"], headers=owner_headers)
    assert missing.status_code == 404
