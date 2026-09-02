from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import yuxi.agents.buildin.content_workflow.graph as content_workflow_graph_module
import yuxi.agents.toolkits.content.tools as content_tools
import yuxi.content.control.workflow.agent_node as agent_node_module
from yuxi.agents.buildin.content_workflow.graph import ContentWorkflowAgent
from yuxi.content.control.workflow.agent_node import AgentNodeHandler, AgentNodeResultMapper
from yuxi.content.control.workflow.deterministic_node import V3DeterministicNodeHandler
from yuxi.content.control.workflow.external_wait import (
    COVER_SKIP_REASON,
    RESEARCH_SKIP_REASON,
    ExternalWaitNodeHandler,
    skip_content_correction_interrupt,
    skip_cover_pipeline,
    skip_formula_lexicon_pipeline,
)
from yuxi.repositories.content_cover_repository import ContentCoverRepository
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
    node = {
        "id": "submit_cover_job",
        "type": "agent",
        "agent_slug": "content-visual-agent",
        "required_skills": ["content-cover-generator"],
        "input_contract": "SubmitCoverJobInputV1",
        "state_inputs": ["visual_plan", "artifact_version", "media_evidence_items"],
        "optional_state_inputs": [],
        "output_contract": "CoverJobSubmissionResultV1",
        "backend": "managed",
        "knowledge_policy": "frozen_evidence_only",
        "timeout_seconds": 120,
        "max_execution_steps": 12,
        "max_tool_calls": 2,
        "token_budget": 8000,
        "result_tool_name": "submit_content_node_result",
    }
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

    assert captured["request"].input_payload["visual_plan"] == visual_plan
    assert captured["request"].governance_values["locked_values"]["visual_plan"] == visual_plan
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
        error_message="供应商余额不足",
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
    with pytest.raises(RuntimeError, match=f"{status}: 供应商余额不足"):
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
    visual_plan = {**_visual_plan(), "mode": "mixed", "plan_hash": "a" * 64}
    node_input = SimpleNamespace(
        task_id="task-1",
        parent_run_id="run-parent",
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
        _content_node_governance={
            "locked_values": {
                "state_version": 7,
                "visual_plan_hash": "a" * 64,
                "visual_plan": visual_plan,
            }
        },
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

    async def fake_get_task_for_user(repo, task_id, user):
        del repo, task_id, user
        return SimpleNamespace(runtime_config_snapshot_json={})

    monkeypatch.setattr(content_tools.ContentRepository, "get_task_for_user", fake_get_task_for_user)
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
    assert captured[0].mode == "image_to_image"
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
async def test_cover_tool_routes_locked_gallery_image_and_template_to_poster_billboard(monkeypatch):
    visual_plan = {**_visual_plan(), "plan_hash": "a" * 64}
    node_input = SimpleNamespace(
        task_id="task-1",
        parent_run_id="run-parent",
        node_id="submit_cover_job",
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
        _content_node_governance={
            "locked_values": {
                "state_version": 7,
                "visual_plan_hash": "a" * 64,
                "visual_plan": visual_plan,
            }
        },
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

    async def fake_get_task_for_user(repo, task_id, user):
        del repo, task_id, user
        return SimpleNamespace(
            runtime_config_snapshot_json={
                "visual_material": {
                    "image_asset_id": "source-1",
                    "poster_template_id": "poster-1",
                    "poster_template_checksum": "checksum-1",
                    "poster_template_version": 3,
                }
            }
        )

    async def fake_get_poster(repo, template_id, owner_uid):
        del repo, template_id, owner_uid
        return SimpleNamespace(status="ready", checksum="checksum-1", version=3)

    captured = []

    async def fake_create_poster(db, user, payload):
        del db, user
        captured.append(payload)
        return {"job": {"id": "poster-job-1", "mode": "poster_billboard"}, "deduplicated": False}

    async def fail_generate(*args, **kwargs):
        del args, kwargs
        raise AssertionError("选择大字报模板后不应进入普通图片生成")

    async def fake_event(*args, **kwargs):
        del args, kwargs

    monkeypatch.setattr(content_tools.pg_manager, "get_async_session_context", fake_session)
    monkeypatch.setattr(content_tools.ContentRepository, "get_task_for_user", fake_get_task_for_user)
    monkeypatch.setattr(ContentCoverRepository, "get_poster_template_for_user", fake_get_poster)
    monkeypatch.setattr(content_tools, "create_poster_billboard_job", fake_create_poster)
    monkeypatch.setattr(content_tools, "create_cover_generate_job", fail_generate)
    monkeypatch.setattr(content_tools, "_emit_content_tool_event", fake_event)

    result = await content_tools.create_content_cover_job.coroutine(
        task_id="task-1",
        runtime=SimpleNamespace(context=context),
    )

    assert result["cover_job_id"] == "poster-job-1"
    assert result["source_asset_ids"] == ["source-1"]
    assert captured[0].poster_template_id == "poster-1"
    assert captured[0].product_asset_id == "source-1"
    assert captured[0].content_task_id == "task-1"
    assert captured[0].enhance_with_image2 is False
    assert captured[0].parameters == {
        "visual_plan_hash": "a" * 64,
        "workflow_resume": {
            "parent_run_id": "run-parent",
            "node_id": "wait_cover_job",
            "expected_state_version": 7,
        },
    }


@pytest.mark.asyncio
async def test_cover_tool_rejects_assets_outside_locked_visual_plan():
    node_input = SimpleNamespace(
        task_id="task-1",
        parent_run_id="run-parent",
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
        _content_node_governance={
            "locked_values": {
                "state_version": 7,
                "visual_plan_hash": "a" * 64,
                "visual_plan": {
                    **_visual_plan(),
                    "plan_hash": "a" * 64,
                    "source_asset_ids": ["other-source"],
                },
            }
        },
    )

    with pytest.raises(ValueError, match="未授权素材"):
        await content_tools.create_content_cover_job.coroutine(
            task_id="task-1",
            runtime=SimpleNamespace(context=context),
        )


def test_cover_tool_only_accepts_task_id_from_agent():
    assert set(content_tools.CreateContentCoverJobInput.model_fields) == {"task_id"}


def test_skip_cover_pipeline_only_for_review_notes():
    assert skip_cover_pipeline({"content_brief": {"form_values": {"mp_service_entry": "好评笔记"}}})
    assert not skip_cover_pipeline({"content_brief": {"form_values": {"mp_service_entry": "装修家居"}}})
    assert not skip_cover_pipeline({"content_brief": {}})
    assert not skip_cover_pipeline({})


def test_mp_decoration_skips_content_correction_interrupt():
    assert skip_content_correction_interrupt(
        {"content_brief": {"form_values": {"mp_service_entry": "装修家居", "mp_content_code": "ZX-1"}}}
    )
    assert not skip_content_correction_interrupt(
        {"content_brief": {"form_values": {"mp_service_entry": "装修家居"}}}
    )


def test_skip_formula_lexicon_pipeline_only_for_review_notes():
    assert skip_formula_lexicon_pipeline({"content_brief": {"form_values": {"mp_service_entry": "好评笔记"}}})
    assert not skip_formula_lexicon_pipeline({"content_brief": {"form_values": {"mp_service_entry": "装修家居"}}})
    assert not skip_formula_lexicon_pipeline({"content_brief": {}})
    assert not skip_formula_lexicon_pipeline({})


@pytest.mark.asyncio
async def test_review_notes_skip_decoration_formula_lexicon_files():
    class ForbiddenDB:
        async def execute(self, *args, **kwargs):
            raise AssertionError("好评笔记不应查询装修标题/正文词库文件")

    result = await V3DeterministicNodeHandler()._load_formula_lexicons(
        db=ForbiddenDB(),
        state=_review_notes_state(
            strategy_snapshot={"title_formula": {"code": "T02"}, "body_formula": {"code": "C02"}},
            industry_pack_version_id="industry-pack-decoration-v3",
        ),
        node_run_id="node-1",
    )
    assert result["formula_lexicon_bundle"]["required"] is False
    assert result["formula_lexicon_bundle"]["title"] == []
    assert result["formula_lexicon_bundle"]["body"] == []


@pytest.mark.asyncio
async def test_home_furnishing_still_loads_decoration_formula_lexicons():
    class ProbeDB:
        async def execute(self, *args, **kwargs):
            raise AssertionError("装修家居应查询装修标题/正文词库文件")

    with pytest.raises(AssertionError, match="装修家居应查询装修标题/正文词库文件"):
        await V3DeterministicNodeHandler()._load_formula_lexicons(
            db=ProbeDB(),
            state=_review_notes_state(
                service_entry="装修家居",
                strategy_snapshot={"title_formula": {"code": "T02"}, "body_formula": {"code": "C02"}},
                industry_pack_version_id="industry-pack-decoration-v3",
            ),
            node_run_id="node-1",
        )


@pytest.mark.asyncio
async def test_review_notes_skip_research_agent_without_delegation():
    class ForbiddenDB:
        async def get(self, *args, **kwargs):
            raise AssertionError("好评笔记不应调用调研 Agent")

        async def execute(self, *args, **kwargs):
            raise AssertionError("好评笔记不应调用调研 Agent")

    result = await AgentNodeHandler().execute(
        db=ForbiddenDB(),
        node={"id": "collect_missing_evidence"},
        state=_review_notes_state(evidence_gap_analysis={"has_missing": True}),
        node_run_id="node-run-1",
    )

    assert result["evidence_collection"]["skipped"] is True
    assert result["evidence_collection"]["skip_reason"] == RESEARCH_SKIP_REASON
    assert result["evidence_collection"]["evidence_items"] == []
    assert result["evidence_collection"]["citations"] == []


@pytest.mark.asyncio
async def test_home_furnishing_skips_research_when_no_evidence_gap():
    class ForbiddenDB:
        async def get(self, *args, **kwargs):
            raise AssertionError("无证据缺口时不应调用调研 Agent")

        async def execute(self, *args, **kwargs):
            raise AssertionError("无证据缺口时不应调用调研 Agent")

    result = await AgentNodeHandler().execute(
        db=ForbiddenDB(),
        node={"id": "collect_missing_evidence"},
        state=_review_notes_state(service_entry="装修家居"),
        node_run_id="node-run-1",
    )

    assert result["evidence_collection"]["skipped"] is True
    assert result["evidence_collection"]["skip_reason"] == "当前公式候选池没有证据缺口"


@pytest.mark.asyncio
async def test_home_furnishing_research_runs_when_evidence_gap_exists():
    class ProbeDB:
        async def get(self, *args, **kwargs):
            raise AssertionError("装修家居有证据缺口时应进入调研 Agent")

        async def execute(self, *args, **kwargs):
            raise AssertionError("装修家居有证据缺口时应进入调研 Agent")

    with pytest.raises(AssertionError, match="装修家居有证据缺口时应进入调研 Agent"):
        await AgentNodeHandler().execute(
            db=ProbeDB(),
            node={"id": "collect_missing_evidence"},
            state=_review_notes_state(
                service_entry="装修家居",
                evidence_gap_analysis={"has_missing": True},
            ),
            node_run_id="node-run-1",
        )


def _review_notes_state(*, service_entry: str = "好评笔记", **extra) -> dict:
    return {
        "task_id": "task-1",
        "uid": "user-1",
        "run_id": "run-1",
        "state_version": 2,
        "content_brief": {"form_values": {"mp_service_entry": service_entry}},
        **extra,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("node_id", "state_key"),
    [
        ("plan_visuals", "visual_plan"),
        ("submit_cover_job", "cover_job"),
        ("visual_review", "visual_review"),
    ],
)
async def test_review_notes_skip_cover_agent_nodes_without_delegation(node_id: str, state_key: str):
    class ForbiddenDB:
        async def get(self, *args, **kwargs):
            raise AssertionError("好评笔记不应查询封面 Agent 节点依赖")

        async def execute(self, *args, **kwargs):
            raise AssertionError("好评笔记不应查询封面 Agent 节点依赖")

    result = await AgentNodeHandler().execute(
        db=ForbiddenDB(),
        node={"id": node_id},
        state=_review_notes_state(),
        node_run_id="node-run-1",
    )

    assert result[state_key]["skipped"] is True
    assert result[state_key]["skip_reason"] == COVER_SKIP_REASON
    if node_id == "visual_review":
        assert result[state_key]["assets"] == []


@pytest.mark.asyncio
async def test_external_wait_skips_cover_wait_for_review_notes(monkeypatch):
    monkeypatch.setattr(
        "yuxi.content.control.workflow.external_wait.interrupt",
        lambda _payload: pytest.fail("好评笔记不应进入封面等待"),
    )

    result = await ExternalWaitNodeHandler().execute(
        db=object(),
        node={
            "id": "wait_cover_job",
            "external_job_type": "content_cover",
            "timeout_seconds": 900,
        },
        state=_review_notes_state(cover_job={}),
    )

    assert result["cover_job"]["skipped"] is True
    assert result["cover_job"]["skip_reason"] == COVER_SKIP_REASON
    assert result["cover_assets"] == []
    assert result["resume_parent_run_id"] is None


@pytest.mark.asyncio
async def test_external_wait_still_requires_cover_job_id_for_home_furnishing():
    with pytest.raises(ValueError, match="外部等待节点缺少 cover_job_id"):
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
                "content_brief": {"form_values": {"mp_service_entry": "装修家居"}},
                "cover_job": {},
            },
        )


