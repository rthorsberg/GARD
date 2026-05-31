# Feature Specification: NetBox Integration (Read-Only)

**Feature Branch**: `007-netbox-integration-read`
**Created**: 2026-05-31
**Status**: Draft
**Input**: User description: "F7 — NetBox Integration (read-only): GARD pulls device identity/inventory from NetBox via REST API and reconciles with Device records. Ecosystem-aware (NetBox Discovery → Diode → NetBox as SoT; complementary to NetBox Assurance). v1 is read-only — no write-back. Dev NetBox runs in an isolated Docker project on high host ports without touching existing NetBox containers."

## Why this feature exists

F1–F6 prove GARD's lifecycle pipeline on CSV-fed devices. Real CSP estates already maintain infrastructure identity in **NetBox** (ADR-0001). F7 closes the gap between "CSV demo" and "operates against the same source-of-truth as the rest of the org":

> *NetBox owns what exists and where it belongs. GARD owns firmware lifecycle intent, drift, readiness, planning, and evidence.*

Without F7, operators duplicate identity work (export CSV from NetBox, re-import into GARD) and F2's `tagged_with` prerequisite predicate stays permanently deferred.

F7 v1 is **read-only**: GARD pulls from NetBox; it never mutates NetBox records, custom fields, or tags.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Trigger a NetBox sync and reconcile devices (Priority: P1)

A platform engineer configures `GARD_NETBOX_URL` and a read-only API token. She calls `POST /api/v1/integrations/netbox/sync` (or runs the CLI). GARD pages through NetBox `/api/dcim/devices/`, maps each device to GARD's identity keys (serial preferred, hostname+site fallback), upserts `Device` rows, stores a stable `netbox_device_id` reference, and emits audit + evidence rows. Devices present in GARD but absent from NetBox are flagged `orphaned_in_gard`, not deleted.

**Why this priority**: The sync/reconcile loop is the core value — without it F7 is documentation only.

**Independent Test**: With dev NetBox seeded with 3 devices matching the ISR1121 fixture identities, sync returns `created=0 updated=3 matched=3`; GARD `Device.netbox_device_id` populated; audit contains `netbox.sync.completed`.

**Acceptance Scenarios**:

1. **Given** NetBox has device `r-osl-001` with serial `FOC123456`, **When** sync runs, **Then** GARD matches the existing CSV-imported device and sets `netbox_device_id` without creating a duplicate.
2. **Given** NetBox adds a new device not in GARD, **When** sync runs, **Then** GARD creates a new `Device` in `imported` state with identity fields copied from NetBox and `source_system=netbox`.
3. **Given** a GARD device has no NetBox match, **When** sync completes, **Then** the sync report lists it under `orphaned_in_gard[]` with reason; the device row is not deleted.
4. **Given** NetBox is unreachable, **When** sync is triggered, **Then** the response is 502 `NETBOX_UNREACHABLE` and no partial device mutations are committed (transaction rollback).

---

### User Story 2 - Enrich GARD scope selectors with NetBox tags (Priority: P2)

After sync, F2 `tagged_with` prerequisite rules become evaluable: tags copied from NetBox device records populate GARD's tag source (via `Device.tags` or a join table). A readiness re-evaluation shows a previously deferred `tagged_with` rule now firing or passing based on live tag data.

**Why this priority**: Unblocks policy authors who already wrote `tagged_with` rules in F2 catalog YAML.

**Independent Test**: NetBox device tagged `edge`; catalog rule `tagged_with: [edge]` evaluates to pass (not `predicate_deferred`) after sync + readiness eval.

**Acceptance Scenarios**:

1. **Given** NetBox device carries tag `edge`, **When** sync runs and readiness evaluates, **Then** `tagged_with` predicates see the tag and do not emit `predicate_deferred`.
2. **Given** NetBox removes a tag, **When** the next sync runs, **Then** GARD's stored tags reflect the removal and readiness may re-block on the next evaluation.

---

### User Story 3 - Operator dev stack with isolated NetBox (Priority: P1)

A developer starts GARD's optional NetBox dev stack using `deploy/netbox/docker-compose.yml` with project name `gard-f7-netbox`, host port **18888** (UI) and **55432** (Postgres). Existing NetBox stacks (e.g. `ietf004-nb-ref` on port 18080) and the GARD stack (`deploy-api-1` on 8080, postgres on 5432) remain untouched — no `docker rm`, `docker compose down -v` on foreign projects, or port collisions.

