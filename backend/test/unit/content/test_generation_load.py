from copy import deepcopy
from types import SimpleNamespace

import json
import pytest

from yuxi.content.control.workflow.generation_input import (
    project_generation_input,
    project_visual_plan_input,
)
from yuxi.content.rules import canonical_brief_facts
from yuxi.agents.middlewares.model_call_timeout import (
    ModelCallTimeoutMiddleware,
    ModelExecutionBudgetExceeded,
)


@pytest.mark.parametrize("node_id", ["select_creation_strategy", "reselect_creation_strategy"])
def test_strategy_has_time_for_two_calls_and_preserves_explicit_reasoning(node_id):
    from yuxi.services.agent_delegation_service import AgentDelegationService, CONTENT_NODE_EXECUTION_LIMITS

    request = SimpleNamespace(node_run=SimpleNamespace(node_id=node_id), knowledge_policy="frozen_evidence_only")
    context = SimpleNamespace(reasoning_effort=None)
    AgentDelegationService._apply_node_constraints(context, request)
    assert context.reasoning_effort == "low"
    assert context.model_call_timeout_seconds == 65
    assert context.model_retry_times == 2
    assert context._content_max_model_calls == 2
    assert (
        CONTENT_NODE_EXECUTION_LIMITS[node_id][0]
        >= context._content_max_model_calls * context.model_call_timeout_seconds + 3 + 15
    )
    context.reasoning_effort = "medium"
    AgentDelegationService._apply_node_constraints(context, request)
    assert context.reasoning_effort == "low"


def test_review_notes_generate_content_allows_forced_submit_retry():
    from yuxi.services.agent_delegation_service import AgentDelegationService, CONTENT_NODE_EXECUTION_LIMITS

    request = SimpleNamespace(
        node_run=SimpleNamespace(node_id="generate_content"),
        knowledge_policy="agent_scope",
    )
    context = SimpleNamespace(reasoning_effort=None)
    AgentDelegationService._apply_node_constraints(context, request)
    assert context.model_call_timeout_seconds == 180
    assert context._content_max_model_calls == 3
    assert context.model_retry_times == 2
    assert CONTENT_NODE_EXECUTION_LIMITS["generate_content"] == (400, 180, "low", 3)
    idle = CONTENT_NODE_EXECUTION_LIMITS["generate_content"][1]
    assert CONTENT_NODE_EXECUTION_LIMITS["generate_content"][0] >= 2 * idle + 3 + 15


def test_generate_content_allows_forced_submit_retry():
    from yuxi.services.agent_delegation_service import AgentDelegationService, CONTENT_NODE_EXECUTION_LIMITS

    request = SimpleNamespace(
        node_run=SimpleNamespace(node_id="generate_content"),
        knowledge_policy="frozen_evidence_only",
    )
    context = SimpleNamespace(reasoning_effort=None)
    AgentDelegationService._apply_node_constraints(context, request)
    assert context.reasoning_effort == "low"
    assert context.model_call_timeout_seconds == 180
    assert context.model_retry_times == 2
    assert context._content_max_model_calls == 3
    assert CONTENT_NODE_EXECUTION_LIMITS["generate_content"] == (400, 180, "low", 3)


def test_plan_visuals_allows_forced_submit_retry():
    from yuxi.services.agent_delegation_service import AgentDelegationService, CONTENT_NODE_EXECUTION_LIMITS

    request = SimpleNamespace(
        node_run=SimpleNamespace(node_id="plan_visuals"),
        knowledge_policy="frozen_evidence_only",
    )
    context = SimpleNamespace(reasoning_effort=None)
    AgentDelegationService._apply_node_constraints(context, request)
    assert context.reasoning_effort == "low"
    assert context.model_call_timeout_seconds == 180
    assert context.model_retry_times == 2
    assert context._content_max_model_calls == 3
    assert CONTENT_NODE_EXECUTION_LIMITS["plan_visuals"] == (400, 180, "low", 3)
    idle = CONTENT_NODE_EXECUTION_LIMITS["plan_visuals"][1]
    assert CONTENT_NODE_EXECUTION_LIMITS["plan_visuals"][0] >= 2 * idle + 3 + 15


def test_siliconflow_50507_is_retryable():
    import httpx
    from openai import APIStatusError

    from yuxi.agents.middlewares.model_call_timeout import retryable_content_model_error

    request = httpx.Request("POST", "https://api.siliconflow.cn/v1/chat/completions")
    response = httpx.Response(500, request=request)
    exc = APIStatusError(
        message="Error code: 500 - {'code': 50507, 'message': 'Request failed: Unknown error.', 'data': None}",
        response=response,
        body={"code": 50507, "message": "Request failed: Unknown error.", "data": None},
    )
    assert retryable_content_model_error(exc) is True
    assert retryable_content_model_error(RuntimeError("Error code: 500 - {'code': 50507}")) is True


def test_content_nodes_disable_siliconflow_thinking():
    from yuxi.agents.buildin.chatbot.graph import build_chat_model_kwargs

    controlled = SimpleNamespace(_content_max_model_calls=3, reasoning_effort="low")
    assert build_chat_model_kwargs(controlled) == {
        "max_retries": 0,
        "streaming": True,
        "extra_body": {"enable_thinking": False},
    }
    assert "reasoning_effort" not in build_chat_model_kwargs(controlled)

    normal = SimpleNamespace(_content_max_model_calls=None, reasoning_effort="low")
    assert build_chat_model_kwargs(normal) == {"reasoning_effort": "low"}


