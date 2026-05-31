# Feature Specification: MVP Vertical Slice Validation (Cisco ISR1121)

**Feature Branch**: `006-mvp-vertical-slice-cisco-isr1121`
**Created**: 2026-05-31
**Status**: Draft
**Input**: User description: "F6 — MVP Vertical Slice Validation: end-to-end proof for Cisco ISR1121 covering all MVP acceptance criteria from gard-speckit-start/specs/04-mvp-scope.md. Integration tests, sample fixture data, and operator runbook. Not new product code — validates F1–F5 work together."

## Why this feature exists

F1 through F5 each shipped as independently testable vertical slices with their own fixtures, contracts, and integration tests. F6 is the **closure gate**: it proves the assembled product can answer the MVP questions from a single reference device family without inventing new lifecycle semantics.

After F6, a stakeholder can upload a Cisco ISR1121 CSV and immediately ask — via REST, seed script, or (delegate-level) MCP — the six MVP questions:

- What is compliant?
- What is outside target?
- What is unknown?
- What is blocked?
- What is ready for uplift?
- What uplift plan would make devices compliant?

F6 deliberately adds **no execution path** (no firmware push, no adapter invocation). It is validation, fixture, and documentation work only.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Automated MVP vertical slice test (Priority: P1)

A developer merges any change to `main` and CI runs a single integration test suite that exercises the full F1→F5 path for Cisco ISR1121: CSV import with mixed valid/invalid rows, normalization to canonical vendor/model, firmware-target assignment, compliance + readiness evaluation, dry-run uplift plan creation, wave draft + submit + approve with separation-of-duties, and audit/evidence assertions. The suite fails loudly if any MVP acceptance criterion regresses.

**Why this priority**: Without one end-to-end test, feature slices can each be green while the composed product silently drifts. This is the regression harness for the MVP claim.

**Independent Test**: `pytest tests/integration/test_mvp_vertical_slice_isr1121.py` (name illustrative) passes against Postgres with seeded ISR1121 catalog + fixture CSV; asserts all ten MVP acceptance criteria from `04-mvp-scope.md`.

**Acceptance Scenarios**:

1. **Given** the ISR1121 fixture CSV contains valid rows, malformed rows, and duplicate rows, **When** the vertical-slice test imports it, **Then** the import summary reports `rows_total = rows_accepted + rows_rejected + rows_duplicate + rows_manual_review` and at least one accepted ISR1121 device is persisted.
2. **Given** accepted ISR1121 devices and loaded catalog entries, **When** compliance and readiness evaluations run, **Then** at least one device is classified `outside_target`, at least one is `ready_for_uplift` or `blocked`, and summary endpoints return non-zero counts.
3. **Given** a device pool with `ready_for_uplift` ISR1121 members, **When** the test creates a plan, drafts a wave, submits it, and approves it with a different principal, **Then** the wave reaches `state=approved`, devices reach `lifecycle_state=approved`, and audit rows exist for import, evaluation, drafting, submission, and approval.
4. **Given** the vertical-slice test completes, **When** CI runs on `main`, **Then** the suite is part of the standard pytest job and completes within the existing CI time budget (no separate infra).

---

### User Story 2 - Operator runbook against Docker (Priority: P1)

An operator clones the repo, starts Docker Compose, and follows a written runbook that mirrors the automated test manually: import the ISR1121 fixture, reload catalogs, trigger evaluations, inspect compliance/readiness summaries, create and approve a wave, and verify audit/evidence output. Every step has expected sample output so a human can eyeball success without reading test code.

**Why this priority**: MVP demos and onboarding depend on a human-runnable path, not only CI. The runbook is the sales-engineering artifact.

**Independent Test**: A reviewer follows `specs/006-mvp-vertical-slice-cisco-isr1121/quickstart.md` on a clean Docker stack and reaches every checkpoint without undocumented steps.

**Acceptance Scenarios**:

1. **Given** a fresh `docker compose up`, **When** the operator runs the documented seed/import commands for the ISR1121 fixture, **Then** `GET /api/v1/devices` returns normalized Cisco ISR1121 entries.
2. **Given** evaluations have run, **When** the operator calls compliance and readiness summary endpoints, **Then** printed output matches the documented checkpoint examples (counts and at least one per-device line).
3. **Given** a ready device exists, **When** the operator drafts and approves a wave using separate tokens, **Then** the runbook's final checkpoint shows `state=approved` and cites the change ticket string used in the example.

---

### User Story 3 - MCP delegate answers ISR1121 planning questions (Priority: P2)

An AI agent (or contract test acting as one) invokes the existing MCP **delegates** — not live transport — to answer: "How many Cisco ISR1121 devices are outside target?" and "Which ISR1121 devices in Oslo are ready for uplift?" against the ISR1121 fixture database state built by the vertical-slice setup.

**Why this priority**: MVP acceptance criterion #8 explicitly requires MCP to answer an outside-target count for ISR1121. F6 validates delegates against realistic ISR1121 data, closing the ADR-0013 deferral gap at the function level.

**Independent Test**: The vertical-slice test module (or a sibling contract test fed by the same fixture factory) calls `count_devices_outside_target`, `get_ready_for_uplift_devices`, and at least one F5 delegate (`create_uplift_wave_draft` or `get_uplift_plan_summary`) with ISR1121-scoped inputs and receives structurally valid envelopes.

**Acceptance Scenarios**:

1. **Given** ISR1121 devices with mixed compliance states, **When** `count_devices_outside_target` runs with vendor/model filters matching ISR1121, **Then** the count matches the number of devices whose latest compliance envelope is `outside_target`.
2. **Given** at least one ISR1121 device is `ready_for_uplift`, **When** `get_ready_for_uplift_devices` runs with a site filter, **Then** the result includes that device with its readiness envelope attached.
3. **Given** F008 transport is still deferred, **When** contract/delegate tests run, **Then** no test requires a live MCP server socket — delegates only.

