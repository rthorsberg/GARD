# F3 Research & Design Decisions

**Generated**: 2026-05-30 by `/speckit-plan`
**Purpose**: Resolve all design unknowns before Phase 1 contracts. Each
decision is captured as **Decision / Rationale / Alternatives
considered**, the format mandated by the plan skill.

---

## R-1 — `ComplianceEvaluation` storage shape

**Decision**: A new dedicated table `compliance_evaluations` in the
`gard_app` schema. Append-only at the row level (re-evaluations
INSERT a new row, never UPDATE). Indexed on `(device_id, evaluated_at DESC)`
so the latest-per-device read is O(log n). Reads in the summary
endpoint use a `DISTINCT ON (device_id)` query with the same index
(Postgres can serve `DISTINCT ON` directly from the composite index).

**Rationale**:
- Storing per-device evaluation history separately from
  `lifecycle_evidence` keeps the audit grade of the evidence table
  pristine — evidence rows are chain-of-custody, evaluations are
  cache. A row-level mutation in evaluations does not pollute
  evidence semantics. (We still emit `compliance.evaluated`
  audit-event rows; the table is the **derived-state cache**, not
  the audit record.)
- Postgres's `DISTINCT ON` plus a descending composite index makes
  the summary query a single index scan — proven to fit the
  SC-001 budget (1 s p95 over 5,000 devices) in F1's import
  benchmarks against similar table sizes.
- Append-only semantics (FR-004) means the table grows linearly
  with evaluations. v1 estimate: 5,000 devices × ~10
  evaluations/day = 50k rows/day = ~18M/year. With a TOAST'd
  reasons JSON, ~3 GB/year. Pruning is a v2 concern; we leave a
  partition seam in the migration comments.

**Alternatives considered**:
- **Single mutable row per device.** Rejected: would lose the
  classification history needed to answer "when did r1.oslo first
  surface evidence_drift?" without a separate event log.
- **Store evaluations inside `lifecycle_evidence` directly.**
  Rejected: evidence rows are append-only by DB grant (no UPDATE,
  no DELETE) and that constraint is for audit not cache; muddying
  the two would erode the audit guarantee.
- **Materialised view** `compliance_summary_mv`. Rejected for v1:
  added refresh-cadence complexity, dual sources of truth, and the
  direct query is already fast enough. We will revisit if SC-001
  goes red at the 10× scale (50k devices).

---

## R-2 — Drift precedence ordering

**Decision**: Fixed v1 precedence for which drift type is "primary"
when a device classifies into multiple:

```
catalog_drift > rule_drift > package_drift > target_drift
              > discovery_drift > evidence_drift > exception_drift
```

Captured in **ADR-0014** (drafted in this plan, will be promoted to
`adr/ADR-0014-drift-taxonomy.md` when F3 implementation lands).

**Rationale**:
- **Upstream causes outrank downstream symptoms.** If a device has
  no target (`catalog_drift`) AND its observation is stale
  (`discovery_drift`), the operator's first move is to define the
  target; fixing the stale observation in isolation would still
  leave the device unclassifiable. So `catalog_drift` is primary.
- **Pipeline blockers (rule/package) outrank version mismatch.**
  Even if `target_drift` is true, an operator cannot act on it
  without a defined upgrade chain (`rule_drift`) and an available
  package (`package_drift`). Surfacing those first routes work to
  the catalog owner team, not the field team.
- **Discovery and evidence drifts are observability concerns**;
  they're secondary to firmware-state drifts because they don't
  block the *device's* lifecycle progression on their own.
- **Exception drift is last** because the exception was a deliberate
  governance action; its expiry should re-surface whatever
  underlying drift the exception was covering.

**Alternatives considered**:
- **Severity-weighted score.** Rejected: introduces a tunable that
  becomes a debate every quarter. Constitution V prefers
  explicit, citable rules over computed scores in v1.
- **Earliest-detected-wins** (chronological primary). Rejected:
  arbitrary; doesn't help operators prioritise work.
- **No "primary" — all equal.** Rejected: clients would have to
  invent their own ordering, defeating Constitution V's
  explainability goal.

---

## R-3 — Summary endpoint query strategy

**Decision**: One SQL query per request:

