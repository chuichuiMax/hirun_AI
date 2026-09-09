from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from server.routers.content_router import content
from server.utils.auth_middleware import get_db, get_required_user
from yuxi.services import xiaohongshu_service
from yuxi.storage.postgres.models_content import (
    ContentArtifact,
    ContentArtifactVersion,
    ContentCoverAsset,
    ContentDistributionJob,
    ContentDistributionResult,
    XiaohongshuAccount,
)
from yuxi.utils.datetime_utils import utc_now_naive


@pytest.mark.parametrize("mode", ["draft", "publish"])
@pytest.mark.parametrize(
    "role,snapshot,owner,deleted,expected_status",
    [
        pytest.param("output", {}, "alice", False, 200, id="generated-cover"),
        pytest.param(
            "source",
            {"design_id": "design-1", "cover_asset_id": "cover-1"},
            "alice",
            False,
            200,
            id="bound-hycanvas-cover",
        ),
        pytest.param("source", {}, "alice", False, 409, id="unbound-source"),
        pytest.param(
            "source",
            {"design_id": "design-1", "cover_asset_id": "old-cover"},
            "alice",
            False,
            409,
            id="stale-design-snapshot",
        ),
        pytest.param(
            "source",
            {"cover_asset_id": "cover-1"},
            "alice",
            False,
            409,
            id="missing-design",
        ),
        pytest.param(
            "template",
            {"design_id": "design-1", "cover_asset_id": "cover-1"},
            "alice",
            False,
            409,
            id="template-is-not-cover",
        ),
        pytest.param(
            "source",
            {"design_id": "design-1", "cover_asset_id": "cover-1"},
            "bob",
            False,
            409,
            id="other-users-cover",
        ),
        pytest.param(
            "source",
            {"design_id": "design-1", "cover_asset_id": "cover-1"},
            "alice",
            True,
            409,
            id="deleted-cover",
        ),
        pytest.param(
            None,
            {"design_id": "design-1", "cover_asset_id": "cover-1"},
            "alice",
            False,
            409,
            id="missing-cover",
        ),
    ],
)
@pytest.mark.asyncio
async def test_distribution_api_uses_bound_cover(monkeypatch, mode, role, snapshot, owner, deleted, expected_status):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        for model in (
            ContentArtifact,
            ContentArtifactVersion,
            ContentCoverAsset,
            XiaohongshuAccount,
            ContentDistributionJob,
            ContentDistributionResult,
        ):
            await connection.run_sync(model.__table__.create)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    enqueued = []

    async def enqueue_job(function, job_id, **kwargs):
        enqueued.append((function, job_id))
        return SimpleNamespace(job_id=job_id)

    async def get_queue():
        return SimpleNamespace(enqueue_job=enqueue_job)

    monkeypatch.setattr(xiaohongshu_service, "get_arq_pool", get_queue)
    try:
        async with session_factory() as db:
            db.add(
                ContentArtifact(
                    id="artifact-1",
                    task_id="task-1",
                    title="封面发布验证",
                    body="已保存封面的内容",
                    created_by="alice",
                    review_snapshot={"status": "passed"},
                    cover_asset_id="cover-1",
                    hycanvas_design_snapshot=snapshot,
                )
            )
            db.add(
                ContentArtifactVersion(
                    id="version-1",
                    artifact_id="artifact-1",
                    version=1,
                    title="封面发布验证",
                    body="已保存封面的内容",
                    rule_version_id="rules-1",
                    created_by="alice",
                    cover_asset_id="cover-1",
                    hycanvas_design_snapshot=snapshot,
                )
            )
            db.add(
                XiaohongshuAccount(
                    id="account-1",
                    owner_uid="alice",
                    display_name="测试账号",
                    enabled=True,
                    login_status="logged_in",
                )
            )
            if role is not None:
                db.add(
                    ContentCoverAsset(
                        id="cover-1",
                        owner_uid=owner,
                        role=role,
                        original_file_name="cover.png",
                        content_type="image/png",
                        file_size=100,
                        image_width=1080,
                        image_height=1440,
                        sha256="a" * 64,
                        bucket_name="covers",
                        object_name="alice/hycanvas.png",
                        deleted_at=utc_now_naive() if deleted else None,
                    )
                )
            await db.commit()

            async def override_db():
                yield db

            async def override_user():
                return SimpleNamespace(uid="alice")

            app = FastAPI()
            app.include_router(content, prefix="/api")
            app.dependency_overrides[get_db] = override_db
            app.dependency_overrides[get_required_user] = override_user
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/content/artifacts/artifact-1/distributions",
                    json={
                        "request_id": "cover-request-1",
                        "account_ids": ["account-1"],
                        "mode": mode,
                        "confirm_publish": mode == "publish",
                    },
                )

            assert response.status_code == expected_status, response.text
            jobs = (await db.execute(select(ContentDistributionJob))).scalars().all()
            if expected_status == 200:
                assert len(jobs) == 1
                assert jobs[0].payload_snapshot["cover"] == {
                    "type": "asset",
                    "asset_id": "cover-1",
                    "bucket_name": "covers",
                    "object_name": "alice/hycanvas.png",
                    "sha256": "a" * 64,
                }
                assert enqueued == [("process_xiaohongshu_distribution", jobs[0].id)]
                assert response.json()["job"]["id"] == jobs[0].id
                assert jobs[0].mode == mode
            else:
                assert response.json()["detail"]["error"]["code"] == "CONTENT_COVER_MISSING"
                assert jobs == []
                assert enqueued == []
    finally:
        await engine.dispose()