@pytest.mark.asyncio
async def test_generate_content_caps_max_tokens_at_1200():
    from langchain.agents.middleware import ModelResponse
    from langchain_core.messages import AIMessage

    from yuxi.agents.middlewares.model_call_timeout import ModelCallTimeoutMiddleware

    context = SimpleNamespace(
        _content_max_model_calls=3,
        _content_node_token_budget=8000,
        _content_node_id="generate_content",
        _content_model_calls=0,
    )

    class Request(SimpleNamespace):
        def override(self, **kwargs):
            return Request(**{**vars(self), **kwargs})

    request = Request(
        runtime=SimpleNamespace(context=context),
        model_settings={},
        messages=[],
        model=SimpleNamespace(reasoning_effort="low"),
        tools=[],
        system_message=None,
    )
    captured = []

    async def handler(req):
        captured.append(req.model_settings["max_tokens"])
        return ModelResponse(result=[AIMessage(content="ok")])

    await ModelCallTimeoutMiddleware(180).awrap_model_call(request, handler)
    assert captured == [1200]


def test_original_generate_content_keeps_layout_humanizer_and_expression():
    from yuxi.services.agent_delegation_service import ORIGINAL_GENERATE_CONTENT_DROP_SKILLS

    request = SimpleNamespace(
        node_run=SimpleNamespace(node_id="generate_content"),
        knowledge_policy="frozen_evidence_only",
        input_payload={"runtime_config_snapshot": {"creation_mode": "original"}},
        required_skills=(
            "content-title-generator",
            "content-outline-builder",
            "content-body-generator",
            "viral-structure-rewriter",
            "viral-layout-formatter",
            "humanizer-zh",
            "content-human-expression",
        ),
    )
    context = SimpleNamespace(
        reasoning_effort=None,
        _required_skill_closure=list(request.required_skills),
        _prompt_skills=["catalog"],
        _runtime_skill_snapshots=[{"slug": slug} for slug in request.required_skills],
    )
    if (
        request.node_run.node_id == "generate_content"
        and request.input_payload["runtime_config_snapshot"].get("creation_mode", "original") == "original"
    ):
        context._required_skill_closure = [
            slug for slug in context._required_skill_closure if slug not in ORIGINAL_GENERATE_CONTENT_DROP_SKILLS
        ]
    assert "viral-structure-rewriter" not in context._required_skill_closure
    assert "content-outline-builder" not in context._required_skill_closure
    assert "viral-layout-formatter" in context._required_skill_closure
    assert "humanizer-zh" in context._required_skill_closure
    assert "content-human-expression" in context._required_skill_closure
    assert "content-body-generator" in context._required_skill_closure
    assert "content-title-generator" in context._required_skill_closure


@pytest.mark.asyncio
async def test_graph_preserves_prepared_generation_scope(monkeypatch):
    from unittest.mock import AsyncMock
    import yuxi.agents.buildin.chatbot.graph as graph_module
    import yuxi.content.model.contracts as contracts

    context = SimpleNamespace(
        _content_runtime_prepared=True,
        _content_max_model_calls=2,
        _content_node_result_collector=object(),
        _required_skill_closure=["content-body-generator"],
        _prompt_skills=[],
        model="provider:model",
        reasoning_effort="medium",
    )
    prepare = AsyncMock(side_effect=AssertionError("must not expand frozen scope again"))
    monkeypatch.setattr(graph_module, "prepare_agent_runtime_context", prepare)
    monkeypatch.setattr(graph_module, "resolve_chat_model_spec", lambda model: model)
    monkeypatch.setattr(graph_module, "load_chat_model", lambda **kwargs: kwargs)
    monkeypatch.setattr(graph_module, "resolve_configured_runtime_tools", AsyncMock(return_value=[]))
    monkeypatch.setattr(graph_module, "_build_middlewares", AsyncMock(return_value=[]))
    monkeypatch.setattr(graph_module, "build_prompt_with_context", lambda ctx: "test")
    monkeypatch.setattr(contracts, "build_content_result_tool", lambda collector: "result-tool")
    monkeypatch.setattr(graph_module, "create_agent", lambda **kwargs: kwargs)
    agent = graph_module.ChatbotAgent.__new__(graph_module.ChatbotAgent)
    agent._get_checkpointer = AsyncMock(return_value=None)
    graph = await agent.get_graph(context=context)
    prepare.assert_not_awaited()
    assert context._required_skill_closure == ["content-body-generator"]
    assert context._prompt_skills == []
    assert graph["model"]["max_retries"] == 0
    assert graph["model"]["streaming"] is True


@pytest.mark.parametrize("mode", ["original", "viral_rewrite"])
def test_layout_instructions_project_mode_and_record_applied_hash(mode):
    from pathlib import Path
    from yuxi.agents.middlewares.skills import SkillsMiddleware
    from yuxi.agents.skills.buildin import BUILTIN_SKILLS

    spec = next(s for s in BUILTIN_SKILLS if s.slug == "viral-layout-formatter")
    instructions = (Path(spec.source_dir) / "SKILL.md").read_text()
    context = SimpleNamespace(
        _content_node_id="generate_content",
        _content_max_model_calls=2,
        _content_node_input=SimpleNamespace(payload={"runtime_config_snapshot": {"creation_mode": mode}}),
        _runtime_skill_metadata={
            spec.slug: {"instructions": instructions, "version": spec.version, "content_hash": "full"}
        },
    )
    text = SkillsMiddleware()._build_required_skills_section([spec.slug], context)
    if mode == "original":
        assert "## 原创模式" in text
        assert "## 一、读取参考排版" not in text
        assert "排版映射表" not in text
    else:
        assert "## 原创模式" not in text
        assert "## 一、读取参考排版" in text
    applied = context._content_applied_skill_instructions[spec.slug]
    assert applied["instruction_chars"] < len(instructions)
    assert len(applied["applied_hash"]) == 64


