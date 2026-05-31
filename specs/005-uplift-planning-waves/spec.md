# Feature Specification: Uplift Planning & Waves

**Feature Branch**: `005-uplift-planning-waves`
**Created**: 2026-05-31
**Status**: Draft
**Input**: User description: "F5 — Uplift Planning & Waves: convert the pool of `ready_for_uplift` devices into reviewable, approvable, schedulable change packets. Operators draft an `UpliftWave` (a set of devices + target version + change window), reviewers approve or reject with a citation, and an audit-grade record of every approval/rejection ships out. `UpliftPlan` is the parent grouping (one plan can contain many waves). `Exception` is the escape hatch for `blocked` devices whose blocker is accepted as a known risk. v1 is **dry-run only** — no devices are actually upgraded; F5 stops at the `approved` state and hands off to a future executor (F7+)."

## Why this feature exists

After F4, the operator knows which devices are `ready_for_uplift`. F5 answers the next two questions every change-management process asks:

> *"Which N devices should we batch into the same maintenance window? Who reviewed and approved that batch, with what citation, and when?"*

> *"Of the devices F4 marked `blocked`, which ones do we accept anyway as a known risk, who signed off, and on what evidence?"*

Without F5, GARD stops at "here's a green light" — but no change-management process accepts a green light without a name attached to the approval. Constitution V mandates that every transition into a higher-trust lifecycle state carries chain-of-custody evidence; F5 is the feature where lifecycle transitions cross into "human signed off on this" territory.

The transitions F5 owns:

- `ready_for_uplift → uplift_planned` — drafter adds device to a wave
- `uplift_planned → approval_pending` — drafter submits wave for review
- `approval_pending → approved` — reviewer approves
- `approval_pending → ready_for_uplift` — reviewer rejects (device returns to the F4 pool)
- `blocked → exception_approved` — reviewer accepts a documented exception

v1 deliberately stops at `approved`. The next state (`executed` / `failed` / `rolled_back`) is F7's surface. This keeps F5 a paper exercise: every artefact is reviewable, but no SSH session is ever opened.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Draft an uplift wave from ready devices (Priority: P1)

A change manager opens a new uplift plan for Q3 2026. She picks the 50 oslo edge routers currently `ready_for_uplift` to target version `7.8.1`, sets a 04:00–06:00 UTC change window for July 14, and saves the draft. The system stores it as one `UpliftWave` row attached to one `UpliftPlan`, leaves each device's `lifecycle_state` at `ready_for_uplift` (no transition yet — it's still a draft), and emits one `uplift_wave.drafted` audit row.

**Why this priority**: A drafting surface that doesn't yet commit devices is the table stakes for any change-management workflow. Without it, every approval is on a verbal batch of devices that exists nowhere as a record.

**Independent Test**: `POST /api/v1/uplift/plans` followed by `POST /api/v1/uplift/plans/{plan_id}/waves` with a scope selector + target version returns 201 with a wave id; calling `GET /api/v1/uplift/waves/{id}` returns the same device set; `lifecycle_state` on every device is still `ready_for_uplift`; `audit_events` contains exactly one `uplift_wave.drafted` row referencing the wave.

**Acceptance Scenarios**:

1. **Given** 50 devices are `ready_for_uplift` to target 7.8.1, **When** the change manager calls `POST /api/v1/uplift/plans/{plan_id}/waves` with `scope_selector={"region_in": ["oslo"], "platform_family": "iosxr"}`, target_version=7.8.1, and a change window, **Then** the response returns 201 with a wave containing all 50 device ids and `state=draft`.
2. **Given** the wave is still `draft`, **When** the manager calls `GET /api/v1/uplift/waves/{id}`, **Then** every device's `lifecycle_state` is still `ready_for_uplift` (no state mutation during drafting).
3. **Given** the scope_selector resolves to ZERO `ready_for_uplift` devices, **When** the manager calls the wave-creation endpoint, **Then** the response returns 422 `EMPTY_WAVE` and no wave row is persisted.
4. **Given** the scope_selector resolves to devices not in `ready_for_uplift` (mixed pool), **When** the manager calls the endpoint with `mode=strict` (default), **Then** the response returns 422 `INELIGIBLE_DEVICES_IN_SCOPE` listing the rejected device ids and predicate violated (state ≠ ready_for_uplift).
5. **Given** the scope_selector resolves to devices not in `ready_for_uplift` AND `mode=skip_ineligible`, **When** the manager calls the endpoint, **Then** the wave is created with only the eligible subset; the response includes a `skipped[]` array with each rejected device + reason.

