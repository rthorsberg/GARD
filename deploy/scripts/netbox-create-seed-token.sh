#!/usr/bin/env bash
# Mint a NetBox v2 API token for dev seed/bootstrap (gard-f7-netbox stack).
#
# Prints a bearer token once (nbt_<key>.<secret>) — save it; NetBox cannot
# show the secret again.
#
# Usage:
#   eval "$(./deploy/scripts/netbox-create-seed-token.sh)"
#   ./deploy/scripts/seed-netbox.sh

set -euo pipefail

CONTAINER="${NETBOX_CONTAINER:-gard-f7-netbox-netbox-1}"

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "NetBox container not running: $CONTAINER" >&2
  exit 1
fi

TOKEN=$(docker exec "$CONTAINER" /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py shell -c "
from users.models import Token, User
u = User.objects.get(username='admin')
t = Token.objects.create(user=u, write_enabled=True, description='gard-f7-seed')
print(f'nbt_{t.key}.{t.token}')
" 2>/dev/null | tail -1)

printf 'export NETBOX_SEED_TOKEN=%q\n' "$TOKEN"
printf 'export NETBOX_URL=%q\n' "${NETBOX_URL:-http://127.0.0.1:18888}"
