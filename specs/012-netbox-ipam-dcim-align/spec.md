# Feature Specification: NetBox IPAM & DCIM Alignment

**Feature Branch**: `012-netbox-ipam-dcim-align`
**Created**: 2026-06-02
**Status**: Draft
**Input**: User description: "In NetBox we should focus on IP address alignment, same with VRFs, route-targets, VLANs etc. What is needed to connect IPAM (and L2VPN) with DCIM so they both align?"

## Why this feature exists

F7–F10 established GARD as a NetBox-aware lifecycle platform: GARD **reads DCIM device identity**, bootstraps credible device types (F9), and **writes lifecycle metadata back** (F10). Operators can see firmware posture in NetBox, but **network identity context is still disconnected**:

> A device can exist in DCIM with a serial and site, while its management IP, interface addresses, VRF membership, VLAN assignments, and overlay identifiers (route-targets, EVPN/VNI) live in separate NetBox IPAM and L2VPN objects — or are missing, duplicated, or inconsistent.

NetBox is designed for DCIM and IPAM to reference each other (interfaces carry addresses; prefixes belong to VRFs; VLANs attach to interfaces; L2VPN services reference route-targets and endpoints). In practice, estates drift: CSV imports, manual edits, partial automation, and multi-team ownership leave **gaps between “the device exists” and “the network identity is correct.”**

F12 closes that gap for GARD operators by **pulling IPAM and overlay context from NetBox alongside DCIM**, validating cross-domain alignment, and surfacing actionable findings in GARD and (optionally) back to NetBox via the existing write-back channel.

GARD does **not** become an IPAM system. NetBox remains source-of-truth for addresses, VRFs, VLANs, and L2VPN services. GARD owns **alignment verdicts, evidence, and lifecycle-aware reporting** so firmware readiness work happens against devices whose network identity is trustworthy.

## User decisions (defaults for v1)

| Topic | Default |
|-------|---------|
| Direction | **Read-only from NetBox** for IPAM/L2VPN/DCIM objects; alignment findings stored in GARD |
| Trigger | **Post-sync extension** — runs after successful F7 device reconciliation in the same operator action |
| Remediation | **Report-only v1** — GARD does not auto-create or mutate NetBox IP/VRF/VLAN/RT objects |
| Write-back | **Optional summary mirror** — extend F10 manifest with alignment status fields/tags when enabled |
| Scope | **All NetBox-linked devices** in the sync batch |
| NetBox ecosystem | **REST read from NetBox `main` only** — no direct Orb, Diode, or Branching integration in F12 |

## Clarifications

### Session 2026-06-02

- Q: Should F12 integrate directly with NetBox Branching, Diode, or Orb, or stay REST-only against populated NetBox? → A: **REST-only from NetBox `main`** — document Orb/Diode/Branching as upstream/complementary ecosystem (per ADR-0018); no direct GARD integration in F12. Deploying and operating NetBox + Orb + Diode + Branching is a **separate NetBox-platform spec** (not mixed into GARD).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Management IP matches device record (Priority: P1)

A network operator syncs NetBox into GARD. For each linked device, GARD compares GARD’s stored management IP (from CSV import or prior sync) with NetBox’s designated primary/management IP assignment on the device or its management interface. Misalignments appear in the sync report and on the device detail view with a clear reason (missing in NetBox, missing in GARD, conflicting values, multiple candidates).

**Why this priority**: Management IP is the minimum viable join key between lifecycle operations and operational access; misalignment blocks safe uplift planning.

**Independent Test**: NetBox device `edge-osl-001` has primary IP `10.10.1.11/24` on `Management0`; GARD device has `management_ip=10.10.1.11` → alignment `pass`. Change GARD to `10.10.1.99` → alignment `mismatch` with both values cited.

**Acceptance Scenarios**:

1. **Given** NetBox assigns a primary IPv4 to a device’s management interface, **When** IPAM alignment runs after sync, **Then** GARD stores the NetBox-sourced management IP reference and marks alignment `pass` when it matches GARD’s value.
2. **Given** GARD has a management IP but NetBox has none on the device or its interfaces, **When** alignment runs, **Then** the finding is `missing_in_netbox` and recommended action suggests assigning IP in NetBox IPAM.
3. **Given** NetBox has a primary IP but GARD’s device row has null management IP, **When** alignment runs, **Then** GARD records `missing_in_gard` and may populate a read-only NetBox-sourced value for display without overwriting operator CSV authority until explicitly accepted.
4. **Given** NetBox lists two primary IP candidates on the same device, **When** alignment runs, **Then** the batch reports `ambiguous` for that device and does not silently pick a winner.

