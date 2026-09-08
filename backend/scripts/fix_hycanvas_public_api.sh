#!/bin/bash
set -euo pipefail
cd /opt/contentSwarm

# Ensure browser API is same-origin behind nginx
if grep -q '^NEXT_PUBLIC_BACKEND_URL=' .env; then
  sed -i 's|^NEXT_PUBLIC_BACKEND_URL=.*|NEXT_PUBLIC_BACKEND_URL=/api|' .env
else
  printf '\nNEXT_PUBLIC_BACKEND_URL=/api\n' >> .env
fi

grep -E '^(NEXT_PUBLIC_BACKEND_URL|HYCANVAS_PUBLIC_URL|HYCANVAS_DEV_PUBLIC_URL|CONTENTSWARM_PUBLIC_URL|HYCANVAS_COOKIE_SECURE)=' .env

# Sync compose override support if present on host (best-effort)
docker compose up -d --force-recreate --no-deps hycanvas-app

echo "waiting for hycanvas..."
for i in $(seq 1 30); do
  if curl -fsS --max-time 3 http://127.0.0.1:8005/healthz >/dev/null \
     && curl -fsS --max-time 3 -o /dev/null http://127.0.0.1:3000/; then
    echo "hycanvas up"
    break
  fi
  sleep 5
done

docker exec contentswarm-hycanvas-app-1 printenv NEXT_PUBLIC_BACKEND_URL
curl -sk --max-time 8 -o /dev/null -w "dashboard:%{http_code}\n" https://127.0.0.1/dashboard/ -H 'Host: ai.hi-run.net'
curl -sk --max-time 8 -o /dev/null -w "api_v1_workspaces:%{http_code}\n" https://127.0.0.1/api/v1/workspaces -H 'Host: ai.hi-run.net'
