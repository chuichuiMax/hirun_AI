"""正文模型视图：审计快照保留在服务端，模型只读取本次创作所需内容。"""

import json
from copy import deepcopy
from typing import Any

from yuxi.content.model.contracts.content_nodes import GenerateContentPromptV1, PlanVisualsPromptV1

_MAX_LEXICON_CHUNKS = 1
_MAX_LEXICON_CHUNK_CHARS = 80
_MAX_EVIDENCE_VALUE_CHARS = 48
_MAX_FORBIDDEN_MAP_ROWS = 16
_MAX_FORBIDDEN_ALTERNATIVES = 1
_MAX_METHOD_PATTERNS = 1
_MAX_REFERENCE_EXAMPLES = 1
_MAX_WRITING_INSTRUCTION_CHARS = 180
_MAX_EVIDENCE_ITEMS = 16
_MAX_GENERATION_PROMPT_CHARS = 10000
_MAX_REVIEW_NOTES_GENERATION_PROMPT_CHARS = 4000
_MAX_REVIEW_NOTES_STYLE_EXCERPTS = 2
_MAX_REVIEW_NOTES_STYLE_CHARS = 400
_MAX_REVIEW_NOTES_EVIDENCE_ITEMS = 8
_MAX_REVIEW_NOTES_EVIDENCE_VALUE_CHARS = 40
_MAX_REVIEW_NOTES_FORBIDDEN_ROWS = 8
_REVIEW_NOTES_BRIEF_KEEP = frozenset(
    {
        "mp_service_entry",
        "writing_instruction",
        "voice",
        "location",
        "brand_name",
        "persona",
        "所在区域",
        "所属店面",
        "门店",
        "设计师",
        "预算师",
        "项目经理",
        "客户经理",
        "工匠",
        "mp_content_code",
    }
)
_MAX_BODY_CALLING_INSTRUCTION_CHARS = 120
_MAX_BODY_CALLING_FILL_RULE_CHARS = 90
_MAX_VISUAL_BODY_CHARS = 280
_MAX_VISUAL_EVIDENCE_ITEMS = 8
_MAX_VISUAL_EVIDENCE_VALUE_CHARS = 40
_MAX_VISUAL_FORBIDDEN_ROWS = 12
_FILLABLE_CONSTRAINT_KEYS = ("maxChars", "maxCharsPerLine", "maxLines", "required", "layoutMeasured")
_EVIDENCE_ITEM_DROP_FIELDS = (
    "source_hash",
    "source_version",
    "created_at",
    "citations",
    "source_id",
)
_EVIDENCE_METADATA_KEEP = frozenset(
    {
        "material_type",
        "rule_kind",
        "selected_reference",
        "reference_blueprint",
        "price_basis",
        "scope",
    }
)
_BRIEF_DROP_KEYS = {
    "mp_content_type_id",
    "attachments",
    "visual_material",
}
_BRIEF_EMPTY_LIST_KEYS = {
    "required_terms",
    "forbidden_terms",
    "attachments",
    "locked_fields",
    "audience",
}


def _trim_text(value: object, limit: int) -> object:
    if not isinstance(value, str) or len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def _is_forbidden_replacement_map(item: dict) -> bool:
    metadata = item.get("metadata")
    return isinstance(metadata, dict) and metadata.get("rule_kind") == "forbidden_replacement_map"


