# F5 — Research: 9 binding decisions

This document locks the design before any code is written. Every decision below is binding for the implementation phase; reversing one requires either an amendment here or a fresh ADR.

## R-1 — Wave state transition matrix

**Decision**: The `UpliftWave.state` enum is closed at `{draft, submitted, approved, rejected, cancelled, invalidated}`. The legal transitions are:

```
draft       → submitted   (drafter submits)
draft       → cancelled   (drafter withdraws)
draft       → invalidated (F4 reverdict / target retired before submit)

submitted   → approved    (approver approves; drafter ≠ approver)
submitted   → rejected    (approver rejects; drafter may = rejecter — self-rejection)
submitted   → cancelled   (drafter withdraws)
submitted   → invalidated (F4 reverdict / target retired during review)

approved    → (terminal)
rejected    → (terminal)
cancelled   → (terminal)
invalidated → (terminal)
```

**Alternatives considered**: An `executed` state was considered for v2; deferred to F7+. An `archived` state on waves was considered and rejected — archival is a plan-level concept; waves are too granular to archive separately.

**Rationale**: 4 terminal states keep the state machine simple to reason about. The 4 mid-states cover every legitimate operational transition. No "in-flight reset" path exists (approved is genuinely terminal) — to "re-do" a wave you draft a new one citing the old one in the description.

## R-2 — Separation-of-duties enforcement

**Decision**: SoD is enforced at **three** layers:

1. **API layer**: the router compares `principal.subject` against `wave.drafted_by` before calling the controller. Mismatch on approval → 403 `SELF_APPROVAL_FORBIDDEN` before any DB call.
2. **Controller layer**: the `approve()` function re-checks identity inside the same transaction that flips state; even if the API check is bypassed (e.g. by a future internal caller), the controller refuses.
3. **Audit layer**: the `uplift_wave.approved` audit row stores both `drafted_by` and `approved_by` subjects; an offline auditor can verify `drafted_by ≠ approved_by` for every approved wave.

Self-rejection IS allowed (it is an explicit withdrawal-by-self) but the audit row carries `audit_events.after.self_rejection=true` so reporting tools can distinguish drafter-rejection from approver-rejection.

**Alternatives considered**: A single check at the controller layer was rejected because the API layer needs to return a clean 403 with a structured error envelope, not just propagate a controller exception.

**Rationale**: Constitution V — chain-of-custody requires that a future auditor can re-verify SoD against the audit log alone, without trusting the API layer was running correctly. The triple-layer enforcement provides that.

## R-3 — Append-only storage shape

**Decision**:

- `uplift_plans` — created once, never deleted. `archived_at` is set to mark archival. Listing endpoints filter `archived_at IS NULL` by default.
- `uplift_waves` — created once, never deleted. Every state transition writes to its dedicated `<state>_at` + `<state>_by` columns (e.g. `approved_at`, `approved_by`, `approval_citation`). `state` is the live column. Older states' timestamps stay populated forever; this gives us the full state history without a separate "wave_state_history" table.
- `uplift_wave_devices` — append-only join table. Once a device is added to a wave at draft time, the row stays even if the wave is later cancelled / invalidated. Captures the F4 verdict snapshot (`readiness_evaluation_ref` FK) for forensics.
- `uplift_exceptions` — created once, never deleted. State transitions populate dedicated `<state>_at` + `<state>_by` columns same as waves.

No row is ever deleted by an operator-callable API in v1. A future pruning concern (>1y old data) is an admin-only DB job; the API surface refuses to delete.

**Alternatives considered**: A separate `wave_state_transitions` history table (one row per transition). Rejected because the audit_events chain already captures it; duplicating into a relational table doubles writes for no read-shape gain (the `<state>_at` columns serve the common queries).

**Rationale**: Constitution V — audit chain is the source of truth for "what happened when". The relational columns are the read-shape accelerator, not a parallel record.

## R-4 — Idempotency on wave submission

**Decision**: `POST /api/v1/uplift/plans/{plan_id}/waves` accepts an optional `Idempotency-Key` header (UUID v4, client-generated). If present, the controller checks for an existing wave with the same `(plan_id, idempotency_key)` created within the last `uplift_idempotency_ttl_seconds` (default 300 = 5 min). On hit, returns the original wave row (HTTP 200, not 201).

The idempotency key is **only** honoured on the create endpoint. State-transition endpoints (`/submit`, `/approve`, etc.) are guarded by the state-machine itself (R-1) — a second `approve` against an `approved` wave returns 409, which is the correct idempotent shape for those.

**Alternatives considered**: Body-hash idempotency (no header needed). Rejected because the same body legitimately produces a new wave (operator drafts the same scope twice 24h apart, intentionally). The header makes intent explicit.

**Rationale**: A double-click in the future UI must not produce two waves with conflicting target_versions. The 5-minute TTL accommodates network flakiness without coupling to long-running automation.

## R-5 — Wave invalidation triggers

**Decision**: Invalidation is fired by three triggers, evaluated inside the F2 reload-sync hook (which already runs F4):