---

### User Story 2 - Submit for review and approve a wave (Priority: P1)

After drafting, the change manager submits the wave for review. A second operator (the "approver") opens it, reads the per-device blocker history, the F3 + F4 envelopes, the proposed change window, and clicks approve with a citation ("change ticket CHG-2026-1872"). Every device in the wave transitions `ready_for_uplift → uplift_planned → approval_pending → approved`, each step emitting an `audit_events` row. The drafter and the approver are different principals (separation-of-duties is enforced).

**Why this priority**: Constitution V's chain-of-custody promise hinges on this story. Approval without an immutable record + a citation back to the change-management ticket is the single most important auditability requirement in the entire system.

**Independent Test**: `POST /api/v1/uplift/waves/{id}/submit` transitions devices to `approval_pending`; `POST /api/v1/uplift/waves/{id}/approve` with a `citation` field transitions them to `approved`; `audit_events` contains 4 entries per device (`drafted`, `submitted`, `approval_pending_entered`, `approved`); a self-approval attempt (same principal as drafter) returns 403 `SELF_APPROVAL_FORBIDDEN`.

**Acceptance Scenarios**:

1. **Given** a wave is in `state=draft`, **When** the drafter calls `POST /api/v1/uplift/waves/{id}/submit`, **Then** the wave moves to `state=submitted` and every device transitions to `lifecycle_state=approval_pending` with one audit row per device.
2. **Given** the wave is `submitted` and a different principal calls `POST /api/v1/uplift/waves/{id}/approve` with `citation="CHG-2026-1872"`, **Then** the wave moves to `state=approved`, every device transitions to `lifecycle_state=approved`, and one `uplift_wave.approved` audit row carries the citation string + approver subject.
3. **Given** the drafter and the approver are the **same** principal, **When** the approval call is attempted, **Then** the response returns 403 `SELF_APPROVAL_FORBIDDEN` and no state changes.
4. **Given** a wave is `submitted`, **When** an approver calls `POST /api/v1/uplift/waves/{id}/reject` with `citation="risk_assessment_failed"`, **Then** the wave moves to `state=rejected`, every device returns to `lifecycle_state=ready_for_uplift`, and one `uplift_wave.rejected` audit row is emitted with the citation.
5. **Given** a wave is `approved`, **When** any caller attempts to approve / reject / submit again, **Then** the response returns 409 `WAVE_TERMINAL` (approved + rejected + cancelled are terminal states in v1).
6. **Given** the underlying F4 readiness verdict for a device in an `approval_pending` wave changes to `blocked` (e.g. a new prereq rule was added), **When** the change is detected by the F2 reload hook, **Then** the wave is automatically `state=invalidated` and devices return to F4's verdict; one `uplift_wave.invalidated` audit row cites the device id + reason.

---

### User Story 3 - Record an exception for a blocked device (Priority: P2)

A second-line engineer has a `blocked` device whose `min_ram_mb` blocker is acknowledged: the device is end-of-life next quarter and is explicitly allowed to skip the uplift. He files an `Exception` citing the blocker rule id + a justification + an expiry date (90 days max). The device transitions `blocked → exception_approved`. A reviewer (different principal) approves it. From that point the device appears in F4's `not_applicable` bucket with reason `active_exception` until the expiry, then automatically returns to `blocked`.

**Why this priority**: Without an explicit exception entity, operators paper over `blocked` devices through ad-hoc out-of-band approval (Slack screenshots etc.), which destroys chain-of-custody. v1's exception surface keeps that signal inside GARD.

