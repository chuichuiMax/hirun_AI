from copy import deepcopy
from types import SimpleNamespace

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
    assert context.model_retry_times == 1
    assert context._content_max_model_calls == 2
    assert CONTENT_NODE_EXECUTION_LIMITS[node_id][0] >= context._content_max_model_calls * context.model_call_timeout_seconds + 3 + 15
    context.reasoning_effort = "medium"
    AgentDelegationService._apply_node_constraints(context, request)
    assert context.reasoning_effort == "low"


def test_generate_content_allows_three_model_calls_with_matching_watchdog():
    from yuxi.services.agent_delegation_service import AgentDelegationService, CONTENT_NODE_EXECUTION_LIMITS

    request = SimpleNamespace(
        node_run=SimpleNamespace(node_id="generate_content"),
        knowledge_policy="frozen_evidence_only",
    )
    context = SimpleNamespace(reasoning_effort=None)
    AgentDelegationService._apply_node_constraints(context, request)
    assert context.reasoning_effort == "low"
    assert context.model_call_timeout_seconds == 180
    assert context._content_max_model_calls == 3
    assert CONTENT_NODE_EXECUTION_LIMITS["generate_content"][0] >= (
        context._content_max_model_calls * context.model_call_timeout_seconds + 3 + 15
    )


def test_plan_visuals_has_execution_budget_for_slow_model_calls():
    from yuxi.services.agent_delegation_service import AgentDelegationService, CONTENT_NODE_EXECUTION_LIMITS

    request = SimpleNamespace(
        node_run=SimpleNamespace(node_id="plan_visuals"),
        knowledge_policy="frozen_evidence_only",
    )
    context = SimpleNamespace(reasoning_effort=None)
    AgentDelegationService._apply_node_constraints(context, request)
    assert context.reasoning_effort == "low"
    assert context.model_call_timeout_seconds == 150
    assert context._content_max_model_calls == 3
    assert CONTENT_NODE_EXECUTION_LIMITS["plan_visuals"][0] >= (
        context._content_max_model_calls * context.model_call_timeout_seconds + 3 + 15
    )


def test_original_generate_content_drops_heavy_layout_skills():
    from yuxi.services.agent_delegation_service import AgentDelegationService

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
    # Simulate the generate_content original narrowing branch used after skill prep.
    if (
        request.node_run.node_id == "generate_content"
        and request.input_payload["runtime_config_snapshot"].get("creation_mode", "original") == "original"
    ):
        drop = {
            "viral-structure-rewriter",
            "humanizer-zh",
            "viral-layout-formatter",
            "content-outline-builder",
            "content-human-expression",
        }
        context._required_skill_closure = [slug for slug in context._required_skill_closure if slug not in drop]
    assert "viral-layout-formatter" not in context._required_skill_closure
    assert "content-outline-builder" not in context._required_skill_closure
    assert "humanizer-zh" not in context._required_skill_closure
    assert "content-human-expression" not in context._required_skill_closure
    assert "content-body-generator" in context._required_skill_closure
    assert "content-title-generator" in context._required_skill_closure
    _ = AgentDelegationService


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
    assert evidence["id"] == "price-1"
    assert set(evidence["allowed_usage"]) == {"body", "title"}
    assert evidence["variable_codes"] == ["price"]
    assert evidence["value"] == payload["evidence_bundle"]["items"][0]["value"]
    assert "source_hash" not in evidence
    cite = result["evidence_cite_index"]
    assert cite[0]["id"] == "price-1"
    assert "title" in cite[0]["allowed_usage"] or "body" in cite[0]["allowed_usage"]
    assert "value_preview" not in cite[0]
    assert "source_id" not in cite[0]
    chunks = result["formula_lexicon_bundle"]["body"][0]["chunks"]
    assert chunks[0] == "短词条"
    assert len(chunks) == 1
    assert chunks[0] == "短词条"


