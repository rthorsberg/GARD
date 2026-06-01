# F11 — Operator Dashboard & Web UI: Research

**Feature**: `011-operator-dashboard` | **Date**: 2026-05-31

## R-1 — Frontend stack

**Decision**: **Vite 6 + React 19 + TypeScript 5** SPA in `web/` at repository root.

**Rationale**: User preference for TypeScript; Vite gives fast dev HMR and static production builds; React ecosystem aligns with shadcn/ui (Radix + Tailwind). No SSR required for internal operator portal v1.

**Alternatives considered**:
- **Next.js** — rejected for v1 (SSR/SSG unnecessary; adds deployment complexity for internal tool).
- **Streamlit** — explicitly excluded by user.
- **Vue/Svelte** — rejected (no team preference stated; shadcn reference is React-native).

## R-2 — Component library & visual reference

**Decision**: **[shadcn/ui](https://ui.shadcn.com/)** (open components) + **Tailwind CSS 4** + **Recharts** for posture/site charts. Layout inspired by [Shadcn UI Kit E-commerce Dashboard](https://shadcnuikit.com/dashboard/ecommerce) per spec design reference — KPI cards, data table, sidebar shell, status badges.

**Rationale**: Spec design reference; shadcn is copy-paste (no vendor lock-in); matches ecommerce-kit patterns without purchasing the kit.

**Alternatives considered**:
- **MUI / Ant Design** — rejected (heavier theming; less aligned with reference).
- **Paid UI Kit wholesale** — rejected (layout inspiration only).

## R-3 — Data fetching & client state

**Decision**: **TanStack Query v5** for server state (caching, refetch, mutation status) + **React Router v7** for URL-driven navigation and shareable filter state.

**Rationale**: Dashboard fan-out (multiple summary GETs) benefits from parallel queries and stale-while-revalidate; mutations (import, evaluate, sync) need in-flight/error/success UX per FR-015.

**Alternatives considered**:
- **Redux Toolkit** — rejected (server state dominates; Query is sufficient).
- **SWR** — viable; Query chosen for mutation helpers and devtools.

## R-4 — API client generation

**Decision**: **Hand-typed fetch wrapper** against GARD `/openapi.json` with TypeScript interfaces colocated in `web/src/api/types/` for v1 consumed endpoints; optional `openapi-typescript` codegen in a later slice if drift becomes painful.

**Rationale**: UI consumes ~25 endpoints, not full surface; hand types keep PR size bounded; contract tests in `web/` assert response shapes against fixture JSON from pytest/OpenAPI snapshots.

**Alternatives considered**:
- **Full openapi-generator client** — deferred (large generated surface, most unused).
- **tRPC/BFF** — rejected for v1 (violates thin-client goal; extra service).

## R-5 — Authentication UX

**Decision**: **Sign-in screen** collects (1) GARD API base URL and (2) JWT bearer token (issued via existing `POST /api/v1/admin/tokens` or lab `.gard/*.jwt` files). Token stored in **sessionStorage** (cleared on tab close); roles/permissions decoded from JWT payload **for UI gating only** — every action re-validated by GARD API (403 → friendly message).

**Rationale**: GARD v1 has JWT issuance but no password/OAuth login endpoint; token paste matches current operator workflow (curl/MCP). SSO deferred per spec assumptions.

**Alternatives considered**:
- **Cookie session via new backend login** — rejected for v1 scope.
- **localStorage persistence** — rejected (longer-lived token exposure on shared workstations).

## R-6 — CORS & deployment topology

**Decision**: **Same-origin reverse proxy** as primary pattern:
- **Dev**: Vite `server.proxy` forwards `/api` → `http://127.0.0.1:8080`.
- **Prod/lab**: nginx (or Caddy) serves `web/dist` and proxies `/api` to GARD uvicorn.

Optional **`GARD_CORS_ORIGINS`** env on FastAPI for split-host dev (UI on `:5173`, API on `:8080`) — implemented as small middleware addition in slice 11a.

**Rationale**: No CORS middleware exists today; same-origin avoids preflight complexity and keeps JWT in Authorization header straightforward.

**Alternatives considered**:
- **CORS-only, no proxy** — acceptable fallback for local dev; not primary prod pattern.
- **Embed UI in FastAPI StaticFiles** — rejected (couples release cycles; spec says separate deliverable).

## R-7 — Dashboard aggregate strategy

**Decision**: **Client-side fan-out** for v1 dashboard — parallel GETs:
- `GET /api/v1/compliance/summary`
- `GET /api/v1/readiness/summary`
- `GET /api/v1/integrations/netbox/summary`
- `GET /api/v1/audit?limit=10` (recent activity)

No new backend `GET /dashboard/summary` in v1.

**Rationale**: Existing summary endpoints return estate aggregates in O(1) DB work; satisfies SC-003 without BFF. Device list uses domain endpoints (`/compliance/devices`, `/devices`) not full estate scan.

**Alternatives considered**:
- **Dedicated BFF aggregate endpoint** — deferred (nice-to-have if fan-out latency exceeds 3s in lab profiling).

## R-8 — Device list data source

**Decision**: Primary browse table uses **`GET /api/v1/compliance/devices`** (paginated, includes compliance envelope) with filters; fallback/generic inventory via **`GET /api/v1/devices`** when compliance read permission absent. Readiness column from parallel fetch or row enrichment on detail page.

**Rationale**: Compliance list matches spec “posture-first” device table; includes drift status badges for ecommerce-kit “product status” mapping.

**Alternatives considered**:
- **Devices endpoint only** — rejected (no compliance_state filter on `/devices` today).

## R-9 — Long-running operations UX

**Decision**: **Synchronous mutation + loading overlay** for v1 (compliance/readiness evaluate, NetBox sync, CSV import). Import uses **`GET /api/v1/imports/jobs/{id}`** polling if job returns before report is ready.

**Rationale**: Spec allows polling; existing API returns completion inline for evaluate/sync in lab scale; import already has job status endpoint.

**Alternatives considered**:
- **WebSocket progress** — out of scope per spec.
- **Server-Sent Events** — deferred.

## R-10 — Testing strategy

**Decision**:
- **Vitest** + **Testing Library** for components and hooks (unit/integration).
- **Playwright** for E2E against `docker compose` lab stack (sign-in → dashboard → device detail smoke).
- **MSW** (Mock Service Worker) for Storybook-less component tests with fixture JSON.

**Rationale**: Constitution contract-and-integration-first applies to UI via E2E smoke on real API; MSW keeps CI fast for component tests.

**Alternatives considered**:
- **Cypress** — viable; Playwright chosen for trace viewer and parallel runs.
- **Frontend-only without E2E** — rejected (would miss RBAC and API integration regressions).

## R-11 — Permission-aware navigation

**Decision**: Map JWT `roles[]` → GARD permission set using a **static mirror** of `gard/core/rbac.py` ROLE_PERMISSIONS in `web/src/auth/permissions.ts`; regenerate or contract-test against Python source in CI.

**Rationale**: FR-011 requires hide/disable before 403; client-side gating improves UX; server remains authoritative.

**Alternatives considered**:
- **Fetch permissions from new API** — rejected for v1 (no endpoint exists).
- **Show all nav, fail on 403** — rejected (violates spec acceptance scenario).

## R-12 — Status vocabulary & badges

**Decision**: Central **`PostureBadge`** component with fixed token map:

| GARD state | Badge variant | Label |
|------------|---------------|-------|
| compliant / ready_for_uplift | success | Compliant / Ready |
| outside_target / drifted | warning | Drifted |
| blocked | destructive | Blocked |
| unknown / not_evaluated | secondary | Not evaluated |

**Rationale**: Constitution III — never imply compliant from missing data; consistent with spec design reference status chips.

**Alternatives considered**:
- **Per-page ad hoc colors** — rejected (inconsistent operator experience).
