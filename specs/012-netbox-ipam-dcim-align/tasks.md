# F12 — NetBox IPAM & DCIM Alignment: Implementation Tasks

**Generated**: 2026-06-02 by `/speckit-tasks`
**Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md)
**Research**: [research.md](./research.md) | **Contracts**: [contracts/](./contracts/)

**Conventions**:
- `[P]` — parallelisable (different files, no dependency on an unfinished task)
- `[US1]` … `[US5]` — task belongs to a user-story phase
- `T001..` — sequential IDs in execution order
- Test tasks included (constitution contract/integration coverage; spec independent-test criteria)

**PR slices**: **12a** (T001–T006), **12b** (T007–T018), **12c** (T019–T033), **12d** (T034–T051)

Status: `[ ]` pending · `[x]` done

---

## Phase 1 — Setup (slice 12a)

**Purpose**: Design artefacts, ADR, manifest schema, finding-kind contract, and canonical catalog before alignment code.

- [x] T001 Verify feature spec at `specs/012-netbox-ipam-dcim-align/spec.md` (clarify session 2026-06-02: REST-only, no Orb/Diode/Branching in F12)
- [x] T002 Verify plan + research at `specs/012-netbox-ipam-dcim-align/plan.md` and `specs/012-netbox-ipam-dcim-align/research.md` (R-1..R-12)
- [x] T003 [P] Verify manifest schema at `specs/012-netbox-ipam-dcim-align/contracts/alignment-policy-manifest.schema.yaml`, reference copy at `specs/012-netbox-ipam-dcim-align/contracts/alignment-policy-manifest.yaml`, and canonical manifest at `gard-catalog/netbox/alignment-policy-manifest.yaml`
- [x] T004 [P] Verify finding kinds contract at `specs/012-netbox-ipam-dcim-align/contracts/finding-kinds.yaml` matches closed enum in `specs/012-netbox-ipam-dcim-align/data-model.md`
- [x] T005 [P] Author `adr/ADR-0023-netbox-ipam-dcim-alignment.md` — REST read from NetBox `main`, alignment phase ordering (pull → align → write-back), Orb/Diode/Branching as upstream ecosystem (FR-016/017), no Diode/Orb integration
- [x] T006 [P] Verify requirements checklist at `specs/012-netbox-ipam-dcim-align/checklists/requirements.md` (update if clarify session adds items)

---

## Phase 2 — Foundational (blocking prerequisites)

**Purpose**: Migration, models, manifest loader, NetBox client extensions, collector skeleton, API schemas, contract tests. **Blocks all user stories.**

**Checkpoint**: `load_alignment_manifest()` validates `gard-catalog/netbox/alignment-policy-manifest.yaml`; contract tests pass without NetBox; migration applies cleanly.

