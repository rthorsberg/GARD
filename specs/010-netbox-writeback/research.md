# F10 — NetBox Lifecycle Write-Back: Research

**Feature**: `010-netbox-writeback` | **Date**: 2026-06-01

## R-1 — Post-sync coupling

**Decision**: Invoke write-back from `netbox_sync_controller.run_sync()` immediately after successful pull reconciliation commit, before returning the HTTP response.

**Rationale**: Spec FR-001 and clarify session lock trigger to post-sync automatic; single operator action (`POST .../sync`) delivers identity + lifecycle mirror.

**Alternatives considered**:
- Separate `POST .../write-back` only — rejected for MVP (extra operator step).
- Async background job — rejected (audit correlation and immediate NetBox visibility requirements).

## R-2 — Phased success HTTP semantics

**Decision**: Sync pull success → **HTTP 200** always; write-back partial failures appear in `data.report.writeback` without rolling back pull mutations.

**Rationale**: Clarify Q1; identity sync and lifecycle publish are separate phases with different failure modes.

**Alternatives considered**:
- 502 on any write-back failure — rejected (would force operators to re-pull unnecessarily).

## R-3 — Custom field provisioning

**Decision**: **Dev bootstrap CLI** creates NetBox `extras.custom_field` rows for `dcim.device` from manifest; **production** manual provisioning; runtime write-back validates existence and marks per-device `failed` if missing.

**Rationale**: Clarify Q2; mirrors F9 device-type bootstrap pattern; avoids production auto-mutation of NetBox schema.

**Alternatives considered**:
- Auto-create fields on every write-back — rejected for production safety.

## R-4 — Tag reconciliation strategy

**Decision**: For each device, compute desired manifest tag slugs from GARD posture; **PATCH** device with full tag list = `(existing_non_manifest_tags) ∪ (desired_manifest_tags)` minus manifest tags no longer warranted.

**Rationale**: Clarify Q4; NetBox tag API is set-based on device PATCH; preserves operator tags outside manifest allow-list.

**Alternatives considered**:
- Tag-level conflict reporting — rejected (tags are reconciled, not conflict-gated).

## R-5 — Custom field conflict detection

**Decision**: Before PATCH, **GET** device (or use pull payload cache when fresh); compare each manifest custom field; if NetBox value differs from GARD desired and differs from last successful write-back fingerprint (or always if no fingerprint), report **conflict** and skip field update.

**Rationale**: Clarify Q4 + US3; prevents silent overwrite of manual NetBox edits.

**Alternatives considered**:
- Blind PATCH — rejected (dual-writer risk that blocked F7 writes).

## R-6 — Manifest location

**Decision**: Canonical manifest at `gard-catalog/netbox/write-back-manifest.yaml`; JSON Schema at `specs/010-netbox-writeback/contracts/write-back-manifest.schema.yaml`.

**Rationale**: Constitution IV lifecycle-as-code; colocate with F9 `device-types-manifest.yaml`.

**Alternatives considered**:
- DB-stored mappings — rejected (reviewability, git diff).

## R-7 — Credentials

**Decision**: Separate settings `GARD_NETBOX_WRITE_TOKEN` for write-back; F7 read sync continues using `GARD_NETBOX_TOKEN`. Dev compose may set both to same v2 bearer token.

**Rationale**: FR-010 least-privilege; read token can stay read-only in production.

**Alternatives considered**:
- Single token with write — allowed in dev only via documented compose example.

## R-8 — Evaluation source timing

**Decision**: Write-back reads **latest stored** compliance/readiness summaries; sync does **not** invoke evaluate endpoints.

**Rationale**: Clarify Q5; keeps sync latency bounded; documented operator flow: evaluate → sync.

**Alternatives considered**:
- Auto-eval on sync — rejected (scope creep into F3/F4 orchestration).

## R-9 — NetBox API surfaces

**Decision**: Use NetBox REST v4:
- `PATCH /api/dcim/devices/{id}/` with `custom_fields` object and `tags` array
- Dev bootstrap: `POST /api/extras/custom-fields/`, `POST /api/extras/tags/` (idempotent ensure)

**Rationale**: Standard NetBox patterns; F9 write client already supports Bearer v2 tokens.

**Alternatives considered**:
- GraphQL — not used elsewhere in GARD NetBox integration.

## R-10 — Feature flag and prod guard

**Decision**: `GARD_NETBOX_WRITEBACK_ENABLED` (default `true` when write token set); prod/non-localhost requires `confirm_writeback=true` query param on sync **or** `GARD_NETBOX_WRITEBACK_CONFIRM=true` env for CLI paths.

**Rationale**: FR-013 + F9 `--confirm` precedent.

**Alternatives considered**:
- Separate confirm for write-back only — deferred; bundled into sync request for MVP simplicity.