**Why this priority**: User constraint from kickoff — must not destroy prior NetBox lab work.

**Independent Test**: `docker compose -p gard-f7-netbox -f deploy/netbox/docker-compose.yml up -d` starts; UI at `http://127.0.0.1:18888/`; `docker ps` still shows pre-existing containers unchanged.

**Acceptance Scenarios**:

1. **Given** an existing NetBox on port 18080, **When** GARD dev NetBox starts, **Then** both stacks coexist; neither container is recreated or removed.
2. **Given** the GARD dev NetBox compose file, **When** inspected, **Then** it never publishes host ports 5432, 8080, or 18080.

---

### User Story 4 - MCP / reporting: NetBox-sourced inventory counts (Priority: P3)

An AI agent asks "how many devices does GARD know from NetBox vs CSV-only?" The system exposes a read-only summary (`GET /api/v1/integrations/netbox/summary` or MCP delegate) with counts: `netbox_linked`, `csv_only`, `orphaned_in_gard`, `last_sync_at`.

**Independent Test**: After sync, summary returns non-zero `netbox_linked`; MCP delegate matches REST.

---

### Edge Cases

- **Duplicate serial in NetBox**: Sync fails the batch with 409 `NETBOX_AMBIGUOUS_IDENTITY` listing conflicting NetBox IDs — no silent merge.
- **Hostname/site collision without serial**: Same fallback rules as F1 CSV identity; manual_review when ambiguous.
- **NetBox custom fields**: v1 maps only standard DCIM fields (name, serial, site, role, device_type, status); custom field mapping deferred.
- **Large estates**: Sync paginates (NetBox limit=1000); bounded batch with cursor; configurable max devices per run.
- **Token scope**: Read-only token required; write permission on token is rejected at config validation time with a warning in logs.

## Functional Requirements

- **FR-001**: GARD MUST support configuration of NetBox base URL, API token, TLS verify flag, and sync timeout via settings/env.
- **FR-002**: GARD MUST implement a read-only sync that pulls DCIM devices from NetBox REST API v4 and reconciles to `Device` rows.
- **FR-003**: Each reconciled device MUST store `netbox_device_id` (integer) and `netbox_last_synced_at` (timestamptz).
- **FR-004**: Sync MUST NOT delete GARD devices; orphans are reported only.
- **FR-005**: Sync MUST NOT write to NetBox (no POST/PATCH/DELETE to NetBox API in v1).
- **FR-006**: Sync MUST emit audit events (`netbox.sync.started`, `netbox.sync.completed`, `netbox.sync.failed`) and LifecycleEvidence.
- **FR-007**: F2 `tagged_with` prerequisite evaluation MUST become evaluable for devices synced from NetBox with tags.
- **FR-008**: Dev NetBox MUST ship as an optional isolated compose stack under `deploy/netbox/` using project name `gard-f7-netbox` and host ports **18888** (HTTP UI) and **55432** (Postgres) by default.
- **FR-009**: Documentation MUST explicitly forbid destructive Docker commands against non-GARD NetBox projects.
- **FR-010**: Operators MAY point GARD at an existing NetBox instance (e.g. `http://127.0.0.1:18080`) instead of the dev stack.

## Key Entities

- **NetBoxSyncRun** — one sync attempt: started_at, completed_at, status, counts, correlation_id.
- **Device** (extended) — `netbox_device_id`, `netbox_url` (optional), `tags[]`, `netbox_last_synced_at`.
- **NetBoxSyncReport** — ephemeral response DTO: matched, created, updated, orphaned, errors[].

## Success Criteria

- **SC-001**: Sync of 100 NetBox devices completes in under 60 seconds on dev hardware.
- **SC-002**: Zero duplicate GARD devices after sync when NetBox identities are unique.
- **SC-003**: Dev NetBox stack starts without modifying any pre-existing Docker container (verified by container ID snapshot before/after).
- **SC-004**: `tagged_with` rules evaluate against synced tags for at least one test device.
- **SC-005**: 100% of sync operations emit audit + evidence rows.

## Assumptions

- NetBox v4.x REST API (matching `netboxcommunity/netbox:v4.6` family).
- Read-only API token with `dcim.view_device` (and tag view) permissions.
- Existing NetBox on user's machine may use port 18080 (`ietf004-nb-ref`); GARD dev stack uses 18888 deliberately higher.
- Write-back, Diode gRPC ingest, and NetBox plugin are out of v1 scope.
