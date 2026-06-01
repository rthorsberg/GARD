# F11 — Operator Dashboard & Web UI: Implementation Tasks

**Generated**: 2026-05-31 by `/speckit-tasks`
**Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md)
**Research**: [research.md](./research.md) | **Contracts**: [contracts/](./contracts/)

**Conventions**:
- `[P]` — parallelisable (different files, no dependency on an unfinished task)
- `[US1]` … `[US5]` — task belongs to a user-story phase
- `T001..` — sequential IDs in execution order
- Test tasks in Phase 8 only (plan slice 11f; spec does not require TDD-first)

**PR slices**: **11a** (T001–T018), **11b** (T019–T025), **11c** (T026–T032), **11d** (T033–T036, T038–T039), **11e** (T037, T040–T047), **11f** (T048–T055)

Status: `[ ]` pending · `[x]` done

---

## Phase 1 — Setup (slice 11a)

**Purpose**: Design artefacts, ADR, `web/` scaffold, toolchain, and optional backend CORS before UI features.

- [x] T001 Verify feature spec at `specs/011-operator-dashboard/spec.md` and checklist at `specs/011-operator-dashboard/checklists/requirements.md` (16/16 pass)
- [x] T002 Verify plan + research at `specs/011-operator-dashboard/plan.md` and `specs/011-operator-dashboard/research.md` (R-1..R-12)
- [x] T003 [P] Author `adr/ADR-0022-operator-web-ui-boundary.md` — thin-client over REST, no Streamlit, RBAC mirror UX-only, shadcn layout reference
- [x] T004 [P] Verify route contract at `specs/011-operator-dashboard/contracts/ui-routes.yaml` and API map at `specs/011-operator-dashboard/contracts/ui-api-map.yaml`
- [x] T005 Scaffold `web/` with Vite 6 + React 19 + TypeScript — `web/package.json`, `web/vite.config.ts`, `web/tsconfig.json`, `web/index.html`, `web/src/main.tsx`
- [x] T006 [P] Configure Tailwind CSS 4 and shadcn/ui in `web/components.json`, `web/tailwind.config.ts`, `web/src/index.css`
- [x] T007 [P] Add Vite dev proxy in `web/vite.config.ts` — forward `/api` and `/healthz` to `http://127.0.0.1:8080`
- [x] T008 [P] Add optional CORS middleware in `gard/api/middleware/cors.py`, `GARD_CORS_ORIGINS` in `gard/core/settings.py`, register in `gard/api/app.py`

---

## Phase 2 — Foundational (blocking prerequisites)

**Purpose**: Auth, API client, routing shell, permission gates, and shared UI primitives. **Blocks all user stories.**

**Checkpoint**: Sign-in with lab JWT → protected route renders app shell; `GET /api/v1/compliance/summary` succeeds with bearer token.

- [x] T009 Implement session storage in `web/src/auth/session.ts` — apiBaseUrl, token, subject, roles, expiresAt (sessionStorage)
- [x] T010 [P] Implement typed fetch client in `web/src/api/client.ts` — Authorization header, 401/403/502 error mapping, correlation id passthrough
- [x] T011 [P] Add API response types in `web/src/api/types/` for compliance, readiness, devices, netbox, audit envelopes per `contracts/ui-api-map.yaml`
- [x] T012 [P] Mirror `gard/core/rbac.py` role permissions in `web/src/auth/permissions.ts` and `CanAccess` component in `web/src/auth/CanAccess.tsx`
- [x] T013 Configure React Router v7 in `web/src/App.tsx` with routes from `contracts/ui-routes.yaml` and auth guard redirect to `/sign-in`
- [x] T014 Implement sign-in page in `web/src/routes/sign-in.tsx` — API base URL + JWT paste, health check, session persist
- [x] T015 [P] Install shadcn layout primitives in `web/src/components/ui/` — button, card, badge, table, tabs, dialog, toast, skeleton
- [x] T016 [P] Implement posture badge tokens in `web/src/lib/posture.ts` and `PostureBadge` in `web/src/components/ui/posture-badge.tsx` (R-12 unknown-first)
- [x] T017 Implement app shell in `web/src/components/layout/AppShell.tsx`, `Sidebar.tsx`, `Header.tsx` — ecommerce-kit sidebar + header per spec design reference
- [x] T018 Configure TanStack Query provider in `web/src/main.tsx` and shared query defaults (staleTime, retry on 502)

