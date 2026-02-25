#!/usr/bin/env bash
set -euo pipefail

BASE="${1:-http://127.0.0.1:8787}"

echo "[smoke] base=$BASE"

echo "[1/4] health"
curl -fsS "$BASE/health" | tee /tmp/cbx_health.json >/dev/null

echo "[2/4] preflight"
curl -fsS "$BASE/preflight" | tee /tmp/cbx_preflight.json >/dev/null

echo "[3/4] group gate (should reject when not addressed)"
RESP_GROUP=$(curl -sS -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -d '{"question":"紫微斗数怎么看","chat_type":"group","addressed":false}')
echo "$RESP_GROUP" | tee /tmp/cbx_group_gate.json >/dev/null
python3 - <<'PY'
import json
obj=json.load(open('/tmp/cbx_group_gate.json'))
assert obj.get('mode')=='reject', obj
assert obj.get('reason')=='group_not_addressed', obj
print('[ok] group gate')
PY

echo "[4/4] non-template + route checks"
RESP_NON=$(curl -sS -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -d '{"question":"帮我写一个站会纪要提纲","chat_type":"private","addressed":true}')
echo "$RESP_NON" | tee /tmp/cbx_non_route.json >/dev/null

RESP_ZW=$(curl -sS -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -d '{"question":"紫微斗数里化禄和化忌怎么理解","chat_type":"private","addressed":true}')
echo "$RESP_ZW" | tee /tmp/cbx_ziwei_route.json >/dev/null

python3 - <<'PY'
import json
non=json.load(open('/tmp/cbx_non_route.json'))
zw=json.load(open('/tmp/cbx_ziwei_route.json'))
assert non.get('mode')=='direct-llm', non
assert zw.get('mode')=='ziweidoushu-kb', zw
# template腔粗检（若命中这些固定标签则判失败）
ans=(non.get('answer') or '') + '\n' + (zw.get('answer') or '')
for bad in ['结论：','依据：','建议：']:
    assert bad not in ans, f'template detected: {bad}'
print('[ok] route + anti-template')
PY

echo "[smoke] all checks passed"
