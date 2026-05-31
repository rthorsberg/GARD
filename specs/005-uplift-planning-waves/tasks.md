# F5 — Tasks

85 tasks across 10 phases. PR slices: **5a** (T001–T020), **5b** (T021–T058), **5c** (T059–T078), **5d** (T079–T085). Each slice is independently green + reviewable.

Status convention: `[ ]` pending · `[x]` done · `[~]` in progress.

## Phase 1 — Foundational (slice 5a)

- [x] **T001** — Author `adr/ADR-0016-wave-state-machine-and-sod.md` covering R-1..R-9.
- [x] **T002** — Add `WaveState` + `ExceptionState` to `gard/models/_enums.py`.
- [x] **T003** — Add `Role.change_approver` to `gard/models/_enums.py`.
- [x] **T004** — Extend `Permission` in `gard/core/rbac.py` with `DRAFT_UPLIFT_WAVE`, `APPROVE_UPLIFT_WAVE`, `READ_UPLIFT`, `MANAGE_EXCEPTION`, `APPROVE_EXCEPTION`; wire all roles.
- [x] **T005** — Extend `gard/core/settings.py` with `uplift_wave_max_devices`, `uplift_change_window_max_hours`, `uplift_change_window_min_minutes`, `uplift_idempotency_ttl_seconds`, `exception_max_lifetime_days`.
- [x] **T006** — Author migration `0009_uplift_planning_waves.py` creating `uplift_plans`, `uplift_waves`, `uplift_wave_devices`, `uplift_exceptions` with all CHECK constraints + indices from data-model.md §1.
- [x] **T007** — ORM `gard/models/uplift_plan.py` (`UpliftPlan`).
- [x] **T008** — ORM `gard/models/uplift_wave.py` (`UpliftWave`).
- [x] **T009** — ORM `gard/models/uplift_wave_device.py` (`UpliftWaveDevice` join).
- [x] **T010** — ORM `gard/models/uplift_exception.py` (`UpliftException`); register all four in `gard/models/__init__.py`.

## Phase 2 — State machine + envelope (slice 5a)

- [x] **T011** — `gard/core/uplift_state_machine.py` — closed transition matrix `WAVE_TRANSITIONS`, `EXCEPTION_TRANSITIONS`, `is_legal_wave_transition(from, to)`, `is_legal_exception_transition(from, to)`, pure-fn `assert_separation_of_duties(drafter, approver, action)`.
- [x] **T012** — Unit tests `tests/unit/test_uplift_state_machine.py` — full truth table for every legal + illegal cell.
- [x] **T013** — Unit tests `tests/unit/test_uplift_separation_of_duties.py` — drafter == approver → raises; drafter ≠ approver → passes; self-rejection allowed.
- [x] **T014** — Extend `gard/core/envelope.py` with `WaveEnvelope`, `PlanEnvelope`, `ExceptionEnvelope`, `build_wave_envelope()`, `build_plan_envelope()`, `build_exception_envelope()`.
- [x] **T015** — Extend `gard/core/envelope.py` `RecommendedActionKind` with F5 kinds; extend `ComplianceReasonKind` with `active_exception`.
- [x] **T016** — Extend `gard/core/recommended_actions.py` with builders for the 5 new F5 kinds.
- [x] **T017** — Extend `tests/conftest.py` `_DATA_TABLES` with the four F5 tables (truncate order: exceptions, wave_devices, waves, plans).
- [x] **T018** — Run alembic upgrade head against the test DB; confirm new tables visible.
- [x] **T019** — `uv run ruff check` + `uv run mypy gard` clean on all foundational + state-machine modules.
- [x] **T020** — Commit + push slice 5a; open draft PR.

## Phase 3 — US1: plans + wave drafting (slice 5b)

