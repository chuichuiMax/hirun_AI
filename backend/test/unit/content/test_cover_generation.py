from __future__ import annotations

import base64
import io
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from PIL import Image
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from yuxi.content_cover.image2_client import Image2Client, Image2Config, Image2Error, image2_is_configured
from yuxi.content_cover.renderer import render_cover
from yuxi.content_cover.schemas import (
    CoverGenerateCreate,
    Image2Input,
    Image2Output,
    Image2Request,
    Image2Submission,
)
from yuxi.content_cover.templates import COVER_TEMPLATES
from yuxi.content.schemas import XiaohongshuDistributionCreate
from yuxi.repositories.content_cover_repository import ContentCoverRepository
from yuxi.services.content_cover_service import _normalize_upload
import yuxi.services.content_cover_worker as content_cover_worker
import yuxi.services.xiaohongshu_service as xiaohongshu_service
from yuxi.storage.postgres.models_content import ContentCoverJob


def _image(color: str, size: tuple[int, int] = (320, 240)) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", size, color).save(output, format="PNG")
    return output.getvalue()


def test_image2_configuration_rejects_invalid_status_path(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("IMAGE2_BASE_URL", "https://relay.example.com/v1")
    monkeypatch.setenv("IMAGE2_API_KEY", "test-key")
    monkeypatch.setenv("IMAGE2_MODEL", "image2-test")
    monkeypatch.setenv("IMAGE2_STATUS_PATH", "/images/generations/status")

    assert image2_is_configured() is False
    with pytest.raises(Image2Error) as exc_info:
        Image2Config.from_env()
    assert exc_info.value.code == "IMAGE2_CONFIG_INVALID"


@pytest.mark.parametrize(
    ("template_id", "count"),
    [
        ("grid_3x3", 9),
        ("split_vertical", 2),
        ("split_horizontal", 2),
        ("before_after", 2),
        ("card_stack", 4),
        ("hero_thumbs", 5),
    ],
)
def test_all_declared_cover_templates_render_expected_dimensions(template_id: str, count: int):
    colors = ["#D64343", "#3F65C6", "#49A86B", "#E1A737", "#8A55B5", "#37A7A7", "#B96D3C", "#67707A", "#D8689A"]

    result = render_cover(
        [_image(colors[index]) for index in range(count)],
        template_id=template_id,
        theme_id="editorial_ink",
        size="1080x1440",
        layout={"title": "测试封面", "gap": 20, "margin": 24},
    )

    with Image.open(io.BytesIO(result)) as rendered:
        assert rendered.format == "PNG"
        assert rendered.size == (1080, 1440)
    assert set(COVER_TEMPLATES) >= {template_id}


def test_multi_reference_accepts_two_sources_without_template():
    payload = CoverGenerateCreate(
        mode="multi_reference",
        source_asset_ids=["source-1", "source-2"],
        prompt="参考两张图片生成封面",
        idempotency_key="request-1234",
    )

    assert payload.template_asset_id is None


def test_mask_generation_requires_one_source_and_mask():
    with pytest.raises(ValidationError):
        CoverGenerateCreate(
            mode="mask",
            source_asset_ids=["source-1"],
            prompt="局部优化",
            idempotency_key="request-1234",
        )


@pytest.mark.parametrize(
    "payload",
    [
        {
            "mode": "text_to_image",
            "source_asset_ids": ["source-1"],
            "prompt": "生成封面",
        },
        {
            "mode": "image_to_image",
            "source_asset_ids": ["source-1"],
            "template_asset_id": "template-1",
            "prompt": "优化封面",
        },
        {
            "mode": "multi_reference",
            "source_asset_ids": ["source-1", "source-2"],
            "mask_asset_id": "mask-1",
            "prompt": "参考生成",
        },
        {
            "mode": "mask",
            "source_asset_ids": ["source-1"],
            "template_asset_id": "template-1",
            "mask_asset_id": "mask-1",
            "prompt": "局部优化",
        },
    ],
)
def test_generation_modes_reject_conflicting_inputs(payload):
    with pytest.raises(ValidationError):
        CoverGenerateCreate(**payload, idempotency_key="request-1234")


def test_mask_upload_preserves_alpha_channel():
    source = io.BytesIO()
    image = Image.new("RGBA", (16, 16), (255, 255, 255, 255))
    image.putpixel((0, 0), (0, 0, 0, 0))
    image.save(source, format="PNG")

    normalized, width, height, content_type = _normalize_upload(source.getvalue(), "mask")

    with Image.open(io.BytesIO(normalized)) as result:
        assert result.mode == "RGBA"
        assert result.getpixel((0, 0))[3] == 0
    assert (width, height, content_type) == (16, 16, "image/png")


def test_cover_upload_rejects_unsupported_decodable_format():
    source = io.BytesIO()
    Image.new("RGB", (16, 16), "white").save(source, format="GIF")

    with pytest.raises(HTTPException) as exc_info:
        _normalize_upload(source.getvalue(), "source")

    assert exc_info.value.detail["error"]["code"] == "COVER_IMAGE_FORMAT_UNSUPPORTED"


def test_worker_normalizes_model_result_to_requested_cover_size():
    normalized, width, height = content_cover_worker._normalize_output(
        _image("#52677A", (640, 480)),
        target_size=(1080, 1440),
    )

    with Image.open(io.BytesIO(normalized)) as result:
        assert result.size == (1080, 1440)
        assert result.format == "PNG"
    assert (width, height) == (1080, 1440)


def _client(handler, *, resolver=None) -> Image2Client:
    async def public_resolver(host: str, port: int) -> list[str]:
        assert host
        assert port in {80, 443}
        return ["93.184.216.34"]

    return Image2Client(
        Image2Config(
            base_url="https://relay.example.com/v1",
            api_key="test-key",
            model="image2-test",
        ),
        transport=httpx.MockTransport(handler),
        resolver=resolver or public_resolver,
    )


@pytest.mark.asyncio
async def test_image2_payload_contains_source_template_and_mask_data_urls():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        encoded = base64.b64encode(_image("#123456")).decode()
        return httpx.Response(200, json={"data": [{"b64_json": encoded}]})

    image = Image2Input(data=_image("#FFFFFF"), content_type="image/png", file_name="source.png")
    request = Image2Request(
        mode="multi_reference",
        prompt="生成小红书封面",
        size="1080x1440",
        source_images=[image],
        template_image=image,
        mask_image=image,
        extra={"strength": 0.7, "model": "must-not-override", "size": "1x1"},
    )
    async with _client(handler) as client:
        result = await client.submit(request)
        raw, content_type = await client.read_output(result.images[0])

    assert result.status == "completed"
    assert captured["model"] == "image2-test"
    assert captured["size"] == "1080x1440"
    assert [item["role"] for item in captured["images"]] == ["source", "template"]
    assert captured["mask"].startswith("data:image/png;base64,")
    assert captured["strength"] == 0.7
    assert content_type == "image/png"
    assert raw.startswith(b"\x89PNG")


@pytest.mark.asyncio
async def test_image2_async_submission_can_be_polled_to_completion():
    calls = []
    encoded = base64.b64encode(_image("#ABCDEF")).decode()

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "POST":
            return httpx.Response(202, json={"task_id": "upstream-1", "status": "queued"})
        return httpx.Response(
            200,
            json={"task_id": "upstream-1", "status": "succeeded", "data": [{"b64_json": encoded}]},
        )

    async with _client(handler) as client:
        submitted = await client.submit(
            Image2Request(mode="text_to_image", prompt="封面", size="1080x1440")
        )
        completed = await client.poll(submitted.provider_task_id)

    assert submitted.status == "pending"
    assert completed.status == "completed"
    assert len(completed.images) == 1
    assert calls == [
        ("POST", "/v1/images/generations"),
        ("GET", "/v1/images/generations/upstream-1"),
    ]


@pytest.mark.asyncio
async def test_image2_understands_nested_async_relay_response():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(202, json={"data": {"taskId": "nested-task", "state": "processing"}})

    async with _client(handler) as client:
        submitted = await client.submit(
            Image2Request(mode="text_to_image", prompt="封面", size="1080x1440")
        )

    assert submitted.provider_task_id == "nested-task"
    assert submitted.status == "pending"


@pytest.mark.asyncio
async def test_image2_understands_plain_base64_response():
    encoded = base64.b64encode(_image("#52677A")).decode()

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": encoded})

    async with _client(handler) as client:
        submitted = await client.submit(
            Image2Request(mode="text_to_image", prompt="封面", size="1080x1440")
        )
        raw, content_type = await client.read_output(submitted.images[0])

    assert submitted.status == "completed"
    assert raw.startswith(b"\x89PNG")
    assert content_type == "image/png"


@pytest.mark.asyncio
async def test_image2_rejects_private_result_url():
    async with _client(lambda _: httpx.Response(200, json={})) as client:
        with pytest.raises(Image2Error) as exc_info:
            await client.read_output(Image2Output(url="http://127.0.0.1/private.png"))

    assert exc_info.value.code == "IMAGE2_OUTPUT_URL_INVALID"


@pytest.mark.asyncio
async def test_image2_allows_admin_configured_relay_origin_for_result_download():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_image("#223344"), headers={"content-type": "image/png"})

    client = Image2Client(
        Image2Config(
            base_url="http://127.0.0.1:8080/v1",
            api_key="test-key",
            model="image2-test",
        ),
        transport=httpx.MockTransport(handler),
    )
    async with client:
        data, _ = await client.read_output(Image2Output(url="http://127.0.0.1:8080/files/result.png"))

    assert data.startswith(b"\x89PNG")


