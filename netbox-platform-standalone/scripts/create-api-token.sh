#!/usr/bin/env bash
# Mint a NetBox v2 API token (write-enabled). Secret shown once.

set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"

CONTAINER="${NETBOX_CONTAINER:-${COMPOSE_PROJECT}-netbox-1}"

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  red "NetBox container not running: $CONTAINER"
  exit 1
fi

TOKEN=$(docker exec "$CONTAINER" /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py shell -c "
from users.models import Token, User
u = User.objects.get(username='admin')
t = Token.objects.create(user=u, write_enabled=True, description='platform-standalone')
print(f'nbt_{t.key}.{t.token}')
" 2>/dev/null | tail -1)

printf 'export NETBOX_API_TOKEN=%q\n' "$TOKEN"
printf 'export NETBOX_URL=%q\n' "${NETBOX_URL:-http://127.0.0.1:18888}"
