# ADR-0014: Drift taxonomy — types, storage shape, and precedence

- **Status**: Accepted (2026-05-30)
- **Feature**: F3 (003-compliance-drift-evaluation)
- **Related**: ADR-0011 (catalog YAML/precedence), ADR-0012
  (LifecycleState.unknown), Constitution III (never coerce), Constitution V
  (audit + explainability)
- **Supersedes**: nothing
- **Decision drivers**: estate-wide triage, machine-readable
  envelopes, auditability

## Context

F2 answered the per-device question *"is this device on its
target?"* with a five-state `FirmwareComplianceState` enum
(`classified / target_defined / compliant / outside_target /
unknown`). F3 needs to answer two harder questions:

1. **Across the whole estate, by category, where is the drift?** —
   so an operator with thousands of devices can route work to the
   right team (catalog owner vs. field engineer vs. audit team).
2. **For one device, why is it non-compliant and what should I do?**
   — so a paged engineer can act without joining four endpoints.

Both demand a vocabulary richer than "compliant vs not". GARD's seed
material (`gard-speckit-start/specs/02-lifecycle-state-machine.md`)
already enumerates a seven-type drift taxonomy. This ADR formalises
that taxonomy, decides how the classification is stored, and locks
the precedence ordering used when a device classifies into multiple
types.

## Decision

### Part A — The seven canonical drift types

| Drift type | Fires when |
|---|---|
| `target_drift` | Resolved target's `target_version` differs from latest `DeviceObservation.observed_firmware` |
| `catalog_drift` | Device is `classified` but no `FirmwareTarget.scope_selector` matches its facts |
| `package_drift` | Resolved target's `target_version` has no `FirmwarePackage` row, OR a row exists but `blob_present = false` |
| `rule_drift` | Target matched and version mismatched, but no `FirmwareUpgradePath` chain from observed to target exists for the platform |
| `discovery_drift` | Latest observation older than `GARD_DISCOVERY_STALE_DAYS` (default 30), OR device has zero observations |
| `evidence_drift` | State `compliant` but no `LifecycleEvidence` of type `re_evaluation` within `GARD_EVIDENCE_STALE_DAYS` (default 90) |
| `exception_drift` | An `Exception` row references the device AND is expired OR has no approver (forward seam — F5 enables; v1 always returns "no exception") |

These types are **categorical, not numerical**. Risk scoring is F7's
domain — F3 emits no score field.

### Part B — Storage shape: append-only `ComplianceEvaluation` rows

A new `gard_app.compliance_evaluations` table stores one row per
evaluation that resulted in a state-or-drift transition.
Re-evaluations against unchanged inputs are **silent** (no row, no
audit). The live verdict for a device is the latest row by
`evaluated_at`; older rows are the classification audit trail.

Rationale:
- Mutating a single row per device would destroy the
  "when did r1.oslo first surface evidence_drift?" question.
- Storing in `lifecycle_evidence` instead would muddy that table's
  append-only-by-DB-grant audit guarantee with what is really a
  derived-state cache.
- Indices: `(device_id, evaluated_at DESC)` serves the latest-per-device
  read via Postgres `DISTINCT ON`; partial index on
  `(primary_drift_type)` accelerates the summary counter.

### Part C — Precedence ordering for the primary drift type

When a device classifies into multiple drift types, the **primary**
type (the one surfaced as `envelope.drift_type` and counted by the
summary endpoint) follows this fixed order:

```
catalog_drift > rule_drift > package_drift > target_drift
              > discovery_drift > evidence_drift > exception_drift
```

Rationale:
- **Upstream causes outrank downstream symptoms.** A device with no
  target *and* a stale observation must surface `catalog_drift`
  first — fixing the observation in isolation leaves the device
  unclassifiable.
- **Pipeline blockers (rule/package) outrank version mismatch.** Even
  if `target_drift` is true, an operator cannot act on the upgrade
  without an upgrade chain or a built package. Surfacing those first
  routes work to the catalog team, not the field team.
- **Observability concerns (discovery/evidence) are secondary**
  because they don't block the *device's* lifecycle progression on
  their own.
- **Exception drift is last** because the exception was a deliberate
  governance action; its expiry should re-surface whatever
  underlying drift the exception was covering.

All secondary drift types still surface in
`envelope.secondary_drift_types[]` (sorted by the same precedence)
so operators can see the full picture.

## Alternatives considered

- **Severity-weighted score.** Rejected: introduces a tunable that
  becomes a debate every quarter. Constitution V prefers explicit,
  citable rules over computed scores in v1.
- **Earliest-detected-wins** for primary. Rejected: arbitrary;
  doesn't help triage.
- **No primary — all equal.** Rejected: clients would invent their
  own ordering, defeating Principle V's explainability goal.
- **Store evaluations in `lifecycle_evidence`.** Rejected: evidence
  is audit-grade, evaluations are derived cache; conflating erodes
  the audit semantics F1 carefully built.
- **Mutable one-row-per-device.** Rejected: loses the classification
  history.

## Consequences

### Positive

- Operators get a categorical drift summary that maps cleanly to
  the team that should fix it.
- The envelope's `drift_type` is a closed enum, safe to forward to
  AI agents or runbook generators.
- The classification trail in `compliance_evaluations` is a free
  side-effect — useful for "show me r1.oslo's compliance history
  this quarter" without a separate event log.

### Negative

- Append-only growth: v1 estimate ~18 M rows/year at 5,000 devices ×
  10 evaluations/day. Pruning is a v2 concern; the migration
  documents the partitioning seam.
- The precedence ordering is one binding decision that future
  features (especially F4 readiness) must respect — F4 cannot
  silently re-rank.

### Neutral

- `exception_drift` is a forward seam. The rule wired in F3 always
  returns "no exception" until F5 introduces the `Exception` entity.
  This is deliberate; no other v1 feature needs `exception_drift` to
  fire.

## Decision record

| What | Where |
|---|---|
| Type catalogue | `gard/core/drift_rules.py` (`DriftType` Literal + one `is_*` function per type) |
| Precedence constant | `gard/core/drift_rules.py::DRIFT_PRECEDENCE` |
| Storage migration | `gard/db/migrations/versions/0007_compliance_evaluations.py` |
| ORM model | `gard/models/compliance_evaluation.py` |
| Public contract | `specs/003-compliance-drift-evaluation/contracts/rest-openapi.yaml#/components/schemas/DriftType` |
| Tests | `tests/unit/test_drift_rules.py` + `tests/unit/test_drift_precedence.py` |