---

## Phase 3 — US1 (P1): Lifecycle posture at a glance 🎯 MVP

**Story goal**: Dashboard shows estate KPIs, posture breakdown, NetBox coverage, recent activity; drill-down links to filtered views.

**Independent test criterion**: Sign in with lifecycle_admin JWT → dashboard displays compliance/readiness/netbox summary counts matching API; click drifted KPI → navigates to filtered device/compliance list.

### US1 — Implementation

- [x] T019 [P] [US1] Add React Query hooks in `web/src/api/hooks/useComplianceSummary.ts`, `useReadinessSummary.ts`, `useNetboxSummary.ts`, `useRecentAudit.ts`
- [x] T020 [P] [US1] Implement `KpiCard` in `web/src/components/dashboard/KpiCard.tsx` with drill-down link support
- [x] T021 [P] [US1] Implement `PostureChart` in `web/src/components/dashboard/PostureChart.tsx` using Recharts (compliance mix)
- [x] T022 [P] [US1] Implement `DevicesBySiteChart` in `web/src/components/dashboard/DevicesBySiteChart.tsx` (client aggregate from compliance devices sample or summary)
- [x] T023 [US1] Implement `RecentActivityTable` in `web/src/components/dashboard/RecentActivityTable.tsx` — audit rows with action badges
- [x] T024 [US1] Implement dashboard page in `web/src/routes/dashboard.tsx` — parallel queries, partial error widgets, empty estate state (FR-012)
- [x] T025 [US1] Wire dashboard KPI drill-down navigation to `/devices?compliance=…` and `/netbox` per `contracts/ui-routes.yaml`

**Checkpoint**: MVP — operator answers "how many devices are drifted?" from dashboard without curl.

---

## Phase 4 — US2 (P1): Device discovery and lifecycle drill-down

**Story goal**: Searchable/filterable device list with pagination; device detail tabs for observation, compliance, readiness, NetBox linkage.

**Independent test criterion**: Filter devices by compliance state in URL → table updates; open device detail → tabs show evaluation timestamps and explicit not-evaluated states.

### US2 — Implementation

- [x] T026 [P] [US2] Add hooks `useComplianceDevices.ts` and `useDeviceDetail.ts` in `web/src/api/hooks/` with pagination and filter params
- [x] T027 [US2] Implement `DeviceTable` in `web/src/components/devices/DeviceTable.tsx` — sortable columns, PostureBadge, pagination controls
- [x] T028 [US2] Implement devices list page in `web/src/routes/devices/index.tsx` — URL-synced filters (`compliance`, `site`, `page`, `limit`), client hostname search
- [x] T029 [P] [US2] Implement `DeviceOverviewTab` in `web/src/components/devices/DeviceOverviewTab.tsx` — identity, firmware, NetBox link indicator
- [x] T030 [P] [US2] Implement `DeviceComplianceTab` and `DeviceReadinessTab` in `web/src/components/devices/` — render API envelopes with reasons (Constitution V)
- [x] T031 [US2] Implement device detail page in `web/src/routes/devices/[deviceId].tsx` — tabbed layout; hide mutation controls for viewer role
- [x] T032 [US2] Add empty and error states for device list/detail in `web/src/components/devices/DeviceEmptyState.tsx`

**Checkpoint**: Device triage workflow completable without external API client.

---

## Phase 5 — US3 (P1): Guided operator actions with feedback

**Story goal**: Permission-gated import, compliance/readiness evaluation, and NetBox sync with in-progress UI and structured result summaries.

**Independent test criterion**: lifecycle_admin runs import → compliance eval → NetBox sync sequentially; each step shows success/partial/failure counts; audit screen lists events.

### US3 — Implementation

