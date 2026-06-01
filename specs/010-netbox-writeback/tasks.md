# F10 — NetBox Lifecycle Write-Back: Implementation Tasks

**Generated**: 2026-06-01 by `/speckit-tasks`
**Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md)
**Research**: [research.md](./research.md) | **Contracts**: [contracts/](./contracts/)

**Conventions**:
- `[P]` — parallelisable (different files, no dependency on an unfinished task)
- `[US1]` … `[US4]` — task belongs to a user-story phase
- `T001..` — sequential IDs in execution order
- Test tasks included (spec SC-001–SC-005 and plan contract/integration/unit coverage)

**PR slices**: **10a** (T001–T005), **10b** (T006–T015), **10c** (T016–T020), **10d** (T021–T037)

Status: `[ ]` pending · `[x]` done

---

## Phase 1 — Setup (slice 10a)

**Purpose**: Design artefacts, ADR, manifest schema, and canonical catalog before write-back code.

- [x] T001 Verify feature spec at `specs/010-netbox-writeback/spec.md` (clarify session complete)
- [x] T002 Verify plan + research at `specs/010-netbox-writeback/plan.md` and `specs/010-netbox-writeback/research.md` (R-1..R-10)
- [x] T003 [P] Verify manifest schema at `specs/010-netbox-writeback/contracts/write-back-manifest.schema.yaml`, reference copy at `specs/010-netbox-writeback/contracts/write-back-manifest.yaml`, and canonical manifest at `gard-catalog/netbox/write-back-manifest.yaml`
- [x] T004 [P] Author `adr/ADR-0021-netbox-lifecycle-writeback.md` — post-sync coupling, conflict policy, tag reconcile, credential split, supersedes ADR-0017 write-back deferral
- [x] T005 Verify requirements checklist at `specs/010-netbox-writeback/checklists/requirements.md` (16/16 pass)

---

## Phase 2 — Foundational (blocking prerequisites)

**Purpose**: Manifest loader, settings, write client extensions, API schemas, contract tests. **Blocks all user stories.**

**Checkpoint**: `load_writeback_manifest()` validates `gard-catalog/netbox/write-back-manifest.yaml` against schema; contract tests pass without NetBox.

- [x] T006 [P] Add `netbox_write_token`, `netbox_writeback_enabled`, and prod confirm helpers in `gard/core/settings.py`
- [x] T007 [P] Implement `gard/integrations/netbox/writeback_manifest.py` — load canonical manifest, JSON Schema validation, allowed `gard_source` catalogue, duplicate slug/field detection
- [x] T008 [P] Add write-back dataclasses (`WritebackSummary`, `WritebackEntry`, `WritebackReport`) in `gard/integrations/netbox/writeback_publisher.py` or `gard/core/netbox_sync_controller.py`
- [x] T009 Extend `gard/integrations/netbox/write_client.py` — `patch_device()` for `custom_fields` + `tags`; idempotent `ensure_custom_field()` and `ensure_tag()` for dev bootstrap (reuse F9 auth)
- [x] T010 [P] Add Pydantic models `WritebackSummaryOut`, `WritebackEntryOut`, `WritebackReportOut` and extend `NetboxSyncReportOut` in `gard/api/schemas/netbox_integration.py` per `specs/010-netbox-writeback/contracts/rest-openapi.yaml`
- [x] T011 [P] Implement `tests/contract/test_netbox_writeback_manifest.py` — schema validation, unique slugs/fields, all `gard_source` keys allowed, broken manifest fails before runtime

---

## Phase 3 — US1 (P1): Lifecycle metadata appears in NetBox after sync 🎯 MVP

**Story goal**: Post-sync write-back pushes custom fields + tags to all linked devices in the sync batch; sync response includes write-back report.

**Independent test criterion**: `tests/integration/test_netbox_writeback_sync.py` — two evaluated linked devices → sync returns `writeback.summary.updated=2`; NetBox devices show `gard_*` fields and `gard-managed` tag.

### US1 — Tests first

- [x] T012 [P] [US1] Scaffold `tests/integration/test_netbox_writeback_sync.py` — evaluate compliance/readiness, sync, assert write-back counts and NetBox field values (skip if NetBox unavailable)

### US1 — Implementation

- [x] T013 [US1] Implement `gard/integrations/netbox/writeback_publisher.py` — resolve GARD lifecycle sources (Device + latest F3/F4 evals), build desired custom field map and tag slugs, PATCH NetBox devices via write client
- [x] T014 [US1] Extend `gard/core/netbox_sync_controller.py` — invoke write-back after successful pull commit; skip when sync fails; aggregate linked devices from sync batch; attach `WritebackReport` to outcome
- [x] T015 [US1] Extend `gard/api/routers/netbox_integration.py` — return extended sync envelope with `data.report.writeback`; HTTP 200 when pull succeeds (FR-011a)

