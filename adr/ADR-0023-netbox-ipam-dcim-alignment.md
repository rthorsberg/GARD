# ADR-0023 — NetBox IPAM & DCIM Alignment (Post-Reconcile Read)

**Status**: Accepted
**Date**: 2026-06-02
**Decision-makers**: GARD core team
**Touches**: F12 (alignment), F7 (read sync), F10 (write-back ordering)
**Supersedes**: none
**Superseded by**: none

## Context

F7 established read-only NetBox DCIM identity sync (ADR-0017). F10 added post-sync lifecycle write-back (ADR-0021). Operators need GARD to validate that management IPs, interface IPAM bindings, VRF scope, VLAN assignments, and optional L2VPN route-targets in NetBox align with lifecycle-as-code policy — without mutating NetBox or GARD device identity in v1.

NetBox Labs extensions (Orb agent, Diode ingestion, Branching) are part of the upstream NetBox platform ecosystem. GARD consumes merged NetBox REST state on `main` only.

## Decision

### A. Pipeline ordering

Extend `netbox_sync_controller.run_sync()`:

```text
Phase 1: F7 pull + reconcile (unchanged)
Phase 2: F12 IPAM/DCIM alignment (new, post-reconcile)
Phase 3: F10 lifecycle write-back (unchanged semantics)
```

Alignment is skipped when disabled, pull failed, or zero NetBox-linked devices in batch.

### B. REST read from NetBox `main`

- All alignment I/O uses F7 read-only `NetboxClient` (GET only).
- No direct Orb, Diode, or Branching API integration in F12.
- Deploying NetBox + Orb + Diode + Branching is a separate platform/lab concern.

### C. Policy manifest

- Canonical expectations: `gard-catalog/netbox/alignment-policy-manifest.yaml`.
- JSON Schema: `specs/012-netbox-ipam-dcim-align/contracts/alignment-policy-manifest.schema.yaml`.
- Fail-closed load: invalid manifest blocks alignment runs (FR-015).

### D. Persistence

- `ipam_alignment_runs`, `ipam_alignment_findings`, `device_network_contexts` (migration 0012).
- Findings are immutable per run; new sync produces new rows.
- v1 does **not** auto-update `Device.management_ip` (research R-8).

### E. Optional write-back mirror (F10 extension)

- Optional custom field `gard_ipam_alignment_status` and tag `gard-ipam-mismatch` in write-back manifest.
- Alignment summary resolved from latest run before write-back phase.

## Consequences

- Audit events: `netbox.ipam_alignment.started`, `netbox.ipam_alignment.completed`, `netbox.ipam_alignment.failed`.
- Evidence type: `netbox_ipam_alignment`.
- Operator visibility via sync report `ipam_alignment` block, findings list API, and device network-context endpoint.

## References

- `specs/012-netbox-ipam-dcim-align/spec.md` (FR-016, FR-017)
- [NetBox Branching](https://netboxlabs.com/docs/extensions/branching/) — upstream; not integrated in F12
- [Diode](https://netboxlabs.com/docs/diode/) — upstream ingestion; not integrated in F12
