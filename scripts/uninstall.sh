#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="chenbanxian-middleware"
WORKDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="$WORKDIR/.install-manifest"

DRY_RUN=true
PURGE=false
YES=false

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

Options:
  --yes          Execute uninstall (without this, default is dry-run)
  --purge        Also remove data/config artifacts (.env, logs, manifest)
  --dry-run      Print planned actions only (default)
  -h, --help     Show help

Examples:
  ./scripts/uninstall.sh --dry-run
  ./scripts/uninstall.sh --yes
  ./scripts/uninstall.sh --yes --purge
EOF
}

log() { echo "[uninstall] $*"; }

for arg in "$@"; do
  case "$arg" in
    --yes) YES=true; DRY_RUN=false ;;
    --purge) PURGE=true ;;
    --dry-run) DRY_RUN=true ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $arg"; usage; exit 1 ;;
  esac
done

run() {
  if $DRY_RUN; then
    echo "[dry-run] $*"
  else
    eval "$@"
  fi
}

service_exists=false
if command -v systemctl >/dev/null 2>&1; then
  if systemctl list-unit-files | grep -q "^${SERVICE_NAME}\.service"; then
    service_exists=true
  fi
fi

log "工作目录: $WORKDIR"
log "模式: $([ "$DRY_RUN" = true ] && echo dry-run || echo execute)"
log "清理级别: $([ "$PURGE" = true ] && echo purge || echo safe)
"

if $service_exists; then
  run "systemctl stop ${SERVICE_NAME} || true"
  run "systemctl disable ${SERVICE_NAME} || true"
  run "rm -f /etc/systemd/system/${SERVICE_NAME}.service"
  run "systemctl daemon-reload"
else
  log "systemd 服务未发现: ${SERVICE_NAME}.service"
fi

run "rm -rf '$WORKDIR/.venv'"

if [ -f "$MANIFEST" ]; then
  run "rm -f '$MANIFEST'"
fi

if $PURGE; then
  run "rm -f '$WORKDIR/.env'"
  run "rm -rf '$WORKDIR/.logs'"
fi

if $DRY_RUN; then
  log "Dry-run 完成。确认无误后执行: ./scripts/uninstall.sh --yes $([ "$PURGE" = true ] && echo --purge)"
else
  log "卸载完成。"
fi