def _compact_forbidden_replacement_value(value: object) -> object:
    """压缩封禁词表体积，保留问题词与有限候选，避免整表撑爆首包。"""
    rows: list[Any]
    if isinstance(value, list):
        rows = value
    elif isinstance(value, dict):
        nested = value.get("rows") or value.get("items") or value.get("mappings")
        if isinstance(nested, list):
            rows = nested
        else:
            rows = [{"problem_term": key, "alternatives": alt} for key, alt in value.items()]
    else:
        return _trim_text(value, 4000) if isinstance(value, str) else value

    compacted: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if len(compacted) >= _MAX_FORBIDDEN_MAP_ROWS:
            break
        if isinstance(row, str):
            term = row.strip()
            alternatives: list[str] = []
        elif isinstance(row, dict):
            term = ""
            for key in ("problem_term", "problem", "term", "问题词"):
                raw = row.get(key)
                if isinstance(raw, str) and raw.strip():
                    term = raw.strip()
                    break
            raw_alts = row.get("alternatives")
            if raw_alts is None:
                raw_alts = row.get("常用表达方式")
            if isinstance(raw_alts, str):
                alternatives = [part.strip() for part in raw_alts.replace("、", ",").split(",") if part.strip()]
            elif isinstance(raw_alts, list):
                alternatives = [str(item).strip() for item in raw_alts if str(item).strip()]
            else:
                alternatives = []
        else:
            continue
        if not term or term in seen:
            continue
        seen.add(term)
        compacted.append(
            {
                "problem_term": term,
                "alternatives": alternatives[:_MAX_FORBIDDEN_ALTERNATIVES],
            }
        )
    return compacted


def _prompt_chars(payload: dict[str, Any]) -> int:
    return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def is_review_notes_generation(payload: dict[str, Any]) -> bool:
    brief = payload.get("content_brief") if isinstance(payload.get("content_brief"), dict) else {}
    form_values = brief.get("form_values") if isinstance(brief.get("form_values"), dict) else {}
    variables = brief.get("business_variables") if isinstance(brief.get("business_variables"), dict) else {}
    return str(form_values.get("mp_service_entry") or variables.get("mp_service_entry") or "") == "好评笔记"


def attach_review_notes_style_excerpts(payload: dict[str, Any], excerpts: list[str]) -> dict[str, Any]:
    """把服务端预取的好评语气样例写入简报，供一次直出模仿，不进入 Evidence ID。"""
    brief = payload.setdefault("content_brief", {})
    if not isinstance(brief, dict):
        return payload
    cleaned = [
        str(_trim_text(item.strip(), _MAX_REVIEW_NOTES_STYLE_CHARS))
        for item in excerpts
        if isinstance(item, str) and item.strip()
    ][:_MAX_REVIEW_NOTES_STYLE_EXCERPTS]
    if cleaned:
        brief["style_excerpts"] = cleaned
    return payload


def _slim_named_entries(entries: object) -> list:
    if not isinstance(entries, list):
        return []
    slim: list[Any] = []
    for item in entries:
        if isinstance(item, dict):
            entry = {
                key: _trim_text(item[key], 40) if key == "name" else item[key]
                for key in ("id", "code", "name", "required")
                if key in item
            }
            if entry:
                slim.append(entry)
        elif isinstance(item, str):
            slim.append(_trim_text(item, 40))
    return slim


def _slim_body_calling(calling: object) -> object:
    if not isinstance(calling, dict):
        return calling
    slim: dict[str, Any] = {
        "formula_name": calling.get("formula_name"),
        "lexicon_calls": list(calling.get("lexicon_calls") or []),
        "variation_rule": calling.get("variation_rule"),
        "reference_examples": list(calling.get("reference_examples") or [])[:_MAX_REFERENCE_EXAMPLES],
        "sections": [],
        "variants": [],
    }
    for section in calling.get("sections") or []:
        if not isinstance(section, dict):
            continue
        slim["sections"].append(
            {
                "id": section.get("id"),
                "name": section.get("name"),
                "instruction": _trim_text(section.get("instruction"), _MAX_BODY_CALLING_INSTRUCTION_CHARS),
                "fill_rule": _trim_text(section.get("fill_rule"), _MAX_BODY_CALLING_FILL_RULE_CHARS),
                "lexicon_calls": list(section.get("lexicon_calls") or []),
                "fact_source": section.get("fact_source"),
            }
        )
    for variant in calling.get("variants") or []:
        if not isinstance(variant, dict):
            continue
        slim["variants"].append(
            {
                "id": variant.get("id"),
                "name": variant.get("name"),
                "instruction": _trim_text(variant.get("instruction"), 100),
                "lexicon_calls": list(variant.get("lexicon_calls") or []),
            }
        )
    return slim


