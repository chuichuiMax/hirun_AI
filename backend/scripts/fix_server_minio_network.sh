#!/bin/bash
set -euo pipefail
cd /opt/contentSwarm

echo "=== current minio ==="
docker inspect minio --format 'status={{.State.Status}} networks={{json .NetworkSettings.Networks}}' || true

ACCESS_KEY=$(grep -E '^MINIO_ACCESS_KEY=' .env 2>/dev/null | cut -d= -f2- || true)
SECRET_KEY=$(grep -E '^MINIO_SECRET_KEY=' .env 2>/dev/null | cut -d= -f2- || true)
ACCESS_KEY=${ACCESS_KEY:-minioadmin}
SECRET_KEY=${SECRET_KEY:-minioadmin}
IMAGE=$(docker inspect minio --format '{{.Config.Image}}' 2>/dev/null || echo 'minio/minio:RELEASE.2023-03-20T20-16-18Z')

echo "=== recreate minio on app-network only (no host :9000; portainer owns it) ==="
docker rm -f minio
docker run -d \
  --name minio \
  --restart unless-stopped \
  --network yuxi-know_app-network \
  --network-alias minio \
  -e MINIO_ACCESS_KEY="$ACCESS_KEY" \
  -e MINIO_SECRET_KEY="$SECRET_KEY" \
  -v /opt/contentSwarm/docker/volumes/milvus/minio:/minio_data \
  --health-cmd='curl -f http://localhost:9000/minio/health/live || exit 1' \
  --health-interval=30s \
  --health-timeout=20s \
  --health-retries=3 \
  "$IMAGE" \
  server /minio_data --address 0.0.0.0:9000 --console-address 0.0.0.0:9001

sleep 5
docker inspect minio --format 'status={{.State.Status}} networks={{json .NetworkSettings.Networks}} health={{if .State.Health}}{{.State.Health.Status}}{{end}}'
docker exec api-dev getent hosts minio
docker exec api-dev python /app/scripts/oss_minio_inventory.py