**Checkpoint**: MVP — single sync call updates NetBox lifecycle mirror for linked devices with evaluations.

---

## Phase 4 — US2 (P1): Write-back manifest governs field mapping

**Story goal**: Lifecycle-as-code manifest is the sole mapping source; dev bootstrap provisions NetBox schema; dry-run validates without writes.

**Independent test criterion**: Contract tests cover all required `gard_source` keys; dev bootstrap creates missing custom fields; per-device `failed` when field absent in prod.

### US2 — Tests + bootstrap

- [x] T016 [P] [US2] Extend `tests/contract/test_netbox_writeback_manifest.py` — assert minimum field set (lifecycle state, compliance/readiness summaries, target firmware, eval timestamps) and tag slugs from spec
- [x] T017 [US2] Add manifest dry-run validation in `gard/integrations/netbox/writeback_manifest.py` — validate-only mode callable from CLI without NetBox PATCH
- [x] T018 [US2] Implement `gard/integrations/netbox/field_bootstrap.py` — idempotent create custom fields + tags from manifest via write client (dev/lab only)
- [x] T019 [US2] Implement `gard/cli/netbox_writeback_bootstrap.py` and wire `netbox bootstrap-writeback-fields` in `gard/__main__.py` with `--dry-run`, `--confirm`, structured report
- [x] T020 [P] [US2] Update `deploy/scripts/sync-gard-netbox.sh` and `deploy/scripts/seed-netbox.sh` to call bootstrap step; document `GARD_NETBOX_WRITE_TOKEN` in `deploy/docker-compose.yml`

**Checkpoint**: Manifest changes drive NetBox field mapping; lab bootstrap removes manual custom-field UI setup.

---

## Phase 5 — US3 (P2): Conflict-safe, idempotent updates

**Story goal**: Second sync with stable evaluations skips unchanged devices; manual NetBox custom-field edits report conflict; tags reconcile without field-style conflicts.

**Independent test criterion**: Unit tests — stable re-run → `skipped`/`unchanged`; manual field edit → `conflict`; removed tag re-applied when posture warrants.

### US3 — Tests + hardening

- [x] T021 [P] [US3] Implement `tests/unit/test_writeback_publisher.py` — conflict detection (R-5), tag reconcile (R-4), unknown sentinel (FR-006), skip-not-linked
- [x] T022 [US3] Add custom-field conflict detection in `gard/integrations/netbox/writeback_publisher.py` — compare NetBox current vs GARD desired; skip PATCH on conflict (default policy)
- [x] T023 [US3] Implement tag reconciliation in `gard/integrations/netbox/writeback_publisher.py` — preserve non-manifest tags; add/remove manifest slugs per posture predicates
- [x] T024 [US3] Add idempotency in `gard/integrations/netbox/writeback_publisher.py` — skip PATCH when custom fields and tags already match desired state
- [x] T025 [US3] Extend `tests/integration/test_netbox_writeback_sync.py` — second sync idempotency scenario; optional conflict scenario with mocked NetBox field drift

**Checkpoint**: No silent overwrite of operator custom-field edits; no duplicate tags on re-sync.

---

## Phase 6 — US4 (P2): Auditable write-back outcomes

**Story goal**: Audit events, evidence, optional DB columns, prod confirm guard; partial write-back failure does not roll back pull.

**Independent test criterion**: Audit log contains `netbox.writeback.started` and `netbox.writeback.completed` with sync `correlation_id`; evidence row has summary counts.

### US4 — Implementation

- [x] T026 [US4] Emit `netbox.writeback.started`, `netbox.writeback.completed`, and `netbox.writeback.failed` audit events in `gard/core/netbox_sync_controller.py` (mirror `netbox.sync.*` pattern)
- [x] T027 [US4] Record write-back evidence summary in `gard/core/netbox_sync_controller.py` via `evidence_emit` with counts and correlation id
- [x] T028 [P] [US4] Add migration `gard/db/migrations/versions/0011_netbox_writeback_counts.py` — optional columns on `netbox_sync_runs`; `devices.netbox_last_writeback_at`
- [x] T029 [US4] Extend `gard/models/netbox_sync_run.py` and `gard/models/device.py` for write-back columns; update run persistence in `gard/core/netbox_sync_controller.py`
- [x] T030 [US4] Add `confirm_writeback` query param and prod/non-localhost guard in `gard/api/routers/netbox_integration.py` (FR-013, R-10)
- [x] T031 [P] [US4] Add audit/evidence unit coverage in `tests/unit/test_writeback_publisher.py` or `tests/unit/test_netbox_writeback_audit.py`

