# F5 — Data Model

## 1. Tables

### 1.1 `uplift_plans`

Top-level grouping. No device list — devices belong to waves.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID v7 (PK) | no | UUID7 — time-ordered. |
| `name` | varchar(200) | no | Free-form operator label. Unique with `archived_at IS NULL`. |
| `description` | text | yes | Markdown allowed, stored verbatim. |
| `created_by` | varchar(255) | no | `principal.subject` of the drafter. |
| `created_at` | timestamptz | no | `default now()`. |
| `archived_at` | timestamptz | yes | When set, plan is hidden from default listings. |
| `archived_by` | varchar(255) | yes | Subject of the archiver. |

**Indexes**: `ix_uplift_plans_created_at_desc`, unique partial on `(lower(name))` where `archived_at IS NULL`.

### 1.2 `uplift_waves`

The reviewable batch. Every state transition writes to its dedicated `<state>_at` + `<state>_by` columns; `state` is the live verdict.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID v7 (PK) | no | |
| `plan_id` | UUID | no | FK → `uplift_plans.id`, ON DELETE RESTRICT. |
| `name` | varchar(200) | no | Unique per plan. |
| `target_version` | varchar(64) | no | Must match a live `FirmwareTarget.target_version` at creation. |
| `target_platform_family` | varchar(64) | no | Captured at draft for invariance. |
| `change_window_start` | timestamptz | no | Future-dated; UTC. |
| `change_window_end` | timestamptz | no | `> start`; `end - start ≤ 24h`. |
| `state` | varchar(32) | no | CHECK `IN ('draft','submitted','approved','rejected','cancelled','invalidated')`. |
| `drafted_by` | varchar(255) | no | Subject. |
| `drafted_at` | timestamptz | no | `default now()`. |
| `submitted_by` | varchar(255) | yes | |
| `submitted_at` | timestamptz | yes | |
| `approved_by` | varchar(255) | yes | |
| `approved_at` | timestamptz | yes | |
| `approval_citation` | varchar(2000) | yes | 20..2000 bytes when set. |
| `rejected_by` | varchar(255) | yes | |
| `rejected_at` | timestamptz | yes | |
| `rejection_citation` | varchar(2000) | yes | |
| `cancelled_by` | varchar(255) | yes | |
| `cancelled_at` | timestamptz | yes | |
| `cancellation_reason` | varchar(500) | yes | 10..500 bytes. |
| `invalidated_at` | timestamptz | yes | |
| `invalidated_reason` | varchar(500) | yes | e.g. `f4_reverdict`, `target_retired`. |
| `idempotency_key` | varchar(64) | yes | UUID v4 string when set. |
| `correlation_id` | varchar(64) | no | Of the create call. |

**Indexes**:

- `ix_uplift_waves_plan_state` on `(plan_id, state)`.
- `ix_uplift_waves_state_drafted_at_desc` on `(state, drafted_at DESC)`.
- `ix_uplift_waves_target_version` on `(target_platform_family, target_version)`.
- unique partial on `(plan_id, idempotency_key)` where `idempotency_key IS NOT NULL`.
- unique on `(plan_id, lower(name))`.

**CHECK constraints**:

- `ck_uplift_waves_state` — state IN enum.
- `ck_uplift_waves_change_window_order` — `change_window_end > change_window_start`.
- `ck_uplift_waves_change_window_max_24h` — `change_window_end - change_window_start <= interval '24 hours'`.
- `ck_uplift_waves_change_window_min_15m` — `change_window_end - change_window_start >= interval '15 minutes'`.
- `ck_uplift_waves_approval_citation_len` — citation NULL or 20..2000 bytes.
- `ck_uplift_waves_rejection_citation_len` — same.
- `ck_uplift_waves_cancellation_reason_len` — reason NULL or 10..500 bytes.
- `ck_uplift_waves_sod` — `approved_by IS NULL OR approved_by <> drafted_by`. **The DB itself enforces R-2.**
- `ck_uplift_waves_terminal_consistency` — when `state IN ('approved','rejected','cancelled','invalidated')`, the matching `<state>_at` column MUST be non-null.

### 1.3 `uplift_wave_devices`