- [x] **T021** — `gard/core/uplift_plan_controller.py` — `create_plan()`, `archive_plan()`, `list_plans()`, `get_plan()` + `_emit` audit helpers.
- [x] **T022** — `gard/core/uplift_wave_controller.py` — `draft_wave()` resolving `scope_selector` via F4's latest verdicts; mode=`strict` vs `skip_ineligible` branches.
- [x] **T023** — Idempotency check inside `draft_wave()` (R-4) — lookup by `(plan_id, idempotency_key)` within TTL.
- [x] **T024** — `gard/api/schemas/uplift.py` — Pydantic models matching `contracts/rest-openapi.yaml`: `CreatePlanRequest`, `CreateWaveRequest`, `PlanEnvelope`, `WaveEnvelope`, `PlanList`, `WaveList`, etc.
- [x] **T025** — `gard/api/routers/uplift.py` — endpoints `POST /uplift/plans`, `GET /uplift/plans`, `POST /uplift/plans/{id}/archive`, `POST /uplift/plans/{plan_id}/waves`, `GET /uplift/waves`, `GET /uplift/waves/{id}` with the `Idempotency-Key` header path.
- [x] **T026** — Wire `uplift` router into `gard/api/app.py` `_PHASE3_ROUTERS`.
- [x] **T027** — Integration test `tests/integration/test_us1_draft_wave.py` — create plan, draft wave from `ready_for_uplift` devices, assert 201 + audit row + no lifecycle transition.
- [x] **T028** — Integration test for `mode=strict` ineligible → 422 with `INELIGIBLE_DEVICES_IN_SCOPE`.
- [x] **T029** — Integration test for `mode=skip_ineligible` → 201 with `skipped[]`.
- [x] **T030** — Integration test for empty scope → 422 `EMPTY_WAVE`.
- [x] **T031** — Integration test idempotency replay (same key within 5 min returns same wave id; same key after TTL creates new).
- [x] **T032** — Integration test invalid change window (past, > 24h, < 15m) → 422 `INVALID_CHANGE_WINDOW`.
- [x] **T033** — Integration test target_version not in live catalogue → 422 `TARGET_VERSION_NOT_LIVE`.
- [x] **T034** — Integration test plan archival hides from default listing, returns via `include_archived=true`.
- [x] **T035** — `uv run pytest -q` green; commit.

## Phase 4 — US2: submit / approve / reject / cancel (slice 5b)

- [x] **T036** — `uplift_wave_controller.submit()` — transitions wave to `submitted`; flips every device `ready_for_uplift → uplift_planned → approval_pending`; emits `uplift_wave.submitted`.
- [x] **T037** — `uplift_wave_controller.approve()` — SoD check (R-2); optimistic state guard (R-7); citation persist; device transitions `approval_pending → approved`; emits `uplift_wave.approved` carrying citation.
- [x] **T038** — `uplift_wave_controller.reject()` — same shape as approve but returns devices to `ready_for_uplift`; emits `uplift_wave.rejected`.
- [x] **T039** — `uplift_wave_controller.cancel()` — drafter OR APPROVE_UPLIFT_WAVE holder; only from `draft` or `submitted`; emits `uplift_wave.cancelled`.
- [x] **T040** — `gard/api/routers/uplift.py` — endpoints `POST /uplift/waves/{id}/submit`, `/approve`, `/reject`, `/cancel`.
- [x] **T041** — Integration test happy-path approval (drafter ≠ approver, citation valid).
- [x] **T042** — Integration test self-approval → 403 `SELF_APPROVAL_FORBIDDEN`.
- [x] **T043** — Integration test self-rejection IS allowed; audit row carries `self_rejection=true`.
- [x] **T044** — Integration test re-approve approved wave → 409 `WAVE_STATE_MISMATCH`.
- [x] **T045** — Integration test concurrent approval — two simultaneous POSTs, exactly one wins (R-7).
- [x] **T046** — Integration test citation length bounds (< 20 → 422; > 2000 → 422).
- [x] **T047** — Integration test cancellation by non-drafter without `APPROVE_UPLIFT_WAVE` → 403.
- [x] **T048** — Integration test `WAVE_TRANSITION_FORBIDDEN` for `draft → approved` (must submit first).
- [x] **T049** — Verify exactly one audit row per state transition per device (SC-002).
- [x] **T050** — `uv run pytest -q` green; commit.

## Phase 5 — Wave invalidation hook (slice 5b)

- [x] **T051** — `uplift_wave_controller.invalidate_affected_waves(session, audit_session, *, affected_device_ids, reason)` — finds non-terminal waves containing any of the device ids; transitions to `invalidated`; returns devices to F4 verdict; emits one audit row per wave.
- [x] **T052** — Extend `gard/core/firmware_catalog_controller._reevaluate_compliance_post_reload` to call `invalidate_affected_waves()` after the F4 pass for the same `affected` set.
- [x] **T053** — Integration test — seed a `submitted` wave, inject a new prereq rule that blocks one of its devices, reload catalogue, assert wave is `invalidated` + audit row.
- [x] **T054** — Integration test — target retirement: remove the wave's `target_version` from catalogue → wave invalidated.
- [x] **T055** — Integration test — invalidation returns devices to `ready_for_uplift` (or `blocked` if F4 reverdicts).
- [x] **T056** — Lifecycle transition correctness: device delete attempt on a member of a non-terminal wave → 409 `DEVICE_IN_OPEN_WAVE` (smoke this at the controller level; full endpoint test deferred to device-decommission feature).
- [x] **T057** — Slice 5b commit + push; mark PR ready.
- [ ] **T058** — Slice 5b merge to `005-uplift-planning-waves` long-running branch.

## Phase 6 — US3: exceptions (slice 5c)