@pytest.mark.asyncio
async def test_parent_cancel_stops_delegated_invocation():
    import asyncio
    from yuxi.services.agent_delegation_service import AgentDelegationService

    started = asyncio.Event()
    stopped = asyncio.Event()

    class Graph:
        async def ainvoke(self, *args, **kwargs):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

    invocation = asyncio.create_task(
        AgentDelegationService._invoke_graph(
            Graph(),
            SimpleNamespace(thread_id="test", uid="test"),
            SimpleNamespace(prompt="test", max_execution_steps=2, cancel_event=None, timeout_seconds=30),
        )
    )
    await started.wait()
    invocation.cancel()
    with pytest.raises(asyncio.CancelledError):
        await invocation
    assert stopped.is_set()


def test_fact_aliases_keep_budget_meaning_and_exclude_control_numbers():
    brief = {
        "form_values": {"area": "89㎡", "budget": "预算18万元", "channel_profile_version_id": "channel-9999"},
        "business_variables": {"area": "89㎡", "quantity": "89㎡", "budget": "预算18万元", "price": "预算18万元"},
    }
    facts = {key: (value, codes) for key, value, codes in canonical_brief_facts(brief)}
    assert facts["budget"] == ("预算18万元", ("budget", "price"))
    assert facts["area"] == ("89㎡", ("area", "quantity"))
    assert "price" not in facts and "quantity" not in facts
    assert "channel_profile_version_id" not in facts
    assert "9999" not in str(facts["number"])


def test_generated_evidence_feedback_reports_all_occurrences_and_allowed_ids():
    from yuxi.content.model.contracts import (
        ContractDomainContext,
        ContractDomainValidationError,
        validate_content_node_result,
    )

    context = ContractDomainContext(
        allowed_evidence_by_usage={"title": frozenset({"ev-real"}), "body": frozenset({"ev-real"})},
    )
    payload = {
        "title": {"text": "标题", "formula_code": "T01", "evidence_ids": ["ev-short"]},
        "outline": {
            "body_formula_code": "C02",
            "sections": [
                {"section_id": "s1", "goal": "开篇", "evidence_ids": ["ev-short"]},
                {"section_id": "s2", "goal": "结果", "evidence_ids": ["ev-short"]},
            ],
        },
        "draft": {
            "body": "正文",
            "topics": [],
            "body_formula_code": "C02",
            "paragraph_evidence": [{"paragraph_id": "p1", "evidence_ids": ["ev-short"]}],
        },
    }
    with pytest.raises(ContractDomainValidationError) as error:
        validate_content_node_result("GeneratedContentResultV1", payload, context)
    assert error.value.code == "evidence_forbidden"
    for path in ("title.evidence_ids", "outline.sections.0", "outline.sections.1", "draft.paragraph_evidence.0"):
        assert path in str(error.value)
    assert "ev-real" in str(error.value)


def test_generated_near_miss_evidence_ids_are_repaired_without_second_call():
    from yuxi.content.model.contracts import ContractDomainContext, validate_content_node_result

    real_title = "ev_2408ea1a8f9963c6"
    real_body = "ev_b799852b085f6696"
    context = ContractDomainContext(
        locked_title_formula_code="T01",
        locked_body_formula_code="C02",
        skip_formula_lexicon_usage=True,
        allowed_evidence_by_usage={"title": frozenset({real_title}), "body": frozenset({real_body})},
    )
    payload = {
        "title": {"text": "标题", "formula_code": "T01", "evidence_ids": ["ev_240ea1a8f9963c6"]},
        "outline": {
            "body_formula_code": "C02",
            "sections": [{"section_id": "s1", "goal": "开篇", "evidence_ids": ["ev_b799b852b085f6696"]}],
        },
        "draft": {
            "body": "正文",
            "topics": [],
            "body_formula_code": "C02",
            "paragraph_evidence": [{"paragraph_id": "p1", "evidence_ids": ["ev_b799b852b085f6696"]}],
        },
    }
    result = validate_content_node_result("GeneratedContentResultV1", payload, context)
    assert result.title.evidence_ids == [real_title]
    assert result.outline.sections[0].evidence_ids == [real_body]
    assert result.draft.paragraph_evidence[0].evidence_ids == [real_body]


def test_generated_cite_aliases_are_mapped_without_second_call():
    from yuxi.content.model.contracts.content_nodes import (
        ContractDomainContext,
        build_evidence_cite_aliases,
        validate_content_node_result,
    )

    real_title = "ev_2408ea1a8f9963c6"
    real_body = "ev_b799852b085f6696"
    aliases = build_evidence_cite_aliases(
        [
            {"id": real_title, "allowed_usage": ["title"], "verified_status": "user_confirmed"},
            {"id": real_body, "allowed_usage": ["body"], "verified_status": "user_confirmed"},
        ]
    )
    assert aliases == {"E01": real_title, "E02": real_body}
    context = ContractDomainContext(
        locked_title_formula_code="T01",
        locked_body_formula_code="C02",
        skip_formula_lexicon_usage=True,
        allowed_evidence_by_usage={"title": frozenset({real_title}), "body": frozenset({real_body})},
        evidence_cite_aliases=aliases,
    )
    payload = {
        "title": {"text": "标题", "formula_code": "T01", "evidence_ids": ["E01"]},
        "outline": {
            "body_formula_code": "C02",
            "sections": [{"section_id": "s1", "goal": "开篇", "evidence_ids": ["e2"]}],
        },
        "draft": {
            "body": "正文",
            "topics": [],
            "body_formula_code": "C02",
            "paragraph_evidence": [{"paragraph_id": "p1", "evidence_ids": ["E02"]}],
        },
    }
    result = validate_content_node_result("GeneratedContentResultV1", payload, context)
    assert result.title.evidence_ids == [real_title]
    assert result.outline.sections[0].evidence_ids == [real_body]
    assert result.draft.paragraph_evidence[0].evidence_ids == [real_body]


