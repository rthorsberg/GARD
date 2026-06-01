# F9 — NetBox Device Type Bootstrap: Implementation Tasks

**Generated**: 2026-06-01 by `/speckit-tasks`
**Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md)
**Research**: [research.md](./research.md) | **Contracts**: [contracts/](./contracts/)

**Conventions**:
- `[P]` — parallelisable (different files, no dependency on an unfinished task)
- `[US1]` … `[US4]` — task belongs to a user-story phase
- `T001..` — sequential IDs in execution order
- Test tasks included (spec SC-003–SC-005 require contract + integration coverage)

**PR slices**: **9a** (T001–T006), **9b** (T007–T012), **9c** (T013–T018), **9d** (T019–T028)

Status: `[ ]` pending · `[x]` done

---

## Phase 1 — Setup (slice 9a)

**Purpose**: Design artefacts, ADR, submodule pin, and canonical manifest before importer code.

- [x] **T001** Spec `specs/009-netbox-devicetype-bootstrap/spec.md`
- [x] **T002** Plan `specs/009-netbox-devicetype-bootstrap/plan.md` + research R-1..R-8
- [x] **T003** Manifest schema `specs/009-netbox-devicetype-bootstrap/contracts/device-types-manifest.schema.yaml` + reference copy `contracts/device-types-manifest.yaml`
- [x] **T004** Requirements checklist `specs/009-netbox-devicetype-bootstrap/checklists/requirements.md`
- [x] **T005** [P] Author `adr/ADR-0020-netbox-devicetype-bootstrap.md` — curated manifest, upstream pin, write-client scope, prerequisite for write-back
- [x] **T006** Add git submodule `vendor/netbox-devicetype-library` at manifest pin; set real `upstream_pin` in `gard-catalog/netbox/device-types-manifest.yaml` (replace placeholder SHA)

---

## Phase 2 — Foundational (blocking prerequisites)

**Purpose**: Manifest loader, NetBox write client, importer core, CLI scaffold. **Blocks all user stories.**

**Checkpoint**: `python -m gard netbox bootstrap-device-types --dry-run` validates manifest + resolves all library YAML paths without NetBox writes.

- [x] **T007** [P] Implement `gard/integrations/netbox/devicetype_manifest.py` — load `gard-catalog/netbox/device-types-manifest.yaml`, validate schema, resolve paths under submodule root, dedupe aliases
- [x] **T008** [P] Implement `gard/integrations/netbox/write_client.py` — POST/PATCH NetBox REST (token auth); separate from F7 read-only `client.py` GET guard
- [x] **T009** Implement `gard/integrations/netbox/devicetype_importer.py` — parse community YAML; create manufacturer + device type + component templates; idempotent skip-by-slug (R-5)
- [x] **T010** Implement `gard/cli/netbox_bootstrap.py` + wire `netbox bootstrap-device-types` in `gard/__main__.py` with `--dry-run`, `--force`, structured stdout report
- [x] **T011** [P] `tests/contract/test_netbox_devicetype_manifest.py` — schema validation, all `library_path` files exist at pin, no duplicate slugs/aliases, broken path fails before import
- [x] **T012** [P] Unit tests for manifest loader edge cases in `tests/unit/test_devicetype_manifest.py` — empty aliases, conflicting slug detection

---

## Phase 3 — US1 (P1): Operator bootstraps NetBox with community device types 🎯 MVP

**Story goal**: Dev bootstrap imports manifest entries; ISR1121 seed devices reference imported types; F7 sync matches by serial.

**Independent test criterion**: `tests/integration/test_netbox_devicetype_bootstrap.py` — bootstrap on dev NetBox, ISR1121 type has interfaces; seed + F7 sync `matched≥2`.

### US1 — Tests first

- [x] **T013** [P] [US1] `tests/integration/test_netbox_devicetype_bootstrap.py` — bootstrap imports ISR1121 entry with components; `seed-netbox.sh` devices use imported slug; F7 sync matches fixture serials

### US1 — Implementation

- [x] **T014** [US1] Extend `gard/integrations/netbox/devicetype_importer.py` — full component import (interfaces, power-ports, console-ports per community YAML)
- [x] **T015** [US1] Update `deploy/scripts/seed-netbox.sh` — call `python -m gard netbox bootstrap-device-types` before device seed; remove hand-rolled `/dcim/device-types/` POST block
- [x] **T016** [US1] Update seeded device payloads in `deploy/scripts/seed-netbox.sh` to reference imported device type slug (`cisco-isr-1121-8p`) from manifest

**Checkpoint**: MVP — dev NetBox bootstrap + ISR1121 seed + F7 sync green.

---

## Phase 4 — US2 (P1): Manifest aligned with GARD-supported models only

**Story goal**: Manifest lists exactly GARD-supported models; validation fails on gaps; no bulk vendor import.

**Independent test criterion**: Contract tests assert entry count matches seed/catalog scope; deliberately broken manifest fails CI.

### US2 — Tests + validation

- [x] **T017** [P] [US2] Extend `tests/contract/test_netbox_devicetype_manifest.py` — assert manifest covers `deploy/scripts/fixtures/isr1121-devices.csv` and `deploy/scripts/fixtures/devices.csv` model_raw values via aliases
- [x] **T018** [US2] Add manifest lint in `gard/integrations/netbox/devicetype_manifest.py` — fail if `library_path` missing, if two entries share `expected_slug`, or if alias appears twice
- [x] **T019** [P] [US2] Document manifest entry addition procedure in `specs/009-netbox-devicetype-bootstrap/quickstart.md` pin-bump section (when adding new GARD-supported model)

