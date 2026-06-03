#!/usr/bin/env bash
# Demonstrate Branching merge gate: branch-only IP change invisible on main until merge.
#
# Usage:
#   GARD_NETBOX_BRANCHING_ENABLED=1 ./deploy/scripts/platform-lab-merge-demo.sh
#
# When Branching is disabled, prints fallback instructions (direct main edit).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
NETBOX_DIR="$REPO_ROOT/deploy/netbox"
ENV_FILE="${NETBOX_ENV_FILE:-$NETBOX_DIR/.env}"
NETBOX_URL="${NETBOX_URL:-http://127.0.0.1:18888}"
NETBOX_URL="${NETBOX_URL%/}"

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
red()  { printf '\033[31m%s\033[0m\n' "$*" >&2; }

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a
  source "$ENV_FILE"
  set +a
fi

if [[ "${GARD_NETBOX_BRANCHING_ENABLED:-0}" != "1" ]]; then
  cat <<'EOF'
Branching is disabled (GARD_NETBOX_BRANCHING_ENABLED=0).

Fallback (FR-011): edit device IP assignments directly on main in NetBox UI,
then run ./deploy/scripts/sync-gard-netbox.sh and verify F12 alignment output.

To run this demo: rebuild with GARD_NETBOX_BRANCHING_ENABLED=1 and restart lab.
EOF
  exit 0
fi

if [[ -z "${NETBOX_SEED_TOKEN:-}" ]]; then
  eval "$("$SCRIPT_DIR/netbox-create-seed-token.sh")"
fi

auth_hdr="Authorization: Token ${NETBOX_SEED_TOKEN}"

device_name="${PLATFORM_LAB_MERGE_DEVICE:-lab-router-01}"
branch_name="gard-lab-merge-demo-$(date +%s)"

bold "==> Selecting device: $device_name"
device_json=$(curl -sS -H "$auth_hdr" \
  "${NETBOX_URL}/api/dcim/devices/?name=${device_name}&limit=1")
device_id=$(python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('results',[]); assert r, 'device not found — run ingest smoke first'; print(r[0]['id'])" <<<"$device_json")

bold "==> Main primary IP before branch"
curl -sS -H "$auth_hdr" "${NETBOX_URL}/api/dcim/devices/${device_id}/" | python3 -m json.tool | grep -E '"primary_ip4"|"name"' || true

bold "==> Creating branch: $branch_name"
branch_json=$(curl -sS -X POST -H "$auth_hdr" -H "Content-Type: application/json" \
  "${NETBOX_URL}/api/plugins/branching/branches/" \
  -d "{\"name\": \"${branch_name}\", \"description\": \"GARD F13 merge demo\"}")
branch_id=$(python3 -c "import json,sys; print(json.load(sys.stdin)['id'])" <<<"$branch_json")
branch_schema=$(python3 -c "import json,sys; print(json.load(sys.stdin)['schema_id'])" <<<"$branch_json")

bold "==> Waiting for branch provisioning (schema_id=$branch_schema)"
for _ in $(seq 1 30); do
  status=$(curl -sS -H "$auth_hdr" \
    "${NETBOX_URL}/api/plugins/branching/branches/${branch_id}/" | python3 -c "import json,sys; print(json.load(sys.stdin).get('status',{}).get('value',''))")
  [[ "$status" == "ready" ]] && break
  sleep 5
done

bold "==> Staging comment change on branch (demo mutation)"
curl -sS -X PATCH -H "$auth_hdr" -H "Content-Type: application/json" \
  -H "X-NetBox-Branch: ${branch_schema}" \
  "${NETBOX_URL}/api/dcim/devices/${device_id}/" \
  -d '{"comments": "gard-f13-branch-only-change"}' >/dev/null

bold "==> Main still shows pre-branch comments (GARD would not see branch edit)"
curl -sS -H "$auth_hdr" "${NETBOX_URL}/api/dcim/devices/${device_id}/" | python3 -c "import json,sys; d=json.load(sys.stdin); print('main comments:', d.get('comments') or '(empty)')"

bold "==> Merging branch to main"
curl -sS -X POST -H "$auth_hdr" -H "Content-Type: application/json" \
  "${NETBOX_URL}/api/plugins/branching/branches/${branch_id}/merge/" \
  -d '{"commit": true}' >/dev/null

sleep 5
bold "==> Main after merge"
curl -sS -H "$auth_hdr" "${NETBOX_URL}/api/dcim/devices/${device_id}/" | python3 -c "import json,sys; d=json.load(sys.stdin); print('main comments:', d.get('comments') or '(empty)')"

cat <<EOF

Merge demo complete. Run GARD sync:

  ./deploy/scripts/sync-gard-netbox.sh

See specs/013-netbox-platform-lab/quickstart.md section 6.

EOF