---

### User Story 2 - Interface addresses bind DCIM to IPAM (Priority: P1)

A platform engineer opens a synced device and sees each relevant NetBox interface with its assigned IP addresses (primary and secondary), VRF, and parent prefix. GARD flags interfaces that exist in DCIM but have no IPAM assignment where policy expects one, and IPAM assignments that point to non-existent or wrong interfaces.

**Why this priority**: Interface↔address binding is the core DCIM/IPAM linkage NetBox models; without it, “device exists” does not mean “reachable on the network.”

**Independent Test**: Device with `GigabitEthernet0/0/0` in NetBox DCIM and `10.10.1.11/24` assigned to that interface → `interface_ip_bound=pass`. Same IP assigned to a different device’s interface → `cross_device_conflict`.

**Acceptance Scenarios**:

1. **Given** a NetBox interface with one or more IP addresses in IPAM, **When** alignment runs, **Then** GARD links the address records to the device via the interface relationship and lists them on the device network tab.
2. **Given** an enabled interface on a production-role device with no IP assignment where site policy requires one, **When** alignment runs, **Then** GARD emits `interface_missing_address` with interface name and site/role context.
3. **Given** an IP address object in NetBox assigned to interface A but the address falls outside the VRF’s expected prefix scope for that site, **When** alignment runs, **Then** GARD emits `prefix_vrf_scope_mismatch` citing prefix, VRF, and site.
4. **Given** a secondary IP on an interface, **When** alignment runs, **Then** secondary addresses are listed and evaluated; primary selection rules follow NetBox designation (`primary` flag) when present.

---

### User Story 3 - VRF and route-target consistency (Priority: P2)

An operator responsible for MPLS/EVPN services reviews alignment for devices in a site. GARD shows each interface’s VRF membership and, where NetBox L2VPN/EVPN objects exist, the associated route-targets (import/export). Findings call out interfaces in the wrong VRF for their role, VRFs without expected route-targets for an L2VPN service, or route-targets referenced by a service but not present on any device interface in scope.

**Why this priority**: VRF/RT misalignment causes silent traffic black-holes; catching it before firmware uplift reduces change-window risk.

**Independent Test**: L2VPN service `evpn-osl-edge` defines RT `65000:100`; device interfaces in that service’s site/role carry matching import/export RT in NetBox → `overlay_rt_aligned=pass`. Remove RT from one interface → `rt_missing_on_interface`.

**Acceptance Scenarios**:

1. **Given** NetBox models VRF on an interface, **When** alignment runs, **Then** GARD records VRF name/identifier per interface and compares against site/role expectations from the alignment policy manifest.
2. **Given** an L2VPN/EVPN service in NetBox with import/export route-targets, **When** alignment runs, **Then** GARD correlates service endpoints to DCIM devices and verifies route-target presence on participating interfaces or VRFs.
3. **Given** a VRF exists in IPAM but no device interface in the sync batch references it, **When** alignment runs, **Then** GARD reports `vrf_orphaned_in_site` at informational severity (not a device blockers by default).
4. **Given** import and export route-targets differ on a symmetric service definition, **When** alignment runs, **Then** both are evaluated independently with explicit finding kinds.

---

### User Story 4 - VLAN and L2 domain alignment (Priority: P2)

A transport engineer validates L2 context before an access-switch firmware wave. GARD shows untagged and tagged VLANs per interface from NetBox, validates they belong to the expected VLAN group for the site, and flags access ports with missing access VLAN or trunk ports without allowed VLANs where policy requires them.

**Why this priority**: VLAN drift breaks site-local segmentation assumptions used in readiness rules and change windows.

**Independent Test**: Access interface with access VLAN `100` in NetBox VLAN group `Oslo-Access` → `vlan_aligned=pass`. Access interface with no untagged VLAN → `access_vlan_missing`.

**Acceptance Scenarios**:

1. **Given** NetBox interface mode/access/trunk data, **When** alignment runs, **Then** GARD captures untagged VLAN and tagged VLAN list per interface.
2. **Given** site policy expects access ports to have an access VLAN, **When** an access-mode interface has none, **Then** GARD emits `access_vlan_missing`.
3. **Given** a VLAN ID used on an interface is not defined in the site’s VLAN group, **When** alignment runs, **Then** GARD emits `vlan_out_of_scope`.
4. **Given** L2VPN pseudowire/EVPN VLAN bindings in NetBox, **When** alignment runs, **Then** GARD correlates service VLAN/VID to device interfaces participating in that service.

