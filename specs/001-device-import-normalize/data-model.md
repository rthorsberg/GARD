# Data Model: Device Import & Normalize (F1)

This document derives concrete entities, fields, relationships,
validation rules, and state transitions from `spec.md`. The shape is
the **contract** for the ORM models in `gard/models/`; deviations from
this document during implementation require updating it in the same PR.

The entities below match the GARD domain model in
`gard-speckit-start/specs/01-domain-model.md`, narrowed to the fields
F1 actually persists. Fields owned by F2+ are explicitly omitted with
a forward reference.

---

## Entity: `Device`

Canonical, deduplicated record for one network device. Slowly-changing
identity. The single record every later feature operates on.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID v7 | PK, server-generated | Time-ordered; helps natural sort |
| `serial_number` | text | nullable, unique when non-null (case-insensitive, trimmed) | Primary identity per D9 |
| `hostname` | text | not null | Operator-meaningful |
| `site` | text | not null | Required for the `(hostname, site)` fallback identity |
| `region` | text | nullable | Filter dimension; comes from CSV |
| `role` | text | nullable | e.g. `core`, `edge`, `bng` |
| `management_ip` | inet | nullable | Stored as native inet |
| `vendor_raw` | text | not null | Verbatim from latest observation |
| `vendor_normalized` | text | nullable | Set when classified |
| `model_raw` | text | not null | Verbatim from latest observation |
| `model_normalized` | text | nullable | Set when classified |
| `platform_family` | text | nullable | e.g. `cisco-ios-xe` |
| `hardware_revision` | text | nullable | From latest observation |
| `source_system` | text | not null | e.g. `csv-import:job-<id>` |
| `lifecycle_state` | enum | not null, default `imported` | See state-machine below |
| `created_at` | timestamptz | not null, default now | |
| `updated_at` | timestamptz | not null, default now, auto-touch | |

**Reserved for later features (not in F1 migration)**: `compliance_state`,
`readiness_state`, `risk_score`.

**Indexes**:
- Unique: `(lower(serial_number))` partial where `serial_number IS NOT NULL`
- Unique: `(lower(hostname), lower(site))` partial where `serial_number IS NULL`
- B-tree: `(vendor_normalized, model_normalized)`, `(lifecycle_state)`

**Validation**:
- `serial_number IS NOT NULL OR (hostname IS NOT NULL AND site IS NOT NULL)`
- Every row must have at least one of `vendor_raw`, `model_raw` non-empty.

---

## Entity: `DeviceObservation`

Immutable, append-only record of one observation of one device's actual
state. One CSV row → one observation.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID v7 | PK | |
| `device_id` | UUID | FK → `devices.id`, not null | Set after identity resolution |
| `import_job_id` | UUID | FK → `import_jobs.id`, not null | Provenance |
| `observed_firmware` | text | nullable | From CSV |
| `observed_bootloader` | text | nullable | From CSV |
| `observed_hardware_revision` | text | nullable | From CSV |
| `observed_at` | timestamptz | not null | From CSV if present, otherwise = import time |
| `observed_by` | text | not null | e.g. `csv:<filename>` |
| `confidence` | enum | not null | `exact`, `high`, `medium`, `low`, `manual_review_required` |
| `confidence_source` | text | nullable | rule id or `manual` |
| `raw_payload` | JSONB | not null | The full original CSV row as a JSON object |
| `created_at` | timestamptz | not null, default now | Equals "ingested at" |

**Immutability**: `UPDATE` and `DELETE` are revoked from the application
DB role; corrections happen through manual mappings (which add a new
record-level annotation, never edit the observation).

**Indexes**:
- B-tree: `(device_id, created_at DESC)` — fastest "latest observation"
- B-tree: `(confidence)` — for the manual-review listing
- GIN: `(raw_payload jsonb_path_ops)` — for ad-hoc raw queries

**Validation**: `observed_at <= now() + 5 minutes` (reject far-future
observations as clock-skew protection).

---

## Entity: `NormalizationRule`