def _slim_strategy_snapshot(strategy: dict[str, Any]) -> dict[str, Any]:
    """去掉审计型大字段，只保留生成所需的公式与手法约束。"""
    title = dict(strategy.get("title_formula") or {})
    body = dict(strategy.get("body_formula") or {})
    methods = []
    for item in strategy.get("creation_method_definitions") or []:
        if not isinstance(item, dict):
            continue
        methods.append(
            {
                "code": item.get("code"),
                "name": item.get("name"),
                "method_type": item.get("method_type"),
                "principle": _trim_text(item.get("principle"), 100),
                "sentence_patterns": list(item.get("sentence_patterns") or [])[:_MAX_METHOD_PATTERNS],
                "risk_rules": list(item.get("risk_rules") or [])[:3],
            }
        )
    strategy["creation_method_definitions"] = methods
    strategy["title_formula"] = {
        "code": title.get("code"),
        "name": title.get("name"),
        "core_goal": _trim_text(title.get("core_goal"), 100),
        "reference_examples": list(title.get("reference_examples") or [])[:_MAX_REFERENCE_EXAMPLES],
        "variable_schema": _slim_named_entries(title.get("variable_schema")),
        "compatible_methods": title.get("compatible_methods") or [],
        "risk_rules": list(title.get("risk_rules") or [])[:3],
        "lexicon_codes": title.get("lexicon_codes") or [],
    }
    strategy["body_formula"] = {
        "code": body.get("code"),
        "name": body.get("name"),
        "structure_schema": _slim_named_entries(body.get("structure_schema")),
        "reference_examples": list(body.get("reference_examples") or [])[:_MAX_REFERENCE_EXAMPLES],
        "required_variables": _slim_named_entries(body.get("required_variables"))
        if isinstance(body.get("required_variables"), list)
        else body.get("required_variables") or [],
        "compatible_methods": body.get("compatible_methods") or [],
        "risk_rules": list(body.get("risk_rules") or [])[:3],
        "lexicon_codes": body.get("lexicon_codes") or [],
        "body_calling": _slim_body_calling(body.get("body_calling")),
    }
    strategy.pop("body_calling_source", None)
    strategy.pop("decision", None)
    return strategy


def _slim_content_brief(brief: dict[str, Any]) -> None:
    """去掉与 business_variables 重复的 form_values，并裁掉写作无用字段。"""
    brief.pop("visual_material", None)
    brief.pop("form_values", None)
    brief.pop("persona", None)
    for key in list(brief):
        if key.endswith("_version_id"):
            del brief[key]
        elif key in _BRIEF_EMPTY_LIST_KEYS and brief.get(key) in ([], None, {}):
            del brief[key]
    variables = brief.get("business_variables")
    if not isinstance(variables, dict):
        return
    for key in list(variables):
        if key.endswith("_version_id") or key in _BRIEF_DROP_KEYS:
            del variables[key]
            continue
        value = variables[key]
        if value in ("", None, [], {}):
            del variables[key]
            continue
        if key == "writing_instruction":
            variables[key] = _trim_text(value, _MAX_WRITING_INSTRUCTION_CHARS)


def _evidence_value_key(value: object) -> str | None:
    if isinstance(value, str):
        normalized = " ".join(value.split())
        return normalized or None
    if isinstance(value, (int, float, bool)):
        return str(value)
    return None


def _merge_unique(existing: list[Any], incoming: list[Any]) -> list[Any]:
    merged = list(existing)
    seen = {str(item) for item in existing}
    for item in incoming:
        token = str(item)
        if token in seen:
            continue
        seen.add(token)
        merged.append(item)
    return merged


