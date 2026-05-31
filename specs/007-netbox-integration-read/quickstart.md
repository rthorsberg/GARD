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

## After F7 implementation lands

```bash
# Trigger sync (endpoint name from contracts/rest-openapi.yaml)
curl -X POST -H "Authorization: Bearer $(cat .gard/token.jwt)" \
  http://127.0.0.1:8080/api/v1/integrations/netbox/sync
```

## Verify isolation

Before and after starting, compare container IDs:

```bash
docker ps -a --format '{{.Names}}' | sort
```

Names outside `gard-f7-netbox-*` should be unchanged.