@pytest.mark.asyncio
async def test_cover_selection_does_not_interrupt_for_review_notes(monkeypatch):
    monkeypatch.setattr(
        content_workflow_graph_module,
        "interrupt",
        lambda _payload: pytest.fail("好评笔记不应触发人工选封面"),
    )

    result = await ContentWorkflowAgent()._v3_human_review(
        {"id": "select_cover", "interrupt_type": "cover_selection"},
        _review_notes_state(),
    )

    assert result["selected_cover"] == {}
    assert result["state_version"] == 3
    assert result["resume_parent_run_id"] is None


@pytest.mark.asyncio
async def test_content_approval_does_not_interrupt_for_review_notes(monkeypatch):
    monkeypatch.setattr(
        content_workflow_graph_module,
        "interrupt",
        lambda _payload: pytest.fail("好评笔记不应触发最终人工审批"),
    )

    result = await ContentWorkflowAgent()._v3_human_review(
        {"id": "human_content_approval", "interrupt_type": "content_approval"},
        _review_notes_state(
            uid="user-1",
            validation_report={"status": "passed", "checks": []},
            review_report={"status": "passed", "checks": []},
            selected_title={"text": "标题"},
            content_draft={"body": "正文"},
            evidence_bundle={"bundle_hash": "h1"},
        ),
    )

    assert result["approval_result"]["status"] == "approved"
    assert result["artifact_version"]["status"] == "approved_content"