---

### User Story 5 - Operator visibility and sync summary (Priority: P1)

After sync, the operator portal NetBox page and device detail show alignment summary counts: passed, mismatched, missing, ambiguous; top finding kinds; drill-down to per-device findings. The sync API response includes an `ipam_alignment` section alongside existing reconciliation and write-back sections.

**Why this priority**: Findings only matter if operators see them where they already run sync and triage devices.

**Independent Test**: Sync report JSON includes `ipam_alignment.devices_checked`, `findings_by_kind`, and per-device finding list capped for pagination; dashboard widget shows non-zero mismatch count after seeding a deliberate drift fixture.

**Acceptance Scenarios**:

1. **Given** a completed sync with alignment enabled, **When** the operator opens the NetBox integration page, **Then** alignment summary matches the API sync report counts.
2. **Given** a device with alignment findings, **When** the operator opens device detail, **Then** network alignment findings appear with kind, severity, and remediation hint.
3. **Given** alignment findings exist, **When** audit/evidence is queried, **Then** a sync-scoped evidence record captures alignment counts and correlation id (no silent runs).

---

### Edge Cases

- **IPv6-only management**: Alignment evaluates IPv6 primary addresses with the same rules as IPv4; dual-stack reports both; mismatch if only one family aligns.
- **Anyccast / shared service IPs**: Addresses assigned to multiple interfaces or devices report `shared_address` informational finding; do not treat as automatic conflict without policy override.
- **VRRP/HSRP secondary**: Secondary addresses on the same interface are listed; primary selection follows NetBox flags.
- **Unnumbered / point-to-point interfaces**: Interfaces without IP where policy allows unnumbered are `not_applicable`, not failures.
- **Stale NetBox cache**: Alignment always uses data from the current sync pull; no stale cross-run comparisons.
- **NetBox missing L2VPN app**: Route-target checks degrade to VRF-only; report `l2vpn_module_unavailable` once per run, not per device failure.
- **NetBox Branching in use**: Operators MUST sync against merged `main` state; GARD does not read unmerged branch schemas in v1.
- **Large estates**: Alignment respects the same sync batch bounds as F7; partial runs document scope in the report.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: GARD MUST extend NetBox sync to pull, for each linked DCIM device, related IPAM address assignments reachable via NetBox interface relationships.
- **FR-002**: GARD MUST determine and compare a canonical management/primary IP for each device using NetBox primary IP designation when available, otherwise a documented fallback order (management interface → first loopback → first IP on enabled interface).
- **FR-003**: GARD MUST store alignment findings per device with closed finding kinds, severity, observed NetBox values, observed GARD values, and remediation hints.
- **FR-004**: GARD MUST validate interface↔address binding integrity (address points to existing interface; interface belongs to synced device).
- **FR-005**: GARD MUST ingest VRF membership per interface from NetBox and evaluate against a version-controlled **alignment policy manifest** (site/role expectations for VRF names or identifiers).
- **FR-006**: GARD MUST ingest VLAN assignments (untagged and tagged) per interface and evaluate against site VLAN group scope rules in the alignment policy manifest.
- **FR-007**: GARD MUST ingest L2VPN/EVPN service metadata (including route-target import/export where NetBox exposes it) and correlate services to synced devices by endpoint relationships defined in NetBox.
- **FR-008**: GARD MUST emit route-target alignment findings when a service’s expected route-targets are absent on participating device interfaces/VRFs.
- **FR-009**: Alignment MUST run automatically after successful device reconciliation in the same sync operation; it MUST NOT run if the DCIM pull fails or rolls back.
- **FR-010**: GARD MUST NOT create, update, or delete NetBox IPAM, VRF, VLAN, or L2VPN objects in v1.
- **FR-011**: Sync API and operator UI MUST expose alignment summary and per-device findings with pagination for large result sets.
- **FR-012**: Alignment runs MUST emit audit events and lifecycle evidence analogous to F7 sync (`netbox.ipam_alignment.completed` / `failed`).
- **FR-013**: GARD MAY extend F10 write-back manifest with optional alignment summary custom fields/tags (e.g., `gard_ipam_alignment_status`, `gard_primary_ip_mismatch`) when write-back is enabled; omission MUST NOT block alignment.
- **FR-014**: Ambiguous primary IP or cross-device address conflicts MUST be reported explicitly and MUST NOT silently resolve.
- **FR-015**: Alignment policy manifest validation MUST fail closed before sync when manifest entries reference undefined sites, roles, VRFs, or VLAN groups.
- **FR-016**: GARD MUST read IPAM/DCIM/L2VPN objects exclusively via NetBox REST against **`main`** (default branch); GARD MUST NOT integrate with Diode gRPC, Orb agent APIs, or NetBox Branching APIs in v1.
- **FR-017**: F12 documentation MUST describe Orb → Diode → NetBox as the upstream ingestion path and NetBox Branching as an optional NetBox-side change workflow, without requiring those components for GARD alignment to function.