def test_generation_projection_hides_real_evidence_ids_behind_cite_aliases():
    from yuxi.content.model.contracts.content_nodes import build_evidence_cite_aliases

    real_title = "ev_2408ea1a8f9963c6"
    real_body = "ev_b799852b085f6696"
    payload = {
        "strategy_snapshot": {"snapshot_hash": "s" * 64, "body_formula": {"code": "C03"}},
        "content_brief": {"business_variables": {}},
        "evidence_bundle": {
            "bundle_hash": "frozen",
            "items": [
                {
                    "id": real_title,
                    "value": "洋湖天旭 110-130㎡",
                    "allowed_usage": ["title", "body"],
                    "verified_status": "user_confirmed",
                },
                {
                    "id": real_body,
                    "value": "鸿扬家装施工",
                    "allowed_usage": ["body"],
                    "verified_status": "user_confirmed",
                },
            ],
        },
        "runtime_config_snapshot": {"creation_mode": "original"},
        "formula_lexicon_bundle": {},
        "channel_profile": {},
        "persona_profile": {},
    }
    result = project_generation_input(payload)
    items = result["evidence_bundle"]["items"]
    assert [item["id"] for item in items] == ["E01", "E02"]
    assert real_title not in json.dumps(result, ensure_ascii=False)
    assert real_body not in json.dumps(result, ensure_ascii=False)
    assert build_evidence_cite_aliases(payload["evidence_bundle"]["items"]) == {
        "E01": real_title,
        "E02": real_body,
    }


def test_ambiguous_or_unrelated_evidence_ids_stay_forbidden():
    from yuxi.content.model.contracts import (
        ContractDomainContext,
        ContractDomainValidationError,
        validate_content_node_result,
    )

    context = ContractDomainContext(
        locked_title_formula_code="T01",
        locked_body_formula_code="C02",
        skip_formula_lexicon_usage=True,
        allowed_evidence_by_usage={
            "title": frozenset({"ev_aaa", "ev_aba"}),
            "body": frozenset({"ev-real"}),
        },
    )
    payload = {
        "title": {"text": "标题", "formula_code": "T01", "evidence_ids": ["ev_aca"]},
        "outline": {
            "body_formula_code": "C02",
            "sections": [{"section_id": "s1", "goal": "开篇", "evidence_ids": ["ev-other"]}],
        },
        "draft": {
            "body": "正文",
            "topics": [],
            "body_formula_code": "C02",
            "paragraph_evidence": [{"paragraph_id": "p1", "evidence_ids": ["ev-other"]}],
        },
    }
    with pytest.raises(ContractDomainValidationError) as error:
        validate_content_node_result("GeneratedContentResultV1", payload, context)
    assert error.value.code == "evidence_forbidden"
    assert "ev_aca" in str(error.value)
    assert "ev-other" in str(error.value)


@pytest.mark.parametrize("text,blocked", [("第一次刷到，第一阶段先看预算", False), ("全国第一，行业第一", True)])
def test_ordinal_is_not_mistaken_for_ranking_claim(text, blocked):
    from yuxi.content.validators import validate_content

    report = validate_content(
        title="案例",
        body=text,
        topics=[],
        brief={},
        evidence_bundle={"items": []},
        strategy={"methods": ["M01"], "title_formula_code": "T01", "body_formula_code": "C02"},
    )
    assert any(c["code"] == "CONTENT_HIGH_RISK_CLAIM" for c in report["checks"]) is blocked


@pytest.mark.parametrize("price", ["预算18万元", "成交18万元"])
def test_separately_entered_price_is_not_merged_with_budget(price):
    facts = {
        key: value
        for key, value, _ in canonical_brief_facts(
            {
                "form_values": {"budget": "预算18万元", "price": price},
            }
        )
    }
    assert facts["price"] == price
    assert facts["budget"] == "预算18万元"


def test_generation_projection_keeps_price_sources_rules_and_revision_without_mutation():
    payload = {
        "strategy_snapshot": {
            "snapshot_hash": "s" * 64,
            "decision": {"scores": [1, 2]},
            "body_formula": {"full_rules": "不能改动"},
        },
        "content_brief": {
            "business_variables": {"budget": "18万", "mp_content_type_id": "a" * 36},
            "form_values": {"budget": "18万", "mp_service_entry": "装修家居"},
            "visual_material": {"template": "large"},
            "required_terms": [],
            "attachments": [],
        },
        "evidence_bundle": {
            "bundle_hash": "frozen",
            "items": [
                {
                    "id": "price-1",
                    "value": "标准单价100元/㎡，含基层",
                    "source_id": "报价表-2",
                    "source_hash": "h" * 64,
                    "created_at": "yesterday",
                    "source_version": "1",
                    "allowed_usage": ["body"],
                    "verified_status": "user_confirmed",
                    "risk_level": "high",
                    "metadata": {"price_basis": "standard_unit_price", "scope": "不含主材"},
                },
                {
                    "id": "price-dup",
                    "value": "标准单价100元/㎡，含基层",
                    "source_id": "报价表-2b",
                    "allowed_usage": ["title", "body"],
                    "verified_status": "user_confirmed",
                    "risk_level": "high",
                    "variable_codes": ["price"],
                },
            ],
        },
        "runtime_config_snapshot": {
            "creation_mode": "original",
            "visual_material": {},
            "selection_policy_snapshot": {},
        },
        "formula_lexicon_bundle": {
            "body": [
                {
                    "chunks": ["短词条", "x" * 900, "保留", "第4段", "第5段应丢弃"],
                }
            ]
        },
        "channel_profile": {"emoji_allowed": False},
        "persona_profile": {},
        "content_draft": {"body": "原稿"},
        "validation_report": {"status": "blocked"},
    }
    before = deepcopy(payload)
    result = project_generation_input(payload)
    assert payload == before
    assert "decision" not in result["strategy_snapshot"]
    assert "source_content" not in result["strategy_snapshot"]["body_formula"]
    assert "full_rules" not in result["strategy_snapshot"]["body_formula"]
    assert result["runtime_config_snapshot"] == {"creation_mode": "original"}
    assert result["content_draft"] == payload["content_draft"]
    assert "form_values" not in result["content_brief"]
    assert "mp_content_type_id" not in result["content_brief"]["business_variables"]
    evidence_items = result["evidence_bundle"]["items"]
    assert len(evidence_items) == 1
    evidence = evidence_items[0]
    assert evidence["id"] == "E01"
    assert set(evidence["allowed_usage"]) == {"body", "title"}
    assert evidence["variable_codes"] == ["price"]
    assert evidence["value"] == payload["evidence_bundle"]["items"][0]["value"]
    assert "source_hash" not in evidence
    assert result["evidence_cite_index"] is None
    chunks = result["formula_lexicon_bundle"]["body"][0]["chunks"]
    assert chunks[0] == "短词条"
    assert len(chunks) == 1
    assert chunks[0] == "短词条"


