# F4 Data Model

**Generated**: 2026-05-31 by `/speckit-plan` Phase 1
**Source**: [spec.md](./spec.md) "Key Entities" + [research.md](./research.md) R-1..R-8

This document specifies the **physical** and **logical** data layout for F4: the new `readiness_evaluations` table, JSONB blocker shape, audit emit catalogue, and the cross-feature dependency graph.

---

## 1. ORM entities

### 1.1 `ReadinessEvaluation`

Append-only row capturing one F4 verdict per device per verdict-change. Persisted in `gard_app`.

```python
class ReadinessEvaluation(Base):
    __tablename__ = "readiness_evaluations"

    # Identity + cross-feature refs
    id:                          UUID                  # primary key (uuid7)
    device_id:                   UUID                  # FK -> devices.id, NOT NULL
    compliance_evaluation_ref:   UUID | None           # FK -> compliance_evaluations.id, SET NULL
                                                       # (the F3 row this verdict was derived from)

    # Verdict
    readiness_state:             str                   # CHECK in (ready_for_uplift, blocked, not_applicable)
    target_version:              str | None            # snapshot from F3 envelope
    observed_version:            str | None
    upgrade_path_exists:         bool                  # NOT NULL
    applicable_rules_count:      int                   # NOT NULL, ge=0

    # Explainability
    blockers:                    list[dict]            # jsonb, sorted per R-1
    recommended_actions:         list[dict]            # jsonb, sorted per R-7
    confidence:                  Decimal(3,2)          # 0.0..1.0; v1 always 1.0
    reasons:                     list[dict]            # jsonb, F3-shape ComplianceReason entries

    # Provenance
    evaluated_at:                datetime              # NOT NULL, default now()
    correlation_id:              str                   # NOT NULL
    actor:                       str                   # "system:..." or "user:..."
```

**Constraints**:
- `CHECK (readiness_state IN ('ready_for_uplift', 'blocked', 'not_applicable'))`.
- `CHECK (confidence >= 0.0 AND confidence <= 1.0)`.
- `CHECK (applicable_rules_count >= 0)`.
- `FK device_id -> devices(id) ON DELETE RESTRICT`.
- `FK compliance_evaluation_ref -> compliance_evaluations(id) ON DELETE SET NULL` (a pruned F3 row leaves F4 evidence intact).

**Indices**:
- `PRIMARY KEY (id)`.
- `ix_readiness_evaluations_device_evaluated_desc` ON `(device_id, evaluated_at DESC)` — serves DISTINCT-ON latest-per-device.
- `ix_readiness_evaluations_state` ON `(readiness_state)` WHERE `readiness_state IN ('ready_for_uplift', 'blocked')` — partial index for the summary counter.
- `ix_readiness_evaluations_first_blocker_kind` ON `((blockers->0->>'predicate_kind'))` WHERE `readiness_state = 'blocked'` — partial expression index for top-blocker-categories aggregate (Postgres JSONB supports this directly).
- `ix_readiness_evaluations_evaluated_at` ON `(evaluated_at DESC)` — supports future pruning + time-range queries.

**Migration**: `gard/db/migrations/versions/0008_readiness_evaluations.py` (continues the F1+F2+F3 sequence: 0001..0007 already taken).

---

## 2. Enum surfaces

Python `Literal` types surfaced in the JSON schemas — same pattern as F1/F2/F3 (no DB enums; CHECK constraints over string values).

### 2.1 `ReadinessState`

```python
ReadinessState = Literal[
    "ready_for_uplift",
    "blocked",
    "not_applicable",
]
```

### 2.2 `BlockerPredicateKind`

Closed enum; mirrors F2's `predicate_kind` plus two F4-synthetic kinds.

```python
BlockerPredicateKind = Literal[
    # inherited verbatim from F2's PredicateKind:
    "min_ram_mb",
    "min_disk_mb",
    "min_current_version",
    "hardware_revision_in",
    "license_present",
    "intermediate_version_required",
    "not_in_state",
    "region_in",
    "tagged_with",
    # F4 synthetic kinds (not in F2's catalogue):
    "missing_upgrade_path",      # No chain from observed_version to target_version
    "missing_observation_field", # Required rule input is null in latest observation
]
```

### 2.3 `BlockerSeverity`

Mirrors F2's:

```python
BlockerSeverity = Literal["required", "recommended"]
```

### 2.4 `RecommendedActionKind` — F3 extension

F4 widens F3's existing `RecommendedActionKind` Literal in place (R-2 decision). New kinds:

```python
# F3 already declared:
#   upgrade_path_query, define_target, define_upgrade_path,
#   upload_firmware_package, trigger_discovery,
#   request_observation_refresh, escalate_to_catalog_owner,
#   acknowledge_exception
# F4 adds:
"schedule_uplift_wave"       # ready_for_uplift devices — drives F5 wave drafting
"hardware_refresh"           # min_ram_mb / min_disk_mb / hardware_revision_in blockers
"license_acquire"            # license_present blocker
"firmware_intermediate_step" # intermediate_version_required blocker — names the hop
"import_observation"         # missing_observation_field blocker
```

The F3 contract test `test_compliance_rest_openapi.py` will detect the schema change; we expect it to update the served OpenAPI when F4 lands.

---

## 3. Readiness state ↔ F3 compliance state matrix

