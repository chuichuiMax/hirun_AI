from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from yuxi.agents.buildin.content_workflow.context import ContentWorkflowContext
from yuxi.agents.buildin.content_workflow.graph import ContentWorkflowAgent
from yuxi.agents.buildin.content_workflow.state import ContentWorkflowState
from yuxi.content.control.workflow.agent_node import AgentNodeResultMapper
from yuxi.content.control.errors import ContentApplicationError
from yuxi.content.control.workflow.revision import resolve_revision_reason
from yuxi.content.v3.workflow import WORKFLOW_V3


@pytest.mark.unit
@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("TITLE_TOO_LONG", "TITLE_VALIDATION_FAILED"),
        ("PERSONA_TONE_MISMATCH", "PERSONA_STYLE_FAILED"),
        ("EVIDENCE_REFERENCE_FORBIDDEN", "BODY_EVIDENCE_FAILED"),
        ("BODY_LENGTH_OUT_OF_RANGE", "BODY_STRUCTURE_FAILED"),
    ],
)
def test_revision_reason_is_deterministic(code: str, expected: str):
    result = resolve_revision_reason(
        title_validation_report=None,
        validation_report={"status": "blocked", "checks": [{"code": code, "level": "error"}]},
        review_report=None,
    )

    assert result == expected


@pytest.mark.unit
def test_revision_reason_is_empty_when_all_checks_pass():
    assert (
        resolve_revision_reason(
            title_validation_report={"status": "passed", "items": []},
            validation_report={"status": "passed", "checks": []},
            review_report={"status": "passed", "checks": []},
        )
        is None
    )


@pytest.mark.asyncio
async def test_strategy_snapshot_locks_one_title_formula_one_body_formula_and_all_group_methods():
    group = SimpleNamespace(
        id="group-1",
        method_members=[
            {"method_code": "M01", "role": "primary", "order": 1},
            {"method_code": "M03", "role": "supporting", "order": 2},
        ],
        methods=[],
    )
    title = SimpleNamespace(
        code="T03",
        name="标题公式",
        core_goal="命中受众与痛点",
        reference_examples=[],
        variable_schema=[],
        compatible_methods=["M01", "M03"],
        risk_rules=[],
    )
    body = SimpleNamespace(
        code="C03",
        name="正文公式",
        structure_schema=[{"slot": "opening"}],
        reference_examples=[],
        required_variables=[],
        output_schema={},
        compatible_methods=["M01", "M03"],
        risk_rules=[],
    )

    class Result:
        def __init__(self, value, *, many=False):
            self.value = value
            self.many = many

        def scalar_one_or_none(self):
            return self.value

        def scalars(self):
            return self.value

    class FakeDb:
        def __init__(self):
            self.results = [
                Result(title),
                Result(body),
            Result(
                [
                    SimpleNamespace(
                        code=code,
                        name=f"手法 {code}",
                        method_type="core",
                        principle="可验证原则",
                        suitable_scenes=[],
                        sentence_patterns=[],
                        variable_schema=["result"],
                        risk_rules=[],
                    )
                    for code in ("M01", "M03")
                ],
                many=True,
            ),
            ]

        async def get(self, model, identity):
            del model
            assert identity == "group-1"
            return group

        async def execute(self, query):
            del query
            return self.results.pop(0)

    snapshot = await ContentWorkflowAgent._build_strategy_snapshot(
        db=FakeDb(),
        state={"rule_version_id": "rules-v3", "selected_angle": {"direction_code": "CT05"}},
        match={"id": "match-1", "selected_group_id": "group-1"},
        formula_snapshot_id="formula-1",
        title_formula_code="T03",
        body_formula_code="C03",
    )

    assert snapshot["creation_methods"] == ["M01", "M03"]
    assert [item["code"] for item in snapshot["creation_method_definitions"]] == ["M01", "M03"]
    assert snapshot["title_formula"]["code"] == "T03"
    assert snapshot["body_formula"]["code"] == "C03"
    assert len(snapshot["snapshot_hash"]) == 64


@pytest.mark.unit
def test_persona_mapper_changes_language_only_and_preserves_locked_draft_fields():
    state = {
        "content_draft": {
            "body": "原正文",
            "topics": ["装修"],
            "paragraph_evidence": [{"paragraph_id": "p1", "evidence_ids": ["ev1"]}],
            "body_formula_code": "C01",
        }
    }

    mapped = AgentNodeResultMapper.to_state(
        "persona_style_polish",
        {
            "polished_body": "润色后的正文",
            "change_summary": ["调整语气"],
            "preserved_fact_checks": [{"evidence_id": "ev1", "preserved": True}],
        },
        state,
    )

    assert mapped["content_draft"] == {
        **state["content_draft"],
        "body": "润色后的正文",
    }
    assert mapped["persona_diff"]["preserved_fact_checks"][0]["preserved"] is True


@pytest.mark.asyncio
async def test_v3_graph_compiles_revision_routes_as_controlled_conditional_edges():
    agent = ContentWorkflowAgent()
    agent.checkpointer = InMemorySaver()
    context = ContentWorkflowContext(
        uid="user-1",
        thread_id="content-v3-compile",
        workflow_definition=deepcopy(WORKFLOW_V3),
        rule_bundle={},
    )

    workflow = await agent.get_graph(context=context)
    revision_edges = {
        edge.target for edge in workflow.get_graph().edges if edge.source == "revise_if_needed" and edge.conditional
    }

    assert revision_edges == {
        "semantic_review",
        "generate_title_candidates",
        "generate_body",
        "persona_style_polish",
        "human_content_approval",
    }


