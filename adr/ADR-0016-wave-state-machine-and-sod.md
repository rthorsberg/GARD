# ADR-0016 — Wave State Machine, Separation of Duties, and Exception Lifecycle

**Status**: Accepted
**Date**: 2026-05-31
**Decision-makers**: GARD core team
**Touches**: F5 (Uplift Planning & Waves), F7+ (Executor — consumer)
**Supersedes**: none
**Superseded by**: none

## Context

F5 introduces two new entities with strict lifecycle semantics:

- `UpliftWave` — a reviewable batch of devices targeted for an uplift, going through `draft → submitted → approved | rejected | cancelled | invalidated`.
- `UpliftException` — an operator-accepted known-risk override for a `blocked` device, going through `pending_review → approved | rejected | withdrawn | expired`.

Both entities cross into "human signed off on this" territory: their approval is the chain-of-custody evidence that justifies a future executor (F7+) actually touching a device. Constitution V mandates that the audit trail alone — without trusting the live API — must be able to re-verify that the approval was legitimate.

Three questions need binding answers before any implementation:

1. **State machine** — what are the legal transitions, and how do we enforce them so no path through the system can bypass them?
2. **Separation of duties** — how do we guarantee that the drafter is not the approver, even if a future internal caller bypasses the API layer?
3. **Exception lifecycle** — how do we handle expiry without a scheduler in v1, and how does the F4 readiness controller respect an active exception?

This ADR locks the answers. The decisions are referenced by R-number from `specs/005-uplift-planning-waves/research.md`.

## Decision

### A. Wave state transition matrix (R-1)

The `UpliftWave.state` enum is **closed** at:

```
draft        # operator drafted; devices not yet committed
submitted    # operator submitted for review; devices transitioned to approval_pending
approved     # reviewer approved with a citation; terminal
rejected     # reviewer (or drafter, as self-withdrawal) rejected with a citation; terminal
cancelled    # drafter or approver cancelled while non-terminal; terminal
invalidated  # system-triggered: F4 reverdict OR target retirement; terminal
```

Legal transitions only:

| From | To | Triggered by |
|---|---|---|
| `draft` | `submitted` | drafter |
| `draft` | `cancelled` | drafter |
| `draft` | `invalidated` | system (F4 reverdict / target retired before submit) |
| `submitted` | `approved` | approver (must differ from drafter — see §B) |
| `submitted` | `rejected` | approver OR drafter (self-rejection allowed) |
| `submitted` | `cancelled` | drafter |
| `submitted` | `invalidated` | system |

`approved`, `rejected`, `cancelled`, `invalidated` are **all terminal**. No "reset" path exists. To "re-do" a wave you draft a new one.

### B. Separation-of-duties enforcement (R-2)

Approval-class transitions (wave approval, exception approval) require the actor's `principal.subject` to differ from the original drafter's / filer's subject. This is enforced at **three layers**:

1. **API layer** (`gard/api/routers/uplift.py`): the router compares subjects before calling the controller. Mismatch → HTTP 403 `SELF_APPROVAL_FORBIDDEN` with a structured error envelope, no DB call.
2. **Controller layer** (`gard/core/uplift_wave_controller.approve`, `gard/core/uplift_exception_controller.approve_exception`): re-checks identity inside the same SQL transaction that flips state. Even if the API check is bypassed by a future internal caller, the controller raises `SelfApprovalForbidden`.
3. **Database layer**: `uplift_waves.ck_uplift_waves_sod` CHECK constraint asserts `approved_by IS NULL OR approved_by <> drafted_by`. Same for `uplift_exceptions.ck_uplift_exceptions_sod`. Any path that bypasses the controller still fails at the DB.

**Self-rejection** is allowed (it is an explicit withdrawal by the drafter). The audit row carries `audit_events.after.self_rejection = true` so reporting tools can distinguish self-rejection from approver-rejection. **Self-cancellation** is allowed for the same reason — a drafter pulling their own draft does not need a second principal.

### C. Exception lifecycle (R-6)

`UpliftException.state` enum:

```
pending_review    # filed; awaiting a different principal's review
approved          # reviewer approved; device flips blocked → exception_approved
rejected          # reviewer declined; device stays blocked
withdrawn         # filer withdrew before review; terminal
expired           # expires_at passed and next F4 evaluate ran; terminal
```

Expiry is **lazy**: the next call to `gard/core/readiness_evaluation_controller.evaluate()` against the device checks `expires_at < now()` for any `state=approved` exception. If true, it:

1. Transitions the exception row to `state=expired` (sets `expired_at = now()`).
2. Emits one `uplift_exception.expired` audit row.
3. Re-computes the F4 verdict without the exception in play (device usually returns to `blocked`).

No cron / Celery / APScheduler is added in v1. Trade-off accepted: a device may sit in `not_applicable` for a few hours past `expires_at` if nothing triggers a re-evaluate. F2 catalogue reloads (typically nightly) trigger a re-eval on every affected device; operators can force a re-eval via `POST /api/v1/readiness/evaluate`. v2 will add a scheduled sweep if real demand surfaces.

While `state=approved` AND `now() < expires_at`, F4's `evaluate()` surfaces:

```json
{
  "state": "not_applicable",
  "reasons": [{"kind": "active_exception", "ref_id": "<exception_id>"}]
}
```

### D. Concurrent transition resolution (R-7)

Every state transition uses an **optimistic state guard** on the UPDATE:

