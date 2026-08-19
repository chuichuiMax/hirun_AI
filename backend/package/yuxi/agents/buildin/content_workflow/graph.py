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
    polish_persona_style,
    review_generated_content,
)
from yuxi.content.rules import recommend_strategy
from yuxi.content.validators import merge_evidence, normalize_manual_evidence, validate_content
from yuxi.content.v2 import (
    CombinationEngineV2,
    ComplianceEngine,
    ContentValueAnalyzer,
    FormulaSlotResolver,
    LexiconResolver,
    NarrativeConsistencyChecker,
    validate_numeric_evidence_coverage,
)
from yuxi.repositories.content_repository import ContentRepository
from yuxi.services.run_queue_service import append_run_stream_event, has_cancel_signal
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_content import ContentArtifact
from yuxi.utils.datetime_utils import utc_now_naive

from .context import ContentWorkflowContext
from .state import ContentWorkflowState

ALLOWED_NODE_TYPES = {
    "compile_brief",
    "compile_context",
    "ingest_materials",
    "assemble_facts",
    "skill",
    "tool_group",
    "human_review",
    "validator",
    "deterministic_validator",
    "combination_engine_v2",
    "formula_slot_resolver",
    "channel_adapter",
    "save_artifact",
}


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


def _review_report(checks: list[dict[str, Any]]) -> dict[str, Any]:
    status = "blocked" if any(item.get("level") == "error" for item in checks) else (
        "warning" if checks else "passed"
    )
    return {"status": status, "checks": checks}


