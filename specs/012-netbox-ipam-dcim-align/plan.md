# F12 — NetBox IPAM & DCIM Alignment: Implementation Plan

**Feature Branch**: `012-netbox-ipam-dcim-align`
**Status**: Draft
**Date**: 2026-06-02
**Inputs**: `spec.md`, `research.md` (R-1..R-12), `data-model.md`, `contracts/`, `quickstart.md`
**Constitution version**: 1.0.0
**Predecessors**: F7 (read sync), F10 (write-back), F11 (operator portal)
**Successor**: none planned

## Summary

F12 extends the NetBox sync pipeline with a **post-reconcile IPAM alignment phase**: for every NetBox-linked device, GARD pulls interfaces, IP addresses, VRF/VLAN context, and (when available) L2VPN/route-target metadata from NetBox, compares against GARD `management_ip` and a lifecycle-as-code **alignment policy manifest**, persists findings + network snapshots, and surfaces results in the sync report, REST list endpoints, and operator portal. v1 is **read-only toward NetBox** (no IPAM mutations); optional alignment summary fields extend F10 write-back.

## Technical Context

| Aspect | Choice |
|---|---|
| Language | Python 3.12 (existing GARD stack) |
| Trigger | Post-reconcile hook in `netbox_sync_controller.run_sync()` before F10 write-back |
| Policy manifest | `gard-catalog/netbox/alignment-policy-manifest.yaml` + JSON Schema in contracts |
| NetBox API | REST v4 — `dcim/interfaces`, `ipam/ip-addresses`, `ipam/vrfs`, `ipam/vlans`, optional `plugins/l2vpn/*` |
| Read client | Extend `gard/integrations/netbox/client.py` (GET-only guard preserved) |
| Collector | `gard/integrations/netbox/ipam_collector.py` — batch prefetch by device/site |
| Controller | `gard/core/ipam_alignment_controller.py` — evaluate policies, persist findings |
| DB | PostgreSQL 16, migration `0012_ipam_alignment.py` |
| REST | Extend sync envelope; `GET .../alignment/findings`, `GET /devices/{id}/network-context` |
| Web | Extend `web/src/routes/netbox.tsx`, device detail Network tab |
| Write-back | Optional F10 manifest extension (`gard_ipam_alignment_status`, tag `gard-ipam-mismatch`) |
| Testing | pytest contract (manifest + finding kinds + OpenAPI) + integration (sync→align) + unit (mgmt IP resolver, policy eval) |
| Scale | Same batch cap as F7; ≤50% sync overhead for 100 devices (SC-003) |
| Feature flag | `GARD_NETBOX_IPAM_ALIGNMENT_ENABLED` (default true) |

## Constitution Check

*GATE: Passed pre-Phase 0 and post-Phase 1 design.*

| Principle | F12 adherence |
|---|---|
| I — Governance Before Execution | Alignment is observe/compare only; no device or NetBox mutations in v1 |
| II — Desired vs Actual | Findings derived from NetBox snapshots vs GARD fields + policy manifest; inputs cited in JSONB |
| III — Unknown Is First-Class | `missing_in_gard`, `missing_in_netbox`, `ambiguous` surfaced explicitly; no silent IP coercion |
| IV — Lifecycle-as-Code | Alignment policy manifest in `gard-catalog/netbox/`; finding kinds in contracts |
| V — Evidence/Audit | `netbox.ipam_alignment.*` audit + evidence per run |
| VI — Curated MCP | No raw NetBox proxy; optional read delegate deferred to tasks phase |
| VII — Integration Over Replacement | NetBox owns IPAM/DCIM; GARD validates alignment only |

**Post-design re-check**: Pipeline order pull → align → write-back preserves F7 read-only client. ADR-0023 documents alignment boundary. No constitutional violation.

## Project Structure

### Documentation (this feature)

```text
specs/012-netbox-ipam-dcim-align/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── alignment-policy-manifest.schema.yaml
│   ├── alignment-policy-manifest.yaml      # reference; canonical in gard-catalog/
│   ├── finding-kinds.yaml
│   └── rest-openapi.yaml
└── tasks.md                                  # /speckit-tasks (not yet)
```

