# Feature Specification: NetBox Platform Lab (Orb, Diode, Branching)

**Feature Branch**: `013-netbox-platform-lab`
**Created**: 2026-06-02
**Status**: Draft
**Input**: User description: "NetBox platform lab: deploy Orb + Diode + Branching with NetBox for dev/lab ingestion; document merge-to-main workflow for GARD sync; no GARD application code"

## Why this feature exists

F7–F12 established GARD as a **downstream consumer** of NetBox: device identity sync (F7), device-type bootstrap (F9), lifecycle write-back (F10), and IPAM/DCIM alignment (F12) all read NetBox REST against the **`main`** branch state. ADR-0018 and F12 explicitly defer **how NetBox gets populated** to the upstream NetBox ecosystem:

> Network sources → discovery agents → Diode ingestion → NetBox (source of truth) → GARD

Today the GARD lab uses **manual seed scripts** (`seed-netbox.sh`, REST POST) to populate a minimal NetBox instance. That is sufficient for DCIM sync demos but does not exercise the **realistic ingestion path** operators use with NetBox Labs Orb (discovery), Diode (normalized ingest), or NetBox Branching (staged changes before merge to `main`).

This feature delivers a **self-contained NetBox platform lab** for developers and operators: deploy Orb + Diode + Branching alongside the existing NetBox dev stack, ingest discovery-shaped data into NetBox, and document the **merge-to-main → GARD sync** workflow so F7/F12 behavior can be validated against branch-merged SoT — **without changing GARD application code**.

## User decisions (defaults for v1)

| Topic | Default |
|-------|---------|
| Scope | **Dev/lab only** — not production deployment guidance |
| GARD code | **No GARD application changes** — compose, scripts, docs, fixtures only |
| NetBox base | **Extend** existing isolated F7 NetBox stack (`gard-f7-netbox`, port 18888) |
| Ingestion path | **Orb → Diode → NetBox** as primary lab narrative |
| Branching | **Included in lab** with documented merge workflow; lab remains usable if Branching plugin setup is skipped |
| GARD sync trigger | Operator runs existing GARD NetBox sync **after** merged `main` reflects intended SoT |
| Assurance | **Out of scope** — complementary per ADR-0018; not part of this lab |

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Start the full platform lab stack (Priority: P1)

A platform engineer clones the repo and starts a documented lab environment that includes NetBox plus Orb and Diode services, isolated from the GARD app stack and other NetBox projects on the machine. The runbook lists ports, credentials location, health checks, and teardown steps that do not destroy unrelated Docker projects.

**Why this priority**: Without a reproducible stack, no downstream ingestion or GARD validation work is possible.

**Independent Test**: Follow the quickstart from a clean machine with Docker; within 30 minutes the operator can reach NetBox UI, confirm Diode is accepting ingest, and confirm Orb agent connectivity — without starting the GARD API stack.

**Acceptance Scenarios**:

1. **Given** Docker is installed and no conflicting NetBox lab uses port 18888, **When** the operator runs the documented start command, **Then** NetBox, Diode, and Orb agent services reach a healthy state.
2. **Given** the lab is running, **When** the operator runs the documented stop command with the correct project name, **Then** only this lab's containers stop and other Docker projects are untouched.
3. **Given** the operator follows the isolation guide, **When** they list running containers before and after lab start/stop, **Then** containers outside the lab project name are unchanged.

---

### User Story 2 - Discovery data reaches NetBox via Diode (Priority: P1)

A lab operator configures Orb to discover a small fixture estate (or simulator) and forwards normalized objects through Diode into NetBox. After ingest completes, NetBox shows new or updated DCIM/IPAM objects that match the fixture intent (devices, interfaces, or addresses as defined in lab fixtures).

**Why this priority**: Proves the upstream ingestion path GARD is designed to consume indirectly.

**Independent Test**: Run the ingest smoke script against lab fixtures; verify expected object counts and key identifiers appear in NetBox UI or read-only API queries — without invoking GARD.

**Acceptance Scenarios**:

