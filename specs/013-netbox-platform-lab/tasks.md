# F13 — NetBox Platform Lab (Orb, Diode, Branching): Implementation Tasks

**Generated**: 2026-06-02 by `/speckit-tasks`
**Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md)
**Research**: [research.md](./research.md) | **Contracts**: [contracts/](./contracts/)

**Conventions**:
- `[P]` — parallelisable (different files, no dependency on an unfinished task)
- `[US1]` … `[US4]` — task belongs to a user-story phase
- `T001..` — sequential IDs in execution order
- Contract tests included (constitution catalogue schema coverage; plan slice 13a)

**PR slices**: **13a** (T001–T008), **13b** (T009–T018), **13c** (T019–T030), **13d** (T031–T042)

**Scope guard**: Zero changes under `gard/`, `web/`, or Alembic migrations (FR-007, SC-005).

Status: `[ ]` pending · `[x]` done

---

## Phase 1 — Setup (slice 13a)

**Purpose**: Verify design artefacts, ADR boundary, contract schemas, and ROADMAP row before deploy implementation.

- [x] T001 Verify feature spec at `specs/013-netbox-platform-lab/spec.md` (four user stories, FR-007 no GARD code, merge-to-main workflow)
- [x] T002 Verify plan + research at `specs/013-netbox-platform-lab/plan.md` and `specs/013-netbox-platform-lab/research.md` (R-1..R-10 resolved)
- [x] T003 [P] Verify contracts at `specs/013-netbox-platform-lab/contracts/lab-stack-manifest.schema.yaml`, `specs/013-netbox-platform-lab/contracts/lab-stack-manifest.yaml`, `specs/013-netbox-platform-lab/contracts/ingest-fixture-catalogue.schema.yaml`, and `specs/013-netbox-platform-lab/contracts/health-check.schema.yaml`
- [x] T004 [P] Author `adr/ADR-0024-netbox-platform-lab-boundary.md` — deploy/ops-only feature, Orb→Diode→NetBox upstream of GARD REST consumer (ADR-0018), no GARD Diode SDK, dev/lab scope (FR-010)
- [x] T005 [P] Add F13 row to `ROADMAP.md` — status planned, branch `013-netbox-platform-lab`, dependencies F7/F9/F12/ADR-0018
- [x] T006 [P] Implement `tests/contract/test_platform_lab_manifest.py` — validate `specs/013-netbox-platform-lab/contracts/lab-stack-manifest.yaml` against schema; assert project name `gard-f7-netbox` and minimum service set
- [x] T007 [P] Implement `tests/contract/test_platform_lab_health_schema.py` — validate sample healthy/degraded JSON fixtures against `specs/013-netbox-platform-lab/contracts/health-check.schema.yaml`
- [x] T008 [P] Implement `tests/contract/test_platform_lab_ingest_catalogue.py` — validate canonical fixture path `deploy/scripts/fixtures/platform-lab/ingest-catalogue.yaml` against ingest schema once file exists (skip or xfail until T024 creates file)

---

## Phase 2 — Foundational (blocking prerequisites, slice 13b)

**Purpose**: Custom NetBox image, plugin config, platform compose overlay, Diode vendored stack, env templates. **Blocks all user stories.**

**Checkpoint**: `docker compose -p gard-f7-netbox -f deploy/netbox/docker-compose.yml -f deploy/netbox/docker-compose.platform.yml config` succeeds; NetBox image builds with Diode plugin; reconciler env uses `http://netbox:8080` not localhost.

