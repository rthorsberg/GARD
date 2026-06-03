#!/usr/bin/env bash
# Shared paths for netbox-platform-standalone scripts.

set -euo pipefail

export ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export COMPOSE_PROJECT="${COMPOSE_PROJECT:-netbox-platform}"
export ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"
export COMPOSE_FILE="$ROOT_DIR/docker-compose.yml"

compose() {
  local extra=()
  if [[ -f "$ENV_FILE" ]]; then
    extra+=(--env-file "$ENV_FILE")
  fi
  if [[ -n "${COMPOSE_EXTRA_FILES:-}" ]]; then
    # shellcheck disable=SC2206
    extra+=(${COMPOSE_EXTRA_FILES})
  fi
  if [[ -n "${COMPOSE_PROFILES:-}" ]]; then
    export COMPOSE_PROFILES
  fi
  docker compose -p "$COMPOSE_PROJECT" -f "$COMPOSE_FILE" "${extra[@]}" "$@"
}

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
dim()  { printf '\033[2m%s\033[0m\n' "$*"; }
red()  { printf '\033[31m%s\033[0m\n' "$*" >&2; }
