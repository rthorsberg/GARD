#!/usr/bin/env bash
# Stop GARD F13 platform lab (project-scoped; preserves volumes by default).
#
# Usage:
#   ./deploy/scripts/platform-lab-stop.sh
#   ./deploy/scripts/platform-lab-stop.sh --volumes   # intentional wipe of THIS lab only

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
NETBOX_DIR="$REPO_ROOT/deploy/netbox"
COMPOSE_PROJECT="${NETBOX_COMPOSE_PROJECT:-gard-f7-netbox}"
ENV_FILE="${NETBOX_ENV_FILE:-$NETBOX_DIR/.env}"

WIPE_VOLUMES=0
if [[ "${1:-}" == "--volumes" || "${1:-}" == "-v" ]]; then
  WIPE_VOLUMES=1
fi

ARGS=(compose -p "$COMPOSE_PROJECT" -f "$NETBOX_DIR/docker-compose.yml" -f "$NETBOX_DIR/docker-compose.platform.yml")
if [[ -f "$ENV_FILE" ]]; then
  ARGS+=(--env-file "$ENV_FILE")
fi

if [[ $WIPE_VOLUMES -eq 1 ]]; then
  echo "Stopping platform lab and removing volumes for project: $COMPOSE_PROJECT"
  docker "${ARGS[@]}" down -v
else
  echo "Stopping platform lab (volumes preserved) for project: $COMPOSE_PROJECT"
  docker "${ARGS[@]}" down
fi

echo "Done. Other Docker projects were not affected."