@pytest.mark.asyncio
async def test_image2_rejects_hostname_that_resolves_to_private_network():
    async def private_resolver(host: str, port: int) -> list[str]:
        assert (host, port) == ("cdn.example.com", 443)
        return ["10.0.0.8"]

    async with _client(
        lambda _: pytest.fail("private output URL must not be requested"),
        resolver=private_resolver,
    ) as client:
        with pytest.raises(Image2Error) as exc_info:
            await client.read_output(Image2Output(url="https://cdn.example.com/result.png"))

    assert exc_info.value.code == "IMAGE2_OUTPUT_URL_INVALID"


@pytest.mark.asyncio
async def test_image2_does_not_send_api_key_to_result_host():
    seen_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.update(request.headers)
        return httpx.Response(200, content=_image("#223344"), headers={"content-type": "image/png"})

    async with _client(handler) as client:
        data, content_type = await client.read_output(Image2Output(url="https://cdn.example.com/result.png"))

    assert "authorization" not in seen_headers
    assert seen_headers["accept"] == "image/*"
    assert content_type == "image/png"
    assert data.startswith(b"\x89PNG")


@pytest.mark.asyncio
async def test_image2_revalidates_redirect_target_before_following():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1/private.png"})

    async with _client(handler) as client:
        with pytest.raises(Image2Error) as exc_info:
            await client.read_output(Image2Output(url="https://cdn.example.com/result.png"))

    assert exc_info.value.code == "IMAGE2_OUTPUT_URL_INVALID"
    assert calls == ["https://cdn.example.com/result.png"]


