from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.content.control.workflow.content_node_input import ContentNodeInputAssembler
from yuxi.content.model.contracts import ContractDomainContext
from yuxi.services.agent_delegation_service import AgentDelegationRequest, AgentDelegationService
from yuxi.storage.postgres.models_business import User
from yuxi.storage.postgres.models_content import ContentNodeRun, ContentTask


PROHIBITED_ACTIONS = {
    "analyze_content_value": ("不锁定组合组", "不选公式", "不修改工作流"),
    "select_content_direction": ("不选择候选集外方向", "不锁定组合组", "不选公式", "不修改工作流"),
    "explain_strategy": ("不改变固定匹配结果", "不扩大候选池"),
    "collect_missing_evidence": ("不直接生成文章", "不编造事实"),
    "collect_strategy_product_evidence": (
        "不生成标题或正文",
        "不修改锁定公式或创作手法",
        "爆款样例不得作为事实或数字来源",
        "不得把案例证明映射为爆款样例或 style_reference",
    ),
    "rank_formula_candidates": ("不提交候选池外公式", "不修改匹配组"),
    "generate_title_candidates": ("不生成正文", "不选最终标题", "不改公式"),
    "select_title": ("不选择未通过校验的候选", "不修改标题文本、公式或证据 ID", "不生成正文"),
    "build_outline": ("不生成新事实", "不改正文公式"),
    "generate_body": ("不改锁定标题", "不检索网页或知识库"),
    "persona_style_polish": ("不改数字、价格、承诺或证据 ID", "不改结构主干"),
    "semantic_review": ("不直接修改文稿", "不跳过确定性校验"),
    "plan_visuals": ("不新增无证据价格、人物或效果",),
    "submit_cover_job": ("不直接写 MinIO", "不轮询封面任务"),
    "visual_review": ("不直接修改或删除资产",),
}


