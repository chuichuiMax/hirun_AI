from __future__ import annotations

from copy import deepcopy

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from yuxi.agents.buildin.content_workflow.context import ContentWorkflowContext
from yuxi.agents.buildin.content_workflow.graph import ContentWorkflowAgent
from yuxi.agents.buildin.content_workflow.state import ContentWorkflowState
from yuxi.content.control.workflow.agent_node import AgentNodeResultMapper
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
        "generate_title_candidates",
        "generate_body",
        "persona_style_polish",
        "human_content_approval",
    }


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
