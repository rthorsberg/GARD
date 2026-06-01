#!/usr/bin/env bash
# End-to-end: configure GARD API for NetBox and run F7 sync against dev stacks.
#
# Prerequisites:
#   - gard-f7-netbox stack up with seeded devices (./deploy/scripts/seed-netbox.sh)
#   - GARD app stack up (docker compose -f deploy/docker-compose.yml up -d)
#
# Usage:
#   ./deploy/scripts/sync-gard-netbox.sh
#
# Optional:
#   GARD_API_URL=http://127.0.0.1:8080
#   GARD_NETBOX_URL=http://127.0.0.1:18888   (host; container uses host.docker.internal)
#   SKIP_REBUILD=1                             skip docker image rebuild

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/deploy/docker-compose.yml"
COMPOSE_PROJECT="${GARD_COMPOSE_PROJECT:-deploy}"

GARD_API_URL="${GARD_API_URL:-http://127.0.0.1:8080}"
# Host URL for curl/scripts; container must reach NetBox via host gateway.
NETBOX_HOST_URL="${NETBOX_URL:-http://127.0.0.1:18888}"
NETBOX_HOST_URL="${NETBOX_HOST_URL%/}"
NETBOX_CONTAINER_URL="${GARD_NETBOX_CONTAINER_URL:-http://host.docker.internal:18888}"
TOKEN_FILE="${GARD_JWT_FILE:-$REPO_ROOT/.gard/netbox-sync.jwt}"

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
red()  { printf '\033[31m%s\033[0m\n' "$*" >&2; }
dim()  { printf '\033[2m%s\033[0m\n' "$*"; }

require() {
  command -v "$1" >/dev/null 2>&1 || { red "missing required command: $1"; exit 127; }
}

require curl
require docker
require python3

if [[ -z "${SKIP_REBUILD:-}" ]]; then
  bold "==> Rebuilding GARD API image (F7 NetBox sync, F8 MCP, v2 token auth)"
  docker build -f "$REPO_ROOT/deploy/Dockerfile" -t gard-api:dev "$REPO_ROOT"
fi

bold "==> Minting NetBox v2 API token for GARD read sync"
# shellcheck disable=SC1091
eval "$("$SCRIPT_DIR/netbox-create-seed-token.sh")"
export GARD_NETBOX_URL="$NETBOX_CONTAINER_URL"
export GARD_NETBOX_TOKEN="$NETBOX_SEED_TOKEN"
export GARD_NETBOX_WRITE_TOKEN="${GARD_NETBOX_WRITE_TOKEN:-$NETBOX_SEED_TOKEN}"
export GARD_NETBOX_VERIFY_TLS=false
export GARD_NETBOX_WRITEBACK_ENABLED="${GARD_NETBOX_WRITEBACK_ENABLED:-true}"

bold "==> Bootstrapping NetBox write-back custom fields (F10)"
if command -v uv >/dev/null 2>&1; then
  GARD_NETBOX_URL="$NETBOX_HOST_URL" GARD_NETBOX_WRITE_TOKEN="$NETBOX_SEED_TOKEN" \
    uv run python -m gard netbox bootstrap-writeback-fields
else
  GARD_NETBOX_URL="$NETBOX_HOST_URL" GARD_NETBOX_WRITE_TOKEN="$NETBOX_SEED_TOKEN" \
    python3 -m gard netbox bootstrap-writeback-fields
fi

bold "==> Restarting GARD API with NetBox settings"
docker compose -p "$COMPOSE_PROJECT" -f "$COMPOSE_FILE" up -d api

bold "==> Waiting for GARD API"
for i in $(seq 1 30); do
  if curl -sS -o /dev/null -w '%{http_code}' "${GARD_API_URL}/healthz" 2>/dev/null | grep -q '^200$'; then
    dim "    healthy after ${i}s"
    break
  fi
  [[ $i -eq 30 ]] && { red "GARD API never became healthy at ${GARD_API_URL}"; exit 1; }
  sleep 2
done

if ! curl -sS "${GARD_API_URL}/openapi.json" | python3 -c "
import json, sys
paths = json.load(sys.stdin).get('paths', {})
assert any('netbox' in p for p in paths), 'netbox routes missing — rebuild api image'
"; then
  red "GARD API image lacks F7 NetBox routes"
  exit 1
fi

bold "==> Minting GARD service JWT (lifecycle_manager)"
mkdir -p "$(dirname "$TOKEN_FILE")"
JWT=$(docker compose -p "$COMPOSE_PROJECT" -f "$COMPOSE_FILE" exec -T api \
  python -m gard issue-token \
  --subject "sync-gard-netbox" \
  --role lifecycle_manager 2>/dev/null | awk '/^eyJ/ { print; exit }')
if [[ -z "$JWT" ]]; then
  red "failed to mint GARD JWT via issue-token"
  exit 1
fi
printf '%s\n' "$JWT" >"$TOKEN_FILE"
dim "    saved ${TOKEN_FILE}"

bold "==> Running NetBox sync"
RESP=$(curl -sS -w '\n%{http_code}' -X POST \
  -H "Authorization: Bearer ${JWT}" \
  "${GARD_API_URL}/api/v1/integrations/netbox/sync")
HTTP_CODE=$(tail -1 <<<"$RESP")
BODY=$(sed '$d' <<<"$RESP")

if [[ "$HTTP_CODE" != "200" ]]; then
  red "sync failed (HTTP ${HTTP_CODE}):"
  echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"
  exit 1
fi

echo "$BODY" | python3 -m json.tool

bold "==> Sync summary"
curl -sS -H "Authorization: Bearer ${JWT}" \
  "${GARD_API_URL}/api/v1/integrations/netbox/summary" | python3 -m json.tool

cat <<EOF

Done.

  GARD JWT:  ${TOKEN_FILE}
  Re-sync:   curl -X POST -H "Authorization: Bearer \$(cat ${TOKEN_FILE})" \\
               ${GARD_API_URL}/api/v1/integrations/netbox/sync

EOF
