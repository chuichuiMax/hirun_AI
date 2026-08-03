#!/usr/bin/env bash
# 在目标服务器上执行：安装 Docker、解压代码、配置 .env.prod、启动生产栈（web 监听 8090，由宝塔 Nginx 反代）
set -euo pipefail

DEPLOY_DIR="${DEPLOY_DIR:-/www/wwwroot/yuxi}"
WEB_HOST_PORT="${WEB_HOST_PORT:-8090}"
ARCHIVE="${1:-/tmp/yuxi-deploy.tar.gz}"

if [[ ! -f "$ARCHIVE" ]]; then
  echo "缺少部署包: $ARCHIVE"
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo ">>> 安装 Docker..."
  if command -v yum >/dev/null 2>&1; then
    yum install -y yum-utils
    yum-config-manager --add-repo https://mirrors.aliyun.com/docker-ce/linux/centos/docker-ce.repo || true
    yum install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
  elif command -v apt-get >/dev/null 2>&1; then
    apt-get update -y
    DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io docker-compose-v2 curl
  else
    curl -fsSL https://get.docker.com | sh
  fi
  systemctl enable docker
  systemctl start docker
  mkdir -p /etc/docker
  if [[ ! -f /etc/docker/daemon.json ]]; then
    cat > /etc/docker/daemon.json <<'EOF'
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://mirror.ccs.tencentyun.com",
    "https://hub-mirror.c.163.com"
  ]
}
EOF
    systemctl restart docker
  fi
fi

echo ">>> Docker: $(docker --version)"
echo ">>> Compose: $(docker compose version)"

mkdir -p "$DEPLOY_DIR"
tar xzf "$ARCHIVE" -C "$DEPLOY_DIR"

cd "$DEPLOY_DIR"

if [[ -f /tmp/yuxi-local.env ]]; then
  touch .env.prod
  for key in SILICONFLOW_API_KEY DEEPSEEK_API_KEY TAVILY_API_KEY JWT_SECRET_KEY YUXI_INSTANCE_ID; do
    val="$(grep -E "^${key}=" /tmp/yuxi-local.env 2>/dev/null | head -1 | cut -d= -f2- || true)"
    if [[ -n "$val" ]]; then
      if grep -q "^${key}=" .env.prod; then
        sed -i "s|^${key}=.*|${key}=${val}|" .env.prod
      else
        echo "${key}=${val}" >> .env.prod
      fi
    fi
  done
fi

if [[ ! -f .env.prod ]]; then
  cp .env.template .env.prod
fi

set_env() {
  local key="$1"
  local value="$2"
  if grep -q "^${key}=" .env.prod; then
    sed -i "s|^${key}=.*|${key}=${value}|" .env.prod
  else
    echo "${key}=${value}" >> .env.prod
  fi
}

set_env YUXI_ENV production
set_env YUXI_INSTANCE_ID "instance-boyun-prod"
set_env VITE_BASE_PATH "/boyun/"

if ! grep -q '^JWT_SECRET_KEY=.\+' .env.prod; then
  set_env JWT_SECRET_KEY "$(openssl rand -hex 32)"
fi

# web 改到 8090，避免与宝塔 Nginx / OpenSwarm 抢 80
sed -i "s/\"80:80\"/\"${WEB_HOST_PORT}:80\"/" docker-compose.prod.yml

echo ">>> 构建并启动服务（首次较慢，请耐心等待）..."
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build

echo ">>> 预拉沙盒镜像..."
docker pull enterprise-public-cn-beijing.cr.volces.com/vefaas-public/all-in-one-sandbox:latest || true

echo ">>> 等待 API 健康..."
for i in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:${WEB_HOST_PORT}/api/system/health" >/dev/null; then
    echo ">>> 部署成功: http://127.0.0.1:${WEB_HOST_PORT}/api/system/health"
    curl -s "http://127.0.0.1:${WEB_HOST_PORT}/api/system/health"
    echo

    if [[ -f "$DEPLOY_DIR/scripts/nginx/yuxi-boyun.conf" ]]; then
      echo ">>> 更新宝塔 Nginx 反代配置..."
      mkdir -p /www/server/panel/vhost/nginx/extension/47.110.157.215
      cp "$DEPLOY_DIR/scripts/nginx/yuxi-boyun.conf" \
        /www/server/panel/vhost/nginx/extension/47.110.157.215/yuxi-boyun.conf
      nginx -t && nginx -s reload || systemctl reload nginx || true
    fi

    echo "请在宝塔为站点配置反向代理 -> http://127.0.0.1:${WEB_HOST_PORT}"
    docker compose --env-file .env.prod -f docker-compose.prod.yml ps
    exit 0
  fi
  sleep 10
done

echo ">>> 健康检查超时，最近容器状态："
docker compose --env-file .env.prod -f docker-compose.prod.yml ps
docker logs api-prod --tail 80 || true
exit 1