1. **F4 reverdict** — any device in a `draft`/`submitted` wave whose F4 verdict flips from `ready_for_uplift` to anything else. The wave moves to `invalidated`; one audit row cites the device id + the new F4 state.
2. **Target retirement** — wave's `target_version` no longer matches a live `FirmwareTarget` on the platform_family. The wave moves to `invalidated`; audit row cites `target_retired`.
3. **Device decommission** — when (future) F-decom-feature deletes a device that's in a non-terminal wave. v1 doesn't ship this trigger — it surfaces as a 409 on device delete (FR-018 in spec); v2 will add the trigger.

Invalidation is **atomic per wave**: either every device in the wave returns to its underlying F4 verdict, or none does. The transition is wrapped in a transaction with the audit emit.

**Alternatives considered**: Per-device invalidation (keep the wave alive with fewer devices). Rejected — a wave is a reviewed *batch*; mutating its membership post-review breaks the audit chain. v2 may allow operator-driven `update_wave_membership` while in `draft` state; that's out of scope here.

**Rationale**: The wave is the approval unit. If any element of the approval (membership, target, prereqs) changes, the whole approval is stale.

## R-6 — Exception expiry semantics

**Decision**: Exception expiry is **lazy** — the next F4 `evaluate()` call against the device checks `expires_at < now()` and if true:

1. Transitions the exception row to `state=expired` (sets `expired_at = now()`).
2. Emits `uplift_exception.expired` audit row.
3. Re-computes the F4 verdict without the exception in play (so the device usually returns to `blocked`).

No cron / scheduler / background worker is required in v1. The trade-off: a device may sit in `not_applicable` for a few hours past its `expires_at` if nothing triggers a re-evaluate. We accept this because:

- F2 catalogue reloads (typically nightly) trigger a re-eval on all devices.
- Operators can force a re-eval via `POST /api/v1/readiness/evaluate` if needed.
- v2 will add a scheduled sweep if real demand surfaces.

**Alternatives considered**: APScheduler / Celery for expiry. Rejected for v1 — adds infra surface (scheduler container, lock table) for a use case that only matters at the hour-precision boundary, which operators don't care about.

**Rationale**: Constitution III — `expired` is a derived state from `expires_at + now`. The persisted `state=approved` row is still authoritative until re-evaluation; the API surface always recomputes against `now()` on read so callers never see stale `state=approved` past expiry.

## R-7 — Concurrent-approval resolution

**Decision**: Approval uses an **optimistic state guard** on the UPDATE:

```sql
UPDATE uplift_waves
SET state = 'approved', approved_at = now(), approved_by = :subject, approval_citation = :citation
WHERE id = :wave_id AND state = 'submitted'
RETURNING id;
```

If `RETURNING` yields zero rows → another approver won the race → return 409 `WAVE_STATE_MISMATCH` with `{expected: "submitted", actual: <fetched_state>}`.

The same pattern applies to every state transition (`submit`, `reject`, `cancel`, `invalidate`).

**Alternatives considered**: `SELECT … FOR UPDATE` then `UPDATE`. Rejected — adds row-level locking + a second round-trip. The optimistic pattern is exactly as safe (RETURNING is atomic) and cheaper.

**Rationale**: Two reviewers may legitimately both look at a wave and both click approve; the system must produce exactly one approval + one clean 409 for the loser, never two approval rows + a chain-of-custody mess.

## R-8 — Change-window grammar

**Decision**: Change windows are specified as two `TIMESTAMPTZ` values (`change_window_start`, `change_window_end`), validated as:

- Both UTC (input must end in `Z` or carry an explicit offset; the API rejects naive timestamps with 422).
- `change_window_start > now() + 5 minutes` (future-dated; the 5-minute buffer accommodates client clock skew).
- `change_window_end - change_window_start ∈ [15 minutes, 24 hours]`.

**Alternatives considered**: Cron expressions for recurring windows. Rejected — adds parsing complexity for zero v1 use cases (every change window is a one-off).

**Rationale**: The maintenance-window vocabulary across the industry is "start at X, end by Y in a single timezone-explicit format". UTC-only at the API boundary keeps the v1 envelope deterministic; a future UI layer can render to local time without coupling to backend storage.

## R-9 — MCP draft-generator semantics

**Decision**: The two F5 MCP "draft generators" (`create_uplift_wave_draft`, `create_exception_review_draft`) are **read-shaped only** — they NEVER write to the database. Their output is a structured proposal payload that the AI agent can:

1. Present to the operator for review.
2. Submit verbatim through the REST surface (`POST /uplift/.../waves`) to actually create the artefact.

This means an AI agent cannot — by itself, without a human-mediated REST call — create an uplift wave or an exception. The audit trail always records a human principal as the creator.

**Alternatives considered**: Letting MCP write directly (a wave drafted by `agent.<id>`). Rejected — the future executor (F7+) needs an unambiguous chain back to a human approver; an AI-only chain breaks the SoD model.

**Rationale**: Constitution VI — MCP exposes curated tools. The "draft" tool is curated to be a *proposal*, not a *commit*. The 6 MCP tools split cleanly: 2 read-shaped draft proposals + 4 reporting reads. Zero MCP tools mutate state in v1.

---

## Resolution log

All R-1..R-9 are **accepted** as of 2026-05-31. ADR-0016 will reference this document by R-number.