- [x] T007 [P] Add `netbox_ipam_alignment_enabled`, `netbox_alignment_manifest_path`, `netbox_ipam_prefetch_concurrency` in `gard/core/settings.py`
- [x] T008 [P] Implement `gard/integrations/netbox/alignment_manifest.py` — load canonical manifest, JSON Schema validation, site/role/vrf/vlan_group catalogue checks (FR-015 fail-closed)
- [x] T009 [P] Extend `gard/integrations/netbox/client.py` — GET helpers for `dcim/interfaces/`, `ipam/ip-addresses/`, `ipam/vrfs/`, `ipam/vlans/`, `ipam/vlan-groups/`; preserve read-only method guard
- [x] T010 [P] Add migration `gard/db/migrations/versions/0012_ipam_alignment.py` — tables `ipam_alignment_runs`, `ipam_alignment_findings`, `device_network_contexts`; optional `devices.netbox_last_alignment_at`, `devices.netbox_alignment_status`
- [x] T011 [P] Add ORM models `gard/models/ipam_alignment_run.py`, `gard/models/ipam_alignment_finding.py`, `gard/models/device_network_context.py`; export in `gard/models/__init__.py`
- [x] T012 [P] Implement `gard/integrations/netbox/ipam_collector.py` — batch fetch interfaces + IP addresses per device id list; normalize to collector dataclasses; site-scoped VRF/VLAN prefetch hooks
- [x] T013 [P] Add Pydantic models in `gard/api/schemas/ipam_alignment.py` per `specs/012-netbox-ipam-dcim-align/contracts/rest-openapi.yaml` (`IpamAlignmentSummary`, `IpamAlignmentFindingOut`, `DeviceNetworkContextOut`, etc.)
- [x] T014 [P] Extend `gard/api/schemas/netbox_integration.py` with `IpamAlignmentReportOut` and embed in sync report envelope
- [x] T015 [P] Implement `tests/contract/test_netbox_alignment_manifest.py` — schema validation, unique policy ids, broken manifest fails, catalogue site/role references
- [x] T016 [P] Implement `tests/contract/test_ipam_alignment_openapi.py` — lock response shapes for sync extension, findings list, network-context endpoint
- [x] T017 [P] Implement `tests/contract/test_finding_kinds.py` — assert application `AlignmentFindingKind` enum matches `specs/012-netbox-ipam-dcim-align/contracts/finding-kinds.yaml`
- [x] T018 Implement `gard/core/ipam_alignment_controller.py` skeleton — `run_alignment()`, create `IpamAlignmentRun`, iterate linked devices, delegate to evaluators (stubs OK until US1)

---

## Phase 3 — US1 (P1): Management IP matches device record 🎯 MVP

**Story goal**: Compare GARD `management_ip` to NetBox canonical management/primary IP; emit explicit findings for match, mismatch, missing, ambiguous.

**Independent test criterion**: `tests/unit/test_ipam_mgmt_ip_resolver.py` — device with matching IPs → `mgmt_ip_match`; deliberate mismatch → `mgmt_ip_mismatch`; dual primary candidates → `mgmt_ip_ambiguous` (SC-004).

### US1 — Tests first

- [x] T019 [P] [US1] Implement `tests/unit/test_ipam_mgmt_ip_resolver.py` — resolution order (primary_ip4 → oob → mgmt_only interface → name patterns → fallback); IPv4/IPv6 preference; ambiguous detection

### US1 — Implementation

- [x] T020 [US1] Implement `resolve_mgmt_ip()` in `gard/core/ipam_alignment_controller.py` (or `gard/integrations/netbox/ipam_collector.py`) per research R-2 and manifest `mgmt_ip` section
- [x] T021 [US1] Implement mgmt IP finding emitters (`mgmt_ip_match`, `mgmt_ip_mismatch`, `mgmt_ip_missing_in_netbox`, `mgmt_ip_missing_in_gard`, `mgmt_ip_ambiguous`, `mgmt_ip_fallback_used`) in `gard/core/ipam_alignment_controller.py`
- [x] T022 [US1] Wire mgmt IP evaluation into `run_alignment()` for each NetBox-linked device; persist findings to `ipam_alignment_findings` and `resolved_mgmt_ip` on `device_network_contexts`
- [x] T023 [US1] Do **not** auto-update `Device.management_ip` (research R-8); store NetBox value in `gard_observed` / network context only

**Checkpoint**: MVP backend — alignment run produces mgmt IP findings for linked devices (callable from tests without full sync).

---

## Phase 4 — US2 (P1): Interface addresses bind DCIM to IPAM

**Story goal**: List per-interface IP assignments; validate binding integrity and policy-required addresses; detect cross-device conflicts.

**Independent test criterion**: Unit tests — interface with bound IP → `interface_ip_bound`; policy-required port without IP → `interface_missing_address`; same host on two devices → `cross_device_address_conflict`.

### US2 — Tests + implementation