A pattern that maps raw vendor/model/platform values to canonical
values. Stored in DB (rules edited via API or seeded from YAML) and
also expressed as YAML in `gard-catalog/normalization/`. The YAML is
the source of truth; DB rows tagged `source=file` mirror it for fast
matching, DB rows tagged `source=db` are hot overrides per D5.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | text | PK | Human-readable, e.g. `cisco-isr-1121` |
| `priority` | int | not null, default 100 | Higher = preferred |
| `match` | JSONB | not null | `{vendor_raw_regex, model_raw_regex, ...}` |
| `output` | JSONB | not null | `{vendor_normalized, model_normalized, platform_family, ...}` |
| `confidence` | enum | not null | `exact`, `high`, `medium` (rules cannot produce `low` or `manual_review_required`) |
| `source` | enum | not null | `file` or `db` |
| `source_path` | text | nullable | YAML file path if `source=file` |
| `enabled` | bool | not null, default true | Disable in lieu of delete |
| `notes` | text | nullable | |
| `exported_at` | timestamptz | nullable | Set when a `db` rule has been written back to YAML |
| `created_at` | timestamptz | not null | |
| `updated_at` | timestamptz | not null | |

**Specificity**: computed at load time = number of constrained match
fields, weighted (exact +2, regex +1).

**Validation**:
- `match` must contain at least one of `vendor_raw_regex`,
  `model_raw_regex`, `vendor_raw`, `model_raw`.
- `output.vendor_normalized` must be non-empty.

---

## Entity: `ManualMapping`

An explicit, audited mapping for one `DeviceObservation`. Highest
precedence in the normalization resolution order. Cannot be deleted —
disabled instead.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID v7 | PK | |
| `observation_id` | UUID | FK → `device_observations.id`, not null, unique | One mapping per observation |
| `vendor_normalized` | text | not null | |
| `model_normalized` | text | not null | |
| `platform_family` | text | nullable | |
| `reason` | text | not null | Operator-supplied explanation |
| `actor` | text | not null | OIDC `sub` or token id |
| `enabled` | bool | not null, default true | |
| `created_at` | timestamptz | not null | |

---

## Entity: `ImportJob`

Record of one CSV ingest attempt.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID v7 | PK | |
| `filename` | text | not null | As uploaded |
| `file_sha256` | text | not null | Lowercase hex |
| `file_size` | bigint | not null | |
| `row_count_total` | int | nullable until completed | |
| `row_count_accepted` | int | nullable until completed | |
| `row_count_rejected` | int | nullable until completed | |
| `row_count_manual_review` | int | nullable until completed | |
| `row_count_duplicate` | int | nullable until completed | |
| `status` | enum | not null | `pending`, `processing`, `completed`, `failed`, `cancelled` |
| `started_at` | timestamptz | nullable | |
| `completed_at` | timestamptz | nullable | |
| `error_report` | JSONB | nullable | Per-row errors, capped at 50,000 entries |
| `summary` | JSONB | nullable | Aggregate report served by the summary endpoint |
| `actor` | text | not null | Who triggered |
| `is_override` | bool | not null, default false | `true` if duplicate-hash override was used |
| `created_at` | timestamptz | not null | |

**Indexes**:
- Unique: `(file_sha256)` partial where `is_override = false` — refuses
  duplicate by default
- B-tree: `(status, created_at)` — worker poll order

---

## Entity: `AuditEvent`

Append-only log. DB role has only `INSERT, SELECT`.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID v7 | PK | |
| `timestamp` | timestamptz | not null, default now | |
| `actor` | text | not null | OIDC `sub`, token id, or `system` |
| `actor_type` | enum | not null | `user`, `system`, `mcp_client`, `adapter` |
| `action` | text | not null | e.g. `import.csv.accepted` |
| `object_type` | text | not null | e.g. `ImportJob` |
| `object_id` | text | not null | UUID or composite key |
| `before` | JSONB | nullable | |
| `after` | JSONB | nullable | |
| `result` | enum | not null | `success`, `failure`, `denied` |
| `correlation_id` | text | not null | Same value also in structured log + response header |
| `source_ip` | inet | nullable | |
| `row_hash` | text | not null | SHA-256 of canonical JSON of all preceding fields |

**Indexes**: `(timestamp DESC)`, `(object_type, object_id, timestamp DESC)`,
`(correlation_id)`, `(actor, timestamp DESC)`.

**Chain table** `audit_chain_heads`: `day date PK, last_event_hash text,
sealed_at timestamptz`.

**Action vocabulary for F1** (extensible):

- `import.csv.accepted`, `import.csv.rejected`, `import.csv.override`
- `import.job.completed`, `import.job.failed`
- `normalization.rule.added`, `normalization.rule.updated`,
  `normalization.rule.disabled`, `normalization.rules.reloaded`
