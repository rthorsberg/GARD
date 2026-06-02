# F7 — NetBox dev stack quickstart

## Safety first (read this)

This stack is **isolated** from your other Docker projects.

- Project name: **`gard-f7-netbox`**
- UI port: **18888** (your existing `ietf004-nb-ref` uses **18080**)
- Postgres port: **55432** (GARD uses **5432**)

**Do NOT run** generic cleanup commands against all containers:

```bash
# NEVER — would hit other projects
docker compose down -v
docker system prune
```

**Only** stop this stack:

```bash
docker compose -p gard-f7-netbox -f deploy/netbox/docker-compose.yml down
```

## Start dev NetBox

```bash
cd /path/to/GARD
docker compose -p gard-f7-netbox -f deploy/netbox/docker-compose.yml up -d
```

Wait ~90s, then open [http://127.0.0.1:18888/](http://127.0.0.1:18888/)

Default superuser (dev only — change after first login):

- Username: `admin`
- Password: see `deploy/netbox/.env.example` (`NETBOX_SUPERUSER_PASSWORD`)

## Create API token

1. Log in → Admin → Users → your user → Add token
2. Permissions: **Read-only** (no write)
3. Export for GARD:

```bash
export GARD_NETBOX_URL=http://127.0.0.1:18888
export GARD_NETBOX_TOKEN=<paste-token>
```

## Use existing NetBox instead

If you prefer your lab instance on port 18080:

```bash
export GARD_NETBOX_URL=http://127.0.0.1:18080
export GARD_NETBOX_TOKEN=<token-from-that-instance>
```

No need to start `gard-f7-netbox` at all.

## After F7 implementation

```bash
export GARD_NETBOX_URL=http://127.0.0.1:18888
export GARD_NETBOX_TOKEN=<read-only-token>
export GARD_NETBOX_WRITE_TOKEN=<write-token>   # F10 write-back
export GARD_NETBOX_WRITEBACK_ENABLED=true
export GARD_NETBOX_VERIFY_TLS=false

# Optional: seed NetBox with ISR1121-aligned devices (write token, dev only)
# F9: seed-netbox.sh bootstraps community device types first — see specs/009-netbox-devicetype-bootstrap/quickstart.md
# F10: seed-netbox.sh also bootstraps write-back custom fields — see specs/010-netbox-writeback/quickstart.md
export NETBOX_SEED_TOKEN=<write-token>
./deploy/scripts/seed-netbox.sh

curl -X POST -H "Authorization: Bearer $(cat .gard/token.jwt)" \
  http://127.0.0.1:8080/api/v1/integrations/netbox/sync

curl -H "Authorization: Bearer $(cat .gard/token.jwt)" \
  http://127.0.0.1:8080/api/v1/integrations/netbox/summary
```

Sync response includes `data.report.writeback` with per-device outcomes (F10). Run compliance/readiness evaluate before sync when fresh lifecycle mirrors are needed.

## Verify isolation

Before and after starting, compare container IDs:

```bash
docker ps -a --format '{{.Names}}' | sort
```

Names outside `gard-f7-netbox-*` should be unchanged.

## F12 — IPAM alignment (post-sync)

After F7 device sync, GARD runs an IPAM/DCIM alignment phase (ADR-0023): management IP, interface IPAM, VRF, and VLAN checks against `gard-catalog/netbox/alignment-policy-manifest.yaml`. Results appear in `report.ipam_alignment` on sync and on the operator portal NetBox / device Network tabs.

See [specs/012-netbox-ipam-dcim-align/quickstart.md](../012-netbox-ipam-dcim-align/quickstart.md).
