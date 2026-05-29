# Data Model: Firmware Catalog

**Feature**: 002-firmware-catalog
**Date**: 2026-05-29
**Inputs**: spec.md FR-001…FR-045, research.md D1…D8 + R-6

This document is the binding specification of the F2 data model. Field-level shapes are pinned; the migration script (`gard/db/migrations/versions/0002_firmware_catalog.py`) MUST match this document exactly.

---

## 1. New tables

All four catalog tables share a common shape:

| Column | Type | Notes |
|---|---|---|
| `id` | `UUID PRIMARY KEY` | UUID v7 (time-ordered, matches F1 convention) |
| `loaded_from_git_sha` | `TEXT NULL` | Per D2: file's last commit SHA. NULL only when dirty load (dev only). |
| `loaded_at` | `TIMESTAMPTZ NOT NULL` | Wall-clock at upsert time |
| `removed_at` | `TIMESTAMPTZ NULL` | Per D3: soft-delete. API filters `removed_at IS NULL`. |
| `source_file_relpath` | `TEXT NOT NULL` | e.g. `firmware/targets/cisco-iosxr-edge.yaml`. Indexed. |
| `catalog_schema_version` | `TEXT NOT NULL` | semver from the YAML's top-level field. v1 = `"1.0.0"`. |

The rest of the columns are entity-specific.

### 1.1 `firmware_targets`

| Column | Type | Notes |
|---|---|---|
| `name` | `TEXT NOT NULL` | Human handle; YAML stem by convention but free-form. UNIQUE per `(name, removed_at IS NULL)` enforced by partial index. |
| `platform_family` | `TEXT NOT NULL` | e.g. `iosxr`, `junos`, `sros`. Indexed. |
| `target_version` | `TEXT NOT NULL` | Vendor's version string verbatim (e.g. `7.5.2`). Not normalized in v1. |
| `scope_selector` | `JSONB NOT NULL` | Selector grammar per research.md R-8. JSON Schema validated on load. |
| `valid_from` | `TIMESTAMPTZ NULL` | Optional policy window start. |
| `valid_until` | `TIMESTAMPTZ NULL` | Optional policy window end. |
| `notes` | `TEXT NULL` | Free-form operator notes. |

**Specificity** (used to break multi-target matches per FR-009): count of non-null leaves in `scope_selector` (each set-membership entry counts once regardless of list length).

**Indexes**: `(platform_family, removed_at)`, `((scope_selector->>'vendor_normalized'), removed_at)`, plus the partial UNIQUE on `name`.

### 1.2 `firmware_packages`

| Column | Type | Notes |
|---|---|---|
| `vendor` | `TEXT NOT NULL` | Normalized vendor handle (`cisco`, `juniper`, `nokia`). Indexed. |
| `platform_family` | `TEXT NOT NULL` | As above. |
| `version` | `TEXT NOT NULL` | Vendor version string. |
| `sha256` | `TEXT NOT NULL CHECK (length(sha256)=64)` | Hex-encoded SHA-256 of the artefact. UNIQUE per `(vendor, platform_family, version, sha256)` so the same artefact cannot be re-declared under two different package rows. |
| `byte_size` | `BIGINT NOT NULL CHECK (byte_size > 0)` | Declared size in bytes. Verified on upload. |
| `signed_by` | `TEXT NOT NULL` | The signing identity declared in the YAML (e.g. `cisco`, `juniper`). Not cryptographically validated in v1 — operator assertion. |
| `release_date` | `DATE NULL` | Optional. |
| `download_url` | `TEXT NULL` | Optional. The vendor's canonical URL; we do not fetch it. |
| `notes` | `TEXT NULL` | Free-form. |
| `blob_present` | `BOOLEAN NOT NULL DEFAULT FALSE` | Set to TRUE on first successful upload; never set back to FALSE except by an explicit `delete-blob` admin path (out of scope F2). |
| `blob_stored_at` | `TIMESTAMPTZ NULL` | Wall-clock of the upload that flipped `blob_present`. |

**Indexes**: `(vendor, platform_family, version, removed_at)`, plus a partial UNIQUE on `(vendor, platform_family, version)` where `removed_at IS NULL` so live rows can't collide.

### 1.3 `firmware_upgrade_paths`

