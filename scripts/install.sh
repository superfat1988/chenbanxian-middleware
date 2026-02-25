#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="chenbanxian-middleware"
PORT="${PORT:-8787}"
HOST="${HOST:-0.0.0.0}"
WORKDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

log() { echo "[install] $*"; }
err() { echo "[install][error] $*" >&2; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { err "缺少命令: $1"; exit 1; }
}

log "工作目录: $WORKDIR"
require_cmd python3

cd "$WORKDIR"

if [ ! -d .venv ]; then
  log "创建虚拟环境 .venv"
  python3 -m venv .venv
fi

log "安装依赖"
.venv/bin/pip install --upgrade pip >/dev/null
.venv/bin/pip install -r requirements.txt

CREATED_ENV=false
if [ ! -f .env ]; then
  log "未发现 .env，自动从 .env.example 生成"
  cp .env.example .env
  CREATED_ENV=true
  log "请编辑 .env 后再生产使用"
fi

SERVICE_FILE=""
if command -v systemctl >/dev/null 2>&1 && [ "$(id -u)" -eq 0 ]; then
  SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
  log "写入 systemd 服务: $SERVICE_FILE"
  cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Chenbanxian RAG Middleware
After=network.target

[Service]
Type=simple
WorkingDirectory=$WORKDIR
EnvironmentFile=$WORKDIR/.env
ExecStart=$WORKDIR/.venv/bin/uvicorn app:app --host $HOST --port $PORT
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

  log "重载并启动服务"
  systemctl daemon-reload
  systemctl enable --now "$SERVICE_NAME"
  systemctl --no-pager --full status "$SERVICE_NAME" || true
else
  log "未检测到 root/systemd，改为前台运行方式："
  echo "cd $WORKDIR && .venv/bin/uvicorn app:app --host $HOST --port $PORT"
fi

cat > "$WORKDIR/.install-manifest" <<EOF
WORKDIR=$WORKDIR
SERVICE_NAME=$SERVICE_NAME
SERVICE_FILE=$SERVICE_FILE
PORT=$PORT
HOST=$HOST
CREATED_ENV=$CREATED_ENV
CREATED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF

log "安装完成。健康检查：curl http://127.0.0.1:${PORT}/health"