@pytest.mark.asyncio
async def test_image2_retries_rate_limit_with_same_idempotency_key():
    calls = []
    encoded = base64.b64encode(_image("#887766")).decode()

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.headers.get("idempotency-key"))
        if len(calls) == 1:
            return httpx.Response(429, json={"message": "slow down"}, headers={"retry-after": "0"})
        return httpx.Response(200, json={"data": [{"b64_json": encoded}]})

    async with _client(handler) as client:
        result = await client.submit(
            Image2Request(mode="text_to_image", prompt="封面", size="1080x1440"),
            idempotency_key="cover-job-1",
        )

    assert result.status == "completed"
    assert calls == ["cover-job-1", "cover-job-1"]


@pytest.mark.asyncio
async def test_image2_post_500_is_retryable_but_not_automatically_resubmitted():
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500, json={"message": "upstream failed"})

    async with _client(handler) as client:
        with pytest.raises(Image2Error) as exc_info:
            await client.submit(Image2Request(mode="text_to_image", prompt="封面", size="1080x1440"))

    assert calls == 1
    assert exc_info.value.retryable is True


@pytest.mark.asyncio
async def test_image2_redacts_configuration_secrets_from_upstream_errors():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error": {"message": "test-key failed at https://relay.example.com/v1"}},
        )

    async with _client(handler) as client:
        with pytest.raises(Image2Error) as exc_info:
            await client.submit(Image2Request(mode="text_to_image", prompt="封面", size="1080x1440"))

    assert "test-key" not in str(exc_info.value)
    assert "relay.example.com" not in str(exc_info.value)
    assert "***" in str(exc_info.value)


