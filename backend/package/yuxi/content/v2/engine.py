"""V2 内容规则的纯领域执行器。

本模块不访问数据库、不调用模型，也不控制工作流跳转。调用方需要先冻结规则、
行业包、词库、Persona、渠道和证据快照，再把普通字典传入这些执行器。这样相同
输入、规则版本和随机种子一定得到相同结果，也便于历史重放和单元测试。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Iterable


_MISSING = object()
_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9])\d+(?:\.\d+)?(?:%|元|万元|天|周|月|年|个|次|㎡|m²)?")


def _as_list(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    return value if isinstance(value, list) else [value]


def _has_value(value: Any) -> bool:
    return value is not _MISSING and value not in (None, "", [], {})


def _path_get(payload: dict[str, Any], path: str | None) -> Any:
    if not path:
        return _MISSING
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _brief_variables(brief: dict[str, Any]) -> dict[str, Any]:
    variables = dict(brief.get("business_variables") or {})
    variables.update(
        {
            key: value
            for key, value in (brief.get("form_values") or {}).items()
            if value not in (None, "", [])
        }
    )
    variables.setdefault("brand_name", (brief.get("brand") or {}).get("name"))
    variables.setdefault("audience", brief.get("audience") or [])
    variables.setdefault("location", (brief.get("scene") or {}).get("location"))
    variables.setdefault("persona", brief.get("persona") or {})
    return variables


def _evidence_items(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in bundle.get("items") or [] if isinstance(item, dict)]


def _evidence_supports(item: dict[str, Any], slot_key: str, usage: str | None = None) -> bool:
    if item.get("verified_status") in {"rejected", "unverified", "blocked"}:
        return False
    variables = set(item.get("variable_codes") or item.get("supported_variables") or [])
    if item.get("key"):
        variables.add(str(item["key"]))
    slots = set(item.get("slot_keys") or item.get("supported_slots") or [])
    if slot_key not in variables and slot_key not in slots:
        return False
    allowed = set(item.get("allowed_usage") or [])
    return not usage or not allowed or usage in allowed


def _evidence_value(item: dict[str, Any], slot_key: str) -> Any:
    values = item.get("values") if isinstance(item.get("values"), dict) else {}
    if slot_key in values:
        return values[slot_key]
    if item.get("variable_code") == slot_key and _has_value(item.get("value")):
        return item["value"]
    if item.get("key") == slot_key and _has_value(item.get("value")):
        return item["value"]
    return item.get("value", item.get("content"))


@dataclass(frozen=True)
class _SlotResult:
    slot_key: str
    status: str
    value: Any
    source_type: str
    source_path: str | None
    evidence_ids: tuple[str, ...]
    lexicon_entry_id: str | None
    message: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "slot_key": self.slot_key,
            "status": self.status,
            "value": self.value,
            "source_type": self.source_type,
            "source_path": self.source_path,
            "evidence_ids": list(self.evidence_ids),
            "lexicon_entry_id": self.lexicon_entry_id,
            "message": self.message,
        }


class FormulaSlotResolver:
    """把已发布 Pattern 的 Slot 绑定到简报、证据、Persona 或词库。"""

    def resolve(
        self,
        pattern: dict[str, Any],
        *,
        brief: dict[str, Any],
        evidence_bundle: dict[str, Any],
        lexicon_entries: Iterable[dict[str, Any]] = (),
        persona: dict[str, Any] | None = None,
        content_goal: str | None = None,
    ) -> dict[str, Any]:
        variables = _brief_variables(brief)
        evidence = _evidence_items(evidence_bundle)
        lexicon = list(lexicon_entries)
        usage = "title" if pattern.get("formula_kind") == "title" else "body"
        resolved: list[_SlotResult] = []

        for slot in sorted(pattern.get("slots") or [], key=lambda value: value.get("sort_order", 0)):
            result = self._resolve_one(
                slot,
                brief=brief,
                variables=variables,
                evidence=evidence,
                lexicon=lexicon,
                persona=persona or {},
                content_goal=content_goal,
                usage=usage,
            )
            resolved.append(result)

        blocking = [item for item in resolved if item.status == "blocked"]
        missing = [item for item in resolved if item.status in {"blocked", "missing"}]
        mapping = {item.slot_key: item.value for item in resolved if _has_value(item.value)}
        rendered = None
        if not blocking and pattern.get("formula_kind") == "title":
            try:
                rendered = str(pattern.get("template_text") or "").format_map(_StrictFormatMap(mapping))
            except (KeyError, ValueError):
                blocking.append(
                    _SlotResult(
                        slot_key="__template__",
                        status="blocked",
                        value=None,
                        source_type="system",
                        source_path=None,
                        evidence_ids=(),
                        lexicon_entry_id=None,
                        message="Pattern 模板引用了未定义或未解析的槽位",
                    )
                )

        return {
            "pattern_code": pattern.get("code"),
            "formula_code": pattern.get("formula_code"),
            "formula_kind": pattern.get("formula_kind"),
            "compatibility": "blocked" if blocking else ("warning" if missing else "compatible"),
            "slots": [item.as_dict() for item in resolved],
            "missing_slots": [item.slot_key for item in missing],
            "blocking_reasons": [item.message for item in blocking if item.message],
            "variable_mapping": mapping,
            "rendered_preview": rendered,
        }

    def _resolve_one(
        self,
        slot: dict[str, Any],
        *,
        brief: dict[str, Any],
        variables: dict[str, Any],
        evidence: list[dict[str, Any]],
        lexicon: list[dict[str, Any]],
        persona: dict[str, Any],
        content_goal: str | None,
        usage: str,
    ) -> _SlotResult:
        key = str(slot.get("slot_key") or "")
        source_type = str(slot.get("source_type") or "brief")
        source_path = slot.get("source_path")
        evidence_matches = [item for item in evidence if _evidence_supports(item, key, usage)]
        value: Any = _MISSING
        lexicon_entry_id: str | None = None

        if source_type == "brief":
            value = _path_get(brief, source_path)
            if value is _MISSING:
                value = variables.get(key, _MISSING)
        elif source_type in {"evidence", "evidence_or_goal"}:
            if evidence_matches:
                value = _evidence_value(evidence_matches[0], key)
            elif source_type == "evidence_or_goal" and content_goal:
                value = content_goal
        elif source_type == "persona":
            value = _path_get(persona, source_path or key)
        elif source_type == "lexicon":
            allowed_packs = set(slot.get("lexicon_pack_codes") or [])
            applicable = [
                item
                for item in lexicon
                if (not allowed_packs or item.get("pack_code") in allowed_packs)
                and (not item.get("applicable_slot_keys") or key in item.get("applicable_slot_keys", []))
                and item.get("risk_level", "safe") not in {"blocked", "high"}
            ]
            applicable.sort(key=lambda item: (item.get("sort_order", 0), item.get("id", "")))
            if applicable:
                value = applicable[0].get("text")
                lexicon_entry_id = applicable[0].get("id")
        elif source_type == "system":
            value = _path_get({"content_goal": content_goal}, source_path or key)

        if value is _MISSING:
            for alternative in slot.get("alternative_sources") or []:
                value = _path_get(
                    {"brief": brief, "variables": variables, "persona": persona},
                    alternative.get("source_path"),
                )
                if value is not _MISSING:
                    source_type = alternative.get("source_type", source_type)
                    source_path = alternative.get("source_path")
                    break

        # 标题槽位必须是可直接渲染的标量。列表来源按稳定顺序取第一个值，
        # 完整列表仍保留在 ContentBrief/EvidenceBundle 中供正文使用。
        if usage == "title" and isinstance(value, list) and value:
            value = value[0]

        evidence_required = bool(slot.get("evidence_required"))
        required = bool(slot.get("required", True))
        fallback = slot.get("fallback_policy", "block")
        if _has_value(value) and evidence_required and not evidence_matches:
            return _SlotResult(
                key,
                "blocked",
                None,
                source_type,
                source_path,
                (),
                lexicon_entry_id,
                f"槽位 {key} 需要证据，但 EvidenceBundle 中没有可用于 {usage} 的已确认来源",
            )
        if not _has_value(value):
            status = "blocked" if required and fallback in {"block", "ask_user"} else "missing"
            return _SlotResult(
                key,
                status,
                None,
                source_type,
                source_path,
                (),
                lexicon_entry_id,
                f"槽位 {key} 缺少值；处理策略：{fallback}",
            )

        max_length = slot.get("max_length")
        if max_length and len(str(value)) > int(max_length):
            return _SlotResult(
                key,
                "blocked",
                None,
                source_type,
                source_path,
                tuple(str(item.get("id")) for item in evidence_matches if item.get("id")),
                lexicon_entry_id,
                f"槽位 {key} 超过最大长度 {max_length}",
            )
        return _SlotResult(
            key,
            "resolved",
            value,
            source_type,
            source_path,
            tuple(str(item.get("id")) for item in evidence_matches if item.get("id")),
            lexicon_entry_id,
            None,
        )


class _StrictFormatMap(dict[str, Any]):
    def __missing__(self, key: str) -> Any:
        raise KeyError(key)


class LexiconResolver:
    """按企业 > 行业 > 渠道 > 平台解析同名词条并保留覆盖轨迹。"""

    _PRIORITY = {"platform": 0, "channel": 1, "industry": 2, "enterprise": 3}

    def resolve(
        self,
        versions: Iterable[dict[str, Any]],
        *,
        formula_code: str | None = None,
        slot_key: str | None = None,
    ) -> dict[str, Any]:
        candidates: list[dict[str, Any]] = []
        version_ids: list[str] = []
        for version in versions:
            version_ids.append(str(version.get("id")))
            for entry in version.get("entries") or []:
                formulas = entry.get("applicable_formula_codes") or []
                slots = entry.get("applicable_slot_keys") or []
                if formula_code and formulas and formula_code not in formulas:
                    continue
                if slot_key and slots and slot_key not in slots:
                    continue
                candidates.append(
                    {
                        **entry,
                        "pack_code": version.get("code"),
                        "lexicon_version_id": version.get("id"),
                        "scope_type": version.get("scope_type", "platform"),
                    }
                )
        candidates.sort(
            key=lambda item: (
                self._PRIORITY.get(str(item.get("scope_type")), -1),
                int(item.get("sort_order", 0)),
                str(item.get("id", "")),
            )
        )
        selected: dict[str, dict[str, Any]] = {}
        overrides: list[dict[str, Any]] = []
        for item in candidates:
            normalized = str(item.get("normalized_text") or item.get("text") or "").strip().lower()
            previous = selected.get(normalized)
            if previous:
                overrides.append({"normalized_text": normalized, "replaced": previous.get("id"), "selected": item.get("id")})
            selected[normalized] = item
        entries = sorted(selected.values(), key=lambda item: (item.get("sort_order", 0), item.get("id", "")))
        return {"version_ids": version_ids, "entries": entries, "overrides": overrides}


class ContentValueAnalyzer:
    """基于已存在事实构造 1～3 个可解释角度，不创造动态事实。"""

    _AXES = {
        "CT01": ["before_after_result", "process_to_result", "constraint_breakthrough"],
        "CT02": ["price_composition", "option_tradeoff", "hidden_cost"],
        "CT03": ["mistake_vs_correct", "risk_consequence", "information_gap"],
        "CT04": ["cost_vs_efficiency", "steps_to_result", "priority_tradeoff"],
        "CT05": ["detail_proves_capability", "process_reduces_risk", "standard_vs_shortcut"],
        "CT06": ["misconception_vs_fact", "concept_to_decision", "question_to_standard"],
        "CT07": ["experience_to_principle", "industry_pain_to_position", "boundary_builds_trust"],
    }

    def analyze(
        self,
        *,
        brief: dict[str, Any],
        evidence_bundle: dict[str, Any],
        content_types: Iterable[dict[str, Any]],
        preferred_content_type: str | None = None,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        variables = _brief_variables(brief)
        evidence = _evidence_items(evidence_bundle)
        evidence_ids = [str(item.get("id")) for item in evidence if item.get("id")]
        types = [item for item in content_types if item.get("enabled", True)]
        if preferred_content_type:
            types.sort(key=lambda item: item.get("code") != preferred_content_type)
        goal = brief.get("content_goal")
        types.sort(
            key=lambda item: (
                item.get("code") != preferred_content_type if preferred_content_type else False,
                goal not in (item.get("supported_goals") or []),
                item.get("sort_order", 0),
            )
        )
        results: list[dict[str, Any]] = []
        for content_type in types:
            code = str(content_type.get("code"))
            required = content_type.get("required_variable_codes") or []
            available = [key for key in required if _has_value(variables.get(key))]
            missing = [key for key in required if key not in available]
            axes = content_type.get("default_narrative_axes") or self._AXES.get(code, [])
            for axis in axes[:1]:
                digest = hashlib.sha1(f"{code}:{axis}:{brief.get('task_id', '')}".encode()).hexdigest()[:10]
                results.append(
                    {
                        "id": f"angle_{digest}",
                        "content_type_code": code,
                        "value_proposition": content_type.get("description") or content_type.get("name"),
                        "target_audience": brief.get("audience") or [],
                        "available_fact_keys": available,
                        "evidence_ids": evidence_ids,
                        "primary_conflict": axis,
                        "primary_narrative_axis": axis,
                        "risks": ["evidence_missing"] if not evidence_ids else [],
                        "missing_information": missing,
                        "recommendation_reason": (
                            f"内容目标 {goal or '未指定'} 与 {content_type.get('name')} 匹配；"
                            f"可用变量 {len(available)} 项、已确认来源 {len(evidence_ids)} 项"
                        ),
                    }
                )
            if len(results) >= limit:
                break
        return results[:limit]


class CombinationEngineV2:
    """先硬过滤再稳定评分的多维组合引擎。"""

    def __init__(self, slot_resolver: FormulaSlotResolver | None = None):
        self.slot_resolver = slot_resolver or FormulaSlotResolver()

    def recommend(
        self,
        bundle: dict[str, Any],
        *,
        brief: dict[str, Any],
        evidence_bundle: dict[str, Any],
        content_goal: str,
        content_type_code: str,
        industry_slug: str | None,
        channel_code: str | None,
        primary_narrative_axis: str,
        lexicon_entries: Iterable[dict[str, Any]] = (),
        persona: dict[str, Any] | None = None,
        limit: int = 5,
        random_seed: int = 0,
    ) -> dict[str, Any]:
        del random_seed  # 排序本身稳定；保留协议字段供未来等分候选抽样。
        patterns = {item["code"]: item for item in bundle.get("formula_patterns") or [] if item.get("enabled", True)}
        results: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []

        for rule in bundle.get("combination_rules") or []:
            hard_reasons = self._hard_filter(
                rule,
                content_goal=content_goal,
                content_type_code=content_type_code,
                industry_slug=industry_slug,
                channel_code=channel_code,
                primary_narrative_axis=primary_narrative_axis,
            )
            if hard_reasons:
                rejected.append({"rule_id": rule.get("id"), "reasons": hard_reasons})
                continue

            title_codes = rule.get("title_pattern_codes") or [
                code
                for code, pattern in patterns.items()
                if pattern.get("formula_kind") == "title"
                and pattern.get("formula_code") in (rule.get("title_formula_codes") or [])
            ]
            body_codes = rule.get("body_pattern_codes") or [
                code
                for code, pattern in patterns.items()
                if pattern.get("formula_kind") == "body"
                and pattern.get("formula_code") == rule.get("content_formula_code")
            ]
            if not title_codes or not body_codes:
                rejected.append({"rule_id": rule.get("id"), "reasons": ["规则没有可执行的标题或正文 Pattern"]})
                continue

            for title_code in sorted(title_codes):
                for body_code in sorted(body_codes):
                    title = patterns.get(title_code)
                    body = patterns.get(body_code)
                    if not title or not body:
                        rejected.append(
                            {"rule_id": rule.get("id"), "reasons": [f"Pattern 引用缺失：{title_code}/{body_code}"]}
                        )
                        continue
                    title_slots = self.slot_resolver.resolve(
                        title,
                        brief=brief,
                        evidence_bundle=evidence_bundle,
                        lexicon_entries=lexicon_entries,
                        persona=persona,
                        content_goal=content_goal,
                    )
                    body_slots = self.slot_resolver.resolve(
                        body,
                        brief=brief,
                        evidence_bundle=evidence_bundle,
                        lexicon_entries=lexicon_entries,
                        persona=persona,
                        content_goal=content_goal,
                    )
                    blocking = [*title_slots["blocking_reasons"], *body_slots["blocking_reasons"]]
                    score = self._score(rule, title_slots, body_slots)
                    results.append(
                        {
                            "rule_id": rule.get("id"),
                            "content_goal": content_goal,
                            "content_type_code": content_type_code,
                            "primary_narrative_axis": primary_narrative_axis,
                            "methods": rule.get("methods") or [],
                            "title_formula_code": title.get("formula_code"),
                            "title_pattern_code": title_code,
                            "body_formula_code": body.get("formula_code"),
                            "body_pattern_code": body_code,
                            "title_slot_plan": title_slots,
                            "body_slot_plan": body_slots,
                            "compatibility": "blocked" if blocking else (
                                "warning"
                                if title_slots["compatibility"] == "warning" or body_slots["compatibility"] == "warning"
                                else "compatible"
                            ),
                            "score": score,
                            "blocking_reasons": blocking,
                            "missing_slots": sorted(
                                set(title_slots["missing_slots"] + body_slots["missing_slots"])
                            ),
                            "recommendation_reason": rule.get("recommendation_reason") or "",
                        }
                    )

        results.sort(
            key=lambda item: (
                item["compatibility"] == "blocked",
                -item["score"],
                str(item["rule_id"]),
                item["title_pattern_code"],
                item["body_pattern_code"],
            )
        )
        viable = [item for item in results if item["compatibility"] != "blocked"]
        selected = viable[0] if viable else (results[0] if results else None)
        alternatives = [item for item in results if item is not selected][: max(0, limit - 1)]
        return {
            "compatibility": "blocked" if selected is None or selected["compatibility"] == "blocked" else "auto_matched",
            "selected": selected,
            "alternatives": alternatives,
            "rejected": rejected,
            "required_actions": self._required_actions(selected, rejected),
        }

    @staticmethod
    def _hard_filter(
        rule: dict[str, Any],
        *,
        content_goal: str,
        content_type_code: str,
        industry_slug: str | None,
        channel_code: str | None,
        primary_narrative_axis: str,
    ) -> list[str]:
        reasons: list[str] = []
        if rule.get("content_goal") != content_goal:
            reasons.append("内容目标不匹配")
        if rule.get("content_type_codes") and content_type_code not in rule["content_type_codes"]:
            reasons.append("内容类型不匹配")
        if rule.get("industry_scope") and industry_slug not in rule["industry_scope"]:
            reasons.append("行业范围不匹配")
        if rule.get("channel_scope") and channel_code not in rule["channel_scope"]:
            reasons.append("渠道范围不匹配")
        if rule.get("narrative_axis_codes") and primary_narrative_axis not in rule["narrative_axis_codes"]:
            reasons.append("主要叙事轴不匹配")
        if rule.get("compatibility") == "blocked":
            reasons.append("规则被明确标记为阻断")
        return reasons

    @staticmethod
    def _score(rule: dict[str, Any], title_slots: dict[str, Any], body_slots: dict[str, Any]) -> float:
        weights = rule.get("score_weights") or {}
        score = float(rule.get("priority", 0))
        score += float(weights.get("title_slot_complete", 10)) * (not title_slots["missing_slots"])
        score += float(weights.get("body_slot_complete", 10)) * (not body_slots["missing_slots"])
        score -= float(weights.get("missing_slot_penalty", 20)) * len(
            set(title_slots["missing_slots"] + body_slots["missing_slots"])
        )
        return round(score, 4)

    @staticmethod
    def _required_actions(selected: dict[str, Any] | None, rejected: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if selected is None:
            return [{"action": "choose_alternative", "message": "没有规则通过硬约束，请调整目标、类型或渠道"}]
        actions = [
            {"action": "provide_slot", "slot_key": key, "message": f"补充公式槽位 {key}"}
            for key in selected.get("missing_slots") or []
        ]
        if selected.get("blocking_reasons"):
            actions.extend(
                {"action": "confirm_evidence", "message": reason}
                for reason in selected["blocking_reasons"]
            )
        if not actions and rejected:
            actions.append({"action": "none", "message": "已自动选择通过硬约束且得分最高的组合"})
        return actions


class NarrativeConsistencyChecker:
    def check(self, primary_axis: str | None, detected_axes: Iterable[str]) -> dict[str, Any]:
        axes = list(dict.fromkeys(axis for axis in detected_axes if axis))
        conflicting = [axis for axis in axes if axis != primary_axis]
        checks: list[dict[str, Any]] = []
        if not primary_axis:
            checks.append({"code": "NARRATIVE_AXIS_MISSING", "level": "error", "message": "未锁定主要叙事轴"})
        if conflicting:
            checks.append(
                {
                    "code": "NARRATIVE_AXIS_CONFLICT",
                    "level": "error",
                    "message": f"检测到与主要叙事轴竞争的逻辑：{', '.join(conflicting)}",
                    "conflicting_axes": conflicting,
                }
            )
        return {"status": "blocked" if checks else "passed", "primary_axis": primary_axis, "checks": checks}


class ComplianceEngine:
    """执行版本化渠道/行业/企业合规规则并返回替换差异。"""

    def validate_and_adapt(
        self,
        *,
        title: str,
        body: str,
        topics: list[str],
        channel_profile: dict[str, Any],
        policies: Iterable[dict[str, Any]],
    ) -> dict[str, Any]:
        output = {"title": title, "body": body, "topics": list(topics)}
        checks: list[dict[str, Any]] = []
        diffs: list[dict[str, Any]] = []
        self._check_length("title", title, channel_profile.get("title_constraints") or {}, checks)
        self._check_length("body", body, channel_profile.get("body_constraints") or {}, checks)
        topic_rules = channel_profile.get("topic_constraints") or {}
        maximum_topics = topic_rules.get("max_count")
        if maximum_topics is not None and len(topics) > int(maximum_topics):
            checks.append(
                {"code": "CHANNEL_TOPIC_COUNT", "level": "error", "location": "topics", "message": f"话题数量超过 {maximum_topics}"}
            )

        for policy in policies:
            for rule in policy.get("rules") or []:
                if not rule.get("enabled", True):
                    continue
                for location in ("title", "body"):
                    source = output[location]
                    matches = self._find_matches(source, rule)
                    if not matches:
                        continue
                    action = rule.get("action", "warn")
                    level = "error" if action in {"block", "confirm"} else "warning"
                    if action == "replace" and rule.get("replacement") is not None:
                        replaced = self._replace(source, rule)
                        if self._numeric_meaning_changed(source, replaced):
                            checks.append(
                                {
                                    "code": "UNSAFE_AUTO_REPLACEMENT",
                                    "level": "error",
                                    "location": location,
                                    "message": f"规则 {rule.get('rule_code')} 的替换会改变数字或事实含义",
                                    "rule_id": rule.get("id"),
                                }
                            )
                        else:
                            output[location] = replaced
                            diffs.append(
                                {"location": location, "before": source, "after": replaced, "rule_id": rule.get("id")}
                            )
                    else:
                        checks.append(
                            {
                                "code": rule.get("rule_code") or "COMPLIANCE_RULE_MATCH",
                                "level": level,
                                "location": location,
                                "message": rule.get("explanation") or f"命中合规规则：{rule.get('pattern')}",
                                "rule_id": rule.get("id"),
                                "human_confirmation_required": bool(rule.get("human_confirmation_required")) or action == "confirm",
                            }
                        )
        status = "blocked" if any(item["level"] == "error" for item in checks) else (
            "warning" if checks or diffs else "passed"
        )
        return {"status": status, **output, "checks": checks, "replacement_diffs": diffs}

    @staticmethod
    def _check_length(location: str, text: str, config: dict[str, Any], checks: list[dict[str, Any]]) -> None:
        minimum = config.get("min_length")
        maximum = config.get("max_length")
        if minimum is not None and len(text) < int(minimum):
            checks.append({"code": f"CHANNEL_{location.upper()}_SHORT", "level": "warning", "location": location, "message": f"{location} 少于 {minimum} 字"})
        if maximum is not None and len(text) > int(maximum):
            checks.append({"code": f"CHANNEL_{location.upper()}_LONG", "level": "error", "location": location, "message": f"{location} 超过 {maximum} 字"})

    @staticmethod
    def _find_matches(text: str, rule: dict[str, Any]) -> list[str]:
        pattern = str(rule.get("pattern") or "")
        if not pattern:
            return []
        if rule.get("match_type") == "regex":
            try:
                return re.findall(pattern, text)
            except re.error:
                return []
        return [pattern] if pattern in text else []

    @staticmethod
    def _replace(text: str, rule: dict[str, Any]) -> str:
        pattern = str(rule.get("pattern") or "")
        replacement = str(rule.get("replacement") or "")
        if rule.get("match_type") == "regex":
            try:
                return re.sub(pattern, replacement, text)
            except re.error:
                return text
        return text.replace(pattern, replacement)

    @staticmethod
    def _numeric_meaning_changed(before: str, after: str) -> bool:
        return _NUMBER_RE.findall(before) != _NUMBER_RE.findall(after)


def validate_numeric_evidence_coverage(text: str, evidence_bundle: dict[str, Any]) -> dict[str, Any]:
    """所有事实性数字必须能在已确认 EvidenceItem 的原文或 values 中找到。"""

    claims = _NUMBER_RE.findall(text)
    supported: set[str] = set()
    evidence_ids_by_claim: dict[str, list[str]] = {}
    for item in _evidence_items(evidence_bundle):
        if item.get("verified_status") in {"rejected", "unverified", "blocked"}:
            continue
        haystack = " ".join(
            str(value)
            for value in (item.get("content"), item.get("value"), item.get("values"), item.get("metadata"))
            if value is not None
        )
        for claim in claims:
            if claim in haystack:
                supported.add(claim)
                if item.get("id"):
                    evidence_ids_by_claim.setdefault(claim, []).append(str(item["id"]))
    unsupported = sorted(set(claims) - supported)
    return {
        "status": "blocked" if unsupported else "passed",
        "claims": claims,
        "unsupported_claims": unsupported,
        "evidence_ids_by_claim": evidence_ids_by_claim,
        "checks": [
            {
                "code": "NUMERIC_CLAIM_UNSUPPORTED",
                "level": "error",
                "location": "content",
                "message": f"数字 {claim} 没有已确认来源",
            }
            for claim in unsupported
        ],
    }