@pytest.mark.asyncio
async def test_deterministic_block_pauses_for_human_before_targeted_agent_revision():
    agent = ContentWorkflowAgent()
    graph = StateGraph(ContentWorkflowState)

    async def revise(state: ContentWorkflowState):
        return await agent._execute_node(
            {"id": "revise_if_needed", "type": "revision_router"},
            state,
            WORKFLOW_V3,
        )

    graph.add_node("revise_if_needed", revise)
    graph.add_edge(START, "revise_if_needed")
    graph.add_edge("revise_if_needed", END)
    workflow = graph.compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "correction-gate"}}
    state = {
        "task_id": "task-1",
        "run_id": "run-1",
        "current_node": "deterministic_validate",
        "state_version": 7,
        "retry_counts": {},
        "validation_report": {
            "status": "blocked",
            "checks": [
                {
                    "code": "BODY_LENGTH_OUT_OF_RANGE",
                    "level": "error",
                    "message": "正文长度不符合要求",
                }
            ],
        },
    }

    await workflow.ainvoke(state, config=config)
    interrupted = await workflow.aget_state(config)
    payload = interrupted.interrupts[0].value
    assert payload["interrupt_type"] == "content_correction"
    assert payload["suggested_target"] == "generate_body"

    await workflow.ainvoke(
        Command(
            resume={
                "run_id": "run-1",
                "node_id": "revise_if_needed",
                "expected_state_version": 7,
                "decision": "revise",
            }
        ),
        config=config,
    )
    completed = await workflow.aget_state(config)
    assert completed.values["revision_target"] == "generate_body"
    assert completed.values["retry_counts"] == {"generate_body": 1}


@pytest.mark.asyncio
async def test_system_validation_failure_never_reaches_semantic_agent_or_human_approval():
    agent = ContentWorkflowAgent()
    state = {
        "task_id": "task-1",
        "run_id": "run-1",
        "current_node": "deterministic_validate",
        "validation_report": {
            "status": "blocked",
            "checks": [{"code": "CONTENT_STRATEGY_SNAPSHOT_MISSING", "level": "error"}],
        },
    }

    with pytest.raises(ContentApplicationError) as exc_info:
        await agent._execute_node(
            {"id": "revise_if_needed", "type": "revision_router"},
            state,
            WORKFLOW_V3,
        )

    assert exc_info.value.code == "system_configuration_failed"


@pytest.mark.asyncio
async def test_final_approval_is_a_backend_hard_gate_for_both_reports():
    agent = ContentWorkflowAgent()
    state = {
        "task_id": "task-1",
        "run_id": "run-1",
        "state_version": 1,
        "validation_report": {"status": "passed", "checks": []},
        "review_report": {
            "status": "blocked",
            "checks": [{"code": "FACT_INCONSISTENT", "status": "blocked"}],
        },
    }

    with pytest.raises(ContentApplicationError) as exc_info:
        await agent._v3_human_review(
            {"id": "human_content_approval", "interrupt_type": "content_approval"},
            state,
        )

    assert exc_info.value.code == "content_approval_blocked"


def _title_gate_graph(agent: ContentWorkflowAgent):
    graph = StateGraph(ContentWorkflowState)

    async def select_title(state: ContentWorkflowState):
        return await agent._v3_human_review(
            {"id": "select_title", "interrupt_type": "title_selection"},
            state,
        )

    graph.add_node("select_title", select_title)
    graph.add_edge(START, "select_title")
    graph.add_edge("select_title", END)
    return graph.compile(checkpointer=InMemorySaver())


@pytest.mark.asyncio
async def test_v3_human_gate_rejects_stale_resume_and_only_exposes_selectable_titles():
    workflow = _title_gate_graph(ContentWorkflowAgent())
    config = {"configurable": {"thread_id": "title-gate-stale"}}
    state = {
        "task_id": "task-1",
        "run_id": "run-1",
        "state_version": 3,
        "title_candidates": [
            {"id": "good", "text": "可选标题", "selectable": True},
            {"id": "bad", "text": "阻断标题", "selectable": False},
        ],
    }

    await workflow.ainvoke(state, config=config)
    interrupted = await workflow.aget_state(config)
    assert [item["id"] for item in interrupted.interrupts[0].value["options"]] == ["good"]

    with pytest.raises(ValueError, match="已过期或目标不匹配"):
        await workflow.ainvoke(
            Command(
                resume={
                    "run_id": "run-1",
                    "node_id": "select_title",
                    "expected_state_version": 2,
                    "title_id": "good",
                }
            ),
            config=config,
        )


@pytest.mark.asyncio
async def test_v3_human_gate_accepts_exact_run_node_and_state_version():
    workflow = _title_gate_graph(ContentWorkflowAgent())
    config = {"configurable": {"thread_id": "title-gate-current"}}
    state = {
        "task_id": "task-1",
        "run_id": "run-1",
        "state_version": 3,
        "title_candidates": [{"id": "good", "text": "可选标题", "selectable": True}],
    }

    await workflow.ainvoke(state, config=config)
    result = await workflow.ainvoke(
        Command(
            resume={
                "run_id": "run-1",
                "node_id": "select_title",
                "expected_state_version": 3,
                "title_id": "good",
            }
        ),
        config=config,
    )

    assert result["selected_title"]["id"] == "good"
    assert result["state_version"] == 4
