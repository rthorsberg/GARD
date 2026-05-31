# F3 Data Model

**Generated**: 2026-05-30 by `/speckit-plan` (Phase 1)
**Source**: `spec.md` §"Key Entities" + `research.md` decisions R-1..R-8

This document specifies the **physical** and **logical** data layout
for F3, including the new `compliance_evaluations` table, indices,
audit-emit catalogue, and state-transition matrix.

---

## 1. ORM entities

### 1.1 `ComplianceEvaluation`

Append-only classification row. One INSERT per evaluation pass per
device that changed. Persisted in the `gard_app` schema.

```python
class ComplianceEvaluation(Base):
    __tablename__ = "compliance_evaluations"

    # Identity + cross-feature references
    id:              UUID                  # primary key
    device_id:       UUID                  # FK -> devices.id, NOT NULL
    target_ref:      UUID | None           # FK -> firmware_targets.id, NULL OK
                                           # (catalog_drift devices have none)

    # Classification result
    compliance_state: str                  # mirrors FirmwareComplianceState enum
                                           # CHECK in (classified, target_defined,
                                           #          compliant, outside_target,
                                           #          unknown)
    primary_drift_type:    str | None      # CHECK in DRIFT_TYPES, NULL == compliant
    secondary_drift_types: list[str]       # jsonb array of DRIFT_TYPES, may be []

    # Cited inputs (snapshot at evaluation time)
    target_version:    str | None          # e.g., "7.8.1" or NULL
    observed_version:  str | None          # e.g., "7.5.2" or NULL
    observation_ref:   UUID | None         # FK -> device_observations.id, NULL OK

    # Explainability payload (kept compact; full envelope reconstructible)
    reasons:               list[dict]      # jsonb, sorted per R-7
    recommended_actions:   list[dict]      # jsonb, sorted per R-7
    confidence:            float           # 0.0..1.0, mirrors F1 confidence ladder

    # Provenance + audit linkage
    evaluated_at:    datetime              # NOT NULL, default now()
    correlation_id:  str                   # NOT NULL, ties to audit row
    actor:           str                   # e.g., "system" or operator email
```

**Constraints**:
- `CHECK (compliance_state IN ('classified', 'target_defined',
  'compliant', 'outside_target', 'unknown'))` — mirrors F2's enum.
- `CHECK ((primary_drift_type IS NULL) = (compliance_state =
  'compliant'))` — compliant ⇔ no drift type.
- `CHECK (primary_drift_type IS NULL OR primary_drift_type IN
  ('target_drift', 'catalog_drift', 'package_drift', 'rule_drift',
  'evidence_drift', 'discovery_drift', 'exception_drift'))`
- `CHECK (confidence >= 0.0 AND confidence <= 1.0)`
- `FK device_id -> devices(id)` — `ON DELETE RESTRICT` (devices
  are soft-deleted; FK protects against hard delete races).
- `FK target_ref -> firmware_targets(id)` — `ON DELETE SET NULL`
  (a target removed via reload leaves stale evaluations valid for
  audit; the next eval pass produces a fresh row).
- `FK observation_ref -> device_observations(id)` — `ON DELETE SET
  NULL`, same reasoning.

**Indices**:
- `PRIMARY KEY (id)`
- `ix_compliance_evaluations_device_evaluated_desc` ON
  `(device_id, evaluated_at DESC)` — serves the "latest per device"
  query via DISTINCT ON.
- `ix_compliance_evaluations_primary_drift_type` ON
  `(primary_drift_type)` WHERE `primary_drift_type IS NOT NULL` —
  partial index for the summary endpoint's drift-type counter
  query.
- `ix_compliance_evaluations_evaluated_at` ON `(evaluated_at DESC)` —
  supports the future pruning job and time-range debug queries.

**Migration**: `gard/db/migrations/versions/0007_compliance_evaluations.py`
(continues the F1+F2 sequence: 0001..0006 already taken).

---

## 2. Enum surfaces

These are Python `Literal` types surfaced in the JSON schemas (per
F1/F2 convention — no DB enums; CHECK constraints over string
values).

### 2.1 `DriftType`

```python
DriftType = Literal[
    "target_drift",
    "catalog_drift",
    "package_drift",
    "rule_drift",
    "evidence_drift",
    "discovery_drift",
    "exception_drift",
]
```

**Precedence** (R-2, surfaces as a tuple constant in
`gard/core/drift_rules.py`):

```python
DRIFT_PRECEDENCE: tuple[DriftType, ...] = (
    "catalog_drift",
    "rule_drift",
    "package_drift",
    "target_drift",
    "discovery_drift",
    "evidence_drift",
    "exception_drift",
)
```

### 2.2 `RecommendedActionKind`

```python
RecommendedActionKind = Literal[
    "upgrade_path_query",
    "define_target",
    "define_upgrade_path",
    "upload_firmware_package",
    "trigger_discovery",
    "request_observation_refresh",
    "escalate_to_catalog_owner",
    "acknowledge_exception",  # contract only; never emitted by F3
]
```

### 2.3 `ComplianceReasonKind`

Extends F2's `FirmwareComplianceReasonKind` (which stays valid via
composition; F3 adds three new kinds):

