from types import SimpleNamespace

import pytest

from yuxi.content.schemas import ReviewReport
from yuxi.services import content_run_worker
from yuxi.services.run_worker import RetryableRunError


class FakeGraph:
    def __init__(self):
        self.updated_state = None
        self.invoked_with = "not-called"
        self.completed = False

    async def aget_state(self, config):
        return SimpleNamespace(next=() if self.completed else ("generate_body",), interrupts=())

    async def aupdate_state(self, config, values):
        self.updated_state = values

    async def ainvoke(self, graph_input, **kwargs):
        self.invoked_with = graph_input
        self.completed = True


@pytest.mark.asyncio
async def test_failed_node_retry_continues_from_checkpoint(monkeypatch):
    graph = FakeGraph()
    statuses = []

    run = SimpleNamespace(
        id="run-retry",
        status="pending",
        uid="user-1",
        request_id="request-1",
        checkpoint_thread_id="content:task-1",
        input_payload={"action": "retry", "node_id": "generate_body", "model_spec": None},
    )
    task = SimpleNamespace(
        id="task-1",
        workflow_version_id="workflow-v1",
        rule_version_id="rules-v1",
        industry_template_version_id="industry-v1",
        brief_json={},
        strategy_json={},
        evidence_json={"items": []},
    )
    workflow = SimpleNamespace(definition_json={"nodes": [], "edges": []})

    async def load_run(run_id):
        return run, task, workflow, {"version": {"id": "rules-v1"}}

    async def set_status(run_id, *, status, **kwargs):
        statuses.append(status)

    async def no_event(*args, **kwargs):
        return None

    async def no_cancel(*args, **kwargs):
        return False

    async def get_graph(*args, **kwargs):
        return graph

    monkeypatch.setattr(content_run_worker, "_load_content_run", load_run)
    monkeypatch.setattr(content_run_worker, "_set_content_run_status", set_status)
    monkeypatch.setattr(content_run_worker, "append_run_stream_event", no_event)
    monkeypatch.setattr(content_run_worker, "clear_cancel_signal", no_event)
    monkeypatch.setattr(content_run_worker, "has_cancel_signal", no_cancel)
    monkeypatch.setattr(
        content_run_worker.agent_manager,
        "get_agent",
        lambda agent_id: SimpleNamespace(get_graph=get_graph),
    )

    await content_run_worker.process_content_run({"job_try": 1}, run.id)

    assert graph.invoked_with is None
    assert graph.updated_state == {"run_id": run.id, "uid": run.uid, "model_spec": None}
    assert statuses == ["running", "completed"]


@pytest.mark.asyncio
async def test_retryable_model_validation_error_is_wrapped_for_arq_retry(monkeypatch):
    class InvalidModelGraph:
        async def ainvoke(self, graph_input, **kwargs):
            del graph_input, kwargs
            ReviewReport.model_validate(
                {"status": "passed", "checks": [{"code": "x", "level": "passed", "message": "ok"}]}
            )

    run = SimpleNamespace(
        id="run-model-retry",
        status="pending",
        uid="user-1",
        request_id="request-model-retry",
        checkpoint_thread_id="content:task-model-retry",
        input_payload={"action": "start", "model_spec": None},
    )
    task = SimpleNamespace(
        id="task-model-retry",
        workflow_version_id="workflow-v2",
        rule_version_id="rules-v2",
        industry_template_version_id="industry-v2",
        runtime_config_snapshot_json={"schema_version": 2},
        brief_json={"task_id": "task-model-retry"},
        strategy_json={"compatibility": "compatible"},
        evidence_json={"items": []},
        selected_angle_json={},
    )
    workflow = SimpleNamespace(definition_json={"nodes": [], "edges": []})
    statuses = []

    async def load_run(run_id):
        return run, task, workflow, {"version": {"id": "rules-v2"}}

    async def set_status(run_id, *, status, **kwargs):
        statuses.append(status)

    async def no_event(*args, **kwargs):
        return None

    async def no_cancel(*args, **kwargs):
        return False

    async def get_graph(*args, **kwargs):
        return InvalidModelGraph()

    monkeypatch.setattr(content_run_worker, "_load_content_run", load_run)
    monkeypatch.setattr(content_run_worker, "_set_content_run_status", set_status)
    monkeypatch.setattr(content_run_worker, "append_run_stream_event", no_event)
    monkeypatch.setattr(content_run_worker, "clear_cancel_signal", no_event)
    monkeypatch.setattr(content_run_worker, "has_cancel_signal", no_cancel)
    monkeypatch.setattr(
        content_run_worker.agent_manager,
        "get_agent",
        lambda agent_id: SimpleNamespace(get_graph=get_graph),
    )

    with pytest.raises(RetryableRunError):
        await content_run_worker.process_content_run({"job_try": 1}, run.id)

    assert statuses == ["running"]