class AgentNodeResultMapper:
    @staticmethod
    def to_state(node_id: str, result: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        if node_id == "analyze_content_value":
            return {
                "value_analysis": result,
                "content_angles": result["direction_candidates"],
            }
        if node_id == "select_content_direction":
            selected = next(
                (
                    item
                    for item in state.get("content_angles") or []
                    if item.get("direction_code") == result["direction_code"]
                ),
                None,
            )
            if selected is None:
                raise ValueError("Agent 选定内容方向不在价值分析候选集中")
            return {
                "selected_angle": {
                    **selected,
                    "reason": result["reason"],
                    "evidence_ids": result["evidence_ids"],
                    "selected_by": "agent",
                }
            }
        if node_id == "explain_strategy":
            return {"strategy_explanation": result}
        if node_id == "collect_missing_evidence":
            return {"evidence_collection": result}
        if node_id == "collect_strategy_product_evidence":
            return {"product_evidence_collection": result}
        if node_id == "rank_formula_candidates":
            return {"formula_rankings": result}
        if node_id == "generate_title_candidates":
            return {"title_candidates": result["candidates"]}
        if node_id == "select_title":
            selected = next(
                (
                    item
                    for item in state.get("title_candidates") or []
                    if item.get("id") == result["selected_title_id"] and item.get("selectable") is True
                ),
                None,
            )
            if selected is None:
                raise ValueError("标题 Agent 只能选择通过确定性校验的候选")
            return {
                "selected_title": {
                    **selected,
                    "selection_reason": result["reason"],
                    "selected_by": "agent",
                }
            }
        if node_id == "build_outline":
            return {"content_outline": result}
        if node_id == "generate_body":
            return {"content_draft": result}
        if node_id == "persona_style_polish":
            draft = dict(state.get("content_draft") or {})
            draft["body"] = result["polished_body"]
            return {
                "content_draft": draft,
                "persona_diff": {
                    "change_summary": result["change_summary"],
                    "preserved_fact_checks": result["preserved_fact_checks"],
                },
            }
        if node_id == "semantic_review":
            return {"review_report": result}
        if node_id == "plan_visuals":
            canonical = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            return {
                "visual_plan": {
                    **result,
                    "plan_hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
                }
            }
        if node_id == "submit_cover_job":
            return {"cover_job": result}
        if node_id == "visual_review":
            return {"visual_review": result}
        raise ValueError(f"未注册的 V3 Agent 节点: {node_id}")


class AgentNodeHandler:
    async def execute(
        self,
        *,
        db: AsyncSession,
        node: dict[str, Any],
        state: dict[str, Any],
        node_run_id: str,
    ) -> dict[str, Any]:
        node_run = await db.get(ContentNodeRun, node_run_id)
        task = await db.get(ContentTask, state["task_id"])
        user = (
            await db.execute(select(User).where(User.uid == state["uid"], User.is_deleted == 0))
        ).scalar_one_or_none()
        if node_run is None or task is None or user is None:
            raise ValueError("Agent 节点缺少任务、用户或节点 Run")

        evidence_bundle = state.get("evidence_bundle") or {"items": []}
        evidence_hash = str(evidence_bundle.get("bundle_hash") or "")
        if not evidence_hash:
            canonical = json.dumps(evidence_bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            evidence_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        locked_versions = {
            "industry_pack_version_id": task.industry_pack_version_id or "",
            "channel_profile_version_id": task.channel_profile_version_id or "",
            "persona_profile_version_id": task.persona_profile_version_id,
            "rule_version_id": task.rule_version_id,
            "title_formula_code": (state.get("formula_selection_snapshot") or {}).get("selected_title_formula_code"),
            "body_formula_code": (state.get("formula_selection_snapshot") or {}).get("selected_body_formula_code"),
            "artifact_version_id": (state.get("artifact_version") or {}).get("id"),
        }
        media = state.get("media_evidence_items") or []
        cover_asset_ids = list((state.get("cover_job") or {}).get("asset_ids") or [])
        visual_material = (state.get("runtime_config_snapshot") or {}).get("visual_material") or {}
        required_source_asset_ids = [visual_material["image_asset_id"]] if visual_material.get("image_asset_id") else []
        locked_values = {
            "selected_title": (state.get("selected_title") or {}).get("text"),
            "source_asset_ids": [
                *[item["id"] for item in media if item.get("id")],
                *cover_asset_ids,
            ],
            "required_source_asset_ids": required_source_asset_ids,
            "visual_plan_hash": (state.get("visual_plan") or {}).get("plan_hash"),
            "state_version": int(state.get("state_version") or 0),
        }
        if node["id"] == "submit_cover_job":
            locked_values["visual_plan"] = state.get("visual_plan") or {}
        assembly = ContentNodeInputAssembler.build(node=node, state=state)
        domain_context = ContractDomainContext.from_governance(
            match_decision_snapshot=state.get("match_decision_snapshot") or {},
            formula_selection_snapshot=state.get("formula_selection_snapshot") or {},
            evidence_bundle=evidence_bundle,
            locked_versions=locked_versions,
            locked_values=locked_values,
            product_material_requirements=state.get("product_material_requirements") or {},
        )
        delegation = AgentDelegationService(db)
        delegated = await delegation.execute(
            AgentDelegationRequest(
                task_id=task.id,
                parent_content_run_id=state["run_id"],
                node_run=node_run,
                user=user,
                agent_slug=node["agent_slug"],
                required_skills=tuple(node["required_skills"]),
                input_contract=assembly.contract_name,
                input_payload=assembly.payload,
                input_snapshot_hash=assembly.snapshot_hash,
                domain_context=domain_context,
                governance_values={
                    "evidence_bundle_hash": evidence_hash,
                    "match_decision_snapshot": state.get("match_decision_snapshot") or {},
                    "formula_selection_snapshot": state.get("formula_selection_snapshot") or {},
                    "locked_versions": locked_versions,
                    "locked_values": locked_values,
                    "product_material_requirements": state.get("product_material_requirements") or {},
                },
                prompt=f"执行内容工作流节点 {node['id']} 的唯一职责",
                output_contract=node["output_contract"],
                result_tool_name=node["result_tool_name"],
                knowledge_policy=node["knowledge_policy"],
                timeout_seconds=node["timeout_seconds"],
                max_execution_steps=node["max_execution_steps"],
                max_tool_calls=node["max_tool_calls"],
                token_budget=node["token_budget"],
                max_retrieval_rounds=int(node.get("max_retrieval_rounds") or 0),
                max_knowledge_bases=int(node.get("max_knowledge_bases") or 0),
                max_chunks_per_knowledge_base=int(node.get("max_chunks_per_knowledge_base") or 0),
                prohibited_actions=PROHIBITED_ACTIONS.get(node["id"], ()),
            )
        )
        mapped = AgentNodeResultMapper.to_state(node["id"], delegated.output, state)
        delegated_runs = dict(state.get("delegated_agent_runs") or {})
        delegated_runs[node["id"]] = delegated.delegated_agent_run_id
        return {**mapped, "delegated_agent_runs": delegated_runs}


__all__ = ["AgentNodeHandler", "AgentNodeResultMapper", "PROHIBITED_ACTIONS"]
