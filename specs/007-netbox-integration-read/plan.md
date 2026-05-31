# F7 — NetBox Integration (Read-Only): Implementation Plan

**Feature Branch**: `007-netbox-integration-read`
**Status**: Draft
**Inputs**: `spec.md`, `research.md` (R-1..R-6), `data-model.md`, `contracts/`, `quickstart.md`
**Constitution version**: 1.0.0
**Predecessors**: F1 (Device), F2 (`tagged_with` deferral), F6 (MVP slice)
**Successor**: NetBox write-back (post-v1)

## Summary

F7 adds read-only NetBox REST sync: pull DCIM devices, reconcile to GARD `Device`, populate tags, emit audit/evidence. Optional isolated dev NetBox on **port 18888** (project `gard-f7-netbox`). No NetBox writes.

Technical shape:

- **Settings**: `GARD_NETBOX_URL`, `GARD_NETBOX_TOKEN`, `GARD_NETBOX_VERIFY_TLS`, `GARD_NETBOX_SYNC_MAX_DEVICES`
- **Migration 0010**: `devices.netbox_device_id`, `netbox_last_synced_at`, `tags TEXT[]`; `netbox_sync_runs` table
- **Client**: `gard/integrations/netbox/client.py` — httpx, pagination, read-only guard
- **Controller**: `gard/core/netbox_sync_controller.py` — reconcile + report
- **REST**: `POST /api/v1/integrations/netbox/sync`, `GET .../summary`, `GET .../sync-runs`
- **ADR-0017**, **ADR-0018**
- **Dev stack**: `deploy/netbox/docker-compose.yml` (isolated, high ports)

## Technical Context

| Aspect | Choice |
|---|---|
| HTTP client | httpx (sync, existing stack pattern) |
| NetBox API | REST v4, token auth `Authorization: Token …` |
| DB | PostgreSQL 16, migration 0010 |
| Dev NetBox | `netboxcommunity/netbox:v4.6-5.0.1` (same family as user's `ietf004-nb-ref`) |
| Dev ports | UI **18888**, PG **55432** |
| Docker safety | Separate compose project; never touch foreign containers |

## Constitution Check

| Principle | F7 adherence |
|---|---|
| I — Governance Before Execution | Sync is ingest only; no execution side effects |
| II — Desired vs Actual | NetBox = identity actuals; GARD lifecycle derived state unchanged |
| III — Unknown Is First-Class | Unmatched/orphan devices reported, not coerced |
| IV — Lifecycle-as-Code | NetBox is not catalog source; firmware YAML unchanged |
| V — Evidence/Audit | Every sync run audited + evidenced |
| VI — Curated MCP | Optional summary delegate; no raw NetBox proxy |
| VII — Integration Over Replacement | NetBox owns identity; GARD reads, never replaces |

## Project Structure

**New**

- `adr/ADR-0017-netbox-integration-boundary.md`
- `adr/ADR-0018-netbox-diode-assurance-ecosystem.md`
- `deploy/netbox/docker-compose.yml`
- `deploy/netbox/README.md`
- `deploy/netbox/.env.example`
- `gard/integrations/netbox/client.py`
- `gard/core/netbox_sync_controller.py`
- `gard/api/routers/netbox_integration.py`
- `gard/api/schemas/netbox_integration.py`
- `gard/db/migrations/versions/0010_netbox_integration.py`
- `tests/integration/test_netbox_sync.py`
- `tests/contract/test_netbox_rest_openapi.py`

**Extended**

- `gard/core/settings.py` — NetBox settings
- `gard/core/prereq_predicates.py` — `eval_tagged_with` reads `Device.tags`
- `gard/models/device.py` — netbox columns + tags
- `deploy/README.md` — pointer to netbox stack

## PR slices

| Slice | Scope |
|---|---|
| **7a** | ADRs, spec/plan, isolated NetBox compose + README (no GARD code) |
| **7b** | Migration, client, controller, REST sync |
| **7c** | `tagged_with` evaluable + integration tests |
| **7d** | MCP summary delegate + docs |

## Docker safety checklist (mandatory)

- [ ] Compose file uses `name: gard-f7-netbox`
- [ ] No host ports 5432, 8080, 18080
- [ ] README forbids `docker compose down -v` without `-p gard-f7-netbox`
- [ ] No `container_name` collisions with `ietf004-nb-ref-*`
- [ ] Volumes prefixed by compose project (default behaviour)
