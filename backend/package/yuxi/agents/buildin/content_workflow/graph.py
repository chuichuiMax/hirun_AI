from __future__ import annotations

import hashlib
import inspect
import os
import uuid
from collections.abc import Callable
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.errors import GraphInterrupt
from langgraph.types import interrupt

from yuxi.agents import BaseAgent
from yuxi.agents.backends.knowledge_base_backend import resolve_visible_knowledge_bases_for_context
from yuxi.content.generation import (
    SKILL_VERSIONS,
    generate_body,
    generate_title_candidates,
    review_generated_content,
)
from yuxi.content.rules import recommend_strategy
from yuxi.content.validators import merge_evidence, normalize_manual_evidence, validate_content
from yuxi.repositories.content_repository import ContentRepository
from yuxi.services.run_queue_service import append_run_stream_event, has_cancel_signal
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_content import ContentArtifact
from yuxi.utils.datetime_utils import utc_now_naive

from .context import ContentWorkflowContext
from .state import ContentWorkflowState

ALLOWED_NODE_TYPES = {"compile_brief", "skill", "tool_group", "human_review", "validator", "save_artifact"}


def _event_payload(state: ContentWorkflowState, node_id: str, status: str, **extra: Any) -> dict[str, Any]:
    return {
        "name": "content.node",
        "task_id": state["task_id"],
        "node_id": node_id,
        "status": status,
        **extra,
    }


async def _update_task(task_id: str, **changes: Any) -> None:
    async with pg_manager.get_async_session_context() as db:
        task = await ContentRepository(db).get_task(task_id, for_update=True)
        if task is None:
            raise ValueError(f"内容任务不存在: {task_id}")
        for key, value in changes.items():
            setattr(task, key, value)
        task.updated_at = utc_now_naive()


async def _collect_knowledge_evidence(state: ContentWorkflowState) -> list[dict[str, Any]]:
    scope = state["content_brief"].get("knowledge_scope") or []
    if not scope or os.environ.get("LITE_MODE", "").lower() in {"true", "1"}:
        return []

    from yuxi.agents.context import BaseContext
    from yuxi.knowledge import knowledge_base
    from yuxi.knowledge.base import KnowledgeBase

    context = BaseContext(uid=state["uid"], thread_id=f"content:{state['task_id']}", knowledges=scope)
    visible = await resolve_visible_knowledge_bases_for_context(context)
    retrievers = knowledge_base.get_retrievers()
    variables = state["content_brief"].get("business_variables") or {}
    query = " ".join(
        str(value)
        for value in (
            (state["content_brief"].get("brand") or {}).get("name"),
            variables.get("product"),
            variables.get("pain_points"),
            variables.get("result"),
        )
        if value
    )
    additions = []
    for kb in visible:
        kb_id = str(kb.get("kb_id") or "")
        target = retrievers.get(kb_id)
        if not target:
            continue
        retriever = target["retriever"]
        result = await retriever(query) if inspect.iscoroutinefunction(retriever) else retriever(query)
        output = (
            result
            if isinstance(result, dict) and "results" in result
            else KnowledgeBase.build_search_output(kb_id, result)
        )
        for item in (output.get("results") if isinstance(output, dict) else [])[:3]:
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            source_id = str(item.get("id") or item.get("file_id") or uuid.uuid4().hex)
            digest = hashlib.sha256(f"{kb_id}:{source_id}:{content}".encode()).hexdigest()[:16]
            additions.append(
                {
                    "id": f"ev_{digest}",
                    "type": "knowledge_fragment",
                    "key": "knowledge_context",
                    "value": content,
                    "source_type": "knowledge_base",
                    "source_id": source_id,
                    "source_version": str((item.get("metadata") or {}).get("version") or "retrieved"),
                    "kb_id": kb_id,
                    "file_id": item.get("file_id"),
                    "verified_status": "retrieved",
                    "allowed_usage": ["body"],
                    "metadata": item.get("metadata") or {},
                }
            )
    return additions


def _merge_review_reports(deterministic: dict[str, Any], llm: dict[str, Any]) -> dict[str, Any]:
    checks = list(deterministic.get("checks") or []) + list(llm.get("checks") or [])
    status = "blocked" if any(item.get("level") == "error" for item in checks) else "warning" if checks else "passed"
    return {"status": status, "checks": checks}