def _dedupe_evidence_items(items: list) -> list[dict[str, Any]]:
    """同值证据只留一条供模型阅读；冻结包本身不改。"""
    kept: list[dict[str, Any]] = []
    by_value: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        if _is_forbidden_replacement_map(item):
            kept.append(item)
            continue
        key = _evidence_value_key(item.get("value"))
        if key is None:
            kept.append(item)
            continue
        existing = by_value.get(key)
        if existing is None:
            by_value[key] = item
            kept.append(item)
            continue
        existing["allowed_usage"] = _merge_unique(
            list(existing.get("allowed_usage") or []),
            list(item.get("allowed_usage") or []),
        )
        existing_codes = list(existing.get("variable_codes") or [])
        incoming_codes = list(item.get("variable_codes") or [])
        if existing_codes or incoming_codes:
            existing["variable_codes"] = _merge_unique(existing_codes, incoming_codes)
    return kept


def _slim_evidence_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    slim = {key: metadata[key] for key in _EVIDENCE_METADATA_KEEP if key in metadata}
    blueprint = slim.get("reference_blueprint")
    if isinstance(blueprint, dict):
        slim["reference_blueprint"] = {
            key: blueprint.get(key)
            for key in (
                "title_pattern",
                "opening_hook",
                "content_block_sequence",
                "paragraph_rhythm",
                "list_pattern",
                "emoji_pattern",
                "interaction_style",
            )
            if key in blueprint
        }
    return slim


def _slim_evidence_item(item: dict[str, Any], *, creation_mode: str) -> None:
    for field in _EVIDENCE_ITEM_DROP_FIELDS:
        item.pop(field, None)
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    material_type = str(metadata.get("material_type") or "")
    if _is_forbidden_replacement_map(item):
        item["value"] = _compact_forbidden_replacement_value(item.get("value"))
        item["metadata"] = _slim_evidence_metadata(metadata)
        return
    if material_type == "viral_example":
        if creation_mode == "original" and metadata.get("selected_reference") is not True:
            item["value"] = _trim_text(item.get("value"), 40)
        else:
            item["value"] = _trim_text(item.get("value"), _MAX_EVIDENCE_VALUE_CHARS)
        item["metadata"] = _slim_evidence_metadata(metadata)
        return
    if "value" in item:
        item["value"] = _trim_text(item.get("value"), _MAX_EVIDENCE_VALUE_CHARS)
    if metadata:
        item["metadata"] = _slim_evidence_metadata(metadata)
    else:
        item.pop("metadata", None)


def _filter_evidence_for_generation(items: list, *, creation_mode: str) -> list[dict[str, Any]]:
    """模型视图只留写作需要的证据；原创丢掉未选中的爆款原文。"""
    kept: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        if item.get("verified_status") == "rejected":
            continue
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        material_type = str(metadata.get("material_type") or "")
        if (
            creation_mode == "original"
            and material_type == "viral_example"
            and metadata.get("selected_reference") is not True
        ):
            continue
        if _is_forbidden_replacement_map(item):
            kept.append(item)
            continue
        usage = set(item.get("allowed_usage") or [])
        if usage & {"title", "body"} or material_type in {"brand", "price", "business_fact", "knowledge"}:
            kept.append(item)
        else:
            deferred.append(item)
    remaining = max(0, _MAX_EVIDENCE_ITEMS - len(kept))
    if remaining:
        kept.extend(deferred[:remaining])
    return kept[:_MAX_EVIDENCE_ITEMS]


