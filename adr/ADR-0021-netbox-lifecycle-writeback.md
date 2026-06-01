# ADR-0021 — NetBox Lifecycle Write-Back (Post-Sync Metadata Mirror)

**Status**: Accepted
**Date**: 2026-06-01
**Decision-makers**: GARD core team
**Touches**: F10 (write-back), F7 (read sync), F9 (write client), F3/F4 (evaluation sources)
**Supersedes**: ADR-0017 write-back deferral (§ deferred to post-v1)
**Superseded by**: none

## Context

F7 established GARD as a read-only consumer of NetBox DCIM identity (ADR-0017). Operators sync inventory and run compliance/readiness in GARD, but NetBox UI cannot show GARD lifecycle conclusions without a controlled write path.

F10 adds **metadata-only write-back**: custom fields and tags on linked `dcim.device` rows after a successful F7 pull reconcile. DCIM identity fields remain NetBox-owned and unchanged.

## Decision

### A. Post-sync coupling

- Write-back runs inside `netbox_sync_controller.run_sync()` immediately after pull commit.
- Single operator action: `POST /api/v1/integrations/netbox/sync`.
- Sync does **not** invoke compliance/readiness evaluation (FR-001a).

### B. Lifecycle-as-code manifest

- Canonical mapping: `gard-catalog/netbox/write-back-manifest.yaml`.
- JSON Schema: `specs/010-netbox-writeback/contracts/write-back-manifest.schema.yaml`.
- GARD manages only fields and tag slugs declared in the manifest.

### C. Credential split

- Read pull: `GARD_NETBOX_TOKEN` via F7 read-only `client.py`.
- Write-back: `GARD_NETBOX_WRITE_TOKEN` via F9 `write_client.py`.
- Dev/lab may set both to the same v2 Bearer token.

### D. Conflict and tag policy

- **Custom fields**: compare NetBox current vs GARD desired before PATCH; manual operator edit → `conflict`, no overwrite (default).
- **Tags**: reconcile manifest slugs each run (add/remove per posture); not conflict-gated; preserve non-manifest tags.

### E. Phased HTTP semantics

- Pull success → **HTTP 200** always.
- Write-back partial failures reported in `data.report.writeback`; pull mutations are not rolled back.

### F. Dev bootstrap, prod manual

- `python -m gard netbox bootstrap-writeback-fields` creates NetBox custom fields + tags in dev/lab only.
- Production: operators provision schema manually; missing fields → per-device `failed`.

### G. Production guard

- Non-localhost NetBox or `GARD_ENV=prod` requires `confirm_writeback=true` on sync (FR-013).

## Consequences

- F7 read client remains GET-only; all NetBox writes go through `write_client.py`.
- Audit events: `netbox.writeback.started`, `netbox.writeback.completed`, `netbox.writeback.failed`.
- Optional DB columns on `netbox_sync_runs` and `devices.netbox_last_writeback_at` for operator queries.

## References

- `specs/010-netbox-writeback/spec.md`
- ADR-0017 (F7 read boundary)
- ADR-0020 (F9 write client precedent)
