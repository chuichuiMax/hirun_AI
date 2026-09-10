-- Raise narrative cover-copy maxChars floors for existing HyCanvas templates.
-- title>=12, subtitle>=16, body_excerpt>=24
UPDATE templates t
SET file = jsonb_set(
  t.file,
  '{meta,brandEditableFields}',
  (
    SELECT COALESCE(jsonb_agg(
      CASE
        WHEN f->>'kind' = 'text' AND f->>'semanticRole' = 'title'
          AND COALESCE((f->'constraints'->>'maxChars')::int, 0) > 0
          AND COALESCE((f->'constraints'->>'maxChars')::int, 0) < 12
          THEN jsonb_set(f, '{constraints,maxChars}', '12'::jsonb, true)
        WHEN f->>'kind' = 'text' AND f->>'semanticRole' = 'subtitle'
          AND COALESCE((f->'constraints'->>'maxChars')::int, 0) > 0
          AND COALESCE((f->'constraints'->>'maxChars')::int, 0) < 16
          THEN jsonb_set(f, '{constraints,maxChars}', '16'::jsonb, true)
        WHEN f->>'kind' = 'text' AND f->>'semanticRole' = 'body_excerpt'
          AND COALESCE((f->'constraints'->>'maxChars')::int, 0) > 0
          AND COALESCE((f->'constraints'->>'maxChars')::int, 0) < 24
          THEN jsonb_set(f, '{constraints,maxChars}', '24'::jsonb, true)
        ELSE f
      END
    ), '[]'::jsonb)
    FROM jsonb_array_elements(COALESCE(t.file->'meta'->'brandEditableFields', '[]'::jsonb)) AS f
  ),
  true
),
updated_at = NOW()
WHERE t.file->'meta'->'brandEditableFields' IS NOT NULL
  AND EXISTS (
    SELECT 1
    FROM jsonb_array_elements(COALESCE(t.file->'meta'->'brandEditableFields', '[]'::jsonb)) AS f
    WHERE f->>'kind' = 'text'
      AND f->>'semanticRole' IN ('title', 'subtitle', 'body_excerpt')
      AND COALESCE((f->'constraints'->>'maxChars')::int, 0) > 0
      AND (
        (f->>'semanticRole' = 'title' AND (f->'constraints'->>'maxChars')::int < 12)
        OR (f->>'semanticRole' = 'subtitle' AND (f->'constraints'->>'maxChars')::int < 16)
        OR (f->>'semanticRole' = 'body_excerpt' AND (f->'constraints'->>'maxChars')::int < 24)
      )
  );

-- Verify remaining tight narrative fields (should be empty for title/subtitle/body_excerpt < floors)
SELECT t.id, t.title, f->>'semanticRole' AS role, f->>'label' AS label,
       (f->'constraints'->>'maxChars')::int AS max_chars
FROM templates t
CROSS JOIN LATERAL jsonb_array_elements(COALESCE(t.file->'meta'->'brandEditableFields', '[]'::jsonb)) AS f
WHERE f->>'kind' = 'text'
  AND f->>'semanticRole' IN ('title', 'subtitle', 'body_excerpt')
  AND COALESCE((f->'constraints'->>'maxChars')::int, 0) > 0
  AND (
    (f->>'semanticRole' = 'title' AND (f->'constraints'->>'maxChars')::int < 12)
    OR (f->>'semanticRole' = 'subtitle' AND (f->'constraints'->>'maxChars')::int < 16)
    OR (f->>'semanticRole' = 'body_excerpt' AND (f->'constraints'->>'maxChars')::int < 24)
  );