### Source Code (repository root)

**New**

- `adr/ADR-0023-netbox-ipam-dcim-alignment.md`
- `gard-catalog/netbox/alignment-policy-manifest.yaml`
- `gard/integrations/netbox/alignment_manifest.py` — load/validate manifest
- `gard/integrations/netbox/ipam_collector.py` — NetBox IPAM/DCIM fetch + normalize
- `gard/core/ipam_alignment_controller.py` — evaluate + persist
- `gard/models/ipam_alignment_run.py`, `ipam_alignment_finding.py`, `device_network_context.py`
- `gard/db/migrations/versions/0012_ipam_alignment.py`
- `gard/api/schemas/ipam_alignment.py`
- `tests/contract/test_netbox_alignment_manifest.py`
- `tests/contract/test_ipam_alignment_openapi.py`
- `tests/unit/test_ipam_mgmt_ip_resolver.py`
- `tests/unit/test_ipam_alignment_policies.py`
- `tests/integration/test_netbox_ipam_alignment.py`
- `deploy/scripts/fixtures/netbox-ipam-drift/` — lab NetBox seed notes (optional)

**Extended**

- `gard/integrations/netbox/client.py` — interfaces, ip-addresses, vrf, vlan list helpers
- `gard/core/netbox_sync_controller.py` — alignment phase between reconcile and write-back
- `gard/api/routers/netbox_integration.py` — findings list endpoint
- `gard/api/routers/devices.py` — network-context endpoint
- `gard/api/schemas/netbox_integration.py` — `IpamAlignmentReportOut`
- `gard/core/settings.py` — alignment enabled, manifest path, prefetch concurrency
- `gard-catalog/netbox/write-back-manifest.yaml` — optional alignment fields (slice 12d)
- `web/src/routes/netbox.tsx` — alignment summary
- `web/src/routes/devices/detail.tsx` + Network tab component
- `web/src/api/hooks/useIpamAlignment.ts`, `useDeviceNetworkContext.ts`
- `ROADMAP.md` — F12 row

**Unchanged**

- F7 read-only HTTP method guard
- F3/F4 evaluation controllers — alignment does not trigger eval

## PR slices

| Slice | Scope |
|---|---|
| **12a** | ADR-0023, spec/plan/research, manifest schema + canonical YAML, finding-kinds contract, contract tests |
| **12b** | Migration, models, ipam_collector, mgmt IP resolver, alignment controller unit tests |
| **12c** | Sync controller hook, REST extensions, integration tests against dev NetBox |
| **12d** | F11 UI (NetBox page + device Network tab), optional F10 manifest fields, quickstart, ROADMAP |

## Complexity Tracking

No constitution violations requiring justification.

## Phase 0 & 1 outputs (this command)

| Artifact | Status |
|---|---|
| `research.md` | Complete (R-1..R-12) |
| `data-model.md` | Complete |
| `contracts/` | Complete (manifest schema, finding kinds, OpenAPI extension) |
| `quickstart.md` | Complete |
| `gard-catalog/netbox/alignment-policy-manifest.yaml` | Complete (canonical); verify in T005 |
| `tasks.md` | Complete (51 tasks, T001–T051) |

## What connects IPAM to DCIM (design answer)

NetBox already links the domains; F12 makes GARD **verify** those links on every sync:

```text
dcim.Device
  ├── primary_ip4 / oob_ip ──────────▶ ipam.IPAddress (device-level)
  └── dcim.Interface[]
        ├── ipam.IPAddress[] (assigned_object)
        ├── ipam.VRF
        ├── ipam.VLAN (untagged / tagged)
        └── plugins.l2vpn.Termination ─▶ route-targets / EVPN service
```

GARD pulls this graph, compares to GARD `Device.management_ip` and manifest expectations, and reports gaps — the operational bridge between “device inventory” and “network identity is correct.”
