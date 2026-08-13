from __future__ import annotations

import asyncio

from langgraph.types import Command

from yuxi.agents.buildin import agent_manager
from yuxi.agents.buildin.content_workflow.context import ContentWorkflowContext
from yuxi.repositories.agent_run_repository import TERMINAL_RUN_STATUSES, AgentRunRepository
from yuxi.repositories.content_repository import ContentRepository
from yuxi.services.run_queue_service import append_run_stream_event, clear_cancel_signal, has_cancel_signal
from yuxi.storage.postgres.manager import pg_manager
from yuxi.utils.logging_config import logger


async def _load_content_run(run_id: str):
    async with pg_manager.get_async_session_context() as db:
        run = await AgentRunRepository(db).get_run(run_id)
        if run is None:
            return None, None, None, None
        task = await ContentRepository(db).get_task(run.thread_id)
        if task is None:
            return run, None, None, None
        repo = ContentRepository(db)
        workflow = await repo.get_workflow(task.workflow_version_id)
        rule_bundle = await repo.get_rule_bundle(task.rule_version_id)
        return run, task, workflow, rule_bundle


async def _set_content_run_status(
    run_id: str,
    *,
    status: str,
    error_type: str | None = None,
    error_message: str | None = None,
) -> None:
    async with pg_manager.get_async_session_context() as db:
        repo = AgentRunRepository(db)
        if status == "running":
            await repo.mark_running(run_id)
        else:
            await repo.set_terminal_status(
                run_id,
                status=status,
                error_type=error_type,
                error_message=error_message,
            )


