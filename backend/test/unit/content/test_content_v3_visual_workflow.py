from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import yuxi.agents.toolkits.content.tools as content_tools
import yuxi.content.control.workflow.agent_node as agent_node_module
from yuxi.content.control.workflow.agent_node import AgentNodeHandler, AgentNodeResultMapper
from yuxi.content.control.workflow.external_wait import ExternalWaitNodeHandler
from yuxi.content.v3.workflow import WORKFLOW_V3_NODES
from yuxi.storage.postgres.models_content import ContentCoverAsset, ContentCoverJob, ContentNodeRun, ContentTask


def _visual_plan() -> dict:
    return {
        "size": {"width": 1080, "height": 1440},
        "safe_area": {"top": 80, "right": 80, "bottom": 80, "left": 80},
        "text": ["真实施工过程"],
        "source_asset_ids": ["source-1"],
        "mode": "generated",
        "risks": [],
        "artifact_version_id": "cav-1",
        "evidence_ids": ["ev-1"],
    }


@pytest.mark.unit
def test_visual_plan_mapper_adds_stable_hash_without_changing_agent_contract_fields():
    first = AgentNodeResultMapper.to_state("plan_visuals", _visual_plan(), {})["visual_plan"]
    second = AgentNodeResultMapper.to_state("plan_visuals", _visual_plan(), {})["visual_plan"]

    assert len(first["plan_hash"]) == 64
    assert first == second
    assert {key: value for key, value in first.items() if key != "plan_hash"} == _visual_plan()


@pytest.mark.asyncio
async def test_submit_cover_node_delegates_the_locked_visual_plan(monkeypatch):
    visual_plan = AgentNodeResultMapper.to_state("plan_visuals", _visual_plan(), {})["visual_plan"]
    captured = {}
    node_run = SimpleNamespace(id="node-run-1", node_id="submit_cover_job", attempt=1)
    task = SimpleNamespace(
        id="task-1",
        industry_pack_version_id="industry-v3",
        channel_profile_version_id="channel-v1",
        persona_profile_version_id=None,
        rule_version_id="rules-v3",
    )

    class FakeResult:
        def scalar_one_or_none(self):
            return SimpleNamespace(uid="user-1")

    class FakeDB:
        async def get(self, model, item_id):
            if model is ContentNodeRun and item_id == "node-run-1":
                return node_run
            if model is ContentTask and item_id == "task-1":
                return task
            return None

        async def execute(self, query):
            del query
            return FakeResult()

    class FakeDelegationService:
        def __init__(self, db):
            del db

        async def execute(self, request):
            captured["request"] = request
            return SimpleNamespace(
                output={
                    "cover_job_id": "job-1",
                    "plan_hash": visual_plan["plan_hash"],
                    "source_asset_ids": ["source-1"],
                },
                delegated_agent_run_id="child-run-1",
            )

    monkeypatch.setattr(agent_node_module, "AgentDelegationService", FakeDelegationService)
    node = next(item for item in WORKFLOW_V3_NODES if item["id"] == "submit_cover_job")
    result = await AgentNodeHandler().execute(
        db=FakeDB(),
        node=node,
        state={
            "task_id": "task-1",
            "uid": "user-1",
            "run_id": "parent-run",
            "content_brief": {},
            "match_decision_snapshot": {},
            "formula_selection_snapshot": {},
            "evidence_bundle": {"items": [], "bundle_hash": "evidence-hash"},
            "selected_title": {"text": "锁定标题"},
            "artifact_version": {"id": "artifact-v1"},
            "media_evidence_items": [{"id": "source-1"}],
            "visual_plan": visual_plan,
            "state_version": 7,
        },
        node_run_id="node-run-1",
    )

    assert captured["request"].input_payload["locked_values"]["visual_plan"] == visual_plan
    assert result["cover_job"]["cover_job_id"] == "job-1"


@pytest.mark.asyncio
async def test_external_wait_returns_only_succeeded_output_assets(monkeypatch):
    import yuxi.content.control.workflow.external_wait as wait_module

    async def ignore_event(*args, **kwargs):
        return None

    monkeypatch.setattr(wait_module, "append_run_stream_event", ignore_event)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(ContentCoverAsset.__table__.create)
        await connection.run_sync(ContentCoverJob.__table__.create)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        asset = ContentCoverAsset(
            id="cover-1",
            owner_uid="user-1",
            content_task_id="task-1",
            role="output",
            original_file_name="cover.png",
            content_type="image/png",
            file_size=10,
            image_width=1080,
            image_height=1440,
            sha256="a" * 64,
            bucket_name="covers",
            object_name="cover-1.png",
            metadata_json={"provider": "image2"},
        )
        job = ContentCoverJob(
            id="job-1",
            owner_uid="user-1",
            content_task_id="task-1",
            mode="text_to_image",
            status="succeeded",
            model="image2-model",
            idempotency_key="visual-workflow-job-1",
            request_json={},
            result_json={"asset_ids": ["cover-1"]},
            progress=100,
        )
        db.add_all([asset, job])
        await db.commit()

        result = await ExternalWaitNodeHandler().execute(
            db=db,
            node={
                "id": "wait_cover_job",
                "external_job_type": "content_cover",
                "timeout_seconds": 900,
            },
            state={
                "task_id": "task-1",
                "uid": "user-1",
                "run_id": "run-1",
                "state_version": 2,
                "cover_job": {"cover_job_id": "job-1"},
            },
        )

    await engine.dispose()
    assert result["cover_job"]["asset_ids"] == ["cover-1"]
    assert result["cover_job"]["provider"] == "image2-model"
    assert result["cover_assets"][0]["id"] == "cover-1"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["failed", "cancelled"])