```sql
UPDATE uplift_waves
SET state = :new_state, <state>_at = now(), <state>_by = :subject, ...
WHERE id = :wave_id AND state = :expected_old_state
RETURNING id, state;
```

If `RETURNING` yields zero rows → another caller won the race → controller raises `WaveStateMismatch(expected=..., actual=<fetched>)` → router returns HTTP 409 `WAVE_STATE_MISMATCH`.

The same pattern applies to every transition (`submit`, `approve`, `reject`, `cancel`, `invalidate`) and to exception transitions.

### E. Idempotency on wave creation (R-4)

`POST /api/v1/uplift/plans/{plan_id}/waves` accepts an optional `Idempotency-Key` header (UUID v4, client-generated). When set, the controller looks for an existing wave with the same `(plan_id, idempotency_key)` whose `drafted_at > now() - GARD_UPLIFT_IDEMPOTENCY_TTL_SECONDS` (default 300 = 5 min). On hit, returns the original row (HTTP 200, not 201) with no DB write.

The key is only honoured on wave create. Other state transitions are already idempotent-shaped via the state-machine guard (D): a second `approve` against an `approved` wave returns 409, which is the correct shape.

## Rationale

**Why a closed enum + DB CHECK rather than a Postgres native ENUM type**: We use the same pattern as F2/F3/F4 — a `VARCHAR(32)` column with a CHECK constraint. Reasons: (a) easier to extend in a non-locking ALTER; (b) the application enum (`WaveState`) is the source of truth via `values_callable`; (c) consistent with the rest of the codebase. The cost (slightly larger row, no enum-type optimisation) is negligible at our scale.

**Why three layers of SoD**: A reviewer asking "how do I know self-approval can't happen?" deserves a one-line answer per layer:

- "The router won't call the controller" (defence in depth #1)
- "The controller checks again before SQL" (defence in depth #2)
- "The database itself refuses the row" (defence in depth #3 — the audit-grade answer)

Each layer is independently testable. Removing any one is a documented risk; removing all three would silently degrade the chain of custody.

**Why lazy expiry**: Constitution III — "expired" is a derived state from `expires_at + now`. The persisted `state=approved` row is authoritative *until re-evaluation*; the API surface always recomputes against `now()` on read so callers never see stale `state=approved` past the expiry. The trade-off (operator may see "still not_applicable" for a few hours) is acceptable because F2 catalogue reloads trigger an automatic re-evaluate on the affected devices and operators can force one via the existing F4 endpoint.

**Why optimistic state guard over SELECT FOR UPDATE**: One round-trip vs two, no row-level lock contention under approval bursts. `RETURNING` is atomic — the same UPDATE either takes the row or doesn't.

**Why per-state timestamp columns instead of a `wave_state_history` table**: The `audit_events` chain already captures every transition with full chain-of-custody metadata. The dedicated columns (`approved_at`, `approved_by`, `approval_citation`, etc.) are read-shape accelerators for the common queries ("show me waves approved in Q3"). Duplicating into a parallel relational table doubles writes for zero new audit guarantee.

## Alternatives considered

1. **Postgres native ENUM type for `state`**. Rejected — extending a Postgres ENUM in a future migration requires a lock; the VARCHAR + CHECK pattern is consistent with F2/F3/F4 and trivially extensible.
2. **Per-transition row in a `wave_state_transitions` table**. Rejected — the audit chain already provides this; the relational columns are sufficient for read queries.
3. **Operator-tunable SoD policy (e.g. allow self-approval for certain device classes)**. Rejected — Constitution V mandates uniform chain of custody. Per-deployment SoD weakening would defeat the audit-grade promise.
4. **Scheduler for exception expiry**. Rejected for v1 — adds infra surface (scheduler container, lock table) for a use case operators have not asked for. The lazy sweep is sufficient.
5. **In-memory state-machine library (e.g. transitions)**. Rejected — a dict-of-tuples and a pure function are easier to read, type-check, and unit-test than any library.
6. **Postgres advisory locks for concurrent approval**. Rejected — the optimistic state guard is simpler, lock-free, and exactly as safe.
7. **Body-hash idempotency instead of header**. Rejected — same body legitimately produces a new wave 24h later; the header makes the intent explicit.

## Consequences

- The `WaveState` and `ExceptionState` enums are first-class lifecycle vocabulary across F5. Any future renaming requires a migration that updates the CHECK constraint, the application enum, and a dual-running compatibility window.
- Adding a new state (e.g. v2 `executing`, `executed`, `rolled_back` for F7+) requires: enum value + CHECK constraint relaxation + new transition cells + new `<state>_at`/`<state>_by` columns + audit-event action names. The pattern is well-understood; the cost is a tracked migration, not a redesign.
- The triple-layer SoD makes "can a system_admin self-approve via a service account" an explicit question — and the answer is: **no, the DB CHECK will refuse the row regardless of role**. Sysadmins who need to push something through must either: (a) use a second principal, or (b) explicitly draft + ask another sysadmin to approve.
- F7+ (the executor) consumes F5 by reading the `approved` rows + the audit chain. It never reads any earlier state (`submitted`, `draft`, etc.) because they don't carry the citation. The handoff contract is: "F5 produces `approved` waves with citations; F7 produces `executed` / `failed` / `rolled_back` outcomes referencing the wave id."
- Exception expiry being lazy means reports built on "current state" are always correct (the read recomputes against `now()`), but reports built on a point-in-time snapshot of `state=approved` will include rows whose `expires_at` has already passed. Reporting tools that care about this distinction MUST recompute against `now()` themselves (the seed script's example output illustrates this).