1. **Given** Orb and Diode are healthy and fixtures are loaded, **When** the operator runs the documented ingest smoke procedure, **Then** at least one device record appears in NetBox with identifiers matching the fixture catalogue.
2. **Given** ingest is run twice with the same fixture data, **When** the second run completes, **Then** the lab documents whether objects are idempotent or how duplicates are handled, and no undocumented silent data loss occurs.
3. **Given** Diode is temporarily unavailable, **When** Orb continues collecting, **Then** the runbook explains recovery steps and expected retry behavior.

---

### User Story 3 - Branch, review, merge to main, then GARD sync (Priority: P1)

A lab operator stages NetBox changes on a Branching branch (e.g., adds IPAM assignments or corrects interface data), reviews the diff, merges to `main`, and only then runs GARD NetBox sync. GARD sees the merged SoT and produces sync/alignment results consistent with F7/F12 expectations documented in cross-linked quickstarts.

**Why this priority**: F12 and ADR-0018 assume GARD reads **`main`**; operators need a practiced workflow for branch merge before sync.

**Independent Test**: Create a branch change that deliberately alters a management IP on a seeded device; merge to `main`; run GARD sync using existing scripts; confirm alignment findings reflect the merged state — using only documented lab steps.

**Acceptance Scenarios**:

1. **Given** Branching is enabled in the lab NetBox, **When** the operator creates a branch and modifies a device IP assignment, **Then** GARD sync run **before** merge does not reflect the branch-only change on `main`.
2. **Given** the same branch change, **When** the operator merges to `main` and runs GARD sync per documented steps, **Then** GARD reflects the merged management IP context in sync/alignment output.
3. **Given** a merge conflict or failed merge, **When** the operator follows the troubleshooting section, **Then** the runbook states how to restore a known-good `main` snapshot for the lab.

---

### User Story 4 - Lab fixtures and drift scenarios for GARD validation (Priority: P2)

A lifecycle operator uses documented planted drift scenarios (management IP mismatch, missing interface address, etc.) that originate from NetBox-side changes flowing through Orb/Diode or branch merge, then validates GARD F12 alignment findings against those scenarios using existing GARD tooling.

**Why this priority**: Connects the platform lab to GARD feature validation without GARD code changes.

**Independent Test**: Execute one fixture scenario end-to-end: ingest → merge → GARD sync → confirm at least one expected alignment finding kind appears in GARD API or portal per F12 contract documentation.

**Acceptance Scenarios**:

1. **Given** a documented drift fixture README, **When** the operator follows the scenario steps, **Then** the expected finding kind is listed with pass/fail criteria before GARD is invoked.
2. **Given** GARD stack is running with lab NetBox URL configured, **When** sync completes after fixture ingest, **Then** cross-links in quickstart point to F12 alignment endpoints for verification.

---

### Edge Cases

- **Branching plugin unavailable or license-blocked in lab**: Document a fallback path using direct `main` edits or seed scripts; lab stack still starts without Branching.
- **Port collisions** with existing NetBox on 18080 or GARD on 8080: Runbook must call out override env vars and pre-flight port check.
- **Orb discovers more than lab fixture scope**: Document how to limit discovery targets so the lab stays small and deterministic.
- **Diode ingest partial failure**: Runbook includes how to inspect Diode logs and re-run smoke without wiping NetBox volumes unintentionally.
- **Operator runs GARD sync against unmerged branch state**: Documented anti-pattern with explicit warning — GARD only reads `main`.
- **Wiping lab volumes**: Separate commands for soft stop vs intentional volume reset; never use global Docker prune commands.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The feature MUST provide a reproducible dev/lab deployment that includes NetBox, Diode, and Orb agent components with documented start, stop, and health-check procedures.
- **FR-002**: The feature MUST remain isolated from the GARD application stack and other NetBox lab projects using explicit Docker Compose project naming and documented port defaults.
- **FR-003**: The feature MUST document the Orb → Diode → NetBox ingestion path with a smoke procedure that verifies objects land in NetBox without manual REST seeding.
- **FR-004**: The feature MUST document NetBox Branching usage for staging changes, including merge-to-`main` steps before GARD sync is invoked.
- **FR-005**: The feature MUST cross-link to existing F7 NetBox sync and F12 IPAM alignment quickstarts for the post-merge GARD validation workflow.
- **FR-006**: The feature MUST include lab fixtures or sample discovery payloads sufficient to populate at least a minimal multi-device estate for GARD sync demos.
- **FR-007**: The feature MUST NOT require changes to GARD application source code, database migrations, or API behavior.
- **FR-008**: The feature MUST document credential bootstrap (tokens for NetBox read/write lab use) without committing secrets to the repository.
- **FR-009**: The feature MUST document teardown and volume reset procedures that scope impact to this lab only.
- **FR-010**: The feature MUST state that production NetBox + Orb + Diode + Branching deployment is out of scope and reference ADR-0018 for GARD ecosystem positioning.
- **FR-011**: When Branching is skipped, the lab MUST still support ingest-to-`main` and GARD sync validation via an documented alternate path.
- **FR-012**: The feature MUST include at least one end-to-end runbook section: ingest → (optional branch merge) → GARD sync → verify alignment summary.

