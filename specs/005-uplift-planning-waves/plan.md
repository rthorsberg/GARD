# F5 — Uplift Planning & Waves: Implementation Plan

**Feature Branch**: `005-uplift-planning-waves`
**Status**: Draft
**Inputs**: `spec.md`, `research.md` (R-1..R-9), `data-model.md`, `contracts/`, `quickstart.md`
**Constitution version**: 1.0.0
**Predecessors**: F4 (`004-readiness-prerequisites`), F3 (`003-compliance-drift-evaluation`), F2 (`002-firmware-catalog`), F1 (`001-device-import-normalize`)
**Successor**: F6 (MVP vertical slice) — F7+ owns execution / rollback.

## Summary

F5 turns F4's `ready_for_uplift` pool into reviewable, approvable, audited change packets. The technical shape is:

- **3 new ORM entities** (`UpliftPlan`, `UpliftWave`, `Exception`) + 1 join table (`UpliftWaveDevice`).
- **2 strict state machines** (wave state + exception state), each with a closed transition matrix + DB CHECK constraint + controller-level guards.
- **8 REST endpoints** across `/api/v1/uplift/{plans,waves,exceptions,...}`.
- **6 MCP delegates** (2 draft generators, 4 reporting tools) — transport deferred per ADR-0013.
- **2 new RBAC permissions** (`DRAFT_UPLIFT_WAVE`, `APPROVE_UPLIFT_WAVE`) + 2 exception permissions + 1 new role (`change_approver`).
- **1 cascading hook extension**: F4's reload-sync hook gains an F5 "wave invalidator" pass that flips affected waves to `invalidated`.
- **1 background sweeper**: exception expiry — runs inline on every F4 evaluation (no separate scheduler in v1).

Technical approach mirrors F3 + F4: pure-function state guards, append-only storage, idempotent endpoints, deterministic envelopes, byte-stable JSON output.

## Technical Context

| Aspect | Choice |
|---|---|
| Runtime | Python 3.12 + FastAPI (no new framework) |
| ORM | SQLAlchemy 2.x (declarative, existing `Base.metadata`) |
| DB | PostgreSQL 16 (existing instance; new tables in `gard_app` schema) |
| Migrations | Alembic 0009 (next free revision) |
| Tests | pytest with the established unit / contract / integration split |
| Performance targets | wave creation p95 < 2s for 500 devices; planning summary p95 < 1s for 5,000 / 200 / 50 |
| Concurrency | DB-level optimistic state guards (`UPDATE … WHERE state = :expected RETURNING …`) |
| Time | All `TIMESTAMPTZ`, UTC-only at the API boundary |
| MCP transport | Deferred — ship delegates only (ADR-0013) |

## Constitution Check

| Principle | F5 adherence |
|---|---|
| I — Governance Before Execution | Every state transition has a closed enum + DB CHECK + controller guard; no path through the system can bypass them. |
| II — Desired vs Actual | Waves are *desired* state. No actual-state mutations happen in F5 (F7+ owns that). |
| III — Unknown is First-Class | Wave invalidation returns devices to F4's verdict (which itself surfaces `not_applicable` rather than silently coercing). Exception expiry triggers a fresh F4 verdict, not a remembered cache. |
| IV — Lifecycle-as-Code | Waves + plans + exceptions are first-class persisted entities; v2 will allow plan-as-YAML import, but v1 stays REST-shaped because the audit chain is the source of truth, not files. |
| V — Evidence/Audit/Explainability | SC-002 + SC-004 are the binding tests: every transition emits exactly one row, every citation is preserved verbatim. |
| VI — Curated MCP Tools | 6 verbs operators *use* (draft, explain, review). No raw CRUD MCP surface. |
| VII — Integration Over Replacement | F7+ handoff is purely state + audit. F5 never imports an executor; F7 never imports an F5 controller. |

All seven principles pass without compromise.

## Project Structure (new + extended files)

**ADR**

- `adr/ADR-0016-wave-state-machine-and-sod.md` (new) — state-machine matrix, R-1 transition guards, R-3 separation-of-duties + R-7 idempotency rules.

**Migrations / ORM / enums**