- [x] T009 [P] Create `deploy/netbox/Dockerfile.plugins` — base `netboxcommunity/netbox:v4.6-5.0.1`, install `netboxlabs-diode-netbox-plugin`, conditional `netboxlabs-netbox-branching` via build arg when `GARD_NETBOX_BRANCHING_ENABLED=1`
- [x] T010 [P] Create `deploy/netbox/configuration/plugins.py` — `PLUGINS` order (`netbox_diode_plugin` first, `netbox_branching` last when enabled), `PLUGINS_CONFIG` for diode secrets from env, `DATABASE_ROUTERS` with `BranchAwareRouter` when branching enabled (research R-2)
- [x] T011 Extend `deploy/netbox/docker-compose.yml` — switch `netbox` and `netbox-worker` to build from `deploy/netbox/Dockerfile.plugins` when `GARD_NETBOX_PLATFORM=1`; mount `deploy/netbox/configuration/plugins.py` into NetBox config path documented in README
- [x] T012 [P] Create `deploy/netbox/docker-compose.platform.yml` — Diode nginx/services, `orb-agent`, three `lab-sim-*` simulator services on dedicated bridge network; explicit `depends_on` health chains (research R-1, R-4)
- [x] T013 [P] Vendor/adapt Diode quickstart under `deploy/netbox/platform/diode/` — compose fragment, nginx config, `.env.example` template; set `NETBOX_DIODE_PLUGIN_API_BASE_URL=http://netbox:8080` (research R-3)
- [x] T014 [P] Extend `deploy/netbox/.env.example` — `GARD_NETBOX_PLATFORM`, `GARD_NETBOX_BRANCHING_ENABLED`, `NETBOX_TO_DIODE_CLIENT_SECRET`, `DIODE_CLIENT_ID`, `DIODE_CLIENT_SECRET`, port overrides (`GARD_DIODE_GRPC_HOST_PORT`, etc.); no committed secrets (FR-008)
- [x] T015 [P] Create `deploy/netbox/platform/orb/agent.yaml` skeleton — `network_discovery` backend, Diode gRPC target via compose DNS, placeholder policy scope for lab subnet (research R-4)
- [x] T016 [P] Create `deploy/scripts/platform-lab-stop.sh` — project-scoped `docker compose -p gard-f7-netbox ... down` without `-v` by default; document `-v` flag for intentional wipe (research R-10, FR-009)
- [x] T017 Create `deploy/scripts/platform-lab-start.sh` — build + up with both compose files and `--env-file deploy/netbox/.env`; print NetBox UI URL and next-step hints (F9 bootstrap, health check)
- [x] T018 Create `deploy/scripts/platform-lab-health.sh` — emit JSON matching `specs/013-netbox-platform-lab/contracts/health-check.schema.yaml`; exit codes 0/1/2 per research R-8; checks NetBox UI, Diode gRPC, orb-agent container, diode plugin endpoint

---

## Phase 3 — US1 (P1): Start the full platform lab stack 🎯 MVP

**Story goal**: Reproducible dev/lab deployment with NetBox + Diode + Orb, isolated via explicit compose project name, documented ports/credentials/teardown.

**Independent test criterion**: Follow `specs/013-netbox-platform-lab/quickstart.md` sections 1–2 from clean Docker host; within 30 minutes reach NetBox UI at port 18888, `./deploy/scripts/platform-lab-health.sh` returns `healthy` or `degraded` (Branching skipped), GARD stack not required (SC-001, acceptance scenario US1-1..3).

### US1 — Implementation

- [x] T019 [US1] Wire `deploy/netbox/platform/diode/` services into `deploy/netbox/docker-compose.platform.yml` with host port **58080** default for Diode gRPC per `specs/013-netbox-platform-lab/contracts/lab-stack-manifest.yaml`
- [x] T020 [US1] Wire `orb-agent` service in `deploy/netbox/docker-compose.platform.yml` — mount `deploy/netbox/platform/orb/agent.yaml`, pass `DIODE_CLIENT_ID`/`DIODE_CLIENT_SECRET` from env, add `cap_add: [NET_RAW]` for discovery
- [x] T021 [US1] Add pre-flight port collision notes and override env table to `deploy/netbox/README.md` — 18888 vs 18080, 8080 GARD, never run global prune (edge cases, FR-002)
- [x] T022 [US1] Extend `deploy/netbox/README.md` with platform lab start/stop/health commands referencing `deploy/scripts/platform-lab-*.sh` and compose project `gard-f7-netbox`
- [x] T023 [US1] Document credential bootstrap flow in `specs/013-netbox-platform-lab/quickstart.md` section 1 — superuser, Diode OAuth secret extraction, Orb client credentials from NetBox UI (FR-008, research R-7)
- [x] T024 [US1] Document soft stop vs volume reset levels in `specs/013-netbox-platform-lab/quickstart.md` section 8 — scoped `-p gard-f7-netbox` only (FR-009, research R-10)

