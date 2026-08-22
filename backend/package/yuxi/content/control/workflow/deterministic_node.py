from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.content.control.evidence import EvidenceApplicationService
from yuxi.content.control.strategy.recommend_v3 import StrategyPreviewActor
from yuxi.content.infrastructure.postgres.decision_snapshot_repository import PostgresDecisionSnapshotRepository
from yuxi.content.infrastructure.postgres.strategy_preview_repository import PostgresStrategyPreviewRepository
from yuxi.content.model.evidence import (
    EvidenceBundleV1,
    EvidenceGovernanceError,
    EvidenceItemV1,
    freeze_evidence_bundle,
    next_evidence_bundle_version,
)
from yuxi.content.model.rules.engine import CombinationMatcher, MatchRequest
from yuxi.content.rules import brief_variable_map
from yuxi.content.validators import validate_content
from yuxi.content.validation import ComplianceEngine, validate_numeric_evidence_coverage
from yuxi.services.run_queue_service import append_run_stream_event
from yuxi.storage.postgres.models_content import ContentTask


class V3DeterministicNodeHandler:
    async def execute(
        self,
        *,
        db: AsyncSession,
        node: dict[str, Any],
        state: dict[str, Any],
        node_run_id: str,
    ) -> dict[str, Any]:
        handlers = {
            "compile_runtime_snapshot": self._compile_runtime_snapshot,
            "ingest_real_materials": self._ingest_real_materials,
            "normalize_evidence": self._normalize_evidence,
            "match_combination_group": self._match_combination_group,
            "resolve_formula_requirements": self._resolve_formula_requirements,
            "freeze_evidence_bundle": self._freeze_evidence_bundle,
            "resolve_product_material_requirements": self._resolve_product_material_requirements,
            "freeze_product_evidence_bundle": self._freeze_product_evidence_bundle,
            "validate_title_candidates": self._validate_title_candidates,
            "adapt_to_channel": self._adapt_to_channel,
            "deterministic_validate": self._deterministic_validate,
            "package_for_distribution": self._package_for_distribution,
        }
        handler = handlers.get(node["id"])
        if handler is None:
            raise ValueError(f"未注册的 V3 固定节点: {node['id']}")
        return await handler(db=db, state=state, node_run_id=node_run_id)

    @staticmethod
    async def _compile_runtime_snapshot(*, db: AsyncSession, state: dict[str, Any], node_run_id: str) -> dict[str, Any]:
        del node_run_id
        task = await db.get(ContentTask, state["task_id"])
        if task is None:
            raise ValueError("内容任务不存在")
        if not task.workflow_definition_hash:
            raise ValueError("V3 任务未锁定工作流定义 hash")
        runtime = {
            **(state.get("runtime_config_snapshot") or {}),
            "schema_version": 3,
            "workflow_version_id": task.workflow_version_id,
            "workflow_definition_hash": task.workflow_definition_hash,
            "rule_version_id": task.rule_version_id,
            "industry_pack_version_id": task.industry_pack_version_id,
            "persona_profile_version_id": task.persona_profile_version_id,
            "channel_profile_version_id": task.channel_profile_version_id,
        }
        task.runtime_config_snapshot_json = runtime
        return {
            "schema_version": 3,
            "runtime_config_snapshot": runtime,
            "state_version": int(state.get("state_version") or 0) + 1,
            "task_mode": task.mode,
        }

    @staticmethod
    async def _ingest_real_materials(*, db: AsyncSession, state: dict[str, Any], node_run_id: str) -> dict[str, Any]:
        del db, node_run_id
        usable = [
            item
            for item in state.get("media_evidence_items") or []
            if item.get("verified_status") != "rejected" and item.get("privacy_status") == "approved"
        ]
        return {"media_evidence_items": usable}

    async def _normalize_evidence(self, *, db: AsyncSession, state: dict[str, Any], node_run_id: str) -> dict[str, Any]:
        del node_run_id
        existing = state.get("evidence_bundle") or {}
        if existing.get("status") == "frozen" and existing.get("bundle_hash"):
            return {"evidence_bundle": existing}
        items: list[EvidenceItemV1] = []
        for key, value in brief_variable_map(state["content_brief"]).items():
            if value in (None, "", [], {}):
                continue
            source_hash = hashlib.sha256(
                json.dumps([state["task_id"], key, value], ensure_ascii=False, sort_keys=True).encode()
            ).hexdigest()
            items.append(
                EvidenceItemV1(
                    id=f"ev_{source_hash[:16]}",
                    variable_codes=(key,),
                    value=value,
                    source_type="manual_input",
                    source_id=f"field_{key}",
                    source_version="brief-v1",
                    verified_status="user_confirmed",
                    allowed_usage=("title", "body", "visual"),
                    source_hash=source_hash,
                )
            )
        for media in state.get("media_evidence_items") or []:
            value = media.get("extracted_text") or media.get("confirmed_facts") or ""
            if not value:
                continue
            items.append(
                EvidenceItemV1(
                    id=str(media["id"]),
                    variable_codes=tuple(
                        str(item.get("variable_code"))
                        for item in media.get("confirmed_facts") or []
                        if item.get("variable_code")
                    ),
                    value=value,
                    source_type="media",
                    source_id=str(media.get("attachment_id") or media["id"]),
                    source_version=str(media.get("parser_version") or media.get("source_hash") or "unknown"),
                    verified_status="confirmed",
                    allowed_usage=tuple(media.get("allowed_usage") or ["body", "visual"]),
                    source_hash=str(media.get("source_hash") or hashlib.sha256(str(value).encode()).hexdigest()),
                    metadata={"object_uri": media.get("object_uri")},
                )
            )
        bundle = freeze_evidence_bundle(task_id=state["task_id"], version=1, items=items)
        await EvidenceApplicationService(db).persist_frozen_bundle(
            bundle,
            run_id=state["run_id"],
            thread_id=state["task_id"],
            added_evidence_ids=tuple(item.id for item in items),
        )
        return {"evidence_bundle": bundle.model_dump(mode="json")}

    @staticmethod
    async def _match_combination_group(*, db: AsyncSession, state: dict[str, Any], node_run_id: str) -> dict[str, Any]:
        selected = state.get("selected_angle") or {}
        direction = selected.get("direction_code") or selected.get("content_direction_code")
        task = await db.get(ContentTask, state["task_id"])
        if task is None or not direction:
            raise ValueError("匹配组合组前必须锁定内容方向")
        context = await PostgresStrategyPreviewRepository(db).load_context(
            task_id=task.id,
            actor=StrategyPreviewActor(
                uid=state["uid"],
                role="superadmin" if task.created_by != state["uid"] else "user",
                tenant_id=task.tenant_id,
            ),
            requested_content_direction_code=direction,
        )
        if context is None:
            raise ValueError("无权访问内容任务")
        decision = CombinationMatcher().match(
            list(context.groups),
            MatchRequest(
                content_direction_code=context.content_direction_code,
                industry_slug=context.industry_slug,
                channel_code=context.channel_code,
                content_goal_code=context.content_goal_code,
                narrative_axis_code=context.narrative_axis_code,
                available_variable_codes=context.available_variable_codes,
                available_evidence_types=context.available_evidence_types,
            ),
        )
        if decision.status != "matched" or not decision.selected_group_code:
            raise ValueError("没有组合组通过固定硬约束")
        snapshot = await PostgresDecisionSnapshotRepository(db).save_match_decision(
            task_id=task.id,
            content_run_id=state["run_id"],
            node_run_id=node_run_id,
            rule_version_id=context.rule_version_id,
            industry_pack_version_id=context.industry_pack_version_id,
            channel_profile_version_id=context.channel_profile_version_id,
            decision=decision,
            selected_by="deterministic",
        )
        payload = decision.to_dict()
        payload["id"] = snapshot.id
        payload["selected_group_id"] = decision.selected_group_code
        selected_group = next(
            item for item in decision.eligible_groups if item.group_code == decision.selected_group_code
        )
        payload["eligible_title_formula_codes"] = list(selected_group.title_formula_candidate_codes)
        payload["eligible_body_formula_codes"] = list(selected_group.body_formula_candidate_codes)
        await append_run_stream_event(
            state["run_id"],
            "content.rule.matched",
            {
                "task_id": task.id,
                "node_id": "match_combination_group",
                "selected_group_id": decision.selected_group_code,
                "eligible_group_ids": [item.group_code for item in decision.eligible_groups],
            },
            thread_id=task.id,
        )
        return {"match_decision_snapshot": payload}

    @staticmethod
    async def _resolve_formula_requirements(
        *, db: AsyncSession, state: dict[str, Any], node_run_id: str
    ) -> dict[str, Any]:
        del db, node_run_id
        match = state.get("match_decision_snapshot") or {}
        return {
            "formula_candidate_pool": {
                "combination_group_id": match.get("selected_group_id"),
                "title_formula_codes": match.get("eligible_title_formula_codes") or [],
                "body_formula_codes": match.get("eligible_body_formula_codes") or [],
            }
        }

    async def _freeze_evidence_bundle(
        self, *, db: AsyncSession, state: dict[str, Any], node_run_id: str
    ) -> dict[str, Any]:
        del node_run_id
        current = EvidenceBundleV1.model_validate(state["evidence_bundle"])
        collection = state.get("evidence_collection") or {}
        additions = [EvidenceItemV1.model_validate(item) for item in collection.get("evidence_items") or []]
        current_by_id = {item.id: item for item in current.items}
        new_additions: list[EvidenceItemV1] = []
        for item in additions:
            existing = current_by_id.get(item.id)
            if existing is None:
                new_additions.append(item)
                continue
            existing_payload = existing.model_dump(mode="json", exclude={"created_at", "metadata"})
            addition_payload = item.model_dump(mode="json", exclude={"created_at", "metadata"})
            if existing_payload != addition_payload:
                raise EvidenceGovernanceError(
                    "evidence_id_conflict",
                    f"Evidence ID {item.id} 已存在但内容不一致",
                )
        additions = new_additions
        if not additions:
            return {"evidence_bundle": current.model_dump(mode="json")}
        bundle = next_evidence_bundle_version(
            current,
            additions=additions,
            citations=[*current.citations, *({"source_id": item} for item in collection.get("citations") or [])],
        )
        await EvidenceApplicationService(db).persist_frozen_bundle(
            bundle,
            run_id=state["run_id"],
            thread_id=state["task_id"],
            added_evidence_ids=tuple(item.id for item in additions),
        )
        return {"evidence_bundle": bundle.model_dump(mode="json")}

    @staticmethod
    async def _resolve_product_material_requirements(
        *, db: AsyncSession, state: dict[str, Any], node_run_id: str
    ) -> dict[str, Any]:
        del db, node_run_id
        strategy = state.get("strategy_snapshot") or {}
        snapshot_hash = str(strategy.get("snapshot_hash") or "")
        if not snapshot_hash:
            raise ValueError("解析产品资料需求前必须锁定 StrategySnapshot")

        title_variables = list((strategy.get("title_formula") or {}).get("variable_schema") or [])
        body_variables = list((strategy.get("body_formula") or {}).get("required_variables") or [])
        method_variables = [
            variable
            for method in strategy.get("creation_method_definitions") or []
            for variable in method.get("variable_schema") or []
        ]
        variable_codes = list(dict.fromkeys([*title_variables, *body_variables, *method_variables]))
        variable_set = set(variable_codes)
        body_formula_code = str((strategy.get("body_formula") or {}).get("code") or "")

        requirements = [
            {
                "requirement_id": "product_profile",
                "material_type": "product_profile",
                "variable_codes": sorted(variable_set & {"product", "advantages", "result", "pain_points"}),
                "target_usages": ["title", "body"],
                "required": bool(variable_set & {"product", "advantages", "result"}),
                "query_hint": "检索当前公司正式产品或服务介绍、适用人群、核心卖点、解决的问题和使用边界",
                "risk_level": "normal",
            },
            {
                "requirement_id": "price",
                "material_type": "price",
                "variable_codes": sorted(variable_set & {"price", "budget", "cost", "discount", "fee"}),
                "target_usages": ["title", "body"],
                "required": bool(variable_set & {"price", "budget", "cost", "discount", "fee"}),
                "query_hint": "检索仍在有效期内的正式价格、报价范围、费用口径、适用区域与生效日期",
                "risk_level": "high_risk",
            },
            {
                "requirement_id": "case_proof",
                "material_type": "case_proof",
                "variable_codes": sorted(variable_set & {"number", "result", "scene", "location"}),
                "target_usages": ["title", "body"],
                "required": body_formula_code == "C02" or bool(variable_set & {"number", "result"}),
                "query_hint": "检索可公开使用的真实案例、结果数字、使用场景、地域与客户问题，不得拼接不同案例",
                "risk_level": "sensitive",
            },
            {
                "requirement_id": "brand",
                "material_type": "brand",
                "variable_codes": sorted(variable_set & {"brand_name", "audience"}),
                "target_usages": ["title", "body"],
                "required": body_formula_code == "C04" or "brand_name" in variable_set,
                "query_hint": "检索正式品牌称谓、品牌定位、服务对象、价值主张、禁用词和承诺边界",
                "risk_level": "normal",
            },
            {
                "requirement_id": "viral_example",
                "material_type": "viral_example",
                "variable_codes": [],
                "target_usages": ["style_reference"],
                "required": False,
                "query_hint": "检索同方向爆款样例，仅提取标题结构、叙事节奏和表达模式，禁止复制事实、数字和原句",
                "risk_level": "normal",
            },
        ]
        if not any(item["required"] for item in requirements):
            requirements[0]["required"] = True
        return {
            "product_material_requirements": {
                "strategy_snapshot_hash": snapshot_hash,
                "required_variable_codes": variable_codes,
                "requirements": requirements,
            }
        }

    async def _freeze_product_evidence_bundle(
        self, *, db: AsyncSession, state: dict[str, Any], node_run_id: str
    ) -> dict[str, Any]:
        del node_run_id
        current = EvidenceBundleV1.model_validate(state["evidence_bundle"])
        requirements = state.get("product_material_requirements") or {}
        collection = state.get("product_evidence_collection") or {}
        additions = [EvidenceItemV1.model_validate(item) for item in collection.get("evidence_items") or []]
        current_by_id = {item.id: item for item in current.items}
        new_additions: list[EvidenceItemV1] = []
        for item in additions:
            existing = current_by_id.get(item.id)
            if existing is None:
                new_additions.append(item)
                continue
            existing_payload = existing.model_dump(mode="json", exclude={"created_at"})
            addition_payload = item.model_dump(mode="json", exclude={"created_at"})
            if existing_payload != addition_payload:
                raise EvidenceGovernanceError("evidence_id_conflict", f"Evidence ID {item.id} 已存在但内容不一致")

        evidence_by_id = {**current_by_id, **{item.id: item for item in new_additions}}
        requirement_by_id = {
            item["requirement_id"]: item
            for item in requirements.get("requirements") or []
            if item.get("requirement_id")
        }
        slot_mappings = list(collection.get("slot_mappings") or [])
        mapped_required = {item.get("slot") for item in slot_mappings if item.get("evidence_ids")}
        missing_required = sorted(
            requirement_id
            for requirement_id, requirement in requirement_by_id.items()
            if requirement.get("required") and requirement_id not in mapped_required
        )
        if missing_required:
            raise EvidenceGovernanceError(
                "required_product_evidence_missing",
                f"锁定公式所需产品资料尚未补齐: {', '.join(missing_required)}",
            )

        for mapping in slot_mappings:
            requirement = requirement_by_id.get(mapping.get("slot"))
            if requirement is None:
                raise EvidenceGovernanceError("product_slot_unknown", f"未知产品资料槽位: {mapping.get('slot')}")
            target_usage = str(mapping.get("target_usage") or "")
            if target_usage not in requirement.get("target_usages", []):
                raise EvidenceGovernanceError(
                    "product_slot_usage_invalid",
                    f"槽位 {mapping['slot']} 不允许用于 {target_usage}",
                )
            for evidence_id in mapping.get("evidence_ids") or []:
                evidence = evidence_by_id.get(evidence_id)
                if evidence is None or target_usage not in evidence.allowed_usage:
                    raise EvidenceGovernanceError(
                        "product_evidence_usage_invalid",
                        f"Evidence {evidence_id} 不允许用于槽位 {mapping['slot']} 的 {target_usage}",
                    )

        if new_additions:
            bundle = next_evidence_bundle_version(
                current,
                additions=new_additions,
                citations=[
                    *current.citations,
                    *({"source_id": item} for item in collection.get("citations") or []),
                ],
            )
            await EvidenceApplicationService(db).persist_frozen_bundle(
                bundle,
                run_id=state["run_id"],
                thread_id=state["task_id"],
                added_evidence_ids=tuple(item.id for item in new_additions),
            )
        else:
            bundle = current

        pack_payload = {
            "strategy_snapshot_hash": requirements.get("strategy_snapshot_hash"),
            "evidence_bundle_id": bundle.id,
            "evidence_bundle_version": bundle.version,
            "evidence_bundle_hash": bundle.bundle_hash,
            "slot_mappings": slot_mappings,
            "unresolved_questions": collection.get("unresolved_questions") or [],
        }
        canonical = json.dumps(pack_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        pack_payload["pack_hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return {
            "evidence_bundle": bundle.model_dump(mode="json"),
            "product_evidence_pack": pack_payload,
        }

    @staticmethod
    async def _validate_title_candidates(
        *, db: AsyncSession, state: dict[str, Any], node_run_id: str
    ) -> dict[str, Any]:
        del db, node_run_id
        candidates = state.get("title_candidates") or []
        locked = (state.get("formula_selection_snapshot") or {}).get("selected_title_formula_code")
        if len(candidates) < 2 or any(item.get("formula_code") != locked for item in candidates):
            raise ValueError("标题候选必须全部使用同一锁定标题公式")
        report = []
        title_mappings = [
            item
            for item in (state.get("product_evidence_pack") or {}).get("slot_mappings") or []
            if item.get("target_usage") == "title"
        ]
        for item in candidates:
            numeric = validate_numeric_evidence_coverage(item.get("text", ""), state["evidence_bundle"])
            length_ok = 1 <= len(item.get("text", "")) <= 60
            cited = set(item.get("evidence_ids") or [])
            missing_product_slots = [
                mapping["slot"]
                for mapping in title_mappings
                if not cited.intersection(mapping.get("evidence_ids") or [])
            ]
            checks = list(numeric["checks"])
            if missing_product_slots:
                checks.append(
                    {
                        "code": "TITLE_PRODUCT_EVIDENCE_NOT_USED",
                        "level": "error",
                        "location": "title",
                        "message": f"标题未植入已映射的产品资料: {', '.join(missing_product_slots)}",
                        "evidence_ids": [],
                    }
                )
            status = (
                "passed" if numeric["status"] == "passed" and length_ok and not missing_product_slots else "blocked"
            )
            report.append({"id": item["id"], "status": status, "checks": checks})
        if all(item["status"] == "blocked" for item in report):
            raise ValueError("所有标题候选都未通过确定性校验")
        status_by_id = {item["id"]: item["status"] for item in report}
        return {
            "title_candidates": [{**item, "selectable": status_by_id[item["id"]] != "blocked"} for item in candidates],
            "title_validation_report": {"status": "passed", "items": report},
        }

    @staticmethod
    async def _adapt_to_channel(*, db: AsyncSession, state: dict[str, Any], node_run_id: str) -> dict[str, Any]:
        del db, node_run_id
        draft = dict(state.get("content_draft") or {})
        title = dict(state.get("selected_title") or {})
        result = ComplianceEngine().validate_and_adapt(
            title=title.get("text", ""),
            body=draft.get("body", ""),
            topics=draft.get("topics") or [],
            channel_profile=state.get("channel_profile") or {},
            policies=state.get("compliance_policies") or [],
        )
        title["text"] = result["title"]
        draft["body"] = result["body"]
        draft["topics"] = result["topics"]
        return {"selected_title": title, "content_draft": draft, "channel_result": result}

    @staticmethod
    async def _deterministic_validate(*, db: AsyncSession, state: dict[str, Any], node_run_id: str) -> dict[str, Any]:
        del db, node_run_id
        draft = state.get("content_draft") or {}
        body = draft.get("body", "")
        report = validate_content(
            title=(state.get("selected_title") or {}).get("text", ""),
            body=body,
            topics=draft.get("topics") or [],
            brief=state["content_brief"],
            evidence_bundle=state["evidence_bundle"],
            strategy={
                "methods": (state.get("strategy_snapshot") or {}).get("creation_methods"),
                "title_formula_code": ((state.get("strategy_snapshot") or {}).get("title_formula") or {}).get("code"),
                "body_formula_code": ((state.get("strategy_snapshot") or {}).get("body_formula") or {}).get("code"),
            },
        )
        if not 200 <= len(body) <= 650:
            report["checks"].append(
                {
                    "code": "BODY_LENGTH_OUT_OF_RANGE",
                    "level": "error",
                    "location": "body",
                    "message": "正文目标长度必须为 200～650 字",
                    "evidence_ids": [],
                }
            )
            report["status"] = "blocked"
        used_body_evidence = {
            evidence_id
            for paragraph in draft.get("paragraph_evidence") or []
            for evidence_id in paragraph.get("evidence_ids") or []
        }
        missing_product_slots = [
            mapping["slot"]
            for mapping in (state.get("product_evidence_pack") or {}).get("slot_mappings") or []
            if mapping.get("target_usage") == "body"
            and not used_body_evidence.intersection(mapping.get("evidence_ids") or [])
        ]
        if missing_product_slots:
            report["checks"].append(
                {
                    "code": "BODY_PRODUCT_EVIDENCE_NOT_USED",
                    "level": "error",
                    "location": "body",
                    "message": f"正文未植入已映射的产品资料: {', '.join(missing_product_slots)}",
                    "evidence_ids": [],
                }
            )
            report["status"] = "blocked"
        return {"validation_report": report}

    @staticmethod
    async def _package_for_distribution(*, db: AsyncSession, state: dict[str, Any], node_run_id: str) -> dict[str, Any]:
        del db, node_run_id
        if not state.get("artifact_id"):
            raise ValueError("发布打包前必须保存 Artifact")
        version = state.get("artifact_version") or {}
        if not version.get("id") or not version.get("cover_asset_id"):
            raise ValueError("发布打包前必须锁定同时包含文案与封面的 ArtifactVersion")
        return {
            "distribution_package": {
                "artifact_id": state["artifact_id"],
                "artifact_version_id": version["id"],
                "cover_asset_id": version["cover_asset_id"],
                "selected_cover": state.get("selected_cover"),
                "evidence_bundle_hash": (state.get("evidence_bundle") or {}).get("bundle_hash"),
                "formula_selection_snapshot_id": (state.get("formula_selection_snapshot") or {}).get("id"),
                "runtime_config_snapshot": state.get("runtime_config_snapshot") or {},
            }
        }


__all__ = ["V3DeterministicNodeHandler"]
