#!/usr/bin/env bash
# Seed the local Docker stack with a dev token + sample devices.
#
# Idempotent: re-runs against an already-populated DB return rows as
# `rows_duplicate` and exit 0. Safe to call after `docker compose down -v`
# once the stack is healthy again.
#
# Usage:
#   ./deploy/scripts/seed.sh                       # default fixture, 5 devices
#   ./deploy/scripts/seed.sh path/to/other.csv     # custom fixture
#   GARD_API_HOST_PORT=9090 ./deploy/scripts/seed.sh
#
# Environment:
#   GARD_API_HOST_PORT   Host port the API is published on (default 8080).
#   GARD_SEED_SUBJECT    Subject email written into the token + audit (default ops@example.com).
#   GARD_SEED_TTL        Token TTL in seconds (default 7200 = 2h).
#   GARD_COMPOSE_FILE    Override compose file path (default deploy/docker-compose.yml).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

COMPOSE_FILE="${GARD_COMPOSE_FILE:-$REPO_ROOT/deploy/docker-compose.yml}"
API_PORT="${GARD_API_HOST_PORT:-8080}"
SUBJECT="${GARD_SEED_SUBJECT:-ops@example.com}"
TTL="${GARD_SEED_TTL:-7200}"
CSV_PATH="${1:-$SCRIPT_DIR/fixtures/devices.csv}"
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

if [[ ! -f "$CSV_PATH" ]]; then
  red "fixture CSV not found: $CSV_PATH"
  exit 2
fi

bold "==> Waiting for API at $API_BASE/healthz"
for i in $(seq 1 30); do
  if curl -sS -o /dev/null -w '%{http_code}' "$API_BASE/healthz" 2>/dev/null | grep -q '^200$'; then
    dim "    healthy after ${i}s"
    break
  fi
  if [[ $i -eq 30 ]]; then
    red "API never became healthy. Is the stack up?"
    red "  docker compose -f $COMPOSE_FILE up -d --build"
    exit 1
  fi
  sleep 1
done

bold "==> Minting dev token (subject=$SUBJECT, ttl=${TTL}s, role=lifecycle_manager)"
TOKEN_META=$(mktemp -t gard-seed-meta.XXXXXX)
trap 'rm -f "$TOKEN_META"' EXIT

TOKEN=$(docker compose -f "$COMPOSE_FILE" exec -T api \
  python -m gard issue-token \
    --subject "$SUBJECT" \
    --role    lifecycle_manager \
    --ttl-seconds "$TTL" \
  2>"$TOKEN_META")

TOKEN="${TOKEN//$'\r'/}"
TOKEN="${TOKEN//$'\n'/}"

if [[ -z "$TOKEN" || ! "$TOKEN" =~ ^eyJ[A-Za-z0-9._-]+$ ]]; then
  red "mint failed; stderr from CLI:"
  cat "$TOKEN_META" >&2
  exit 1
fi
dim "    $(cat "$TOKEN_META")"

mkdir -p "$REPO_ROOT/.gard"
printf '%s' "$TOKEN" > "$REPO_ROOT/.gard/token.jwt"
chmod 600 "$REPO_ROOT/.gard/token.jwt"
dim "    saved to .gard/token.jwt (mode 600)"

bold "==> Importing fixture: $CSV_PATH"
# First attempt: no override. If the API replies HTTP 409 with the
# duplicate-file marker (per ADR-0009 chain-of-custody), retry with
# override=true so the seed is idempotent across re-runs against a
# populated DB. Device-level idempotency (serial number is the natural
# key) then shows up as `rows_duplicate` in the totals.
RESPONSE_FILE=$(mktemp -t gard-seed-resp.XXXXXX)
trap 'rm -f "$TOKEN_META" "$RESPONSE_FILE"' EXIT

HTTP_CODE=$(curl -sS -o "$RESPONSE_FILE" -w '%{http_code}' \
  -X POST -H "Authorization: Bearer $TOKEN" \
  -F "file=@$CSV_PATH;type=text/csv" \
  -F "actor_email=$SUBJECT" \
  "$API_BASE/api/v1/imports/devices/csv")