- [x] T024 [P] [US2] Extend `tests/unit/test_ipam_alignment_policies.py` — interface `require_ip` policy, cross-device IP conflict, prefix/VRF scope mismatch fixtures
- [x] T025 [US2] Extend `gard/integrations/netbox/ipam_collector.py` — build per-device interface graph with addresses, primary/secondary, VRF on interface; detect shared addresses across batch
- [x] T026 [US2] Implement interface/IPAM findings (`interface_ip_bound`, `interface_missing_address`, `prefix_vrf_scope_mismatch`, `cross_device_address_conflict`, `shared_address`) in `gard/core/ipam_alignment_controller.py`
- [x] T027 [US2] Populate `device_network_contexts.interfaces` JSONB with normalized interface records (FR-001, FR-004)

**Checkpoint**: Device network context includes interfaces + addresses; interface-level findings persist.

---

## Phase 5 — US5 (P1): Operator visibility and sync summary

**Story goal**: Alignment runs after reconcile in sync pipeline; sync report + list endpoints + operator portal surfaces findings; audit/evidence emitted.

**Independent test criterion**: `tests/integration/test_netbox_ipam_alignment.py` — sync returns `ipam_alignment` block; findings list endpoint returns planted mismatch; device network-context endpoint returns interface snapshot (SC-001, SC-005, SC-006).

### US5 — Integration + API

- [x] T028 [US5] Extend `gard/core/netbox_sync_controller.py` — invoke alignment after successful reconcile, **before** F10 write-back; skip on pull failure; attach `IpamAlignmentReport` to `NetboxSyncReport`; respect `GARD_NETBOX_IPAM_ALIGNMENT_ENABLED`
- [x] T029 [US5] Extend `gard/api/routers/netbox_integration.py` — return sync envelope with `report.ipam_alignment`; paginate truncated entries (cap 100)
- [x] T030 [P] [US5] Add `GET /api/v1/integrations/netbox/alignment/findings` in `gard/api/routers/netbox_integration.py` with filters (`run_id`, `device_id`, `severity`, pagination)
- [x] T031 [P] [US5] Add `GET /api/v1/devices/{device_id}/network-context` in `gard/api/routers/devices.py` — latest snapshot by `captured_at`
- [x] T032 [US5] Emit audit events `netbox.ipam_alignment.started|completed|failed` and evidence type `netbox_ipam_alignment` in `gard/core/ipam_alignment_controller.py` (FR-012)

### US5 — Tests + UI

- [x] T033 [P] [US5] Implement `tests/integration/test_netbox_ipam_alignment.py` — sync + alignment against dev NetBox (skip if unavailable); assert summary counts and findings endpoint
- [x] T034 [P] [US5] Add `web/src/api/hooks/useIpamAlignment.ts` and `web/src/api/hooks/useDeviceNetworkContext.ts`; extend `web/src/api/types/index.ts`
- [x] T035 [US5] Extend `web/src/routes/netbox.tsx` — alignment summary cards and findings drill-down after sync
- [x] T036 [US5] Add Network tab to device detail (`web/src/components/devices/DeviceNetworkTab.tsx`, wire in `web/src/routes/devices/detail.tsx`) — findings list + interface table

**Checkpoint**: End-to-end operator flow — sync → see alignment on NetBox page and device detail.

---

## Phase 6 — US3 (P2): VRF and route-target consistency

**Story goal**: Evaluate interface VRF against manifest expectations; correlate L2VPN/EVPN route-targets when plugin available.

**Independent test criterion**: Unit tests — wrong VRF on mgmt interface → `vrf_mismatch`; missing RT on service participant → `rt_missing_on_interface`; no L2VPN plugin → single `l2vpn_module_unavailable` run finding.

### US3 — Implementation

