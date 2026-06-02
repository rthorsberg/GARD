# F12 — NetBox IPAM & DCIM Alignment: Research

**Feature**: `012-netbox-ipam-dcim-align` | **Date**: 2026-06-02

## R-1 — NetBox object graph for DCIM↔IPAM linkage

**Decision**: Pull network context via NetBox REST v4 in this order per synced device batch:

1. `GET /api/dcim/devices/` (existing F7) — include `primary_ip4`, `primary_ip6`, `oob_ip` when present on list/detail.
2. `GET /api/dcim/interfaces/?device_id={id}` — enabled interfaces with `mode`, `untagged_vlan`, `tagged_vlans`, `vrf`, `mgmt_only`.
3. `GET /api/ipam/ip-addresses/?device_id={id}` — all assignments with `address`, `vrf`, `assigned_object_type`, `assigned_object_id`, `status`, family.
4. Site-scoped bulk prefetch where cheaper: `GET /api/ipam/vrfs/?site_id=`, `GET /api/ipam/vlans/?site_id=`, `GET /api/ipam/vlan-groups/?site_id=` for policy validation.

**Rationale**: NetBox models IP assignments on interfaces (or VM interfaces); device-level primary IP is a convenience pointer. Batch prefetch by site reduces N+1 for VRF/VLAN group scope checks.

**Alternatives considered**:
- Single GraphQL query — not used elsewhere in GARD; httpx REST matches F7/F10.
- Storing only device primary IP — rejected (misses interface binding and overlay context per spec FR-001/004).

## R-2 — Canonical management IP resolution

**Decision**: Resolve NetBox-side management IP using this deterministic order:

1. Device `primary_ip4` / `primary_ip6` (prefer IPv4 when both exist unless policy says IPv6-only site).
2. `oob_ip` on device when set.
3. First IP on interface with `mgmt_only=true`.
4. First IP on interface whose name matches manifest regex list (default: `(?i)^(mgmt|management|lo0?|loopback0?)`).
5. First IP on any enabled interface (last resort — emit `mgmt_ip_fallback_used` informational finding).

Compare host portion only to GARD `Device.management_ip` (strip prefix length). Multiple candidates at same priority → `mgmt_ip_ambiguous`.

**Rationale**: Matches NetBox operator conventions and spec FR-002; fallback order documented in manifest for lifecycle-as-code tuning.

**Alternatives considered**:
- Always use CSV `management_ip` as truth — rejected (NetBox is identity SoT per ADR-0017).

## R-3 — Alignment phase ordering in sync pipeline

**Decision**: Extend `netbox_sync_controller.run_sync()` pipeline:

```text
Phase 1: F7 pull + reconcile (unchanged)
Phase 2: F12 IPAM alignment (new) — only if phase 1 committed
Phase 3: F10 write-back (existing) — unchanged trigger; may read alignment summary
```

**Rationale**: Alignment consumes fresh pull data; write-back can mirror alignment status tags/fields. Spec FR-009 requires alignment after reconcile, not on pull failure.

**Alternatives considered**:
- Separate `POST .../align` endpoint only — rejected for MVP (operators already run sync).
- Alignment before write-back commit — chosen so write-back manifest can reference alignment status.

## R-4 — Persistence model

**Decision**: New Postgres tables:

- `ipam_alignment_runs` — 1:1 with `netbox_sync_runs` when alignment executes
- `ipam_alignment_findings` — append-only per run + device + kind (latest run queryable via sync run id or device id + max evaluated_at)
- `device_network_contexts` — one JSONB snapshot per device per alignment run (interfaces, addresses, vrf/vlan summary) for UI drill-down

Replace findings for a device within the same run on re-execution idempotency: delete prior findings for `(run_id, device_id)` before insert in same transaction.

**Rationale**: Findings are derived state (Principle II) with cited NetBox snapshots; JSONB avoids premature normalization of NetBox's rich interface model.

**Alternatives considered**:
- Findings-only, no snapshot table — rejected (device detail UI needs structured network tab per SC-005).
- Full relational interface/IP tables — rejected (over-modeling external SoT).

## R-5 — Alignment policy manifest

**Decision**: Canonical manifest at `gard-catalog/netbox/alignment-policy-manifest.yaml`; JSON Schema at `specs/012-netbox-ipam-dcim-align/contracts/alignment-policy-manifest.schema.yaml`.

