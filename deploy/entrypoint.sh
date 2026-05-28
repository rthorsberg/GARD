#!/usr/bin/env bash
set -euo pipefail

cmd="${1:-serve}"

case "$cmd" in
  serve)
    exec python -m uvicorn gard.api.app:app --host "${GARD_API_HOST:-0.0.0.0}" --port "${GARD_API_PORT:-8000}"
    ;;
  mcp)
    exec python -m gard mcp
    ;;
  migrate)
    exec python -m alembic -c gard/db/alembic.ini upgrade head
    ;;
  *)
    exec python -m gard "$@"
    ;;
esac
