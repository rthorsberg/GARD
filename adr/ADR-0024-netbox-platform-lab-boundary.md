# ADR-0024 — NetBox Platform Lab Boundary (Deploy-Only)

**Status**: Accepted
**Date**: 2026-06-02
**Decision-makers**: GARD core team
**Touches**: F13 (platform lab), F7 (NetBox read sync), F12 (IPAM alignment), ADR-0018
**Supersedes**: none
**Superseded by**: none

## Context

F7–F12 established GARD as a **downstream REST consumer** of NetBox on the **`main`** branch state (ADR-0017, ADR-0018, ADR-0023). Operators currently populate the dev NetBox lab via manual REST seed scripts. The upstream NetBox ecosystem (Orb discovery → Diode ingestion → NetBox, optional Branching for staged merges) is not exercised in-repo.

F13 delivers a **dev/lab-only** platform stack and runbooks so contributors can validate the realistic ingestion path and merge-to-`main` workflow before GARD sync — without changing GARD application code.

## Decision

### A. Deploy and documentation only

F13 changes are limited to:

- Docker Compose extensions under `deploy/netbox/`
- Shell scripts under `deploy/scripts/`
- Versioned lab fixtures and contracts under `specs/013-netbox-platform-lab/` and `deploy/scripts/fixtures/platform-lab/`
- Contract tests for lab manifest/fixture schemas
- Operator runbooks and cross-links to F7/F12 quickstarts

No changes to `gard/`, `web/`, database migrations, REST API, or MCP tools (FR-007, SC-005).

### B. Upstream ingestion path (lab narrative)

The lab's primary population path is:

```text
Orb agent → Diode server → NetBox Diode plugin → NetBox main schema
```

GARD does **not** integrate with Diode gRPC or Orb control APIs in F13 or v1.

### C. Branching and GARD read boundary

When NetBox Branching is enabled in the lab:

- Operators stage DCIM/IPAM edits on a branch
- Merge to `main` before invoking GARD sync
- GARD continues REST read against **`main` only** (ADR-0018, ADR-0023)

When Branching is skipped, the lab documents direct `main` edits and existing `seed-netbox.sh` as alternate paths (FR-011).

### D. Scope limits

- **In scope**: Dev/lab reproducibility, health checks, ingest smoke, merge demo scripts, drift scenario docs for F12 validation
- **Out of scope**: Production HA, NetBox Assurance, GARD Diode SDK, automated CI against real network discovery

## Consequences

- F7 `sync-gard-netbox.sh` remains the GARD handoff script; F13 adds upstream lab setup only
- F12 alignment findings validate against NetBox state populated via platform lab or legacy seed scripts
- Platform lab secrets live in operator-local `.env` files, never committed (FR-008)

## References

- [ADR-0018](./ADR-0018-netbox-diode-assurance-ecosystem.md)
- [ADR-0023](./ADR-0023-netbox-ipam-dcim-alignment.md)
- [F13 spec](../specs/013-netbox-platform-lab/spec.md)
