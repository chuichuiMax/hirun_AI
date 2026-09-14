from types import SimpleNamespace

import pytest

import yuxi.services.inspire_samples as inspire_samples

from yuxi.services.inspire_samples import (
    _inspire_account_id,
    _metric_value,
    build_reference_blueprint,
    get_inspire_media_content,
    normalize_inspire_item,
)


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


def test_present_sample_uses_visible_platform_copy_when_snapshot_body_is_empty():
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
        body_expires_at=None,
        fetched_at=None,
        reference_ready=True,
        blueprint_version="v1",
    )

    presented = inspire_samples._present_sample(
        sample,
        snapshot,
        now=inspire_samples.utc_now_naive(),
        include_body=True,
    )

    assert presented["body"] == "平台卡片可见文案"


@pytest.mark.asyncio
async def test_inspire_media_is_downloaded_through_backend(monkeypatch: pytest.MonkeyPatch):
    media = SimpleNamespace(
        sample_id="sample-1",
        object_key="inspire-covers/owner/cover.jpg",
        mime_type="image/jpeg",
        expires_at=None,
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