async def process_content_run(ctx, run_id: str):
    run, task, workflow, rule_bundle = await _load_content_run(run_id)
    if run is None:
        logger.warning(f"Content run not found: {run_id}")
        return
    if run.status in TERMINAL_RUN_STATUSES:
        return
    if task is None or workflow is None or rule_bundle is None:
        await _set_content_run_status(
            run_id,
            status="failed",
            error_type="content_configuration_missing",
            error_message="内容任务、工作流或规则版本不存在",
        )
        return

    payload = run.input_payload or {}
    action = payload.get("action") or "start"
    job_try = int((ctx or {}).get("job_try") or 1)
    await _set_content_run_status(run_id, status="running")
    await append_run_stream_event(
        run_id,
        "metadata",
        {
            "task_id": task.id,
            "workflow_version_id": task.workflow_version_id,
            "rule_version_id": task.rule_version_id,
            "action": action,
        },
        thread_id=task.id,
    )

    agent = agent_manager.get_agent("ContentWorkflowAgent")
    context = ContentWorkflowContext(
        uid=run.uid,
        thread_id=run.checkpoint_thread_id or f"content:{task.id}",
        run_id=run.id,
        request_id=run.request_id,
        task_id=task.id,
        workflow_definition=workflow.definition_json or {},
        rule_bundle=rule_bundle,
        model_spec=payload.get("model_spec"),
    )
    graph = await agent.get_graph(context=context)
    config = {
        "configurable": {"thread_id": context.thread_id, "uid": run.uid},
        "recursion_limit": 100,
    }
    try:
        if action == "resume":
            await graph.aupdate_state(
                config,
                {"run_id": run.id, "uid": run.uid, "model_spec": payload.get("model_spec")},
            )
            graph_input = Command(resume=payload.get("resume") or {})
        elif action == "retry" or job_try > 1:
            snapshot = await graph.aget_state(config)
            pending_nodes = set(snapshot.next or ())
            requested_node = payload.get("node_id")
            if not pending_nodes:
                raise RuntimeError("工作流 checkpoint 中没有可重试的失败节点")
            if requested_node and requested_node not in pending_nodes:
                raise RuntimeError(f"节点 {requested_node} 不是当前可重试节点")
            await graph.aupdate_state(
                config,
                {"run_id": run.id, "uid": run.uid, "model_spec": payload.get("model_spec")},
            )
            graph_input = None
        else:
            graph_input = {
                "task_id": task.id,
                "run_id": run.id,
                "uid": run.uid,
                "model_spec": payload.get("model_spec"),
                "workflow_version_id": task.workflow_version_id,
                "rule_version_id": task.rule_version_id,
                "industry_template_version_id": task.industry_template_version_id,
                "content_brief": task.brief_json or {},
                "strategy_plan": task.strategy_json or {},
                "evidence_bundle": task.evidence_json or {"items": []},
                "title_candidates": [],
                "selected_title": None,
                "content_draft": None,
                "validation_report": None,
                "review_report": None,
                "artifact_id": None,
                "current_node": "queued",
                "retry_counts": {},
            }

        await graph.ainvoke(graph_input, config=config, context=context)
        snapshot = await graph.aget_state(config)
        if snapshot.next:
            interrupts = list(getattr(snapshot, "interrupts", ()) or ())
            interrupt_payload = interrupts[0].value if interrupts else {"interrupt_type": "human_review"}
            async with pg_manager.get_async_session_context() as db:
                persisted_task = await ContentRepository(db).get_task(task.id, for_update=True)
                persisted_task.status = "waiting_human"
                persisted_task.current_stage = "generation"
                persisted_task.latest_run_id = run.id
                await ContentRepository(db).track(
                    "content_run_interrupted",
                    uid=run.uid,
                    task_id=task.id,
                    run_id=run.id,
                    properties={"interrupt_type": interrupt_payload.get("interrupt_type")},
                )
            await append_run_stream_event(
                run_id,
                "interrupt",
                interrupt_payload,
                thread_id=task.id,
            )
            await _set_content_run_status(run_id, status="interrupted")
            await append_run_stream_event(
                run_id,
                "end",
                {"status": "interrupted", "interrupt": interrupt_payload},
                thread_id=task.id,
            )
            return

        if await has_cancel_signal(run_id):
            raise asyncio.CancelledError
        await _set_content_run_status(run_id, status="completed")
        await append_run_stream_event(
            run_id,
            "end",
            {"status": "completed", "task_id": task.id},
            thread_id=task.id,
        )
    except (asyncio.CancelledError, InterruptedError):
        async with pg_manager.get_async_session_context() as db:
            persisted_task = await ContentRepository(db).get_task(task.id, for_update=True)
            persisted_task.status = "cancelled"
            persisted_task.error_json = {"code": "CONTENT_RUN_CANCELLED", "message": "内容运行已取消"}
        await _set_content_run_status(
            run_id,
            status="cancelled",
            error_type="cancelled",
            error_message="内容运行已取消",
        )
        await append_run_stream_event(run_id, "end", {"status": "cancelled"}, thread_id=task.id)
    except Exception as exc:
        if job_try < 2:
            await append_run_stream_event(
                run_id,
                "error",
                {"status": "retrying", "message": str(exc), "job_try": job_try},
                thread_id=task.id,
            )
            raise
        async with pg_manager.get_async_session_context() as db:
            persisted_task = await ContentRepository(db).get_task(task.id, for_update=True)
            persisted_task.status = "failed"
            persisted_task.error_json = {
                "code": "CONTENT_WORKFLOW_FAILED",
                "message": str(exc),
                "retryable": True,
            }
            await ContentRepository(db).track(
                "content_run_failed",
                uid=run.uid,
                task_id=task.id,
                run_id=run.id,
                properties={"error_type": type(exc).__name__},
            )
        await _set_content_run_status(
            run_id,
            status="failed",
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        await append_run_stream_event(
            run_id,
            "error",
            {"status": "failed", "message": str(exc), "retryable": True},
            thread_id=task.id,
        )
        await append_run_stream_event(run_id, "end", {"status": "failed"}, thread_id=task.id)
    finally:
        await clear_cancel_signal(run_id)
