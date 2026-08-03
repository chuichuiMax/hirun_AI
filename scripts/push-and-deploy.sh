#!/usr/bin/env bash
# 在本机执行：打包并上传到目标服务器，然后在远端运行 deploy-prod-server.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${DEPLOY_HOST:-root@47.110.157.215}"
DEPLOY_DIR="${DEPLOY_DIR:-/www/wwwroot/yuxi}"
WEB_HOST_PORT="${WEB_HOST_PORT:-8090}"
ARCHIVE="/tmp/yuxi-deploy.tar.gz"

cd "$ROOT"
tar czf "$ARCHIVE" \
  --exclude=node_modules \
  --exclude=.git \
  --exclude='docker/volumes' \
  --exclude='web/node_modules' \
  --exclude='docs/node_modules' \
  --exclude='.cursor' \
  .

echo ">>> 上传部署包到 ${HOST}:${DEPLOY_DIR} ..."
ssh "$HOST" "mkdir -p '$DEPLOY_DIR' /tmp"
scp "$ARCHIVE" "${HOST}:/tmp/yuxi-deploy.tar.gz"
scp "$ROOT/scripts/deploy-prod-server.sh" "${HOST}:/tmp/deploy-prod-server.sh"

if [[ -f "$ROOT/.env" ]]; then
  scp "$ROOT/.env" "${HOST}:/tmp/yuxi-local.env"
fi

echo ">>> 远端执行部署..."
ssh "$HOST" "chmod +x /tmp/deploy-prod-server.sh && DEPLOY_DIR='$DEPLOY_DIR' WEB_HOST_PORT='$WEB_HOST_PORT' bash /tmp/deploy-prod-server.sh /tmp/yuxi-deploy.tar.gz"
