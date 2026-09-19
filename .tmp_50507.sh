#!/bin/bash
set -uo pipefail
echo '==== latest failed tasks'
docker exec -i postgres psql -U postgres -d yuxi <<'SQL'
SELECT right(id,8), status,
       to_char((updated_at AT TIME ZONE 'UTC') AT TIME ZONE 'Asia/Shanghai','HH24:MI:SS') AS cst,
       LEFT(COALESCE(error_json::text,''),400)
FROM content_tasks
WHERE updated_at >= NOW() - INTERVAL '2 hours'
ORDER BY updated_at DESC LIMIT 8;
SQL

echo '==== generate_content node errors'
docker exec -i postgres psql -U postgres -d yuxi <<'SQL'
SELECT right(task_id::text,8), attempt, status,
       to_char((started_at AT TIME ZONE 'UTC') AT TIME ZONE 'Asia/Shanghai','HH24:MI:SS') AS cst,
       ROUND(EXTRACT(EPOCH FROM (finished_at-started_at))::numeric,1) AS wall,
       LEFT(COALESCE(error_message,''),250) AS err
FROM content_node_runs
WHERE node_id='generate_content'
  AND started_at >= NOW() - INTERVAL '2 hours'
ORDER BY started_at DESC LIMIT 12;
SQL

echo '==== worker around 50507 / InternalServer / generate_content'
docker logs worker-dev --since 90m 2>&1 \
  | grep -iE '50507|Unknown error|InternalServer|Error code: 500|generate_content|Content model call|已用完|title_formula' \
  | tail -60
