# ADR-0017 — NetBox Integration Boundary (Read-Only v1)

**Status**: Accepted
**Date**: 2026-05-31
**Decision-makers**: GARD core team
**Touches**: F7 (NetBox Integration — read-only), F2 (`tagged_with`), F1 (Device identity)
**Supersedes**: none (operationalises ADR-0001 for v1)
**Superseded by**: none (write-back deferred to post-v1 ADR)

## Context

ADR-0001 establishes the product boundary:

> NetBox owns what exists and where it belongs. GARD owns firmware lifecycle intent, drift, readiness, planning, and evidence.

F1–F6 prove the lifecycle pipeline on CSV-fed devices. Real deployments already maintain identity in NetBox. F7 must close the integration gap without blurring ownership or introducing silent data loss.

Three questions need binding answers before implementation:

1. **Direction of data flow** — does GARD ever mutate NetBox in v1?
2. **Reconciliation semantics** — how does GARD match NetBox devices to existing `Device` rows, and what happens to orphans?
3. **Identity keys** — which fields are authoritative when CSV and NetBox disagree?

This ADR locks the answers. Decisions reference R-3 and R-4 from `specs/007-netbox-integration-read/research.md`.

## Decision

### A. Read-only integration (R-3)

F7 v1 is **pull-only**:

- GARD calls NetBox REST (`GET /api/dcim/devices/`, paginated) with a read-only API token.
- GARD MUST NOT issue `POST`, `PATCH`, `PUT`, or `DELETE` to NetBox in v1.
- The NetBox HTTP client (`gard/integrations/netbox/client.py`) MUST reject or omit write methods at the module boundary.

Write-back (custom fields, tags, status) is explicitly deferred to post-v1.

### B. Reconciliation identity keys (R-4)

Match order — same as F1 CSV import:

1. `serial_number` (case-insensitive) when present on both sides
2. `(hostname, site)` pair
3. Otherwise: create a new GARD `Device` from NetBox data, OR flag `manual_review` when ambiguous

On match, GARD stores `netbox_device_id` (NetBox DCIM device PK) and `netbox_last_synced_at`.

### C. Orphans and duplicates

| Situation | GARD action |
|---|---|
| GARD device with no NetBox match after sync | Listed in sync report `orphaned_in_gard[]`; row **not deleted** |
| NetBox device with no GARD match | Insert new `Device` with `source_system=netbox`, `lifecycle_state=imported` |
| Duplicate serial in NetBox | Sync fails batch with 409 `NETBOX_AMBIGUOUS_IDENTITY`; no silent merge |
| Hostname+site collision without serial | Same ambiguity rules as F1 CSV; `manual_review` when unresolved |

Constitution III applies: unknown and ambiguous states are first-class, never coerced away.

### D. Field ownership

| Domain | Owner | F7 behaviour |
|---|---|---|
| Infrastructure identity (hostname, serial, site, role, device type, tags) | NetBox | Copied into GARD on sync |
| Observed firmware / lifecycle state | GARD (CSV, adapters, evaluation) | **Not** sourced from NetBox in v1 |
| Target firmware, drift, readiness, uplift | GARD | Unchanged by sync |
| Catalog YAML | GARD | NetBox is not a catalog source |

### E. Sync durability

Each sync run:

1. Opens a single DB transaction for all device mutations.
2. On NetBox unreachable or unrecoverable parse error → rollback; HTTP 502 `NETBOX_UNREACHABLE`.
3. Emits audit events: `netbox.sync.started`, `netbox.sync.completed` or `netbox.sync.failed`.
4. Persists a `netbox_sync_runs` row with counts and `correlation_id`.

### F. Tag source for F2 `tagged_with` (R-5)

NetBox tag slugs are copied into `Device.tags` (`TEXT[]`). F4 `eval_tagged_with` reads `Device.tags` instead of returning `predicate_deferred` for NetBox-synced devices.

## Rationale

**Why read-only first**: NetBox is already the org's identity SoT. GARD becoming a write client before the reconciliation story is proven would create dual-writer conflicts and audit ambiguity. Pull-only lets operators validate match quality before any write-back design.

**Why same identity keys as F1**: One reconciliation story across CSV import and NetBox sync. Operators who CSV-seeded in F6 and then sync from NetBox get stable matches on serial without duplicate rows.

**Why never delete orphans**: A device absent from NetBox may be decommissioned in NetBox but still under GARD lifecycle review. Deleting would destroy audit history and readiness state. Reporting orphans is the correct v1 shape.

**Why tags on Device row**: Matches the existing `licenses TEXT[]` pattern; avoids a join table for v1 scope.

## Alternatives considered

1. **NetBox as write client from day one**. Rejected — dual-writer risk, out of F7 scope.
2. **NetBox plugin only (no standalone sync)**. Rejected — ADR-0001 chose standalone platform with integration.
3. **Delete GARD rows missing from NetBox**. Rejected — violates Constitution III and destroys lifecycle evidence.
4. **Separate `device_netbox_tags` join table**. Rejected for v1 — array column is sufficient at MVP scale.
5. **GraphQL or Diode gRPC ingest**. Rejected — standard REST is sufficient and matches operator tooling.

## Consequences

- Operators MUST provision a read-only NetBox API token (`dcim.view_device`, tag view).
- GARD settings add `GARD_NETBOX_URL`, `GARD_NETBOX_TOKEN`, `GARD_NETBOX_VERIFY_TLS`, `GARD_NETBOX_SYNC_MAX_DEVICES`.
- Migration 0010 adds `netbox_device_id`, `netbox_last_synced_at`, `tags` to `devices` and creates `netbox_sync_runs`.
- F2 catalog authors can rely on `tagged_with` after at least one successful sync.
- Post-v1 write-back requires a new ADR defining conflict resolution and audit semantics.
