# F3 — Compliance & Drift Evaluation: Implementation Tasks

**Generated**: 2026-05-30 by `/speckit-tasks`
**Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md)
| **Data model**: [data-model.md](./data-model.md) | **Contracts**: [contracts/](./contracts/)

**Conventions**:
- `[P]` — parallelisable (different files, no dependency on an unfinished task)
- `[US1]` / `[US2]` / `[US3]` — task belongs to a user-story phase
- `T001..` — sequential IDs in execution order
- Test tasks are included (F1+F2 lessons-learned: deferring tests to
  polish phase led to PR #2's documented integration-test gap; F3
  ships tests inline)

---

## Phase 1 — Setup (no story label)

- [ ] T001 [P] Add ADR-0014 stub at `adr/ADR-0014-drift-taxonomy.md` capturing storage shape (R-1), precedence ordering (R-2), and the seven canonical drift types; promote from `research.md` §2
- [ ] T002 [P] Create `gard/api/routers/__init__.py` placeholder if missing; create `gard/mcp/tools/__init__.py` for the new tool package directory
- [ ] T003 Verify migration sequence: confirm `0006_evidence_catalog_load.py` exists as latest head; `0007_compliance_evaluations.py` will be the new head

## Phase 2 — Foundational (blocking prerequisites for all user stories)

These tasks land first; every US depends on them.

- [ ] T004 [P] Add new permissions `READ_COMPLIANCE` and `RUN_COMPLIANCE_EVAL` to `gard/core/rbac.py` and assign per the F2 convention (analyst/auditor → READ; lifecycle_manager → READ+RUN; system_admin → READ+RUN)
- [ ] T005 [P] Add settings `discovery_stale_days: int = 30` and `evidence_stale_days: int = 90` to `gard/core/settings.py`; bound `>= 1`; document env-var names `GARD_DISCOVERY_STALE_DAYS` / `GARD_EVIDENCE_STALE_DAYS`
- [ ] T006 [P] Extend `gard/core/envelope.py`: add `ComplianceEnvelope` model (extends `FirmwareComplianceEnvelope` with `drift_type`, `secondary_drift_types`, populated `recommended_actions[]`, `observation_ref`); add `ComplianceReasonKind` Literal union of F2 kinds + 3 new kinds (`stale_observation`, `missing_upgrade_path`, `package_not_built`); add `RecommendedAction` / `RecommendedActionKind` models; add `build_compliance_envelope()` helper
- [ ] T007 Create `gard/db/migrations/versions/0007_compliance_evaluations.py`: implements the table schema from data-model.md §1.1 including all CHECK constraints, FK relationships (RESTRICT for devices, SET NULL for target_ref + observation_ref), and three indices (`(device_id, evaluated_at DESC)`, `(primary_drift_type) WHERE NOT NULL`, `(evaluated_at DESC)`); include downgrade
- [ ] T008 Create `gard/models/compliance_evaluation.py`: SQLAlchemy 2.x ORM model matching the migration; register in `gard/models/__init__.py`

---

## Phase 3 — US1 (P1): Estate-wide drift dashboard

**Story goal**: A lifecycle manager calls `GET /compliance/summary` and sees per-drift-type counts across the whole estate in <1s p95.

**Independent test criterion**: Against the seeded 5-device fixture set, the summary returns counts that sum to `total_evaluated`, and filtering by `region=oslo` returns counts matching the manual ground truth.

### US1 — Tests first

- [ ] T009 [P] [US1] `tests/unit/test_drift_rules.py`: pure-function truth table for each of the 7 drift rules; one positive + one negative test per rule (14 cases minimum)
- [ ] T010 [P] [US1] `tests/unit/test_drift_precedence.py`: assert `DRIFT_PRECEDENCE` constant matches R-2; assert `primary_of(drift_set)` resolves multi-drift devices deterministically (catalog > rule > package > target > discovery > evidence > exception)
- [ ] T011 [P] [US1] `tests/integration/test_us1_summary_endpoint.py`: walk all of US1's Acceptance Scenarios from spec.md (summary returns 7 counters; filter narrows result; reload+resync changes counts without per-device call)

### US1 — Implementation

- [ ] T012 [P] [US1] `gard/core/drift_rules.py`: one pure function per drift type (`is_target_drift`, `is_catalog_drift`, `is_package_drift`, `is_rule_drift`, `is_discovery_drift`, `is_evidence_drift`, `is_exception_drift`); each takes `(device, observation, target, envelope_f2, settings)` and returns `(bool, ReasonModel | None)`. Plus `DRIFT_PRECEDENCE` tuple constant and `primary_of(drift_set)` helper
- [ ] T013 [US1] `gard/core/compliance_evaluation_controller.py`: implements `evaluate(session, audit_session, device_id, actor)` per R-4; calls F2's `compliance_controller.evaluate()`, runs drift rules, composes envelope (sorted per R-7), idempotency-checks against latest row, INSERTs new row + emits `compliance.evaluated` audit only on diff. Also implements `evaluate_many(device_ids, ...)` returning `(evaluated_count, unchanged_count)`. Depends on T007, T008, T012
- [ ] T014 [P] [US1] `gard/api/schemas/compliance.py`: Pydantic models `SummaryResponse`, `ComplianceDeviceRow`, `ComplianceDeviceList`, `EvaluateRequest`, `EvaluateResponse` per `contracts/rest-openapi.yaml`; `extra="forbid"` throughout
- [ ] T015 [US1] `gard/api/routers/compliance.py` part 1: `GET /api/v1/compliance/summary` with optional filters; serves from DISTINCT ON query per R-3; emits one `compliance.read` audit row per request; auth `READ_COMPLIANCE`. Register router in `gard/api/app.py`'s `_PHASE3_ROUTERS`. Depends on T004, T013, T014