def compact_evidence_items_for_bundle(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """冻结/合并前压缩大字段：封禁词表与过长 value，不改 Evidence ID。"""
    compacted: list[dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        item = deepcopy(raw)
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        if _is_forbidden_replacement_map(item):
            item["value"] = _compact_forbidden_replacement_value(item.get("value"))
        elif isinstance(item.get("value"), str) and len(item["value"]) > 500:
            # 冻结包保留比模型视图更长的摘录，但仍截断异常长知识片段。
            item["value"] = _trim_text(item["value"], 500)
        if metadata:
            item["metadata"] = _slim_evidence_metadata(metadata)
        compacted.append(item)
    return compacted


def project_generation_input(payload: dict) -> dict:
    # 调用方必须先完成 GenerateContentInputV1 校验（包括冻结策略 hash）。
    projected = deepcopy(payload)
    review_notes = is_review_notes_generation(projected)
    creation_mode = payload["runtime_config_snapshot"].get("creation_mode", "original")
    strategy = projected["strategy_snapshot"]
    strategy.pop("decision", None)
    strategy["source_snapshot_hash"] = strategy.pop("snapshot_hash")
    projected["strategy_snapshot"] = _slim_strategy_snapshot(strategy)
    projected["runtime_config_snapshot"] = {
        "creation_mode": creation_mode,
    }
    _slim_content_brief(projected["content_brief"])
    evidence_items = projected["evidence_bundle"].get("items", [])
    for item in evidence_items:
        if isinstance(item, dict):
            _slim_evidence_item(item, creation_mode=creation_mode)
    evidence_items = _dedupe_evidence_items(evidence_items)
    evidence_items = _filter_evidence_for_generation(evidence_items, creation_mode=creation_mode)
    projected["evidence_bundle"]["items"] = evidence_items
    # 模型直接读 items[].id / allowed_usage；不再附带重复 cite 索引。
    projected["evidence_cite_index"] = None
    lexicon = projected.get("formula_lexicon_bundle") or {}
    for scope in ("title", "body"):
        entries = lexicon.get(scope)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            chunks = entry.get("chunks")
            if not isinstance(chunks, list):
                continue
            entry["chunks"] = [
                _trim_text(chunk, _MAX_LEXICON_CHUNK_CHARS) for chunk in chunks[:_MAX_LEXICON_CHUNKS] if chunk
            ]
            for heavy in ("source_heading", "raw_text", "document_text", "document_id", "kb_id"):
                entry.pop(heavy, None)
    # 渠道/人设只保留生成约束，去掉连接器等无关配置。
    channel = projected.get("channel_profile") or {}
    projected["channel_profile"] = {
        key: channel.get(key)
        for key in (
            "emoji_allowed",
            "title_constraints",
            "body_constraints",
            "topic_constraints",
            "cta_policy",
        )
        if key in channel
    }
    persona = projected.get("persona_profile") or {}
    projected["persona_profile"] = {
        key: persona.get(key)
        for key in ("name", "voice", "tone", "forbidden_expressions", "style_notes")
        if key in persona
    }
    # 首轮生成不带空壳回修字段，避免无用 schema 噪声。
    for optional in ("validation_report", "review_report", "selected_title", "content_outline", "content_draft"):
        value = projected.get(optional)
        if value in (None, {}, []):
            projected[optional] = None
    dumped = GenerateContentPromptV1.model_validate(projected).model_dump(mode="json")
    if review_notes:
        return _finalize_review_notes_generation(dumped)
    return _fit_generation_prompt(dumped)


def _finalize_review_notes_generation(projected: dict[str, Any]) -> dict[str, Any]:
    """好评笔记不读装修公式/词库；样例已预取进 style_excerpts，视图压到约 4000 字。"""
    strategy = projected.get("strategy_snapshot") or {}
    title = strategy.get("title_formula") if isinstance(strategy.get("title_formula"), dict) else {}
    body = strategy.get("body_formula") if isinstance(strategy.get("body_formula"), dict) else {}
    projected["strategy_snapshot"] = {
        "title_formula": {"code": title.get("code")},
        "body_formula": {"code": body.get("code")},
        "source_snapshot_hash": strategy.get("source_snapshot_hash"),
    }
    projected["formula_lexicon_bundle"] = {}
    brief = projected.get("content_brief") if isinstance(projected.get("content_brief"), dict) else {}
    variables = brief.get("business_variables") if isinstance(brief.get("business_variables"), dict) else {}
    brief["business_variables"] = {key: value for key, value in variables.items() if key in _REVIEW_NOTES_BRIEF_KEEP}
    excerpts = brief.get("style_excerpts")
    if isinstance(excerpts, list):
        brief["style_excerpts"] = [
            str(_trim_text(str(item).strip(), _MAX_REVIEW_NOTES_STYLE_CHARS)) for item in excerpts if str(item).strip()
        ][:_MAX_REVIEW_NOTES_STYLE_EXCERPTS]
    elif "style_excerpts" in brief:
        brief.pop("style_excerpts", None)
    projected["content_brief"] = brief
    items = projected.get("evidence_bundle", {}).get("items")
    if isinstance(items, list):
        kept: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if _is_forbidden_replacement_map(item):
                value = item.get("value")
                if isinstance(value, list):
                    item["value"] = value[:_MAX_REVIEW_NOTES_FORBIDDEN_ROWS]
                kept.append(item)
                continue
            usage = set(item.get("allowed_usage") or [])
            if usage & {"title", "body"}:
                if isinstance(item.get("value"), str):
                    item["value"] = _trim_text(item["value"], _MAX_REVIEW_NOTES_EVIDENCE_VALUE_CHARS)
                kept.append(item)
        projected["evidence_bundle"]["items"] = kept[:_MAX_REVIEW_NOTES_EVIDENCE_ITEMS]
    channel = projected.get("channel_profile") or {}
    projected["channel_profile"] = {
        key: channel.get(key) for key in ("emoji_allowed", "title_constraints") if key in channel
    }
    persona = projected.get("persona_profile") or {}
    projected["persona_profile"] = {key: persona.get(key) for key in ("name", "voice", "tone") if key in persona}
    return _fit_generation_prompt(projected, max_chars=_MAX_REVIEW_NOTES_GENERATION_PROMPT_CHARS)


def _fit_generation_prompt(
    projected: dict[str, Any],
    *,
    max_chars: int = _MAX_GENERATION_PROMPT_CHARS,
) -> dict[str, Any]:
    """硬顶字数：先丢低优先级证据，再压词库/样例，避免首包被整包证据撑爆。"""
    items = projected.get("evidence_bundle", {}).get("items")
    if not isinstance(items, list):
        return projected
    floor = 4 if max_chars <= _MAX_REVIEW_NOTES_GENERATION_PROMPT_CHARS else 8
    while _prompt_chars(projected) > max_chars and len(items) > floor:
        drop_at = next(
            (index for index in range(len(items) - 1, -1, -1) if not _is_forbidden_replacement_map(items[index])),
            None,
        )
        if drop_at is None:
            break
        items.pop(drop_at)
    if _prompt_chars(projected) <= max_chars:
        return projected
    brief = projected.get("content_brief") if isinstance(projected.get("content_brief"), dict) else {}
    excerpts = brief.get("style_excerpts")
    if isinstance(excerpts, list) and excerpts:
        brief["style_excerpts"] = [str(_trim_text(str(item), 200)) for item in excerpts[:1] if str(item).strip()]
        projected["content_brief"] = brief
    if _prompt_chars(projected) > max_chars:
        projected["evidence_bundle"]["items"] = [
            item for item in items if isinstance(item, dict) and not _is_forbidden_replacement_map(item)
        ][:floor]
    lexicon = projected.get("formula_lexicon_bundle") or {}
    for scope in ("title", "body"):
        entries = lexicon.get(scope)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("chunks"), list):
                continue
            entry["chunks"] = [_trim_text(chunk, 40) for chunk in entry["chunks"][:1] if chunk]
    return projected


def _slim_fillable_field(field: dict[str, Any]) -> dict[str, Any]:
    slim = {key: field[key] for key in ("key", "label", "semanticRole", "kind") if key in field}
    constraints = field.get("constraints")
    if isinstance(constraints, dict):
        slim["constraints"] = {key: constraints[key] for key in _FILLABLE_CONSTRAINT_KEYS if key in constraints}
    return slim


def _filter_evidence_for_visuals(items: list) -> list[dict[str, Any]]:
    """封面只读标题事实、品牌/价格卡点和压缩后的封禁词，不读正文知识长文。"""
    kept: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        if item.get("verified_status") == "rejected":
            continue
        if _is_forbidden_replacement_map(item):
            value = item.get("value")
            if isinstance(value, list):
                item["value"] = value[:_MAX_VISUAL_FORBIDDEN_ROWS]
            kept.append(item)
            continue
        usage = set(item.get("allowed_usage") or [])
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        material_type = str(metadata.get("material_type") or "")
        if usage & {"title", "visual"} or material_type in {"brand", "price", "business_fact"}:
            kept.append(item)
    return kept[:_MAX_VISUAL_EVIDENCE_ITEMS]


def _project_visual_evidence_item(item: dict[str, Any]) -> dict[str, Any]:
    projected = {"id": item.get("id"), "value": item.get("value")}
    if isinstance(projected["value"], str):
        projected["value"] = _trim_text(projected["value"], _MAX_VISUAL_EVIDENCE_VALUE_CHARS)
    if item.get("variable_codes"):
        projected["variable_codes"] = item["variable_codes"]
    return projected


def project_visual_plan_input(payload: dict) -> dict:
    """封面规划只看标题、短正文、模板框和封面事实，不把生成节点的整包策略再喂一遍。"""
    projected = deepcopy(payload)
    strategy = projected.get("strategy_snapshot") or {}
    title_formula = strategy.get("title_formula") or {}
    body_formula = strategy.get("body_formula") or {}
    projected["strategy_snapshot"] = {
        "title_formula": {"code": title_formula.get("code")},
        "body_formula": {"code": body_formula.get("code")},
    }
    evidence_items = projected.get("evidence_bundle", {}).get("items", [])
    for item in evidence_items:
        if isinstance(item, dict):
            _slim_evidence_item(item, creation_mode="original")
    visual_items = [
        _project_visual_evidence_item(item)
        for item in _filter_evidence_for_visuals(_dedupe_evidence_items(evidence_items))
    ]
    projected["evidence_bundle"] = {"items": visual_items}
    draft = dict(projected.get("content_draft") or {})
    projected["content_draft"] = {
        "body": _trim_text(draft.get("body"), _MAX_VISUAL_BODY_CHARS) if draft.get("body") else draft.get("body")
    }
    title = dict(projected.get("selected_title") or {})
    projected["selected_title"] = {key: title.get(key) for key in ("text", "evidence_ids") if key in title} or title
    channel = projected.get("channel_profile") or {}
    projected["channel_profile"] = {key: channel.get(key) for key in ("emoji_allowed",) if key in channel}
    runtime = dict(projected.get("runtime_config_snapshot") or {})
    visual = dict(runtime.get("visual_material") or {})
    format_ = visual.get("format") if isinstance(visual.get("format"), dict) else {}
    fillable = [
        _slim_fillable_field(field) for field in visual.get("hycanvas_fillable_fields") or [] if isinstance(field, dict)
    ]
    visual_material = {
        key: visual.get(key)
        for key in ("image_asset_id", "template_id", "required_template_field_repairs")
        if key in visual
    }
    if fillable or "hycanvas_fillable_fields" in visual:
        visual_material["hycanvas_fillable_fields"] = fillable
    projected["runtime_config_snapshot"] = {
        "visual_material": visual_material,
        "canvas": {
            "width": int(format_.get("width") or 1080),
            "height": int(format_.get("height") or 1440),
            "safe_area": {"top": 20, "right": 20, "bottom": 20, "left": 20},
        },
    }
    media: list[dict[str, Any]] = []
    for item in projected.get("media_evidence_items") or []:
        if not isinstance(item, dict):
            continue
        media.append({key: item.get(key) for key in ("id", "selected_for_cover") if key in item})
    selected = [item for item in media if item.get("selected_for_cover")]
    projected["media_evidence_items"] = selected or media
    artifact = dict(projected.get("artifact_version") or {})
    if artifact.get("id"):
        projected["artifact_version"] = {"id": artifact.get("id")}
    return PlanVisualsPromptV1.model_validate(projected).model_dump(mode="json")
