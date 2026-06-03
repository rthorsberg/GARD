# F13 — NetBox Platform Lab (Orb, Diode, Branching)

**Branch**: `013-netbox-platform-lab`
**Status**: Implemented — ready for review

## Summary

Deploy a dev/lab NetBox platform stack with Orb discovery ingestion via Diode, optional Branching for staged changes, and documented merge-to-`main` workflow before GARD sync. No GARD application code.

## Artifacts

| File | Purpose |
|------|---------|
| [spec.md](./spec.md) | Feature specification |
| [plan.md](./plan.md) | Implementation plan |
| [research.md](./research.md) | Phase 0 decisions (R-1..R-10) |
| [data-model.md](./data-model.md) | Lab entity model |
| [tasks.md](./tasks.md) | Implementation tasks (T001–T045, complete) |
| [quickstart.md](./quickstart.md) | Operator runbook |
| [contracts/](./contracts/) | Stack manifest, fixture schema, health JSON |

## Deliverables (scripts & deploy)

| Path | Purpose |
|------|---------|
| `./deploy/scripts/platform-lab-start.sh` | Start NetBox + Diode + Orb stack |
| `./deploy/scripts/platform-lab-stop.sh` | Project-scoped stop |
| `./deploy/scripts/platform-lab-health.sh` | JSON health report |
| `./deploy/scripts/platform-lab-ingest-smoke.sh` | Verify ingest catalogue devices |
| `./deploy/scripts/platform-lab-merge-demo.sh` | Branch merge before/after demo |
| `deploy/netbox/docker-compose.platform.yml` | Platform overlay compose |
| `deploy/netbox/Dockerfile.plugins` | NetBox + Diode (+ optional Branching) |
| [ADR-0024](../../adr/ADR-0024-netbox-platform-lab-boundary.md) | Deploy-only boundary |

## Timeline

- 2026-06-02 — Spec drafted via `/speckit-specify`
- 2026-06-02 — Plan drafted via `/speckit-plan`
- 2026-06-02 — Implemented via `/speckit-implement` (45/45 tasks)

## Scope guards

| In scope | Out of scope |
|----------|--------------|
| Docker compose extensions, lab scripts, fixtures, runbooks | GARD app code, migrations, API |
| Orb → Diode → NetBox ingest smoke | Production HA / Assurance |
| Branch merge → GARD sync documentation | GARD Diode SDK integration |

## Related

- [ADR-0018](../../adr/ADR-0018-netbox-diode-assurance-ecosystem.md) — ecosystem positioning
- [ADR-0023](../../adr/ADR-0023-netbox-ipam-dcim-alignment.md) — GARD reads `main` only
- [ADR-0024](../../adr/ADR-0024-netbox-platform-lab-boundary.md) — F13 boundary
- [F12 spec](../012-netbox-ipam-dcim-align/spec.md) — alignment validation target
- [deploy/netbox/README.md](../../deploy/netbox/README.md) — lab stack docs
