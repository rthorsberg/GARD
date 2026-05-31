# F7 — Research: 6 binding decisions

## R-1 — Isolated dev NetBox Docker project

**Decision**: GARD ships `deploy/netbox/docker-compose.yml` with Compose project name **`gard-f7-netbox`** (via top-level `name:` key). Operators MUST start it with:

```bash
docker compose -p gard-f7-netbox -f deploy/netbox/docker-compose.yml up -d
```

Never run `docker compose down`, `rm`, or `down -v` without `-p gard-f7-netbox` and without `-f deploy/netbox/docker-compose.yml`.

**Alternatives considered**: Adding NetBox as a service to `deploy/docker-compose.yml`. Rejected — couples GARD app lifecycle to NetBox and increases risk of accidental teardown.

**Rationale**: User has multiple existing NetBox stacks; isolation by project name + separate compose file is the safest default.

## R-2 — Host port allocation (avoid collisions)

**Decision**: Default published ports for the GARD dev NetBox stack:

| Service | Host port | Notes |
|---------|-----------|-------|
| NetBox UI | **18888** | Existing lab stack uses **18080** (`ietf004-nb-ref-netbox-1`) |
| NetBox Postgres | **55432** | GARD Postgres uses **5432** on host |
| Redis | *(none)* | Internal network only |

All ports overridable via env: `GARD_NETBOX_HOST_PORT`, `GARD_NETBOX_PG_HOST_PORT`.

**Alternatives considered**: Reuse 18080. Rejected — would conflict when user restarts existing stack.

## R-3 — NetBox API surface (v1)

**Decision**: Read-only client wraps:

- `GET /api/dcim/devices/` (paginated, `limit=1000`)
- `GET /api/dcim/devices/{id}/` (detail when needed)
- Tag slugs via nested serializer or secondary `GET /api/extras/tags/`

No plugins, no GraphQL, no Diode gRPC in v1.

**Rationale**: Standard NetBox REST is sufficient for identity + tags; matches ADR-0001 boundary.

## R-4 — Reconciliation identity keys

**Decision**: Match order (same as F1 CSV):

1. `serial_number` (case-insensitive) if present on both sides
2. `(hostname, site)` pair
3. Otherwise → create new GARD device OR `manual_review` if collision

Store `netbox_device_id` on match. Never delete GARD rows on orphan.

**Rationale**: Consistent with F1 `DeviceIdentity` — one reconciliation story across CSV and NetBox.

## R-5 — Tag source for `tagged_with`

**Decision**: Sync copies NetBox tag slugs into `Device.tags` (`TEXT[]` column, new migration). F4 `eval_tagged_with` reads from `Device.tags` instead of returning `predicate_deferred`.

**Alternatives considered**: Separate `device_netbox_tags` join table. Rejected for v1 — array matches existing `licenses` pattern on Device.

## R-6 — Existing NetBox instances

**Decision**: GARD settings accept any NetBox base URL. Dev compose is optional. Document pointing at `http://127.0.0.1:18080` for users who prefer their existing `ietf004-nb-ref` stack over starting `gard-f7-netbox`.

**Rationale**: Docker safety ≠ forcing a new stack; isolation is for when you need a greenfield lab.
