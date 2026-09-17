from __future__ import annotations

import asyncio
import json
from time import monotonic
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from server import xhs_browser_gateway
from yuxi.integrations.xiaohongshu.runtime import (
    XiaohongshuRuntime,
    XiaohongshuRuntimeError,
    parse_inspire_note_detail,
)
from yuxi.integrations.xiaohongshu.session_manager import (
    BrowserSessionCapacityError,
    XiaohongshuBrowserSessionManager,
)


class FakeMouse:
    def __init__(self):
        self.clicks = []
        self.wheels = []

    async def click(self, x, y):
        self.clicks.append((x, y))

    async def wheel(self, x, y):
        self.wheels.append((x, y))


class FakeKeyboard:
    def __init__(self):
        self.inserted = []
        self.pressed = []

    async def insert_text(self, text):
        self.inserted.append(text)

    async def press(self, key):
        self.pressed.append(key)


class FakePage:
    def __init__(self):
        self.url = "https://creator.xiaohongshu.com/new/home"
        self.mouse = FakeMouse()
        self.keyboard = FakeKeyboard()

    async def goto(self, url, **kwargs):
        del kwargs
        self.url = url

    async def wait_for_timeout(self, milliseconds):
        del milliseconds

    async def screenshot(self, **kwargs):
        del kwargs
        return b"png"


class FakeContext:
    def __init__(self, page):
        self.pages = [page]
        self.closed = False

    async def close(self):
        self.closed = True


class FakePlaywright:
    def __init__(self):
        self.stopped = False

    async def stop(self):
        self.stopped = True


class FakeRuntime:
    def __init__(self):
        self.page = FakePage()
        self.context = FakeContext(self.page)
        self.drafts_opened = 0
        self.inspire_collections = []

    async def _launch_context(self, playwright, owner_uid, account_id):
        del playwright, owner_uid, account_id
        return self.context

    async def _is_logged_in(self, page):
        del page
        return True

    async def _profile(self, page):
        del page
        return {"nickname": "测试账号", "account_id": "platform-1"}

    async def _is_inspire_logged_in(self, page):
        return page.url.startswith("https://ad.xiaohongshu.com/")

    async def collect_inspire_cards(self, page, *, industry, limit):
        self.inspire_collections.append((page, industry, limit))
        return [{"note_id": "note-1", "title": "装修样本", "metrics": {"likes": "1w"}}]

    async def open_drafts(self, page):
        self.drafts_opened += 1
        page.url = "https://creator.xiaohongshu.com/publish/drafts"


class IsolatedFakeRuntime(FakeRuntime):
    def __init__(self):
        self.contexts = {}
        self.all_contexts = []

    async def _launch_context(self, playwright, owner_uid, account_id):
        del playwright
        page = FakePage()
        context = FakeContext(page)
        self.contexts[(owner_uid, account_id)] = context
        self.all_contexts.append(context)
        return context


def test_inspire_detail_parser_reads_exact_ssr_note_and_preserves_string_tokens():
    html = """<script>window.__INITIAL_STATE__={
        "note":{"noteDetailMap":{"note-1":{"note":{
            "title":"完整标题",
            "desc":"第一段\\n字符串里的 undefined 保持原样",
            "tagList":[{"name":"家居美学"},{"name":"入住新家"}],
            "optional":undefined,
            "score":NaN
        }}}},"unrelated":Infinity}</script>"""

    detail = parse_inspire_note_detail(html, "note-1")

    assert detail["title"] == "完整标题"
    assert detail["desc"] == "第一段\n字符串里的 undefined 保持原样"
    assert [item["name"] for item in detail["tagList"]] == ["家居美学", "入住新家"]
    assert detail["optional"] is None
    assert detail["score"] is None


def test_inspire_detail_parser_rejects_missing_note_state():
    with pytest.raises(XiaohongshuRuntimeError, match="结构已变化"):
        parse_inspire_note_detail("<script>window.__INITIAL_STATE__={}</script>", "note-1")