## Phase 4 — US2 (P1): Explainable per-device verdict

**Story goal**: A field engineer hits `GET /devices/{id}/compliance` and gets a full envelope with cited reasons + machine-readable recommended actions.

**Independent test criterion**: Each seeded device returns an envelope whose `state`/`drift_type`/`reasons`/`recommended_actions` match the per-device truth table in `quickstart.md` §3.

### US2 — Tests first

- [ ] T016 [P] [US2] `tests/unit/test_recommended_actions.py`: assert the 8 action kinds (7 emitted + `acknowledge_exception` contract-only); per-kind params validation; one builder test per kind asserting params populated from the right inputs
- [ ] T017 [P] [US2] `tests/unit/test_compliance_envelope.py`: SC-005 determinism — same inputs → byte-identical envelope (modulo correlation_id, as_of); reasons[] and actions[] sort stably on `(kind, ref)`
- [ ] T018 [P] [US2] `tests/integration/test_us2_explainable_envelope.py`: walk all US2 Acceptance Scenarios; r1.oslo returns `outside_target` + `target_drift` + 1 upgrade_path_query action; r3.oslo returns `classified` + `catalog_drift` + 1 define_target action; stale observation surfaces secondary `discovery_drift`

### US2 — Implementation

- [ ] T019 [P] [US2] `gard/core/recommended_actions.py`: one builder function per `RecommendedActionKind`; deterministic param composition; `build_actions_for(drift_set, device, envelope_f2)` returns the sorted list per R-7
- [ ] T020 [US2] Wire T019 into T013's controller so `recommended_actions[]` populates on every envelope; the F2 envelope's empty list (left by ADR-0013 seam) is overwritten with the F3-computed list
- [ ] T021 [US2] `gard/api/routers/compliance.py` part 2: `GET /api/v1/devices/{device_id}/compliance` — composes envelope from latest `ComplianceEvaluation` row + live target/observation joins for cited refs; auth `READ_COMPLIANCE`; emits `compliance.read` audit. Depends on T015, T020

## Phase 5 — US1+US2 finishing surface: bulk list + trigger

- [ ] T022 [P] `tests/integration/test_compliance_devices_list.py`: pagination + every filter combination (drift_type, state, region, site, platform_family, vendor_normalized)
- [ ] T023 [P] `tests/integration/test_compliance_evaluate_trigger.py`: happy path + 413 EVALUATION_TOO_LARGE + 400 missing-both-or-both-given + bounded scope_selector
- [ ] T024 `gard/api/routers/compliance.py` part 3: `GET /api/v1/compliance/devices` (list) and `POST /api/v1/compliance/evaluate` (trigger); evaluate uses `scope_selector.evaluate()` from F2 to resolve device sets; refuses sets > 5,000 with structured 413. Emits `compliance.evaluation_triggered` audit. Depends on T013, T015, T021

## Phase 6 — Reload→F3 sync (R-6 implementation)

- [ ] T025 [P] `tests/integration/test_post_reload_compliance_sync.py`: trigger a catalog reload that touches a target's scope; assert exactly the affected devices receive new `ComplianceEvaluation` rows; assert unaffected devices do not
- [ ] T026 Extend `gard/core/firmware_catalog_controller._reevaluate_compliance_post_reload`: after the F2 `compliance_controller.evaluate` call inside the loop, call `compliance_evaluation_controller.evaluate` for the same device id. Same actor, same correlation_id. F2 hook signature unchanged

## Phase 7 — US3 (P2): MCP tool contracts + delegates

**Story goal**: Four read-only MCP tools published as contracts and implemented as REST-parity delegates. Transport remains deferred to F008.

### US3 — Tests first

- [ ] T027 [P] [US3] `tests/contract/test_compliance_mcp_tools.py`: parse `contracts/mcp-tools.yaml`; assert each tool has non-empty `input_schema`, `output_schema`, `auth`; assert `auth` value matches a `Permission` enum value
- [ ] T028 [P] [US3] `tests/integration/test_us3_mcp_parity.py`: per-tool parity tests — each tool's output matches the REST equivalent's data (modulo correlation_id) for the same filter set

### US3 — Implementation

