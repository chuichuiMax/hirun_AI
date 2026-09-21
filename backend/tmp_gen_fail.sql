SELECT version, evidence_ids
FROM content_evidence_bundle_versions
WHERE task_id = 'ct_b2ef2d4f486b4a7f95c9d129091cd07b'
ORDER BY version;

SELECT item->>'id' AS id,
       item->'metadata'->>'material_type' AS material_type,
       item->'metadata'->>'selected_reference' AS selected_reference
FROM content_tasks t
CROSS JOIN LATERAL json_array_elements(t.evidence_json::json->'items') item
WHERE t.id = 'ct_b2ef2d4f486b4a7f95c9d129091cd07b'
  AND (
    item->'metadata'->>'material_type' = 'viral_example'
    OR item->>'id' LIKE 'vav_%'
  );

SELECT id, task_id
FROM content_evidence_items
WHERE id LIKE 'vav_%'
LIMIT 10;
