#!/usr/bin/env bash
# Start GARD F13 NetBox platform lab (NetBox + Diode + Orb + simulators).
#
# Usage:
#   ./deploy/scripts/platform-lab-start.sh
#
# Optional:
#   GARD_NETBOX_BRANCHING_ENABLED=1 ./deploy/scripts/platform-lab-start.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
NETBOX_DIR="$REPO_ROOT/deploy/netbox"
COMPOSE_PROJECT="${NETBOX_COMPOSE_PROJECT:-gard-f7-netbox}"
ENV_FILE="${NETBOX_ENV_FILE:-$NETBOX_DIR/.env}"

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
dim()  { printf '\033[2m%s\033[0m\n' "$*"; }
red()  { printf '\033[31m%s\033[0m\n' "$*" >&2; }

require() {
  command -v "$1" >/dev/null 2>&1 || { red "missing required command: $1"; exit 127; }
}

require docker

if [[ ! -f "$ENV_FILE" ]]; then
  bold "==> Creating $ENV_FILE from .env.example"
  cp "$NETBOX_DIR/.env.example" "$ENV_FILE"
  dim "    Edit Diode/Orb secrets before ingest smoke (see quickstart section 1)"
fi

# shellcheck disable=SC1090
set -a
source "$ENV_FILE"
set +a

export GARD_NETBOX_PLATFORM="${GARD_NETBOX_PLATFORM:-1}"

bold "==> Starting platform lab (project: $COMPOSE_PROJECT)"
docker compose -p "$COMPOSE_PROJECT" \
  -f "$NETBOX_DIR/docker-compose.yml" \
  -f "$NETBOX_DIR/docker-compose.platform.yml" \
  --env-file "$ENV_FILE" \
  up -d --build

NETBOX_PORT="${GARD_NETBOX_HOST_PORT:-18888}"
bold "==> Waiting for NetBox UI on port $NETBOX_PORT"
for i in $(seq 1 60); do
  if curl -fsS -o /dev/null "http://127.0.0.1:${NETBOX_PORT}/login/" 2>/dev/null; then
    dim "    healthy after ${i} attempts"
    break
  fi
  [[ $i -eq 60 ]] && { red "NetBox did not become healthy"; exit 1; }
  sleep 5
done

cat <<EOF

Platform lab is up.

  NetBox UI:  http://127.0.0.1:${NETBOX_PORT}/
  Diode gRPC: 127.0.0.1:${GARD_DIODE_GRPC_HOST_PORT:-58080} (host)

Next steps:
  1. Bootstrap device types (F9) if fresh volume
  2. Configure Diode/Orb credentials in $ENV_FILE
  3. ./deploy/scripts/platform-lab-health.sh
  4. ./deploy/scripts/platform-lab-ingest-smoke.sh

Runbook: specs/013-netbox-platform-lab/quickstart.md

EOF