**Checkpoint**: Operations reviewers trace write-back via audit + evidence; prod requires explicit confirm.

---

## Phase 7 — Polish & cross-cutting

- [x] T032 [P] Validate and finalize operator flow in `specs/010-netbox-writeback/quickstart.md` against implemented CLI and sync API
- [x] T033 [P] Add write-back section cross-link in `specs/007-netbox-integration-read/quickstart.md`
- [x] T034 [P] Update `ROADMAP.md` and `specs/010-netbox-writeback/README.md` — mark F10 implementation status
- [x] T035 [P] Ensure `deploy/docker-compose.yml` documents `GARD_NETBOX_WRITE_TOKEN`, `GARD_NETBOX_WRITEBACK_ENABLED`, and container NetBox URL conventions
- [x] T036 Run full `pytest`, `ruff check`, `ruff format --check`, and `mypy gard` green
- [x] T037 PR ready — slices 10a→10d reviewed; ADR-0021 linked in PR description

---

## Dependencies & Execution Order

### Phase Dependencies

```text
Phase 1 (Setup) — mostly complete from /speckit-plan
    ↓
Phase 2 (Foundational) ── BLOCKS all user stories
    ↓
Phase 3 (US1) ── MVP post-sync write-back
    ↓
Phase 4 (US2) ── can overlap after T007; full value after US1 publisher
    ↓
Phase 5 (US3) ── conflict + idempotency hardening
    ↓
Phase 6 (US4) ── audit, migration, prod guard
    ↓
Phase 7 (Polish)
```

### User Story Dependencies

| Story | Priority | Depends on | Independent test |
|---|---|---|---|
| US1 | P1 | Phase 2 | `test_netbox_writeback_sync.py` (T012) |
| US2 | P1 | Phase 2 (T007) | Extended contract tests (T016) + bootstrap CLI (T019) |
| US3 | P2 | US1 publisher (T013) | `test_writeback_publisher.py` (T021) |
| US4 | P2 | US1 sync hook (T014) | Audit/evidence tests (T031) |

### Parallel Opportunities

**Phase 2** (after T005):
```text
T006  gard/core/settings.py
T007  gard/integrations/netbox/writeback_manifest.py
T010  gard/api/schemas/netbox_integration.py
T011  tests/contract/test_netbox_writeback_manifest.py
```

**Phase 3–4** (after T009–T010):
```text
T012  tests/integration/test_netbox_writeback_sync.py
T016  tests/contract/test_netbox_writeback_manifest.py (extend)
T020  deploy/scripts/sync-gard-netbox.sh + seed-netbox.sh
```

**Phase 5–6** (after T013):
```text
T021  tests/unit/test_writeback_publisher.py
T028  gard/db/migrations/versions/0011_netbox_writeback_counts.py
T031  tests/unit/test_netbox_writeback_audit.py
```

---

## Implementation Strategy

### MVP First (US1 path)

1. Complete Phase 1 (T004 ADR only) + Phase 2 (manifest loader, settings, schemas, contract tests)
2. Complete Phase 3 (US1) — **STOP and validate** sync→write-back on lab NetBox with two linked devices
3. Continue US2 → US3 → US4 → Polish

### Incremental PR slices

| Slice | Tasks | Delivers |
|---|---|---|
| **10a** | T001–T005 | ADR-0021, verified design artefacts |
| **10b** | T006–T015 | Manifest loader, publisher, sync hook, REST response, integration test scaffold |
| **10c** | T016–T020 | Dev field bootstrap CLI, deploy scripts, extended contract tests |
| **10d** | T021–T037 | Conflict/idempotency, audit/evidence, migration, prod guard, docs, CI green |

### Suggested MVP scope

**Minimum shippable increment**: Phase 1 (T004) + Phase 2 + Phase 3 (T012–T015) — post-sync lifecycle mirror in NetBox for linked devices after evaluate + sync.

---

## Notes

- F7 read-only `gard/integrations/netbox/client.py` MUST remain GET-only; all writes go through `write_client.py`.
- Sync MUST NOT invoke compliance/readiness evaluate (FR-001a); operator runs evaluate before sync when fresh mirrors are needed.
- Write-back runs for **all linked devices in the sync batch**, not only created/updated rows (clarify Q3).
- Tag reconciliation is not conflict-gated; custom-field conflicts only (clarify Q4).
- Operator flow: evaluate → sync (pull + write-back) → verify in NetBox UI.
