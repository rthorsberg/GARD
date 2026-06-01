# ADR-0020 — NetBox Device Type Bootstrap (Curated Community Import)

**Status**: Accepted
**Date**: 2026-06-01
**Decision-makers**: GARD core team
**Touches**: F9 (device type bootstrap), F7 (read sync, dev seed), post-v1 write-back prerequisite
**Supersedes**: none
**Superseded by**: none (write-back remains a separate ADR)

## Context

F7 read sync pulls device identity from NetBox but does not provision DCIM shape. Dev demos used hand-rolled device types in `seed-netbox.sh` that diverge from the [NetBox community device type library](https://github.com/netbox-community/devicetype-library) and from production NetBox conventions.

Post-v1 NetBox write-back requires consistent device types (manufacturers, slugs, component templates). Importing the entire community library is out of scope — GARD only supports a curated set of models aligned with normalization catalog and seed fixtures.

## Decision

### A. Curated manifest (lifecycle-as-code)

- Canonical allow-list: `gard-catalog/netbox/device-types-manifest.yaml`.
- Each entry maps GARD normalization identities (`vendor_normalized`, `model_raw_aliases`) to a pinned community YAML path and expected NetBox slug.
- Manifest pins upstream library commit SHA in `upstream_pin`; git submodule `vendor/netbox-devicetype-library/` tracks the same pin for offline/CI reproducibility.

### B. Bootstrap CLI (explicit operator action)

- Command: `python -m gard netbox bootstrap-device-types [--dry-run] [--force] [--confirm]`.
- Imports manufacturers, device types, and component templates via NetBox REST v4.
- Emits structured stdout report with per-entry status and summary counts.
- **Never** runs on GARD API startup or during F7 sync.

### C. Write client boundary

- `gard/integrations/netbox/write_client.py` — POST/PATCH for bootstrap only.
- `gard/integrations/netbox/client.py` (F7) remains **GET-only**; no shared mutation helpers.

### D. Idempotency and conflict policy

- Skip when device type slug already exists with matching component count.
- Report `conflict` when slug exists but component count differs; skip unless `--force`.
- Re-run after successful import reports all entries `skipped` (no duplicates).

### E. Production guard

- Non-localhost NetBox URL or `GARD_ENV=prod` requires explicit `--confirm`.
- `--dry-run` validates manifest and resolves library paths without NetBox writes.

### F. Relationship to write-back

F9 is a **prerequisite** for post-v1 NetBox write-back: operators must bootstrap DCIM device types before GARD can safely attach lifecycle metadata to NetBox objects. F9 does not implement write-back.

## Consequences

- `deploy/scripts/seed-netbox.sh` calls bootstrap before device seed; hand-rolled device type POST removed.
- Submodule pin bumps require paired manifest `upstream_pin` change in the same PR.
- F7 sync behaviour unchanged; improved `model_raw` alignment from community types.

## References

- `specs/009-netbox-devicetype-bootstrap/spec.md`
- ADR-0017 (read-only F7 boundary)
- ADR-0001 (NetBox vs GARD ownership)
