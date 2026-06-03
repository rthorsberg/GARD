# F13 — NetBox Platform Lab: Data Model

**Feature**: `013-netbox-platform-lab` | **Date**: 2026-06-02

This feature has **no GARD database entities**. The model below describes lab artefacts, external NetBox/Branching state, and operator workflow gates documented in runbooks and YAML contracts.

## PlatformLabStack

The compose-defined set of services and their dependency graph for the dev/lab environment.

| Field | Type | Description |
|---|---|---|
| `project_name` | string | Docker Compose project (default `gard-f7-netbox`) |
| `compose_files` | string[] | Base + platform overlay paths |
| `services` | ServiceRef[] | Named services with role tags |
| `ports` | PortBinding[] | Host port mappings (UI, Diode gRPC, Postgres) |
| `volumes` | string[] | Named volumes scoped to project |
| `health_script` | string | Path to `platform-lab-health.sh` |

**Relationships**:

- Contains one **NetBox core** group (postgres, redis, netbox, netbox-worker)
- Optionally contains **Diode** group (nginx, diode services from quickstart)
- Contains **OrbAgent** (depends on Diode gRPC + credentials)
- Contains **SimulatorHost** containers (discovery targets)

**Validation rules**:

- `project_name` MUST be explicit in all documented start/stop commands (FR-002)
- Host port defaults MUST NOT collide with GARD (8080, 5432) or common alt NetBox (18080) without documented override env vars

## ServiceRef

| Field | Type | Description |
|---|---|---|
| `name` | string | Compose service name |
| `role` | enum | `netbox`, `diode`, `orb`, `simulator`, `datastore` |
| `health_probe` | string | HTTP/gRPC/shell probe identifier |
| `required` | boolean | If false, stack may start in degraded mode (e.g. Branching) |

## IngestFixtureCatalogue

Version-controlled catalogue driving deterministic ingest smoke tests (not stored in GARD DB).

| Field | Type | Description |
|---|---|---|
| `schema_version` | string | Contract version (`"1"`) |
| `minimum_device_count` | integer | Smoke pass threshold (≥ 3 per SC-002) |
| `devices` | IngestDevice[] | Expected devices after ingest |
| `idempotency_notes` | string | Operator guidance for re-run behavior |

### IngestDevice

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | NetBox device name (unique key for smoke) |
| `site` | string | yes | NetBox site slug |
| `role` | string | yes | Device role slug |
| `device_type` | string | yes | Device type model (must exist via F9 bootstrap) |
| `serial` | string | no | Expected serial if discovery provides it |
| `simulator_ip` | string | yes | Orb discovery target IP on lab bridge |
| `expected_primary_ip` | string | no | CIDR; validated after ingest+merge |

**Validation rules**:

- Device names MUST be unique within catalogue
- `device_type` MUST be bootstrapped before ingest smoke (F9 dependency)
- Smoke script MUST fail if `count(devices found in NetBox) < minimum_device_count`

## BranchChangeSet

A NetBox Branching branch containing staged DCIM/IPAM edits before merge to `main`.

| Field | Type | Description |
|---|---|---|
| `branch_id` | uuid/string | NetBox Branching branch identifier |
| `branch_name` | string | Human-readable name |
| `status` | enum | `provisioning`, `ready`, `merged`, `failed` |
| `base_snapshot_at` | datetime | Branch creation time |
| `changes` | BranchChange[] | Staged object mutations |

### BranchChange

| Field | Type | Description |
|---|---|---|
| `object_type` | string | e.g. `ipam.ipaddress`, `dcim.device` |
| `object_id` | integer | NetBox object PK |
| `field` | string | Changed attribute |
| `before` | string | Value on `main` at branch creation |
| `after` | string | Staged value on branch |

**State transitions**:

```text
(create) → provisioning → ready → (merge job) → merged
                              ↘ failed
```

**Validation rules**:

- Merge MUST reach `completed` job status before **MergeCheckpoint** passes
- Changes MUST NOT be assumed visible to GARD until merged to `main`

## MergeCheckpoint

Documented operator gate confirming NetBox `main` reflects intended SoT before GARD sync.

| Field | Type | Description |
|---|---|---|
| `checkpoint_id` | string | Runbook step identifier |
| `main_device_query` | string | REST path used for verification |
| `expected_field` | string | e.g. `primary_ip4.address` |
| `expected_value` | string | Post-merge expected value |
| `gard_sync_allowed` | boolean | MUST be `true` only after verification passes |

**Workflow**:

```text
ingest_complete → (optional branch edits) → merge_to_main → MergeCheckpoint.verify → gard_sync
```

**Validation rules**:

- GARD sync scripts MUST document warning if run before checkpoint (FR-004, anti-pattern)
- Before/after REST snapshots MUST be captured in merge-demo script output (SC-003)

## LabRunbook

Operator-facing procedure collection (markdown + shell entrypoints).

| Field | Type | Description |
|---|---|---|
| `sections` | RunbookSection[] | Ordered procedures |
| `cross_links` | LinkRef[] | F7, F12 quickstarts, ADR-0018, ADR-0024 |

### RunbookSection

| Field | Type | Description |
|---|---|---|
| `id` | string | e.g. `start`, `ingest-smoke`, `branch-merge`, `gard-handoff`, `teardown` |
| `script` | string | Optional automation path |
| `estimated_minutes` | integer | Onboarding budget (SC-001) |

## DriftScenario

Planted mismatch documentation linking NetBox state to F12 finding kinds.

| Field | Type | Description |
|---|---|---|
| `scenario_id` | string | Filename slug |
| `netbox_steps` | string[] | Ordered operator actions |
| `gard_precondition` | string | Required GARD estate state |
| `expected_finding_kind` | string | F12 contract kind |
| `verification_endpoint` | string | GARD REST path |

**Validation rules**:

- At least **2** scenarios required (SC-004)
- Each MUST list pass/fail criteria before GARD invocation (User Story 4)

## Entity relationship (conceptual)

```text
PlatformLabStack
  ├── OrbAgent ──gRPC──► DiodeServer ──plugin──► NetBox(main)
  │       │
  │       └── discovers ──► SimulatorHost(s)
  │
  └── IngestFixtureCatalogue ──validates──► NetBox devices on main

BranchChangeSet ──merge──► MergeCheckpoint ──gates──► LabRunbook.gard-handoff ──► GARD sync (external)

DriftScenario ──references──► MergeCheckpoint + F12 findings (external)
```
