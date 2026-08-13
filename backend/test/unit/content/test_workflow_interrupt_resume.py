from __future__ import annotations

from copy import deepcopy

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from yuxi.agents.buildin.content_workflow import graph as graph_module
from yuxi.agents.buildin.content_workflow.context import ContentWorkflowContext
from yuxi.agents.buildin.content_workflow.graph import ContentWorkflowAgent
from yuxi.content.rules import BODY_FORMULAS, METHODS, TITLE_FORMULAS, WORKFLOW_DEFINITION


class WorkflowUnderTest(ContentWorkflowAgent):
    @property
    def module_name(self):
        return "content_workflow_test"

    def _node_runner(self, node, rule_bundle):
        async def run(state):
            result = await self._execute_node(node, state, rule_bundle)
            return {**result, "current_node": node["id"]}

        return run

    async def _save_artifact(self, state):
        assert state["selected_title"]["id"] == "title_2"
        return {"artifact_id": "artifact_1"}


@pytest.mark.asyncio
async def test_workflow_interrupts_for_title_and_resumes_with_same_evidence(monkeypatch):
    evidence_seen = {}

    async def ignore_task_update(*args, **kwargs):
        return None

    async def no_knowledge_evidence(state):
        return []

    async def generate_titles(**kwargs):
        evidence_seen["titles"] = deepcopy(kwargs["evidence_bundle"])
        return [
            {
                "id": f"title_{index}",
                "text": text,
                "formula_code": "T05",
                "variable_mapping": {},
                "evidence_ids": [],
                "risk_flags": [],
            }
            for index, text in enumerate(("标题一", "标题二", "标题三", "标题四"), start=1)
        ]

    async def generate_body(**kwargs):
        evidence_seen["body"] = deepcopy(kwargs["evidence_bundle"])
        assert kwargs["selected_title"]["id"] == "title_2"
        return {"body": "这是一篇只使用已确认事实的正文。", "topics": ["企业内容"], "evidence_ids": []}

    async def review_content(**kwargs):
        evidence_seen["review"] = deepcopy(kwargs["evidence_bundle"])
        return {"status": "passed", "checks": []}

    monkeypatch.setattr(graph_module, "_update_task", ignore_task_update)
    monkeypatch.setattr(graph_module, "_collect_knowledge_evidence", no_knowledge_evidence)
    monkeypatch.setattr(graph_module, "generate_title_candidates", generate_titles)
    monkeypatch.setattr(graph_module, "generate_body", generate_body)
    monkeypatch.setattr(graph_module, "review_generated_content", review_content)

    rule_bundle = {
        "version": {"id": "rules-v1"},
        "methods": deepcopy(METHODS),
        "title_formulas": deepcopy(TITLE_FORMULAS),
        "content_formulas": deepcopy(BODY_FORMULAS),
        "combination_rules": [],
    }
    context = ContentWorkflowContext(
        uid="user-1",
        thread_id="content:task-1",
        run_id="run-1",
        task_id="task-1",
        workflow_definition=deepcopy(WORKFLOW_DEFINITION),
        rule_bundle=rule_bundle,
    )
    agent = WorkflowUnderTest()
    agent.checkpointer = InMemorySaver()
    workflow = await agent.get_graph(context=context)
    config = {"configurable": {"thread_id": context.thread_id, "uid": context.uid}}
    initial_state = {
        "task_id": "task-1",
        "run_id": "run-1",
        "uid": "user-1",
        "workflow_version_id": "workflow-v1",
        "rule_version_id": "rules-v1",
        "industry_template_version_id": "industry-v1",
        "content_brief": {
            "task_id": "task-1",
            "industry": "professional-services",
            "content_goal": "brand",
            "mode": "pro",
            "brand": {"name": "示例企业"},
            "audience": ["企业经营者"],
            "business_variables": {
                "product": "内容咨询",
                "pain_points": ["表达缺少结构"],
                "advantages": ["真实业务资料驱动"],
            },
            "required_terms": [],
            "forbidden_terms": [],
            "knowledge_scope": [],
        },
        "strategy_plan": {
            "content_goal": "brand",
            "methods": ["M03", "M04"],
            "scene_enhancer": "S01",
            "title_formula_code": "T05",
            "content_formula_code": "C04",
            "compatibility": "compatible",
            "rule_version_id": "rules-v1",
        },
        "evidence_bundle": {"items": []},
        "title_candidates": [],
        "selected_title": None,
        "current_node": "queued",
    }

    await workflow.ainvoke(initial_state, config=config, context=context)
    interrupted = await workflow.aget_state(config)

    assert interrupted.next == ("select_title",)
    assert interrupted.interrupts[0].value["interrupt_type"] == "select_title"
    assert len(interrupted.interrupts[0].value["options"]) == 4

    await workflow.aupdate_state(config, {"run_id": "run-2", "uid": "user-1"})
    await workflow.ainvoke(
        Command(resume={"interrupt_type": "select_title", "selected_candidate_id": "title_2"}),
        config=config,
        context=context,
    )
    completed = await workflow.aget_state(config)

    assert completed.next == ()
    assert completed.values["artifact_id"] == "artifact_1"
    assert completed.values["run_id"] == "run-2"
    assert completed.values["selected_title"]["id"] == "title_2"
    assert evidence_seen["titles"] == evidence_seen["body"] == evidence_seen["review"]
