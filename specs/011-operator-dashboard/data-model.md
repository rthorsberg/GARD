# F11 — Data Model

F11 is a **thin client**. It does not introduce GARD Postgres tables or lifecycle business logic. This document defines **frontend view models** (TypeScript interfaces) and how they map to existing GARD API responses.

## Architecture boundary

```text
┌─────────────────────────────────────────────────────────┐
│  web/ (Operator Portal SPA)                             │
│  View models · React Query cache · Permission gate      │
└───────────────────────────┬─────────────────────────────┘
                            │ HTTPS + Bearer JWT
                            ▼
┌─────────────────────────────────────────────────────────┐
│  gard/ (existing FastAPI) — F1–F10                      │
│  Authoritative lifecycle state · RBAC · Audit             │
└─────────────────────────────────────────────────────────┘
```

## Operator session (client-only)

Persisted in `sessionStorage` under key `gard.session`.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `apiBaseUrl` | string | yes | e.g. `""` (same-origin) or `http://127.0.0.1:8080` |
| `token` | string | yes | JWT bearer (never logged) |
| `subject` | string | yes | From JWT `sub` |
| `roles` | string[] | yes | From JWT `roles` claim |
| `expiresAt` | ISO datetime | yes | From JWT `exp`; trigger re-auth when past |
| `environment` | string | no | Operator label (`lab`, `prod`) — UI-only badge |

**Validation**: On app boot, `GET /healthz` (or `/api/v1/...` with token) validates connectivity; invalid/expired token clears session and redirects to `/sign-in`.

## Dashboard snapshot (derived client aggregate)

Built by merging parallel API responses; not persisted.

| Field | Type | Source API |
|-------|------|------------|
| `totalDevices` | number | `compliance.summary.total_devices` or sum of drift buckets |
| `complianceBuckets` | DriftCounts | `GET /api/v1/compliance/summary` |
| `readinessBuckets` | ReadinessCounts | `GET /api/v1/readiness/summary` |
| `netboxLinked` | number | `GET /api/v1/integrations/netbox/summary` → `netbox_linked` |
| `csvOnly` | number | same → `csv_only` |
| `lastNetboxSyncAt` | datetime \| null | same → `last_sync_at` |
| `recentActivity` | AuditEntrySummary[] | `GET /api/v1/audit?limit=10` |
| `fetchedAt` | datetime | client timestamp for staleness hint |

**Validation rules**:
- Unknown/not-evaluated counts MUST display explicitly (never omitted when API returns them).
- If any sub-request fails, dashboard shows partial data + per-widget error — not zeros.

## Device summary (list row)

Maps from `ComplianceDeviceRow` or `DeviceWithEnvelope`.

| Field | Type | Notes |
|-------|------|-------|
| `id` | uuid | Device PK |
| `hostname` | string | Primary display name |
| `vendor` | string | normalized preferred |
| `model` | string | normalized preferred |
| `site` | string | |
| `region` | string | optional |
| `currentFirmware` | string \| null | From latest observation |
| `complianceState` | enum | compliant \| outside_target \| unknown |
| `readinessState` | enum | ready_for_uplift \| blocked \| not_applicable \| unknown |
| `netboxLinked` | boolean | `source_system === 'netbox'` or netbox id present |
| `lastEvaluatedAt` | datetime \| null | |

**List state (URL query params)**:

| Param | Example | Maps to API query |
|-------|---------|-------------------|
| `q` | `edge-router` | client filter on hostname (until server search) |
| `compliance` | `outside_target` | `compliance_state` |
| `site` | `osl1` | `site` |
| `page` | `2` | cursor / page token |
| `limit` | `50` | `limit` (max 500) |

## Device lifecycle profile (detail aggregate)

Fetched on device detail route `/devices/:id`.

| Section | Source endpoint |
|---------|-----------------|
| Identity overview | `GET /api/v1/devices/{id}` |
| Compliance tab | `GET /api/v1/devices/{id}/compliance` |
| Readiness tab | `GET /api/v1/devices/{id}/readiness` |
| NetBox tab | Device facts + latest sync run if linked |

**Explainability**: Render `envelope.reasons[]`, `facts`, `recommended_actions` from API — do not synthesize drift explanations client-side (Constitution V).

## Action result (mutation feedback)

Normalized UI shape for import, evaluate, sync responses.

| Field | Type | Notes |
|-------|------|-------|
| `action` | enum | `import` \| `compliance_evaluate` \| `readiness_evaluate` \| `netbox_sync` |
| `status` | enum | `success` \| `partial` \| `failed` |
| `summary` | string | Human headline |
| `counts` | Record<string, number> | e.g. `{ updated: 12, failed: 1 }` |
| `errors` | string[] | Detail messages |
| `correlationId` | string \| null | From response header if exposed |
| `followUpLinks` | Link[] | `{ label, href }` to devices/audit |

## Sync report view

Maps `NetboxSyncEnvelope` from `POST .../sync` or `GET .../sync-runs/{id}`.

| Field | Type | Notes |
|-------|------|-------|
| `runId` | uuid | |
| `startedAt` / `finishedAt` | datetime | |
| `pullPhase` | ReconcileSummary | created/updated/skipped/failed |
| `writebackPhase` | WritebackSummary | F10 counts |
| `writebackEntries` | WritebackEntry[] | Truncated table with link to device |

## Audit entry (list/detail)

Maps `AuditPage.items[]`.

| Field | Type | Notes |
|-------|------|-------|
| `id` | uuid | |
| `timestamp` | datetime | |
| `actor` | string | |
| `action` | string | e.g. `compliance.evaluation_triggered` |
| `objectType` | string | |
| `objectId` | string | |
| `result` | string | |

## Uplift wave summary

Maps `WaveList` / `WaveEnvelope`.

| Field | Type | Notes |
|-------|------|-------|
| `id` | uuid | |
| `name` | string | |
| `status` | string | draft \| submitted \| approved \| … |
| `deviceCount` | number | |
| `updatedAt` | datetime | |

## Permission gate (client mirror)

Static map `Role → Permission[]` synced with `gard/core/rbac.py`. UI components:

- `CanAccess permission="compliance.evaluate"` — render children or fallback
- `NavItem` hidden when no read permission for domain

**Rule**: Client gate is optimistic UX only; API 403 always handled with toast + no state mutation.

## Optional backend addition (slice 11a, non-domain)

| Change | Location | Purpose |
|--------|----------|---------|
| CORS middleware | `gard/api/middleware/cors.py` | Optional split-origin dev |
| `GARD_CORS_ORIGINS` | `gard/core/settings.py` | Comma-separated allow list |

No new lifecycle tables or controllers.