```sql
SELECT primary_drift_type, COUNT(*)
FROM (
  SELECT DISTINCT ON (device_id) primary_drift_type
  FROM compliance_evaluations ce
  JOIN devices d ON d.id = ce.device_id
  WHERE <filter predicates from query params>
  ORDER BY device_id, evaluated_at DESC
) latest
GROUP BY primary_drift_type;
```

Plus a parallel `SELECT COUNT(*) … WHERE lifecycle_state = 'unknown'`
for the `unknown_count`. The two queries return in <50 ms each
against 5,000 devices on a Postgres 16 + cold cache in F1's
benchmarks.

**Rationale**:
- Single-query design keeps the controller stateless and the
  cache-warming question moot.
- `DISTINCT ON` is Postgres-native, planner-friendly, and uses the
  composite index from R-1 directly.
- Joining `devices` for the filter predicates (region, site,
  platform_family, vendor_normalized) keeps F3 from duplicating
  those columns onto evaluation rows.

**Alternatives considered**:
- **Window function `ROW_NUMBER() OVER (PARTITION BY device_id ORDER
  BY evaluated_at DESC) = 1`.** Equivalent plan in Postgres 16; we
  prefer `DISTINCT ON` for readability.
- **Per-drift-type cached counters** (Redis or in-process).
  Rejected: cache invalidation across F2 reload + manual evaluate
  is non-trivial; pre-mature optimisation given measured query
  latency.

---

## R-4 — Composition with F2's compliance_controller

**Decision**: F3 introduces
`compliance_evaluation_controller.evaluate(device_id)` which:

1. Calls F2's `compliance_controller.evaluate(device_id)` to obtain
   the per-device `FirmwareComplianceEnvelope` (state, target_ref,
   observed_version, reasons).
2. Runs F3's pure-function drift rules (one per drift type) over
   the device + envelope + catalog state.
3. Composes the final `ComplianceEnvelope` (extends F2's shape
   with `drift_type`, secondary drift list, populated
   `recommended_actions[]`).
4. Persists one `ComplianceEvaluation` row.
5. Emits one `compliance.evaluated` audit row.

F2's controller is treated as **black box** — F3 does not bypass it
or re-implement target resolution.

**Rationale**:
- Single source of truth for the per-device compliance verdict.
- F3 stays cleanly above F2 in the dependency graph.
- The F2 controller's idempotency (re-running against unchanged
  state is silent) propagates to F3 — if nothing changed, no new
  row is INSERTED, no audit is emitted. Implementation: compare
  `(primary_drift_type, secondary_drift_types_sorted,
  target_ref, observed_version)` against the latest row; insert
  only on diff.

**Alternatives considered**:
- **F3 reimplements target resolution in-house.** Rejected: drift
  from F2's logic would surface as classification disagreements
  between `firmware-compliance` and `compliance` endpoints.
- **Merge F3 logic into F2's controller.** Rejected: would
  retroactively expand F2's scope and force every F3 change to
  touch F2 code — bad for feature isolation.

---

## R-5 — `recommended_actions[]` v1 vocabulary

**Decision**: Six action kinds, each with a typed Pydantic params
model:

| Kind | When emitted | params |
|---|---|---|
| `upgrade_path_query` | `target_drift` with both versions known | `{platform_family, from_version, to_version}` |
| `define_target` | `catalog_drift` | `{vendor_normalized, platform_family, hardware_revision?}` |
| `define_upgrade_path` | `rule_drift` | `{platform_family, from_version, to_version}` |
| `upload_firmware_package` | `package_drift` (target version unbuilt) | `{vendor, platform_family, version}` |
| `trigger_discovery` / `request_observation_refresh` | `discovery_drift` | `{device_id}` |
| `escalate_to_catalog_owner` | any drift type where the rule cannot identify a single concrete fix | `{drift_type, contact_role: "catalog_owner"}` |

Plus a future-only `acknowledge_exception` kind that is **defined in
the contract** but never emitted by F3 (F5 will emit it).

**Rationale**:
- Closed enum + typed params makes envelopes machine-consumable by
  the future MCP transport and by runbook generators.
- Six kinds covers the seven drift types cleanly (some drifts emit
  multiple actions; `exception_drift` is the placeholder that
  emits `escalate_to_catalog_owner` in v1).
