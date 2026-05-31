#!/usr/bin/env bash
# Seed the optional gard-f7-netbox dev stack with DCIM devices for GARD sync demos.
#
# Requires a NetBox API token with *write* permission (dev only). This is
# separate from GARD's read-only GARD_NETBOX_TOKEN.
#
# Usage:
#   export NETBOX_SEED_TOKEN=<write-token-from-netbox-ui>
#   ./deploy/scripts/seed-netbox.sh
#
# Optional:
#   NETBOX_URL=http://127.0.0.1:18888   (default)
#   NETBOX_COMPOSE_PROJECT=gard-f7-netbox

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/deploy/netbox/docker-compose.yml"
COMPOSE_PROJECT="${NETBOX_COMPOSE_PROJECT:-gard-f7-netbox}"

NETBOX_URL="${NETBOX_URL:-http://127.0.0.1:18888}"
NETBOX_URL="${NETBOX_URL%/}"

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
red()  { printf '\033[31m%s\033[0m\n' "$*" >&2; }
dim()  { printf '\033[2m%s\033[0m\n' "$*"; }

require() {
  command -v "$1" >/dev/null 2>&1 || { red "missing required command: $1"; exit 127; }
}

require curl
require python3

if [[ -z "${NETBOX_SEED_TOKEN:-}" ]]; then
  red "NETBOX_SEED_TOKEN is required (NetBox write token for dev seeding only)"
  exit 1
fi

nb_api() {
  local method="$1"
  local path="$2"
  local data="${3:-}"
  if [[ -n "$data" ]]; then
    curl -sS -X "$method" \
      -H "Authorization: Token ${NETBOX_SEED_TOKEN}" \
      -H "Content-Type: application/json" \
      -H "Accept: application/json" \
      -d "$data" \
      "${NETBOX_URL}/api${path}"
  else
    curl -sS -X "$method" \
      -H "Authorization: Token ${NETBOX_SEED_TOKEN}" \
      -H "Accept: application/json" \
      "${NETBOX_URL}/api${path}"
  fi
}

ensure_id() {
  # POST helper: print numeric id from response, or fetch existing on duplicate slug/name.
  local create_path="$1"
  local lookup_path="$2"
  local payload="$3"
  local resp
  resp=$(nb_api POST "$create_path" "$payload")
  local id
  id=$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("id",""))' <<<"$resp" 2>/dev/null || true)
  if [[ -n "$id" && "$id" != "None" ]]; then
    echo "$id"
    return
  fi
  # fallback lookup (slug in payload)
  local slug
  slug=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1]).get("slug",""))' "$payload")
  resp=$(nb_api GET "${lookup_path}?slug=${slug}&limit=1")
  python3 -c 'import json,sys; r=json.load(sys.stdin); print(r["results"][0]["id"] if r.get("results") else "")' <<<"$resp"
}

bold "==> Waiting for NetBox at ${NETBOX_URL}/login/"
for i in $(seq 1 60); do
  if curl -sS -o /dev/null -w '%{http_code}' "${NETBOX_URL}/login/" 2>/dev/null | grep -q '^200$'; then
    dim "    healthy after ${i}s"
    break
  fi
  [[ $i -eq 60 ]] && { red "NetBox never became healthy"; exit 1; }
  sleep 2
done

bold "==> Ensuring NetBox reference objects (site, manufacturer, device type, role, tag)"
SITE_ID=$(ensure_id "/dcim/sites/" "/dcim/sites/" \
  '{"name":"Oslo DC1","slug":"oslo-dc1","status":"active"}')
MFG_ID=$(ensure_id "/dcim/manufacturers/" "/dcim/manufacturers/" \
  '{"name":"Cisco","slug":"cisco"}')
DTYPE_ID=$(ensure_id "/dcim/device-types/" "/dcim/device-types/" \
  "$(python3 - <<PY
import json
print(json.dumps({"manufacturer": int("${MFG_ID}"), "model": "ISR1121-8P", "slug": "isr1121-8p"}))
PY
)")
ROLE_ID=$(ensure_id "/dcim/device-roles/" "/dcim/device-roles/" \
  '{"name":"edge","slug":"edge","color":"2196f3"}')
TAG_ID=$(ensure_id "/extras/tags/" "/extras/tags/" \
  '{"name":"edge","slug":"edge","color":"ff9800"}')

seed_device() {
  local name="$1"
  local serial="$2"
  local existing
  existing=$(nb_api GET "/dcim/devices/?serial=${serial}&limit=1")
  local found
  found=$(python3 -c 'import json,sys; r=json.load(sys.stdin); print(r["results"][0]["id"] if r.get("results") else "")' <<<"$existing")
  if [[ -n "$found" ]]; then
    dim "    device ${name} (serial ${serial}) already exists — skip"
    return
  fi
  local payload
  payload=$(python3 - <<PY
import json
print(json.dumps({
  "name": "${name}",
  "serial": "${serial}",
  "site": int("${SITE_ID}"),
  "device_type": int("${DTYPE_ID}"),
  "role": int("${ROLE_ID}"),
  "status": "active",
  "tags": [{"id": int("${TAG_ID}")}],
}))
PY
)
  nb_api POST "/dcim/devices/" "$payload" >/dev/null
  dim "    created device ${name} (serial ${serial})"
}

bold "==> Seeding ISR1121-aligned devices (matches deploy/scripts/fixtures/isr1121-devices.csv)"
seed_device "r-osl-001" "FOC123456"
seed_device "r-osl-002" "FOC123457"

bold "==> Done. Point GARD at NetBox and sync:"
cat <<EOF

  export GARD_NETBOX_URL=${NETBOX_URL}
  export GARD_NETBOX_TOKEN=<read-only-token>
  export GARD_NETBOX_VERIFY_TLS=false

  curl -X POST -H "Authorization: Bearer \$(cat .gard/token.jwt)" \\
    http://127.0.0.1:8080/api/v1/integrations/netbox/sync

NetBox stack (this project only):
  docker compose -p ${COMPOSE_PROJECT} -f deploy/netbox/docker-compose.yml up -d
  docker compose -p ${COMPOSE_PROJECT} -f deploy/netbox/docker-compose.yml down

EOF