def _media_evidence_dict(item: Any) -> dict[str, Any]:
    return {
        "id": item.id,
        "attachment_id": item.attachment_id,
        "object_uri": item.object_uri,
        "media_type": item.media_type,
        "original_filename": item.original_filename,
        "extracted_text": item.extracted_text,
        "metadata": item.metadata_json or {},
        "source_hash": item.source_hash,
        "verified_status": item.verified_status,
        "privacy_status": item.privacy_status,
        "allowed_usage": item.allowed_usage or [],
        "confirmed_facts": item.confirmed_facts or [],
    }


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
        if node_type == "compile_context":
            return await self._compile_context(state, rule_bundle)
        if node_type == "ingest_materials":
            evidence = dict(state.get("evidence_bundle") or {"items": []})
            additions = []
            for item in state.get("media_evidence_items") or []:
                if item.get("privacy_status") != "approved" or item.get("verified_status") == "rejected":
                    continue
                facts = {
                    str(fact.get("variable_code") or fact.get("key")): fact.get("value")
                    for fact in item.get("confirmed_facts") or []
                    if (fact.get("variable_code") or fact.get("key"))
                    and fact.get("value") not in (None, "", [])
                }
                additions.append(
                    {
                        "id": item["id"],
                        "type": "media_evidence",
                        "source_type": "media",
                        "source_id": item["attachment_id"],
                        "source_version": item["source_hash"],
                        "content": item.get("extracted_text") or "",
                        "values": facts,
                        "variable_codes": sorted(facts),
                        "verified_status": (
                            "confirmed" if item.get("verified_status") == "confirmed" else "needs_confirmation"
                        ),
                        "privacy_status": item.get("privacy_status"),
                        "allowed_usage": item.get("allowed_usage") or ["body"],
                    }
                )
            evidence = merge_evidence(evidence, additions)
            return {"evidence_bundle": evidence}
        if node_type == "assemble_facts":
            evidence = normalize_manual_evidence(state["task_id"], state["content_brief"])
            evidence = merge_evidence(evidence, (state.get("evidence_bundle") or {}).get("items") or [])
            persona = state.get("persona_profile") or {}
            persona_facts = []
            source_ids = list(persona.get("evidence_ids") or [])
            for index, fact in enumerate(persona.get("experience_facts") or []):
                if fact in (None, "", [], {}):
                    continue
                source_id = source_ids[index] if index < len(source_ids) else None
                digest = hashlib.sha256(f"{persona.get('id')}:{index}:{fact}".encode()).hexdigest()[:16]
                persona_facts.append(
                    {
                        "id": f"ev_persona_{digest}",
                        "type": "persona_fact",
                        "key": "persona_fact",
                        "value": fact,
                        "source_type": "persona_profile",
                        "source_id": source_id or persona.get("id"),
                        "source_version": persona.get("id"),
                        "verified_status": "confirmed" if source_id else "needs_confirmation",
                        "allowed_usage": ["title", "body"],
                    }
                )
            evidence = merge_evidence(evidence, persona_facts)
            evidence = merge_evidence(evidence, await _collect_knowledge_evidence(state))
            await _update_task(state["task_id"], evidence_json=evidence, status="collecting_evidence")
            return {"evidence_bundle": evidence}
        if node_type == "tool_group":
            evidence = dict(state.get("evidence_bundle") or {"items": []})
            evidence = merge_evidence(evidence, await _collect_knowledge_evidence(state))
            await _update_task(state["task_id"], evidence_json=evidence, status="collecting_evidence")
            return {"evidence_bundle": evidence}
        if node_type == "human_review":
            return await self._human_review(node, state, rule_bundle)
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
        if node_type == "combination_engine_v2":
            selected_angle = state.get("selected_angle") or {}
            content_type_code = selected_angle.get("content_type_code") or state["content_brief"].get(
                "content_type_code"
            )
            primary_axis = selected_angle.get("primary_narrative_axis") or state["content_brief"].get(
                "primary_narrative_axis"
            )
            if not content_type_code or not primary_axis:
                raise ValueError("V2 策略匹配前必须锁定内容类型和主要叙事轴")
            industry = state.get("industry_pack") or {}
            channel = state.get("channel_profile") or {}
            recommendation = CombinationEngineV2().recommend(
                rule_bundle,
                brief=state["content_brief"],
                evidence_bundle=state["evidence_bundle"],
                content_goal=state["content_brief"]["content_goal"],
                content_type_code=content_type_code,
                industry_slug=industry.get("slug") or state["content_brief"].get("industry"),
                channel_code=channel.get("code"),
                primary_narrative_axis=primary_axis,
                lexicon_entries=state.get("lexicon_entries") or [],
                persona=state.get("persona_profile") or {},
                limit=5,
                random_seed=0,
            )
            selected = recommendation.get("selected")
            if selected is None:
                raise ValueError("没有创作组合通过内容类型、行业、渠道和叙事轴硬约束")
            strategy = {
                **selected,
                "content_formula_code": selected["body_formula_code"],
                "content_goal": state["content_brief"]["content_goal"],
                "content_type_code": content_type_code,
                "content_angle": selected_angle,
                "primary_narrative_axis": primary_axis,
                "compatibility": recommendation["compatibility"],
                "recommendation_trace": {
                    "alternatives": recommendation.get("alternatives") or [],
                    "rejected": recommendation.get("rejected") or [],
                    "required_actions": recommendation.get("required_actions") or [],
                },
                "rule_version_id": state["rule_version_id"],
            }
            await _update_task(
                state["task_id"],
                strategy_json=strategy,
                primary_narrative_axis=primary_axis,
                selected_angle_json=selected_angle,
                content_type_code=content_type_code,
                status="planning_strategy",
                current_stage="strategy",
            )
            return {"strategy_plan": strategy}
        if node_type == "formula_slot_resolver":
            strategy = dict(state.get("strategy_plan") or {})
            patterns = {item["code"]: item for item in rule_bundle.get("formula_patterns") or []}
            resolver = FormulaSlotResolver()
            plans = {}
            for kind, strategy_key in (("title", "title_pattern_code"), ("body", "body_pattern_code")):
                pattern = patterns.get(strategy.get(strategy_key))
                if pattern is None:
                    raise ValueError(f"策略缺少可执行的 {kind} Pattern")
                plans[kind] = resolver.resolve(
                    pattern,
                    brief=state["content_brief"],
                    evidence_bundle=state["evidence_bundle"],
                    lexicon_entries=state.get("lexicon_entries") or [],
                    persona=state.get("persona_profile") or {},
                    content_goal=state["content_brief"].get("content_goal"),
                )
            strategy["slot_plan"] = plans
            await _update_task(state["task_id"], strategy_json=strategy)
            return {"strategy_plan": strategy, "slot_plan": plans}
        if node_type == "channel_adapter":
            draft = dict(state.get("content_draft") or {})
            selected_title = dict(state.get("selected_title") or {})
            result = ComplianceEngine().validate_and_adapt(
                title=selected_title.get("text", ""),
                body=draft.get("body", ""),
                topics=draft.get("topics") or [],
                channel_profile=state.get("channel_profile") or {},
                policies=state.get("compliance_policies") or [],
            )
            selected_title["text"] = result["title"]
            draft["body"] = result["body"]
            draft["topics"] = result["topics"]
            return {"selected_title": selected_title, "content_draft": draft, "channel_result": result}
        if node_type == "deterministic_validator":
            return await self._deterministic_validate(node, state)
        if node_type == "save_artifact":
            return await self._save_artifact(state)
        if node_type == "skill":
            return await self._execute_skill(node["skill"], state, rule_bundle)
        raise ValueError(f"未实现的节点类型: {node_type}")

    async def _compile_context(
        self, state: ContentWorkflowState, rule_bundle: dict[str, Any]
    ) -> dict[str, Any]:
        async with pg_manager.get_async_session_context() as db:
            repo = ContentRepository(db)
            task = await repo.get_task(state["task_id"], for_update=True)
            if task is None:
                raise ValueError(f"内容任务不存在: {state['task_id']}")
            if not state.get("content_brief"):
                raise ValueError("ContentBrief 为空")
            content_type = next(
                (
                    item
                    for item in rule_bundle.get("content_types") or []
                    if item.get("code") == task.content_type_code
                ),
                None,
            )
            if content_type is None:
                raise ValueError("V2 任务锁定的内容类型不存在")
            industry_pack = None
            if task.industry_pack_version_id:
                pack = await repo.get_industry_pack(task.industry_pack_version_id)
                if pack is not None:
                    industry_pack = {
                        "id": pack.id,
                        "slug": pack.slug,
                        "version": pack.version,
                        "status": pack.status,
                        "name": pack.name,
                        "content_type_aliases": pack.content_type_aliases or {},
                        "variable_schema": pack.variable_schema or [],
                        "lexicon_version_ids": pack.lexicon_version_ids or [],
                        "pattern_ids": pack.pattern_ids or [],
                        "evidence_policy": pack.evidence_policy or {},
                        "review_policy": pack.review_policy or {},
                    }
            channels = await repo.list_channel_profiles(published_only=False)
            channel = next(
                (item for item in channels if item["id"] == task.channel_profile_version_id), {}
            )
            persona: dict[str, Any] = {}
            if task.persona_profile_version_id:
                persona_row = await repo.get_persona_version(task.persona_profile_version_id)
                if persona_row:
                    version, profile = persona_row
                    persona = {
                        "id": version.id,
                        "profile_id": profile.id,
                        "name": profile.name,
                        "version": version.version,
                        "status": version.status,
                        "identity": version.identity or {},
                        "experience_facts": version.experience_facts or [],
                        "professional_background": version.professional_background or {},
                        "tone": version.tone or {},
                        "values": version.values or [],
                        "positions": version.positions or [],
                        "service_boundaries": version.service_boundaries or [],
                        "preferred_phrases": version.preferred_phrases or [],
                        "forbidden_phrases": version.forbidden_phrases or [],
                        "evidence_ids": version.evidence_ids or [],
                    }
            policies = []
            for policy in await repo.list_compliance_policies(published_only=True):
                applies = policy["scope_type"] == "platform"
                applies = applies or (
                    policy["scope_type"] == "industry"
                    and industry_pack
                    and policy.get("scope_id") == industry_pack.get("slug")
                )
                applies = applies or (
                    policy["scope_type"] == "channel"
                    and channel
                    and policy.get("scope_id") == channel.get("code")
                )
                applies = applies or (
                    policy["scope_type"] == "enterprise" and policy.get("tenant_id") == task.tenant_id
                )
                if applies:
                    policies.append(policy)
            lexicon_catalog = await repo.list_lexicon_packs(published_only=True)
            industry_lexicons = set((industry_pack or {}).get("lexicon_version_ids") or [])
            selected_lexicons = [
                item
                for item in lexicon_catalog
                if item["scope_type"] == "platform"
                or item["id"] in industry_lexicons
                or (
                    channel
                    and item["scope_type"] == "channel"
                    and item.get("scope_id") == channel.get("code")
                )
                or (item["scope_type"] == "enterprise" and item.get("tenant_id") == task.tenant_id)
            ]
            lexicon_versions = [
                {**item, "entries": await repo.list_lexicon_entries(item["id"])}
                for item in selected_lexicons
            ]
            lexicon = LexiconResolver().resolve(lexicon_versions)
            media = [_media_evidence_dict(item) for item in await repo.list_media_evidence(task.id)]
            runtime_snapshot = {
                **(task.runtime_config_snapshot_json or {}),
                "schema_version": 2,
                "workflow_version_id": task.workflow_version_id,
                "rule_version_id": task.rule_version_id,
                "content_type_code": task.content_type_code,
                "industry_pack_version_id": task.industry_pack_version_id,
                "persona_profile_version_id": task.persona_profile_version_id,
                "channel_profile_version_id": task.channel_profile_version_id,
                "lexicon_version_ids": lexicon["version_ids"],
                "compliance_policy_version_ids": [item["id"] for item in policies],
            }
            task.runtime_config_snapshot_json = runtime_snapshot
            task.status = "collecting_evidence"
            task.current_stage = "brief"
            return {
                "schema_version": 2,
                "runtime_config_snapshot": runtime_snapshot,
                "content_type": content_type,
                "industry_pack": industry_pack or {},
                "persona_profile": persona,
                "channel_profile": channel,
                "compliance_policies": policies,
                "lexicon_entries": lexicon["entries"],
                "media_evidence_items": media,
            }

    async def _deterministic_validate(
        self, node: dict[str, Any], state: ContentWorkflowState
    ) -> dict[str, Any]:
        if node["id"] == "validate_title_candidates":
            validated = []
            for original in state.get("title_candidates") or []:
                candidate = dict(original)
                numeric = validate_numeric_evidence_coverage(
                    candidate.get("text", ""), state["evidence_bundle"]
                )
                channel = ComplianceEngine().validate_and_adapt(
                    title=candidate.get("text", ""),
                    body="",
                    topics=[],
                    channel_profile={
                        **(state.get("channel_profile") or {}),
                        "body_constraints": {},
                    },
                    policies=state.get("compliance_policies") or [],
                )
                candidate["text"] = channel["title"]
                checks = numeric["checks"] + [
                    item
                    for item in channel["checks"]
                    if item.get("location") == "title"
                ]
                candidate["risk_flags"] = sorted(
                    set(candidate.get("risk_flags") or [])
                    | {str(item.get("code")) for item in checks if item.get("code")}
                )
                candidate["validation"] = _review_report(checks)
                candidate["selectable"] = candidate["validation"]["status"] != "blocked"
                validated.append(candidate)
            if not validated:
                raise ValueError("标题生成没有返回候选")
            if all(item["validation"]["status"] == "blocked" for item in validated):
                raise ValueError("所有标题候选均未通过数字证据或渠道合规门禁")
            validated.sort(key=lambda item: (not item["selectable"], item["id"]))
            await _update_task(state["task_id"], title_candidates_json=validated, status="waiting_title")
            return {
                "title_candidates": validated,
                "title_validation_report": _review_report(
                    [
                        check
                        for item in validated
                        for check in item["validation"].get("checks") or []
                    ]
                ),
            }

        draft = state.get("content_draft") or {}
        title = (state.get("selected_title") or {}).get("text", "")
        body = draft.get("body", "")
        topics = draft.get("topics") or []
        base = validate_content(
            title=title,
            body=body,
            topics=topics,
            brief=state["content_brief"],
            evidence_bundle=state["evidence_bundle"],
            strategy=state["strategy_plan"],
        )
        numeric = validate_numeric_evidence_coverage(
            f"{title}\n{body}\n{' '.join(topics)}", state["evidence_bundle"]
        )
        primary_axis = state["strategy_plan"].get("primary_narrative_axis")
        detected_axes = state["strategy_plan"].get("detected_narrative_axes") or [primary_axis]
        narrative = NarrativeConsistencyChecker().check(primary_axis, detected_axes)
        slot_checks = []
        for kind, plan in (state.get("slot_plan") or {}).items():
            for message in plan.get("blocking_reasons") or []:
                slot_checks.append(
                    {
                        "code": "FORMULA_SLOT_BLOCKED",
                        "level": "error",
                        "location": kind,
                        "message": message,
                    }
                )
        checks = (
            list(base.get("checks") or [])
            + list(numeric.get("checks") or [])
            + list(narrative.get("checks") or [])
            + slot_checks
            + list((state.get("channel_result") or {}).get("checks") or [])
        )
        report = _review_report(checks)
        await _update_task(
            state["task_id"], review_json=report, status="reviewing", current_stage="review"
        )
        return {"validation_report": report}

    async def _execute_skill(
        self, skill_slug: str, state: ContentWorkflowState, rule_bundle: dict[str, Any]
    ) -> dict[str, Any]:
        if skill_slug == "content-value-analyzer":
            angles = ContentValueAnalyzer().analyze(
                brief=state["content_brief"],
                evidence_bundle=state["evidence_bundle"],
                content_types=rule_bundle.get("content_types") or [],
                preferred_content_type=state["content_brief"].get("content_type_code"),
                limit=3,
            )
            if not angles:
                raise ValueError("当前事实无法形成可执行的内容角度")
            selected = state.get("selected_angle")
            strategy = {
                **(state.get("strategy_plan") or {}),
                "content_angle_candidates": angles,
            }
            await _update_task(
                state["task_id"], strategy_json=strategy, status="planning_strategy", current_stage="strategy"
            )
            return {"content_angles": angles, "selected_angle": selected, "strategy_plan": strategy}
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
                channel_profile=state.get("channel_profile") or {},
            )
            await _update_task(
                state["task_id"], title_candidates_json=titles, status="waiting_title", current_stage="generation"
            )
            return {"title_candidates": titles}
        if skill_slug == "content-outline-builder":
            strategy = dict(state["strategy_plan"])
            pattern = next(
                (
                    item
                    for item in rule_bundle.get("formula_patterns") or []
                    if item.get("code") == strategy.get("body_pattern_code")
                ),
                None,
            )
            if pattern is None:
                raise ValueError("正文大纲缺少已锁定的 Body Pattern")
            resolved_slots = {
                item["slot_key"]: item
                for item in (state.get("slot_plan") or {}).get("body", {}).get("slots") or []
            }
            sections = []
            evidence_usage = []
            for paragraph in pattern.get("paragraph_schema") or []:
                slot_keys = paragraph.get("slots") or []
                evidence_ids = sorted(
                    {
                        evidence_id
                        for slot_key in slot_keys
                        for evidence_id in (resolved_slots.get(slot_key) or {}).get("evidence_ids") or []
                    }
                )
                sections.append(
                    {
                        "code": paragraph.get("code"),
                        "purpose": paragraph.get("purpose"),
                        "slot_keys": slot_keys,
                        "evidence_required": bool(paragraph.get("evidence_required")),
                        "evidence_ids": evidence_ids,
                        "length": paragraph.get("length") or [],
                    }
                )
                evidence_usage.append(
                    {
                        "section_code": paragraph.get("code"),
                        "evidence_ids": evidence_ids,
                    }
                )
            outline = {
                "pattern_code": pattern["code"],
                "primary_narrative_axis": strategy.get("primary_narrative_axis"),
                "sections": sections,
            }
            usage_plan = {"sections": evidence_usage}
            strategy.update({"content_outline": outline, "evidence_usage_plan": usage_plan})
            await _update_task(state["task_id"], strategy_json=strategy, status="generating_body")
            return {
                "strategy_plan": strategy,
                "content_outline": outline,
                "evidence_usage_plan": usage_plan,
            }
        if skill_slug == "content-body-generator":
            draft = await generate_body(
                model_spec=state.get("model_spec"),
                brief=state["content_brief"],
                strategy=state["strategy_plan"],
                evidence_bundle=state["evidence_bundle"],
                selected_title=state["selected_title"],
                rule_bundle=rule_bundle,
                channel_profile=state.get("channel_profile") or {},
            )
            await _update_task(state["task_id"], status="generating_body")
            return {"content_draft": draft}
        if skill_slug == "persona-style-polisher":
            persona = state.get("persona_profile") or {}
            if not persona:
                return {}
            before = state["content_draft"]
            after = await polish_persona_style(
                model_spec=state.get("model_spec"),
                draft=before,
                brief=state["content_brief"],
                strategy=state["strategy_plan"],
                evidence_bundle=state["evidence_bundle"],
                persona=persona,
            )
            diff = {
                "before": before,
                "after": after,
                "persona_profile_version_id": persona.get("id"),
            }
            return {"content_draft": after, "persona_diff": diff}
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

    async def _human_review(
        self,
        node: dict[str, Any],
        state: ContentWorkflowState,
        rule_bundle: dict[str, Any],
    ) -> dict[str, Any]:
        interrupt_type = node.get("interrupt_type")
        if interrupt_type == "confirm_facts":
            pending = [
                item
                for item in (state.get("evidence_bundle") or {}).get("items", [])
                if item.get("verified_status") == "needs_confirmation"
            ]
            missing_slots = sorted(
                {
                    slot_key
                    for plan in (state.get("slot_plan") or {}).values()
                    for slot_key in plan.get("missing_slots") or []
                }
            )
            if not pending and not missing_slots and node.get("optional"):
                return {}
            answer = interrupt(
                {
                    "interrupt_type": "confirm_facts",
                    "task_id": state["task_id"],
                    "run_id": state["run_id"],
                    "node_id": node["id"],
                    "options": pending,
                    "missing_slots": missing_slots,
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
            submitted = []
            for index, item in enumerate((answer or {}).get("evidence_items") or []):
                key = str(item.get("key") or item.get("variable_code") or "").strip()
                value = item.get("value")
                if not key or value in (None, "", [], {}):
                    raise ValueError("补充事实必须包含 key 和非空 value")
                digest = hashlib.sha256(
                    f"{state['task_id']}:{key}:{value}:{index}".encode()
                ).hexdigest()[:16]
                submitted.append(
                    {
                        "id": str(item.get("id") or f"ev_resume_{digest}"),
                        "type": item.get("type") or "business_fact",
                        "key": key,
                        "value": value,
                        "values": item.get("values") or {key: value},
                        "variable_codes": item.get("variable_codes") or [key],
                        "source_type": "human_confirmation",
                        "source_id": state["uid"],
                        "source_version": state["run_id"],
                        "verified_status": "user_confirmed",
                        "allowed_usage": item.get("allowed_usage") or ["title", "body"],
                    }
                )
            evidence = merge_evidence(evidence, submitted)
            strategy = dict(state.get("strategy_plan") or {})
            plans = {}
            patterns = {item["code"]: item for item in rule_bundle.get("formula_patterns") or []}
            resolver = FormulaSlotResolver()
            for kind, strategy_key in (("title", "title_pattern_code"), ("body", "body_pattern_code")):
                pattern = patterns.get(strategy.get(strategy_key))
                if pattern:
                    plans[kind] = resolver.resolve(
                        pattern,
                        brief=state["content_brief"],
                        evidence_bundle=evidence,
                        lexicon_entries=state.get("lexicon_entries") or [],
                        persona=state.get("persona_profile") or {},
                        content_goal=state["content_brief"].get("content_goal"),
                    )
            if plans:
                strategy["slot_plan"] = plans
            await _update_task(state["task_id"], evidence_json=evidence)
            return {"evidence_bundle": evidence, "slot_plan": plans, "strategy_plan": strategy}
        if interrupt_type == "select_content_angle":
            selected = state.get("selected_angle")
            if selected:
                return {}
            options = state.get("content_angles") or []
            if not options and node.get("optional"):
                return {}
            answer = interrupt(
                {
                    "interrupt_type": "select_content_angle",
                    "task_id": state["task_id"],
                    "run_id": state["run_id"],
                    "node_id": node["id"],
                    "options": options,
                }
            )
            angle_id = (answer or {}).get("angle_id")
            selected = next((item for item in options if item.get("id") == angle_id), None)
            if selected is None:
                raise ValueError("angle_id 不属于当前内容角度候选")
            requested_axis = (answer or {}).get("primary_narrative_axis")
            if requested_axis and requested_axis != selected.get("primary_narrative_axis"):
                raise ValueError("主要叙事轴必须来自所选内容角度")
            await _update_task(
                state["task_id"],
                selected_angle_json=selected,
                primary_narrative_axis=selected["primary_narrative_axis"],
                content_type_code=selected["content_type_code"],
            )
            return {"selected_angle": selected}
        if interrupt_type == "select_title":
            options = [
                item
                for item in state.get("title_candidates") or []
                if item.get("selectable", True)
            ]
            answer = interrupt(
                {
                    "interrupt_type": "select_title",
                    "task_id": state["task_id"],
                    "run_id": state["run_id"],
                    "node_id": node["id"],
                    "options": options,
                }
            )
            selected_id = (answer or {}).get("selected_candidate_id")
            selected = next(
                (item for item in state.get("title_candidates") or [] if item.get("id") == selected_id), None
            )
            if selected is None:
                raise ValueError("selected_candidate_id 不属于当前标题候选")
            if not selected.get("selectable", True):
                raise ValueError("该标题候选未通过事实或渠道门禁，不能选择")
            await _update_task(state["task_id"], selected_title_json=selected, status="generating_body")
            return {"selected_title": selected}
        if interrupt_type == "human_approval":
            report = state.get("review_report") or state.get("validation_report") or {"status": "passed", "checks": []}
            requires_approval = report.get("status") != "passed" or any(
                check.get("human_confirmation_required")
                for check in report.get("checks") or []
            )
            if not requires_approval and node.get("optional"):
                return {"approval_result": {"status": "not_required"}}
            answer = interrupt(
                {
                    "interrupt_type": "human_approval",
                    "task_id": state["task_id"],
                    "run_id": state["run_id"],
                    "node_id": node["id"],
                    "review": report,
                    "channel_result": state.get("channel_result") or {},
                }
            )
            approval = {
                "status": "approved" if (answer or {}).get("approved") else "rejected",
                "note": (answer or {}).get("note"),
                "reviewer_uid": state["uid"],
            }
            return {"approval_result": approval}
        raise ValueError(f"未知人工节点: {interrupt_type}")

    async def _save_artifact(self, state: ContentWorkflowState) -> dict[str, Any]:
        draft = state["content_draft"]
        review = state.get("review_report") or state.get("validation_report") or {"status": "passed", "checks": []}
        approval_rejected = (state.get("approval_result") or {}).get("status") == "rejected"
        artifact_status = "blocked" if review["status"] == "blocked" or approval_rejected else "reviewed"
        async with pg_manager.get_async_session_context() as db:
            repo = ContentRepository(db)
            task = await repo.get_task(state["task_id"], for_update=True)
            artifact = await repo.get_artifact_for_task(task.id)
            if artifact is None:
                artifact = ContentArtifact(
                    id=f"ca_{uuid.uuid4().hex}",
                    task_id=task.id,
                    tenant_id=task.tenant_id,
                    status=artifact_status,
                    current_version=1,
                    title=state["selected_title"]["text"],
                    body=draft["body"],
                    topics=draft.get("topics") or [],
                    strategy_snapshot=state["strategy_plan"],
                    evidence_snapshot=state["evidence_bundle"],
                    review_snapshot=review,
                    content_type_snapshot=state.get("content_type") or {},
                    angle_snapshot=state.get("selected_angle") or {},
                    pattern_slot_snapshot={
                        "title_pattern_code": state["strategy_plan"].get("title_pattern_code"),
                        "body_pattern_code": state["strategy_plan"].get("body_pattern_code"),
                        "slot_plan": state.get("slot_plan") or {},
                        "outline": state.get("content_outline") or {},
                        "evidence_usage_plan": state.get("evidence_usage_plan") or {},
                    },
                    persona_snapshot={
                        "profile": state.get("persona_profile") or {},
                        "diff": state.get("persona_diff") or {},
                    },
                    channel_snapshot=state.get("channel_profile") or {},
                    compliance_snapshot={
                        "policies": state.get("compliance_policies") or [],
                        "result": state.get("channel_result") or {},
                        "approval": state.get("approval_result") or {},
                    },
                    runtime_config_snapshot=state.get("runtime_config_snapshot") or {},
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
                artifact.review_snapshot = review
                artifact.content_type_snapshot = state.get("content_type") or {}
                artifact.angle_snapshot = state.get("selected_angle") or {}
                artifact.pattern_slot_snapshot = {
                    "title_pattern_code": state["strategy_plan"].get("title_pattern_code"),
                    "body_pattern_code": state["strategy_plan"].get("body_pattern_code"),
                    "slot_plan": state.get("slot_plan") or {},
                    "outline": state.get("content_outline") or {},
                    "evidence_usage_plan": state.get("evidence_usage_plan") or {},
                }
                artifact.persona_snapshot = {
                    "profile": state.get("persona_profile") or {},
                    "diff": state.get("persona_diff") or {},
                }
                artifact.channel_snapshot = state.get("channel_profile") or {}
                artifact.compliance_snapshot = {
                    "policies": state.get("compliance_policies") or [],
                    "result": state.get("channel_result") or {},
                    "approval": state.get("approval_result") or {},
                }
                artifact.runtime_config_snapshot = state.get("runtime_config_snapshot") or {}
                artifact.status = artifact_status
                artifact.updated_at = utc_now_naive()
            version = await repo.save_artifact_version(
                artifact=artifact,
                source_type="generated",
                model_spec=state.get("model_spec"),
                skill_versions=SKILL_VERSIONS,
                rule_version_id=task.rule_version_id,
                knowledge_snapshot=state["evidence_bundle"],
                review_snapshot=review,
                created_by=state["uid"],
            )
            await repo.add_review_record(
                artifact_version_id=version.id,
                review_type="combined",
                status=review["status"],
                checks=review.get("checks") or [],
                reviewer_uid=(state.get("approval_result") or {}).get("reviewer_uid"),
            )
            task.status = "review_blocked" if artifact_status == "blocked" else "reviewed"
            task.current_stage = "review"
            task.review_json = review
            task.evidence_json = state["evidence_bundle"]
            task.selected_title_json = state["selected_title"]
            await repo.track(
                "content_run_completed",
                uid=state["uid"],
                task_id=task.id,
                run_id=state["run_id"],
                properties={"artifact_id": artifact.id, "review_status": review["status"]},
            )
            return {"artifact_id": artifact.id}