- Aligns with Constitution VI: no free-form prose actions.

**Alternatives considered**:
- **Free-form string actions.** Rejected: not machine-consumable
  and would invite LLM hallucination at the agent layer.
- **Single generic `do_something` action with `params: dict[str,
  Any]`.** Rejected: defeats the type-safety goal.

---

## R-6 — Reload → F3 sync invocation point

**Decision**: Extend F2's existing post-reload bounded re-evaluation
hook (`firmware_catalog_controller._reevaluate_compliance_post_reload`).
After F2's loop calls `compliance_controller.evaluate(device_id)`
for each affected device, the same loop calls
`compliance_evaluation_controller.evaluate(device_id)` to refresh
F3's persisted row. The cross-feature touchpoint is **one
additional call inside an existing loop** — no new scheduler, no
new queue.

**Rationale**:
- Bounded set is the same: devices in firmware lifecycle states OR
  matching a touched target's scope. F3 should resync exactly
  those devices; broadening the set would scan unrelated devices.
- Reuses F2's hard-cap protection (the loop already refuses
  unbounded sets).
- One transaction, one audit correlation id — operators see
  reload-triggered evaluations grouped together in the audit
  chain.

**Alternatives considered**:
- **F3-owned scheduler that polls for stale evaluations.** Rejected
  for v1: introduces scheduler complexity (cron? celery?
  in-process tick?) for a problem already solved by the loader.
- **DB trigger on `firmware_targets` insert/delete.** Rejected:
  triggers move evaluation off the API process where Postgres
  cannot run Python code, forcing either a stored-procedure
  rewrite or a `LISTEN/NOTIFY` reactor — both heavy for v1.

---

## R-7 — Determinism strategy (sort keys)

**Decision**: Envelope serialisation sorts:

- `reasons[]` by `(kind, ref or "")` ascending
- `recommended_actions[]` by `(kind, ref or "")` ascending
- `secondary_drift_types[]` by the R-2 precedence order (drift
  closer to "catalog" sorts first)

Excluded from sort comparison for determinism checks: `correlation_id`,
`as_of`, `ComplianceEvaluation.id`, `evaluated_at`.

**Rationale**:
- SC-005 demands byte-identical responses for identical inputs.
- Sorting on stable string keys is O(n log n) where n is small
  (typically <10 reasons, <5 actions). Cost is negligible.
- Diff-friendly: an envelope diff between two evaluations shows
  only meaningful changes, not key reordering.

**Alternatives considered**:
- **Preserve insertion order from the rule loop.** Rejected:
  insertion order depends on rule iteration order which depends
  on Python dict ordering, which is stable within a process but
  not guaranteed across releases.
- **Hash-based ordering** (e.g., SHA of the reason payload).
  Rejected: opaque to humans reading the audit log.

---

## R-8 — Staleness configuration shape

**Decision**: Two environment variables read by `gard.core.settings`:

- `GARD_DISCOVERY_STALE_DAYS` (default `30`) — observation older
  than this fires `discovery_drift` with kind `stale_observation`.
- `GARD_EVIDENCE_STALE_DAYS` (default `90`) — last
  `LifecycleEvidence` of type `re_evaluation` older than this
  fires `evidence_drift`.

Both surface in the existing `Settings` Pydantic model with type
`int` (days) and bounds `>= 1`. When unset, defaults apply.
Setting either to `0` is rejected at startup (would mark every
device immediately stale; not a sensible config).

**Rationale**:
- Matches the F1/F2 settings convention (env-var-driven,
  Pydantic-validated, documented in `deploy/docker-compose.yml`).
- Lifecycle-as-Code (Principle IV) is satisfied by these living
  in compose/env config rather than a code constant.
- Two separate knobs because the operationally-appropriate windows
  differ — observations refresh every CSV import (days), validation
  evidence refreshes only on uplift completion (months).

**Alternatives considered**:
- **Single `GARD_STALE_DAYS` for both.** Rejected: conflates two
  semantically different freshness windows.
- **Per-platform-family overrides** in YAML. Rejected for v1 —
  no operator has asked for it; would couple F3 to F2's catalog
  shape unnecessarily.

---

## Open questions for `/speckit-tasks`

None. All eight design unknowns are resolved here. The tasks
generator can proceed with full context.
