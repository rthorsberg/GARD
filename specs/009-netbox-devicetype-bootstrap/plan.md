# F9 — NetBox Device Type Bootstrap: Implementation Plan

**Feature Branch**: `009-netbox-devicetype-bootstrap`
**Status**: Draft
**Date**: 2026-06-01
**Inputs**: `spec.md`, `research.md` (R-1..R-8), `data-model.md`, `contracts/`, `quickstart.md`
**Constitution version**: 1.0.0
**Predecessors**: F7 (NetBox read sync, dev stack, `seed-netbox.sh`)
**Successor**: NetBox write-back (post-v1; blocked until F9 ships)

## Summary

F9 replaces hand-rolled NetBox device types in dev seed with **curated imports** from the [NetBox community device type library](https://github.com/netbox-community/devicetype-library). A **lifecycle-as-code manifest** (`gard-catalog/netbox/device-types-manifest.yaml`) lists only GARD-supported models (~7 entries across Cisco/Juniper/Nokia), pins an upstream library commit SHA, and maps GARD normalization identities to community YAML paths. A bootstrap CLI imports manufacturers + device types + component templates into NetBox; `seed-netbox.sh` calls bootstrap before seeding devices. F7 read sync is unchanged.

## Technical Context

| Aspect | Choice |
|---|---|
| Language | Python 3.12 (existing GARD stack) |
| Upstream source | `netbox-community/devicetype-library` pinned via manifest `upstream_pin` (git commit SHA) |
| Manifest | YAML under `gard-catalog/netbox/` (version-controlled, reviewable) |
| Submodule | `vendor/netbox-devicetype-library/` — git submodule at manifest pin (offline/CI reproducibility) |
| NetBox API | REST v4, token auth; **write client** separate from F7 read-only client |
| Import logic | Python importer (`gard/integrations/netbox/devicetype_importer.py`) — parses community YAML, POST/PATCH NetBox DCIM endpoints |
| CLI | `python -m gard netbox bootstrap-device-types [--confirm] [--force]` |
| Dev integration | `deploy/scripts/seed-netbox.sh` invokes bootstrap before device seed |
| Testing | pytest contract (manifest schema + pin paths exist) + integration (bootstrap against dev NetBox) |
| Scale | ~7 device types, ~4 manufacturers — not bulk library import |

## Constitution Check

*GATE: Passed pre-Phase 0 and post-Phase 1 design.*

| Principle | F9 adherence |
|---|---|
| I — Governance Before Execution | Bootstrap is DCIM provisioning only; no device firmware execution |
| II — Desired vs Actual | NetBox DCIM shape improved; GARD lifecycle derived state unchanged |
| III — Unknown Is First-Class | Manifest validation fails loudly on missing library entries (no silent skip) |
| IV — Lifecycle-as-Code | Manifest + upstream pin live in `gard-catalog/netbox/`; reviewable diffs |
| V — Evidence/Audit | Bootstrap emits structured report (stdout + optional JSON); no GARD DB mutation required |
| VI — Curated MCP | No new MCP tools; no raw NetBox proxy |
| VII — Integration Over Replacement | Uses community library as upstream; NetBox remains identity SoT |

**Post-design re-check**: Write-capable NetBox client is scoped to explicit bootstrap CLI only — F7 sync client remains GET-only. No constitutional violation.

## Project Structure

### Documentation (this feature)

```text
specs/009-netbox-devicetype-bootstrap/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── device-types-manifest.schema.yaml
│   └── device-types-manifest.yaml      # reference copy; canonical file in gard-catalog/
└── tasks.md                            # /speckit-tasks (not yet)
```

### Source Code (repository root)

**New**

- `adr/ADR-0020-netbox-devicetype-bootstrap.md`
- `gard-catalog/netbox/device-types-manifest.yaml`
- `vendor/netbox-devicetype-library/` (git submodule — initialized in implement)
- `gard/integrations/netbox/devicetype_manifest.py` — load/validate manifest
- `gard/integrations/netbox/devicetype_importer.py` — YAML → NetBox REST
- `gard/integrations/netbox/write_client.py` — POST/PATCH client (bootstrap only)
- `gard/cli/netbox_bootstrap.py` — CLI entry wired in `gard/__main__.py`
- `tests/contract/test_netbox_devicetype_manifest.py`
- `tests/integration/test_netbox_devicetype_bootstrap.py`

**Extended**

- `deploy/scripts/seed-netbox.sh` — call bootstrap; remove hand-rolled dtype creation
- `deploy/netbox/README.md` — bootstrap docs
- `specs/007-netbox-integration-read/quickstart.md` — cross-link F9 bootstrap step
- `ROADMAP.md` — F9 row

**Unchanged**

- `gard/core/netbox_sync_controller.py` — F7 read sync
- `gard/integrations/netbox/client.py` — read-only GET guard preserved

## PR slices

| Slice | Scope |
|---|---|
| **9a** | ADR-0020, spec/plan/research, manifest schema + initial 7 entries, submodule pin |
| **9b** | Manifest validator + importer + CLI + contract tests |
| **9c** | `seed-netbox.sh` integration + integration tests (ISR1121 + F7 sync) |
| **9d** | Prod provision docs, quickstart, ROADMAP, CI pin-bump checklist |

## Complexity Tracking

No constitution violations requiring justification.
