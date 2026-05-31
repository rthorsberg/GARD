#!/usr/bin/env bash
# Seed the Docker stack with the F6 Cisco ISR1121 MVP vertical-slice fixture.
#
# Usage:
#   ./deploy/scripts/seed-isr1121.sh
#   GARD_API_HOST_PORT=9090 ./deploy/scripts/seed-isr1121.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

COMPOSE_FILE="${GARD_COMPOSE_FILE:-$REPO_ROOT/deploy/docker-compose.yml}"
API_PORT="${GARD_API_HOST_PORT:-8080}"
SUBJECT="${GARD_SEED_SUBJECT:-ops@example.com}"
TTL="${GARD_SEED_TTL:-7200}"
CSV_PATH="$SCRIPT_DIR/fixtures/isr1121-devices.csv"
API_BASE="http://127.0.0.1:${API_PORT}"

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
red()  { printf '\033[31m%s\033[0m\n' "$*" >&2; }
dim()  { printf '\033[2m%s\033[0m\n' "$*"; }

require() {
  command -v "$1" >/dev/null 2>&1 || { red "missing required command: $1"; exit 127; }
}

require docker
require curl
require python3

bold "==> Waiting for API at $API_BASE/healthz"
for i in $(seq 1 30); do
  if curl -sS -o /dev/null -w '%{http_code}' "$API_BASE/healthz" 2>/dev/null | grep -q '^200$'; then
    dim "    healthy after ${i}s"
    break
  fi
  [[ $i -eq 30 ]] && { red "API never became healthy"; exit 1; }
  sleep 1
done

bold "==> Minting lifecycle_manager token (subject=$SUBJECT)"
TOKEN=$(docker compose -f "$COMPOSE_FILE" exec -T api \
  python -m gard issue-token \
    --subject "$SUBJECT" \
    --role lifecycle_manager \
    --ttl-seconds "$TTL" \
  2>/dev/null | tr -d '\r\n')
[[ "$TOKEN" =~ ^eyJ ]] || { red "token mint failed"; exit 1; }
printf '%s' "$TOKEN" > "$REPO_ROOT/.gard/token.jwt"
chmod 600 "$REPO_ROOT/.gard/token.jwt" 2>/dev/null || true

bold "==> Reloading firmware catalog (includes ISR1121 target)"
docker compose -f "$COMPOSE_FILE" exec -T api \
  python -m gard catalog reload --only firmware >/dev/null

bold "==> Importing ISR1121 fixture: $CSV_PATH"
IMPORT_RES=$(curl -sS -X POST -H "Authorization: Bearer $TOKEN" \
  -F "file=@$CSV_PATH" \
  "$API_BASE/api/v1/imports/devices/csv")
echo "$IMPORT_RES" | python3 -c "
import json, sys
r = json.loads(sys.stdin.read())
t = r['totals']
print(f'    rows_total={t[\"rows_total\"]} accepted={t[\"rows_accepted\"]} rejected={t[\"rows_rejected\"]} duplicate={t[\"rows_duplicate\"]} manual_review={t[\"rows_manual_review\"]}')
"

bold "==> F3/F4: compliance + readiness evaluate (scope=all)"
curl -sS -X POST -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
  -d '{"scope_selector":{}}' "$API_BASE/api/v1/compliance/evaluate" >/dev/null
curl -sS -X POST -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
  -d '{"scope_selector":{}}' "$API_BASE/api/v1/readiness/evaluate" >/dev/null

bold "==> F4: readiness summary (expect ready_for_uplift >= 1)"
curl -sS -H "Authorization: Bearer $TOKEN" "$API_BASE/api/v1/readiness/summary" \
  | python3 -c "
import json, sys
r = json.loads(sys.stdin.read())
print(f'    ready_for_uplift={r[\"ready_for_uplift_count\"]} blocked={r[\"blocked_count\"]} outside_target={r[\"total_outside_target\"]}')
"

bold "==> F5: plan + wave + approval (SoD)"
APPROVER_TOKEN=$(docker compose -f "$COMPOSE_FILE" exec -T api \
  python -m gard issue-token \
    --subject "approver@example.com" \
    --role change_approver \
    --ttl-seconds "$TTL" \
  2>/dev/null | tr -d '\r\n')

PLAN_ID=$(curl -sS -X POST -H "Authorization: Bearer $TOKEN" \
  -H "content-type: application/json" \
  -d '{"name":"seed-isr1121-plan","description":"F6 MVP vertical slice"}' \
  "$API_BASE/api/v1/uplift/plans" | python3 -c "import json,sys; print(json.load(sys.stdin).get('id',''))")

START=$(python3 -c "import datetime as dt; s=dt.datetime.now(dt.UTC)+dt.timedelta(hours=24); e=s+dt.timedelta(hours=2); print(s.isoformat()); print(e.isoformat())")
CW_START=$(echo "$START" | sed -n '1p')
CW_END=$(echo "$START" | sed -n '2p')

WAVE=$(curl -sS -X POST -H "Authorization: Bearer $TOKEN" \
  -H "content-type: application/json" \
  -H "Idempotency-Key: seed-isr1121-wave" \
  -d "{\"name\":\"seed-isr1121-wave\",\"target_version\":\"17.12.4\",\"target_platform_family\":\"ios\",\"scope_selector\":{\"site_in\":[\"Oslo\"],\"platform_family\":\"ios\"},\"mode\":\"skip_ineligible\",\"change_window_start\":\"$CW_START\",\"change_window_end\":\"$CW_END\"}" \
  "$API_BASE/api/v1/uplift/plans/$PLAN_ID/waves")
WAVE_ID=$(echo "$WAVE" | python3 -c "import json,sys; print(json.load(sys.stdin).get('id',''))")
echo "$WAVE" | python3 -c "
import json, sys
w = json.loads(sys.stdin.read())
print(f'    wave_id={w.get(\"id\",\"?\")} state={w.get(\"state\",\"?\")} devices={w.get(\"device_count\",0)}')
"

if [[ -n "$WAVE_ID" && -n "$APPROVER_TOKEN" && "$APPROVER_TOKEN" =~ ^eyJ ]]; then
  curl -sS -X POST -H "Authorization: Bearer $TOKEN" \
    "$API_BASE/api/v1/uplift/waves/$WAVE_ID/submit" >/dev/null
  curl -sS -X POST -H "Authorization: Bearer $APPROVER_TOKEN" \
    -H "content-type: application/json" \
    -d '{"citation":"Seed ISR1121 demo — CAB ticket CHG-ISR1121-001."}' \
    "$API_BASE/api/v1/uplift/waves/$WAVE_ID/approve" >/dev/null
  dim "    submitted + approved with separate approver principal"
fi

bold "==> Done. Token at .gard/token.jwt"
echo "  pytest: uv run pytest tests/integration/test_mvp_vertical_slice_isr1121.py -q"
