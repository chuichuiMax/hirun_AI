"""正文模型视图：审计快照保留在服务端，模型只读取本次创作所需内容。"""

from copy import deepcopy
from typing import Any

from yuxi.content.model.contracts.content_nodes import GenerateContentPromptV1, PlanVisualsPromptV1

_MAX_LEXICON_CHUNKS = 1
_MAX_LEXICON_CHUNK_CHARS = 220
_MAX_EVIDENCE_VALUE_CHARS = 120
_MAX_FORBIDDEN_MAP_ROWS = 40
_MAX_FORBIDDEN_ALTERNATIVES = 2
_MAX_METHOD_PATTERNS = 3
_MAX_REFERENCE_EXAMPLES = 1
_MAX_WRITING_INSTRUCTION_CHARS = 400
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
                "instruction": _trim_text(section.get("instruction"), 220),
                "fill_rule": _trim_text(section.get("fill_rule"), 180),
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
                "instruction": _trim_text(variant.get("instruction"), 160),
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
                "principle": _trim_text(item.get("principle"), 160),
                "sentence_patterns": list(item.get("sentence_patterns") or [])[:_MAX_METHOD_PATTERNS],
                "risk_rules": list(item.get("risk_rules") or [])[:3],
            }
        )
    strategy["creation_method_definitions"] = methods
    strategy["title_formula"] = {
        "code": title.get("code"),
        "name": title.get("name"),
        "core_goal": _trim_text(title.get("core_goal"), 160),
        "reference_examples": list(title.get("reference_examples") or [])[:_MAX_REFERENCE_EXAMPLES],
        "variable_schema": title.get("variable_schema") or [],
        "compatible_methods": title.get("compatible_methods") or [],
        "risk_rules": list(title.get("risk_rules") or [])[:3],
        "lexicon_codes": title.get("lexicon_codes") or [],
    }
    strategy["body_formula"] = {
        "code": body.get("code"),
        "name": body.get("name"),
        "structure_schema": body.get("structure_schema") or [],
        "reference_examples": list(body.get("reference_examples") or [])[:_MAX_REFERENCE_EXAMPLES],
        "required_variables": body.get("required_variables") or [],
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


def _slim_evidence_item(item: dict[str, Any], *, creation_mode: str) -> None:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    material_type = str(metadata.get("material_type") or "")
    if _is_forbidden_replacement_map(item):
        item["value"] = _compact_forbidden_replacement_value(item.get("value"))
        return
    if material_type == "viral_example":
        blueprint = metadata.get("reference_blueprint")
        if isinstance(blueprint, dict):
            metadata["reference_blueprint"] = {
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
            item["metadata"] = metadata
        if creation_mode == "original" or metadata.get("selected_reference") is not True:
            item["value"] = _trim_text(item.get("value"), 120)
            return
    if "value" in item:
        item["value"] = _trim_text(item.get("value"), _MAX_EVIDENCE_VALUE_CHARS)


def _build_evidence_cite_index(items: list) -> list[dict]:
    """引用索引只保留挂载所需元数据；正文事实看 evidence_bundle，避免 preview 双份。"""
    index: list[dict] = []
    for item in items:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        if item.get("verified_status") == "rejected":
            continue
        entry: dict[str, Any] = {
            "id": item["id"],
            "allowed_usage": list(item.get("allowed_usage") or []),
        }
        metadata = item.get("metadata")
        if isinstance(metadata, dict) and metadata.get("material_type"):
            entry["material_type"] = metadata.get("material_type")
        index.append(entry)
    return index


def project_generation_input(payload: dict) -> dict:
    # 调用方必须先完成 GenerateContentInputV1 校验（包括冻结策略 hash）。
    projected = deepcopy(payload)
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
        for field in ("source_hash", "source_version", "created_at", "citations"):
            item.pop(field, None)
        _slim_evidence_item(item, creation_mode=creation_mode)
    evidence_items = _dedupe_evidence_items(evidence_items)
    projected["evidence_bundle"]["items"] = evidence_items
    # 在证据瘦身与去重后建索引，避免与 bundle 重复塞满预览。
    projected["evidence_cite_index"] = _build_evidence_cite_index(evidence_items)
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
            for heavy in ("source_heading", "raw_text", "document_text"):
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
    return GenerateContentPromptV1.model_validate(projected).model_dump(mode="json")


def project_visual_plan_input(payload: dict) -> dict:
    """封面规划只看标题、正文、模板框和精简证据，不把生成节点的整包策略再喂一遍。"""
    projected = deepcopy(payload)
    strategy = projected.get("strategy_snapshot") or {}
    projected["strategy_snapshot"] = _slim_strategy_snapshot(strategy)
    evidence_items = projected.get("evidence_bundle", {}).get("items", [])
    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        for field in ("source_hash", "source_version", "created_at", "citations"):
            item.pop(field, None)
        _slim_evidence_item(item, creation_mode="original")
    if isinstance(projected.get("evidence_bundle"), dict):
        projected["evidence_bundle"]["items"] = _dedupe_evidence_items(evidence_items)
    draft = dict(projected.get("content_draft") or {})
    if "body" in draft:
        draft["body"] = _trim_text(draft.get("body"), 650)
    for heavy in ("lexicon_usage", "paragraph_evidence", "outline"):
        draft.pop(heavy, None)
    projected["content_draft"] = draft
    title = dict(projected.get("selected_title") or {})
    projected["selected_title"] = {
        key: title.get(key) for key in ("text", "evidence_ids") if key in title
    } or title
    channel = projected.get("channel_profile") or {}
    projected["channel_profile"] = {
        key: channel.get(key)
        for key in ("emoji_allowed", "title_constraints", "body_constraints")
        if key in channel
    }
    runtime = dict(projected.get("runtime_config_snapshot") or {})
    visual = dict(runtime.get("visual_material") or {})
    projected["runtime_config_snapshot"] = {
        "visual_material": {
            key: visual.get(key)
            for key in (
                "image_asset_id",
                "template_id",
                "hycanvas_fillable_fields",
                "required_template_field_repairs",
            )
            if key in visual
        }
    }
    media: list[dict[str, Any]] = []
    for item in projected.get("media_evidence_items") or []:
        if not isinstance(item, dict):
            continue
        media.append(
            {
                key: item.get(key)
                for key in ("id", "selected_for_cover", "object_uri", "allowed_usage")
                if key in item
            }
        )
    projected["media_evidence_items"] = media
    artifact = dict(projected.get("artifact_version") or {})
    if artifact.get("id"):
        projected["artifact_version"] = {"id": artifact.get("id")}
    return PlanVisualsPromptV1.model_validate(projected).model_dump(mode="json")