- [x] T033 [P] [US3] Implement `ActionResultPanel` in `web/src/components/actions/ActionResultPanel.tsx` — normalized mutation outcome (data-model Action result)
- [x] T034 [US3] Implement compliance page in `web/src/routes/compliance.tsx` — fleet summary, run evaluation mutation, loading overlay (FR-015)
- [x] T035 [US3] Implement readiness page in `web/src/routes/readiness.tsx` — fleet summary, run evaluation mutation, refresh on success
- [x] T036 [US3] Implement CSV import dialog in `web/src/components/devices/ImportCsvDialog.tsx` — `POST /api/v1/imports/devices/csv`, job polling via `GET .../jobs/{id}`
- [x] T037 [US3] Implement NetBox page in `web/src/routes/netbox.tsx` — summary, sync runs list, sync trigger with `confirm_writeback`, write-back counts (F10)
- [x] T038 [US3] Gate mutation buttons with `CanAccess` per `contracts/ui-api-map.yaml`; map 403 to user-friendly toast in `web/src/api/client.ts`
- [x] T039 [US3] Add mutation hooks in `web/src/api/hooks/useComplianceEvaluate.ts`, `useReadinessEvaluate.ts`, `useNetboxSync.ts`, `useImportCsv.ts`

**Checkpoint**: Common operator mutation workflow (import → eval → sync) completable entirely in portal.

---

## Phase 6 — US4 (P2): Uplift planning visibility

**Story goal**: Wave and exception list/detail with member device posture; permitted draft/submit actions when role allows.

**Independent test criterion**: Lab data with draft wave → uplift list and detail render wave metadata and member devices matching API.

### US4 — Implementation

- [x] T040 [P] [US4] Add hooks `useUpliftWaves.ts`, `useUpliftWaveDetail.ts`, `useUpliftExceptions.ts` in `web/src/api/hooks/`
- [x] T041 [US4] Implement uplift list page in `web/src/routes/uplift/index.tsx` — wave name, status, device count, last updated
- [x] T042 [US4] Implement wave detail page in `web/src/routes/uplift/waves/[waveId].tsx` — member devices with compliance/readiness badges
- [x] T043 [US4] Implement exceptions page in `web/src/routes/uplift/exceptions.tsx` — read-only list with link to devices
- [x] T044 [US4] Add permission-gated wave submit action on detail page when `uplift.draft` permitted (no execution controls)

**Checkpoint**: Uplift visibility without CSV export or manual API queries.

---

## Phase 7 — US5 (P3): Audit and evidence for traceability

**Story goal**: Searchable audit log with filters; evidence metadata view for read-only stakeholders.

**Independent test criterion**: After US3 mutations, audit page lists events with correct actor, timestamp, action type; evidence links resolve when present.

### US5 — Implementation

- [x] T045 [P] [US5] Add hooks `useAuditLog.ts` and `useEvidenceList.ts` in `web/src/api/hooks/`
- [x] T046 [US5] Implement audit page in `web/src/routes/audit.tsx` — filter by action type, time range, reverse chronological table
- [x] T047 [US5] Implement evidence detail drawer/modal in `web/src/components/audit/EvidenceDrawer.tsx` — read-only metadata display

**Checkpoint**: Auditor traceability workflow without mutation access.

---

## Phase 8 — Polish & cross-cutting (slice 11f)

**Purpose**: Tests, CI, deploy reference, docs, RBAC drift guard, quickstart validation.

- [x] T048 [P] Add MSW fixtures in `web/src/api/__fixtures__/` and Vitest setup in `web/vitest.config.ts` for `PostureBadge`, `KpiCard`, session helpers
- [x] T049 [P] Add Playwright E2E smoke in `web/tests/e2e/dashboard.spec.ts` — sign-in → dashboard → device detail against lab stack
- [x] T050 [P] Add RBAC mirror contract test in `web/tests/unit/permissions.test.ts` — compare TS map to `gard/core/rbac.py` exports
- [x] T051 [P] Add GitHub Actions workflow `.github/workflows/web-ci.yml` — pnpm lint, vitest, build
- [x] T052 [P] Add reference nginx config `deploy/nginx/gard-ui.conf` for same-origin static + API proxy
- [x] T053 Validate operator flow in `specs/011-operator-dashboard/quickstart.md` against implemented UI
- [x] T054 [P] Update `ROADMAP.md`, root `README.md`, and `specs/011-operator-dashboard/README.md` — F11 status
- [x] T055 Run `pnpm --dir web lint`, `pnpm --dir web test`, `pnpm --dir web build` green; existing `pytest`/`ruff`/`mypy` unchanged on backend

---

## Dependencies & Execution Order

### Phase Dependencies

