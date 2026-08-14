from __future__ import annotations

import hashlib
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from server.routers.content_router import content
from server.utils.auth_middleware import get_db, get_required_user
from yuxi.content.schemas import XiaohongshuDistributionCreate
from yuxi.integrations.xiaohongshu import XiaohongshuRuntime, XiaohongshuRuntimeError
from yuxi.repositories.xiaohongshu_repository import XiaohongshuRepository
import yuxi.services.xiaohongshu_service as xiaohongshu_service
import yuxi.services.xiaohongshu_worker as xiaohongshu_worker
from yuxi.services.run_worker import WorkerSettings
from yuxi.services.xiaohongshu_worker import process_xiaohongshu_distribution
from yuxi.storage.postgres.models_content import (
    ContentDistributionJob,
    ContentDistributionResult,
    XiaohongshuAccount,
    XiaohongshuLoginSession,
)
from yuxi.utils.datetime_utils import utc_now_naive


@pytest.mark.asyncio
async def test_account_repository_never_crosses_owner_boundary():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(XiaohongshuAccount.__table__.create)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        repo = XiaohongshuRepository(db)
        alice = await repo.create_account(owner_uid="alice", display_name="Alice 的账号")
        await repo.create_account(owner_uid="bob", display_name="Bob 的账号")
        await db.commit()

        assert [item.owner_uid for item in await repo.list_accounts("alice")] == ["alice"]
        assert await repo.get_account(alice.id, "bob") is None
        assert "owner_uid" not in alice.to_dict()

    await engine.dispose()


@pytest.mark.asyncio
async def test_xiaohongshu_account_api_is_user_private():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(XiaohongshuAccount.__table__.create)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    app = FastAPI()
    app.include_router(content, prefix="/api")
    current_uid = {"value": "alice"}
    async with session_factory() as db:
        async def override_db():
            yield db

        async def override_user():
            return SimpleNamespace(uid=current_uid["value"])

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_required_user] = override_user
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            alice_response = await client.post(
                "/api/content/xiaohongshu/accounts",
                json={"display_name": "主账号"},
            )
            assert alice_response.status_code == 200
            alice_id = alice_response.json()["account"]["id"]

            current_uid["value"] = "bob"
            bob_response = await client.post(
                "/api/content/xiaohongshu/accounts",
                json={"display_name": "主账号"},
            )
            assert bob_response.status_code == 200
            bob_items = (await client.get("/api/content/xiaohongshu/accounts")).json()["items"]
            assert [item["id"] for item in bob_items] == [bob_response.json()["account"]["id"]]
            assert all("owner_uid" not in item for item in bob_items)
            assert (
                await client.patch(
                    f"/api/content/xiaohongshu/accounts/{alice_id}",
                    json={"display_name": "越权修改"},
                )
            ).status_code == 404
            assert (await client.delete(f"/api/content/xiaohongshu/accounts/{alice_id}")).status_code == 404

            current_uid["value"] = "alice"
            alice_items = (await client.get("/api/content/xiaohongshu/accounts")).json()["items"]
            assert [item["id"] for item in alice_items] == [alice_id]

    await engine.dispose()


@pytest.mark.asyncio
async def test_expired_login_session_is_closed_even_if_worker_never_started():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(XiaohongshuAccount.__table__.create)
        await connection.run_sync(XiaohongshuLoginSession.__table__.create)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        repo = XiaohongshuRepository(db)
        account = await repo.create_account(owner_uid="alice", display_name="主账号")
        account.login_status = "pending"
        login_session = await repo.create_login_session(
            account=account,
            expires_at=utc_now_naive() - timedelta(seconds=1),
        )
        await db.commit()

        response = await xiaohongshu_service.get_login_session(
            db,
            SimpleNamespace(uid="alice"),
            login_session.id,
        )

        assert response["session"]["status"] == "expired"
        assert response["session"]["qr_code"] is None
        assert account.login_status == "expired"

    await engine.dispose()


def test_runtime_account_path_is_private_and_traversal_safe(tmp_path: Path):
    runtime = XiaohongshuRuntime(root=tmp_path)

    owner_namespace = hashlib.sha256(b"oidc:user@example.com").hexdigest()
    assert runtime.account_dir("oidc:user@example.com", "xha_1") == tmp_path / owner_namespace / "xha_1"
    with pytest.raises(XiaohongshuRuntimeError, match="运行目录标识无效"):
        runtime.account_dir("user_1", "../another-account")


def test_generated_cover_is_ready_for_image_note(tmp_path: Path):
    runtime = XiaohongshuRuntime(root=tmp_path)

    cover = runtime.render_cover("user_1", "xha_1", "job_1", "一键分发测试", ["效率", "内容创作"])

    assert cover.is_file()
    assert cover.suffix == ".png"
    assert cover.stat().st_size > 0


def test_distribution_schema_requires_explicit_publish_confirmation_and_request_key():
    with pytest.raises(ValidationError):
        XiaohongshuDistributionCreate(account_ids=["xha_1"], mode="publish", confirm_publish=True)

    payload = XiaohongshuDistributionCreate(
        request_id="request-123",
        account_ids=["xha_1"],
        mode="publish",
        confirm_publish=True,
    )
    assert payload.confirm_publish is True