F4 does NOT introduce new lifecycle_state values for the device row. It writes one of `ready_for_uplift` or `blocked` into `devices.lifecycle_state` when the F3 verdict was `outside_target`, and leaves the device's lifecycle state alone otherwise.

| Latest F3 `compliance_state` | F4 reads | F4 verdict | `devices.lifecycle_state` write |
|---|---|---|---|
| `compliant`         | — | `not_applicable` (reason `already_compliant`)        | leave (`compliant`) |
| `classified`        | — | `not_applicable` (reason `no_target_resolved`)       | leave (`classified`) |
| `target_defined`    | — | `not_applicable` (reason `no_observation_to_verify`) | leave (`target_defined`) |
| `unknown`           | — | `not_applicable` (reason `lifecycle_unknown`)        | leave (`unknown`) |
| `outside_target`    | run predicates + graph check | `ready_for_uplift` OR `blocked` | write the new state |

The biconditional that F4 enforces:
- `readiness_state == 'ready_for_uplift'` ⇔ (no required blocker fired) AND (`upgrade_path_exists`)
- `readiness_state == 'blocked'`           ⇔ (at least one required blocker fired)
- `readiness_state == 'not_applicable'`    ⇔ F3 state ≠ `outside_target`

---

## 4. Blocker JSON shape

Stored in `readiness_evaluations.blockers` and surfaced in the response envelope:

```yaml
blocker:
  type: object
  additionalProperties: false
  required: [predicate_kind, severity, detail]
  properties:
    rule_id:          {type: [string, "null"], format: uuid,
                       description: "FirmwarePrerequisiteRule id; null for synthetic blockers"}
    rule_name:        {type: [string, "null"]}
    predicate_kind:   {$ref: "#/components/schemas/BlockerPredicateKind"}
    severity:         {$ref: "#/components/schemas/BlockerSeverity"}
    required:         {type: [object, "null"],
                       description: "predicate-kind-specific required value(s); e.g. {min_mb: 2048} or {versions: ['7.5.x']}"}
    observed:         {type: [object, "null"],
                       description: "the observation value F4 read"}
    detail:           {type: string,
                       description: "operator-readable explanation"}
```

Examples:

```json
{
  "rule_id": "06a1...",
  "rule_name": "iosxr-minimum-ram",
  "predicate_kind": "min_ram_mb",
  "severity": "required",
  "required": {"min_mb": 2048},
  "observed": {"ram_mb": 1024},
  "detail": "device has 1024 MB RAM; rule requires >= 2048 MB"
}

{
  "rule_id": null,
  "predicate_kind": "missing_upgrade_path",
  "severity": "required",
  "required": {"target_version": "7.8.1", "platform_family": "iosxr"},
  "observed": {"observed_version": "7.5.2"},
  "detail": "no upgrade-path chain from 7.5.2 to 7.8.1 on platform iosxr (or all chains exceed weight cap 1000)"
}

{
  "rule_id": "06a1...",
  "rule_name": "iosxr-discovery-tag",
  "predicate_kind": "tagged_with",
  "severity": "recommended",
  "required": {"tags": ["pre-uplift-review"]},
  "observed": {"tags_known": false},
  "detail": "tagged_with predicate deferred to F8; surfacing as advisory"
}
```

---

## 5. Audit emit catalogue

F4 contributes three new audit action families. Same writer session as F1/F2/F3; no schema change to `audit_events`.

| `action`                            | `object_type`                     | `result`        | When |
|---|---|---|---|
| `readiness.evaluated`               | `Device`                          | `success`       | One per controller invocation that actually INSERTed a new evaluation row. |
| `readiness.read`                    | `ReadinessSummary` / `ReadinessDeviceList` | `success` / `failure` | One per `GET /api/v1/readiness/summary` and `GET /api/v1/readiness/devices`. |
| `readiness.evaluation_triggered`    | `ReadinessEvaluationBatch`        | `success` / `partial` | One per `POST /api/v1/readiness/evaluate`. |

`compliance.evaluated`'s `after_state` already carries `evaluation_id` (F3 PR #3) — F4's `readiness.evaluated.after_state` carries an analogous `evaluation_id` + the device's prior readiness_state so a diff is trivially constructible from the audit log.

---

## 6. Cross-feature dependencies (read-only)

| Feature | Tables consumed | Purpose |
|---|---|---|
| F1 | `devices` | filter facts (region/site/platform_family) + `lifecycle_state` write target |
| F1 | `device_observations` | `ram_mb`, `disk_mb`, `licenses`, `hardware_revision`, `observed_firmware` |
| F2 | `firmware_prerequisite_rules` | the prereq catalogue; rule evaluator dispatches per `predicate_kind` |
| F2 | `firmware_upgrade_paths` | reachability via the existing `UpgradePathGraphCache` |
| F3 | `compliance_evaluations` | source of `target_version`, `observed_version`, `compliance_state` for the per-device pipeline |

F4 writes only to:
- `readiness_evaluations` (its own table)
- `audit_events` (append-only via the writer session)
- `devices.lifecycle_state` (atomic with the F4 row insert; transitions only across `outside_target` ↔ `ready_for_uplift` ↔ `blocked`)

---

## 7. Pruning seam (v2)

`readiness_evaluations` grows at the same cadence as `compliance_evaluations` (which is itself bounded by F3 R-4 idempotency). v1 has no pruning. v2 will reuse whichever pruning shape F3 ends up adopting (partitioning or scheduled `DELETE`). Documented in the migration's docstring.