| Column | Type | Notes |
|---|---|---|
| `platform_family` | `TEXT NOT NULL` | The graph each edge belongs to. Indexed. |
| `from_version` | `TEXT NOT NULL` | Source vertex. |
| `to_version` | `TEXT NOT NULL` | Sink vertex. |
| `weight` | `INTEGER NOT NULL DEFAULT 1 CHECK (weight >= 1)` | Used by Dijkstra. Operators can mark "stability cost". |
| `notes` | `TEXT NULL` | Optional rationale (e.g. "skip-version not supported by vendor"). |

**Indexes**: `(platform_family, removed_at, from_version, to_version)`. Per R-8 + R-9 we MUST handle cycles defensively at traversal time, not at load time — cycles in the catalog are logged but not rejected.

**No edges-table FK to packages** in v1: an `UpgradePath` is a policy edge, not an artefact bind. Whether the artefact for `to_version` exists is a separate question.

### 1.4 `firmware_prerequisite_rules`

| Column | Type | Notes |
|---|---|---|
| `name` | `TEXT NOT NULL` | Partial UNIQUE on `(name, removed_at IS NULL)`. |
| `applies_to` | `JSONB NOT NULL` | Same scope-selector grammar as `firmware_targets.scope_selector`. |
| `predicate_kind` | `TEXT NOT NULL` | Enum: one of the nine listed in spec FR-021. |
| `predicate_args` | `JSONB NOT NULL` | The right-hand side of the predicate. Shape depends on kind; JSON-Schema validated. |
| `severity` | `TEXT NOT NULL CHECK (severity IN ('required','recommended'))` | F4 will use this for ordering blocker reasons. |
| `evaluable` | `BOOLEAN NOT NULL` | Set to FALSE on load when `predicate_kind = 'tagged_with'`; TRUE otherwise. F4's evaluator MUST short-circuit on FALSE and emit a `predicate_deferred` reason. |

**Indexes**: `(predicate_kind, removed_at)`, `((applies_to->>'platform_family'), removed_at)`.

---

## 2. `BlobStore` protocol and persistence

The protocol lives in `gard/core/blob_store/__init__.py`. v1 ships `LocalFsBlobStore` only.

```python
class BlobStore(Protocol):
    def put(self, key: str, stream: BinaryIO, expected_sha256: str) -> WriteReceipt: ...
    def get(self, key: str) -> StreamWithVerify: ...
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...
    def iter_keys(self) -> Iterator[str]: ...
```

- `key` is the content address: `sha256/<first-2-hex>/<remaining-62-hex>`. So a blob with SHA-256 `d4...e1` lives at `<GARD_BLOB_ROOT>/sha256/d4/<remaining-62>.bin`.
- `put` is the only mutator. It computes SHA chunked during write to a temp file (`.tmp.<uuid7>` in the same directory), compares the computed SHA against `expected_sha256`, and only `os.rename`s into place on match (atomic on POSIX). Mismatch deletes the temp file and raises `BlobChecksumMismatch`.
- `get` returns an object that wraps an `io.BufferedReader` plus a side-channel `hashlib.sha256()`. The caller MUST call `.verify_at_eof()` after the stream is exhausted; the FastAPI handler does this and returns HTTP 500 / `code=blob_checksum_mismatch_on_read` on mismatch.
- `exists` checks the final (non-`.tmp.`) path.
- `iter_keys` walks `<GARD_BLOB_ROOT>/sha256/` — used by `make seed` and integrity-audit tooling.

Concurrent uploads to the same key serialise via an exclusive `flock()` on a sibling `.lock` file. Loser: `flock(LOCK_EX | LOCK_NB)` returns `BlockingIOError` → router returns HTTP 409 `code=blob_upload_in_progress`.

**Configuration**:

```python
class Settings:
    blob_root: Path = Path("/var/lib/gard/blobs")            # GARD_BLOB_ROOT
    firmware_blob_max_bytes: int = 5 * 1024 ** 3              # GARD_FIRMWARE_BLOB_MAX_BYTES
```

---

## 3. `Device` model extensions

### 3.1 New columns on `devices`

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `ram_mb` | `INTEGER` | YES | Constitution III: never coerced to a default. |
| `disk_mb` | `INTEGER` | YES | Same. |
| `licenses` | `TEXT[]` | YES | Semicolon-separated in CSV per D7; postgres array natively in the model. |