- `gard/db/migrations/versions/0009_uplift_planning_waves.py` (new)
- `gard/models/uplift_plan.py` (new)
- `gard/models/uplift_wave.py` (new)
- `gard/models/uplift_wave_device.py` (new)
- `gard/models/uplift_exception.py` (new)
- `gard/models/__init__.py` (extend)
- `gard/models/_enums.py` (extend with `WaveState`, `ExceptionState`, new `Role.change_approver`)

**Core**

- `gard/core/uplift_state_machine.py` (new) — pure-function state guards (R-1).
- `gard/core/uplift_wave_controller.py` (new) — drafting, submit, approve, reject, cancel, invalidate.
- `gard/core/uplift_plan_controller.py` (new) — plan CRUD-shape (no devices directly).
- `gard/core/uplift_exception_controller.py` (new) — exception lifecycle + expiry sweep.
- `gard/core/rbac.py` (extend) — add `DRAFT_UPLIFT_WAVE`, `APPROVE_UPLIFT_WAVE`, `READ_UPLIFT`, `MANAGE_EXCEPTION`, `APPROVE_EXCEPTION`; new `change_approver` role.
- `gard/core/settings.py` (extend) — `uplift_wave_max_devices`, `uplift_change_window_max_hours`, `uplift_idempotency_ttl_seconds`, `exception_max_lifetime_days`.
- `gard/core/envelope.py` (extend) — `WaveEnvelope`, `PlanEnvelope`, `ExceptionEnvelope` types.
- `gard/core/recommended_actions.py` (extend) — F5 action kinds (`submit_for_approval`, `assign_approver`, `extend_change_window`, `request_exception_review`).
- `gard/core/firmware_catalog_controller.py` (extend) — reload hook now also calls `uplift_wave_controller.invalidate_affected_waves()` after F4 pass.
- `gard/core/readiness_evaluation_controller.py` (extend) — `not_applicable` reason `active_exception` recognised; exception-expiry sweep runs at the top of `evaluate()`.

**REST**

- `gard/api/schemas/uplift.py` (new) — Pydantic models for plans, waves, exceptions, draft envelopes.
- `gard/api/routers/uplift.py` (new) — 8 endpoints (plans list/create/archive, waves list/create/submit/approve/reject/cancel/get, exceptions list/create/approve/reject/withdraw/get).
- `gard/api/app.py` (extend) — register the new router.

**MCP delegates**

- `gard/mcp/tools/create_uplift_wave_draft.py` (new)
- `gard/mcp/tools/create_exception_review_draft.py` (new)
- `gard/mcp/tools/get_uplift_plan_summary.py` (new)
- `gard/mcp/tools/list_open_waves.py` (new)
- `gard/mcp/tools/list_active_exceptions.py` (new)
- `gard/mcp/tools/explain_wave.py` (new)

**Tests**

- `tests/unit/test_uplift_state_machine.py` (new) — truth table for every transition.
- `tests/unit/test_uplift_separation_of_duties.py` (new) — drafter ≠ approver invariant.
- `tests/unit/test_uplift_exception_expiry.py` (new) — expiry sweep behaviour.
- `tests/contract/test_uplift_rest_openapi.py` (new) — OpenAPI conformance against `contracts/rest-openapi.yaml`.
- `tests/contract/test_uplift_mcp_tools.py` (new) — 6 MCP delegates exist, metadata matches `contracts/mcp-tools.yaml`.
- `tests/conftest.py` (extend) — `_DATA_TABLES` += `uplift_exceptions, uplift_wave_devices, uplift_waves, uplift_plans`.

**Seed / docs**

- `deploy/scripts/seed.sh` (extend) — 3 new F5 sections (draft a wave, submit, approve).
- `README.md` (extend) — F5 quickstart block.
- `ROADMAP.md` (extend) — F5 row flipped to "shipped" on PR merge.

## Complexity Tracking

F5 is the **most complex** feature so far in terms of state-machine surface. The risks tracked:

