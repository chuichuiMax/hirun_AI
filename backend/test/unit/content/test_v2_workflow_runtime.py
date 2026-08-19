from __future__ import annotations

from copy import deepcopy

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from yuxi.agents.buildin.content_workflow import graph as graph_module
from yuxi.agents.buildin.content_workflow.context import ContentWorkflowContext
from yuxi.agents.buildin.content_workflow.graph import ContentWorkflowAgent
from yuxi.content.v2.seed import WORKFLOW_V2


class V2WorkflowUnderTest(ContentWorkflowAgent):
    @property
    def module_name(self):
        return "content_workflow_v2_test"

    def _node_runner(self, node, rule_bundle):
        async def run(state):
            result = await self._execute_node(node, state, rule_bundle)
            return {**result, "current_node": node["id"]}

        return run

    async def _compile_context(self, state, rule_bundle):
        del state
        return {
            "schema_version": 2,
            "runtime_config_snapshot": {
                "schema_version": 2,
                "rule_version_id": rule_bundle["version"]["id"],
                "industry_pack_version_id": "industry-pack-decoration-v2",
                "channel_profile_version_id": "channel-xiaohongshu-v1",
            },
            "content_type": rule_bundle["content_types"][0],
            "industry_pack": {"id": "industry-pack-decoration-v2", "slug": "decoration"},
            "persona_profile": {},
            "channel_profile": {
                "id": "channel-xiaohongshu-v1",
                "code": "xiaohongshu",
                "title_constraints": {"max_length": 20},
            },
            "compliance_policies": [],
            "lexicon_entries": [],
            "media_evidence_items": [],
        }

    async def _save_artifact(self, state):
        assert state["strategy_plan"]["title_pattern_code"] == "T01-P01"
        assert state["content_outline"]["pattern_code"] == "C02-P01"
        assert state["selected_title"]["id"] == "title_2"
        return {"artifact_id": "artifact_v2"}


def _rule_bundle():
    title_pattern = {
        "code": "T01-P01",
        "formula_kind": "title",
        "formula_code": "T01",
        "template_text": "{audience}：{number}完成{result}",
        "slots": [
            {"slot_key": "audience", "source_type": "brief", "source_path": "audience", "required": True},
            {"slot_key": "number", "source_type": "evidence", "required": True, "evidence_required": True},
            {"slot_key": "result", "source_type": "evidence", "required": True, "evidence_required": True},
        ],
    }
    body_pattern = {
        "code": "C02-P01",
        "formula_kind": "body",
        "formula_code": "C02",
        "template_text": "背景→过程→结果",
        "paragraph_schema": [
            {"code": "background", "purpose": "背景", "slots": ["audience"], "evidence_required": False},
            {"code": "process", "purpose": "过程", "slots": ["process"], "evidence_required": True},
            {"code": "result", "purpose": "结果", "slots": ["result"], "evidence_required": True},
        ],
        "slots": [
            {"slot_key": "audience", "source_type": "brief", "source_path": "audience", "required": True},
            {"slot_key": "process", "source_type": "evidence", "required": True, "evidence_required": True},
            {"slot_key": "result", "source_type": "evidence", "required": True, "evidence_required": True},
        ],
    }
    return {
        "version": {"id": "content-rules-platform-v2"},
        "content_types": [
            {
                "code": "CT01",
                "name": "案例/成果展示",
                "description": "用真实过程和结果证明能力",
                "supported_goals": ["acquire"],
                "required_variable_codes": ["result", "process"],
                "default_narrative_axes": ["before_after_result"],
                "enabled": True,
            }
        ],
        "methods": [{"code": "M01", "name": "数字法"}, {"code": "M04", "name": "人群定位法"}],
        "title_formulas": [{"code": "T01", "name": "细分人群＋数字＋结果"}],
        "content_formulas": [{"code": "C02", "name": "案例流量类", "structure_schema": []}],
        "formula_patterns": [title_pattern, body_pattern],
        "combination_rules": [
            {
                "id": "combination-acquire-ct01-v2",
                "content_goal": "acquire",
                "content_type_codes": ["CT01"],
                "methods": ["M01", "M04"],
                "title_formula_codes": ["T01"],
                "title_pattern_codes": ["T01-P01"],
                "content_formula_code": "C02",
                "body_pattern_codes": ["C02-P01"],
                "narrative_axis_codes": ["before_after_result"],
                "priority": 100,
                "score_weights": {},
            }
        ],
    }