**Independent Test**: `POST /api/v1/uplift/exceptions` with a device id + blocker_rule_id + justification + expires_at returns 201; the second approver `POST /api/v1/uplift/exceptions/{id}/approve` flips the device to `exception_approved`; F4's `GET /api/v1/devices/{id}/readiness` then returns `state=not_applicable` with reason `active_exception` and references the exception id; after the expiry date passes, the next readiness re-evaluation returns the device to `state=blocked`.

**Acceptance Scenarios**:

1. **Given** device `r3.oslo` is `blocked` by rule `iosxr-min-ram`, **When** the engineer calls `POST /api/v1/uplift/exceptions` with `device_id`, `blocker_rule_id`, `justification`, `expires_at=now+30d`, **Then** the response returns 201 with `state=pending_review` and no lifecycle transition yet.
2. **Given** a pending exception, **When** a different principal approves it, **Then** the device transitions to `exception_approved`, the exception row state becomes `approved`, and F4's per-device endpoint surfaces `state=not_applicable, reasons[].kind=active_exception, reasons[].ref_id=<exception_id>`.
3. **Given** an approved exception, **When** the system clock crosses `expires_at`, **Then** the next F4 evaluation pass returns the device to `state=blocked` and emits one `uplift_exception.expired` audit row.
4. **Given** the same device + blocker rule has an already-active exception, **When** a second exception is filed for the same pair, **Then** the response returns 409 `EXCEPTION_ALREADY_ACTIVE` with the existing exception's id.
5. **Given** the `justification` field is empty or shorter than 20 characters, **When** the exception is created, **Then** the response returns 422 `JUSTIFICATION_TOO_SHORT` (audit-grade evidence requires a real explanation; not a checkbox).

---

### User Story 4 - MCP-callable planning surface (Priority: P2)

