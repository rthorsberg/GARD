# GARD F7 — NetBox dev stack

Optional read-only NetBox lab for F7 integration work. **Isolated** from:

- GARD app stack (`deploy/docker-compose.yml`, port 8080 / 5432)
- Other NetBox labs (e.g. `ietf004-nb-ref` on port **18080**)

## F7-only start

```bash
docker compose -p gard-f7-netbox -f deploy/netbox/docker-compose.yml up -d
```

UI: [http://127.0.0.1:18888/](http://127.0.0.1:18888/)

## F13 platform lab (Orb + Diode + Branching optional)

```bash
cp deploy/netbox/.env.example deploy/netbox/.env   # first time
./deploy/scripts/platform-lab-start.sh
./deploy/scripts/platform-lab-health.sh | jq .
./deploy/scripts/platform-lab-stop.sh
```

Runbook: [specs/013-netbox-platform-lab/quickstart.md](../../specs/013-netbox-platform-lab/quickstart.md)

### Standalone bundle (no GARD code)

For a discovery host or agent VM, use the self-contained folder (sparse-checkout friendly):

[netbox-platform-standalone/](../../netbox-platform-standalone/README.md) — single `docker-compose.yml`, project `netbox-platform`, same Orb → Diode → NetBox path without cloning the full GARD repo.

### Port matrix

| Service | Host port | Override env | Notes |
|---------|-----------|--------------|-------|
| NetBox UI | 18888 | `GARD_NETBOX_HOST_PORT` | GARD reads `main` here |
| NetBox Postgres | 55432 | `GARD_NETBOX_PG_HOST_PORT` | Debug only |
| Diode gRPC (nginx) | 58080 | `GARD_DIODE_GRPC_HOST_PORT` | Orb agent target |

**Collisions**: If 18888 is taken (another NetBox lab), set `GARD_NETBOX_HOST_PORT`. GARD API uses 8080 — do not remap without updating `sync-gard-netbox.sh`.

### Isolation

- Always use compose project **`gard-f7-netbox`**
- Never run `docker system prune` or `docker compose down -v` without `-p gard-f7-netbox`

## Stop (this project only)

```bash
./deploy/scripts/platform-lab-stop.sh
# or F7-only:
docker compose -p gard-f7-netbox -f deploy/netbox/docker-compose.yml down
```

Add `--volumes` to `platform-lab-stop.sh` only when intentionally wiping **this** lab's data.

## Never run

These can destroy unrelated containers/volumes:

```bash
docker system prune
docker container prune
docker compose -f deploy/netbox/docker-compose.yml down -v   # missing -p gard-f7-netbox
```

## Configuration

Copy and edit:

```bash
cp deploy/netbox/.env.example deploy/netbox/.env
docker compose -p gard-f7-netbox -f deploy/netbox/docker-compose.yml --env-file deploy/netbox/.env up -d
```

See [specs/007-netbox-integration-read/quickstart.md](../specs/007-netbox-integration-read/quickstart.md) for token setup and GARD settings.

## Device type bootstrap (F9)

Before seeding devices or running platform ingest smoke, import curated community device types:

```bash
git submodule update --init vendor/netbox-devicetype-library
export GARD_NETBOX_URL=http://127.0.0.1:18888
export GARD_NETBOX_TOKEN=$NETBOX_SEED_TOKEN
export GARD_NETBOX_VERIFY_TLS=false
python -m gard netbox bootstrap-device-types
```

## F12 IPAM alignment & drift scenarios

GARD sync reads NetBox REST on `main` only. After merge-to-main (F13) or seed (F7), run alignment validation:

- [F12 quickstart](../../specs/012-netbox-ipam-dcim-align/quickstart.md)
- Drift scenarios: [deploy/scripts/fixtures/platform-lab/drift-scenarios/](../scripts/fixtures/platform-lab/drift-scenarios/)

## F12 note (upstream)

F12 does not deploy Orb/Diode/Branching. F13 platform lab exercises the upstream path documented in [ADR-0024](../../adr/ADR-0024-netbox-platform-lab-boundary.md).
