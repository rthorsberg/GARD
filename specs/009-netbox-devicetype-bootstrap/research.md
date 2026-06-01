# F9 — Research: Binding Decisions

**Feature**: `009-netbox-devicetype-bootstrap`
**Date**: 2026-06-01
**Status**: Draft

## R-1 — Upstream pin strategy

**Decision**: Record `upstream_pin` as a **full git commit SHA** of `netbox-community/devicetype-library` in the manifest. Vendor the snapshot as a **git submodule** at `vendor/netbox-devicetype-library/` checked out to that SHA.

**Rationale**: Reproducible dev/CI; air-gapped labs can `git submodule update` once; pin bumps are explicit manifest PRs with reviewable diffs.

**Alternatives rejected**:
- Download ZIP at bootstrap time — network-dependent, harder to audit offline.
- Vendor copied YAML into GARD repo — loses upstream traceability; large diffs on bump.

## R-2 — Manifest location (lifecycle-as-code)

**Decision**: Canonical manifest at `gard-catalog/netbox/device-types-manifest.yaml`. JSON Schema at `specs/009-netbox-devicetype-bootstrap/contracts/device-types-manifest.schema.yaml`. Contract tests validate the canonical file.

**Rationale**: Constitution IV — catalogue knowledge is Git-managed alongside normalization/firmware YAML.

## R-3 — Import mechanism

**Decision**: Implement a **Python importer** in GARD that:
1. Loads community YAML from submodule path + manifest `library_path`
2. Creates/updates NetBox manufacturer (if missing)
3. Creates device type with components (interfaces, power ports, etc.) via NetBox REST

Inspired by [Device-Type-Library-Import](https://github.com/netbox-community/Device-Type-Library-Import) behaviour but embedded to avoid subprocess + version skew.

**Alternatives rejected**:
- Shell-only wrapper around upstream import script — extra dependency, harder to test in pytest.
- Manual `curl` in `seed-netbox.sh` — cannot import component templates faithfully.

## R-4 — Write client separation from F7

**Decision**: New `gard/integrations/netbox/write_client.py` for bootstrap POST/PATCH. Existing `client.py` keeps `_ALLOWED_METHODS = frozenset({"GET"})` for F7 sync.

**Rationale**: Prevents accidental write from sync path; clear security boundary for code review.

## R-5 — Idempotency and conflict policy

**Decision**:
- Match existing NetBox device types by **manufacturer + slug** (community slug from YAML).
- If type exists with same slug and no `--force`: **skip** (report `skipped`).
- If type exists but component count differs: **skip** with `conflict` unless `--force` (default safe).
- If manufacturer exists: reuse ID.

**Rationale**: Spec edge case — no silent overwrite of types already in use by devices.

## R-6 — Initial manifest scope (7 entries)

**Decision**: Ship manifest covering all models in official GARD seeds at F9 delivery:

| GARD source | vendor_normalized | model_normalized | model_raw aliases | Community YAML |
|---|---|---|---|---|
| ISR1121 fixture | cisco | ISR1121 | ISR1121-8P | `device-types/Cisco/ISR-1121-8P.yaml` |
| `devices.csv` | cisco | *(platform iosxr)* | ASR9006 | `device-types/Cisco/ASR-9006.yaml` |
| `devices.csv` | cisco | *(platform iosxr)* | NCS5501 | `device-types/Cisco/NCS-5501-SE.yaml` |
| `devices.csv` | juniper | *(platform junos)* | MX204 | `device-types/Juniper/MX204.yaml` |
| `devices.csv` | juniper | *(platform junos)* | MX480 | `device-types/Juniper/MX480.yaml` |
| `devices.csv` | nokia | *(platform sros)* | 7750 SR-1 | `device-types/Nokia/7750-SR-1.yaml` |

Note: Generic demo CSV models use platform-level normalization rules (`cisco-iosxr`, `juniper-junos`, `nokia-sros`) without chassis `model_normalized`; manifest keys primarily on `model_raw` aliases + `vendor_normalized`.

**Gap handling**: If a future seed model lacks community YAML, manifest validation fails at CI (FR-007).

## R-7 — CLI and prod hook

**Decision**:
- `python -m gard netbox bootstrap-device-types` — dev default (uses `NETBOX_URL` / `NETBOX_SEED_TOKEN` or dedicated env vars)
- `--confirm` required when `GARD_ENV=prod` or when target URL is not localhost/127.0.0.1
- `--force` optional for conflict overwrite (documented as destructive)
- `--dry-run` validates manifest + resolves YAML without NetBox writes

**Rationale**: FR-008 — prod never auto-mutates; operator explicit opt-in.

## R-8 — ADR and roadmap placement

**Decision**: Add **ADR-0020** — NetBox device type bootstrap boundary (curated manifest, pin, write client scope, prerequisite for write-back). Insert F9 in ROADMAP between F8 and post-v1 write-back.

**Rationale**: Closes the gap left by F7 (read-only assumed types exist) without conflating with write-back.
