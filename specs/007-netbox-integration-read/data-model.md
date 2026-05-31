# F7 — Data Model

## Device extensions (migration 0010)

| Column | Type | Notes |
|--------|------|-------|
| `netbox_device_id` | `INTEGER NULL UNIQUE` | NetBox DCIM device PK |
| `netbox_last_synced_at` | `TIMESTAMPTZ NULL` | Last successful sync touching this row |
| `tags` | `TEXT[] NULL` | Tag slugs copied from NetBox; powers `tagged_with` |

Partial unique index: `netbox_device_id WHERE netbox_device_id IS NOT NULL`.

## netbox_sync_runs

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `status` | enum | `running`, `completed`, `failed` |
| `started_at` | timestamptz | |
| `completed_at` | timestamptz nullable | |
| `correlation_id` | text | |
| `matched_count` | int | |
| `created_count` | int | |
| `updated_count` | int | |
| `orphaned_count` | int | |
| `error_summary` | text nullable | |

Append-only for v1 (no delete API).

## NetBox → GARD field map (v1)

| NetBox field | GARD field |
|--------------|------------|
| `id` | `netbox_device_id` |
| `name` | `hostname` |
| `serial` | `serial_number` |
| `site.slug` or `site.name` | `site` |
| `role.slug` | `role` |
| `device_type.manufacturer.name` | `vendor_raw` (until normalized) |
| `device_type.model` | `model_raw` |
| `tags[].slug` | `tags[]` |
| `status.value` | informational only in v1 |

Observed firmware is **not** sourced from NetBox in v1 (lifecycle observations remain CSV/adapter path).

## Reconciliation outcomes

| Outcome | GARD action |
|---------|-------------|
| Match by serial | Update identity fields + netbox refs |
| Match by hostname+site | Same |
| NetBox-only | Insert `Device`, `source_system=netbox`, `lifecycle_state=imported` |
| GARD-only after sync | Listed in `orphaned_in_gard[]`; no delete |
