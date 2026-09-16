from datetime import timedelta
from types import SimpleNamespace

import pytest

import yuxi.services.inspire_samples as inspire_samples

from yuxi.services.inspire_samples import (
    InspireDirectCrawler,
    _inspire_account_id,
    _metric_value,
    build_reference_blueprint,
    get_inspire_media_content,
    normalize_inspire_item,
)


@pytest.mark.asyncio
async def test_inspire_crawler_uses_gateway_session_and_normalizes_cards(monkeypatch: pytest.MonkeyPatch):
    captured = {}

    class FakeResponse:
        @staticmethod
        def json():
            return {
                "items": [
                    {
                        "note_id": "note-1",
                        "title": "装修避坑清单",
                        "body": "装修避坑清单\n#装修避坑[话题]# #全屋定制[话题]#",
                        "tags": ["装修避坑", "全屋定制"],
                        "cover_url": "https://ci.xiaohongshu.com/cover.jpg",
                        "metrics": {"likes": "1w", "collects": "397"},
                    }
                ]
            }

    async def gateway_request(method, path, **kwargs):
        captured.update(method=method, path=path, **kwargs)
        return FakeResponse()

    monkeypatch.setattr(inspire_samples, "_gateway_request", gateway_request)

    items = await InspireDirectCrawler().collect(
        owner_uid="owner-1",
        account_id="account-1",
        session_id="session-1",
        industry_slug="decoration",
        limit=10,
    )

    assert captured["path"] == "/internal/sessions/session-1/inspire/collect"
    assert captured["json"]["industry"] == "家居家装"
    assert items[0]["title"] == "装修避坑清单"
    assert items[0]["body"] == "装修避坑清单\n#装修避坑[话题]# #全屋定制[话题]#"
    assert items[0]["tags"] == ["装修避坑", "全屋定制"]
    assert items[0]["metrics"] == {"likes": 10_000, "collects": 397}


def test_normalize_inspire_item_keeps_structure_separate_from_body():
    item = normalize_inspire_item(
        {
            "id": "note-1",
            "url": "https://ad.xiaohongshu.com/microapp/creativity/inspire/note-1",
            "title": "装修避坑清单",
            "content": "先看预算\n1. 明确需求\n2. 对照报价",
            "tags": ["装修", "避坑"],
            "metrics": {"likes": 123, "secret": "drop"},
        },
        "decoration",
        1,
    )
    assert item["note_id"] == "note-1"
    assert item["metrics"] == {"likes": 123}
    assert item["reference_blueprint"]["content_block_sequence"]
    assert item["body"]


def test_normalize_inspire_item_rejects_external_url():
    with pytest.raises(ValueError, match="允许域名"):
        normalize_inspire_item(
            {"url": "https://example.com/note", "title": "标题", "body": "正文"},
            "food",
            1,
        )


def test_blueprint_is_abstract_and_stable_for_empty_body():
    blueprint = build_reference_blueprint("标题", "")
    assert "quote" not in str(blueprint)
    assert blueprint["title_slot_sequence"]


def test_source_hash_does_not_change_when_rank_changes():
    payload = {
        "url": "https://ad.xiaohongshu.com/microapp/creativity/inspire/note-1",
        "title": "同一篇样本",
        "body": "正文",
        "tags": ["标签"],
    }
    first = normalize_inspire_item(payload, "food", 1)
    second = normalize_inspire_item(payload, "food", 2)
    assert first["source_hash"] == second["source_hash"]


def test_platform_metric_units_are_normalized():
    assert _metric_value("1w") == 10_000
    assert _metric_value("2.5k") == 2_500
    assert _metric_value("397") == 397
    assert _metric_value("0:49") is None


def test_inspire_browser_account_is_stable_and_hidden_by_prefix():
    account_id = _inspire_account_id("owner-1")
    assert account_id.startswith("xhsi_")
    assert account_id == _inspire_account_id("owner-1")
    assert account_id != _inspire_account_id("owner-2")


def test_present_sample_does_not_disguise_missing_body_as_title():
    now = inspire_samples.utc_now_naive()
    sample = SimpleNamespace(
        id="sample-1",
        industry_slug="decoration",
        title="平台卡片可见文案",
        tags_json=[],
        author_name=None,
        metrics_json={},
        current_rank=1,
        canonical_url="https://ad.xiaohongshu.com/microapp/creativity/inspire#note-1",
        source_hash="hash",
    )
    snapshot = SimpleNamespace(
        id="snapshot-1",
        body_text=None,
        body_expires_at=now - timedelta(hours=1),
        fetched_at=None,
        reference_ready=True,
        blueprint_version="v1",
    )

    presented = inspire_samples._present_sample(
        sample,
        snapshot,
    )

    assert presented["body"] == ""
    assert presented["body_expired"] is False


@pytest.mark.asyncio
async def test_inspire_crawler_rejects_incomplete_gateway_item(monkeypatch: pytest.MonkeyPatch):
    class FakeResponse:
        @staticmethod
        def json():
            return {
                "items": [
                    {
                        "note_id": "note-1",
                        "title": "装修避坑清单",
                        "body": "正文完整，但平台没有返回话题标签。",
                        "tags": [],
                        "cover_url": "https://ci.xiaohongshu.com/cover.jpg",
                        "metrics": {},
                    }
                ]
            }

    async def gateway_request(*args, **kwargs):
        del args, kwargs
        return FakeResponse()

    monkeypatch.setattr(inspire_samples, "_gateway_request", gateway_request)

    with pytest.raises(inspire_samples.XiaohongshuRuntimeError) as exc_info:
        await InspireDirectCrawler().collect(
            owner_uid="owner-1",
            account_id="account-1",
            session_id="session-1",
            industry_slug="decoration",
            limit=10,
        )

    assert exc_info.value.code == "INSPIRE_ITEM_INCOMPLETE"


@pytest.mark.asyncio
async def test_inspire_media_is_downloaded_through_backend(monkeypatch: pytest.MonkeyPatch):
    media = SimpleNamespace(
        sample_id="sample-1",
        object_key="inspire-covers/owner/cover.jpg",
        mime_type="image/jpeg",
        expires_at=inspire_samples.utc_now_naive() - timedelta(hours=1),
    )
    sample = SimpleNamespace(owner_uid="owner-1")

    class FakeDb:
        async def get(self, model, row_id):
            del model
            return media if row_id == "media-1" else sample

    class FakeMinio:
        async def adownload_file(self, bucket_name, object_name):
            assert (bucket_name, object_name) == ("public", media.object_key)
            return b"image-bytes"

    monkeypatch.setattr(inspire_samples, "get_minio_client", lambda: FakeMinio())

    data, media_type = await get_inspire_media_content(
        FakeDb(),
        SimpleNamespace(uid="owner-1"),
        "media-1",
    )

    assert data == b"image-bytes"
    assert media_type == "image/jpeg"