**Checkpoint**: MVP — operator starts platform lab, health JSON green, stops lab without affecting other Docker projects.

---

## Phase 4 — US2 (P1): Discovery data reaches NetBox via Diode

**Story goal**: Orb forwards fixture-scoped discovery through Diode into NetBox `main`; smoke script verifies device objects without `seed-netbox.sh` REST posts.

**Independent test criterion**: `./deploy/scripts/platform-lab-ingest-smoke.sh` exits 0; NetBox REST shows ≥3 devices matching `deploy/scripts/fixtures/platform-lab/ingest-catalogue.yaml` names — GARD not invoked (SC-002, US2 independent test).

### US2 — Implementation

- [x] T025 [P] [US2] Create `deploy/scripts/fixtures/platform-lab/ingest-catalogue.yaml` — ≥3 devices with `name`, `site`, `role`, `device_type`, `simulator_ip`; include `idempotency_notes` for second-run behavior (research R-5, SC-002)
- [x] T026 [P] [US2] Configure three simulator containers in `deploy/netbox/docker-compose.platform.yml` — static IPs on lab bridge matching catalogue `simulator_ip` values; hostnames discoverable by Orb
- [x] T027 [US2] Finalize `deploy/netbox/platform/orb/agent.yaml` — scope `network_discovery` targets to simulator IPs only; document recovery when Diode unavailable in `specs/013-netbox-platform-lab/quickstart.md` troubleshooting (US2 acceptance scenario 3)
- [x] T028 [US2] Create `deploy/scripts/platform-lab-ingest-smoke.sh` — trigger/wait for Orb discovery cycle, query NetBox REST `GET /api/dcim/devices/`, assert catalogue names and `minimum_device_count`; exit non-zero on failure
- [x] T029 [US2] Update `tests/contract/test_platform_lab_ingest_catalogue.py` — load and validate `deploy/scripts/fixtures/platform-lab/ingest-catalogue.yaml` (remove xfail from T008)
- [x] T030 [US2] Document ingest smoke procedure in `specs/013-netbox-platform-lab/quickstart.md` section 4 — F9 bootstrap prerequisite, no `seed-netbox.sh` (FR-003, FR-006)

**Checkpoint**: Ingest smoke passes; idempotency notes documented; Diode partial-failure recovery in troubleshooting.

---

## Phase 5 — US3 (P1): Branch, review, merge to main, then GARD sync

**Story goal**: Operator stages IPAM/DCIM edits on Branching branch, merges to `main`, verifies GARD sync only observes merged SoT via existing scripts.

**Independent test criterion**: `./deploy/scripts/platform-lab-merge-demo.sh` prints before/after REST snapshots — branch-only IP invisible on `main`, visible after merge; `./deploy/scripts/sync-gard-netbox.sh` reflects merged state (SC-003, US3 independent test).

### US3 — Implementation

