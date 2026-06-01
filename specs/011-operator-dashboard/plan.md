# F11 — Operator Dashboard & Web UI: Implementation Plan

**Feature Branch**: `011-operator-dashboard`
**Status**: Draft
**Date**: 2026-05-31
**Inputs**: `spec.md`, `research.md` (R-1..R-12), `data-model.md`, `contracts/`, `quickstart.md`
**Constitution version**: 1.0.0
**Predecessors**: F1–F10 (REST API, RBAC, compliance, readiness, uplift, NetBox sync + write-back)
**Successor**: none planned

## Summary

F11 delivers a **TypeScript operator portal** (`web/`) — a thin client over the existing GARD FastAPI service. Layout follows the [Shadcn UI Kit e-commerce dashboard](https://shadcnuikit.com/dashboard/ecommerce) pattern (KPI cards, posture tables, status badges, sidebar shell) mapped to lifecycle domain vocabulary. Stack: **Vite + React + TypeScript + shadcn/ui + TanStack Query + React Router**. Auth via JWT bearer (lab token paste). v1 is read-heavy with permission-gated mutations (import, evaluate, NetBox sync). **No Streamlit.** Optional FastAPI CORS for split-origin dev; production uses same-origin nginx proxy.

## Technical Context

| Aspect | Choice |
|--------|--------|
| Language | TypeScript 5.x (frontend); Python 3.12 unchanged (backend) |
| Framework | React 19 + Vite 6 |
| UI components | shadcn/ui + Tailwind CSS 4 + Recharts |
| Routing | React Router v7 (URL-synced filters) |
| Server state | TanStack Query v5 |
| API client | Typed fetch wrapper; fixtures + optional openapi-typescript later |
| Auth | JWT in sessionStorage; roles mirrored from `gard/core/rbac.py` for UI gates |
| Dev proxy | Vite `/api` → `http://127.0.0.1:8080` |
| Prod deploy | Static `web/dist` + nginx reverse proxy to GARD API |
| Backend delta | Optional `GARD_CORS_ORIGINS` middleware only — no new lifecycle logic |
| Testing | Vitest + Testing Library + MSW; Playwright E2E vs docker lab |
| Performance target | Dashboard interactive ≤3s @ 1k devices (SC-003) via summary endpoints |
| Scale | 1,000+ device list via pagination (compliance/devices) |

## Constitution Check

*GATE: Passed pre-Phase 0 and post-Phase 1 design.*

| Principle | F11 adherence |
|-----------|---------------|
| I — Governance Before Execution | UI triggers existing gated API mutations only; no execution/provisioning controls in v1 |
| II — Desired vs Actual | UI displays API envelopes; no client-side drift/readiness computation |
| III — Unknown Is First-Class | `PostureBadge` + dashboard widgets show unknown/not-evaluated explicitly |
| IV — Lifecycle-as-Code | No catalog YAML editing in v1; firmware catalog browse read-only (P3 optional) |
| V — Evidence/Audit | Audit/evidence screens read-only; mutations flow through audited API endpoints |
| VI — Curated MCP | No MCP client in browser |
| VII — Integration Over Replacement | NetBox screen shows sync/write-back status; does not replace NetBox UI |

**Post-design re-check**: Thin-client boundary preserved in ADR-0022. UI permission mirror is UX-only; GARD RBAC remains authoritative. No constitutional violations.

## Project Structure

### Documentation (this feature)

```text
specs/011-operator-dashboard/
├── plan.md                 # This file
├── research.md             # R-1..R-12
├── data-model.md           # Frontend view models + API mapping
├── quickstart.md           # Dev/prod runbook
├── contracts/
│   ├── ui-routes.yaml      # Route + widget contract
│   └── ui-api-map.yaml     # Screen → REST endpoint map
└── tasks.md                # /speckit-tasks (pending)
```

### Source Code (repository root)

**New — `web/` (Operator Portal SPA)**

```text
web/
├── package.json
├── vite.config.ts              # /api proxy
├── tailwind.config.ts
├── components.json             # shadcn config
├── index.html
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── routes/                 # React Router pages
│   │   ├── sign-in.tsx
│   │   ├── dashboard.tsx
│   │   ├── devices/
│   │   ├── compliance.tsx
│   │   ├── readiness.tsx
│   │   ├── netbox.tsx
│   │   ├── uplift/
│   │   └── audit.tsx
│   ├── components/
│   │   ├── layout/             # Sidebar, Header (ecommerce-kit shell)
│   │   ├── dashboard/          # KpiCard, PostureChart, RecentActivity
│   │   ├── devices/            # DeviceTable, DeviceDetailTabs
│   │   └── ui/                 # shadcn primitives
│   ├── api/
│   │   ├── client.ts           # fetch + auth header + error mapping
│   │   ├── types/              # Response interfaces
│   │   └── hooks/              # useComplianceSummary, etc.
│   ├── auth/
│   │   ├── session.ts
│   │   ├── permissions.ts      # mirror of rbac.py
│   │   and CanAccess.tsx
│   └── lib/
│       └── posture.ts          # badge tokens (R-12)
├── tests/
│   ├── unit/
│   └── e2e/                    # Playwright
└── public/
```

**New — ADR & deploy**

- `adr/ADR-0022-operator-web-ui-boundary.md`
- `deploy/nginx/gard-ui.conf` (optional reference config)
- `.github/workflows/web-ci.yml` (lint, test, build)

**Extended (minimal backend)**

- `gard/api/middleware/cors.py` — optional CORS when `GARD_CORS_ORIGINS` set
- `gard/core/settings.py` — `cors_origins: list[str]`
- `gard/api/app.py` — register CORS middleware
- `ROADMAP.md` — F11 row
- `README.md` — pointer to `web/` quickstart

**Unchanged**

- All lifecycle controllers, MCP server, NetBox integration semantics
- Postgres schema (no F11 migrations)

## PR slices

| Slice | Scope |
|-------|-------|
| **11a** | ADR-0022, `web/` scaffold (Vite/React/TS/shadcn), sign-in + session, API client, Vite proxy, optional CORS, health smoke |
| **11b** | App shell (sidebar/header per design reference), dashboard page (KPI cards, posture chart, recent activity) |
| **11c** | Devices list (compliance/devices table, filters in URL) + device detail tabs |
| **11d** | Compliance + Readiness pages with run-evaluation mutations + import CSV dialog |
| **11e** | NetBox sync screen (pull + write-back report), Uplift list/detail, Audit viewer |
| **11f** | Playwright E2E, Vitest/MSW fixtures, CI workflow, quickstart validation, ROADMAP/docs |

## Complexity Tracking

No constitution violations requiring justification.

## Phase 0 & 1 outputs (this command)

| Artifact | Status |
|----------|--------|
| `research.md` | Complete (R-1..R-12) |
| `data-model.md` | Complete |
| `contracts/ui-routes.yaml` | Complete |
| `contracts/ui-api-map.yaml` | Complete |
| `quickstart.md` | Complete |
| `tasks.md` | Complete (55/55 shipped) |
| Implementation | shipped (`web/`, ADR-0022, `.github/workflows/web-ci.yml`) |

## Screen wireframe notes (planning reference)

Align with spec design reference — ecommerce kit → GARD:

```text
┌──────────────────────────────────────────────────────────────────┐
│ GARD Operator Portal          [lab]  operator@lab  lifecycle_admin│
├────────────┬─────────────────────────────────────────────────────┤
│ Dashboard  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐       │
│ Devices    │  │ 847    │ │ 72%    │ │ 18%    │ │ 612    │       │
│ Compliance │  │ Devices│ │Compliant│ │ Drifted│ │ Ready  │       │
│ Readiness  │  └────────┘ └────────┘ └────────┘ └────────┘       │
│ Uplift     │  ┌─────────────────────┐ ┌──────────────────────┐  │
│ NetBox     │  │ Posture mix (chart) │ │ Devices by site      │  │
│ Audit      │  └─────────────────────┘ └──────────────────────┘  │
│            │  Recent activity (imports / evals / syncs)          │
│            │  ┌────────────────────────────────────────────────┐ │
│            │  │ time │ actor │ action │ status badge           │ │
│            │  └────────────────────────────────────────────────┘ │
└────────────┴─────────────────────────────────────────────────────┘
```

Device list ≈ ecommerce **Products** table; device detail ≈ **Product detail** with tabs instead of gallery.

## Risks & mitigations

| Risk | Mitigation |
|------|------------|
| JWT paste UX friction | Document token issuance in quickstart; future SSO out of scope |
| RBAC mirror drift | CI contract test: extract Python permissions vs TS map |
| Dashboard fan-out latency | Parallel Query; defer BFF if profiling fails SC-003 |
| Device search limited | Client hostname filter v1; server search in future feature |
| shadcn setup churn | Pin component versions; copy only needed blocks |

## Next step

Run **`/speckit-tasks`** to generate dependency-ordered implementation tasks for slices 11a–11f.