The (wave, device) join, with F4 verdict snapshot.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `wave_id` | UUID | no | FK → `uplift_waves.id`, ON DELETE RESTRICT. Composite PK with `device_id`. |
| `device_id` | UUID | no | FK → `devices.id`, ON DELETE RESTRICT. |
| `position` | int | no | 1-based display order; (`wave_id`, `position`) unique. |
| `readiness_evaluation_ref` | UUID | yes | FK → `readiness_evaluations.id`. Null if F4 row was later pruned. |
| `snapshot_target_version` | varchar(64) | yes | Captured at draft. |
| `snapshot_observed_version` | varchar(64) | yes | Captured at draft. |
| `added_at` | timestamptz | no | `default now()`. |

**Indexes**:

- `ix_uplift_wave_devices_device` on `(device_id)`.
- unique on `(wave_id, position)`.

### 1.4 `uplift_exceptions`

Operator-accepted known-risk override.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | UUID v7 (PK) | no | |
| `device_id` | UUID | no | FK → `devices.id`. |
| `blocker_rule_id` | UUID | yes | FK → `firmware_prerequisite_rules.id`. Null when blocker is a synthetic kind (e.g. `missing_upgrade_path`); in that case `synthetic_kind` carries the predicate kind. |
| `synthetic_kind` | varchar(64) | yes | One of `missing_upgrade_path`, `missing_observation_field` when `blocker_rule_id IS NULL`. |
| `justification` | text | no | 20..2000 bytes. |
| `expires_at` | timestamptz | no | Future-dated; ≤ 365 days from `filed_at`. |
| `state` | varchar(32) | no | CHECK `IN ('pending_review','approved','rejected','expired','withdrawn')`. |
| `filed_by` | varchar(255) | no | |
| `filed_at` | timestamptz | no | `default now()`. |
| `approved_by` | varchar(255) | yes | |
| `approved_at` | timestamptz | yes | |
| `rejected_by` | varchar(255) | yes | |
| `rejected_at` | timestamptz | yes | |
| `withdrawn_by` | varchar(255) | yes | |
| `withdrawn_at` | timestamptz | yes | |
| `expired_at` | timestamptz | yes | Set by the F4 lazy-expiry sweep. |
| `correlation_id` | varchar(64) | no | |

**Indexes**:

- `ix_uplift_exceptions_device_state` on `(device_id, state)`.
- partial unique on `(device_id, coalesce(blocker_rule_id::text, synthetic_kind))` where `state = 'approved'` — only one active exception per (device, blocker) at a time.
- `ix_uplift_exceptions_expires_at` on `(expires_at)` where `state = 'approved'` — supports the lazy sweep.

**CHECK constraints**:

- `ck_uplift_exceptions_state` — enum.
- `ck_uplift_exceptions_blocker_one_of` — exactly one of `blocker_rule_id` / `synthetic_kind` is non-null.
- `ck_uplift_exceptions_justification_len` — `length(justification) BETWEEN 20 AND 2000`.
- `ck_uplift_exceptions_expires_after_filed` — `expires_at > filed_at`.
- `ck_uplift_exceptions_max_lifetime_365d` — `expires_at <= filed_at + interval '365 days'`.
- `ck_uplift_exceptions_sod` — `approved_by IS NULL OR approved_by <> filed_by`.

## 2. New enum surfaces

### 2.1 `WaveState` (Python `StrEnum`)

```python
class WaveState(enum.StrEnum):
    draft = "draft"
    submitted = "submitted"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"
    invalidated = "invalidated"
```

### 2.2 `ExceptionState`

```python
class ExceptionState(enum.StrEnum):
    pending_review = "pending_review"
    approved = "approved"
    rejected = "rejected"
    expired = "expired"
    withdrawn = "withdrawn"
```

### 2.3 `Role.change_approver` (new)

Added to `Role` enum. Carries: `APPROVE_UPLIFT_WAVE`, `APPROVE_EXCEPTION`, `READ_UPLIFT`. Distinct from `system_admin` so an org can grant pure-approval authority without DB superpowers.

### 2.4 `RecommendedActionKind` extension

Five new F5 kinds: `submit_for_approval`, `assign_approver`, `extend_change_window`, `request_exception_review`, `cancel_wave`.

### 2.5 `ComplianceReasonKind` extension

New kind: `active_exception` — F4 surfaces this on `not_applicable` for devices with an approved-and-active exception.

## 3. State transition matrix

### 3.1 Wave (R-1)