An AI agent is helping a planner draft a quarterly uplift plan. The agent calls `create_uplift_wave_draft` with a scope selector + target version, the system returns the draft envelope (with all device ids + each device's F4 readiness snapshot), and the agent can then surface "you have N devices that meet the criteria; here's the platform breakdown" without the planner ever leaving the chat surface.

**Why this priority**: F5 plays the same MCP-deferred-transport game as F3 + F4: the delegate functions ship now, the transport (F008) lands later. Without MCP delegates the AI-agent layer cannot help during draft construction — the slowest, error-prone part of every change cycle.

**Independent Test**: Each of the six F5 MCP tool delegates registers under `gard/mcp/tools/<name>.py` with a `TOOL_NAME`, `REQUIRED_PERMISSION`, and a callable `invoke()` whose input + output Pydantic models match the design-time contract in `contracts/mcp-tools.yaml`. The contract test parses the YAML and exercises each delegate against a mocked session.

**Acceptance Scenarios**:

1. **Given** the F008 MCP transport is not yet shipped, **When** the contract test runs, **Then** all six F5 MCP delegate modules import and pass the metadata + permissions checks.
2. **Given** an AI agent calls `create_uplift_wave_draft` with a scope selector resolving to 50 devices, **When** the delegate runs, **Then** it returns a `proposed_wave` envelope with the 50 device ids + each device's F4 envelope summary; no DB write happens (drafting via MCP is read-shaped — the actual `POST /uplift/.../waves` call is still REST-bound for audit determinism).
3. **Given** an AI agent calls `create_exception_review_draft` for a blocked device, **When** the delegate runs, **Then** it returns a structured exception draft (device id + blocker rule + suggested expiry) that a human reviewer can submit verbatim through the REST surface.

---

### Edge Cases

- **Device removed mid-wave**: A device in an `approval_pending` wave gets deleted via the (future) device-decommission flow. v1: deletion of a device with `lifecycle_state ∈ {uplift_planned, approval_pending, approved}` returns 409 `DEVICE_IN_OPEN_WAVE`. Operator must cancel the wave first.
- **Target version changes mid-wave**: F2's catalogue reloads with a new `FirmwareTarget` for the wave's platform, retiring the wave's `target_version`. The wave auto-`invalidates`; devices return to F4's verdict (which may also have changed).
- **F4 reverdict during approval**: A device in an `approval_pending` wave flips to `blocked` due to a new prereq rule. The reload-sync hook (extends F4's, which extends F3's) marks the wave `invalidated` and emits an audit row with the offending rule id.
- **Concurrent approvals**: Two reviewers approve a wave simultaneously. DB transaction + state-check guards mean exactly one approval wins; the other gets 409 `WAVE_STATE_MISMATCH` (`expected=submitted, actual=approved`).
- **Cancellation by drafter**: The drafter can `cancel` a wave only while it is in `draft` or `submitted` state. After approval, the wave is terminal — a future "rollback" surface is F7+.
- **Empty plan**: A plan with zero waves is allowed (operators draft plans before knowing the device pool). Plans never carry devices directly — only waves do.
- **Plan archival**: Plans never delete in v1 (chain-of-custody). Operators can `archive` a plan (sets `archived_at`), which hides it from default listings but keeps every audit row queryable.
- **Self-rejection**: A drafter rejecting their own wave is allowed (it's an explicit withdrawal). The audit row distinguishes self-rejection from approver-rejection via `actor == drafter` flag.
- **Citation governance**: Approval citations are free-form strings (a change-ticket id, a URL, a multi-line justification). v1 enforces 20 ≤ len ≤ 2000 bytes; no parsing.

## Functional Requirements

- **FR-001**: The system MUST expose `UpliftPlan`, `UpliftWave`, and `Exception` as first-class entities, each with a strict state machine, append-only audit trail per state transition, and read-only API surfaces.
- **FR-002**: `UpliftWave.state` MUST follow the closed enum `{draft, submitted, approved, rejected, cancelled, invalidated}` with only these transitions allowed: `draft→submitted`, `draft→cancelled`, `submitted→approved`, `submitted→rejected`, `submitted→cancelled`, `submitted→invalidated`, `approval_pending wave → invalidated`. Any other transition returns 409.
- **FR-003**: Wave creation MUST resolve its `scope_selector` against the F4 `readiness_evaluations` "latest per device" view AND verify every resolved device is in `lifecycle_state=ready_for_uplift`. Mixed scopes are accepted only when `mode=skip_ineligible` is set; default `mode=strict` rejects with 422.
- **FR-004**: Wave creation MUST require a non-null `target_version`, a non-empty `change_window_start` + `change_window_end` (UTC, future-dated, ≤ 24 h apart), and a non-empty `name` (1..200 chars, unique per parent plan).
- **FR-005**: `POST /api/v1/uplift/waves/{id}/submit` MUST be callable only by a principal holding `DRAFT_UPLIFT_WAVE` and only against `state=draft`.
- **FR-006**: `POST /api/v1/uplift/waves/{id}/approve` MUST be callable only by a principal holding `APPROVE_UPLIFT_WAVE`, only against `state=submitted`, AND the approver's `subject` MUST differ from the original drafter's `subject` (separation-of-duties, FR-013).
- **FR-007**: Approval MUST require a `citation` field, 20 ≤ len ≤ 2000 bytes UTF-8. The citation is stored verbatim on the `uplift_waves.approval_citation` column AND on the `audit_events.after.citation` JSONB.
- **FR-008**: Approving a wave MUST atomically transition every device in the wave from `lifecycle_state=approval_pending` to `lifecycle_state=approved` AND emit one `uplift_wave.approved` audit row carrying `device_count`, `target_version`, `citation`, `approver_subject`.
- **FR-009**: Wave invalidation MUST be triggered automatically when any device in a `submitted` or `draft` wave loses its `ready_for_uplift` status (via F4 reverdict) OR when the wave's target_version no longer exists in F2's live catalogue. Invalidation returns devices to their underlying F4 verdict and emits one `uplift_wave.invalidated` audit row with the trigger reason.
- **FR-010**: `Exception` MUST carry `device_id`, `blocker_rule_id`, `justification` (20..2000 bytes), `expires_at` (UTC, future-dated, ≤ 365 days from creation), and `state ∈ {pending_review, approved, rejected, expired, withdrawn}`.
- **FR-011**: Exception approval MUST be subject to the same separation-of-duties as wave approval (approver ≠ filer).
- **FR-012**: F4's readiness controller MUST treat an `approved` exception as a not_applicable carve-out: `state=not_applicable, reasons=[{kind=active_exception, ref_id=<exception_id>}]`. After `expires_at`, the next F4 evaluation pass MUST return the device to its computed verdict and emit `uplift_exception.expired`.
- **FR-013**: Self-approval (drafter == approver) MUST be rejected with HTTP 403 `SELF_APPROVAL_FORBIDDEN`. Self-rejection (drafter == rejecter) MUST be allowed (an explicit withdrawal) but recorded as `audit_events.after.self_rejection=true`.
- **FR-014**: `GET /api/v1/uplift/plans` MUST support filters `state`, `region`, `platform_family`, pagination via opaque page tokens (same shape as F3/F4), and a default of 50 / max 500 per page.
- **FR-015**: `GET /api/v1/uplift/waves` MUST support filters `plan_id`, `state`, `target_version`, `region`, `site`, `platform_family`, and the same pagination shape.
- **FR-016**: `GET /api/v1/uplift/waves/{id}` MUST return the full wave envelope: state, drafter, change window, target version, device list (each with last-known F4 envelope summary), audit-event count, and the persisted approval citation when present.
- **FR-017**: Wave creation MUST emit `uplift_wave.drafted`. Every state transition MUST emit exactly one audit row of the form `uplift_wave.<new_state>` (submitted/approved/rejected/cancelled/invalidated) — never zero, never two.
- **FR-018**: Wave + plan deletion is NOT supported in v1. Plans support `archive`/`unarchive`; waves support `cancel`. Both write to dedicated columns + emit audit rows; the row itself stays. Devices in archived plans / cancelled waves are eligible to participate in new waves.
- **FR-019**: The system MUST expose six MCP tool delegates: `create_uplift_wave_draft`, `create_exception_review_draft`, `get_uplift_plan_summary`, `list_open_waves`, `list_active_exceptions`, `explain_wave`. The first two are *draft generators* (no DB writes); the latter four are read-shaped reporting tools.
- **FR-020**: RBAC: `DRAFT_UPLIFT_WAVE` (lifecycle_manager+), `APPROVE_UPLIFT_WAVE` (system_admin OR a new `change_approver` role), `READ_UPLIFT` (viewer+), `MANAGE_EXCEPTION` (lifecycle_manager+), `APPROVE_EXCEPTION` (system_admin OR change_approver).
- **FR-021**: All F5 endpoints MUST emit `uplift.read` audit rows on every GET (chain-of-custody requirement for planning artefacts is the same as for compliance + readiness).
- **FR-022**: All envelopes MUST carry the standard explainable surface (`state`, `summary`, `reasons[]`, `recommended_actions[]`, `confidence`, `correlation_id`, `as_of`).
- **FR-023**: Performance: `GET /api/v1/uplift/plans/summary` (estate-wide counters) MUST return p95 < 1s for 5,000 devices / 200 waves / 50 plans. Wave creation MUST return p95 < 2s for a 500-device wave.
- **FR-024**: Determinism: device ordering inside a wave envelope MUST be stable (`hostname asc, device_id asc`). Wave ordering inside a plan envelope MUST be stable (`created_at asc, wave_id asc`).
- **FR-025**: Idempotency: re-submitting the same wave (idempotency key) within 5 minutes MUST return the original wave row, not a duplicate.
- **FR-026**: `POST /api/v1/uplift/waves/{id}/cancel` MUST be callable only by the drafter OR by an `APPROVE_UPLIFT_WAVE` holder, only against `state ∈ {draft, submitted}`, and MUST require a `reason` field (10..500 bytes).

## Key Entities

- **UpliftPlan**: top-level grouping for one operator-defined "campaign" (e.g. "Q3 2026 edge refresh"). Fields: `id`, `name`, `description`, `created_by`, `created_at`, `archived_at` (nullable), `archived_by`, plus standard audit columns. No device list directly — devices belong to waves.
- **UpliftWave**: one reviewable, approvable batch within a plan. Fields: `id`, `plan_id`, `name` (unique per plan), `target_version`, `change_window_start`, `change_window_end`, `state` (enum FR-002), `drafted_by`, `drafted_at`, `submitted_by`, `submitted_at`, `approved_by`, `approved_at`, `approval_citation`, `rejected_by`, `rejected_at`, `rejection_citation`, `cancelled_by`, `cancelled_at`, `cancellation_reason`, `invalidated_at`, `invalidated_reason`, `idempotency_key` (nullable).
- **UpliftWaveDevice**: join table — one row per `(wave_id, device_id)` capturing the snapshot of F4's readiness verdict at draft time. Fields: `wave_id`, `device_id`, `position` (display order), `readiness_evaluation_ref` (FK into F4), `snapshot_target_version`, `snapshot_observed_version`. Append-only.
- **Exception**: one row per `(device_id, blocker_rule_id)` accepted-known-risk override. Fields: `id`, `device_id`, `blocker_rule_id` (FK into F2 `firmware_prerequisite_rules`), `justification`, `expires_at`, `state` (enum FR-010), `filed_by`, `filed_at`, `approved_by`, `approved_at`, `rejected_by`, `rejected_at`, `withdrawn_by`, `withdrawn_at`, `expired_at`.

## Success Criteria

- **SC-001**: Estate-wide planning dashboard returns wave + plan counters p95 < 1s on a synthetic 5,000-device / 200-wave fixture.
- **SC-002**: Every state transition (draft → submitted → approved/rejected/invalidated) emits exactly one audit row per device per wave-level transition; total audit-row count == device_count × transition_count.
- **SC-003**: Self-approval test (drafter == approver) returns 403 for every wave + every exception; never a transient slip.
- **SC-004**: Approval citation is preserved verbatim on both the wave row AND the audit row; the chain-of-custody assertion `wave.approval_citation == audit_events.after.citation` holds for every approved wave.
- **SC-005**: Wave invalidation via F4 reverdict happens automatically — no operator polling. The integration test seeds a wave then injects a new prereq rule and asserts the wave is `invalidated` within one reload pass.
- **SC-006**: Exception expiry is automatic; the integration test seeds an exception with `expires_at = now() - 1m` and asserts the next F4 evaluation transitions the device back to `blocked`.
- **SC-007**: Idempotency: repeated `POST /uplift/.../waves` with the same `Idempotency-Key` header within 5 minutes returns the original wave row (same id, same drafted_at).
- **SC-008**: ≥ 90% unit-test coverage on the controller; 100% predicate coverage on the state-machine guards.
- **SC-009**: Determinism — re-running the contract suite against a fresh fixture returns identical envelope JSON for every wave + plan + exception read.

## Assumptions

- F4's `readiness_evaluations` table is the single authoritative source of "is this device safe to uplift now". F5 never re-derives readiness — it reads.
- F2's `firmware_targets` + `firmware_packages` remain the source of truth for `target_version`. A wave's `target_version` must match a live target; F2 catalogue invalidation cascades to F5.
- F1's `audit_events` chain (via `audit_chain_heads`) provides the immutable chain-of-custody record. F5 emits into the same chain; no separate F5 audit table.
- The MCP transport (F008) is still deferred — F5 ships delegates only, mirroring the F3 + F4 pattern (ADR-0013).
- Constitution VI (curated tools): F5 MCP tools surface verbs operators *care about* (`create_uplift_wave_draft`, `explain_wave`), not raw CRUD on every column.
- Constitution VII (integration over replacement): the future executor (F7+) consumes the `approved` state by reading F5's tables — F5 does not embed any executor logic. The handoff is purely the lifecycle_state transition + the audit chain.
- Time discipline: every timestamp is `TIMESTAMPTZ` stored UTC; change windows are explicitly UTC-only (operators provide local-time inputs through the future UI layer, not the v1 API).
- ADR-0016 will formalize the wave state-machine + the separation-of-duties enforcement matrix; the placeholder slot is already reserved in ROADMAP.md.
