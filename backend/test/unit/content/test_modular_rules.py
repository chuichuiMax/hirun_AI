import pytest
from pydantic import ValidationError

from yuxi.content.schemas import ContentTaskCreate
from yuxi.content.v3.modular_rules import (
    GENERATE_ALWAYS_SKILLS,
    VIRAL_BODY_AUTHOR,
    VIRAL_PRICE_AUTHOR,
    VIRAL_TITLE_AUTHOR,
    assemble_required_skills,
    compile_content_rule_bundle,
    has_price_signal,
    resolve_visual_intent,
    revision_skill_slugs,
)
from yuxi.content.v3.workflow import WORKFLOW_V3
from yuxi.content.v3.joint_workflow import PLATFORM_WORKFLOW_V5_ID, WORKFLOW_VIRAL_V5
from yuxi.content.model.workflows.definition import DEFAULT_CONTRACTS, WorkflowCatalog, WorkflowDefinitionPolicy
from yuxi.content.control.workflow.generation_input import project_generation_input
from yuxi.content.control.workflow.revision import resolve_revision_reason


def test_compile_bundle_has_hash_and_eleven_modules():
    bundle = compile_content_rule_bundle(brief={"form_values": {"topic": "旧房翻新"}})
    assert bundle["bundle_version"]
    assert bundle["bundle_hash"]
    assert len(bundle["modules"]) == 11
    assert "旧房翻新" in bundle["topic_candidate_pool"]
    assert all(module["content_hash"] and module["active_rule_ids"] for module in bundle["modules"])


def test_assemble_drops_price_without_quote_and_keeps_it_with_price():
    assert VIRAL_PRICE_AUTHOR not in assemble_required_skills(node_id="generate_content", has_price=False)
    assert assemble_required_skills(node_id="generate_content", has_price=False) == list(GENERATE_ALWAYS_SKILLS)
    assert VIRAL_PRICE_AUTHOR in assemble_required_skills(node_id="generate_content", has_price=True)


def test_title_revision_does_not_load_body_module():
    slugs = assemble_required_skills(node_id="generate_content", block_codes=["TITLE_TOO_LONG"], has_price=True)
    assert VIRAL_TITLE_AUTHOR in slugs
    assert VIRAL_BODY_AUTHOR not in slugs
    assert VIRAL_TITLE_AUTHOR in revision_skill_slugs(["TITLE_MULTI_SELLING_POINT"])
    assert VIRAL_BODY_AUTHOR not in revision_skill_slugs(["TITLE_MULTI_SELLING_POINT"])


def test_projection_drops_rule_bundle_keeps_expression_guidance():
    payload = {
        "content_brief": {
            "business_variables": {"budget": "18万"},
            "form_values": {"budget": "18万", "mp_service_entry": "装修家居"},
        },
        "strategy_snapshot": {
            "snapshot_hash": "abc",
            "title_formula": {"code": "T01", "lexicon_codes": []},
            "body_formula": {"code": "C01", "body_calling": {"lexicon_calls": []}},
        },
        "formula_lexicon_bundle": {"title_formula_code": "T01", "body_formula_code": "C01", "title": [], "body": []},
        "evidence_bundle": {"items": []},
        "channel_profile": {"emoji_allowed": True, "title_constraints": {"min": 6, "max": 20}},
        "persona_profile": {"name": "顾问", "tone": "口语"},
        "runtime_config_snapshot": {"creation_mode": "viral_rewrite", "workflow_version_id": PLATFORM_WORKFLOW_V5_ID},
        "content_rule_bundle": {"bundle_hash": "secret", "runtime_rules": [{"id": "CORE-ONCE"}]},
        "expression_guidance": {"tone": ["口语"], "concrete": ["泥瓦"], "snapshot_hash": "snap-1"},
    }
    view = project_generation_input(payload)
    assert "content_rule_bundle" not in view
    assert view["expression_guidance"]["snapshot_hash"] == "snap-1"
    assert view["runtime_config_snapshot"] == {"creation_mode": "viral_rewrite"}


def test_visual_intent_scene_first():
    assert (
        resolve_visual_intent(
            brief={"form_values": {"process_type": "局部改造", "quote": "有报价"}},
            evidence_bundle={"items": [{"metadata": {"material_type": "price"}, "value": "19800"}]},
            has_price=True,
        )
        == "partial_renovation"
    )
    assert (
        resolve_visual_intent(brief={"form_values": {"project_stage": "全屋装修"}}, has_price=True)
        == "whole_house_quote"
    )
    assert resolve_visual_intent(brief={"form_values": {"process_type": "泥瓦工艺"}}, has_price=False) == "craft_detail"


