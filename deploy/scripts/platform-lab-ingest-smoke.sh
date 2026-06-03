#!/usr/bin/env bash
# Verify Orb → Diode → NetBox ingest against fixture catalogue (no GARD).
#
# Usage:
#   ./deploy/scripts/platform-lab-ingest-smoke.sh
#
# Prerequisites:
#   - platform lab running
#   - F9 device types bootstrapped
#   - DIODE_CLIENT_ID / DIODE_CLIENT_SECRET configured for orb-agent

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CATALOGUE="$REPO_ROOT/deploy/scripts/fixtures/platform-lab/ingest-catalogue.yaml"
NETBOX_URL="${NETBOX_URL:-http://127.0.0.1:18888}"
NETBOX_URL="${NETBOX_URL%/}"
WAIT_SECONDS="${PLATFORM_LAB_INGEST_WAIT:-300}"

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
red()  { printf '\033[31m%s\033[0m\n' "$*" >&2; }

require() {
  command -v "$1" >/dev/null 2>&1 || { red "missing required command: $1"; exit 127; }
}

require curl
require python3

if [[ ! -f "$CATALOGUE" ]]; then
  red "missing catalogue: $CATALOGUE"
  exit 1
fi

if [[ -z "${NETBOX_SEED_TOKEN:-}" ]]; then
  bold "==> Minting NetBox token for read verification"
  # shellcheck disable=SC1091
  eval "$("$SCRIPT_DIR/netbox-create-seed-token.sh")"
fi

read -r MIN_COUNT EXPECTED_NAMES <<<"$(python3 - <<'PY' "$CATALOGUE"
import sys, yaml
cat = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
names = " ".join(d["name"] for d in cat["devices"])
print(cat["minimum_device_count"], names)
PY
)"

bold "==> Waiting up to ${WAIT_SECONDS}s for >= ${MIN_COUNT} catalogue devices in NetBox"
deadline=$((SECONDS + WAIT_SECONDS))
found=0
while (( SECONDS < deadline )); do
  resp=$(curl -sS -H "Authorization: Token ${NETBOX_SEED_TOKEN}" \
    "${NETBOX_URL}/api/dcim/devices/?limit=100")
  found=$(python3 -c "
import json, sys
expected = set('${EXPECTED_NAMES}'.split())
data = json.loads(sys.argv[1])
names = {r['name'] for r in data.get('results', [])}
print(len(expected & names))
" "$resp")
  if (( found >= MIN_COUNT )); then
    bold "==> Ingest smoke passed ($found / $MIN_COUNT expected catalogue devices visible on main)"
    exit 0
  fi
  sleep 15
done

red "Ingest smoke failed: only $found / $MIN_COUNT catalogue devices found after ${WAIT_SECONDS}s"
red "Check orb-agent and diode-reconciler logs; verify DIODE_CLIENT_* in deploy/netbox/.env"
exit 1
