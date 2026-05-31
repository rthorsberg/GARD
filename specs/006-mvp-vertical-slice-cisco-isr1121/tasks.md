# F6 — Tasks

42 tasks across 8 phases. PR slices: **6a** (T001–T012), **6b** (T013–T032), **6c** (T033–T042). Each slice is independently green + reviewable.

Status convention: `[ ]` pending · `[x]` done · `[~]` in progress.

## Phase 1 — Catalog + normalization (slice 6a)

- [ ] **T001** [P] Add `gard-catalog/firmware/targets/cisco-ios-isr1121.yaml` (target `17.12.4`, scope `vendor_normalized: cisco`, `platform_family: ios`).
- [ ] **T002** [P] Add `gard-catalog/firmware/packages/cisco-ios-17.12.4.yaml` and `cisco-ios-16.9.5.yaml`.
- [ ] **T003** [P] Add `gard-catalog/firmware/upgrade-paths/cisco-ios-isr1121.yaml` (edge `16.9.5 → 17.12.4`).
- [ ] **T004** [P] Add `gard-catalog/firmware/prerequisites/isr1121-minimum-flash.yaml` (`min_disk_mb: 1500`, applies to `platform_family: ios`).
- [ ] **T005** [P] Add `gard-catalog/normalization/cisco-ios-isr1121.yaml` (priority 200, sets `model_normalized: ISR1121`).
- [ ] **T006** Add `deploy/scripts/fixtures/isr1121-devices.csv` (golden + blocked + duplicate + rejected + manual_review rows).
- [ ] **T007** Fix `gard/core/device_controller.py` — persist `ram_mb`, `disk_mb`, `licenses` from CSV on upsert (F2 gap).
- [ ] **T008** Verify `load_firmware_catalog()` succeeds with new YAML via unit smoke or loader import.
- [ ] **T009** `uv run ruff check` + `uv run mypy gard` clean on touched modules.
- [ ] **T010** Commit + push slice 6a.

## Phase 2 — Test helpers (slice 6b)

- [ ] **T011** Add `tests/integration/_mvp_isr1121_helpers.py` — catalog load, CSV import, eval triggers, token mint, `MvpContext` dataclass.
- [ ] **T012** Extend `tests/integration/_csv_helpers.py` or helpers with ISR1121 row builder including `ram_mb`/`disk_mb`.

## Phase 3 — US1: automated vertical slice (slice 6b)

- [ ] **T013** [US1] Add `tests/integration/test_mvp_vertical_slice_isr1121.py` — `TestImport::test_mixed_csv_import` (MVP-01).
- [ ] **T014** [US1] `TestImport::test_import_summary_invariant` (MVP-02).
- [ ] **T015** [US1] `TestNormalize::test_isr1121_normalization` (MVP-03).
- [ ] **T016** [US1] `TestCatalog::test_isr1121_target_loaded` (MVP-04).
- [ ] **T017** [US1] `TestEvaluation::test_isr1121_state_taxonomy` (MVP-05).
- [ ] **T018** [US1] `TestUplift::test_create_plan` (MVP-06).
- [ ] **T019** [US1] `TestUplift::test_draft_submit_approve_golden_path` (MVP-07 + golden lifecycle).
- [ ] **T020** [US1] Commit slice 6b partial if large; else continue.

## Phase 4 — US3: MCP delegates (slice 6b)

- [ ] **T021** [US3] `TestMcpDelegates::test_count_outside_target_isr1121` (MVP-08).
- [ ] **T022** [US3] `TestMcpDelegates::test_get_ready_for_uplift_isr1121`.
- [ ] **T023** [US3] `TestMcpDelegates::test_create_uplift_wave_draft_read_shaped`.

## Phase 5 — US4: audit chain (slice 6b)

- [ ] **T024** [US4] `TestAudit::test_golden_device_audit_chain` (MVP-09).
- [ ] **T025** [US4] `TestAudit::test_lifecycle_evidence_emitted` (MVP-10).
- [ ] **T026** [US1] Full `uv run pytest -q` green; mark tasks T001–T025 done.
- [ ] **T027** Commit + push slice 6b.

## Phase 6 — US2: operator runbook (slice 6c)

- [ ] **T028** [US2] Add `deploy/scripts/seed-isr1121.sh` mirroring automated golden path.
- [ ] **T029** [US2] Finalize `specs/006-mvp-vertical-slice-cisco-isr1121/quickstart.md` with real checkpoint output.
- [ ] **T030** [US2] Manual smoke: run `seed-isr1121.sh` against Docker (document result in commit message if skipped in CI).

## Phase 7 — Docs + polish (slice 6c)

- [ ] **T031** Update `README.md` F6 status (in progress → shipped when merge-ready).
- [ ] **T032** Update `ROADMAP.md` progress table.
- [ ] **T033** Mark all tasks done; `uv run ruff format .` + full CI suite clean.
- [ ] **T034** Commit + push slice 6c; open PR.

## Dependencies

```text
6a (catalog/fixture) → 6b (tests) → 6c (runbook/docs)
US1 bootstrap → US3 MCP → US4 audit (same bootstrap fixture)
```

## MVP scope (first green bar)

Slice **6a + 6b** through T026 delivers the CI regression harness (User Story 1). Slice **6c** adds human runbook (User Story 2).