- [ ] **T059** — `gard/core/uplift_exception_controller.py` — `file_exception()` validating device is `blocked` and matching blocker exists in the latest F4 row.
- [ ] **T060** — `approve_exception()` — SoD check; flips device `blocked → exception_approved`; emits `uplift_exception.approved`.
- [ ] **T061** — `reject_exception()` + `withdraw_exception()`.
- [ ] **T062** — Lazy expiry sweep — extend `readiness_evaluation_controller.evaluate()` to call `expire_overdue_exceptions(device_id)` at the top; transitions any matching approved-and-expired row to `expired`; emits audit; F4 then evaluates without the exception in play.
- [ ] **T063** — Extend `readiness_evaluation_controller` carve-out logic to surface `state=not_applicable, reasons=[{kind: active_exception, ref_id: <id>}]` when an active exception exists.
- [ ] **T064** — `gard/api/routers/uplift.py` — endpoints for `/uplift/exceptions` GET/POST + `/uplift/exceptions/{id}/{approve,reject,withdraw}`.
- [ ] **T065** — Integration test happy path: blocked device → file exception → second principal approves → F4 reports `not_applicable`.
- [ ] **T066** — Integration test expiry: file + approve with `expires_at = now() + 1s`; sleep; trigger F4 evaluate; assert device returns to `blocked` + audit `uplift_exception.expired`.
- [ ] **T067** — Integration test second exception for same (device, blocker) while first is active → 409 `EXCEPTION_ALREADY_ACTIVE`.
- [ ] **T068** — Integration test justification length bounds (< 20, > 2000).
- [ ] **T069** — Integration test SoD on exception approval (filer == approver → 403).
- [ ] **T070** — Integration test exception withdrawal by filer (allowed in any non-terminal state).
- [ ] **T071** — Integration test synthetic blocker exception (no `blocker_rule_id`, only `synthetic_kind`).
- [ ] **T072** — Verify F4 audit chain still works correctly when exception cancels out blocker.

## Phase 7 — US4: MCP delegates (slice 5c)

- [ ] **T073** — `gard/mcp/tools/create_uplift_wave_draft.py` — read-shaped proposal (R-9); no DB write.
- [ ] **T074** — `gard/mcp/tools/create_exception_review_draft.py`.
- [ ] **T075** — `gard/mcp/tools/get_uplift_plan_summary.py`.
- [ ] **T076** — `gard/mcp/tools/list_open_waves.py`.
- [ ] **T077** — `gard/mcp/tools/list_active_exceptions.py` + `gard/mcp/tools/explain_wave.py`.
- [ ] **T078** — Contract test `tests/contract/test_uplift_mcp_tools.py` — load `contracts/mcp-tools.yaml`, assert each of the 6 delegates exists with matching `TOOL_NAME` + `REQUIRED_PERMISSION` + `invoke()`.

## Phase 8 — Contract lock (slice 5d)

- [ ] **T079** — Contract test `tests/contract/test_uplift_rest_openapi.py` — parses `contracts/rest-openapi.yaml`; asserts every contract path + method + parameter is in `/openapi.json`.
- [ ] **T080** — Schema enum coverage tests — assert all `WaveState`, `ExceptionState`, new `RecommendedActionKind` values, and `active_exception` reason kind appear in served schema (recursive enum walk per F4 pattern).
- [ ] **T081** — Assert the new role `change_approver` is registered with `READ_UPLIFT`, `APPROVE_UPLIFT_WAVE`, `APPROVE_EXCEPTION` and nothing else.
- [ ] **T082** — Run full test suite + lint + mypy; commit slice 5d Part 1.

## Phase 9 — Seed + docs (slice 5d)

- [ ] **T083** — Extend `deploy/scripts/seed.sh` with 3 new F5 sections: draft a wave, submit + approve (using a second-mint token), estate-wide plan summary.
- [ ] **T084** — Update `README.md` Status section + Quickstart snapshot to include F5; update `ROADMAP.md` F5 row to "shipped (PR #5)" and adjust ADR-0016 entry.

## Phase 10 — Polish + sign-off (slice 5d)

- [ ] **T085** — `uv run ruff format .` pass; final `uv run pytest -q && uv run ruff check . && uv run mypy gard` clean; commit; mark PR #5 ready for review; verify CI green; squash-merge to main.

---

### Dependency notes

- T021..T035 (US1) require T001..T020 done.
- T036..T050 (US2) require US1 done.
- T051..T058 (invalidation hook) requires US2 + extends F4 hook — touches `firmware_catalog_controller.py` already extended for F4.
- T059..T072 (exceptions) is independent of US1/US2 in the controller layer (different table) BUT integration tests need F2/F3/F4 to be running, so it's slice 5c (after the wave PR lands).
- T073..T078 (MCP) follows once the controllers stabilize.
- Phase 8–10 are pure polish + locking.