### Key Entities

- **Platform Lab Stack**: The compose-defined set of NetBox platform services (NetBox core, Diode, Orb agent, supporting data stores) and their health relationships.
- **Ingest Fixture**: A versioned catalogue of discovery-shaped objects used to drive deterministic lab ingest smoke tests.
- **Branch Change Set**: A NetBox Branching branch containing staged DCIM/IPAM edits before merge to `main`.
- **Merge Checkpoint**: A documented gate confirming `main` reflects intended SoT before GARD sync runs.
- **Lab Runbook**: Operator-facing procedures for start/stop, ingest, branch workflow, GARD handoff, and troubleshooting.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new contributor can start the platform lab and reach a healthy NetBox UI within 30 minutes using only repository documentation (excluding image download time).
- **SC-002**: The ingest smoke procedure demonstrates at least 3 NetBox-linked devices available on `main` suitable for GARD sync without using `seed-netbox.sh` manual REST posts.
- **SC-003**: The merge-to-main workflow documentation includes explicit before/after checks proving GARD sync does not observe unmerged branch-only changes.
- **SC-004**: At least 2 planted drift scenarios are documented with expected F12 alignment finding kinds and verification steps via existing GARD operator flows.
- **SC-005**: Zero GARD application files are modified in the feature delivery PR(s); changes are limited to deploy artefacts, fixtures, and documentation.
- **SC-006**: Lab teardown using documented project-scoped commands leaves non-lab Docker containers running on a standard developer machine.

## Assumptions

- NetBox Labs Orb, Diode, and Branching documentation and container images are available for lab use at feature delivery time.
- The existing F7 NetBox dev stack (`deploy/netbox/`) remains the NetBox core baseline; this feature extends rather than replaces it.
- GARD F7/F12 behavior remains REST read against `main` only; no GARD Diode SDK integration (per ADR-0018).
- Lab operators have Docker Compose v2 and sufficient local resources for an extended stack (roughly 8 GB RAM recommended).
- Branching may require NetBox configuration or licensing steps that vary by edition; lab docs treat Branching as optional with fallback.
- Discovery targets in lab are synthetic or fixture-scoped — not production network scanning.
- GARD lab sync continues to use `host.docker.internal:18888` (or documented override) from the GARD API container.

## Dependencies

- **F7** NetBox read sync — GARD consumer validated after lab `main` is populated
- **F9** Device type bootstrap — may still be required before devices are credible in NetBox
- **F12** IPAM alignment — optional validation target for post-sync findings
- **ADR-0018** NetBox ecosystem positioning — GARD remains downstream REST consumer
- **ADR-0023** IPAM alignment boundary — reinforces `main`-only GARD reads

## Out of scope (v1)

- GARD application code, API routes, migrations, or UI changes
- Production-grade high availability, backup, or multi-tenant NetBox operations
- NetBox Assurance deployment or integration
- Direct GARD integration with Diode gRPC or Orb control APIs
- Automated CI that runs full Orb hardware discovery against real networks
- Replacing existing `seed-netbox.sh` — it remains valid for minimal DCIM-only labs
