# GARD — Local Docker stack

A self-contained, reproducible local stack: Postgres 16 + GARD API,
with database migrations and the normalization-rule catalog
**bootstrapped automatically** on first boot.

## TL;DR

```bash
# from repo root
docker compose -f deploy/docker-compose.yml up -d --build
curl http://127.0.0.1:8080/healthz
# {"status":"ok","version":"0.1.0","service":"gard"}
```

The first `up` will build the image, start Postgres, run the
one-shot `migrate` service to apply Alembic migrations, then start
the API. The API's lifespan handler then upserts every YAML rule
from `gard-catalog/normalization/` into the `normalization_rules`
table (5 vendor rules at the time of writing).

## Topology

| Service | Image | Role | Port (host) |
|---|---|---|---|
| `postgres` | `postgres:16-alpine` | Application + audit + evidence DB | 5432 |
| `migrate` | `gard-api:dev` | One-shot — `alembic upgrade head`, then exits | — |
| `api` | `gard-api:dev` | FastAPI on uvicorn | 8080 → 8000 |

`api` waits on both `postgres` (healthy) and `migrate`
(`service_completed_successfully`), so a fresh `up` is safe to run
even on an empty volume.

The host port for the API is configurable via `GARD_API_HOST_PORT`
to avoid collisions with whatever else you have running on `:8000`:

```bash
GARD_API_HOST_PORT=9090 docker compose -f deploy/docker-compose.yml up -d
```

## Common operations

```bash
# tail API logs
docker compose -f deploy/docker-compose.yml logs -f api

# mint a bootstrap JWT (the API requires Bearer auth on every /api/v1 route)
docker compose -f deploy/docker-compose.yml exec api \
  python -m gard issue-token --subject ops@example.com --role lifecycle_manager --ttl-seconds 3600

# manually re-run catalog load (idempotent)
docker compose -f deploy/docker-compose.yml exec api python -m gard catalog reload

# connect a psql shell
docker compose -f deploy/docker-compose.yml exec postgres psql -U gard -d gard

# wipe everything (including the volume)
docker compose -f deploy/docker-compose.yml down -v
```

## Smoke test (CSV import → classified Devices)

```bash
TOK=$(docker compose -f deploy/docker-compose.yml exec api \
  python -m gard issue-token --subject ops@example.com --role lifecycle_manager --ttl-seconds 3600 \
  | grep -E '^eyJ')

cat > /tmp/gard-smoke.csv <<'CSV'
hostname,site,serial_number,vendor_raw,model_raw,observed_firmware,os_string,management_ip,observed_at,actor_email
r1.oslo,oslo-1,FOX1234ABC1,Cisco Systems,ASR9006,7.5.2,Cisco IOS XR Software 7.5.2,10.0.0.1,2026-05-28T20:00:00Z,ops@example.com
r2.oslo,oslo-1,JN1234567890,Juniper Networks,MX204,22.4R3-S2,Junos 22.4R3-S2,10.0.0.2,2026-05-28T20:00:00Z,ops@example.com
r3.oslo,oslo-1,NS1234567890,Nokia,7750 SR-1,23.10.R3,TiMOS-B-23.10.R3,10.0.0.3,2026-05-28T20:00:00Z,ops@example.com
CSV

curl -sS -X POST -H "Authorization: Bearer $TOK" \
  -F "file=@/tmp/gard-smoke.csv;type=text/csv" \
  -F "actor_email=ops@example.com" \
  http://127.0.0.1:8080/api/v1/imports/devices/csv

curl -sS -H "Authorization: Bearer $TOK" http://127.0.0.1:8080/api/v1/devices
```

Expected: three `classified` Devices, each with envelope
`confidence=0.85` and `reasons[0].ref` set to the matching rule
(`cisco-iosxr`, `juniper-junos`, `nokia-sros`).

## Notes

- `GARD_REQUIRE_TLS=false` is set explicitly on the dev compose stack;
  in `prod` mode (`GARD_ENV=prod`) the API refuses to start unless
  TLS is on **and** `GARD_DATABASE_URL_APPEND_ONLY` points at a
  distinct DSN connecting as the `gard_writer_append_only` role per
  ADR-0009.
- The image runs as a non-root `gard` user (uid 10001).
- The healthcheck inside the container hits `/healthz` directly; the
  Dockerfile exposes `:8000` and the entrypoint binds to `0.0.0.0`.
- Migrations are run via `python -m alembic` (no console-script
  shim is shipped in the runtime image).
