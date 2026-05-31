# F4 — Readiness & Prerequisites: Implementation Tasks

**Generated**: 2026-05-31 by `/speckit-tasks`
**Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md)
| **Data model**: [data-model.md](./data-model.md) | **Contracts**: [contracts/](./contracts/)

**Conventions** (carried over from F3):
- `[P]` — parallelisable (different files, no dependency on an unfinished task)
- `[US1]` / `[US2]` / `[US3]` — task belongs to a user-story phase
- Test tasks are inline (F3 PR #3 lesson — inline tests shipped clean, integration-test backlog stayed zero)

---

## Phase 1 — Setup

- [ ] T001 [P] Add ADR-0015 stub at `adr/ADR-0015-readiness-verdict-precedence.md` capturing R-1 (severity + predicate-kind precedence), R-2 (append-only storage), R-3 (controller composition).
- [ ] T002 Verify migration sequence: confirm `0007_compliance_evaluations.py` is latest head; `0008_readiness_evaluations.py` is the new head.

## Phase 2 — Foundational (blocks all user stories)

- [ ] T003 [P] Add permissions `READ_READINESS` (viewer+, lifecycle_manager+, mcp_client+, system_admin+) and `RUN_READINESS_EVAL` (lifecycle_manager+, system_admin+) to `gard/core/rbac.py`.
- [ ] T004 [P] Add settings `readiness_stale_days: int = 30` and `readiness_upgrade_weight_cap: int = 1000` to `gard/core/settings.py`; bound `>= 1`; document env vars.
- [ ] T005 [P] Extend `gard/core/envelope.py`: add `ReadinessState` Literal, `BlockerPredicateKind` Literal, `Blocker` Pydantic model, `ReadinessEnvelope` Pydantic model, `build_readiness_envelope()` helper. Widen the existing `RecommendedActionKind` Literal with the 5 new F4 kinds (`schedule_uplift_wave`, `hardware_refresh`, `license_acquire`, `firmware_intermediate_step`, `import_observation`).
- [ ] T006 [P] Extend `gard/core/recommended_actions.py` with the 5 new builder functions; update `build_actions_for(...)` to dispatch on the F4 blockers as well.
- [ ] T007 Create `gard/db/migrations/versions/0008_readiness_evaluations.py`: implements the table schema from data-model.md §1.1 including all CHECK constraints, FK relationships (RESTRICT for devices, SET NULL for `compliance_evaluation_ref`), and four indices (`(device_id, evaluated_at DESC)`, partial `(readiness_state)`, partial expression on `blockers->0->>'predicate_kind'`, `(evaluated_at DESC)`). Include downgrade.
- [ ] T008 Create `gard/models/readiness_evaluation.py`: SQLAlchemy 2.x ORM model matching the migration; register in `gard/models/__init__.py`.

## Phase 3 — US1 (P1): Estate-wide readiness dashboard

**Story goal**: A capacity planner calls `GET /readiness/summary` and sees per-state counters + top blocker categories across the whole estate in <1s p95.

**Independent test criterion**: Against the seeded 5-device fixture set, the summary returns counters that sum to the F3 `outside_target_count` and `top_blocker_categories[]` matches the ground truth from the per-device endpoint.

### US1 — Tests first

- [ ] T009 [P] [US1] `tests/unit/test_prereq_predicates.py`: pure-function truth table for each of the 9 predicate kinds (one positive + one negative per kind, 18 cases minimum); test the deferred `tagged_with` returns a recommended-severity blocker; test missing-input cases for the predicates that depend on observation fields.
- [ ] T010 [P] [US1] `tests/unit/test_readiness_precedence.py`: assert R-1's severity + predicate-kind ordering; assert `primary_blocker_of(blockers)` resolves multi-blocker devices deterministically; lock the canonical `BLOCKER_PREDICATE_ORDER` constant.
- [ ] T011 [P] [US1] `tests/integration/test_us1_readiness_summary_endpoint.py`: walk US1 Acceptance Scenarios (summary returns counters; filter narrows result; reload+resync changes counts without per-device call).

### US1 — Implementation

- [ ] T012 [P] [US1] `gard/core/prereq_predicates.py`: one pure function per `predicate_kind` (9 total: `min_ram_mb`, `min_disk_mb`, `min_current_version`, `hardware_revision_in`, `license_present`, `intermediate_version_required`, `not_in_state`, `region_in`, `tagged_with`). Plus `BLOCKER_PREDICATE_ORDER` tuple + `primary_blocker_of(blockers)` helper.
- [ ] T013 [US1] `gard/core/readiness_evaluation_controller.py`: implements `evaluate(session, audit_session, device_id, actor)` per R-3 pipeline; calls `compliance_evaluation_controller.latest_evaluation_for()`, branches on F3 state, runs predicates, calls `upgrade_path_graph.find_chain()`, composes envelope (sorted per R-1, R-7), idempotency-checks against latest row (R-5), INSERTs new row + emits `readiness.evaluated` audit only on diff. Implements `evaluate_many(device_ids, ...)` returning `(evaluated_count, unchanged_count, not_applicable_count)`. Implements `fetch_summary(...)` and `fetch_device_list(...)` mirroring F3's read-paths. Depends on T007, T008, T012.
- [ ] T014 [P] [US1] `gard/api/schemas/readiness.py`: Pydantic models `SummaryResponse`, `ReadinessDeviceRow`, `ReadinessDeviceList`, `EvaluateRequest`, `EvaluateResponse` per `contracts/rest-openapi.yaml`; `extra="forbid"` throughout; `EvaluateRequest` keeps F3's mutually-exclusive `device_ids`/`scope_selector` validator.
- [ ] T015 [US1] `gard/api/routers/readiness.py` part 1: `GET /api/v1/readiness/summary` with optional filters; serves from DISTINCT-ON query; emits `readiness.read` audit; auth `READ_READINESS`. Register router in `gard/api/app.py`'s `_PHASE3_ROUTERS`. Depends on T003, T013, T014.

## Phase 4 — US2 (P1): Explainable per-device verdict

**Story goal**: A field engineer hits `GET /devices/{id}/readiness` and gets a full envelope with cited blockers + recommended actions.

**Independent test criterion**: Each seeded device returns an envelope whose `state`/`blockers`/`recommended_actions` match the per-device truth table in `quickstart.md` §1.

### US2 — Tests first

- [ ] T016 [P] [US2] `tests/unit/test_readiness_envelope.py`: SC-004 determinism — same inputs → byte-identical envelope (modulo `correlation_id`, `as_of`, `evaluation_id`); blockers + actions sort stably.
- [ ] T017 [P] [US2] `tests/integration/test_us2_explainable_readiness.py`: walk US2 Acceptance Scenarios; r1.oslo returns `blocked` + missing_upgrade_path or min_ram_mb; r4.bergen returns `not_applicable`; r3.oslo returns `not_applicable` (no_target_resolved); stale F3 row returns 409.

### US2 — Implementation

- [ ] T018 [US2] `gard/api/routers/readiness.py` part 2: `GET /api/v1/devices/{device_id}/readiness` — calls controller's `evaluate()` (so a not-yet-evaluated device gets a fresh row on first read); auth `READ_READINESS`; emits `readiness.read` audit; raises 409 `READINESS_INPUT_STALE` per R-8. Depends on T015.

## Phase 5 — US1+US2 finishing surface: bulk list + trigger

- [ ] T019 [P] `tests/integration/test_readiness_devices_list.py`: pagination + every filter combination (state, blocker_kind, region, site, platform_family, vendor_normalized).
- [ ] T020 [P] `tests/integration/test_readiness_evaluate_trigger.py`: happy path + 413 `EVALUATION_TOO_LARGE` + 400 missing-both-or-both-given + bounded scope_selector.
- [ ] T021 `gard/api/routers/readiness.py` part 3: `GET /api/v1/readiness/devices` (list) and `POST /api/v1/readiness/evaluate` (trigger). Trigger uses F2's `scope_selector.evaluate()` to resolve device sets; refuses sets > cap with structured 413. Emits `readiness.evaluation_triggered` audit. Depends on T013, T015, T018.

## Phase 6 — Reload→F4 sync (R-6 implementation)

- [ ] T022 [P] `tests/integration/test_post_reload_readiness_sync.py`: trigger a catalog reload that touches a prereq rule's `applies_to`; assert exactly the affected devices receive new `ReadinessEvaluation` rows; assert unaffected devices do not.
- [ ] T023 Extend `gard/core/firmware_catalog_controller._reevaluate_compliance_post_reload`: after the existing F2→F3 call inside the loop, call `readiness_evaluation_controller.evaluate` for the same device id. Same actor, same correlation_id. Wrap in `try/except` (mirror F3 pattern). Compute set3 (devices whose facts match the `applies_to` of any touched prereq rule) and union into `affected`.

## Phase 7 — US3 (P2): MCP tool contracts + delegates

**Story goal**: Four read-only MCP tools published as contracts and implemented as REST-parity delegates. Transport remains deferred to F008 per ADR-0013.

### US3 — Tests first

- [ ] T024 [P] [US3] `tests/contract/test_readiness_mcp_tools.py`: parse `contracts/mcp-tools.yaml`; assert each tool has non-empty `input_schema`, `output_schema`, `auth`; assert `auth` matches a `Permission` attribute name.
- [ ] T025 [P] [US3] `tests/integration/test_us3_readiness_mcp_parity.py`: per-tool parity — each tool's output matches the REST equivalent's data (modulo correlation_id) for the same filter set.

### US3 — Implementation

- [ ] T026 [P] [US3] `gard/mcp/tools/get_readiness_summary.py`: delegate calls into `readiness_evaluation_controller.fetch_summary()` directly (NOT the REST router).
- [ ] T027 [P] [US3] `gard/mcp/tools/list_blocked_devices.py`: capped at 500 items.
- [ ] T028 [P] [US3] `gard/mcp/tools/explain_blockers.py`: single-device version of the readiness envelope.
- [ ] T029 [P] [US3] `gard/mcp/tools/get_ready_for_uplift_devices.py`: F5's primary upstream consumer.

## Phase 8 — REST contract lock + OpenAPI

- [ ] T030 [P] `tests/contract/test_readiness_rest_openapi.py`: parse `contracts/rest-openapi.yaml`; for every path × method, assert the generated `/openapi.json` carries the same path, parameter set, request schema, and response schemas.
- [ ] T031 Verify `tests/contract/test_compliance_rest_openapi.py` still passes after F4 widens the `RecommendedActionKind` enum. The F3 served schema MUST grow the new F4 action kinds — that's a feature.

## Phase 9 — Seed + dev workflow

- [ ] T032 [P] Extend `deploy/scripts/seed.sh` to invoke `POST /api/v1/readiness/evaluate` after the F3 walk, then print the per-device readiness table from `quickstart.md` §1.
- [ ] T033 [P] (Optional) Add 1–2 new prerequisite YAML fixtures under `gard-catalog/firmware/prerequisites/` to exercise `min_ram_mb` and `min_disk_mb` blockers in the seed walk.

## Phase 10 — Polish & cross-cutting

- [ ] T034 [P] Performance smoke: `tests/perf/test_readiness_summary_p95.py` (marked `pytest.mark.perf`, excluded from default `pytest -q`); synthesise 5,000 devices + 50 prereq rules; assert summary endpoint p95 < 1s.
- [ ] T035 [P] Update `README.md` Status section: F4 status → "shipped"; quickstart additions per F4 quickstart.md.
- [ ] T036 [P] Update `ROADMAP.md`: F4 row → "shipped (PR #N)"; ADR-0015 listed as shipped.
- [ ] T037 Run `/speckit-analyze` cross-artefact consistency pass; fix any drift.
- [ ] T038 Run `make lint && make test`; CI green before marking PR ready for review.

---

## Dependencies

```
Setup (T001-T002)
   ↓
Foundational (T003-T008)
   ↓
   ├── US1 tests (T009-T011)  ─┐
   ├── US2 tests (T016-T017)   │  (all test files independent)
   └── US3 tests (T024-T025)   │
                               ↓
   ┌── US1 impl (T012-T015) ──→ Phase 5 (T019-T021)
   │       ↑                        ↑
   │       T013 (controller)        │
   │       ↑                        │
   └── US2 impl (T018) ─────────────┘
           ↑
           T013

   Phase 6 (T022-T023) — depends on T013
   Phase 7 (T026-T029) — depend on T013
   Phase 8 (T030-T031) — depends on T015, T018, T021
   Phase 9 (T032-T033) — depend on T015, T018, T021
   Phase 10 polish (T034-T038) — depends on everything
```

## Parallel execution examples

**Wave 1 (after Foundational lands)**: T009, T010, T011, T012, T014, T016, T017, T024, T025, T030 can all start in parallel.

**Wave 2**: T013 lands → T015, T018, T021, T026-T029 unblock.

**Wave 3**: T021 ships → T022, T023, T030, T032, T033 parallelizable.

## Implementation strategy — MVP

MVP for F4 is **US1 only** (Phases 1, 2, 3, plus T022-T023 for reload-sync). That's T001..T015 + T022..T023 = 15 tasks. Ships as draft PR #4 with the summary endpoint live, explainable verdict deferred to a follow-up slice.

Recommended: ship **US1 + US2** together (Phases 1-6) as the first reviewable PR; pick up US3 + polish in a follow-up. The two P1 stories are tightly coupled by the controller and shipping one without the other leaves a half-built envelope (same lesson as F3 PR #3).

## Task count summary

| Phase | Tasks | Notes |
|---|---|---|
| 1 Setup | 2 | ADR + scaffolding |
| 2 Foundational | 6 | Migration, ORM, RBAC, settings, envelope extension, actions extension |
| 3 US1 | 7 | 3 tests + 4 impl (summary endpoint MVP) |
| 4 US2 | 3 | 2 tests + 1 impl (per-device endpoint reuses controller from US1) |
| 5 Bulk surface | 3 | List + trigger endpoints |
| 6 Reload sync | 2 | F2-hook extension (extends F3's hook) |
| 7 US3 (MCP) | 6 | 2 tests + 4 delegate impls |
| 8 OpenAPI lock | 2 | F4 contract test + F3 schema-drift acknowledgement |
| 9 Seed/dev | 2 | seed.sh + optional fixtures |
| 10 Polish | 5 | Perf, README, ROADMAP, analyze, CI |
| **Total** | **38** | |

## Notes

- This task list is deliberately **test-first** for each user story (carried over from F3 PR #3 — the pattern shipped clean).
- ADR-0015 is the only new ADR planned. ADR-0013 (MCP deferral) and ADR-0014 (drift taxonomy) continue to apply.
- No new top-level project directories.
- F4 widening of F3's `RecommendedActionKind` is intentional and locked by the F3 OpenAPI contract test — the served schema will grow to accommodate the new kinds.
