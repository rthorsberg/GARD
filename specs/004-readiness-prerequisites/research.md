# F4 Research & Design Decisions

**Generated**: 2026-05-31 by `/speckit-plan` Phase 0
**Source spec**: [spec.md](./spec.md)
**Sibling features grounding this work**: F1 (devices/observations), F2 (prereq catalogue + upgrade-path graph), F3 (compliance envelope + bounded reload re-eval).

Eight decisions (R-1 through R-8). Each is binding for v1 and overridable only via an ADR (R-1 gets ADR-0015 explicitly because it shapes every downstream feature's blocker interpretation).

---

## R-1 — Blocker severity precedence: required > recommended; ties broken by `predicate_kind` enum order

**Decision**: When a device fires multiple blockers, the envelope sorts them by `(severity desc, predicate_kind enum index asc, rule_id asc)`. The *primary blocker* (the one the engineer sees first) is `blockers[0]` after this sort.

**Rationale**:
- A single `required` blocker is enough to flip the device to `blocked` (FR-003). The engineer cares first about what's actively blocking, not advisory warnings.
- Within severity, the predicate-kind ordering chooses what to suggest acting on first. ADR-0015 §B locks the canonical order: hardware constraints (`min_ram_mb`, `min_disk_mb`, `hardware_revision_in`) outrank firmware-chain constraints (`min_current_version`, `intermediate_version_required`), which outrank licensing (`license_present`), then deferred (`tagged_with`), then synthetic (`missing_upgrade_path`, `missing_observation_field`).
- Hardware first because it's the only blocker that may require physical work — surface that fact first so capacity planning catches it.
- Stable sort on `rule_id` keeps the order deterministic across reloads even when the rule set rotates (SC-004).

**Alternatives considered**:
- *Severity-only ordering*: gives a list but no useful primary; engineers would invent their own ordering, defeating explainability.
- *"First-rule-loaded wins"*: arbitrary; not deterministic on a reload.
- *Numerical "fixability score"*: introduces a tunable that becomes a debate every quarter (same reasoning we rejected this in ADR-0014).

---

## R-2 — Storage: append-only `ReadinessEvaluation` table, one row per verdict-change

**Decision**: New table `gard_app.readiness_evaluations`, written by the regular `gard_writer` role (NOT the append-only audit role; same pattern as F3's `compliance_evaluations`). One INSERT per evaluation pass that changes the verdict; silent re-evaluations make no row, no audit. Latest row per device is the live verdict.

**Rationale**:
- Same pattern as F3 → no new database discipline to learn (Constitution-friendly).
- Append-only at the row level preserves the audit trail of "when did r1.oslo first surface as blocked-by-RAM?" without needing a parallel event-log table.
- The cache can be rebuilt from upstream sources (`compliance_evaluations` + F2 prereqs + F2 graph) — the chain-of-custody record stays in `audit_events`.
- Indices mirror F3: `(device_id, evaluated_at DESC)` for DISTINCT-ON latest-per-device, partial `(readiness_state)` for the summary counter, and a partial index on `(blockers->'$[0].predicate_kind')` for the top-categories aggregate (Postgres JSONB supports this via expression indices).

**Alternatives considered**:
- *Single mutable row per device*: loses history; engineers need to see when a device transitioned blocked → ready or vice versa.
- *Reuse F3's `compliance_evaluations`*: muddies F3's table contract; F3's drift_type and F4's readiness_state aren't a 1:1 shape.
- *Materialised view*: doesn't capture history; refresh cadence is harder to reason about than INSERT-on-change.

---

## R-3 — Controller composition: F4 reads F3's latest row, never recomputes target resolution

**Decision**: `readiness_evaluation_controller.evaluate(session, audit_session, device_id, actor)` follows this exact pipeline:

1. `latest_evaluation = compliance_evaluation_controller.latest_evaluation_for(session, device_id)`. If null → readiness state is `not_applicable` with reason `no_compliance_evaluation`.
2. If `latest_evaluation.evaluated_at > now - GARD_READINESS_STALE_DAYS` → continue. Else → raise `ReadinessInputStale` (router translates to 409 + structured error).
3. Branch on `latest_evaluation.compliance_state`:
   - `compliant`, `classified`, `target_defined`, `unknown` → `not_applicable` with reason citing the F3 state.
   - `outside_target` → continue into prereq + graph evaluation.
4. Run **all** F2 prerequisite rules whose `applies_to` selector matches the device facts (reuses `gard.core.scope_selector.evaluate`).
5. For each fired rule, dispatch to the per-`predicate_kind` predicate function (R-4). Collect blockers.
6. Check upgrade-path reachability: ask the `UpgradePathGraphCache` (reuse F2's `gard.core.upgrade_path_graph`) for a chain from `observed_version` to `target_version` on `platform_family`, refusing chains with cumulative weight > `GARD_READINESS_UPGRADE_WEIGHT_CAP`. If none → append a synthetic blocker `kind=missing_upgrade_path`, severity `required`.
7. Apply R-1 sort. Decide state: `blocked` iff any `required`-severity blocker; `ready_for_uplift` otherwise.
8. Compare to the latest persisted `readiness_evaluations` row (R-5 idempotency). If same → return envelope; no INSERT, no audit. Else → INSERT row + emit `readiness.evaluated` audit + flip device.lifecycle_state if applicable.

**Rationale**:
- Reading F3's row instead of recomputing target resolution keeps F4's logic narrow and means a stale F3 row will *cause* a stale F4 verdict — surfaced as a 409, not silently absorbed.
- Reusing F2's graph cache and scope selector means F4 cannot drift from F2's "does this upgrade chain exist?" answer (no two implementations of the same question).

**Alternatives considered**:
- *F4 recomputes target resolution from F2*: duplicates F3's work and risks divergent verdicts.
- *F4 calls F3's controller directly*: would re-INSERT F3 evaluation rows on every F4 call. Pure side-effects; rejected.
- *F4 derives directly from `outside_target` lifecycle_state*: loses the F3-cited `target_ref` + `target_version`; the blocker explanations would have no upstream proof.

---

## R-4 — One pure function per `predicate_kind` in `gard/core/prereq_predicates.py`

**Decision**: For each of F2's seven evaluable `predicate_kind` values (`min_ram_mb`, `min_disk_mb`, `min_current_version`, `hardware_revision_in`, `license_present`, `intermediate_version_required`, `not_in_state`, `region_in`) plus the deferred `tagged_with`, ship one pure function:

```python
def eval_min_ram_mb(rule: FirmwarePrerequisiteRule, device: Device, observation: DeviceObservation | None) -> Blocker | None
```

Each returns either a `Blocker` (with the missing input named) or `None`. The controller dispatches via a `dict[str, Predicate]`. The `tagged_with` predicate ships but always returns a `recommended`-severity blocker noting deferral (matches F2's `predicate_deferred` behaviour).

**Rationale**:
- Same testability discipline as F3's drift_rules — pure functions, unit-testable with constructed inputs, no DB.
- Closed dispatch table means an unknown `predicate_kind` value loaded from YAML fails loud (with a `KeyError`) rather than silently passing — Constitution III.
- `region_in` + `not_in_state` are device-fact predicates rather than observation predicates; the dispatch signature accepts the observation as optional, which the type system enforces.

**Alternatives considered**:
- *Single switch-statement controller*: 200-line function, hard to test, hard to extend.
- *Predicates declared on the rule model itself*: ties business logic to the ORM layer; rejected (F1/F2 keep ORM thin).

---

## R-5 — Idempotency: silent on identical verdict

**Decision**: An evaluation is "the same as last time" iff `(readiness_state, sorted blockers (kind, severity, rule_id, required, observed), recommended_actions sorted by kind + payload, upgrade_path_exists, applicable_rules_count)` all match the latest persisted row. Anything different → INSERT. Identical → no INSERT, no audit, return current envelope with the existing `evaluation_id`.

**Rationale**:
- Mirrors F3 R-4 verbatim. Same test cases catch regressions across both controllers.
- Comparing the blocker JSON shape (not just count) avoids the trap "same count, different rules" — which IS a verdict change worth recording.
- `correlation_id` and `evaluated_at` are explicitly excluded from the comparison — they change on every call.

---

## R-6 — Reload-sync extends F3's hook in place

**Decision**: `gard.core.firmware_catalog_controller._reevaluate_compliance_post_reload` already calls F3's `compliance_evaluation_controller.evaluate` for each affected device. F4 extends this hook by adding a third call to `readiness_evaluation_controller.evaluate` after the F3 call returns, same actor + correlation_id. The "affected" set definition (set1 ∪ set2 from F2's current implementation) is unchanged — it's already correct for F4 because:

- set1 (firmware-derived lifecycle_state) already includes `outside_target` and `ready_for_uplift` / `blocked` once F4 ships.
- set2 (devices whose facts match a touched target's scope) covers the case where a new target makes more devices outside_target.

What's added for prereq rule reloads: F4 contributes a **set3** = devices whose facts match the `applies_to` selector of any added/removed/changed prerequisite rule. The hook's signature extension is internal — no F2 ABI change.

**Rationale**:
- One hook, three controllers — easy to reason about, easy to test ("did exactly the affected devices receive new F4 rows?").
- No new scheduler / worker / queue. Constitution-friendly: every code path is synchronous and audited.
- F4's failure is wrapped in `try/except` (matches F3's pattern from PR #3) so a F4 bug never breaks the F2 reload pipeline (ADR-0011 §8).

---

## R-7 — Determinism: blockers + actions are sorted, JSON payloads are stable

**Decision**: Inside the controller, `blockers` are sorted with the R-1 key tuple before envelope construction. `recommended_actions` are sorted by `(kind, model_dump_json())` — same recipe as F3. The Pydantic model emit order matches the OpenAPI schema field order so JSON output is stable across Python releases (Pydantic v2 guarantees model dump order = field declaration order).

**Rationale**:
- SC-004 requires byte-identical envelopes for unchanged inputs. Sort + stable Pydantic dump = byte-identical.
- Contract test `test_readiness_envelope_determinism.py` will call evaluate twice on the same inputs and assert byte-equality (modulo `correlation_id`, `as_of`, `evaluation_id`).

---

## R-8 — Stale F3 input: 409, not silent

**Decision**: If the latest `compliance_evaluation` for a device is older than `GARD_READINESS_STALE_DAYS` (default 30), the per-device endpoint returns **HTTP 409** with a structured error envelope:

```json
{
  "error": {
    "code": "READINESS_INPUT_STALE",
    "message": "compliance_evaluation for this device is older than 30 days; refresh via POST /api/v1/compliance/evaluate",
    "details": {"latest_compliance_evaluated_at": "2026-04-30T...", "stale_threshold_days": 30}
  }
}
```

The summary endpoint silently skips stale rows (counts them as `not_applicable` with reason `stale_compliance_input`) — this preserves the bounded-latency contract for the dashboard.

**Rationale**:
- Constitution III: do not pretend a stale verdict is fresh.
- Different per-device vs summary behaviour because the dashboard's whole *purpose* is to give a verdict in <1s; making it raise on staleness would defeat that. Per-device callers can afford to see an actionable 409 and trigger the refresh.
- 409 (Conflict) rather than 4xx because it's a recoverable state, not a client error — the recovery action is named in the error body.

**Alternatives considered**:
- *Auto-trigger F3 evaluation on stale read*: violates the "summary endpoint never triggers" constraint and turns a read into a write.
- *Always return a stale verdict with a flag*: AI agents would routinely treat the flag as advisory. Hard 409 forces correct handling.
