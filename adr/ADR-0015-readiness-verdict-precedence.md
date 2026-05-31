# ADR-0015 — Readiness Verdict Precedence & Ordering

**Status**: Accepted
**Date**: 2026-05-31
**Decision-makers**: GARD core team
**Touches**: F4 (Readiness & Prerequisites), F5 (Uplift Planning — consumer)
**Supersedes**: none
**Superseded by**: none

## Context

F4 must answer two related-but-distinct questions for every device F3
classified as `outside_target`:

1. **Verdict**: is this device `ready_for_uplift`, `blocked`, or
   `not_applicable`?
2. **Primary blocker** (when blocked): of the N blockers fired, which
   one should the operator (or AI agent) act on first?

The verdict is a biconditional (data-model.md §3). The primary blocker
choice is an ordering — and the wrong ordering will make every
blocker triage decision a debate. We need this nailed in v1 so that
F5's wave planner can rely on a deterministic primary signal when it
sorts candidate devices.

## Decision

### A. Verdict biconditional

For a device whose latest F3 `compliance_state` is `outside_target`:

- `readiness_state == 'ready_for_uplift'` ⇔ (no `required`-severity
  blocker fired) AND (`upgrade_path_exists`)
- `readiness_state == 'blocked'` ⇔ (at least one `required`-severity
  blocker fired) OR (`upgrade_path_exists == false`)
- `readiness_state == 'not_applicable'` is reserved for devices whose
  latest F3 state is one of `compliant`, `classified`,
  `target_defined`, or `unknown` — F4 has nothing to say. Each carries
  a reason citing why.

### B. Primary blocker ordering (R-1 binding)

Inside `blockers[]`, the order is:

1. Sort by `severity` descending: `required` > `recommended`.
2. Tie-break by canonical `predicate_kind` index ascending:

```python
BLOCKER_PREDICATE_ORDER: tuple[BlockerPredicateKind, ...] = (
    # Hardware constraints first — may require physical work.
    "min_ram_mb",
    "min_disk_mb",
    "hardware_revision_in",
    # Firmware-chain constraints next — actionable via catalog.
    "min_current_version",
    "intermediate_version_required",
    "missing_upgrade_path",
    # Licensing and operational state.
    "license_present",
    "not_in_state",
    "region_in",
    # Observation hygiene — a missing observation field is "we can't
    # tell"; surface late so genuine blockers are first.
    "missing_observation_field",
    # Deferred predicates — F4 cannot yet evaluate fully.
    "tagged_with",
)
```

3. Tie-break by `rule_id` ascending (stable across reloads). Synthetic
   blockers (`missing_upgrade_path`, `missing_observation_field`)
   carry `rule_id = null` and sort first within their kind bucket.

`blockers[0]` after this sort is the **primary blocker** F5 keys off.

### C. Recommended action ordering (R-7 binding)

`recommended_actions[]` is sorted by `(kind, json_canonical(payload))`
— byte-stable. v1 emits at most three actions per envelope (one
"unblock me" action keyed off the primary blocker + at most two
contextual actions).

### D. State carve-out reasons for `not_applicable`

When F4 returns `not_applicable`, the envelope's `reasons[]` carries
exactly one of these canonical reason kinds:

- `already_compliant` — latest F3 state is `compliant`
- `no_target_resolved` — latest F3 state is `classified`
- `no_observation_to_verify` — latest F3 state is `target_defined`
- `lifecycle_unknown` — latest F3 state is `unknown`
- `no_compliance_evaluation` — device has never been F3-evaluated
- `stale_compliance_input` — only used in the summary aggregate (the
  per-device endpoint raises 409 instead per R-8)

## Rationale

**Hardware before chain**: a `min_ram_mb` blocker may require a truck
roll; the operator needs that fact in the first line of the envelope,
not buried under three license-check blockers. Letting hardware
constraints lose to other categories would systematically delay
capacity-planning escalations.

**`missing_upgrade_path` is firmware-chain-class, not synthetic**:
even though it carries `rule_id = null`, the operator's remedy is the
same as a `min_current_version` blocker — touch the F2 catalogue. We
group it with the chain blockers.

**`missing_observation_field` is late** because the remedy is "import
better observations" — that's an F1/F7 concern. Surfacing it first
would mask real prereq blockers behind a data-hygiene complaint.

**Deferred `tagged_with` is last** because F4 cannot yet evaluate it
fully; it surfaces as `recommended` severity and never flips a
verdict to blocked alone. Putting it last keeps it out of the
operator's primary action.

**`rule_id` ascending tie-break** is arbitrary but deterministic.
UUID7 ordering correlates with rule creation time, which is roughly
what operators expect ("the rule I added last week is at the end").

## Alternatives considered

1. **Operator-tunable precedence via env or YAML**. Rejected — gives
   each deployment a different blocker primacy, defeating the
   audit-grade explainability promise. v2 may add per-deployment
   weights if real demand surfaces.
2. **Severity-only ordering with no kind ordering**. Rejected — leaves
   the primary-blocker choice non-deterministic across reloads.
3. **Numerical "fixability score"**. Rejected for the same reason
   ADR-0014 rejected it for drift precedence: a tunable becomes a
   debate every quarter.
4. **`missing_upgrade_path` separate from the firmware-chain bucket**.
   Rejected — operators expect "no chain exists" right next to "your
   chain isn't long enough".

## Consequences

- F5's wave planner sorts candidate `ready_for_uplift` devices by
  `(target_version asc, hostname asc)` knowing the verdict itself is
  authoritative (no need to inspect blockers).
- F5's "blocked retry" queue (a v2 affordance) keys off `blockers[0]`
  to know which blocker to re-check.
- Operators see one canonical primary blocker per device across
  every UI and audit row. Diagnosing "why did the dashboard show X
  but the device endpoint show Y" reduces to "show me the diff
  between the persisted row's blockers[0] and the just-computed
  blockers[0]" — both are stable.
- Adding a new `predicate_kind` to F2 requires extending the F4
  enum + ordering tuple. The contract test in `tests/contract/`
  catches the omission.