def test_generation_projection_compacts_forbidden_replacement_map():
    long_map = [
        {"problem_term": f"问题词{i}", "alternatives": [f"替代表达{i}", f"备选{i}", f"多余{i}", f"再多{i}"]}
        for i in range(80)
    ]
    serialized = "报价" * 200 + "私信" * 200
    payload = {
        "strategy_snapshot": {
            "snapshot_hash": "s" * 64,
            "body_formula": {
                "code": "C03",
                "name": "干货",
                "source_content": {"huge": "x" * 500},
                "body_calling": {
                    "formula_name": "干货",
                    "sections": [
                        {"id": "a", "name": "开篇", "instruction": "讲工艺", "fill_rule": "用证据", "lexicon_calls": []}
                    ],
                    "variants": [],
                },
            },
            "creation_method_definitions": [
                {"code": "M03", "name": "价值法", "sentence_patterns": ["a", "b", "c", "d"], "principle": "p"}
            ],
        },
        "content_brief": {"business_variables": {}},
        "evidence_bundle": {
            "bundle_hash": "frozen",
            "items": [
                {
                    "id": "ev-map-list",
                    "value": long_map,
                    "source_id": "forbidden-kb",
                    "allowed_usage": ["title", "body"],
                    "verified_status": "user_confirmed",
                    "risk_level": "sensitive",
                    "metadata": {"material_type": "platform_rule", "rule_kind": "forbidden_replacement_map"},
                },
                {
                    "id": "ev-map-str",
                    "value": serialized,
                    "source_id": "forbidden-kb-2",
                    "allowed_usage": ["title", "body"],
                    "verified_status": "user_confirmed",
                    "risk_level": "sensitive",
                    "metadata": {"material_type": "platform_rule", "rule_kind": "forbidden_replacement_map"},
                },
                {
                    "id": "ev-normal",
                    "value": "y" * 500,
                    "source_id": "brand",
                    "allowed_usage": ["body"],
                    "verified_status": "user_confirmed",
                    "risk_level": "normal",
                    "metadata": {"material_type": "brand"},
                },
            ],
        },
        "runtime_config_snapshot": {"creation_mode": "original"},
        "formula_lexicon_bundle": {},
        "channel_profile": {"emoji_allowed": True, "connector_config_ref": "drop-me"},
        "persona_profile": {"name": "工长", "extra": "drop"},
    }
    result = project_generation_input(payload)
    items = {item["id"]: item for item in result["evidence_bundle"]["items"]}
    assert set(items) == {"E01", "E02", "E03"}
    assert len(items["E01"]["value"]) == 10
    assert items["E01"]["value"][0] == {
        "problem_term": "问题词0",
        "alternatives": ["替代表达0"],
    }
    assert isinstance(items["E02"]["value"], str)
    assert len(items["E02"]["value"]) <= 4000
    assert items["E03"]["value"].endswith("…")
    assert len(items["E03"]["value"]) == 36
    body = result["strategy_snapshot"]["body_formula"]
    assert body["code"] == "C03"
    assert "source_content" not in body
    assert body["body_calling"]["sections"][0]["id"] == "a"
    assert len(result["strategy_snapshot"]["creation_method_definitions"][0]["sentence_patterns"]) == 1
    assert result["channel_profile"] == {"emoji_allowed": True}
    assert result["persona_profile"] == {"name": "工长"}
    assert result["evidence_cite_index"] is None
    assert "source_id" not in items["E03"]
    assert items["E01"]["metadata"]["material_type"] == "platform_rule"
    assert set(items["E03"]["allowed_usage"]) == {"body"}
    assert len(json.dumps(result, ensure_ascii=False, separators=(",", ":"))) <= 4000