- [x] T037 [P] [US3] Extend `tests/unit/test_ipam_alignment_policies.py` — vrf_expectations and overlay_expectations eval cases
- [x] T038 [US3] Extend `gard/integrations/netbox/ipam_collector.py` — probe L2VPN plugin availability; fetch L2VPN/EVPN services and route-targets when present; graceful degrade (R-6)
- [x] T039 [US3] Implement VRF/overlay findings (`vrf_mismatch`, `vrf_orphaned_in_site`, `overlay_rt_aligned`, `rt_missing_on_interface`, `rt_import_missing`, `rt_export_missing`, `l2vpn_module_unavailable`) in `gard/core/ipam_alignment_controller.py`
- [x] T040 [US3] Populate `device_network_contexts.overlay_bindings` JSONB and correlate service endpoints to synced devices (FR-007, FR-008)

**Checkpoint**: VRF and overlay alignment findings appear for lab devices with seeded drift.

---

## Phase 7 — US4 (P2): VLAN and L2 domain alignment

**Story goal**: Capture untagged/tagged VLANs per interface; validate against site VLAN group scope and access-port policy.

**Independent test criterion**: Unit tests — access port without VLAN → `access_vlan_missing`; VLAN outside group → `vlan_out_of_scope`.

### US4 — Implementation

- [x] T041 [P] [US4] Extend `tests/unit/test_ipam_alignment_policies.py` — vlan_expectations and access_interface_pattern cases
- [x] T042 [US4] Extend `gard/integrations/netbox/ipam_collector.py` — untagged/tagged VLAN normalization on interfaces; site VLAN group membership lookup
- [x] T043 [US4] Implement VLAN findings (`access_vlan_missing`, `vlan_out_of_scope`, `vlan_aligned`) in `gard/core/ipam_alignment_controller.py` (FR-006)

**Checkpoint**: Full alignment taxonomy operational for mgmt IP, interface IPAM, VRF/RT, VLAN.

---

## Phase 8 — Polish & cross-cutting (slice 12d)

**Purpose**: Optional write-back mirror, lab fixtures, docs, CI, roadmap.

- [x] T044 [P] Extend `gard-catalog/netbox/write-back-manifest.yaml` with optional `gard_ipam_alignment_status` custom field and `gard-ipam-mismatch` tag rule (FR-013)
- [x] T045 [P] Extend `gard/integrations/netbox/writeback_publisher.py` — resolve alignment summary from latest `IpamAlignmentRun` / device cache for write-back sources
- [x] T046 [P] Add `deploy/scripts/fixtures/netbox-ipam-drift/README.md` — document planted drift scenarios for integration tests (SC-002)
- [x] T047 Update `specs/012-netbox-ipam-dcim-align/quickstart.md` and `deploy/netbox/README.md` — Orb→Diode→NetBox upstream path; sync against merged `main` only; pointer to future NetBox-platform spec
- [x] T048 Update `specs/007-netbox-integration-read/quickstart.md` — cross-link F12 alignment section
- [x] T049 Update `ROADMAP.md` — mark F12 **shipped** when complete
- [x] T050 Run `uv run ruff check .`, `uv run mypy gard`, `uv run pytest tests/contract/test_netbox_alignment_manifest.py tests/contract/test_ipam_alignment_openapi.py tests/unit/test_ipam_mgmt_ip_resolver.py tests/integration/test_netbox_ipam_alignment.py -q`
- [x] T051 Mark all tasks `[x]` in this file when implementation complete

---

## Dependencies & Execution Order

### Phase Dependencies

```text
Phase 1 (Setup)
    ↓
Phase 2 (Foundational) — BLOCKS all user stories
    ↓
Phase 3 (US1 mgmt IP) — MVP backend
    ↓
Phase 4 (US2 interface IPAM) — extends collector + findings
    ↓
Phase 5 (US5 visibility) — sync hook + REST + UI (needs US1+US2 findings for meaningful demo)
    ↓
Phase 6 (US3 VRF/RT) ─┐
Phase 7 (US4 VLAN)    ─┴─ parallel after Phase 5 API stable
    ↓
Phase 8 (Polish)
```

### User Story Dependencies

