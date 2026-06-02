# GARD F7 — NetBox dev stack

Optional read-only NetBox lab for F7 integration work. **Isolated** from:

- GARD app stack (`deploy/docker-compose.yml`, port 8080 / 5432)
- Other NetBox labs (e.g. `ietf004-nb-ref` on port **18080**)

## Start

```bash
docker compose -p gard-f7-netbox -f deploy/netbox/docker-compose.yml up -d
```

UI: [http://127.0.0.1:18888/](http://127.0.0.1:18888/)

## Stop (this project only)

```bash
docker compose -p gard-f7-netbox -f deploy/netbox/docker-compose.yml down
```

Add `-v` only if you intentionally wipe **this** stack's data volumes.

## Never run

These can destroy unrelated containers/volumes:

```bash
docker system prune
docker container prune
docker compose -f deploy/netbox/docker-compose.yml down -v   # missing -p gard-f7-netbox
```

## Ports

| Service | Host port | Override env |
|---------|-----------|--------------|
| NetBox UI | 18888 | `GARD_NETBOX_HOST_PORT` |
| Postgres | 55432 | `GARD_NETBOX_PG_HOST_PORT` |
| Redis | (internal) | — |

## Configuration

Copy and edit:

```bash
cp deploy/netbox/.env.example deploy/netbox/.env
docker compose -p gard-f7-netbox -f deploy/netbox/docker-compose.yml --env-file deploy/netbox/.env up -d
```

See [specs/007-netbox-integration-read/quickstart.md](../specs/007-netbox-integration-read/quickstart.md) for token setup and GARD settings.

## Device type bootstrap (F9)

Before seeding devices, import curated community device types from the pinned manifest:

```bash
git submodule update --init vendor/netbox-devicetype-library
export GARD_NETBOX_URL=http://127.0.0.1:18888
export GARD_NETBOX_TOKEN=$NETBOX_SEED_TOKEN
export GARD_NETBOX_VERIFY_TLS=false
python -m gard netbox bootstrap-device-types
```

`seed-netbox.sh` runs bootstrap automatically. For production NetBox, use `--confirm`. See [specs/009-netbox-devicetype-bootstrap/quickstart.md](../../specs/009-netbox-devicetype-bootstrap/quickstart.md).

## F12 IPAM alignment

GARD sync reads this NetBox instance via REST on `main` only (no Orb/Diode/Branching integration in F12). After device reconcile, alignment validates IP/VRF/VLAN policy — see [specs/012-netbox-ipam-dcim-align/quickstart.md](../../specs/012-netbox-ipam-dcim-align/quickstart.md).