def test_generation_projection_caps_prompt_under_five_thousand_chars():
    payload = {
        "strategy_snapshot": {
            "snapshot_hash": "s" * 64,
            "body_formula": {
                "code": "C03",
                "lexicon_codes": ["body.industry_suspense"],
                "structure_schema": [{"id": f"s{i}", "name": "段落说明很长" * 8} for i in range(12)],
                "body_calling": {
                    "lexicon_calls": ["body.industry_suspense", "body.professional_answer"],
                    "sections": [
                        {"id": "a", "name": "开篇", "instruction": "讲工艺" * 40, "fill_rule": "用证据" * 20}
                    ],
                },
            },
            "title_formula": {
                "code": "T01",
                "lexicon_codes": ["title.positioning", "title.question", "title.beneficial_result"],
                "variable_schema": [{"id": f"v{i}", "name": "槽位"} for i in range(12)],
            },
            "creation_method_definitions": [
                {"code": "M01", "name": "价值法", "sentence_patterns": ["a", "b", "c"], "principle": "p" * 80}
            ],
        },
        "content_brief": {"business_variables": {"writing_instruction": "写" * 400, "community_name": "洋湖"}},
        "evidence_bundle": {
            "bundle_hash": "frozen",
            "items": [
                {
                    "id": f"ev-{i}",
                    "value": f"事实{i}" + "详" * 120,
                    "allowed_usage": ["title", "body"],
                    "verified_status": "user_confirmed",
                    "metadata": {"material_type": "business_fact"},
                }
                for i in range(40)
            ],
        },
        "runtime_config_snapshot": {"creation_mode": "original"},
        "formula_lexicon_bundle": {
            "title": [
                {"code": "title.positioning", "name": "定位", "chunks": ["同城装修" * 40]},
                {"code": "title.question", "name": "问题", "chunks": ["怎么避坑" * 40]},
                {"code": "title.beneficial_result", "name": "利好", "chunks": ["少花冤枉钱" * 40]},
            ],
            "body": [
                {"code": "body.industry_suspense", "name": "悬念", "chunks": ["词" * 180] * 4},
                {"code": "body.professional_answer", "name": "正解", "chunks": ["标准" * 80]},
            ],
        },
        "channel_profile": {"emoji_allowed": True},
        "persona_profile": {},
    }
    result = project_generation_input(payload)
    assert len(json.dumps(result, ensure_ascii=False, separators=(",", ":"))) <= 4000
    assert len(result["evidence_bundle"]["items"]) <= 10
    title_codes = {item["code"] for item in result["formula_lexicon_bundle"].get("title") or []}
    assert {"title.positioning", "title.question", "title.beneficial_result"} <= title_codes
    assert result["strategy_snapshot"]["title_formula"]["lexicon_codes"] == [
        "title.positioning",
        "title.question",
        "title.beneficial_result",
    ]