def test_has_price_signal_from_evidence():
    assert has_price_signal(evidence_bundle={"items": [{"metadata": {"material_type": "price"}}]})
    assert not has_price_signal(evidence_bundle={"items": [{"value": "只谈工艺"}]}, brief={"form_values": {}})


def test_original_create_payload_is_rejected():
    with pytest.raises(ValidationError):
        ContentTaskCreate(industry_template_id="industry-decoration-v3", creation_mode="original")


def test_viral_v5_validator_topics_cta_and_keycap():
    from yuxi.content.validators import validate_viral_v5_content

    report = validate_viral_v5_content(
        title="旧房翻新怎么排坑",
        body="立即咨询\n" + "短段\n" * 8,
        topics=["池外标签"] + [f"话题{i}" for i in range(9)],
        brief={"forbidden_terms": []},
        evidence_bundle={"items": []},
        strategy={"methods": ["rewrite"], "title_formula_code": "T01", "body_formula_code": "C01"},
        rule_bundle={"topic_candidate_pool": ["旧房翻新"]},
    )
    codes = {item["code"] for item in report["checks"]}
    assert "CTA_HARD_SELL" in codes
    assert "TOPIC_COUNT_INVALID" in codes or "TOPIC_NOT_IN_POOL" in codes
    keycap = validate_viral_v5_content(
        title="第一次刷到",
        body="1️⃣ 只是序号不是造价\n" + "这是一段正常说明，不含业务数字。\n" * 6,
        topics=["旧房翻新"] * 10,
        brief={},
        evidence_bundle={"items": []},
        strategy={"methods": ["rewrite"], "title_formula_code": "T01", "body_formula_code": "C01"},
        rule_bundle={"topic_candidate_pool": ["旧房翻新"]},
    )
    assert not any(item["code"] == "FACT_NUMBER_WITHOUT_SOURCE" for item in keycap["checks"])


def test_revision_maps_new_codes():
    assert (
        resolve_revision_reason(
            title_validation_report=None,
            validation_report={"checks": [{"code": "TITLE_MULTI_SELLING_POINT", "level": "error"}]},
            review_report=None,
        )
        == "TITLE_VALIDATION_FAILED"
    )
    assert (
        resolve_revision_reason(
            title_validation_report=None,
            validation_report={"checks": [{"code": "TOPIC_NOT_IN_POOL", "level": "error"}]},
            review_report=None,
        )
        == "BODY_STRUCTURE_FAILED"
    )


def test_v5_workflow_is_immutable_fork_and_valid():
    from yuxi.content.v3.agents import CONTENT_AGENT_SPECS
    from yuxi.content.v3.modular_rules import GENERATE_ALL_SKILLS, MODULE_SPECS

    catalog = WorkflowCatalog(
        agents=frozenset(spec.slug for spec in CONTENT_AGENT_SPECS),
        skills=frozenset(
            {
                *GENERATE_ALL_SKILLS,
                "viral-modular-reviewer",
                "viral-cover-matcher",
                "content-visual-planner",
                "content-cover-generator",
                "content-visual-reviewer",
                "content-joint-strategy-selector",
                "prepared-viral-reference-selector",
                "content-price-researcher",
                "content-business-rule-researcher",
                "content-compliance-researcher",
                *{slug for slug, _name in MODULE_SPECS},
            }
        ),
        contracts=frozenset(DEFAULT_CONTRACTS),
        backends=frozenset({"managed"}),
    )
    WorkflowDefinitionPolicy.validate(WORKFLOW_VIRAL_V5, catalog=catalog)
    assert PLATFORM_WORKFLOW_V5_ID == "content-workflow-blueprint-first-v5"
    assert WORKFLOW_VIRAL_V5 is not WORKFLOW_V3
    assert {node["id"] for node in WORKFLOW_VIRAL_V5["nodes"]} >= {
        "freeze_rule_bundle",
        "retrieve_expression_kbs",
    }
    generate = next(node for node in WORKFLOW_VIRAL_V5["nodes"] if node["id"] == "generate_content")
    assert generate["agent_slug"] == "content-viral-generation-agent"
    assert generate["required_skills"] == list(GENERATE_ALL_SKILLS)
    visual = next(node for node in WORKFLOW_VIRAL_V5["nodes"] if node["id"] == "plan_visuals")
    assert visual["max_execution_steps"] == 16
