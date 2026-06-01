# ADR-0022 — Operator Web UI Boundary (Thin Client)

**Status**: Accepted
**Date**: 2026-05-31
**Decision-makers**: GARD core team
**Touches**: F11 (operator dashboard), F1–F10 REST API, ADR-0008 (auth/RBAC)
**Supersedes**: MVP deferral of production-grade UI (`gard-speckit-start/specs/04-mvp-scope.md`)
**Superseded by**: none

## Context

F1–F10 delivered lifecycle governance via REST API, MCP, and CLI. Operators need a browser workspace for posture at a glance, device triage, and guided mutations (import, evaluate, NetBox sync) without curl or Streamlit.

## Decision

### A. Thin client over existing API

- Operator portal lives in `web/` as a **TypeScript SPA** (Vite + React).
- All lifecycle truth and mutations flow through the **existing GARD FastAPI service** — no parallel business logic in the browser.
- UI displays API envelopes and triggers documented REST endpoints only (`specs/011-operator-dashboard/contracts/ui-api-map.yaml`).

### B. No Streamlit / Python rapid UI

- Streamlit and similar notebook-style Python UIs are **explicitly excluded** (user kickoff).

### C. Authentication v1

- Operators paste a **JWT bearer token** (issued via `POST /api/v1/admin/tokens` or lab bootstrap) at sign-in.
- Token stored in `sessionStorage`; roles decoded from JWT for **UX gating only** — GARD RBAC remains authoritative on every request.

### D. Visual reference

- Layout inspired by [Shadcn UI Kit E-commerce Dashboard](https://shadcnuikit.com/dashboard/ecommerce) — KPI cards, inventory table, status badges — mapped to GARD lifecycle vocabulary (not ecommerce copy).
- Implemented with open [shadcn/ui](https://ui.shadcn.com/) components + Tailwind.

### E. Deployment

- **Dev**: Vite proxy to GARD API (`/api` → uvicorn).
- **Prod**: Static `web/dist` behind nginx same-origin reverse proxy to GARD API.
- Optional `GARD_CORS_ORIGINS` for split-origin dev only.

### F. Scope boundaries (v1)

**In**: Dashboard, devices, compliance/readiness, NetBox sync visibility, uplift read, audit read, permission-gated mutations.

**Out**: MCP in browser, catalog YAML editing, firmware execution/provisioning, NetBox DCIM editing, SSO (unless pre-existing platform auth).

## Consequences

- Positive: Operators get daily workspace; backend unchanged except optional CORS.
- Negative: JWT paste UX until SSO; client RBAC mirror must stay synced with `gard/core/rbac.py` (contract test in CI).
- Neutral: Separate release artifact (`web/`) from Python service.

## Compliance

| Principle | Adherence |
|-----------|-----------|
| I Governance Before Execution | UI triggers gated API mutations only; no execution controls |
| II Desired vs Actual | No client-side drift computation |
| III Unknown First-Class | Posture badges show unknown/not-evaluated explicitly |
| V Evidence/Audit | Mutations use audited API; audit screen read-only |