def test_generation_projection_compacts_forbidden_replacement_map():
    long_map = [{"problem_term": f"问题词{i}", "alternatives": [f"替代表达{i}", f"备选{i}", f"多余{i}", f"再多{i}"]} for i in range(80)]
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
                    "sections": [{"id": "a", "name": "开篇", "instruction": "讲工艺", "fill_rule": "用证据", "lexicon_calls": []}],
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
    assert len(items["ev-map-list"]["value"]) == 40
    assert items["ev-map-list"]["value"][0] == {
        "problem_term": "问题词0",
        "alternatives": ["替代表达0", "备选0"],
    }
    assert isinstance(items["ev-map-str"]["value"], str)
    assert len(items["ev-map-str"]["value"]) <= 4000
    assert items["ev-normal"]["value"].endswith("…")
    assert len(items["ev-normal"]["value"]) == 120
    body = result["strategy_snapshot"]["body_formula"]
    assert body["code"] == "C03"
    assert "source_content" not in body
    assert body["body_calling"]["sections"][0]["id"] == "a"
    assert len(result["strategy_snapshot"]["creation_method_definitions"][0]["sentence_patterns"]) == 3
    assert result["channel_profile"] == {"emoji_allowed": True}
    assert result["persona_profile"] == {"name": "工长"}
    cite_by_id = {row["id"]: row for row in result["evidence_cite_index"]}
    assert "value_preview" not in cite_by_id["ev-map-list"]
    assert cite_by_id["ev-map-list"]["material_type"] == "platform_rule"
    assert "value_preview" not in cite_by_id["ev-map-str"]
    assert "value_preview" not in cite_by_id["ev-normal"]
    assert set(cite_by_id["ev-normal"]["allowed_usage"]) == {"body"}


def test_visual_plan_projection_drops_duplicate_evidence_and_heavy_runtime():
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
            "body_formula": {"code": "C03", "source_content": {"huge": "x" * 200}},
            "title_formula": {"code": "T01", "reference_examples": ["a", "b"]},
            "creation_method_definitions": [],
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
            ],
        },
        "media_evidence_items": [
            {
                "id": "asset-1",
                "selected_for_cover": True,
                "extracted_text": "很长的 OCR " * 80,
                "display_name": "长沙图",
            }
        ],
        "artifact_version": {"id": "av-1", "payload": {"huge": True}},
        "channel_profile": {"emoji_allowed": True, "connector_config_ref": "drop"},
        "runtime_config_snapshot": {
            "creation_mode": "original",
            "visual_material": {
                "image_asset_id": "asset-1",
                "hycanvas_fillable_fields": [{"key": "t1", "semanticRole": "title"}],
                "unused_blob": "x" * 500,
            },
        },
    }
    result = project_visual_plan_input(payload)
    assert result["selected_title"] == {"text": "洋湖天旭工艺", "evidence_ids": ["ev-1"]}
    assert "lexicon_usage" not in result["content_draft"]
    assert len(result["content_draft"]["body"]) <= 650
    assert "decision" not in result["strategy_snapshot"]
    assert "source_content" not in result["strategy_snapshot"]["body_formula"]
    assert len(result["evidence_bundle"]["items"]) == 1
    assert set(result["evidence_bundle"]["items"][0]["allowed_usage"]) == {"title", "body"}
    assert result["media_evidence_items"] == [{"id": "asset-1", "selected_for_cover": True}]
    assert result["artifact_version"] == {"id": "av-1"}
    assert result["runtime_config_snapshot"]["visual_material"]["image_asset_id"] == "asset-1"
    assert "unused_blob" not in result["runtime_config_snapshot"]["visual_material"]
    assert result["channel_profile"] == {"emoji_allowed": True}


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
async def test_timeout_and_correction_share_two_calls_and_preserve_cancel():
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
    with pytest.raises(ModelExecutionBudgetExceeded):
        await middleware.awrap_model_call(request, good)
    assert calls == [6000, 6000]

    context._content_model_calls = 0

    async def cancelled(req):
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await middleware.awrap_model_call(request, cancelled)
    assert context._content_model_calls == 1
