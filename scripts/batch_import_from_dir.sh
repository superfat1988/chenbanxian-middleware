#!/usr/bin/env bash
set -euo pipefail

API="http://127.0.0.1:5055/api"
DIR=""
NOTEBOOK_ID=""

usage() {
  cat <<EOF
Usage: $(basename "$0") --dir <local-dir> [--api <api-base>] [--notebook-id <id>]

Examples:
  $(basename "$0") --dir "/vol3/1000/KaitOP/修养/斗数学习"
  $(basename "$0") --api http://127.0.0.1:5055/api --dir /data/books --notebook-id notebook:abc
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --api) API="$2"; shift 2 ;;
    --dir) DIR="$2"; shift 2 ;;
    --notebook-id) NOTEBOOK_ID="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1"; usage; exit 1 ;;
  esac
done

[ -n "$DIR" ] || { echo "--dir is required"; exit 1; }
[ -d "$DIR" ] || { echo "dir not found: $DIR"; exit 1; }

if [ -z "$NOTEBOOK_ID" ]; then
  NOTEBOOK_ID=$(curl -sS "$API/notebooks" | grep -o 'notebook:[^"]*' | head -n1 || true)
fi

[ -n "$NOTEBOOK_ID" ] || { echo "cannot resolve notebook id"; exit 1; }

echo "[batch-import] api=$API"
echo "[batch-import] dir=$DIR"
echo "[batch-import] notebook_id=$NOTEBOOK_ID"

created=0
failed=0
total=0

while IFS= read -r -d '' f; do
  total=$((total+1))
  code=$(curl -sS -o /tmp/on_import_resp.json -w "%{http_code}" -X POST "$API/sources" \
    -F "type=upload" \
    -F "title=$(basename "$f")" \
    -F "notebooks=[\"$NOTEBOOK_ID\"]" \
    -F "async_processing=true" \
    -F "delete_source=true" \
    -F "file=@$f") || code=000

  if [ "$code" = "200" ]; then
    created=$((created+1))
  else
    failed=$((failed+1))
    echo "[fail] code=$code file=$f"
    sed -n '1,2p' /tmp/on_import_resp.json || true
  fi

  if [ $((total%20)) -eq 0 ]; then
    echo "[progress] total=$total created=$created failed=$failed"
  fi
done < <(find "$DIR" -type f \( -iname "*.pdf" -o -iname "*.epub" -o -iname "*.txt" -o -iname "*.md" -o -iname "*.doc" -o -iname "*.docx" -o -iname "*.pptx" -o -iname "*.xlsx" \) -print0)

echo "[summary] total=$total created=$created failed=$failed"
