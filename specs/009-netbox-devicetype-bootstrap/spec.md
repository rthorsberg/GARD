# Feature Specification: NetBox Device Type Bootstrap (Community Library)

**Feature Branch**: `009-netbox-devicetype-bootstrap`
**Created**: 2026-06-01
**Status**: Draft
**Input**: User description: "F9 — NetBox device type bootstrap from community library for GARD-supported models only; pinned upstream, curated manifest, dev seed + optional prod provision hook."

## Why this feature exists

F7 made GARD a **read-only consumer** of NetBox device identity. Today, the dev seed path creates **minimal, hand-rolled** device types (manufacturer + model + slug only). That is enough for sync demos but misses the value of the broader NetBox ecosystem: community-maintained port layouts, physical attributes, and consistent slugs used by operators, diagrams, and downstream tools.

The [NetBox Device Type Library](https://github.com/netbox-community/devicetype-library) captures thousands of community-contributed device definitions. GARD does **not** need the whole library — only the **small set of vendors and models GARD already supports** in normalization rules, firmware catalog targets, and seed fixtures (on the order of single-digit device types across ~4 vendors, not thousands).

F9 is a **prerequisite for NetBox write-back** (post-v1): before GARD pushes lifecycle state to NetBox, NetBox must already hold **canonical, community-aligned device types** so devices reference real DCIM definitions rather than ad-hoc stubs.

> *NetBox owns infrastructure identity and DCIM shape. GARD owns firmware lifecycle. F9 ensures the DCIM shape matches community standards for the models GARD actually governs.*

F9 does **not** change GARD lifecycle semantics, sync logic, or write-back (write-back remains a separate future feature).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Operator bootstraps NetBox with GARD-supported device types (Priority: P1)

A platform engineer runs the documented dev bootstrap for the optional NetBox stack. Instead of hand-creating bare device types, the process loads a **curated manifest** of GARD-supported models and imports the matching community definitions into NetBox (manufacturers, device types, and their component templates). She then seeds demo devices (ISR1121 fixture) that reference those imported types. A subsequent GARD NetBox sync matches devices without type mismatches.

**Why this priority**: Without canonical device types in NetBox, sync and future write-back operate on incomplete DCIM data — the core prerequisite this feature addresses.

**Independent Test**: After bootstrap on a fresh dev NetBox, each manifest entry exists as a NetBox device type with non-empty component definitions (e.g., at least one interface on ISR1121-class types); seeded devices reference those types; F7 sync reports successful match for fixture serials.

**Acceptance Scenarios**:

1. **Given** a fresh dev NetBox and the GARD curated manifest, **When** the bootstrap command runs, **Then** every manifest entry is present in NetBox as a device type under the expected manufacturer.
2. **Given** bootstrap completed, **When** the operator seeds ISR1121 demo devices, **Then** each device references an imported community-backed device type (not a hand-rolled stub with only model/slug).
3. **Given** seeded NetBox and GARD with matching fixture data, **When** F7 sync runs, **Then** devices reconcile by serial without duplicate creation caused by device-type mismatch.
4. **Given** bootstrap is run a second time, **When** device types already exist, **Then** the operation is idempotent (no duplicate manufacturers/types; clear skip-or-update report).

---

### User Story 2 - Manifest stays aligned with GARD-supported models only (Priority: P1)

A catalog maintainer adds or changes GARD normalization/firmware coverage for a reference model. The feature's **curated manifest** lists only models GARD actively supports — derived from normalization catalog entries and official seed fixtures — with explicit mapping from GARD canonical vendor/model to the community library entry. Models not in GARD scope never get imported.

**Why this priority**: Importing the full community library would pollute NetBox and defeat the purpose of curated governance.

**Independent Test**: Manifest contains exactly the supported set (initially ~6–8 types across Cisco, Juniper, Nokia); running bootstrap imports no other vendors; adding an out-of-scope model to the upstream library does not affect NetBox until the GARD manifest is updated.

**Acceptance Scenarios**:

1. **Given** the manifest lists N supported models, **When** bootstrap runs, **Then** exactly N device types (plus required manufacturers) are targeted; no bulk vendor import occurs.
2. **Given** a GARD seed CSV uses `model_raw` alias (e.g., `ISR1121-8P`) and normalized form (`ISR1121`), **When** manifest is inspected, **Then** mapping documents which community library entry applies and which raw aliases are covered.
3. **Given** a model appears in GARD fixtures but has no community library entry, **When** manifest validation runs, **Then** the operator receives an explicit gap report (not a silent skip).

---

### User Story 3 - Reproducible pinned upstream snapshot (Priority: P2)

An operator or CI job bootstraps NetBox from a **pinned** community library snapshot recorded alongside the GARD manifest. Two runs on different days with the same pin produce equivalent device type definitions in NetBox (same model slugs and component counts), so lab and pipeline results are comparable.

**Why this priority**: Unpinned upstream would cause drift between developer laptops and CI without GARD code changes.

**Independent Test**: Manifest records an upstream pin identifier; bootstrap output logs the pin applied; re-run with same pin yields idempotent result.

**Acceptance Scenarios**:

1. **Given** a manifest with a recorded upstream pin, **When** bootstrap runs, **Then** the report includes the pin identifier applied.
2. **Given** the upstream pin is bumped deliberately in the manifest, **When** bootstrap runs, **Then** the report shows which device types changed relative to the previous pin (at minimum: created/updated/skipped counts per entry).

---

### User Story 4 - Optional production provision hook (Priority: P3)

An operator with an existing production NetBox instance runs an **optional, explicit** provision step (documented separately from dev seed) to import the same curated manifest into their environment. The step requires confirmation flags and a write-capable token; it never runs automatically during GARD API startup.

**Why this priority**: Production NetBox is customer-operated; GARD must offer a repeatable hook without imposing silent mutations.

**Independent Test**: Documented prod provision command imports manifest entries when invoked with `--confirm`; GARD API boot does not mutate NetBox.

**Acceptance Scenarios**:

1. **Given** production NetBox credentials and `--confirm`, **When** the provision hook runs, **Then** curated device types are created or verified present.
2. **Given** GARD API starts normally, **When** no provision command was run, **Then** NetBox is unchanged by this feature's prod path.

---

### Edge Cases

- **Community library entry renamed or removed upstream**: Pin bump fails validation with a clear manifest error listing broken paths before any NetBox mutation.
- **Ambiguous model mapping** (e.g., raw `NCS5501` vs several community variants): Manifest MUST document one chosen community entry; validation fails if multiple manifest rows resolve to conflicting slugs for the same GARD normalized model.
- **NetBox already has a conflicting hand-rolled type** with the same slug but different layout: Bootstrap reports conflict and skips or requires operator `--force` policy (documented in runbook; default: no silent overwrite of existing types with devices attached).
- **Partial bootstrap failure** (NetBox unreachable mid-import): No half-applied state without rollback report; operator can safely retry.
- **Air-gapped environment**: Manifest supports offline mode when community YAML is vendored or mirrored at the pinned snapshot (operator responsibility to populate mirror).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST maintain a **curated manifest** listing GARD-supported device types only, with mapping from GARD canonical vendor/model (and documented raw aliases) to a specific community library definition.
- **FR-002**: The manifest MUST record a **pinned upstream snapshot identifier** for the community library so bootstrap is reproducible.
- **FR-003**: A **dev bootstrap command** MUST import manifest entries into the optional GARD NetBox dev stack, replacing hand-rolled minimal device type creation for supported models.
- **FR-004**: Bootstrap MUST be **idempotent**: re-running on an already-provisioned dev NetBox reports created/updated/skipped per entry without duplicate manufacturers or device types.
- **FR-005**: Bootstrap MUST import **full community device type definitions** (not bare model/slug stubs), including component templates defined in the community YAML.
- **FR-006**: The manifest initial scope MUST cover all models present in official GARD seed fixtures and firmware catalog reference targets at feature delivery time (Cisco ISR1121-class, generic multi-vendor demo CSV models, and Nokia/Juniper entries used in catalog seeds).
- **FR-007**: The system MUST **validate the manifest** before import: unknown library paths, missing manufacturers, or unmapped GARD models MUST fail with an actionable report.
- **FR-008**: An **optional production provision hook** MUST be documented and executable independently of GARD API startup, requiring explicit operator confirmation before mutating production NetBox.
- **FR-009**: Bootstrap and provision actions MUST emit an **operator-visible summary** (entries processed, pin applied, created/updated/skipped/failed).
- **FR-010**: F7 NetBox read sync behavior MUST remain unchanged except that seeded/synced devices are expected to reference imported community device types.
- **FR-011**: This feature MUST NOT import the entire community library or bulk-import all models for a vendor.
- **FR-012**: This feature MUST NOT implement NetBox write-back of GARD lifecycle fields (deferred to a later feature).

### Key Entities

- **Curated Device Type Manifest**: Authoritative list of GARD-supported models, upstream pin, community library reference per entry, and GARD↔NetBox model alias mapping.
- **Manifest Entry**: One supported model — links GARD normalization identity to one community library definition and expected NetBox slug.
- **Bootstrap Report**: Outcome of a dev or prod provision run — per-entry status, pin applied, errors, and idempotency hints.
- **Upstream Pin**: Immutable identifier (commit/tag/version) of the community library snapshot used for import.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator can bootstrap a fresh dev NetBox with all GARD-supported device types from the manifest in under 5 minutes following the quickstart (excluding NetBox container startup wait).
- **SC-002**: 100% of manifest entries result in a matching NetBox device type on successful bootstrap (zero silent skips for in-scope models).
- **SC-003**: ISR1121 fixture devices seeded after bootstrap pass F7 sync match-by-serial without duplicate device creation attributable to device type mismatch.
- **SC-004**: Re-running bootstrap against an unchanged dev NetBox produces zero duplicate manufacturers/device types and completes with an all-skipped-or-verified report.
- **SC-005**: Manifest validation catches a deliberately broken library reference before any NetBox API write in automated tests.
- **SC-006**: Production provision never runs unless the operator explicitly invokes the documented hook with confirmation.

## Assumptions

- GARD continues to treat NetBox as identity SoT for infrastructure fields (ADR-0001/0017); F9 only improves DCIM **type** quality, not lifecycle ownership.
- The community library remains the upstream source of YAML definitions; GARD curates **references**, not forks of the full library.
- Initial manifest scope is **single-digit device type count** across ~4 vendors (Cisco, Juniper, Nokia, plus any others already in official seed/catalog), not dynamic discovery of every model in customer estates.
- Dev NetBox remains the isolated `gard-f7-netbox` stack on port 18888; F9 extends `seed-netbox.sh` behavior rather than replacing F7 sync APIs.
- Operators accept that some raw model strings require explicit alias mapping (e.g., `ISR1121-8P` → community `ISR-1121-8P`).
- NetBox write-back remains out of scope; F9 is a prerequisite, not a replacement for that future feature.

## Dependencies

- **F7** — NetBox read sync and dev stack (`deploy/netbox/`, `seed-netbox.sh`).
- **F1/F2/F6** — Normalization catalog and seed fixtures define which models are "GARD-supported".
- **F8** — Not required for F9; MCP transport is independent.

## Out of Scope

- Importing the full NetBox community device type library or all models per vendor.
- Automatic continuous sync from upstream community library (pin bumps are deliberate manifest changes).
- NetBox write-back of GARD lifecycle/compliance/readiness fields.
- Creating new community library contributions upstream (operators may contribute separately).
- Module type or rack type import unless explicitly added to a future manifest revision.