@pytest.mark.asyncio
async def test_worker_resumes_existing_provider_task_without_resubmit(monkeypatch: pytest.MonkeyPatch):
    calls = {"submit": 0, "poll": 0}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            del exc_type, exc, traceback

        async def submit(self, request, *, idempotency_key=None):
            del request, idempotency_key
            calls["submit"] += 1
            raise AssertionError("existing provider task must not be resubmitted")

        async def poll(self, task_id):
            calls["poll"] += 1
            assert task_id == "provider-existing"
            return Image2Submission(
                provider_task_id=task_id,
                status="completed",
                images=[Image2Output(b64_data="done")],
            )

        async def read_output(self, output):
            assert output.b64_data == "done"
            return _image("#456789"), "image/png"

    async def no_event(*args, **kwargs):
        del args, kwargs

    async def no_assets(job):
        del job
        return [], None, None

    monkeypatch.setattr(content_cover_worker, "Image2Client", FakeClient)
    monkeypatch.setattr(content_cover_worker, "_load_job_assets", no_assets)
    monkeypatch.setattr(content_cover_worker, "_check_cancelled", no_event)
    monkeypatch.setattr(content_cover_worker, "_set_job", no_event)
    monkeypatch.setattr(content_cover_worker, "_emit", no_event)
    monkeypatch.setattr(content_cover_worker, "POLL_INTERVAL_SECONDS", 0)
    job = SimpleNamespace(
        id="ccj-resume",
        mode="text_to_image",
        provider_task_id="provider-existing",
        result_json={},
        request_json={"prompt": "封面", "size": "1080x1440", "n": 1},
    )

    outputs = await content_cover_worker._run_image2(job)

    assert len(outputs) == 1
    assert calls == {"submit": 0, "poll": 1}


@pytest.mark.asyncio
async def test_worker_generates_multiple_candidates_sequentially(monkeypatch: pytest.MonkeyPatch):
    submitted = []

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            del exc_type, exc, traceback

        async def submit(self, request, *, idempotency_key=None):
            submitted.append((request.n, idempotency_key))
            return Image2Submission(
                status="completed",
                images=[Image2Output(b64_data=f"result-{len(submitted)}")],
            )

        async def read_output(self, output):
            assert output.b64_data
            return _image("#456789"), "image/png"

    async def no_event(*args, **kwargs):
        del args, kwargs

    async def no_assets(job):
        del job
        return [], None, None

    monkeypatch.setattr(content_cover_worker, "Image2Client", FakeClient)
    monkeypatch.setattr(content_cover_worker, "_load_job_assets", no_assets)
    monkeypatch.setattr(content_cover_worker, "_check_cancelled", no_event)
    monkeypatch.setattr(content_cover_worker, "_set_job", no_event)
    monkeypatch.setattr(content_cover_worker, "_emit", no_event)
    job = SimpleNamespace(
        id="ccj-serial",
        mode="text_to_image",
        provider_task_id=None,
        result_json={},
        request_json={"prompt": "封面", "size": "1080x1440", "n": 3},
    )

    outputs = await content_cover_worker._run_image2(job)

    assert len(outputs) == 3
    assert submitted == [
        (1, "ccj-serial:0"),
        (1, "ccj-serial:1"),
        (1, "ccj-serial:2"),
    ]