| From → To | draft | submitted | approved | rejected | cancelled | invalidated |
|---|---|---|---|---|---|---|
| draft | — | drafter | — | — | drafter | system |
| submitted | — | — | approver (≠drafter) | approver OR drafter | drafter | system |
| approved | — | — | — | — | — | — |
| rejected | — | — | — | — | — | — |
| cancelled | — | — | — | — | — | — |
| invalidated | — | — | — | — | — | — |

Empty cells = forbidden transition → 409 `WAVE_TRANSITION_FORBIDDEN`. Self-approval is a separate 403 `SELF_APPROVAL_FORBIDDEN`.

### 3.2 Exception

| From → To | pending_review | approved | rejected | expired | withdrawn |
|---|---|---|---|---|---|
| pending_review | — | approver (≠filer) | approver | — | filer |
| approved | — | — | — | system (lazy) | filer |
| rejected | — | — | — | — | — |
| expired | — | — | — | — | — |
| withdrawn | — | — | — | — | — |

## 4. Device lifecycle_state transitions driven by F5

| Trigger | From | To |
|---|---|---|
| Wave drafted (US1) | — (no change) | — |
| Wave submitted | `ready_for_uplift` | `uplift_planned` → `approval_pending` |
| Wave approved | `approval_pending` | `approved` |
| Wave rejected / cancelled / invalidated | `approval_pending` OR `uplift_planned` | `ready_for_uplift` (re-runs F4) |
| Exception approved | `blocked` | `exception_approved` |
| Exception expired / rejected / withdrawn | `exception_approved` | `blocked` (re-runs F4) |

## 5. Audit catalogue

Every action below writes exactly one `audit_events` row through the standard append-only role.

| Action | Object type | Triggered by |
|---|---|---|
| `uplift_plan.created` | UpliftPlan | `POST /uplift/plans` |
| `uplift_plan.archived` | UpliftPlan | `POST /uplift/plans/{id}/archive` |
| `uplift_plan.unarchived` | UpliftPlan | `POST /uplift/plans/{id}/unarchive` |
| `uplift_plan.read` | UpliftPlan | every GET on a plan endpoint |
| `uplift_wave.drafted` | UpliftWave | `POST /uplift/plans/{plan_id}/waves` |
| `uplift_wave.submitted` | UpliftWave | `POST /uplift/waves/{id}/submit` |
| `uplift_wave.approved` | UpliftWave | `POST /uplift/waves/{id}/approve` — carries citation + approver |
| `uplift_wave.rejected` | UpliftWave | `POST /uplift/waves/{id}/reject` — carries citation |
| `uplift_wave.cancelled` | UpliftWave | `POST /uplift/waves/{id}/cancel` — carries reason |
| `uplift_wave.invalidated` | UpliftWave | F2/F3/F4 reload hook |
| `uplift_wave.read` | UpliftWave | every GET on a wave endpoint |
| `uplift_exception.filed` | UpliftException | `POST /uplift/exceptions` |
| `uplift_exception.approved` | UpliftException | `POST /uplift/exceptions/{id}/approve` |
| `uplift_exception.rejected` | UpliftException | `POST /uplift/exceptions/{id}/reject` |
| `uplift_exception.withdrawn` | UpliftException | `POST /uplift/exceptions/{id}/withdraw` |
| `uplift_exception.expired` | UpliftException | F4 lazy-expiry sweep |
| `uplift_exception.read` | UpliftException | every GET |

## 6. Cross-feature dependencies

- **F1 audit chain**: F5 emits into `audit_events` via the same append-only role + chain head.
- **F2 catalogue**: wave creation validates `target_version` against the live `FirmwareTarget` for the platform_family.
- **F3 compliance_evaluations**: F5 never reads this directly — F4 is the consumer.
- **F4 readiness_evaluations**: wave creation reads the latest row per device to assert `readiness_state = 'ready_for_uplift'`. Exception approval also writes into F4's evaluation chain (the next F4 evaluate returns `state=not_applicable, reasons=[active_exception]`).
- **`devices.lifecycle_state`**: F5 owns transitions `ready_for_uplift ↔ uplift_planned ↔ approval_pending ↔ approved` and `blocked ↔ exception_approved`. Writes through `Device.lifecycle_state` only inside the wave / exception controllers; the catalog controller already mediates `ready_for_uplift` and `blocked` writes.

## 7. Pruning

Not in v1. Plans + waves + exceptions stay forever. v2 will add a `GARD_UPLIFT_RETENTION_DAYS` env + an admin-callable prune endpoint. The audit chain itself is never pruned (Constitution V).