- [x] T031 [P] [US3] Enable optional Branching in `deploy/netbox/Dockerfile.plugins` and `deploy/netbox/configuration/plugins.py` when `GARD_NETBOX_BRANCHING_ENABLED=1`; document skip path when disabled (FR-011, edge case)
- [x] T032 [US3] Create `deploy/scripts/platform-lab-merge-demo.sh` — select device from ingest catalogue, record `main` primary IP, create branch + change IP assignment, assert `main` unchanged pre-merge, merge branch, assert `main` updated post-merge
- [x] T033 [US3] Document merge-to-main workflow and GARD anti-pattern warning in `specs/013-netbox-platform-lab/quickstart.md` section 5 — GARD reads `main` only (FR-004, ADR-0023)
- [x] T034 [US3] Document GARD sync handoff in `specs/013-netbox-platform-lab/quickstart.md` section 6 — reuse `./deploy/scripts/sync-gard-netbox.sh`, cross-link F7/F12 quickstarts (FR-005, FR-012)
- [x] T035 [P] [US3] Add merge-before-sync cross-link in `specs/012-netbox-ipam-dcim-align/quickstart.md` — point to `specs/013-netbox-platform-lab/quickstart.md` upstream platform lab
- [x] T036 [P] [US3] Add platform lab ingest path cross-link in `specs/007-netbox-integration-read/quickstart.md` — Orb/Diode alternative to `seed-netbox.sh`

**Checkpoint**: Merge demo proves branch isolation; documented fallback when Branching skipped (direct `main` edit).

---

## Phase 6 — US4 (P2): Lab fixtures and drift scenarios for GARD validation

**Story goal**: Planted drift scenarios connect NetBox-side changes to expected F12 alignment finding kinds; end-to-end runbook ties ingest → merge → GARD sync → findings check.

**Independent test criterion**: Operator follows one drift scenario README; after merge + GARD sync, expected finding kind appears via F12 alignment endpoints (SC-004, US4 independent test).

### US4 — Implementation

- [x] T037 [P] [US4] Create `deploy/scripts/fixtures/platform-lab/drift-scenarios/mgmt-ip-mismatch.md` — NetBox steps, GARD precondition (stale CSV mgmt IP), expected kind `mgmt_ip_mismatch`, verification via `GET .../alignment/findings`, pass/fail criteria before GARD invoke
- [x] T038 [P] [US4] Create `deploy/scripts/fixtures/platform-lab/drift-scenarios/missing-interface-address.md` — remove mgmt interface IP on merge, expected F12 kind, verification steps
- [x] T039 [US4] Add end-to-end runbook section to `specs/013-netbox-platform-lab/quickstart.md` section 7–8 — ingest → optional merge → GARD sync → F12 findings (FR-012)
- [x] T040 [US4] Extend `deploy/netbox/README.md` with drift scenario pointers and link to F12 alignment quickstart for verification

**Checkpoint**: ≥2 drift scenarios documented; quickstart cross-links F12 alignment endpoints.

---

## Phase 7 — Polish & cross-cutting concerns (slice 13d)

**Purpose**: Validation, scope guard, optional CI, documentation consistency.

- [x] T041 [P] Run contract tests: `uv run pytest tests/contract/test_platform_lab_manifest.py tests/contract/test_platform_lab_health_schema.py tests/contract/test_platform_lab_ingest_catalogue.py -q`
- [x] T042 [P] Verify zero GARD application diffs — confirm no changes under `gard/`, `web/src/`, or `gard/db/migrations/` in feature branch (SC-005, FR-007)
- [x] T043 Walk through `specs/013-netbox-platform-lab/quickstart.md` end-to-end on local Docker; fix any broken commands or paths discovered
- [x] T044 [P] Update `specs/013-netbox-platform-lab/README.md` — mark plan/tasks complete, list deliverable script paths
- [x] T045 [P] Optional: add non-blocking CI workflow `.github/workflows/platform-lab-smoke.yml` — contract tests only (skip full Docker pull in PR unless labeled) per plan testing note

---

## Dependencies & execution order

### Phase dependencies

```text
Phase 1 (Setup)
    ↓
Phase 2 (Foundational) — BLOCKS all user stories
    ↓
Phase 3 (US1) 🎯 MVP
    ↓
Phase 4 (US2) — requires US1 stack + F9 bootstrap documented
    ↓
Phase 5 (US3) — requires US2 populated devices on main
    ↓
Phase 6 (US4) — requires US3 merge workflow (or main-edit fallback)
    ↓
Phase 7 (Polish)
```

