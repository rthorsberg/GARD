# ADR-0012 — Add `unknown` to the device lifecycle state machine

- **Status**: Accepted
- **Date**: 2026-05-29
- **Feature**: F2 (`002-firmware-catalog`)
- **Author**: Cursor agent (autonomous F2 implementation pass)
- **Constitution principles**: III (Never coerce missing data), V (Evidence/Audit), VII (Defer rather than guess)

## Context

`spec.md` FR-010 specifies that a device can transition into a terminal
`unknown` state when a `FirmwareTarget` matches the device but the
device's `observed_firmware` is `null`. F1's schema (`0002_initial_schema`)
encoded the lifecycle vocabulary as a CHECK constraint on a fixed value
tuple that did **not** include `unknown`. The `LifecycleState` Python
enum was likewise missing the value.

We discovered the gap while implementing the F2 compliance controller
(`gard/core/compliance_controller.py`). Three options were on the table:

1. **Persist `unknown` in the DB** by extending both the `LifecycleState`
   enum and the CHECK constraint via a new migration.
2. **Persist `target_defined`** (closest existing state) and only
   surface `unknown` in the response envelope.
3. **Persist `classified`** and surface `unknown` in the envelope only.

## Decision

**Choose (1): persist `unknown` in the DB.** Add migration `0004` that
drops and re-creates `ck_devices_lifecycle_state` with the extended
value tuple, and add `LifecycleState.unknown = "unknown"` to the Python
enum.

## Rationale

- **Constitution III ("never coerce")**: a missing observation is not
  the same fact as a "target was just defined for this device"
  (`target_defined`) or "device classified but no firmware policy"
  (`classified`). Collapsing the three onto either of the existing
  states would silently fold one fact into another — exactly what III
  forbids.
- **Audit fidelity (V)**: every transition emits a
  `firmware_target.compliance_evaluated` audit row with `before`/`after`
  state. If `unknown` is not a first-class state, the audit chain
  cannot tell "we evaluated and found an unknown" from "we re-evaluated
  the existing classification". Operators reading the audit history
  would not be able to distinguish "we have a target but no observation"
  from "we don't have a target".
- **Spec fidelity (FR-010)**: the spec was explicit. The migration
  cost is one ALTER TABLE that drops + re-adds a CHECK constraint —
  cheap, reversible, and additive.
- **Future-proofing**: F3 (drift taxonomy) and later features will key
  off the persisted state. Having `unknown` as a real state lets those
  features rank, filter, and gate on it without re-discovering the
  observation gap at every layer.

## Consequences

### Positive

- The lifecycle state machine in FR-010 is now implementable verbatim.
- Audit rows carry the true `before`/`after` transition.
- API filters (e.g. `GET /api/v1/devices?lifecycle_state=unknown`) work
  out-of-the-box thanks to F1's existing query plumbing.

### Negative

- Adds one more value to a value tuple that already had 11 members;
  consumers iterating the enum exhaustively (none yet exist in F1) must
  consider it.
- The migration is technically a schema bump that any external reader
  of the DB must accommodate. The risk is bounded — the column is a
  `varchar` with a CHECK constraint; widening the CHECK does not change
  the column type.

### Migration safety

- Migration `0004` is pure expand: existing rows keep their values,
  the new value is additionally accepted. There is no data backfill.
- Downgrade drops back to the pre-F2 tuple. If any rows have already
  been written with `unknown`, the downgrade will fail (CHECK
  violation). Operators must first re-map those rows to `classified`
  before reverting — the downgrade docstring spells this out.

## Alternatives considered

### (2) Persist `target_defined`, expose `unknown` in envelope only

Rejected because `target_defined` already has a meaning in FR-010:
"a target has been resolved for this device but compliance has not yet
been determined". Folding "no observation" into that state would make
the persisted column ambiguous and force every downstream consumer
(F3+) to re-join the device's observation history to disambiguate —
expensive at scale and error-prone.

### (3) Persist `classified`, expose `unknown` in envelope only

Rejected for the same reason as (2), with the added drawback that
`classified` is the F1 baseline state. Letting a device that has a
firmware target "look classified" in the DB would mask the fact that a
firmware policy applies to it — a regression in observability.

## References

- `specs/002-firmware-catalog/spec.md` FR-010, FR-013
- `gard/db/migrations/versions/0004_lifecycle_unknown.py`
- `gard/models/_enums.py` (LifecycleState)
- `gard/core/compliance_controller.py`
