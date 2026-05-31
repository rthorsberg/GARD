# F6 — Research: 5 binding decisions

Binding decisions for the MVP vertical slice. Reversal requires an amendment here or a new ADR.

## R-1 — ISR1121 fixture CSV shape

**Decision**: The ISR1121 fixture lives at `deploy/scripts/fixtures/isr1121-devices.csv` and MUST use the **F1 import contract** column names from `specs/001-device-import-normalize/contracts/csv-schema.yaml`:

`hostname`, `site`, `serial_number`, `vendor_raw`, `model_raw`, `observed_firmware`, `os_string`, `management_ip`, `observed_at`, `actor_email`

Rows are derived from `gard-speckit-start/examples/devices.csv` (ISR1121 row) plus additional synthetic rows to produce:

- ≥ 1 `outside_target` ISR1121 device (observed firmware below target)
- ≥ 1 `ready_for_uplift` ISR1121 device (observed firmware on approved path, prereqs satisfied)
- ≥ 1 rejected/malformed row (proves import error reporting — MVP criterion #1–2)
- Optional non-ISR1121 row (proves filter scoping in MCP/REST queries)

**Alternatives considered**: Reusing the generic `devices.csv` (iosxr/junos mix). Rejected — it does not exercise ISR1121 normalization or MVP criterion #8 wording.

**Rationale**: One fixture file, one contract, zero adapter layers.

## R-2 — Catalog entries for ISR1121

**Decision**: Add minimal F2 catalog files under `gard-catalog/firmware/`:

| File | Purpose |
|---|---|
| `targets/cisco-ios-isr1121.yaml` | Target `17.12.4`, approved/deprecated lists from seed examples |
| `packages/cisco-ios-17.12.4.yaml` | Target package metadata |
| `packages/cisco-ios-16.9.5.yaml` | Observed-version package for drift |
| `upgrade-paths/cisco-ios-isr1121.yaml` | Path `16.9.5 → 17.12.4` |
| `prerequisites/isr1121-minimum-flash.yaml` | Flash/disk prereq tuned so golden device passes readiness |

Normalization reuses existing `gard-catalog/normalization/cisco-ios.yaml` (ISR1121 matches Cisco IOS / IOS-XE).

Platform family key for uplift waves: `ios` (matches `os_family: cisco-ios` emit).

**Alternatives considered**: Inline catalog in test code only. Rejected — runbook and Docker seed must reload the same files CI uses.

**Rationale**: Lifecycle-as-Code (Principle IV) — desired state lives in YAML on disk.

## R-3 — Golden-path device lifecycle tuning

**Decision**: Exactly **one** golden ISR1121 device (`r-osl-001` or equivalent) MUST traverse the full lifecycle in the integration test:

`imported → classified → outside_target → ready_for_uplift → approval_pending → approved`

Tuning levers (in fixture only, not product code):

- `observed_firmware` starts at deprecated `16.9.5` (outside target)
- Observation fields satisfy prereq rules after catalog reload
- Readiness evaluation flips to `ready_for_uplift` before wave draft
- Wave uses `scope_selector` with `site_in` + `platform_family: ios`

If golden device cannot reach `ready_for_uplift`, the test MUST fail at setup — never skip wave steps.

**Alternatives considered**: Mock readiness in test. Rejected — violates F6 purpose (real composed behaviour).

## R-4 — Test module structure

**Decision**: Single primary module `tests/integration/test_mvp_vertical_slice_isr1121.py` with:

1. Session-scoped fixture: load ISR1121 CSV, reload catalogs, run compliance + readiness eval
2. Class or ordered tests mapping 1:1 to MVP criteria (see `contracts/acceptance-matrix.yaml`)
3. Shared helpers in `tests/integration/_mvp_isr1121_helpers.py` (tokens, audit queries, delegate calls)

MCP delegate assertions run in the same module (not a separate feature PR) to keep one green bar.

**Alternatives considered**: Extend `seed.sh` only without pytest. Rejected — no CI regression harness.

## R-5 — Runbook vs automated seed

**Decision**:

- **`deploy/scripts/seed-isr1121.sh`** — idempotent ISR1121 demo path (mirrors generic `seed.sh` structure)
- **`quickstart.md`** — human-readable checkpoints referencing the script + manual curl fallbacks
- Generic `seed.sh` unchanged (multi-vendor demo remains the default quickstart)

**Alternatives considered**: Replace `seed.sh` entirely. Rejected — F5 demo fixture still valuable for multi-vendor drift taxonomy demos.

**Rationale**: ISR1121 is the MVP proof line; generic seed is the platform demo line.