- [ ] T029 [P] [US3] `gard/mcp/tools/count_devices_outside_target.py`: input model, output model, delegate calls into `compliance_evaluation_controller` (NOT the REST router) for the count
- [ ] T030 [P] [US3] `gard/mcp/tools/list_devices_outside_target.py`: same pattern; capped at 500 items
- [ ] T031 [P] [US3] `gard/mcp/tools/get_compliance_summary.py`: delegates to the same summary query as the REST endpoint
- [ ] T032 [P] [US3] `gard/mcp/tools/get_unknown_lifecycle_items.py`: queries devices with `lifecycle_state = 'unknown'` and surfaces the F2 reason kind that put them there

## Phase 8 — REST contract lock + OpenAPI

- [ ] T033 [P] `tests/contract/test_compliance_rest_openapi.py`: load `contracts/rest-openapi.yaml`; for every path × method, assert the generated `/openapi.json` carries the same path, parameter set, request schema, and response schemas. Catches future drift between contract and code
- [ ] T034 Verify `openapi.json` references regenerate cleanly; no orphan `$ref`s; `additionalProperties: false` on every response schema

## Phase 9 — Seed + dev workflow

- [ ] T035 [P] Extend `deploy/scripts/seed.sh` to invoke `POST /api/v1/compliance/evaluate` with `{scope_selector: {}}` after the F2 firmware reload, then print the per-device drift classification table from `quickstart.md` §1
- [ ] T036 [P] Update `Makefile` if needed (no new target expected; `make seed` already invokes the script)

## Phase 10 — Polish & cross-cutting

- [ ] T037 [P] Performance smoke: `tests/perf/test_summary_p95.py` (marked `pytest.mark.perf`, excluded from default `pytest -q`); synthesise 5,000 devices + 200 targets via factory; assert summary endpoint p95 < 1s; exclude from CI default
- [ ] T038 [P] Update `README.md` Status section: F3 status → "shipped", quickstart additions per F3 quickstart.md
- [ ] T039 [P] Update `ROADMAP.md`: F3 row → "shipped (PR #N)"; ADR-0014 marked as shipped
- [ ] T040 Run `/speckit-analyze` cross-artefact consistency pass; fix any drift
- [ ] T041 Run `make lint && make test`; CI green before opening PR for review

---

## Dependencies

```
Setup (T001-T003)
   ↓
Foundational (T004-T008)
   ↓
   ├── US1 tests (T009-T011)  ─┐
   ├── US2 tests (T016-T018)   │  (all test files independent)
   └── US3 tests (T027-T028)   │
                               ↓
   ┌── US1 impl (T012-T015) ──→ Phase 5 (T022-T024)
   │       ↑                        ↑
   │       T013 (controller)        │
   │       ↑                        │
   └── US2 impl (T019-T021) ────────┘
           ↑
           T019 → T020 → T021

   Phase 6 (T025-T026) — depends on T013
   Phase 7 (T029-T032) — depend on T013
   Phase 8 (T033-T034) — depends on T015, T021, T024
   Phase 9 (T035-T036) — depend on T015, T021, T024
   Phase 10 polish (T037-T041) — depends on everything
```

## Parallel execution examples

**Wave 1 (after Foundational lands)**: T009, T010, T011, T012, T014, T016, T017, T018, T027, T028 can all start in parallel — different files, no inter-dependencies.

**Wave 2**: T013 lands → T019, T020, T021, T029-T032 all unblock.

**Wave 3**: T024, T026, T033, T034, T035 all parallelizable once T021 ships.

## Implementation strategy — MVP

The MVP for F3 is **US1 only** — Phases 1, 2, 3, plus T025-T026 for the reload-sync. That's `T001..T015` + `T025..T026` = 17 tasks. Ship as draft PR #3 with the summary endpoint live and explainable verdicts deferred.

Recommended: ship **US1 + US2** together (Phases 1-6) as the first reviewable PR; pick up US3 + polish in a follow-up PR. The two P1 stories are tightly coupled by the controller and shipping one without the other leaves a half-built envelope.

## Task count summary

| Phase | Tasks | Notes |
|---|---|---|
| 1 Setup | 3 | ADR + scaffolding |
| 2 Foundational | 5 | Migration, ORM, RBAC, settings, envelope extension |
| 3 US1 | 7 | 3 tests + 4 impl (summary endpoint MVP) |
| 4 US2 | 6 | 3 tests + 3 impl (per-device endpoint) |
| 5 Bulk surface | 3 | List + trigger endpoints |
| 6 Reload sync | 2 | F2-hook extension |
| 7 US3 (MCP) | 6 | 2 tests + 4 delegate impls |
| 8 OpenAPI lock | 2 | Contract test + regen verify |
| 9 Seed/dev | 2 | seed.sh + Makefile (likely no-op) |
| 10 Polish | 5 | Perf, README, ROADMAP, analyze, CI |
| **Total** | **41** | |

## Notes

- This task list is deliberately **test-first** for each user story
  (correcting F2 PR #2's documented integration-test gap).
- ADR-0014 is the only new ADR planned. ADR-0013 (MCP deferral) is
  already shipped on `main` and continues to apply.
- No new top-level project directories; F3 fits cleanly into the F1+F2
  layout.
- Bounded re-eval reuse (T026) keeps F3's runtime cost piggybacked
  onto F2's existing pipeline — no new scheduler / worker.
