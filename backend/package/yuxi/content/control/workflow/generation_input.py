"""正文模型视图：审计快照保留在服务端，模型只读取本次创作所需内容。"""

from copy import deepcopy

from yuxi.content.model.contracts.content_nodes import GenerateContentPromptV1

_MAX_LEXICON_CHUNKS = 3
_MAX_LEXICON_CHUNK_CHARS = 400
_MAX_EVIDENCE_VALUE_CHARS = 320
_MAX_CITE_VALUE_CHARS = 80


def _trim_text(value: object, limit: int) -> object:
    if not isinstance(value, str) or len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def _is_forbidden_replacement_map(item: dict) -> bool:
    metadata = item.get("metadata")
    return isinstance(metadata, dict) and metadata.get("rule_kind") == "forbidden_replacement_map"


def _build_evidence_cite_index(items: list) -> list[dict]:
    index: list[dict] = []
    for item in items:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        if item.get("verified_status") == "rejected":
            continue
        index.append(
            {
                "id": item["id"],
                "allowed_usage": list(item.get("allowed_usage") or []),
                "source_id": item.get("source_id"),
                "source_type": item.get("source_type"),
                "material_type": (item.get("metadata") or {}).get("material_type")
                if isinstance(item.get("metadata"), dict)
                else None,
                "value_preview": _trim_text(item.get("value"), _MAX_CITE_VALUE_CHARS),
            }
        )
    return index


def project_generation_input(payload: dict) -> dict:
    # 调用方必须先完成 GenerateContentInputV1 校验（包括冻结策略 hash）。
    projected = deepcopy(payload)
    strategy = projected["strategy_snapshot"]
    strategy.pop("decision", None)
    strategy["source_snapshot_hash"] = strategy.pop("snapshot_hash")
    projected["runtime_config_snapshot"] = {
        "creation_mode": payload["runtime_config_snapshot"].get("creation_mode", "original"),
    }
    brief = projected["content_brief"]
    brief.pop("visual_material", None)
    for key in list(brief):
        if key.endswith("_version_id"):
            del brief[key]
    for section in ("business_variables", "form_values"):
        for key in list(brief.get(section) or {}):
            if key.endswith("_version_id") or key in {"attachments", "visual_material"}:
                del brief[section][key]
    evidence_items = projected["evidence_bundle"].get("items", [])
    projected["evidence_cite_index"] = _build_evidence_cite_index(evidence_items)
    for item in evidence_items:
        for field in ("source_hash", "source_version", "created_at"):
            item.pop(field, None)
        if "value" in item and not _is_forbidden_replacement_map(item):
            # 封禁词替换表必须完整到达生成端，截断会导致问题词漏替换。
            item["value"] = _trim_text(item["value"], _MAX_EVIDENCE_VALUE_CHARS)
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
    return GenerateContentPromptV1.model_validate(projected).model_dump(mode="json")