if [[ "$HTTP_CODE" == "409" ]] && grep -q 'duplicate file' "$RESPONSE_FILE"; then
  dim "    file already imported; retrying with override=true"
  HTTP_CODE=$(curl -sS -o "$RESPONSE_FILE" -w '%{http_code}' \
    -X POST -H "Authorization: Bearer $TOKEN" \
    -F "file=@$CSV_PATH;type=text/csv" \
    -F "actor_email=$SUBJECT" \
    "$API_BASE/api/v1/imports/devices/csv?override=true")
fi

if [[ "$HTTP_CODE" != "200" ]]; then
  red "import failed: HTTP $HTTP_CODE"
  cat "$RESPONSE_FILE" >&2
  exit 1
fi

python3 -c '
import json, sys
r = json.load(sys.stdin)
t = r.get("totals") or {}
top = (("job_id", r.get("job_id")),
       ("status", r.get("status")),
       ("correlation_id", r.get("correlation_id")))
totals = (("rows_total","rows_accepted","rows_duplicate","rows_rejected",
           "devices_created","devices_updated"))
for k, v in top:
    print(f"    {k:<17}{v}")
for k in totals:
    print(f"    {k:<17}{t.get(k)}")
sys.exit(0 if r.get("status") in ("completed","partial") else 1)
' < "$RESPONSE_FILE"

bold "==> Verifying via GET /api/v1/devices"
COUNT=$(curl -sS -H "Authorization: Bearer $TOKEN" "$API_BASE/api/v1/devices?limit=200" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['total_returned'])")
dim "    $COUNT device(s) currently in the catalog"

# F2 (002): trigger an explicit firmware-catalog reload inside the API
# container so the bundled `gard-catalog/firmware/` fixtures land in the
# DB. The API also reloads on lifespan startup, but re-running here makes
# the seed deterministic regardless of when the catalog YAML last changed.
bold "==> Reloading firmware catalog (F2)"
docker compose -f "$COMPOSE_FILE" exec -T api \
  python -m gard catalog reload --only firmware 2>&1 \
  | tail -2 | sed 's/^/    /'

bold "==> Firmware compliance snapshot (F2)"
curl -sS -H "Authorization: Bearer $TOKEN" \
  "$API_BASE/api/v1/firmware/targets" 2>/dev/null \
  | python3 -c "
import json, sys
r = json.load(sys.stdin)
print(f'    {r[\"total_returned\"]} firmware target(s) loaded:')
for t in r['items']:
    print(f'      - {t[\"name\"]:<26} platform={t[\"platform_family\"]:<8} target_version={t[\"target_version\"]}')
" 2>/dev/null || dim "    (skipped: firmware targets endpoint not reachable)"

bold "==> Per-device firmware compliance"
# Walk every device and hit the F2 compliance endpoint. Each call also
# transitions the persisted lifecycle_state and emits one audit row.
DEVICE_IDS=$(curl -sS -H "Authorization: Bearer $TOKEN" "$API_BASE/api/v1/devices?limit=200" \
  | python3 -c "import json,sys; [print(d['facts']['id'], d['facts']['hostname']) for d in json.load(sys.stdin)['items']]")