**Checkpoint**: Manifest is the single allow-list; CI catches drift.

---

## Phase 5 — US3 (P2): Reproducible pinned upstream snapshot

**Story goal**: Bootstrap logs applied pin; re-run is idempotent; pin bump is deliberate manifest change.

**Independent test criterion**: Second bootstrap run all-skipped; report includes `upstream_pin`.

### US3 — Tests + hardening

- [x] **T020** [P] [US3] Extend `tests/integration/test_netbox_devicetype_bootstrap.py` — second bootstrap run reports all entries `skipped`; summary counts zero duplicates
- [x] **T021** [US3] Ensure bootstrap report JSON/stdout includes `upstream_pin`, per-entry status, and summary `{created, updated, skipped, conflict, failed}` in `gard/cli/netbox_bootstrap.py`
- [x] **T022** [US3] Conflict policy in `devicetype_importer.py` — existing type with different component count → `conflict` + skip unless `--force` (R-5)

**Checkpoint**: Reproducible lab/CI bootstrap without NetBox drift.

---

## Phase 6 — US4 (P2): Optional production provision hook

**Story goal**: Same CLI works against prod NetBox with explicit `--confirm`; never runs on GARD API startup.

**Independent test criterion**: CLI refuses non-localhost without `--confirm`; `create_app()` lifespan does not invoke bootstrap.

### US4 — Implementation + docs

- [x] **T023** [US4] Add `--confirm` guard in `gard/cli/netbox_bootstrap.py` — required when target URL is not localhost/127.0.0.1 or when `GARD_ENV=prod`
- [x] **T024** [P] [US4] `tests/unit/test_netbox_bootstrap_cli.py` — prod URL without `--confirm` exits non-zero; `--dry-run` never calls write client
- [x] **T025** [P] [US4] Update `deploy/netbox/README.md` + `specs/009-netbox-devicetype-bootstrap/quickstart.md` with production provision section
- [x] **T026** [US4] Verify `gard/api/app.py` lifespan and F7 sync path do not import bootstrap (regression comment or unit smoke)

**Checkpoint**: Operators can provision prod NetBox explicitly; no surprise mutations.

---

## Phase 7 — Polish & cross-cutting

- [x] **T027** [P] Cross-link F9 bootstrap step in `specs/007-netbox-integration-read/quickstart.md`
- [x] **T028** [P] Update `ROADMAP.md` — mark F9 shipped when complete; note ADR-0020; write-back still post-v1
- [x] **T029** Full `pytest` + `ruff check` + `ruff format --check` + `mypy gard` green
- [x] **T030** PR ready — slices 9a→9d reviewed; submodule pin documented in PR description

---

## Dependencies & Execution Order

### Phase Dependencies

```text
Phase 1 (Setup)
    ↓
Phase 2 (Foundational) ── BLOCKS all user stories
    ↓
Phase 3 (US1) ── MVP bootstrap + seed + sync
    ↓
Phase 4 (US2) ── can overlap after T007; full value after US1
    ↓
Phase 5 (US3) ── idempotency + pin reporting
    ↓
Phase 6 (US4) ── prod hook
    ↓
Phase 7 (Polish)
```

### User Story Dependencies

| Story | Priority | Depends on | Independent test |
|---|---|---|---|
| US1 | P1 | Phase 2 | `test_netbox_devicetype_bootstrap.py` (T013) |
| US2 | P1 | Phase 2 (T007) | Extended contract manifest tests (T017) |
| US3 | P2 | US1 importer (T014) | Re-run idempotency test (T020) |
| US4 | P2 | Phase 2 CLI (T010) | CLI confirm unit tests (T024) |

### Parallel Opportunities

**Phase 2** (after T006):
```bash
T007  gard/integrations/netbox/devicetype_manifest.py
T008  gard/integrations/netbox/write_client.py
T011  tests/contract/test_netbox_devicetype_manifest.py
T012  tests/unit/test_devicetype_manifest.py
```

**Phase 3–4** (after T009–T010):
```bash
T013  tests/integration/test_netbox_devicetype_bootstrap.py
T017  tests/contract/test_netbox_devicetype_manifest.py (extend)
```

---

## Implementation Strategy

### MVP First (US1 path)

1. Complete Phase 1 + Phase 2 (manifest, submodule, importer, CLI dry-run)
2. Complete Phase 3 (US1) — **STOP and validate** ISR1121 bootstrap + F7 sync
3. Continue US2 → US3 → US4 → Polish

### Incremental PR slices

| Slice | Tasks | Delivers |
|---|---|---|
| **9a** | T001–T006 | ADR-0020, submodule pin, manifest finalized |
| **9b** | T007–T012 | Loader, write client, importer, CLI, contract tests |
| **9c** | T013–T018 | seed-netbox.sh, integration test, manifest lint |
| **9d** | T019–T030 | Idempotency, prod hook, docs, CI green |

### Suggested MVP scope

**Minimum shippable increment**: Phase 1 + Phase 2 + Phase 3 (T013–T016) — community-backed ISR1121 device type in dev NetBox with F7 sync parity.

---

## Notes

- F7 read sync (`gard/core/netbox_sync_controller.py`, read-only `client.py`) MUST remain unchanged except docs cross-links.
- Submodule updates require paired manifest `upstream_pin` bump in the same PR.
- Initial manifest: 6 entries (Cisco×3, Juniper×2, Nokia×1) per research R-6.
- No GARD Postgres migrations in F9.
