#!/usr/bin/env bash
# Stop stack (project-scoped). Use --volumes to wipe this project's data only.

set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"

WIPE=0
if [[ "${1:-}" == "--volumes" || "${1:-}" == "-v" ]]; then
  WIPE=1
fi

if [[ $WIPE -eq 1 ]]; then
  bold "Stopping and removing volumes for project: $COMPOSE_PROJECT"
  compose down -v
else
  bold "Stopping (volumes preserved) for project: $COMPOSE_PROJECT"
  compose down
fi

dim "Done."
