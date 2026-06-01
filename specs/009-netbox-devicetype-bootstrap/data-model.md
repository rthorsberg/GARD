# F9 — Data Model

F9 does **not** add GARD Postgres tables. Entities are **catalog artefacts** and **ephemeral bootstrap reports**.

## Curated Device Type Manifest

**Location**: `gard-catalog/netbox/device-types-manifest.yaml`

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `schema_version` | string | yes | Manifest format version (e.g. `1`) |
| `upstream_pin` | string | yes | Full git SHA of `devicetype-library` |
| `upstream_repo` | string | yes | Default `netbox-community/devicetype-library` |
| `entries` | array | yes | One row per supported device type |

### Manifest Entry

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `id` | string | yes | Stable GARD key (e.g. `cisco-isr1121-8p`) |
| `vendor_normalized` | string | yes | GARD canonical vendor |
| `model_normalized` | string | no | When normalization produces chassis model |
| `model_raw_aliases` | string[] | yes | CSV/NetBox raw strings covered |
| `library_path` | string | yes | Path relative to submodule root |
| `expected_slug` | string | yes | NetBox device type slug after import |
| `notes` | string | no | Operator hints (e.g. NCS5501 variant choice) |

**Validation rules**:
- `library_path` MUST resolve to an existing file at `upstream_pin`
- No two entries may share the same `(vendor_normalized, expected_slug)`
- No two entries may share the same `id`
- Every `model_raw_aliases` value MUST be unique across entries

## Bootstrap Report (stdout / JSON)

Ephemeral output of one bootstrap run — not persisted in GARD DB.

| Field | Type | Notes |
|-------|------|-------|
| `upstream_pin` | string | Pin applied |
| `netbox_url` | string | Target instance |
| `started_at` | datetime | ISO-8601 |
| `completed_at` | datetime | ISO-8601 |
| `entries` | array | Per-entry results |
| `summary` | object | `{created, updated, skipped, failed, conflict}` counts |

### Entry Result

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | Manifest entry id |
| `status` | enum | `created`, `updated`, `skipped`, `conflict`, `failed` |
| `netbox_device_type_id` | int | nullable |
| `message` | string | Human-readable detail |

## NetBox objects created (external)

| NetBox model | Source |
|--------------|--------|
| `dcim.Manufacturer` | YAML `manufacturer` field |
| `dcim.DeviceType` | YAML model, slug, u_height, is_full_depth, … |
| Component templates | interfaces, power-ports, console-ports, module-bays, … from YAML |

## Relationships to F7

- F7 sync reads `device_type.model` → GARD `model_raw` — unchanged.
- F9 ensures seeded NetBox devices reference imported types so `model_raw` matches community model strings (e.g. `ISR-1121-8P` vs hand-rolled `ISR1121-8P` — manifest documents expected mapping).