---

### User Story 4 - Chain-of-custody evidence across the slice (Priority: P2)

A compliance auditor traces one ISR1121 device from import through approved wave and finds a contiguous audit trail: import job, normalization, compliance evaluation, readiness evaluation, wave lifecycle transitions, and `LifecycleEvidence` rows where the platform emits them. No step relies on out-of-band logs.

**Why this priority**: Constitution Principle V is the binding differentiator. F6 proves the vertical slice is audit-grade, not merely functionally correct.

**Independent Test**: The vertical-slice test queries `audit_events` (and evidence tables where applicable) for one golden device id and asserts minimum event types and monotonic timestamps across the lifecycle.

**Acceptance Scenarios**:

1. **Given** a golden ISR1121 device imported in the test, **When** the test completes the full flow, **Then** audit events exist for import, at least one compliance evaluation, at least one readiness evaluation, and wave approval.
2. **Given** the approval step, **When** audit rows are inspected, **Then** the approver subject differs from the drafter subject and the citation string is preserved verbatim.

---

### Edge Cases

- **Catalog gap**: ISR1121 firmware target / upgrade path / prerequisite rules are missing from `gard-catalog/`. F6 MUST add minimal catalog entries derived from `gard-speckit-start/examples/` so evaluations are meaningful, not `unknown` by omission.
- **Zero ready devices**: If fixture tuning yields no `ready_for_uplift` devices, the vertical-slice test MUST fail setup with an explicit assertion message — not silently skip wave approval.
- **CSV schema drift**: The ISR1121 fixture MUST conform to the F1 import contract (`specs/001-device-import-normalize/contracts/csv-schema.yaml`) or document a deliberate mapping layer in the runbook.
- **Idempotent re-runs**: Re-running the runbook or test factory against the same database MUST not produce duplicate waves (use idempotency keys or isolated test transactions per existing conventions).
- **Non-ISR1121 rows in fixture**: The seed CSV MAY include non-ISR1121 devices to prove filtering; assertions MUST scope to ISR1121 where the MVP criterion requires it.

## Functional Requirements

- **FR-001**: F6 MUST deliver a dedicated ISR1121 fixture CSV, catalog snippets (normalization already exists via `cisco-ios`; firmware target, packages, upgrade paths, prerequisite rules MUST be added under `gard-catalog/`), and a factory/helper that loads them in integration tests.
- **FR-002**: F6 MUST implement one primary integration test (or tightly coupled test module) that asserts all ten MVP acceptance criteria from `gard-speckit-start/specs/04-mvp-scope.md`.
- **FR-003**: F6 MUST NOT introduce new REST endpoints, ORM entities, or lifecycle states — only tests, fixtures, catalog data, scripts, and documentation.
- **FR-004**: F6 MUST include `quickstart.md` as an operator runbook with copy-paste commands, expected output checkpoints, and troubleshooting for the three most common failures (catalog not loaded, no ready devices, self-approval).
- **FR-005**: F6 MUST extend or complement `deploy/scripts/seed.sh` (or add a sibling script invoked from the runbook) with an ISR1121 path distinct from the generic multi-vendor demo fixture.
- **FR-006**: MCP validation MUST exercise existing F3/F4/F5 delegates against ISR1121-scoped data; no new MCP tools unless a delegate is discovered missing for an MVP criterion (then treat as a bug fix, not scope expansion).
- **FR-007**: F6 MUST update `README.md` and `ROADMAP.md` to mark F6 in progress / shipped when complete.
- **FR-008**: All F6 deliverables MUST pass the existing CI pipeline (`ruff`, `mypy`, `pytest`) without new infrastructure.

## Key Entities *(reference only — no new entities)*

F6 validates existing entities end-to-end:

- **Device / DeviceObservation** — imported ISR1121 rows
- **FirmwareTarget / FirmwarePackage / UpgradePath / PrerequisiteRule** — ISR1121 catalog entries
- **ComplianceEvaluation / ReadinessEvaluation** — per-device verdict envelopes
- **UpliftPlan / UpliftWave / Exception** — dry-run planning artefacts
- **audit_events / LifecycleEvidence** — chain-of-custody proof

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of the ten MVP acceptance criteria in `04-mvp-scope.md` are mapped to an automated assertion in the vertical-slice test suite.
- **SC-002**: A new contributor can complete the Docker runbook in under 30 minutes on first attempt (timed during review, not automated).
- **SC-003**: CI pytest job duration increases by no more than 90 seconds versus pre-F6 baseline (vertical slice stays lean).
- **SC-004**: At least one ISR1121 device traverses `imported → classified → outside_target → ready_for_uplift → approval_pending → approved` in the golden-path test without manual intervention.
- **SC-005**: MCP delegate tests for ISR1121 return counts consistent with REST summary endpoints for the same fixture state (zero drift between surfaces).

## Assumptions

- **Reference family**: Cisco ISR1121 (`model_normalized=ISR1121`, platform `ios` / `cisco-ios`) is the sole MVP proof device; other vendors in the fixture are optional noise for filter testing.
- **Catalog source**: `gard-speckit-start/examples/{firmware-targets,upgrade-paths,prerequisite-rules}.yaml` are the authoritative starting point for ISR1121 catalog entries, adapted to the on-disk `gard-catalog/` layout used by F2 reload.
- **Transport deferral**: Live MCP server transport remains out of scope (ADR-0013); delegate-level tests satisfy MVP criterion #8.
- **Execution deferral**: Wave approval is the terminal state; no firmware execution assertions in F6.
- **Environment**: Postgres 16 + Docker Compose, matching existing CI and local dev conventions.