while IFS= read -r line; do
  [[ -z "$line" ]] && continue
  DEV_ID="${line%% *}"
  HOST="${line#* }"
  STATE=$(curl -sS -H "Authorization: Bearer $TOKEN" \
    "$API_BASE/api/v1/devices/$DEV_ID/firmware-compliance" \
    | python3 -c "
import json, sys
r = json.load(sys.stdin)
state = r.get('state') or '?'
tv = r.get('target_version') or '-'
ov = r.get('observed_version') or '-'
print(f'{state:<14} target_ver={tv:<12} observed={ov}')")
  printf '    %-14s %s\n' "$HOST" "$STATE"
done <<< "$DEVICE_IDS"

bold "==> F3: triggering bounded compliance re-eval (scope=all)"
EVAL_RES=$(curl -sS -X POST -H "Authorization: Bearer $TOKEN" \
  -H "content-type: application/json" \
  -d '{"scope_selector":{}}' \
  "$API_BASE/api/v1/compliance/evaluate")
echo "$EVAL_RES" | python3 -c "
import json, sys
r = json.loads(sys.stdin.read())
print(f'    requested={r[\"requested_count\"]} evaluated={r[\"evaluated_count\"]} unchanged={r[\"unchanged_count\"]}')
print(f'    correlation_id={r[\"correlation_id\"]}')
" 2>/dev/null || dim "    (skipped: evaluate endpoint not reachable)"

bold "==> F3: estate-wide drift summary"
curl -sS -H "Authorization: Bearer $TOKEN" "$API_BASE/api/v1/compliance/summary" \
  | python3 -c "
import json, sys
r = json.loads(sys.stdin.read())
print(f'    total_evaluated={r[\"total_evaluated\"]} compliant={r[\"compliant_count\"]} unknown={r[\"unknown_count\"]}')
counts = r['counts_by_drift_type']
ordered = ['catalog_drift', 'rule_drift', 'package_drift', 'target_drift', 'discovery_drift', 'evidence_drift', 'exception_drift']
for k in ordered:
    v = counts.get(k, 0)
    if v:
        print(f'      - {k:<18} {v}')
" 2>/dev/null || dim "    (skipped: summary endpoint not reachable)"

bold "==> F3: per-device drift classification"
curl -sS -H "Authorization: Bearer $TOKEN" "$API_BASE/api/v1/compliance/devices?limit=200" \
  | python3 -c "
import json, sys
r = json.loads(sys.stdin.read())
for it in r['items']:
    env = it['envelope']
    drift = env['drift_type'] or '-'
    secondary = ','.join(env['secondary_drift_types']) or '-'
    actions = ','.join(a['kind'] for a in env['recommended_actions']) or '-'
    print(f'    {it[\"hostname\"]:<14} state={env[\"state\"]:<14} drift={drift:<16} secondary={secondary:<14} actions={actions}')
" 2>/dev/null || dim "    (skipped: devices listing endpoint not reachable)"

bold "==> F4: triggering bounded readiness re-eval (scope=all)"
EVAL_RES=$(curl -sS -X POST -H "Authorization: Bearer $TOKEN" \
  -H "content-type: application/json" \
  -d '{"scope_selector":{}}' \
  "$API_BASE/api/v1/readiness/evaluate")
echo "$EVAL_RES" | python3 -c "
import json, sys
r = json.loads(sys.stdin.read())
print(f'    requested={r[\"requested_count\"]} evaluated={r[\"evaluated_count\"]} unchanged={r[\"unchanged_count\"]} not_applicable={r[\"not_applicable_count\"]}')
print(f'    correlation_id={r[\"correlation_id\"]}')
" 2>/dev/null || dim "    (skipped: readiness/evaluate endpoint not reachable)"

bold "==> F4: estate-wide readiness summary"
curl -sS -H "Authorization: Bearer $TOKEN" "$API_BASE/api/v1/readiness/summary" \
  | python3 -c "
import json, sys
r = json.loads(sys.stdin.read())
print(f'    total_outside_target={r[\"total_outside_target\"]} ready_for_uplift={r[\"ready_for_uplift_count\"]} blocked={r[\"blocked_count\"]} not_applicable={r[\"not_applicable_count\"]}')
if r['top_blocker_categories']:
    print('    top_blocker_categories:')
    for c in r['top_blocker_categories']:
        print(f'      - {c[\"predicate_kind\"]:<28} {c[\"count\"]}')
" 2>/dev/null || dim "    (skipped: readiness/summary endpoint not reachable)"

bold "==> F4: per-device readiness verdict"
curl -sS -H "Authorization: Bearer $TOKEN" "$API_BASE/api/v1/readiness/devices?limit=200" \
  | python3 -c "
import json, sys
r = json.loads(sys.stdin.read())
for it in r['items']:
    env = it['envelope']
    blockers = env.get('blockers') or []
    primary_kind = blockers[0]['predicate_kind'] if blockers else '-'
    primary_rule = blockers[0].get('rule_name') or '-' if blockers else '-'
    print(f'    {it[\"hostname\"]:<14} state={env[\"state\"]:<18} primary={primary_kind:<28} rule={primary_rule}')
" 2>/dev/null || dim "    (skipped: readiness/devices listing endpoint not reachable)"

bold "==> Done."
echo
echo "Token (also at .gard/token.jwt):"
echo "  $TOKEN"
echo
echo "Try:"
echo "  curl -H 'Authorization: Bearer \$(cat .gard/token.jwt)' $API_BASE/api/v1/devices | jq"
echo "  open $API_BASE/docs"
