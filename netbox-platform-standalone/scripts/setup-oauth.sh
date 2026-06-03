#!/usr/bin/env bash
# Bootstrap Diode OAuth clients and print steps to finish .env + Orb config.

set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"

if [[ ! -f "$ENV_FILE" ]]; then
  red "Missing $ENV_FILE — run ./scripts/start.sh first"
  exit 1
fi

bold "==> Re-run Hydra client bootstrap"
compose run --rm diode-auth-bootstrap 2>&1 | tail -5

bold "==> Read secrets from platform/diode/oauth2/client/client-credentials.json"
NB_SECRET=$(python3 -c "import json; print([c['client_secret'] for c in json.load(open('$ROOT_DIR/platform/diode/oauth2/client/client-credentials.json')) if c['client_id']=='netbox-to-diode'][0])")
DN_SECRET=$(python3 -c "import json; print([c['client_secret'] for c in json.load(open('$ROOT_DIR/platform/diode/oauth2/client/client-credentials.json')) if c['client_id']=='diode-to-netbox'][0])")

if [[ "$NB_SECRET" == REPLACE_WITH_STRONG_SECRET ]]; then
  red "Edit platform/diode/oauth2/client/client-credentials.json with real secrets first, then re-run."
  exit 1
fi

bold "==> Patching $ENV_FILE (NETBOX_TO_DIODE / DIODE_TO_NETBOX secrets)"
# shellcheck disable=SC1090
set -a
source "$ENV_FILE"
set +a

tmp=$(mktemp)
grep -v '^NETBOX_TO_DIODE_CLIENT_SECRET=' "$ENV_FILE" | grep -v '^DIODE_TO_NETBOX_CLIENT_SECRET=' >"$tmp" || true
{
  cat "$tmp"
  echo "NETBOX_TO_DIODE_CLIENT_SECRET=$NB_SECRET"
  echo "DIODE_TO_NETBOX_CLIENT_SECRET=$DN_SECRET"
} >"$ENV_FILE"
rm -f "$tmp"

bold "==> Restart NetBox + Diode services"
compose up -d netbox netbox-worker diode-auth diode-reconciler diode-nginx

bold "==> Create Orb ingest client (save output)"
ORB_ID="${ORB_CLIENT_ID:-orb-discovery}"
ORB_SECRET="${ORB_CLIENT_SECRET:-}"
if [[ -z "$ORB_SECRET" ]]; then
  ORB_SECRET="orb-$(openssl rand -hex 16)"
fi
compose run --rm --no-deps diode-auth authmanager create-client \
  --client-id "$ORB_ID" \
  --allow-ingest \
  --client-secret "$ORB_SECRET" 2>&1 || true

tmp=$(mktemp)
grep -v '^DIODE_CLIENT_ID=' "$ENV_FILE" | grep -v '^DIODE_CLIENT_SECRET=' >"$tmp" || true
{
  cat "$tmp"
  echo "DIODE_CLIENT_ID=$ORB_ID"
  echo "DIODE_CLIENT_SECRET=$ORB_SECRET"
} >"$ENV_FILE"
rm -f "$tmp"

AGENT_YAML="$ROOT_DIR/platform/orb/agent.yaml"
if [[ -f "$AGENT_YAML" ]]; then
  sed -i.bak -E "s/^([[:space:]]*client_id:).*/\1 $ORB_ID/" "$AGENT_YAML"
  sed -i.bak -E "s/^([[:space:]]*client_secret:).*/\1 $ORB_SECRET/" "$AGENT_YAML"
  rm -f "${AGENT_YAML}.bak"
  dim "    Patched $AGENT_YAML"
fi

compose restart orb-agent diode-nginx

cat <<EOF

Orb credentials written to .env and platform/orb/agent.yaml.

  client_id: $ORB_ID
  client_secret: (in .env — not repeated here)

Next:
  ./scripts/health.sh | jq .

Optional: NetBox UI → Diode → Client Credentials (alternate to authmanager).

EOF