| Story | Depends on | Notes |
|-------|------------|-------|
| US1 | Phase 2 | MVP; no other stories required |
| US2 | Phase 2, US1 collector wiring | Shares `ipam_collector` and controller |
| US5 | US1 + US2 (minimal findings) | UI/API can stub until US1 done, but E2E needs findings |
| US3 | Phase 2, US2 interface graph | Overlay correlates to interfaces |
| US4 | Phase 2, US2 interface graph | VLAN data on interfaces |

### Parallel Opportunities

**Phase 1**: T003–T006 in parallel after T001–T002.

**Phase 2**: T007–T017 all marked [P] except T018 (integrates stubs).

**After Phase 2**:
- Track A: US1 (T019–T023) → US2 (T024–T027) → US5 backend (T028–T033)
- Track B (after T013): T034 UI hooks can start in parallel with US3/US4 backend work

**Phase 6 + 7**: T037–T040 and T041–T043 can run in parallel on different files.

---

## Parallel Example: Phase 2

```bash
# Manifest + client + models in parallel:
T008 gard/integrations/netbox/alignment_manifest.py
T009 gard/integrations/netbox/client.py
T010 gard/db/migrations/versions/0012_ipam_alignment.py
T011 gard/models/ipam_alignment_*.py
T015 tests/contract/test_netbox_alignment_manifest.py
T016 tests/contract/test_ipam_alignment_openapi.py
```

---

## Implementation Strategy

### MVP First (US1 + US5 minimal)

1. Complete Phase 1–2 (foundation)
2. Complete Phase 3 (US1 mgmt IP findings)
3. Complete Phase 5 sync hook + REST only (T028–T032, skip UI T034–T036 initially)
4. **Validate**: unit tests + integration test for mgmt IP mismatch in sync report
5. Add US2, then full US5 UI

### Incremental Delivery (matches PR slices)

| Slice | Delivers |
|-------|----------|
| **12a** | ADR-0023, contracts, manifest, contract tests (T001–T006, T015–T017) |
| **12b** | DB, collector, US1+US2 evaluators, unit tests (T007–T027) |
| **12c** | Sync hook, REST, integration tests, US3+US4 (T028–T043) |
| **12d** | UI, write-back extension, docs, CI (T034–T051) |

### Suggested MVP Scope

**User Story 1 (management IP alignment)** plus **US5 sync report API** (without full portal) — satisfies SC-001 and SC-004 with smallest vertical slice.

---

## Task Summary

| Phase | Tasks | Story |
|-------|-------|-------|
| 1 Setup | T001–T006 (6) | — |
| 2 Foundational | T007–T018 (12) | — |
| 3 US1 | T019–T023 (5) | Management IP |
| 4 US2 | T024–T027 (4) | Interface IPAM |
| 5 US5 | T028–T036 (9) | Operator visibility |
| 6 US3 | T037–T040 (4) | VRF / route-target |
| 7 US4 | T041–T043 (3) | VLAN |
| 8 Polish | T044–T051 (8) | — |
| **Total** | **51 tasks** | |

**Parallel opportunities**: 28 tasks marked `[P]`

**Independent test criteria**:
- **US1**: `tests/unit/test_ipam_mgmt_ip_resolver.py`
- **US2**: `tests/unit/test_ipam_alignment_policies.py` (interface section)
- **US5**: `tests/integration/test_netbox_ipam_alignment.py` + portal NetBox/device pages
- **US3**: `tests/unit/test_ipam_alignment_policies.py` (VRF/overlay section)
- **US4**: `tests/unit/test_ipam_alignment_policies.py` (VLAN section)

---

## Notes

- F12 reads NetBox REST **`main` only** — no Orb, Diode, or Branching API integration (see ADR-0023, spec FR-016).
- Alignment phase order: **pull → align → write-back** (research R-3).
- Do not auto-mutate NetBox or GARD `management_ip` in v1.
- Optional MCP delegate `get_ipam_alignment_summary` deferred post-v1 unless added in Polish phase.