```python
ComplianceReasonKind = Literal[
    # inherited verbatim from F2's FirmwareComplianceReasonKind:
    "target_matched", "target_runner_up", "version_match",
    "version_mismatch", "missing_observation", "no_target_matched",
    "empty_catalog", "predicate_deferred",
    # new in F3:
    "stale_observation",       # discovery_drift: obs older than threshold
    "missing_upgrade_path",    # rule_drift: graph has no chain to target
    "package_not_built",       # package_drift: target version has no pkg
]
```

---

## 3. Compliance state-transition matrix

F3 does NOT introduce new lifecycle states — F2 owns
`target_defined / compliant / outside_target / unknown`. F3 only
classifies into drift types within those states.

**Transition triggers** (verbose form of FR-002):

| Current state | Trigger | Next state | Primary drift |
|---|---|---|---|
| `classified` | F2 evaluate finds no target | `classified` | `catalog_drift` |
| `classified` | F2 evaluate finds target | `target_defined` | none yet — wait for next obs |
| `target_defined` | F2 sees observed_version present, matches | `compliant` | none |
| `target_defined` | F2 sees observed_version present, mismatches | `outside_target` | `target_drift` (+ possibly `package_drift`, `rule_drift`) |
| `target_defined` | F2 sees no observation row | `target_defined` | `discovery_drift` (missing_observation) |
| `compliant` | latest obs > GARD_DISCOVERY_STALE_DAYS old | `compliant` | `discovery_drift` (stale_observation) |
| `compliant` | last `re_evaluation` evidence > GARD_EVIDENCE_STALE_DAYS old | `compliant` | `evidence_drift` |
| any | exception expired | unchanged | `exception_drift` (F5 enables) |

**Multi-drift devices**: a `compliant` device that also has a stale
observation surfaces with `compliance_state = "compliant"`,
`primary_drift_type = "discovery_drift"`, `secondary_drift_types =
[]`. A `outside_target` device with no upgrade path:
`primary_drift_type = "rule_drift"`, `secondary_drift_types = ["target_drift"]`
(rule_drift sorts higher per R-2).

---

## 4. Audit emit catalogue

F3 contributes three new action families to the existing `audit_events`
table (no schema change to F1's table). Each row is written by the
existing `gard.core.audit.emit()` helper.

| `action`                              | `object_type`          | `result`        | When |
|---|---|---|---|
| `compliance.evaluated`                | `Device`               | `success`       | One per controller invocation that actually INSERTed a new evaluation row (no-op evaluations are silent). |
| `compliance.read`                     | `ComplianceSummary` or `ComplianceDeviceList` | `success` / `failure` | One per `GET /api/v1/compliance/summary` and `GET /api/v1/compliance/devices`. `after_state` carries the resolved filter set. |
| `compliance.evaluation_triggered`     | `ComplianceEvaluationBatch` | `success` / `partial` / `failure` | One per `POST /api/v1/compliance/evaluate`. `after_state` carries `requested_device_count`, `evaluated_count`, `unchanged_count`, and the first 100 device ids for cross-reference. |

**Payload schemas** (rendered into the actual emit calls; included
here so contract tests can lock them):

```yaml
compliance.evaluated.after_state:
  type: object
  required: [device_id, compliance_state, primary_drift_type,
             secondary_drift_types, target_ref, observed_version,
             confidence, evaluation_id]
  properties:
    device_id:               {type: string, format: uuid}
    compliance_state:        {type: string, enum: [classified,
                              target_defined, compliant,
                              outside_target, unknown]}
    primary_drift_type:      {type: [string, "null"]}
    secondary_drift_types:   {type: array, items: {type: string}}
    target_ref:              {type: [string, "null"], format: uuid}
    observed_version:        {type: [string, "null"]}
    confidence:              {type: number, minimum: 0, maximum: 1}
    evaluation_id:           {type: string, format: uuid}
```

---

## 5. Cross-feature dependencies (read-only)

F3 reads from but does not mutate:

| Feature | Tables consumed | Purpose |
|---|---|---|
| F1 | `devices`, `device_observations` | Device facts + observation freshness; `latest_observation_per_device` query |
| F1 | `lifecycle_evidence` | `evidence_drift` rule: last `re_evaluation` row per device |
| F2 | `firmware_targets` | Target resolution (delegated through F2's `compliance_controller`) |
| F2 | `firmware_packages` | `package_drift` rule: does the target version have a package row? Is `blob_present`? |
| F2 | `firmware_upgrade_paths` | `rule_drift` rule: is there a chain from observed to target on the platform's graph? |

F3 writes only to:
- `compliance_evaluations` (its own table)
- `audit_events` (append-only via the writer session)
- `lifecycle_evidence` (only when F2's reload hook also triggers F3
  — F3 itself does not emit evidence rows in v1; the
  `re_evaluation` evidence rows that the `evidence_drift` rule
  reads come from a future feature, currently the rule reads zero
  rows and behaves accordingly)

---

## 6. Pruning seam (v2)

`compliance_evaluations` grows linearly. v1 has no pruning. The
migration's docstring documents that v2 will add either:
1. A time-partitioned table layout (`compliance_evaluations_YYYYMM`),
   or
2. A scheduled `DELETE WHERE evaluated_at < now() - interval` job
   with a retention period sourced from `GARD_EVALUATION_RETENTION_DAYS`.

Either choice is non-breaking against the v1 query patterns.
Decision deferred until measured growth justifies the work.