@pytest.mark.asyncio
async def test_inspire_collection_combines_list_fields_with_signed_detail_ssr():
    note_id = "note-1"
    detail_url = f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token=signed"
    detail_state = {
        "note": {
            "noteDetailMap": {
                note_id: {
                    "note": {
                        "title": "110 平彩色小家",
                        "desc": "第一段\n\n第二段\n\n#家居美学[话题]#",
                        "tagList": [
                            {"name": "家居美学"},
                            {"name": "入住新家"},
                            {"name": "家居美学"},
                        ],
                    }
                }
            }
        }
    }
    detail_html = f"<script>window.__INITIAL_STATE__={json.dumps(detail_state, ensure_ascii=False)}</script>"

    class FakeLocator:
        @property
        def last(self):
            return self

        async def click(self):
            return None

        async def wait_for(self, **kwargs):
            del kwargs

    class FakeSearchResponse:
        url = "https://edith.xiaohongshu.com/api/pgy_leona/content_square/search_note_v2"
        status = 200
        request = SimpleNamespace(post_data_json={"spuIndustry": "家居家装"})

        async def json(self):
            return {
                "data": {
                    "noteList": [
                        {
                            "noteInfo": {
                                "noteId": "video-1",
                                "noteType": 2,
                                "title": "视频样本",
                                "noteLink": "https://www.xiaohongshu.com/explore/video-1?xsec_token=signed",
                                "noteImages": [{"imageUrl": "http://ci.xiaohongshu.com/video.jpg"}],
                            }
                        },
                        {
                            "noteInfo": {
                                "noteId": note_id,
                                "noteType": 1,
                                "title": "110 平彩色小家",
                                "noteLink": detail_url,
                                "noteImages": [{"imageUrl": "http://ci.xiaohongshu.com/cover.jpg"}],
                                "likeNum": 321,
                                "favNum": 257,
                                "cmtNum": 24,
                            }
                        },
                    ]
                }
            }

    class FakeExpectedResponse:
        def __init__(self, predicate):
            response = FakeSearchResponse()
            assert predicate(response)
            self.value = asyncio.get_running_loop().create_future()
            self.value.set_result(response)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            del exc_type, exc, traceback

    class FakeDetailResponse:
        status = 200

        async def text(self):
            return detail_html

    class FakeRequest:
        async def get(self, url, **kwargs):
            assert url == detail_url
            assert kwargs["headers"] == {"referer": "https://ad.xiaohongshu.com/microapp/creativity/inspire"}
            return FakeDetailResponse()

    class FakeInspirePage:
        context = SimpleNamespace(request=FakeRequest())

        def get_by_text(self, text, **kwargs):
            del text, kwargs
            return FakeLocator()

        def expect_response(self, predicate, **kwargs):
            assert kwargs == {"timeout": 15000}
            return FakeExpectedResponse(predicate)

    runtime = XiaohongshuRuntime()
    runtime._is_inspire_logged_in = AsyncMock(return_value=True)

    items = await runtime.collect_inspire_cards(FakeInspirePage(), industry="家居家装", limit=10)

    assert items == [
        {
            "note_id": note_id,
            "title": "110 平彩色小家",
            "body": "第一段\n\n第二段\n\n#家居美学[话题]#",
            "tags": ["家居美学", "入住新家"],
            "cover_url": "https://ci.xiaohongshu.com/cover.jpg",
            "metrics": {"likes": "321", "collects": "257", "comments": "24"},
        }
    ]


@pytest.mark.asyncio
async def test_action_returns_status_without_reentrant_lock_deadlock():
    runtime = FakeRuntime()
    manager = XiaohongshuBrowserSessionManager(runtime=runtime)
    manager._playwright = FakePlaywright()

    opened = await asyncio.wait_for(manager.open("session-1", "owner-1", "account-1"), timeout=1)
    assert opened["status"] == "ready"

    acted = await asyncio.wait_for(
        manager.action(
            session_id="session-1",
            owner_uid="owner-1",
            account_id="account-1",
            payload={"action": "click", "x": 10, "y": 20},
        ),
        timeout=1,
    )
    assert acted["logged_in"] is True
    assert runtime.page.mouse.clicks == [(10.0, 20.0)]

    await manager.close_all()
    assert runtime.context.closed is True


@pytest.mark.asyncio
async def test_drafts_target_opens_once_and_is_reported_in_status():
    runtime = FakeRuntime()
    manager = XiaohongshuBrowserSessionManager(runtime=runtime)
    manager._playwright = FakePlaywright()

    opened = await manager.open(
        "session-1",
        "owner-1",
        "account-1",
        target="drafts",
    )
    reopened = await manager.open(
        "session-1",
        "owner-1",
        "account-1",
        target="drafts",
    )

    assert opened["view"] == "drafts"
    assert reopened["view"] == "drafts"
    assert runtime.drafts_opened == 1
    await manager.close_all()


@pytest.mark.asyncio
async def test_inspire_target_opens_authorized_content_square():
    runtime = FakeRuntime()
    manager = XiaohongshuBrowserSessionManager(runtime=runtime)
    manager._playwright = FakePlaywright()

    opened = await manager.open(
        "session-1",
        "owner-1",
        "inspire-account",
        target="inspire",
    )

    assert runtime.page.url == "https://ad.xiaohongshu.com/microapp/creativity/inspire"
    assert opened["logged_in"] is True
    assert opened["view"] == "inspire"
    await manager.close_all()