@pytest.mark.asyncio
async def test_asset_reference_is_active_until_job_reaches_terminal_status():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(ContentCoverJob.__table__.create)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        job = await ContentCoverRepository(db).create_job(
            id="ccj-active-reference",
            owner_uid="alice",
            mode="image_to_image",
            status="running",
            idempotency_key="reference-test",
            request_json={"source_asset_ids": ["source-1"]},
            result_json={},
        )
        await db.commit()
        assert await ContentCoverRepository(db).asset_is_in_active_job("source-1", "alice") is True

        job.status = "succeeded"
        await db.commit()
        assert await ContentCoverRepository(db).asset_is_in_active_job("source-1", "alice") is False

    await engine.dispose()


@pytest.mark.asyncio
async def test_xiaohongshu_distribution_snapshot_locks_selected_cover(monkeypatch: pytest.MonkeyPatch):
    artifact = SimpleNamespace(
        id="artifact-1",
        created_by="alice",
        review_snapshot={"status": "passed"},
        title="封面测试",
        body="正文",
        topics=["内容创作"],
        current_version=2,
        cover_asset_id="cover-2",
    )
    account = SimpleNamespace(id="account-1", enabled=True, login_status="logged_in")
    cover = SimpleNamespace(
        id="cover-2",
        role="output",
        bucket_name="content-covers",
        object_name="content-covers/alice/cover-2.png",
        sha256="a" * 64,
    )
    captured = {}
    job = SimpleNamespace(
        id="distribution-1",
        status="queued",
        to_dict=lambda: {"id": "distribution-1", "status": "queued"},
    )

    class FakeContentRepo:
        async def get_artifact(self, artifact_id):
            assert artifact_id == artifact.id
            return artifact

    class FakeXhsRepo:
        async def get_accounts(self, account_ids, owner_uid):
            assert account_ids == [account.id]
            assert owner_uid == "alice"
            return [account]

        async def get_artifact_version(self, artifact_id, version):
            return SimpleNamespace(artifact_id=artifact_id, version=version)

        async def get_job_by_idempotency_key(self, request_key, owner_uid):
            del request_key, owner_uid
            return None

        async def create_distribution_job(self, **values):
            captured.update(values)
            return job

        async def list_distribution_results(self, job_id):
            assert job_id == job.id
            return []

    class FakeCoverRepo:
        async def get_asset_for_user(self, asset_id, owner_uid):
            assert (asset_id, owner_uid) == (cover.id, "alice")
            return cover

    class FakeQueue:
        async def enqueue_job(self, *args, **kwargs):
            del args, kwargs
            return object()

    class FakeDb:
        async def commit(self):
            return None

    async def fake_pool():
        return FakeQueue()

    monkeypatch.setattr(xiaohongshu_service, "ContentRepository", lambda db: FakeContentRepo())
    monkeypatch.setattr(xiaohongshu_service, "XiaohongshuRepository", lambda db: FakeXhsRepo())
    monkeypatch.setattr(xiaohongshu_service, "ContentCoverRepository", lambda db: FakeCoverRepo())
    monkeypatch.setattr(xiaohongshu_service, "get_arq_pool", fake_pool)

    response = await xiaohongshu_service.create_distribution(
        FakeDb(),
        SimpleNamespace(uid="alice"),
        artifact.id,
        XiaohongshuDistributionCreate(
            request_id="request-cover-snapshot",
            account_ids=[account.id],
            mode="draft",
        ),
    )

    assert response["deduplicated"] is False
    assert captured["payload_snapshot"]["cover"] == {
        "type": "asset",
        "asset_id": cover.id,
        "bucket_name": cover.bucket_name,
        "object_name": cover.object_name,
        "sha256": cover.sha256,
    }
