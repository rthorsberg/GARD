#!/usr/bin/env bash
# Start NetBox + Diode + Orb stack.
#
# Usage:
#   ./scripts/start.sh
#   COMPOSE_EXTRA_FILES="-f docker-compose.orb-host.yml" ./scripts/start.sh
#   docker compose --profile lab  →  COMPOSE_PROFILES=lab ./scripts/start.sh

set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"

if [[ ! -f "$ENV_FILE" ]]; then
  bold "==> Creating $ENV_FILE from .env.example"
  cp "$ROOT_DIR/.env.example" "$ENV_FILE"
  dim "    Edit secrets, then re-run if needed (see docs/diode-oauth.md)"
fi

# shellcheck disable=SC1090
set -a
source "$ENV_FILE"
set +a

bold "==> Starting stack (project: $COMPOSE_PROJECT)"
compose up -d --build

PORT="${NETBOX_HOST_PORT:-18888}"
bold "==> Waiting for NetBox UI on port $PORT"
for i in $(seq 1 60); do
  if curl -fsS -o /dev/null "http://127.0.0.1:${PORT}/login/" 2>/dev/null; then
    dim "    healthy after ${i} attempts"
    break
  fi
  [[ $i -eq 60 ]] && { red "NetBox did not become healthy"; exit 1; }
  sleep 5
done

cat <<EOF

Stack is up.

  NetBox UI:  http://127.0.0.1:${PORT}/
  Diode gRPC: 127.0.0.1:${DIODE_GRPC_HOST_PORT:-58080}

Next:
  ./scripts/setup-oauth.sh
  ./scripts/health.sh | jq .

EOF