@pytest.mark.asyncio
async def test_inspire_collection_reuses_the_authenticated_gateway_page():
    runtime = FakeRuntime()
    manager = XiaohongshuBrowserSessionManager(runtime=runtime)
    manager._playwright = FakePlaywright()
    await manager.open("session-1", "owner-1", "inspire-account", target="inspire")

    items = await manager.collect_inspire(
        session_id="session-1",
        owner_uid="owner-1",
        account_id="inspire-account",
        industry="家居家装",
        limit=10,
    )

    assert items == [{"note_id": "note-1", "title": "装修样本", "metrics": {"likes": "1w"}}]
    assert runtime.inspire_collections == [(runtime.page, "家居家装", 10)]
    assert runtime.context.closed is False
    await manager.close_all()


@pytest.mark.asyncio
async def test_direct_takeover_keyboard_and_wheel_actions_are_bounded():
    runtime = FakeRuntime()
    manager = XiaohongshuBrowserSessionManager(runtime=runtime)
    manager._playwright = FakePlaywright()
    await manager.open("session-1", "owner-1", "account-1")

    for payload in (
        {"action": "type", "text": "直接输入中文"},
        {"action": "keypress", "key": "Control+A"},
        {"action": "keypress", "key": "Delete"},
        {"action": "scroll", "delta_y": 5000},
    ):
        await manager.action(
            session_id="session-1",
            owner_uid="owner-1",
            account_id="account-1",
            payload=payload,
        )

    assert runtime.page.keyboard.inserted == ["直接输入中文"]
    assert runtime.page.keyboard.pressed == ["Control+A", "Delete"]
    assert runtime.page.mouse.wheels == [(0, 2000)]
    await manager.close_all()


@pytest.mark.asyncio
async def test_idle_sessions_are_closed_and_removed():
    runtime = FakeRuntime()
    manager = XiaohongshuBrowserSessionManager(runtime=runtime)
    manager._playwright = FakePlaywright()
    await manager.open("session-1", "owner-1", "account-1")
    session = await manager.get("session-1", "owner-1", "account-1")
    session.last_used_at = 0

    assert await manager.reap_idle(60) == ["session-1"]
    assert manager.active_session_count == 0
    assert runtime.context.closed is True


@pytest.mark.asyncio
async def test_idle_reaper_does_not_close_a_session_that_became_active():
    runtime = FakeRuntime()
    manager = XiaohongshuBrowserSessionManager(runtime=runtime)
    manager._playwright = FakePlaywright()
    await manager.open("session-1", "owner-1", "account-1")
    session = await manager.get("session-1", "owner-1", "account-1")
    session.last_used_at = 0
    await session.lock.acquire()

    reap_task = asyncio.create_task(manager.reap_idle(60))
    await asyncio.sleep(0)
    session.last_used_at = monotonic()
    session.lock.release()

    assert await reap_task == []
    assert manager.active_session_count == 1
    assert runtime.context.closed is False
    await manager.close_all()


@pytest.mark.asyncio
async def test_click_rejects_missing_or_out_of_range_coordinates():
    runtime = FakeRuntime()
    manager = XiaohongshuBrowserSessionManager(runtime=runtime)
    manager._playwright = FakePlaywright()
    await manager.open("session-1", "owner-1", "account-1")

    with pytest.raises(ValueError, match="缺少坐标"):
        await manager.action(
            session_id="session-1",
            owner_uid="owner-1",
            account_id="account-1",
            payload={"action": "click"},
        )
    with pytest.raises(ValueError, match="超出允许范围"):
        await manager.action(
            session_id="session-1",
            owner_uid="owner-1",
            account_id="account-1",
            payload={"action": "click", "x": -1, "y": 20},
        )

    await manager.close_all()


@pytest.mark.asyncio
async def test_concurrent_accounts_keep_sessions_and_pages_isolated():
    runtime = IsolatedFakeRuntime()
    manager = XiaohongshuBrowserSessionManager(runtime=runtime, max_sessions=10)
    manager._playwright = FakePlaywright()

    opened = await asyncio.gather(
        *(manager.open(f"session-{index}", "owner-1", f"account-{index}") for index in range(10))
    )

    assert manager.active_session_count == 10
    assert {item["session_id"] for item in opened} == {f"session-{index}" for index in range(10)}
    assert len({id(context) for context in runtime.contexts.values()}) == 10
    assert len({id(context.pages[0]) for context in runtime.contexts.values()}) == 10

    with pytest.raises(KeyError, match="browser session not found"):
        await manager.status(
            session_id="session-0",
            owner_uid="owner-1",
            account_id="account-1",
        )

    await manager.close_all()
    assert all(context.closed for context in runtime.contexts.values())


