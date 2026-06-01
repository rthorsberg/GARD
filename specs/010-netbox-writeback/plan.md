# F10 — NetBox Lifecycle Write-Back: Implementation Plan

**Feature Branch**: `010-netbox-writeback`
**Status**: Draft
**Date**: 2026-06-01
**Inputs**: `spec.md`, `research.md` (R-1..R-10), `data-model.md`, `contracts/`, `quickstart.md`
**Constitution version**: 1.0.0
**Predecessors**: F7 (read sync), F9 (device-type bootstrap, write client), F3/F4 (evaluation summaries)
**Successor**: none planned

## Summary

F10 adds **post-sync write-back**: after a successful F7 pull reconcile, GARD publishes lifecycle metadata to NetBox for every linked device in the sync batch — **custom fields** (lifecycle state, compliance/readiness summaries, target firmware, eval timestamps) and **reconciled tags** (GARD-managed posture slugs). Mapping is lifecycle-as-code in `gard-catalog/netbox/write-back-manifest.yaml`. Dev/lab bootstrap CLI provisions NetBox custom fields; production operators provision manually. Phased HTTP **200** on partial write-back failure; tag reconciliation without field-style conflicts; no auto-eval on sync.

## Technical Context

| Aspect | Choice |
|---|---|
| Language | Python 3.12 (existing GARD stack) |
| Trigger | Post-sync hook in `netbox_sync_controller.run_sync()` after pull commit |
| Manifest | `gard-catalog/netbox/write-back-manifest.yaml` + JSON Schema in contracts |
| NetBox API | REST v4 — `PATCH /api/dcim/devices/{id}/` (`custom_fields`, `tags`); bootstrap `POST /api/extras/custom-fields/`, `/api/extras/tags/` |
| Write client | Reuse `gard/integrations/netbox/write_client.py` (F9); read client unchanged |
| Credentials | `GARD_NETBOX_TOKEN` (read pull), `GARD_NETBOX_WRITE_TOKEN` (write-back) |
| Auth format | NetBox v2 Bearer tokens via `gard/integrations/netbox/auth.py` |
| Conflict policy | Custom fields: conflict + skip; tags: reconcile (clarify session) |
| HTTP semantics | Pull success → 200; write-back failures in response body (FR-011a) |
| Dev bootstrap | `python -m gard netbox bootstrap-writeback-fields` |
| Testing | pytest contract (manifest schema) + integration (sync→write-back against dev NetBox) + unit (conflict/tag reconcile) |
| Scale | Same batch as F7 sync (`max_devices` bound) |

## Constitution Check

*GATE: Passed pre-Phase 0 and post-Phase 1 design.*

| Principle | F10 adherence |
|---|---|
| I — Governance Before Execution | Write-back publishes derived lifecycle metadata only; no firmware execution |
| II — Desired vs Actual | Writes **derived** summaries already computed by F3/F4 controllers; does not mutate GARD authoritative state |
| III — Unknown Is First-Class | `unknown_sentinel` in manifest for unevaluated devices |
| IV — Lifecycle-as-Code | Write-back manifest in `gard-catalog/netbox/`; reviewable diffs |
| V — Evidence/Audit | `netbox.writeback.*` audit events + evidence row with summary counts |
| VI — Curated MCP | No new MCP tools; optional future delegate deferred |
| VII — Integration Over Replacement | NetBox remains identity SoT; GARD writes only declared lifecycle mirror fields |

**Post-design re-check**: Write-back extends F7 sync but uses separate write token and manifest allow-list. ADR-0017 read-only pull client preserved. ADR-0021 documents new write boundary. No constitutional violation.

## Project Structure

### Documentation (this feature)

```text
specs/010-netbox-writeback/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── write-back-manifest.schema.yaml
│   ├── write-back-manifest.yaml      # reference; canonical in gard-catalog/
│   └── rest-openapi.yaml             # F10 extensions to sync response
└── tasks.md                          # /speckit-tasks (not yet)
```

### Source Code (repository root)

**New**

- `adr/ADR-0021-netbox-lifecycle-writeback.md`
- `gard-catalog/netbox/write-back-manifest.yaml`
- `gard/integrations/netbox/writeback_manifest.py` — load/validate manifest
- `gard/integrations/netbox/writeback_publisher.py` — build payloads, conflict check, PATCH devices
- `gard/integrations/netbox/field_bootstrap.py` — dev custom field + tag provisioning
- `gard/cli/netbox_writeback_bootstrap.py` — `bootstrap-writeback-fields` CLI
- `gard/db/migrations/versions/0011_netbox_writeback_counts.py` — optional sync run columns + `devices.netbox_last_writeback_at`
- `tests/contract/test_netbox_writeback_manifest.py`
- `tests/unit/test_writeback_publisher.py`
- `tests/integration/test_netbox_writeback_sync.py`

**Extended**

- `gard/core/netbox_sync_controller.py` — post-sync write-back phase, report aggregation
- `gard/api/schemas/netbox_integration.py` — `WritebackReportOut`, extend sync envelope
- `gard/api/routers/netbox_integration.py` — `confirm_writeback` query param, phased 200
- `gard/core/settings.py` — `netbox_write_token`, `netbox_writeback_enabled`
- `gard/__main__.py` — `netbox bootstrap-writeback-fields` subcommand
- `deploy/scripts/sync-gard-netbox.sh` — bootstrap fields step before sync
- `deploy/scripts/seed-netbox.sh` — optional call to field bootstrap
- `specs/007-netbox-integration-read/quickstart.md` — write-back section
- `ROADMAP.md` — F10 status

**Unchanged**

- `gard/integrations/netbox/client.py` — GET-only F7 read guard
- F3/F4 evaluation controllers — no auto-invoke from sync

## PR slices

| Slice | Scope |
|---|---|
| **10a** | ADR-0021, spec/plan/research, manifest schema + canonical YAML, contract tests |
| **10b** | Manifest loader + publisher + sync controller hook + REST schema |
| **10c** | Dev field bootstrap CLI + deploy script integration + integration tests |
| **10d** | Prod confirm guard, docs, ROADMAP, migration for sync run counts |

## Complexity Tracking

No constitution violations requiring justification.

## Phase 0 & 1 outputs (this command)

| Artifact | Status |
|---|---|
| `research.md` | Complete (R-1..R-10) |
| `data-model.md` | Complete |
| `contracts/` | Complete (manifest schema + OpenAPI extension) |
| `quickstart.md` | Complete |
| `gard-catalog/netbox/write-back-manifest.yaml` | Complete |
| `tasks.md` | Pending `/speckit-tasks` |