| Risk | Mitigation |
|---|---|
| State-machine bug allowing approved → submitted | DB CHECK + controller guard + truth-table unit test for every transition (test_uplift_state_machine.py). |
| Self-approval slip past the guard | Identity check happens in controller AND in API layer; integration test seeds drafter + approver as same principal and asserts 403. |
| Wave invalidation cascade producing audit storms | Invalidation runs inside the F2/F3/F4 reload hook which is already bounded; only waves containing affected devices are touched; one audit row per wave (not per device) on invalidation. |
| Exception expiry races with active waves | An exception cannot cover a device whose `lifecycle_state ∈ {uplift_planned, approval_pending, approved}` — enforced at exception creation. |
| Citation injection (HTML / SQL) | Citations are stored as opaque UTF-8 strings; JSONB serialization; no template interpolation anywhere; max length 2000 bytes. |

No complexity is unmanaged — every risk has a paired test in the task list.

## Phase 0: Outline & Research

See `research.md` for the 9 binding decisions:

- **R-1**: Wave state transition matrix (closed enum, every cell decided).
- **R-2**: Separation-of-duties enforcement (controller + API + audit-row evidence).
- **R-3**: Append-only storage shape (one row per wave + one row per (wave, device) snapshot; no UPDATE-in-place except dedicated transition columns).
- **R-4**: Idempotency on wave submission (header-based, 5-minute TTL).
- **R-5**: Wave invalidation triggers (F4 reverdict, F2 catalogue retirement, device decommission).
- **R-6**: Exception expiry semantics (lazy — surfaces at next F4 evaluate, not via cron).
- **R-7**: Concurrent-approval resolution (optimistic state guard on UPDATE).
- **R-8**: Change-window grammar (UTC-only, future-dated, ≤ 24 h apart).
- **R-9**: MCP draft-generator semantics (read-shaped only; no DB write from the AI path).

## Phase 1: Design & Contracts

Outputs:

- `data-model.md` — full ORM shape with column types, FKs, indices, CHECK constraints, audit catalogue.
- `contracts/rest-openapi.yaml` — 8 REST endpoints, request/response schemas, error envelopes.
- `contracts/mcp-tools.yaml` — 6 MCP delegate definitions, input/output schemas, required permissions.
- `quickstart.md` — operator + AI-agent walkthrough showing the full "draft → submit → approve → exception" loop.

## Implementation Strategy

The PR is **too large to land in one chunk**. Recommended split:

| PR slice | Content | Target size |
|---|---|---|
| 5a (this PR) | Phase 1 + 2 (foundational + ORM + RBAC + state machine + unit tests for guards). No router; no MCP. | ~25 tasks |
| 5b | Phase 3 + 4 + 5 (US1 + US2 — full REST surface for plans + waves through approval). | ~30 tasks |
| 5c | Phase 6 + 7 (US3 exceptions + MCP delegates). | ~20 tasks |
| 5d | Phase 8 + 9 + 10 (contract lock + seed + docs + final polish). | ~10 tasks |

Each slice is independently reviewable, has its own integration tests, leaves `main` green. The reviewer can stop at any boundary and the system is functional + auditable.

We will **start with slice 5a** in the implementation phase. The current PR (#5) opens after this design phase commits.

## Task Count Summary

`tasks.md` enumerates **~85 tasks across 10 phases**:

| Phase | Slice | Tasks |
|---|---|---|
| 1 — Foundational | 5a | T001..T010 (ADR + migration + ORM + enums + RBAC + settings) |
| 2 — State machine + envelope | 5a | T011..T020 (pure guards + envelope types + recommended_actions) |
| 3 — US1 plans + wave drafting | 5b | T021..T035 (plan + wave controllers, REST endpoints, integration tests) |
| 4 — US2 submit/approve/reject | 5b | T036..T050 (state transitions, separation-of-duties, citation handling) |
| 5 — Wave invalidation hook | 5b | T051..T058 (F4 hook extension, integration test) |
| 6 — US3 exceptions | 5c | T059..T072 (exception controller, expiry sweep, F4 carve-out) |
| 7 — US4 MCP delegates | 5c | T073..T078 (6 delegate modules + contract test) |
| 8 — Contract lock | 5d | T079..T082 (OpenAPI conformance, schema enum coverage) |
| 9 — Seed + docs | 5d | T083..T084 (seed.sh + README + ROADMAP) |
| 10 — Polish + sign-off | 5d | T085 (ruff format, mypy, final smoke) |

## Open Questions (resolved before T001 starts)

None — every question raised in research.md has a binding decision. ADR-0016 will be written in T001.
