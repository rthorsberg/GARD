# F11 — Operator Dashboard & Web UI

## TL;DR

Browser-based operator portal on top of GARD F1–F10: dashboard posture at a glance, device search/detail, compliance/readiness/uplift views, NetBox sync visibility, and permission-aware guided actions. TypeScript preferred; **no Streamlit**.

## Status

| Artifact | Status | Updated | Notes |
|----------|--------|---------|-------|
| spec.md | drafted | 2026-05-31 | `/speckit-specify` — UI IA, design reference (shadcn e-commerce kit), 5 user stories |
| plan.md | drafted | 2026-05-31 | `/speckit-plan` — Vite/React/TS/shadcn thin client, slices 11a–11f |
| research.md | done | 2026-05-31 | R-1..R-12 |
| data-model.md | done | 2026-05-31 | Frontend view models + optional CORS |
| contracts/ | done | 2026-05-31 | ui-routes.yaml, ui-api-map.yaml |
| quickstart.md | done | 2026-05-31 | Dev proxy + nginx prod pattern |
| checklists/requirements.md | pass | 2026-05-31 | 16/16 |
| tasks.md | pending | — | `/speckit-tasks` |

## Timeline

- **2026-05-31** — F11 spec drafted on branch `011-operator-dashboard`. Kickoff: TypeScript web app, no Streamlit, consume existing GARD API.
- **2026-05-31** — Design reference added: [Shadcn UI Kit E-commerce Dashboard](https://shadcnuikit.com/dashboard/ecommerce) mapped to GARD dashboard, devices, and posture aggregates.
- **2026-05-31** — Plan complete (`/speckit-plan`): Vite/React/TS/shadcn thin client, research R-1..R-12, contracts, quickstart, PR slices 11a–11f.

## Scope guards

**In**: Dashboard, devices list/detail, compliance/readiness/uplift/NetBox/audit screens, RBAC-aware actions (import, evaluate, sync), loading/empty/error states.

**Out**: Streamlit, catalog YAML editor, MCP in browser, execution/provisioning, NetBox DCIM editing, mobile-native apps, SSO (unless pre-existing).

## Related references

- Prior MVP deferral: `gard-speckit-start/specs/04-mvp-scope.md`
- API surface: `gard-speckit-start/specs/09-api-surface.md`
- RBAC: `gard-speckit-start/specs/08-security-rbac-audit.md`
- F7 NetBox read: `specs/007-netbox-integration-read/`
- F10 write-back: `specs/010-netbox-writeback/`