Sections: `mgmt_ip`, `interface_policies`, `vrf_expectations`, `vlan_expectations`, `overlay_expectations`, `severity_overrides`.

Site/role keys use NetBox slug strings matching synced `Device.site` / `Device.role`.

**Rationale**: Constitution IV; per-estate expectations differ (edge vs core VRF naming).

**Alternatives considered**:
- Hard-coded rules in Python — rejected (not lifecycle-as-code).

## R-6 — L2VPN / route-target ingestion

**Decision**: Probe NetBox plugin availability at run start via `GET /api/plugins/` or feature endpoint; if L2VPN unavailable, set run flag `l2vpn_available=false` and emit one run-level `l2vpn_module_unavailable` finding.

When available, pull:

- `GET /api/plugins/l2vpn/l2vpns/` (or version-appropriate path documented in quickstart)
- `GET /api/plugins/l2vpn/route-targets/` where exposed

Correlate EVPN/L2VPN terminations to DCIM interfaces via NetBox termination objects.

**Rationale**: Spec edge case; NetBox installs vary; graceful degradation required.

**Alternatives considered**:
- Require L2VPN plugin — rejected (blocks estates without overlay modeling).

## R-7 — Finding taxonomy and severity

**Decision**: Closed enum `AlignmentFindingKind` (see `contracts/finding-kinds.yaml`); severities `error`, `warning`, `info`.

Default mapping: mismatches/ambiguity/conflicts → `error`; orphaned VRF informational → `info`; shared anycast → `info` unless manifest elevates.

**Rationale**: Explainability (Principle V); contract tests lock enum.

**Alternatives considered**:
- Free-text finding kinds — rejected (summary aggregation breaks).

## R-8 — GARD field mutation policy

**Decision**: v1 **does not** auto-update `Device.management_ip` from NetBox. Store `netbox_primary_ip` on `device_network_contexts` snapshot and surface `missing_in_gard` / `mismatch` findings. Optional future `POST .../accept-netbox-mgmt-ip` deferred.

**Rationale**: Spec assumption — CSV authority until operator accepts; avoids silent dual-writer on GARD device row.

**Alternatives considered**:
- Always overwrite GARD management_ip on sync — rejected (constitution III + operator trust).

## R-9 — Write-back extension (optional)

**Decision**: Extend F10 write-back manifest with optional fields:

- `gard_ipam_alignment_status` — `aligned`, `mismatch`, `unknown`
- `gard_primary_ip_mismatch` — boolean text

Optional tag `gard-ipam-mismatch` when any error-severity alignment finding exists.

Gated by existing `GARD_NETBOX_WRITEBACK_ENABLED`; alignment works without write-back.

**Rationale**: Spec FR-013; reuses F10 publisher patterns.

## R-10 — API and UI surfaces

**Decision**:

- Extend `NetboxSyncReport` / sync REST envelope with `ipam_alignment` block (summary + truncated entries).
- Add `GET /api/v1/integrations/netbox/alignment/findings` with pagination filters.
- Add `GET /api/v1/devices/{id}/network-context` (latest snapshot).
- F11: extend `web/src/routes/netbox.tsx` summary cards; device detail **Network** tab.

**Rationale**: Spec US5; operators already use sync page and device detail.

**Alternatives considered**:
- Dedicated alignment-only SPA route — deferred (summary on existing pages sufficient for v1).

## R-11 — Performance and batching

**Decision**: Reuse F7 `max_devices` cap; prefetch interfaces and IP addresses in batches of 50 device IDs per httpx parallel limit (sequential batches, max 4 concurrent requests). Target ≤50% overhead vs F7-only sync for 100 devices (SC-003).

**Rationale**: Spec success criterion; NetBox rate limits vary.

**Alternatives considered**:
- Full estate alignment without cap — rejected (inherits F7 bounds).

## R-12 — Audit and evidence

**Decision**: Emit:

- `netbox.ipam_alignment.started` / `completed` / `failed`
- Evidence type `netbox_ipam_alignment` with counts by kind and severity

Correlation id = sync run correlation id.

**Rationale**: Principle V parity with F7/F10.

**Alternatives considered**:
- Piggyback only on `netbox.sync.completed` — rejected (alignment can fail independently after successful pull).