def test_xiaohongshu_distribution_is_registered_on_existing_worker():
    assert process_xiaohongshu_distribution in WorkerSettings.functions


@pytest.mark.asyncio
async def test_distribution_rejects_artifact_owned_by_another_user(monkeypatch: pytest.MonkeyPatch):
    artifact = SimpleNamespace(id="artifact_1", created_by="bob")
    monkeypatch.setattr(
        xiaohongshu_service,
        "ContentRepository",
        lambda db: SimpleNamespace(get_artifact=lambda artifact_id: _async_value(artifact)),
    )
    payload = XiaohongshuDistributionCreate(
        request_id="request-123",
        account_ids=["xha_1"],
    )

    with pytest.raises(HTTPException) as exc_info:
        await xiaohongshu_service.create_distribution(object(), SimpleNamespace(uid="alice"), "artifact_1", payload)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_distribution_requires_completed_review(monkeypatch: pytest.MonkeyPatch):
    artifact = SimpleNamespace(id="artifact_1", created_by="alice", review_snapshot={"status": "pending"})
    monkeypatch.setattr(
        xiaohongshu_service,
        "ContentRepository",
        lambda db: SimpleNamespace(get_artifact=lambda artifact_id: _async_value(artifact)),
    )
    payload = XiaohongshuDistributionCreate(
        request_id="request-123",
        account_ids=["xha_1"],
    )

    with pytest.raises(HTTPException) as exc_info:
        await xiaohongshu_service.create_distribution(object(), SimpleNamespace(uid="alice"), "artifact_1", payload)

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_direct_publish_requires_service_level_confirmation(monkeypatch: pytest.MonkeyPatch):
    artifact = SimpleNamespace(id="artifact_1", created_by="alice", review_snapshot={"status": "passed"})
    monkeypatch.setattr(
        xiaohongshu_service,
        "ContentRepository",
        lambda db: SimpleNamespace(get_artifact=lambda artifact_id: _async_value(artifact)),
    )
    payload = XiaohongshuDistributionCreate(
        request_id="request-123",
        account_ids=["xha_1"],
        mode="publish",
        confirm_publish=False,
    )

    with pytest.raises(HTTPException) as exc_info:
        await xiaohongshu_service.create_distribution(object(), SimpleNamespace(uid="alice"), "artifact_1", payload)

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error"]["code"] == "XHS_PUBLISH_CONFIRM_REQUIRED"


@pytest.mark.asyncio
async def test_status_check_queue_failure_returns_retryable_api_error(monkeypatch: pytest.MonkeyPatch):
    account = SimpleNamespace(id="xha_1", owner_uid="alice", to_dict=lambda: {"id": "xha_1"})
    monkeypatch.setattr(
        xiaohongshu_service,
        "XiaohongshuRepository",
        lambda db: SimpleNamespace(get_account=lambda account_id, owner_uid: _async_value(account)),
    )

    async def unavailable_queue():
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr(xiaohongshu_service, "get_arq_pool", unavailable_queue)

    with pytest.raises(HTTPException) as exc_info:
        await xiaohongshu_service.check_account_login(object(), SimpleNamespace(uid="alice"), "xha_1")

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["error"] == {
        "code": "XHS_STATUS_QUEUE_UNAVAILABLE",
        "message": "账号状态检查暂时不可用，请稍后重试",
        "retryable": True,
    }


@pytest.mark.asyncio
async def test_interrupted_publish_is_not_automatically_retried(monkeypatch: pytest.MonkeyPatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(XiaohongshuAccount.__table__.create)
        await connection.run_sync(ContentDistributionJob.__table__.create)
        await connection.run_sync(ContentDistributionResult.__table__.create)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        repo = XiaohongshuRepository(db)
        account = await repo.create_account(owner_uid="alice", display_name="主账号")
        job = await repo.create_distribution_job(
            owner_uid="alice",
            artifact_id="artifact_1",
            artifact_version=1,
            mode="publish",
            payload_snapshot={"title": "标题", "body": "正文", "topics": []},
            idempotency_key="request-key",
            dedupe_key="dedupe-key",
            accounts=[account],
        )
        result = (await repo.list_distribution_results(job.id))[0]
        job.status = "running"
        result.status = "running"
        await db.commit()

        @asynccontextmanager
        async def session_context():
            yield db

        runtime_calls = []

        class FakeRuntime:
            async def distribute(self, *args, **kwargs):
                runtime_calls.append((args, kwargs))
                return {}

        monkeypatch.setattr(
            xiaohongshu_worker,
            "pg_manager",
            SimpleNamespace(get_async_session_context=session_context),
        )
        monkeypatch.setattr(xiaohongshu_worker, "XiaohongshuRuntime", FakeRuntime)

        await xiaohongshu_worker.process_xiaohongshu_distribution({}, job.id)

        assert runtime_calls == []
        assert result.status == "failed"
        assert result.error_code == "XHS_PREVIOUS_ATTEMPT_INTERRUPTED"
        assert "不会自动重发" in result.error_message
        assert job.status == "failed"

    await engine.dispose()


async def _async_value(value):
    return value