class ContentWorkflowAgent(BaseAgent):
    name = "通用内容生产工作流"
    description = "由数据库工作流定义装配，执行内容策略、证据、标题、正文和审核节点。"
    capabilities = []
    context_schema = ContentWorkflowContext

    async def _get_checkpointer(self):
        if self.checkpointer is not None:
            return self.checkpointer
        checkpointer = await self._create_postgres_checkpointer()
        if checkpointer is not None:
            await checkpointer.setup()
            self.checkpointer = checkpointer
            return checkpointer
        return await super()._get_checkpointer()

    async def get_graph(self, context: ContentWorkflowContext | None = None, **kwargs):
        del kwargs
        context = context or self.context_schema()
        definition = context.workflow_definition
        self._validate_definition(definition)
        graph = StateGraph(ContentWorkflowState)
        nodes = {node["id"]: node for node in definition["nodes"]}
        for node_id, node in nodes.items():
            graph.add_node(node_id, self._node_runner(node, context.rule_bundle))

        incoming = {node_id: 0 for node_id in nodes}
        outgoing = {node_id: 0 for node_id in nodes}
        for source, target in definition["edges"]:
            graph.add_edge(source, target)
            incoming[target] += 1
            outgoing[source] += 1
        roots = [node_id for node_id, count in incoming.items() if count == 0]
        leaves = [node_id for node_id, count in outgoing.items() if count == 0]
        for node_id in roots:
            graph.add_edge(START, node_id)
        for node_id in leaves:
            graph.add_edge(node_id, END)
        return graph.compile(checkpointer=await self._get_checkpointer())

    @staticmethod
    def _validate_definition(definition: dict[str, Any]) -> None:
        nodes = definition.get("nodes") if isinstance(definition, dict) else None
        edges = definition.get("edges") if isinstance(definition, dict) else None
        if not isinstance(nodes, list) or not nodes or not isinstance(edges, list):
            raise ValueError("工作流定义必须包含 nodes 和 edges")
        ids = [node.get("id") for node in nodes if isinstance(node, dict)]
        if len(ids) != len(set(ids)) or any(not node_id for node_id in ids):
            raise ValueError("工作流节点 ID 不能为空或重复")
        for node in nodes:
            if node.get("type") not in ALLOWED_NODE_TYPES:
                raise ValueError(f"不支持的工作流节点类型: {node.get('type')}")
        indegree = {node_id: 0 for node_id in ids}
        outgoing = {node_id: [] for node_id in ids}
        for edge in edges:
            if not isinstance(edge, list) or len(edge) != 2 or edge[0] not in ids or edge[1] not in ids:
                raise ValueError(f"无效的工作流连线: {edge}")
            outgoing[edge[0]].append(edge[1])
            indegree[edge[1]] += 1

        ready = [node_id for node_id, count in indegree.items() if count == 0]
        visited = 0
        while ready:
            source = ready.pop()
            visited += 1
            for target in outgoing[source]:
                indegree[target] -= 1
                if indegree[target] == 0:
                    ready.append(target)
        if visited != len(ids):
            raise ValueError("工作流定义不能包含循环依赖")

    def _node_runner(self, node: dict[str, Any], rule_bundle: dict[str, Any]) -> Callable:
        async def run(state: ContentWorkflowState) -> dict[str, Any]:
            node_id = node["id"]
            run_id = state["run_id"]
            if await has_cancel_signal(run_id):
                raise InterruptedError("内容运行已取消")
            await append_run_stream_event(
                run_id,
                "custom",
                _event_payload(state, node_id, "running"),
                thread_id=state["task_id"],
            )
            async with pg_manager.get_async_session_context() as db:
                repo = ContentRepository(db)
                node_run = await repo.add_node_run(
                    task_id=state["task_id"],
                    run_id=run_id,
                    node_id=node_id,
                    node_type=node["type"],
                    input_snapshot={"current_node": state.get("current_node")},
                )
            try:
                result = await self._execute_node(node, state, rule_bundle)
            except GraphInterrupt:
                async with pg_manager.get_async_session_context() as db:
                    repo = ContentRepository(db)
                    persisted = await db.get(type(node_run), node_run.id)
                    if persisted:
                        await repo.finish_node_run(persisted, status="waiting_human")
                raise
            except Exception as exc:
                async with pg_manager.get_async_session_context() as db:
                    repo = ContentRepository(db)
                    persisted = await db.get(type(node_run), node_run.id)
                    if persisted:
                        await repo.finish_node_run(
                            persisted,
                            status="failed",
                            error_type=type(exc).__name__,
                            error_message=str(exc),
                        )
                await append_run_stream_event(
                    run_id,
                    "custom",
                    _event_payload(state, node_id, "failed", message=str(exc)),
                    thread_id=state["task_id"],
                )
                raise
            async with pg_manager.get_async_session_context() as db:
                repo = ContentRepository(db)
                persisted = await db.get(type(node_run), node_run.id)
                if persisted:
                    await repo.finish_node_run(
                        persisted,
                        status="completed",
                        output_snapshot={"updated_fields": sorted(result.keys())},
                    )
            await append_run_stream_event(
                run_id,
                "custom",
                _event_payload(state, node_id, "completed"),
                thread_id=state["task_id"],
            )
            return {**result, "current_node": node_id}

        return run

    async def _execute_node(
        self, node: dict[str, Any], state: ContentWorkflowState, rule_bundle: dict[str, Any]
    ) -> dict[str, Any]:
        node_type = node["type"]
        if node_type == "compile_brief":
            if not state.get("content_brief"):
                raise ValueError("ContentBrief 为空")
            return {"content_brief": state["content_brief"]}
        if node_type == "tool_group":
            evidence = normalize_manual_evidence(state["task_id"], state["content_brief"])
            evidence = merge_evidence(evidence, await _collect_knowledge_evidence(state))
            await _update_task(state["task_id"], evidence_json=evidence, status="collecting_evidence")
            return {"evidence_bundle": evidence}
        if node_type == "human_review":
            return await self._human_review(node, state)
        if node_type == "validator":
            draft = state.get("content_draft") or {}
            report = validate_content(
                title=(state.get("selected_title") or {}).get("text", ""),
                body=draft.get("body", ""),
                topics=draft.get("topics") or [],
                brief=state["content_brief"],
                evidence_bundle=state["evidence_bundle"],
                strategy=state["strategy_plan"],
            )
            await _update_task(state["task_id"], review_json=report, status="reviewing", current_stage="review")
            return {"validation_report": report}
        if node_type == "save_artifact":
            return await self._save_artifact(state)
        if node_type == "skill":
            return await self._execute_skill(node["skill"], state, rule_bundle)
        raise ValueError(f"未实现的节点类型: {node_type}")

    async def _execute_skill(
        self, skill_slug: str, state: ContentWorkflowState, rule_bundle: dict[str, Any]
    ) -> dict[str, Any]:
        if skill_slug == "content-strategy-planner":
            strategy = state.get("strategy_plan") or recommend_strategy(
                rule_bundle,
                brief=state["content_brief"],
                content_goal=state["content_brief"]["content_goal"],
            )
            await _update_task(state["task_id"], strategy_json=strategy, status="planning_strategy")
            return {"strategy_plan": strategy}
        if skill_slug == "content-title-generator":
            titles = await generate_title_candidates(
                model_spec=state.get("model_spec"),
                brief=state["content_brief"],
                strategy=state["strategy_plan"],
                evidence_bundle=state["evidence_bundle"],
                rule_bundle=rule_bundle,
            )
            await _update_task(
                state["task_id"], title_candidates_json=titles, status="waiting_title", current_stage="generation"
            )
            return {"title_candidates": titles}
        if skill_slug == "content-body-generator":
            draft = await generate_body(
                model_spec=state.get("model_spec"),
                brief=state["content_brief"],
                strategy=state["strategy_plan"],
                evidence_bundle=state["evidence_bundle"],
                selected_title=state["selected_title"],
                rule_bundle=rule_bundle,
            )
            await _update_task(state["task_id"], status="generating_body")
            return {"content_draft": draft}
        if skill_slug == "content-reviewer":
            draft = state["content_draft"]
            llm_report = await review_generated_content(
                model_spec=state.get("model_spec"),
                title=state["selected_title"]["text"],
                body=draft["body"],
                topics=draft.get("topics") or [],
                brief=state["content_brief"],
                strategy=state["strategy_plan"],
                evidence_bundle=state["evidence_bundle"],
            )
            report = _merge_review_reports(state["validation_report"], llm_report)
            await _update_task(state["task_id"], review_json=report, status="reviewing")
            return {"review_report": report}
        raise ValueError(f"工作流引用了未知 Skill: {skill_slug}")

    async def _human_review(self, node: dict[str, Any], state: ContentWorkflowState) -> dict[str, Any]:
        interrupt_type = node.get("interrupt_type")
        if interrupt_type == "confirm_facts":
            pending = [
                item
                for item in (state.get("evidence_bundle") or {}).get("items", [])
                if item.get("verified_status") == "needs_confirmation"
            ]
            if not pending and node.get("optional"):
                return {}
            answer = interrupt(
                {
                    "interrupt_type": "confirm_facts",
                    "task_id": state["task_id"],
                    "run_id": state["run_id"],
                    "node_id": node["id"],
                    "options": pending,
                }
            )
            confirmed_ids = set((answer or {}).get("confirmed_evidence_ids") or [])
            evidence = dict(state["evidence_bundle"])
            evidence["items"] = [
                {**item, "verified_status": "user_confirmed"}
                if item.get("id") in confirmed_ids
                else item
                for item in evidence.get("items", [])
            ]
            await _update_task(state["task_id"], evidence_json=evidence)
            return {"evidence_bundle": evidence}
        if interrupt_type == "select_title":
            answer = interrupt(
                {
                    "interrupt_type": "select_title",
                    "task_id": state["task_id"],
                    "run_id": state["run_id"],
                    "node_id": node["id"],
                    "options": state.get("title_candidates") or [],
                }
            )
            selected_id = (answer or {}).get("selected_candidate_id")
            selected = next(
                (item for item in state.get("title_candidates") or [] if item.get("id") == selected_id), None
            )
            if selected is None:
                raise ValueError("selected_candidate_id 不属于当前标题候选")
            await _update_task(state["task_id"], selected_title_json=selected, status="generating_body")
            return {"selected_title": selected}
        raise ValueError(f"未知人工节点: {interrupt_type}")

    async def _save_artifact(self, state: ContentWorkflowState) -> dict[str, Any]:
        draft = state["content_draft"]
        async with pg_manager.get_async_session_context() as db:
            repo = ContentRepository(db)
            task = await repo.get_task(state["task_id"], for_update=True)
            artifact = await repo.get_artifact_for_task(task.id)
            if artifact is None:
                artifact = ContentArtifact(
                    id=f"ca_{uuid.uuid4().hex}",
                    task_id=task.id,
                    tenant_id=task.tenant_id,
                    status="blocked" if state["review_report"]["status"] == "blocked" else "reviewed",
                    current_version=1,
                    title=state["selected_title"]["text"],
                    body=draft["body"],
                    topics=draft.get("topics") or [],
                    strategy_snapshot=state["strategy_plan"],
                    evidence_snapshot=state["evidence_bundle"],
                    review_snapshot=state["review_report"],
                    created_by=state["uid"],
                )
                db.add(artifact)
                await db.flush()
            else:
                artifact.current_version += 1
                artifact.title = state["selected_title"]["text"]
                artifact.body = draft["body"]
                artifact.topics = draft.get("topics") or []
                artifact.strategy_snapshot = state["strategy_plan"]
                artifact.evidence_snapshot = state["evidence_bundle"]
                artifact.review_snapshot = state["review_report"]
                artifact.status = "blocked" if state["review_report"]["status"] == "blocked" else "reviewed"
                artifact.updated_at = utc_now_naive()
            version = await repo.save_artifact_version(
                artifact=artifact,
                source_type="generated",
                model_spec=state.get("model_spec"),
                skill_versions=SKILL_VERSIONS,
                rule_version_id=task.rule_version_id,
                knowledge_snapshot=state["evidence_bundle"],
                review_snapshot=state["review_report"],
                created_by=state["uid"],
            )
            await repo.add_review_record(
                artifact_version_id=version.id,
                review_type="combined",
                status=state["review_report"]["status"],
                checks=state["review_report"].get("checks") or [],
                reviewer_uid=None,
            )
            task.status = "review_blocked" if state["review_report"]["status"] == "blocked" else "reviewed"
            task.current_stage = "review"
            task.review_json = state["review_report"]
            task.evidence_json = state["evidence_bundle"]
            task.selected_title_json = state["selected_title"]
            await repo.track(
                "content_run_completed",
                uid=state["uid"],
                task_id=task.id,
                run_id=state["run_id"],
                properties={"artifact_id": artifact.id, "review_status": state["review_report"]["status"]},
            )
            return {"artifact_id": artifact.id}