@pytest.mark.asyncio
async def test_session_capacity_is_enforced_under_concurrent_opens():
    runtime = IsolatedFakeRuntime()
    manager = XiaohongshuBrowserSessionManager(runtime=runtime, max_sessions=2)
    manager._playwright = FakePlaywright()

    results = await asyncio.gather(
        *(manager.open(f"session-{index}", "owner-1", f"account-{index}") for index in range(3)),
        return_exceptions=True,
    )

    assert manager.active_session_count == 2
    assert sum(isinstance(item, BrowserSessionCapacityError) for item in results) == 1
    await manager.close_all()


@pytest.mark.asyncio
async def test_new_authoritative_session_id_replaces_stale_account_context():
    runtime = IsolatedFakeRuntime()
    manager = XiaohongshuBrowserSessionManager(runtime=runtime, max_sessions=1)
    manager._playwright = FakePlaywright()

    await manager.open("session-old", "owner-1", "account-1")
    old_context = runtime.all_contexts[0]
    replaced = await manager.open("session-new", "owner-1", "account-1")

    assert replaced["session_id"] == "session-new"
    assert old_context.closed is True
    assert manager.active_session_count == 1
    await manager.close_all()


@pytest.mark.asyncio
async def test_stale_close_cannot_remove_a_replacement_session():
    runtime = IsolatedFakeRuntime()
    manager = XiaohongshuBrowserSessionManager(runtime=runtime, max_sessions=1)
    manager._playwright = FakePlaywright()
    await manager.open("session-old", "owner-1", "account-1")
    account_lock = await manager._account_lock("owner-1", "account-1")
    await account_lock.acquire()

    open_task = asyncio.create_task(manager.open("session-new", "owner-1", "account-1"))
    await asyncio.sleep(0)
    stale_close_task = asyncio.create_task(
        manager.close(session_id="session-old", owner_uid="owner-1", account_id="account-1")
    )
    await asyncio.sleep(0)
    account_lock.release()

    opened = await open_task
    with pytest.raises(KeyError, match="browser session not found"):
        await stale_close_task
    status = await manager.status(
        session_id="session-new",
        owner_uid="owner-1",
        account_id="account-1",
    )
    assert opened["session_id"] == "session-new"
    assert status["session_id"] == "session-new"
    assert manager.active_session_count == 1
    await manager.close_all()


@pytest.mark.asyncio
async def test_gateway_capacity_returns_retryable_http_status(monkeypatch: pytest.MonkeyPatch):
    async def capacity_reached(*args, **kwargs):
        del args, kwargs
        raise BrowserSessionCapacityError("capacity reached")

    monkeypatch.setattr(xhs_browser_gateway.manager, "open", capacity_reached)
    request = xhs_browser_gateway.SessionRequest(
        session_id="session-123",
        owner_uid="owner-1",
        account_id="account-1",
    )

    with pytest.raises(HTTPException) as exc_info:
        await xhs_browser_gateway.open_session(request)

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["code"] == "XHS_GATEWAY_CAPACITY_REACHED"


@pytest.mark.asyncio
async def test_gateway_forwards_restricted_drafts_target(monkeypatch: pytest.MonkeyPatch):
    captured = {}

    async def open_drafts(session_id, owner_uid, account_id, *, target):
        captured.update(
            session_id=session_id,
            owner_uid=owner_uid,
            account_id=account_id,
            target=target,
        )
        return {"status": "ready", "view": target}

    monkeypatch.setattr(xhs_browser_gateway.manager, "open", open_drafts)
    request = xhs_browser_gateway.SessionRequest(
        session_id="session-123",
        owner_uid="owner-1",
        account_id="account-1",
        target="drafts",
    )

    response = await xhs_browser_gateway.open_session(request)

    assert response == {"status": "ready", "view": "drafts"}
    assert captured == {
        "session_id": "session-123",
        "owner_uid": "owner-1",
        "account_id": "account-1",
        "target": "drafts",
    }


@pytest.mark.asyncio
async def test_gateway_collects_inspire_cards_from_existing_session(monkeypatch: pytest.MonkeyPatch):
    captured = {}

    async def collect_inspire(**kwargs):
        captured.update(kwargs)
        return [{"note_id": "note-1", "title": "装修样本"}]

    monkeypatch.setattr(xhs_browser_gateway.manager, "collect_inspire", collect_inspire)
    request = xhs_browser_gateway.InspireCollectRequest(
        session_id="session-123",
        owner_uid="owner-1",
        account_id="inspire-account",
        industry="家居家装",
        limit=10,
    )

    response = await xhs_browser_gateway.session_collect_inspire("session-123", request)

    assert response == {"items": [{"note_id": "note-1", "title": "装修样本"}]}
    assert captured == {
        "session_id": "session-123",
        "owner_uid": "owner-1",
        "account_id": "inspire-account",
        "industry": "家居家装",
        "limit": 10,
    }