### Out of scope (v1)

- Direct integration with **NetBox Diode** (gRPC ingest), **Orb agent** (discovery), or **NetBox Branching** (branch API / branch-aware sync).
- Deploying or configuring the NetBox discovery/ingestion stack — reserved for a **future NetBox-platform feature** (NetBox-only spec, no GARD application code).
- Auto-remediation in NetBox (creating missing IPs, VRFs, VLANs, or L2VPN objects from GARD).
- Replacing NetBox Assurance inventory/config drift monitoring.

### Key Entities

- **IpamAlignmentRun** — one alignment pass tied to a NetBox sync run: devices checked, finding counts, duration, status, correlation id.
- **IpamAlignmentFinding** — one issue or pass record: device reference, kind, severity, netbox snapshot, gard snapshot, remediation hint, created at.
- **DeviceNetworkContext** — read model attached to a device: interfaces, addresses, VRFs, VLANs, overlay service links (from latest sync).
- **AlignmentPolicyManifest** — lifecycle-as-code rules: per site/role expectations for management IP presence, VRF, VLAN, route-target checks; severity overrides.
- **OverlayServiceBinding** — correlation between an NetBox L2VPN/EVPN service and zero or more device interfaces with expected route-targets/VNIs.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Operators can identify management IP mismatches for 100% of NetBox-linked devices in a sync batch within the sync report (no manual NetBox UI hunting).
- **SC-002**: For a lab estate of at least 30 devices with intentional IP/VRF/VLAN/RT drift seeded, alignment surfaces at least 95% of planted inconsistencies as findings with the correct kind.
- **SC-003**: Sync plus alignment for 100 NetBox-linked devices completes within 90 seconds on dev hardware (alignment adds no more than 50% overhead vs F7-only sync baseline).
- **SC-004**: Zero silent primary IP selections when NetBox presents multiple primary candidates — all appear as `ambiguous` findings.
- **SC-005**: Operators viewing device detail can see network alignment context in one screen without opening NetBox for 100% of devices with findings.
- **SC-006**: Alignment runs produce audit and evidence records on 100% of successful syncs.

## Assumptions

- NetBox v4.x with standard IPAM and DCIM modules; L2VPN/EVPN features available in the target NetBox instance (graceful degradation when not).
- F7 device sync and F10 write-back remain prerequisites; F12 extends rather than replaces them.
- NetBox remains authoritative for all network identity objects; GARD stores snapshots and findings only.
- Alignment policy manifest lives in-repo (lifecycle-as-code) similar to F9/F10 manifests; per-tenant customization via manifest edits, not hard-coded strings.
- Auto-remediation in NetBox (creating missing IPs/VRFs/VLANs) is out of v1 scope.
- **Orb, Diode, and NetBox Branching are upstream/platform concerns**: Orb discovers network data, Diode ingests into NetBox, Branching optionally stages NetBox changes before merge to `main`. GARD consumes the result via REST only; activating that stack is documented separately and is not a prerequisite coded into F12.
- Diode ingest and NetBox Assurance config drift are complementary; F12 does not duplicate Assurance’s config compliance role.
- GARD CSV import may still seed `management_ip`; alignment compares rather than unconditionally overwriting GARD fields in v1.
- Alignment assumes NetBox `main` reflects the operator’s intended production SoT at sync time (merged branch state), not an in-progress unmerged branch.

## Dependencies

- **F7** NetBox read sync (DCIM device reconciliation)
- **F10** NetBox write-back (optional alignment summary mirror)
- **F11** Operator portal (NetBox and device detail surfaces)
- **External (not GARD features)**: A populated NetBox instance — data may originate from manual curation, CSV, Diode ingest, or Orb-driven discovery; how NetBox is populated is outside F12 scope.