- `observation.manual_mapping.created`,
  `observation.manual_mapping.disabled`
- `observation.re_evaluated`
- `device.created`, `device.classified`
- `auth.token.issued`, `auth.token.revoked`
- `auth.denied`
- `mcp.tool.invoked`

---

## Entity: `LifecycleEvidence`

Structured proof of lifecycle-relevant events. Append-only.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID v7 | PK | |
| `evidence_type` | enum | not null | F1 emits `import` and `manual_mapping`; later features extend |
| `subject_type` | text | not null | e.g. `Device`, `ImportJob` |
| `subject_id` | text | not null | |
| `before_state` | JSONB | nullable | |
| `after_state` | JSONB | nullable | |
| `actor` | text | not null | |
| `system` | text | not null | e.g. `gard@v1.0.0` |
| `timestamp` | timestamptz | not null, default now | |
| `source_checksum` | text | nullable | e.g. CSV SHA-256 for `import` evidence |
| `references` | JSONB | nullable | List of related ids (audit events, observations, etc.) |
| `row_hash` | text | not null | Same construction as `AuditEvent.row_hash` |

---

## Entity: `ApiToken` *(infrastructure, but persisted)*

For service / MCP clients.

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID v7 | PK | Also embedded in JWT as `jti` |
| `name` | text | not null | Operator-readable |
| `subject` | text | not null | The `sub` claim |
| `roles` | text[] | not null | Subset of role catalog |
| `issued_at` | timestamptz | not null | |
| `expires_at` | timestamptz | not null | Default = `issued_at + 90 days`; operators with `manage_mcp_tools` may override per-token via the issuance endpoint, but the column itself is never null (FR-025) |
| `revoked_at` | timestamptz | nullable | |
| `created_by` | text | not null | |

---

## Relationships (ERD-lite)

```text
ImportJob 1 ───< n DeviceObservation >─── 1 Device
                          │
                          └─< 0..1 ManualMapping

NormalizationRule (no FK; consulted at classification time)

AuditEvent ─── references → (object_type, object_id) of any entity
LifecycleEvidence ─── references → (subject_type, subject_id)
ApiToken (standalone)
```

---

## State Machine: `Device.lifecycle_state`

F1 implements two transitions (the rest belong to later features and
are listed here so the enum and state table are correct from day one):

```text
                  ┌──── F1 transitions ──────┐
imported ─────────► classified
                  └──────────────────────────┘

(F2+) classified  ─► target_defined
(F3+) target_defined ─► compliant
(F3+) target_defined ─► outside_target
(F4+) outside_target ─► ready_for_uplift
(F4+) outside_target ─► blocked
(F5+) ready_for_uplift ─► uplift_planned ─► approval_pending ─► approved
(F5+) blocked ─► exception_approved
... (see gard-speckit-start/specs/02-lifecycle-state-machine.md for full set)
```

**Invariant for F1**: a `Device` cannot enter `classified` unless at
least one `DeviceObservation` exists with `confidence` ∈
{`exact`, `high`, `medium`} **or** a `ManualMapping` exists for the
latest observation.

A `Device` remains in `imported` while every observation has
`confidence = manual_review_required` and no manual mapping exists.

---

## Validation Rules Summary (cross-cuts)

1. **No silent defaults**: every Pydantic model uses strict mode; fields
   are explicit; missing inputs become rejections, not zero-values.
2. **Append-only enforcement**: `device_observations`, `audit_events`,
   and `lifecycle_evidence` tables are owned by a Postgres role that
   has `UPDATE` and `DELETE` revoked. Migrations create both roles
   (`gard_app`, `gard_writer_append_only`) and grant accordingly.
3. **Explainable response envelope**: every `Device` and
   `DeviceObservation` returned by API or MCP includes:
   ```json
   {
     "state": "classified",
     "summary": "Matched rule cisco-isr-1121 against vendor_raw='Cisco Systems'",
     "facts": { "matched_rule": "cisco-isr-1121", "raw_payload_keys": [...] },
     "reasons": ["regex match on vendor_raw_regex"],
     "recommended_actions": [],
     "confidence": "exact"
   }
   ```
4. **UUID v7 everywhere**: ensures time-orderable PKs and easy listing
   without secondary `created_at` indexes for default sort.