### 3.2 `lifecycle_state` enum extension

The Postgres enum `lifecycle_state_kind` already carries the F1 values. F2 adds three:

```sql
ALTER TYPE lifecycle_state_kind ADD VALUE 'target_defined';
ALTER TYPE lifecycle_state_kind ADD VALUE 'compliant';
ALTER TYPE lifecycle_state_kind ADD VALUE 'outside_target';
```

The migration MUST run these `ADD VALUE` statements *before* any code references them, and MUST be wrapped in a transaction that is also safe to re-run (Alembic's idempotency story).

### 3.3 State transition matrix

| From | Event | To | Writer |
|---|---|---|---|
| `classified` | F2 catalog loaded, scope_selector now matches device | `target_defined` | `compliance_controller` |
| `target_defined` | `observed_firmware == target_version` | `compliant` | `compliance_controller` |
| `target_defined` | `observed_firmware != target_version` AND `observed_firmware IS NOT NULL` | `outside_target` | `compliance_controller` |
| `target_defined` | `observed_firmware IS NULL` | `target_defined` (no transition; envelope says `unknown`) | n/a — sticky |
| `compliant` | `observed_firmware` changes | recompute via `target_defined` | `compliance_controller` |
| `outside_target` | `observed_firmware` changes | recompute via `target_defined` | `compliance_controller` |
| any of `{target_defined, compliant, outside_target}` | catalog reload removes the matching target, no other target matches | `classified` | `compliance_controller` |
| any of `{target_defined, compliant, outside_target}` | catalog reload, a *different* target now matches | re-resolve, transition through `target_defined` | `compliance_controller` |

Every transition emits one `AuditEvent` with `action=firmware_target.compliance_evaluated` carrying `before.state`, `after.state`, `target_ref`, and the `correlation_id` of the triggering request or reload.

---

## 4. Audit event taxonomy (additive)

New `AuditEvent.action` values landing in F2:

| Action | When emitted | `after` payload |
|---|---|---|
| `firmware_catalog.target.loaded` | A `firmware_targets` row is inserted or its `removed_at` is set back to NULL | `{git_commit_sha, source_file_relpath, name, platform_family, target_version}` |
| `firmware_catalog.target.removed` | A `firmware_targets` row gets `removed_at` set | `{git_commit_sha_of_removing_commit, source_file_relpath, name}` |
| `firmware_catalog.package.loaded` | A `firmware_packages` row is inserted/resurrected | `{git_commit_sha, source_file_relpath, vendor, platform_family, version, sha256, byte_size}` |
| `firmware_catalog.package.removed` | A package row gets `removed_at` set | `{git_commit_sha, source_file_relpath, vendor, platform_family, version}` |
| `firmware_catalog.package.blob_stored` | A successful blob upload | `{package_id, computed_sha256, bytes_written}` |
| `firmware_catalog.package.blob_read_failed` | A `GET .../blob` recompute does not match the stored SHA | `{package_id, expected_sha256, observed_sha256_at_eof}` |
| `firmware_catalog.upgrade_path.loaded` | An edge row is inserted/resurrected | `{git_commit_sha, source_file_relpath, platform_family, from_version, to_version, weight}` |
| `firmware_catalog.upgrade_path.removed` | An edge row gets `removed_at` set | `{git_commit_sha, source_file_relpath, platform_family, from_version, to_version}` |
| `firmware_catalog.prerequisite.loaded` | A prerequisite rule row is inserted/resurrected | `{git_commit_sha, source_file_relpath, name, predicate_kind, evaluable}` |
| `firmware_catalog.prerequisite.removed` | A prerequisite rule row gets `removed_at` set | `{git_commit_sha, source_file_relpath, name}` |
| `firmware_catalog.reload_failed` | Loader exits non-zero on validation, FS conflict, or duplicate identity | `{failing_file_relpath, reason, schema_path}` |
| `firmware_target.compliance_evaluated` | Per row above | `{before_state, after_state, target_ref, observed_version, target_version}` |
| `mcp.disallowed_tool_attempt` | Already established in F1; F2 reuses for the new tool surface | `{tool_name, client_identity}` |

All emits go through the F1 `core.audit.emit(...)` helper. No schema change to `audit_events`.

---

## 5. Lifecycle evidence (additive)

New `LifecycleEvidence.evidence_type` values:

| evidence_type | Subject | When emitted | `source_checksum` |
|---|---|---|---|
| `firmware_package_upload` | `FirmwarePackage` | Successful blob upload | The computed SHA-256 of the blob bytes |
| `firmware_catalog_load` | `CatalogReload` (synthetic subject; subject_id = the reload's correlation_id) | Each successful loader pass (one row per pass, not per file) | SHA-256 of the *list* of loaded SHAs (Merkle-style for chain-of-custody) |

The `firmware_catalog_load` evidence is a single row per loader pass so an auditor can prove "this exact catalog state was active at time T" without walking every per-file audit row. Per-file granularity stays in audit_events.

---

## 6. JSON Schema files in `contracts/`

Each entity has its own JSON Schema 2020-12 file. Shapes summarised here; full schemas are in `contracts/`.

### 6.1 `firmware-target.schema.yaml` (top level)

```yaml
type: object
required: [catalog_schema_version, name, platform_family, target_version, scope_selector]
properties:
  catalog_schema_version: {type: string, pattern: "^1\\.0\\.0$"}
  name: {type: string, minLength: 1, maxLength: 200}
  platform_family: {type: string, minLength: 1}
  target_version: {type: string, minLength: 1}
  scope_selector: {$ref: "scope-selector.schema.yaml"}
  valid_from: {type: string, format: date-time, nullable: true}
  valid_until: {type: string, format: date-time, nullable: true}
  notes: {type: string, nullable: true}
additionalProperties: false
```

### 6.2 `firmware-package.schema.yaml`

```yaml
type: object
required: [catalog_schema_version, vendor, platform_family, version, sha256, byte_size, signed_by]
properties:
  catalog_schema_version: {type: string, pattern: "^1\\.0\\.0$"}
  vendor: {type: string, enum: [cisco, juniper, nokia]}   # extensible later
  platform_family: {type: string}
  version: {type: string}
  sha256: {type: string, pattern: "^[0-9a-f]{64}$"}
  byte_size: {type: integer, minimum: 1, maximum: 5368709120}
  signed_by: {type: string}
  release_date: {type: string, format: date, nullable: true}
  download_url: {type: string, format: uri, nullable: true}
  notes: {type: string, nullable: true}
additionalProperties: false
```

### 6.3 `firmware-upgrade-path.schema.yaml`

A single YAML file may declare multiple edges for one `platform_family`:

```yaml
type: object
required: [catalog_schema_version, platform_family, edges]
properties:
  catalog_schema_version: {type: string, pattern: "^1\\.0\\.0$"}
  platform_family: {type: string}
  edges:
    type: array
    minItems: 1
    items:
      type: object
      required: [from_version, to_version]
      properties:
        from_version: {type: string}
        to_version: {type: string}
        weight: {type: integer, minimum: 1, default: 1}
        notes: {type: string, nullable: true}
      additionalProperties: false
additionalProperties: false
```

### 6.4 `firmware-prerequisite.schema.yaml`

```yaml
type: object
required: [catalog_schema_version, name, applies_to, predicate]
properties:
  catalog_schema_version: {type: string, pattern: "^1\\.0\\.0$"}
  name: {type: string, minLength: 1}
  applies_to: {$ref: "scope-selector.schema.yaml"}
  predicate:
    oneOf:
      - {type: object, required: [kind, min_mb], properties: {kind: {const: min_ram_mb}, min_mb: {type: integer, minimum: 1}}, additionalProperties: false}
      - {type: object, required: [kind, min_mb], properties: {kind: {const: min_disk_mb}, min_mb: {type: integer, minimum: 1}}, additionalProperties: false}
      - {type: object, required: [kind, min_version], properties: {kind: {const: min_current_version}, min_version: {type: string}}, additionalProperties: false}
      - {type: object, required: [kind, revisions], properties: {kind: {const: hardware_revision_in}, revisions: {type: array, items: {type: string}, minItems: 1}}, additionalProperties: false}
      - {type: object, required: [kind, license], properties: {kind: {const: license_present}, license: {type: string}}, additionalProperties: false}
      - {type: object, required: [kind, version], properties: {kind: {const: intermediate_version_required}, version: {type: string}}, additionalProperties: false}
      - {type: object, required: [kind, states], properties: {kind: {const: not_in_state}, states: {type: array, items: {type: string, enum: [imported, classified, target_defined, compliant, outside_target, manual_review_required]}}}, additionalProperties: false}
      - {type: object, required: [kind, regions], properties: {kind: {const: region_in}, regions: {type: array, items: {type: string}}}, additionalProperties: false}
      - {type: object, required: [kind, tags], properties: {kind: {const: tagged_with}, tags: {type: array, items: {type: string}}}, additionalProperties: false}
  severity: {type: string, enum: [required, recommended], default: required}
additionalProperties: false
```

### 6.5 `scope-selector.schema.yaml` (shared)

```yaml
type: object
minProperties: 1
properties:
  vendor_normalized: {type: string}
  platform_family: {type: string}
  region_in: {type: array, items: {type: string}, minItems: 1}
  site_in: {type: array, items: {type: string}, minItems: 1}
  role_in: {type: array, items: {type: string}, minItems: 1}
  hardware_revision_in: {type: array, items: {type: string}, minItems: 1}
  not_in_state: {type: array, items: {type: string, enum: [imported, classified, target_defined, compliant, outside_target, manual_review_required]}, minItems: 1}
  tagged_with: {type: array, items: {type: string}, minItems: 1}
additionalProperties: false
```

---

## 7. Migration order

`gard/db/migrations/versions/0002_firmware_catalog.py` MUST apply in this order to satisfy enum-extension semantics:

1. `ALTER TYPE lifecycle_state_kind ADD VALUE 'target_defined'` (in autocommit block).
2. `ALTER TYPE lifecycle_state_kind ADD VALUE 'compliant'`.
3. `ALTER TYPE lifecycle_state_kind ADD VALUE 'outside_target'`.
4. `ALTER TABLE devices ADD COLUMN ram_mb INTEGER`, `disk_mb INTEGER`, `licenses TEXT[]`.
5. `CREATE TABLE firmware_targets …` (+ indexes).
6. `CREATE TABLE firmware_packages …` (+ indexes).
7. `CREATE TABLE firmware_upgrade_paths …` (+ indexes).
8. `CREATE TABLE firmware_prerequisite_rules …` (+ indexes).
9. Grant the new tables to `gard_writer_append_only` for INSERT only on resurrection paths (the controller transitions soft-deleted rows back to active by setting `removed_at = NULL` — that is an UPDATE, so the append-only role is *not* the writer of catalog tables; the regular `gard_writer` role is).

Downgrade is non-trivial because Postgres cannot remove enum values without a table-rebuild dance; v1 downgrade for 0002 explicitly errors out with a message pointing to the operational runbook. We accept this — F2's data isn't recoverable from F1 anyway.

---

## 8. Read paths and indexes summary

| Query | Endpoint | Index used |
|---|---|---|
| List active targets | `GET /api/v1/firmware/targets` | `(removed_at, platform_family)` |
| Resolve target for device | `compliance_controller.evaluate` | `(removed_at, platform_family)` then in-memory selector scan |
| List packages by platform | `GET /api/v1/firmware/packages?platform_family=X` | `(vendor, platform_family, version, removed_at)` |
| Find shortest path A→B | `GET /api/v1/firmware/upgrade-paths` | `(platform_family, removed_at)` → in-memory `networkx` graph cached per platform |
| List prerequisites by predicate kind | `GET /api/v1/firmware/prerequisites?kind=X` | `(predicate_kind, removed_at)` |
| Read device compliance | `GET /api/v1/devices/{id}/firmware-compliance` | Device PK + the resolved target row PK |

---

## 9. What's deliberately not in the model

- `FirmwareApproval` / `CatalogReviewer` entities — approval = merged PR, no in-app state.
- `FirmwarePackageBlobLocation` table — content-addressed paths derived from `sha256`, no separate row.
- Computed-shortest-path cache table — graphs are small enough to recompute in-process per reload.
- `DeviceComplianceHistory` table — history lives in `audit_events` (every `firmware_target.compliance_evaluated` row IS the history).
- `FirmwareTargetVersionWindow` — `valid_from`/`valid_until` are columns, not a separate entity.
- Any FK from `devices.lifecycle_state` to a target — the target reference is materialised via a join (or, more honestly, by re-evaluating); not stored as a foreign key.