@pytest.mark.asyncio
async def test_v2_workflow_pauses_for_angle_and_title_then_saves_same_source_artifact(monkeypatch):
    evidence_seen = []

    async def ignore_task_update(*args, **kwargs):
        return None

    async def no_knowledge_evidence(state):
        return []

    async def generate_titles(**kwargs):
        evidence_seen.append(deepcopy(kwargs["evidence_bundle"]))
        items = [
            {
                "id": f"title_{index}",
                "text": f"杭州小户型：12㎡完成收纳优化{suffix}",
                "formula_code": "T01",
                "pattern_code": "T01-P01",
                "variable_mapping": {},
                "evidence_ids": [],
                "risk_flags": [],
            }
            for index, suffix in enumerate(("甲", "乙", "丙", "丁"), start=1)
        ]
        items[0]["text"] = "杭州小户型刚需家庭：12㎡完成现场确认增加12㎡收纳空间"
        return items

    async def generate_body(**kwargs):
        evidence_seen.append(deepcopy(kwargs["evidence_bundle"]))
        return {
            "body": "面向杭州小户型家庭，按现场流程完成改造，真实结果是增加12㎡收纳空间。",
            "topics": ["装修案例"],
            "evidence_ids": [],
            "paragraph_evidence": [],
        }

    async def review_content(**kwargs):
        evidence_seen.append(deepcopy(kwargs["evidence_bundle"]))
        return {"status": "passed", "checks": []}

    monkeypatch.setattr(graph_module, "_update_task", ignore_task_update)
    monkeypatch.setattr(graph_module, "_collect_knowledge_evidence", no_knowledge_evidence)
    monkeypatch.setattr(graph_module, "generate_title_candidates", generate_titles)
    monkeypatch.setattr(graph_module, "generate_body", generate_body)
    monkeypatch.setattr(graph_module, "review_generated_content", review_content)

    bundle = _rule_bundle()
    context = ContentWorkflowContext(
        uid="user-1",
        thread_id="content:task-v2",
        run_id="run-v2-1",
        task_id="task-v2",
        workflow_definition=deepcopy(WORKFLOW_V2),
        rule_bundle=bundle,
    )
    agent = V2WorkflowUnderTest()
    agent.checkpointer = InMemorySaver()
    workflow = await agent.get_graph(context=context)
    config = {"configurable": {"thread_id": context.thread_id, "uid": context.uid}}
    initial_state = {
        "task_id": "task-v2",
        "run_id": "run-v2-1",
        "uid": "user-1",
        "workflow_version_id": "content-workflow-enterprise-v2",
        "rule_version_id": bundle["version"]["id"],
        "industry_template_version_id": "industry-decoration-v2",
        "content_brief": {
            "task_id": "task-v2",
            "industry": "decoration",
            "content_goal": "acquire",
            "content_type_code": "CT01",
            "brand": {"name": "示例装修"},
            "audience": ["杭州小户型家庭"],
            "business_variables": {
                "number": "12㎡",
                "result": "增加12㎡收纳空间",
                "process": "按现场测量、设计和施工流程改造",
            },
            "knowledge_scope": [],
            "required_terms": [],
            "forbidden_terms": [],
        },
        "strategy_plan": {},
        "evidence_bundle": {"items": []},
        "title_candidates": [],
        "selected_title": None,
        "current_node": "queued",
    }

    await workflow.ainvoke(initial_state, config=config, context=context)
    angle_pause = await workflow.aget_state(config)
    assert angle_pause.next == ("select_content_angle",)
    angle = angle_pause.interrupts[0].value["options"][0]

    await workflow.ainvoke(
        Command(
            resume={
                "angle_id": angle["id"],
                "primary_narrative_axis": angle["primary_narrative_axis"],
            }
        ),
        config=config,
        context=context,
    )
    title_pause = await workflow.aget_state(config)
    assert title_pause.next == ("select_title",)
    assert len(title_pause.interrupts[0].value["options"]) == 3
    assert all(item["id"] != "title_1" for item in title_pause.interrupts[0].value["options"])

    await workflow.ainvoke(
        Command(resume={"selected_candidate_id": "title_2"}),
        config=config,
        context=context,
    )
    completed = await workflow.aget_state(config)
    assert completed.next == (), completed.values.get("review_report")
    assert completed.values["artifact_id"] == "artifact_v2"
    assert completed.values["validation_report"]["status"] == "passed"
    assert evidence_seen[0] == evidence_seen[1] == evidence_seen[2]