### User story dependencies

| Story | Depends on | Independent test |
|-------|------------|------------------|
| US1 | Phase 2 | Health JSON + NetBox UI without GARD |
| US2 | US1 (+ F9 bootstrap once) | Ingest smoke REST counts |
| US3 | US2 (devices on `main`) | Merge demo before/after REST |
| US4 | US3 (or main-edit path) | F12 finding kind after GARD sync |

US3 merge-demo can use ingest-catalogue devices; US4 drift scenarios assume GARD estate has intentional stale mgmt IPs.

### Parallel opportunities

**Phase 1** (after T001–T002): T003–T008 all `[P]`

**Phase 2** (after T011): T009+T010, T012+T013+T014+T015, T016 in parallel

**Phase 4**: T025+T026 parallel before T027–T028

**Phase 5**: T035+T036 parallel with T031–T034

**Phase 6**: T037+T038 parallel

**Phase 7**: T041+T042+T044+T045 parallel

### Parallel example: Phase 2 foundation

```bash
# Different files — run together after T001–T002 complete:
Task T009: deploy/netbox/Dockerfile.plugins
Task T010: deploy/netbox/configuration/plugins.py
Task T012: deploy/netbox/docker-compose.platform.yml
Task T013: deploy/netbox/platform/diode/
Task T014: deploy/netbox/.env.example
Task T015: deploy/netbox/platform/orb/agent.yaml
```

### Parallel example: US4 drift scenarios

```bash
Task T037: deploy/scripts/fixtures/platform-lab/drift-scenarios/mgmt-ip-mismatch.md
Task T038: deploy/scripts/fixtures/platform-lab/drift-scenarios/missing-interface-address.md
```

---

## Implementation strategy

### MVP first (User Story 1 only)

1. Complete Phase 1 — Setup (T001–T008)
2. Complete Phase 2 — Foundational (T009–T018)
3. Complete Phase 3 — US1 (T019–T024)
4. **STOP and VALIDATE**: `./deploy/scripts/platform-lab-start.sh` → `./deploy/scripts/platform-lab-health.sh`
5. Demo isolated NetBox + Diode + Orb lab without GARD

### Incremental delivery

1. Setup + Foundational → compose builds
2. US1 → healthy stack (MVP)
3. US2 → ingest smoke proves Orb→Diode→NetBox
4. US3 → merge workflow + GARD handoff docs
5. US4 → drift scenarios for F12 validation
6. Polish → contract tests + scope guard

### Suggested PR merge order

Align with plan slices: **13a** → **13b** → **13c** (US1+US2) → **13d** (US3+US4+polish).

---

## Task summary

| Phase | Tasks | Story |
|-------|-------|-------|
| 1 Setup | T001–T008 (8) | — |
| 2 Foundational | T009–T018 (10) | — |
| 3 US1 | T019–T024 (6) | Start platform lab 🎯 |
| 4 US2 | T025–T030 (6) | Diode ingest smoke |
| 5 US3 | T031–T036 (6) | Branch merge → GARD sync |
| 6 US4 | T037–T040 (4) | Drift scenarios |
| 7 Polish | T041–T045 (5) | Cross-cutting |
| **Total** | **45 tasks** | |

**Parallel opportunities**: 22 tasks marked `[P]`

**MVP scope**: Phases 1–3 (T001–T024, 24 tasks) — full platform lab start + health without ingest smoke.

**Full feature scope**: All 45 tasks through Phase 7.

---

## Notes

- F9 device-type bootstrap remains a **manual prerequisite** before US2 ingest smoke on fresh volumes — not implemented in F13 (existing `python -m gard netbox bootstrap-device-types`).
- `deploy/scripts/seed-netbox.sh` stays valid as FR-011 alternate path; do not remove or break.
- Branching is optional; health script MUST return `degraded` (exit 1) not `unhealthy` when core ingest path works but Branching disabled.