async def test_external_wait_never_falls_back_from_failed_or_cancelled_cover(status: str, monkeypatch):
    job = SimpleNamespace(
        id="job-1",
        owner_uid="user-1",
        content_task_id="task-1",
        status=status,
        error_code="PROVIDER_FAILED",
        created_at=None,
    )

    class FakeRepo:
        def __init__(self, db):
            del db

        async def get_job(self, job_id):
            assert job_id == "job-1"
            return job

    import yuxi.content.control.workflow.external_wait as wait_module

    async def ignore_event(*args, **kwargs):
        return None

    monkeypatch.setattr(wait_module, "ContentCoverRepository", FakeRepo)
    monkeypatch.setattr(wait_module, "append_run_stream_event", ignore_event)
    with pytest.raises(RuntimeError, match=status):
        await ExternalWaitNodeHandler().execute(
            db=object(),
            node={
                "id": "wait_cover_job",
                "external_job_type": "content_cover",
                "timeout_seconds": 900,
            },
            state={
                "task_id": "task-1",
                "uid": "user-1",
                "run_id": "run-1",
                "cover_job": {"cover_job_id": "job-1"},
            },
        )


@pytest.mark.asyncio
async def test_cover_tool_uses_locked_plan_and_persists_event_resume_metadata(monkeypatch):
    captured = []
    events = []
    visual_plan = {**_visual_plan(), "plan_hash": "a" * 64}
    node_input = SimpleNamespace(
        task_id="task-1",
        parent_run_id="run-parent",
        locked_values={
            "state_version": 7,
            "visual_plan_hash": "a" * 64,
            "visual_plan": visual_plan,
        },
    )
    context = SimpleNamespace(
        uid="user-1",
        run_id="child-run",
        thread_id="content:task-1:submit_cover_job:1",
        _content_node_output_contract="CoverJobSubmissionResultV1",
        _content_node_result_collector=SimpleNamespace(
            domain_context=SimpleNamespace(
                visual_plan_hash="a" * 64,
                allowed_asset_ids=frozenset({"source-1"}),
            )
        ),
        _content_node_input=node_input,
    )

    class FakeResult:
        def scalar_one_or_none(self):
            return SimpleNamespace(uid="user-1")

    class FakeDB:
        async def execute(self, query):
            del query
            return FakeResult()

    @asynccontextmanager
    async def fake_session():
        yield FakeDB()

    async def fake_create(db, user, payload):
        del db, user
        captured.append(payload)
        return {
            "job": {"id": "job-1", "mode": payload.mode},
            "deduplicated": len(captured) > 1,
        }

    async def fake_event(runtime, event_type, payload):
        del runtime
        events.append((event_type, payload))

    monkeypatch.setattr(content_tools.pg_manager, "get_async_session_context", fake_session)
    monkeypatch.setattr(content_tools, "create_cover_generate_job", fake_create)
    monkeypatch.setattr(content_tools, "_emit_content_tool_event", fake_event)

    kwargs = {
        "task_id": "task-1",
        "runtime": SimpleNamespace(context=context),
    }
    first = await content_tools.create_content_cover_job.coroutine(**kwargs)
    await content_tools.create_content_cover_job.coroutine(**kwargs)

    assert first == {
        "cover_job_id": "job-1",
        "plan_hash": "a" * 64,
        "source_asset_ids": ["source-1"],
    }
    assert captured[0].idempotency_key == captured[1].idempotency_key
    assert captured[0].size == "1080x1440"
    assert captured[0].title == "真实施工过程"
    assert captured[0].source_asset_ids == ["source-1"]
    assert captured[0].parameters["workflow_resume"] == {
        "parent_run_id": "run-parent",
        "node_id": "wait_cover_job",
        "expected_state_version": 7,
    }
    assert [event[0] for event in events[:3]] == [
        "content.tool.called",
        "content.cover.started",
        "content.tool.completed",
    ]


@pytest.mark.asyncio
async def test_cover_tool_rejects_assets_outside_locked_visual_plan():
    node_input = SimpleNamespace(
        task_id="task-1",
        parent_run_id="run-parent",
        locked_values={
            "state_version": 7,
            "visual_plan_hash": "a" * 64,
            "visual_plan": {
                **_visual_plan(),
                "plan_hash": "a" * 64,
                "source_asset_ids": ["other-source"],
            },
        },
    )
    context = SimpleNamespace(
        uid="user-1",
        _content_node_output_contract="CoverJobSubmissionResultV1",
        _content_node_result_collector=SimpleNamespace(
            domain_context=SimpleNamespace(
                visual_plan_hash="a" * 64,
                allowed_asset_ids=frozenset({"source-1"}),
            )
        ),
        _content_node_input=node_input,
    )

    with pytest.raises(ValueError, match="未授权素材"):
        await content_tools.create_content_cover_job.coroutine(
            task_id="task-1",
            runtime=SimpleNamespace(context=context),
        )


def test_cover_tool_only_accepts_task_id_from_agent():
    assert set(content_tools.CreateContentCoverJobInput.model_fields) == {"task_id"}