```text
Phase 1 (Setup)
    ↓
Phase 2 (Foundational) ── BLOCKS all user stories
    ↓
Phase 3 (US1 Dashboard) ── MVP 🎯
    ↓
Phase 4 (US2 Devices) ── depends on shell + API client only
    ↓
Phase 5 (US3 Actions) ── depends on US2 components for import entry; independent test via compliance/netbox routes
    ↓
Phase 6 (US4 Uplift) ── independent after Phase 2; best after US2 device badges
    ↓
Phase 7 (US5 Audit) ── independent after Phase 2; integrates with US3 for smoke data
    ↓
Phase 8 (Polish)
```

### User Story Dependencies

| Story | Priority | Depends on | Independent test |
|-------|----------|------------|------------------|
| US1 | P1 | Phase 2 | Dashboard KPIs match API summaries |
| US2 | P1 | Phase 2 | Device list/detail without mutations |
| US3 | P1 | Phase 2; import dialog links US2 | import → eval → sync with feedback |
| US4 | P2 | Phase 2 | Wave list/detail read-only |
| US5 | P3 | Phase 2 | Audit search after any mutation |

### Parallel Opportunities

**Phase 1** (after T001–T002): T003, T004, T006, T007, T008 in parallel.

**Phase 2** (after T009): T010, T011, T012, T015, T016 in parallel.

**Phase 3 US1**: T019–T022 all parallel; then T023–T025 sequential.

**Phase 4 US2**: T026 parallel with T029–T030; T027–T028 sequential.

**Phase 5 US3**: T033, T039 parallel; T034–T035 parallel after hooks.

**Phase 8**: T048–T052 all parallel.

### Parallel Example: Phase 2 foundation

```bash
# After T009 session.ts:
Task T010: web/src/api/client.ts
Task T011: web/src/api/types/
Task T012: web/src/auth/permissions.ts + CanAccess.tsx
Task T015: web/src/components/ui/ shadcn primitives
Task T016: web/src/lib/posture.ts + posture-badge.tsx
```

### Parallel Example: US1 dashboard widgets

```bash
Task T019: web/src/api/hooks/useComplianceSummary.ts (+ siblings)
Task T020: web/src/components/dashboard/KpiCard.tsx
Task T021: web/src/components/dashboard/PostureChart.tsx
Task T022: web/src/components/dashboard/DevicesBySiteChart.tsx
# Then assemble T024 dashboard.tsx
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Complete Phase 1: Setup (T001–T008)
2. Complete Phase 2: Foundational (T009–T018) — **CRITICAL**
3. Complete Phase 3: US1 Dashboard (T019–T025)
4. **STOP and VALIDATE**: Dashboard independent test criterion
5. Demo to stakeholders before devices/actions

### Incremental Delivery (PR slices)

| Slice | Tasks | Delivers |
|-------|-------|----------|
| 11a | T001–T018 | Scaffold, auth, API client, shell skeleton |
| 11b | T019–T025 | Dashboard MVP |
| 11c | T026–T032 | Devices list + detail |
| 11d | T033–T036, T038–T039 | Compliance, readiness, import |
| 11e | T037, T040–T047 | NetBox, uplift, audit |
| 11f | T048–T055 | Tests, CI, docs |

### Suggested MVP scope

**Minimum shippable increment**: Phases 1–3 (through T025) — sign-in, dashboard with drill-down. Adds immediate operator value per SC-001.

**Full P1 scope**: Phases 1–5 (through T039) — completes all P1 user stories before P2 uplift.

---

## Task Summary

| Metric | Count |
|--------|-------|
| **Total tasks** | 55 |
| Phase 1 Setup | 8 |
| Phase 2 Foundational | 10 |
| US1 Dashboard | 7 |
| US2 Devices | 7 |
| US3 Actions | 7 |
| US4 Uplift | 5 |
| US5 Audit | 3 |
| Phase 8 Polish | 8 |

**Format validation**: All tasks use `- [x] T### [P?] [US?]` checklist format with file paths.

---

## Notes

- UI MUST NOT implement lifecycle rules client-side (FR-013); display API envelopes only.
- No Streamlit; all UI code under `web/` (FR-014).
- Unknown/not-evaluated posture MUST remain visible (Constitution III, R-12).
- NetBox sync UI MUST show write-back phase counts from F10 sync response (SC-006).
- Optional P3 firmware catalog browse (`/catalog`) deferred — not in task list unless spec amended.
