# F10 — Data Model

F10 extends existing GARD models minimally and adds catalog artefacts. No new Postgres tables required for MVP; optional columns on `netbox_sync_runs` and `devices` store write-back metadata.

## Write-Back Manifest (catalog artefact)

**Location**: `gard-catalog/netbox/write-back-manifest.yaml`

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `schema_version` | string | yes | `"1"` |
| `object_type` | string | yes | NetBox object type (default `dcim.device`) |
| `unknown_sentinel` | string | yes | Value when GARD evaluation absent (e.g. `unknown`) |
| `custom_fields` | array | yes | Field mappings |
| `tags` | array | yes | Tag rules |

### Custom field mapping

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `id` | string | yes | Stable GARD key |
| `gard_source` | string | yes | Enum: lifecycle attribute path (see plan) |
| `netbox_field` | string | yes | NetBox custom field name |
| `netbox_type` | string | yes | `text`, `longtext`, `integer`, `date`, `datetime` |
| `description` | string | no | Operator hint |

### Tag rule

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `slug` | string | yes | NetBox tag slug |
| `apply_when` | string | yes | Rule id referencing GARD posture predicate |
| `description` | string | no | |

**Validation rules**:
- Unique `id` per custom field mapping
- Unique `slug` per tag rule
- Every `gard_source` must be in allowed source catalogue
- `netbox_field` names must match `[a-z0-9_]+`

## Write-Back Report (ephemeral)

Returned in sync API response; optionally summarized on `NetboxSyncRun`.

| Field | Type | Notes |
|-------|------|-------|
| `phase` | enum | `completed`, `partial`, `failed`, `skipped` |
| `summary` | object | `{updated, skipped, unchanged, conflict, failed, skipped_not_linked}` |
| `entries` | array | Per-device results (may truncate in API; full detail in audit) |

### Entry result

| Field | Type | Notes |
|-------|------|-------|
| `device_id` | uuid | GARD device PK |
| `netbox_device_id` | int | NetBox DCIM device PK |
| `status` | enum | `updated`, `skipped`, `unchanged`, `conflict`, `failed` |
| `message` | string | Human-readable detail |
| `conflicts` | array | `{field, expected, actual}` for custom fields only |

## GARD Postgres extensions (MVP)

### `devices` (optional column)

| Column | Type | Notes |
|--------|------|-------|
| `netbox_last_writeback_at` | timestamptz | nullable; set on successful device write-back |

### `netbox_sync_runs` (optional columns)

| Column | Type | Notes |
|--------|------|-------|
| `writeback_updated_count` | int | default 0 |
| `writeback_conflict_count` | int | default 0 |
| `writeback_failed_count` | int | default 0 |
| `writeback_phase` | string | nullable enum string |

Migration: `0011_netbox_writeback_counts.py` (during implement).

## GARD source attributes (read-only inputs)

Write-back reads these from existing GARD state (not NetBox):

| `gard_source` key | Origin |
|-------------------|--------|
| `lifecycle_state` | `Device.lifecycle_state` |
| `compliance_summary` | Latest `ComplianceEvaluation` summary for device |
| `readiness_summary` | Latest `ReadinessEvaluation` summary for device |
| `target_firmware` | Resolved target from F2 catalog for device |
| `compliance_evaluated_at` | Timestamp of latest compliance eval |
| `readiness_evaluated_at` | Timestamp of latest readiness eval |

Tag rules (`apply_when`) reference derived predicates, e.g. `drift_outside_target`, `readiness_blocked`, `readiness_ready_for_uplift`, `gard_managed`.

## External NetBox objects (mutated)

| NetBox object | F10 action |
|---------------|------------|
| `dcim.Device.custom_fields` | PATCH allowed keys only |
| `dcim.Device.tags` | Reconcile manifest slugs only |
| `extras.CustomField` | Created by dev bootstrap only |
| `extras.Tag` | Created by dev bootstrap only |

**Never mutated**: device name, serial, site, device type, rack, position, status, interfaces.

## Relationships

```text
NetboxSyncRun 1──1 WriteBackReport (ephemeral in response)
Device 1──1 NetBox dcim.Device (via netbox_device_id)
WriteBackManifest N──1 Device (same manifest for all devices)
ComplianceEvaluation / ReadinessEvaluation → WriteBackReport entries (read at sync time)
```