def test_review_notes_generation_projection_caps_wrapped_prompt_under_five_thousand_chars():
    from yuxi.content.control.workflow.agent_node import REVIEW_NOTES_GENERATE_PROHIBITED_ACTIONS
    from yuxi.content.control.workflow.generation_input import attach_review_notes_style_excerpts

    payload = {
        "strategy_snapshot": {
            "snapshot_hash": "s" * 64,
            "body_formula": {
                "code": "C03",
                "structure_schema": [{"id": f"s{i}", "name": "段落说明很长" * 8} for i in range(12)],
                "body_calling": {
                    "sections": [
                        {"id": "a", "name": "开篇", "instruction": "讲工艺" * 40, "fill_rule": "用证据" * 20}
                    ]
                },
            },
            "title_formula": {"code": "T01", "variable_schema": [{"id": f"v{i}", "name": "槽位"} for i in range(12)]},
            "creation_method_definitions": [
                {"code": "M01", "name": "价值法", "sentence_patterns": ["a", "b", "c"], "principle": "p" * 80}
            ],
        },
        "content_brief": {
            "form_values": {"mp_service_entry": "好评笔记", "设计师": "林工"},
            "business_variables": {
                "mp_service_entry": "好评笔记",
                "writing_instruction": "写" * 400,
                "设计师": "林工",
                "项目经理": "陈经理",
                "所属店面": "芙蓉店",
                "project_type": "业主好评笔记",
                "pain": "痛点" * 40,
                "advantage": "优势" * 40,
                "craft_and_materials": "材料" * 40,
            },
        },
        "evidence_bundle": {
            "bundle_hash": "frozen",
            "items": [
                {
                    "id": f"ev-{i}",
                    "value": f"事实{i}" + "详" * 120,
                    "allowed_usage": ["title", "body"],
                    "verified_status": "user_confirmed",
                    "metadata": {"material_type": "business_fact"},
                }
                for i in range(40)
            ],
        },
        "runtime_config_snapshot": {"creation_mode": "original"},
        "formula_lexicon_bundle": {"body": [{"chunks": ["词" * 180] * 4}]},
        "channel_profile": {"emoji_allowed": True, "title_constraints": {"min_length": 6, "max_length": 20}},
        "persona_profile": {"name": "业主", "extra": "drop"},
    }
    attach_review_notes_style_excerpts(payload, ["样例甲" * 80, "样例乙" * 80, "多余"])
    result = project_generation_input(payload)
    assert result["formula_lexicon_bundle"] == {}
    assert result["strategy_snapshot"]["body_formula"] == {"code": "C03"}
    assert "project_type" not in result["content_brief"]["business_variables"]
    assert result["content_brief"]["business_variables"]["mp_service_entry"] == "好评笔记"
    excerpts = result["content_brief"]["style_excerpts"]
    assert len(excerpts) == 2
    assert all(len(item) <= 220 for item in excerpts)
    assert len(result["evidence_bundle"]["items"]) <= 5
    prompt_chars = len(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    assert prompt_chars <= 2800
    wrapped = json.dumps(
        {
            "payload": result,
            "duty": (
                "执行内容工作流节点 generate_content：模仿 payload.content_brief.style_excerpts 的语气结构，"
                "直接 submit_content_node_result"
            ),
            "ban": list(REVIEW_NOTES_GENERATE_PROHIBITED_ACTIONS),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    assert len(wrapped) <= 4000


@pytest.mark.asyncio
async def test_review_notes_prefetch_keeps_two_style_chunks():
    from yuxi.content.control.workflow.generation_input import attach_review_notes_style_excerpts
    from yuxi.services.agent_delegation_service import AgentDelegationService

    async def retriever(query_text: str, **kwargs):
        assert "业主第一人称好评" in query_text
        assert "芙蓉店" in query_text
        return {"results": [{"content": "样例甲" * 50}, {"content": "样例乙" * 50}, {"content": "多余"}]}

    context = SimpleNamespace(
        knowledges=["kb-review"],
        _required_skill_tools=["query_kb", "submit_content_node_result"],
        _visible_knowledge_bases=[
            {"kb_id": "kb-review", "name": "好评知识库", "retriever": retriever},
        ],
    )
    payload = {
        "content_brief": {
            "business_variables": {"设计师": "林工", "所属店面": "芙蓉店", "mp_service_entry": "好评笔记"}
        }
    }
    excerpts = await AgentDelegationService._prefetch_review_notes_style_excerpts(context, payload)
    attach_review_notes_style_excerpts(payload, excerpts)
    assert payload["content_brief"]["style_excerpts"] == ["样例甲" * 50, "样例乙" * 50]
    context.knowledges = []
    AgentDelegationService._apply_knowledge_tool_scope(context)
    assert context._required_skill_tools == ["submit_content_node_result"]


def test_visual_plan_projection_drops_duplicate_evidence_and_heavy_runtime():
    import json

    payload = {
        "selected_title": {"text": "洋湖天旭工艺", "evidence_ids": ["ev-1"], "debug": "drop-me"},
        "content_draft": {
            "body": "正文" * 400,
            "lexicon_usage": {"body": ["x"]},
            "paragraph_evidence": [{"evidence_ids": ["ev-1"]}],
        },
        "strategy_snapshot": {
            "snapshot_hash": "s" * 64,
            "decision": {"scores": [1]},
            "body_formula": {"code": "C03", "source_content": {"huge": "x" * 200}, "body_calling": {"sections": [{}]}},
            "title_formula": {"code": "T01", "reference_examples": ["a", "b"]},
            "creation_method_definitions": [{"principle": "x" * 80}],
        },
        "evidence_bundle": {
            "bundle_hash": "frozen",
            "items": [
                {
                    "id": "ev-1",
                    "value": "90-110㎡",
                    "source_hash": "h" * 64,
                    "allowed_usage": ["title"],
                    "verified_status": "user_confirmed",
                },
                {
                    "id": "ev-2",
                    "value": "90-110㎡",
                    "allowed_usage": ["body"],
                    "verified_status": "user_confirmed",
                },
                {
                    "id": "ev-body-only",
                    "value": "长篇工艺说明" * 40,
                    "allowed_usage": ["body"],
                    "verified_status": "user_confirmed",
                    "metadata": {"material_type": "knowledge"},
                },
            ],
        },
        "media_evidence_items": [
            {
                "id": "asset-1",
                "selected_for_cover": True,
                "extracted_text": "很长的 OCR " * 80,
                "display_name": "长沙图",
                "object_uri": "oss://drop",
            },
            {
                "id": "asset-2",
                "selected_for_cover": False,
                "extracted_text": "配图",
            },
        ],
        "artifact_version": {"id": "av-1", "payload": {"huge": True}},
        "channel_profile": {
            "emoji_allowed": True,
            "connector_config_ref": "drop",
            "title_constraints": {"max_length": 20},
            "body_constraints": {"max_length": 1000},
        },
        "runtime_config_snapshot": {
            "creation_mode": "original",
            "visual_material": {
                "image_asset_id": "asset-1",
                "hycanvas_fillable_fields": [
                    {
                        "key": "t1",
                        "label": "主标题",
                        "semanticRole": "title",
                        "kind": "text",
                        "nodeId": "node-1",
                        "constraints": {"maxChars": 22, "layoutMeasured": True},
                        "typography": {
                            "runs": [{"fontFamily": "SourceHanSans", "fontSize": 64, "fontWeight": 700}],
                            "paragraphs": [{"style": {"huge": "x" * 400}, "runs": [{"style": {}}]}],
                            "box": {"x": 0, "y": 0, "width": 1080},
                        },
                    }
                ],
                "unused_blob": "x" * 500,
            },
        },
    }
    result = project_visual_plan_input(payload)
    assert result["selected_title"] == {"text": "洋湖天旭工艺"}
    assert set(result["content_draft"]) == {"body"}
    assert len(result["content_draft"]["body"]) <= 100
    assert result["strategy_snapshot"] == {}
    assert [item["id"] for item in result["evidence_bundle"]["items"]] == ["ev-1"]
    assert "allowed_usage" not in result["evidence_bundle"]["items"][0]
    assert "variable_codes" not in result["evidence_bundle"]["items"][0]
    assert result["media_evidence_items"] == [{"id": "asset-1", "selected_for_cover": True}]
    assert result["artifact_version"] == {"id": "av-1"}
    visual = result["runtime_config_snapshot"]["visual_material"]
    assert visual["image_asset_id"] == "asset-1"
    assert visual["hycanvas_fillable_fields"] == [
        {
            "key": "t1",
            "label": "主标题",
            "semanticRole": "title",
            "constraints": {"maxChars": 22},
        }
    ]
    assert "unused_blob" not in visual
    assert "kind" not in visual["hycanvas_fillable_fields"][0]
    assert "typography" not in visual["hycanvas_fillable_fields"][0]
    assert result["runtime_config_snapshot"]["canvas"] == {
        "width": 1080,
        "height": 1440,
        "safe_area": {"top": 20, "right": 20, "bottom": 20, "left": 20},
    }
    assert result["channel_profile"] == {}
    assert len(json.dumps(result, ensure_ascii=False, separators=(",", ":"))) <= 1800


def test_visual_text_is_clamped_and_uniquified_for_first_pass():
    from yuxi.content.control.visual_template_fields import clamp_visual_text, uniquify_visual_template_fields

    assert clamp_visual_text("超过七个字符的封面标题", 7) == "超过七个字符的"
    fields = uniquify_visual_template_fields(
        {"主标题": "收纳动线焕新", "强调标题": "收纳 动线焕新！"},
        limits={"主标题": {"maxChars": 12}, "强调标题": {"maxChars": 12}},
        extra_texts=["复尺后规划"],
    )
    assert fields["主标题"] == "收纳动线焕新"
    assert fields["强调标题"] == "复尺后规划"


def test_visual_text_max_char_floor_raises_cover_copy_limits():
    from yuxi.content.control.visual_template_fields import (
        apply_visual_text_max_char_floor,
        is_ordinal_badge_template_field,
        resolved_visual_text_max_chars,
        resolve_visual_cover_title,
    )

    assert apply_visual_text_max_char_floor("title", 4) == 12
    assert apply_visual_text_max_char_floor("body_excerpt", 6) == 24
    assert apply_visual_text_max_char_floor("title", 20) == 20
    assert apply_visual_text_max_char_floor("label", 4) == 4
    assert resolved_visual_text_max_chars("title", {"maxChars": 8, "layoutMeasured": True}) == 8
    assert resolved_visual_text_max_chars("title", {"maxChars": 8}) == 8
    assert is_ordinal_badge_template_field(
        {"key": "field_2", "label": "01", "semanticRole": "title", "constraints": {"maxChars": 1}}
    )
    assert is_ordinal_badge_template_field(
        {"key": "field_x", "label": "副标题", "semanticRole": "title", "constraints": {"maxChars": 2}}
    )
    assert not is_ordinal_badge_template_field(
        {"key": "field_1", "label": "标题醒目", "semanticRole": "title", "constraints": {"maxChars": 22}}
    )
    # 序号角标不得把整页 title 上限压到 1。
    narrative = [
        {"key": "field_1", "label": "主标题", "semanticRole": "title", "constraints": {"maxChars": 22}},
        {"key": "field_2", "label": "01", "semanticRole": "title", "constraints": {"maxChars": 1}},
        {"key": "field_3", "label": "强调", "semanticRole": "title", "constraints": {"maxChars": 12}},
    ]
    limits: dict[str, int] = {}
    allowed: dict[str, dict[str, int]] = {}
    for field in narrative:
        if is_ordinal_badge_template_field(field):
            continue
        role = field["semanticRole"]
        max_chars = resolved_visual_text_max_chars(role, field["constraints"])
        allowed[field["key"]] = {"maxChars": max_chars}
        limits[role] = min(limits.get(role, max_chars), max_chars)
    assert "field_2" not in allowed
    assert limits["title"] == 12
    assert (
        resolve_visual_cover_title(
            visual_text=[],
            template_fields={"field_1": "后悔没早知道！洋湖天旭装修"},
            declarations=[{"key": "field_1", "semanticRole": "title"}],
        )
        == "后悔没早知道！洋湖天旭装修"
    )
    assert resolve_visual_cover_title(visual_text=["封面标题"], template_fields={}) == "封面标题"
    assert (
        resolve_visual_cover_title(
            visual_text=["1"],
            template_fields={
                "field_1": "旧房改造130-150㎡预算避坑",
                "field_2": "1",
            },
            declarations=[
                {"key": "field_1", "semanticRole": "title"},
                {"key": "field_2", "semanticRole": "title"},
            ],
        )
        == "旧房改造130-150㎡预算避坑"
    )


@pytest.mark.asyncio
async def test_idle_timeout_does_not_consume_correction_budget_and_preserves_cancel():
    import asyncio
    from langchain.agents.middleware import ModelResponse
    from langchain_core.messages import AIMessage

    context = SimpleNamespace(_content_max_model_calls=2, _content_node_token_budget=12000)

    class Request(SimpleNamespace):
        def override(self, **kwargs):
            return Request(**{**vars(self), **kwargs})

    request = Request(runtime=SimpleNamespace(context=context), model_settings={}, messages=[])
    middleware = ModelCallTimeoutMiddleware(0.01)
    calls = []

    async def slow(req):
        calls.append(req.model_settings["max_tokens"])
        await asyncio.sleep(1)

    async def good(req):
        calls.append(req.model_settings["max_tokens"])
        return ModelResponse(result=[AIMessage(content="ok")])

    with pytest.raises(TimeoutError):
        await middleware.awrap_model_call(request, slow)
    await middleware.awrap_model_call(request, good)
    await middleware.awrap_model_call(request, good)
    with pytest.raises(ModelExecutionBudgetExceeded):
        await middleware.awrap_model_call(request, good)
    assert calls == [6000, 6000, 6000]

    context._content_model_calls = 0

    async def cancelled(req):
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await middleware.awrap_model_call(request, cancelled)
    assert context._content_model_calls == 1


@pytest.mark.asyncio
async def test_idle_timeout_does_not_consume_one_shot_submit_budget():
    import asyncio
    from langchain.agents.middleware import ModelResponse
    from langchain_core.messages import AIMessage

    context = SimpleNamespace(_content_max_model_calls=1, _content_node_token_budget=8000)

    class Request(SimpleNamespace):
        def override(self, **kwargs):
            return Request(**{**vars(self), **kwargs})

    request = Request(runtime=SimpleNamespace(context=context), model_settings={}, messages=[])
    middleware = ModelCallTimeoutMiddleware(0.01)

    async def slow(req):
        await asyncio.sleep(1)

    async def good(req):
        return ModelResponse(result=[AIMessage(content="ok")])

    with pytest.raises(TimeoutError):
        await middleware.awrap_model_call(request, slow)
    await middleware.awrap_model_call(request, good)
    with pytest.raises(ModelExecutionBudgetExceeded):
        await middleware.awrap_model_call(request, good)
