# Feature Specification: Operator Dashboard & Web UI

**Feature Branch**: `011-operator-dashboard`
**Created**: 2026-05-31
**Status**: Draft
**Input**: User description: "F11 (011) — UI + dashboard and user interface on top of what we have built so far. Elaborate and plan for how a real UI should look. TypeScript preferred. NO Streamlit app."

## Why this feature exists

F1–F10 delivered a **complete lifecycle backend**: device inventory, firmware catalog, compliance and readiness evaluation, uplift planning, NetBox read sync, MCP access, and NetBox lifecycle write-back. Operators today rely on **OpenAPI clients, curl, MCP tools, and ad-hoc scripts** to answer questions like *"How many devices are drifted?"*, *"Which ISR1121 units are ready for uplift?"*, or *"Did the last NetBox sync write lifecycle tags?"*

The MVP scope explicitly deferred a **production-grade operator interface**. F11 closes that gap with a **dedicated web portal** that surfaces GARD lifecycle truth in human-readable dashboards and guided workflows — without duplicating business logic already owned by the GARD service.

> *GARD remains the system of record for lifecycle decisions. F11 is the operator-facing lens: read posture at a glance, drill into devices, and trigger existing approved actions with clear feedback.*

F11 does **not** replace NetBox UI, MCP, or the REST API. It complements them for lifecycle operators who need a cohesive daily workspace.

## User decisions (from kickoff)

| Topic | Decision |
|-------|----------|
| UI form factor | **Web application** — browser-based operator portal (not CLI-only, not notebook-style tools) |
| Implementation preference | **TypeScript** — captured for planning; not a functional requirement in this spec |
| Explicitly excluded | **No Streamlit** (or similar Python rapid-UI frameworks) |
| Backend coupling | **Consume existing GARD service** — UI displays and triggers capabilities already exposed by the platform; no parallel lifecycle engine |
| v1 posture | **Read-heavy + guided actions** — dashboards, search, detail views, and buttons for existing mutations (import, evaluate, sync); not a full catalog editor or execution orchestrator |
| Visual reference | **[Shadcn UI Kit — E-commerce Dashboard](https://shadcnuikit.com/dashboard/ecommerce)** — layout and interaction patterns for dashboard, list, detail, and status aggregates (see Design reference below) |

## Target users

| Persona | Typical goals | Access level (mirrors existing roles) |
|---------|---------------|--------------------------------------|
| **Platform engineer** | Run imports, NetBox sync, compliance/readiness runs; triage drift | Full lifecycle operations |
| **Lifecycle analyst** | Review posture, draft uplift waves, manage exceptions | Read + evaluate + uplift draft |
| **Auditor / stakeholder** | Verify evidence and audit trail without changing state | Read-only |

## UI information architecture (v1)

The portal is organized as a **persistent shell** (header, role indicator, primary navigation) with focused content areas. Desktop-first layout with usable tablet widths; mobile is best-effort in v1.

### Global shell

- **Header**: product name, signed-in identity (role label), environment badge (e.g., lab/production when configured), sign-out
- **Primary navigation** (left or top): Dashboard, Devices, Compliance, Readiness, Uplift, NetBox, Audit
- **Global search** (optional P2): quick jump to device by hostname or identifier

### Screen catalog

| Screen | Purpose | Primary data shown |
|--------|---------|-------------------|
| **Sign-in / session** | Establish authenticated session to GARD | Connection status, role, session expiry hint |
| **Dashboard (home)** | At-a-glance lifecycle posture | Device counts by posture, compliance/readiness summary tiles, NetBox linkage coverage, recent sync/eval activity, top exceptions or at-risk devices |
| **Devices (list)** | Browse and filter estate | Sortable/filterable table: hostname, vendor/model, site, current firmware, compliance state, readiness state, NetBox link indicator |
| **Device detail** | Single-device lifecycle story | Overview tab (identity, firmware, NetBox link), Observations, Compliance result, Readiness result, linked evidence references |
| **Compliance** | Fleet compliance view + run | Summary charts/tables, filter by drift status, action to run compliance evaluation (when permitted), last-run timestamp |
| **Readiness** | Fleet readiness view + run | Prerequisite posture summary, action to run readiness evaluation (when permitted) |
| **Uplift** | Planning workspace | Wave list/detail (read), exception list; draft actions when permitted — no execution/provisioning |
| **NetBox integration** | Sync and write-back visibility | Last sync report summary (created/updated/skipped/failed), write-back counts, link to affected devices, trigger sync (when permitted) |
| **Audit & evidence** | Traceability | Searchable audit log entries and evidence artifacts (read-only) |

### Visual design principles (product, not implementation)

- **Status-first**: color and labels align with GARD lifecycle vocabulary (compliant, drifted, ready, blocked, unknown/not evaluated)
- **Progressive disclosure**: dashboard summarizes; detail pages show full context without overwhelming the home view
- **Action feedback**: long-running operations (import, sync, evaluation) show in-progress state, completion summary, and errors in plain language
- **Permission-aware**: navigation items and action buttons hidden or disabled when the signed-in role lacks capability — never fail silently on click

### Design reference

**Primary visual reference**: [Shadcn UI Kit — E-commerce Dashboard](https://shadcnuikit.com/dashboard/ecommerce) and its subpages (product list, product detail, orders/activity).

This reference is **layout and UX inspiration only** — not a requirement to purchase the kit or replicate ecommerce copy. Planning may use open [shadcn/ui](https://ui.shadcn.com/) components to achieve the same patterns. The goal is a familiar **inventory + status + aggregates + recent activity** operator workspace.

#### Domain mapping (ecommerce → GARD)

| E-commerce pattern | GARD operator portal |
|--------------------|----------------------|
| KPI summary cards (revenue, users, growth) | **Estate KPIs**: total devices, % compliant, % drifted, % ready, NetBox-linked count; each card links to a filtered view |
| “Best selling products” ranking table | **Top risk groupings**: models, sites, or firmware versions with highest drift or blocked readiness |
| Product catalog list | **Devices list** — primary daily inventory (hostname, model, site, firmware, posture badges) |
| Product detail page | **Device detail** — tabs for overview, observation, compliance, readiness, NetBox linkage |
| Product catalog (secondary) | **Firmware catalog browse** (read-only in v1) — firmware packages/targets as catalog “SKUs” |
| Valid / invalid / in-stock product states | **Compliance posture buckets**: compliant, drifted, not evaluated, unknown |
| Recent orders table | **Recent activity**: imports, compliance/readiness runs, NetBox syncs with outcome badges |
| Order status chips (`processing`, `paid`, `failed`) | **Lifecycle status badges**: compliant, drifted, ready, blocked, sync/write-back failed |
| Sales by location chart | **Devices by site** (or region) breakdown |
| Star-rating / review distribution | **Posture distribution** chart (compliance or readiness mix across estate) |
| Export actions on tables | **Export filtered device lists** and report summaries where backend supports it |
| Sidebar app shell + section nav | **GARD nav**: Dashboard, Devices, Compliance, Readiness, Uplift, NetBox, Audit |

#### Kit subpages to mirror in v1 (priority)

1. **Dashboard home** — KPI row, breakdown charts, recent activity table, drill-down links (“View more” → filtered lists).
2. **Product list → Devices** — sortable/filterable data table, pagination, status badges, row click to detail.
3. **Product detail → Device detail** — header summary + tabbed sections for lifecycle context.
4. **Orders / activity → Recent operations** — embedded on dashboard and dedicated Audit/NetBox views.

#### GARD-specific screens (not in kit)

These have **no direct ecommerce equivalent** and must be designed explicitly in planning:

- **NetBox integration** — last sync report with pull reconciliation **and** lifecycle write-back counts (F10).
- **Compliance / Readiness run** — permission-gated action panels with in-progress and result summaries.
- **Uplift waves & exceptions** — planning workspace beyond simple product/order metaphors.

#### What to borrow vs adapt

**Borrow (structure & interaction):**

- Persistent sidebar shell, header with user/role, environment badge.
- Top-row metric cards with trend or delta hints where meaningful (e.g., drift count since last eval).
- Primary data table as the main working surface (filters, sort, pagination, export).
- Status-first badge colors aligned to GARD vocabulary (green / amber / red / neutral for unknown).
- Chart widgets for posture mix and geographic/site breakdown.
- “Recent activity” strip linking to audit or operation detail.

**Adapt (language & domain):**

- Replace revenue, MRR, and sales copy with **posture**, **coverage**, **last evaluated**, **sync health**.
- Primary CTAs are **Run evaluation**, **Import devices**, **Sync NetBox** — not checkout or purchase flows.
- Device detail emphasizes **technical timeline** (observations, evaluations, evidence) rather than product gallery or reviews.
- Group aggregates by **compliance/readiness posture**, not “valid/invalid product” — UI labels use GARD lifecycle terms.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Lifecycle posture at a glance (Priority: P1)

A platform engineer opens the GARD operator portal after morning standup. The **dashboard** shows how many devices are in the estate, what percentage are compliant vs drifted, readiness blocked vs ready, and how many devices are linked to NetBox. She spots an elevated drift count, clicks through to the compliance view filtered to drifted devices, and identifies three hosts needing attention — all without writing API calls.

**Why this priority**: The dashboard is the primary reason operators adopt a UI over raw API access; it must answer "how are we doing?" in under one minute.

**Independent Test**: With a seeded lab estate of at least 20 devices spanning compliant, drifted, and unevaluated states, load the dashboard and verify summary counts match GARD backend totals within the same session; drill-down links land on correctly filtered device or compliance lists.

**Acceptance Scenarios**:

1. **Given** an authenticated operator with read access, **When** she opens the dashboard, **Then** she sees aggregate counts for total devices, compliance posture buckets, readiness posture buckets, and NetBox-linked device count.
2. **Given** summary tiles on the dashboard, **When** she selects a posture bucket (e.g., drifted), **Then** she navigates to a list pre-filtered to devices in that posture.
3. **Given** no devices exist in the estate, **When** the dashboard loads, **Then** she sees an empty-state message with guidance to import devices (if permitted) rather than blank or broken widgets.
4. **Given** the backend is temporarily unreachable, **When** the dashboard loads, **Then** she sees a clear error state with retry guidance — not partial misleading zeros.

---

### User Story 2 - Device discovery and lifecycle drill-down (Priority: P1)

A lifecycle analyst needs to inspect `edge-router-07`. She opens **Devices**, searches by hostname, opens the **device detail** page, and reviews tabs for current firmware observation, latest compliance evaluation (drift reason), readiness prerequisites, and whether the device is NetBox-linked with last sync metadata visible.

**Why this priority**: Device detail is the daily working surface for triage; it must unify data presently scattered across multiple API endpoints.

**Independent Test**: Open any device with compliance and readiness evaluations; verify all tabs render consistent hostname/serial identity and evaluation timestamps match backend records.

**Acceptance Scenarios**:

1. **Given** a device list with pagination, **When** the analyst applies filters (vendor, compliance state, NetBox linked yes/no), **Then** only matching devices appear and filter state is visible in the URL or UI so views are shareable.
2. **Given** a device detail page, **When** compliance evaluation exists, **Then** drift status, target firmware reference, and evaluation time are shown; when none exists, **Then** an explicit "not evaluated" state appears.
3. **Given** a device linked to NetBox, **When** viewing overview, **Then** NetBox linkage indicator and last known sync/write-back summary are visible without leaving GARD.
4. **Given** a read-only user, **When** viewing device detail, **Then** no mutation controls (import, re-evaluate, sync) are offered.

---

### User Story 3 - Guided operator actions with feedback (Priority: P1)

A platform engineer uploads a CSV of new observations via the **Devices** import flow (or dedicated import entry point), runs **compliance evaluation** from the Compliance screen, then triggers **NetBox sync** from the NetBox screen. Each action shows progress, a structured result summary (counts of created/updated/skipped/failed), and links to affected devices or audit entries.

**Why this priority**: Operators must execute existing workflows from the UI; triggering actions without clear outcomes recreates the pain of raw API usage.

**Independent Test**: As lifecycle_admin in lab, perform import → compliance run → NetBox sync sequentially; each step shows success summary consistent with API response payloads; audit log contains corresponding entries viewable in Audit screen.

**Acceptance Scenarios**:

1. **Given** a user with import permission, **When** she submits a valid CSV import, **Then** she receives a result summary (devices/observations affected) and can navigate to imported devices.
2. **Given** a user with compliance run permission, **When** she starts fleet compliance evaluation, **Then** the UI shows in-progress state until completion and then refreshed compliance summaries.
3. **Given** a user with NetBox sync permission, **When** sync completes, **Then** the NetBox screen shows pull reconciliation counts **and** write-back counts (updated/skipped/failed) from the sync report.
4. **Given** a user without permission for an action, **When** she views the relevant screen, **Then** the action is not available (hidden or disabled with explanation) — not an opaque 403 after submit.

---

### User Story 4 - Uplift planning visibility (Priority: P2)

A lifecycle analyst reviews **Uplift** to see active waves, devices assigned to waves, and open exceptions. She opens a wave detail view to understand scope and blocked devices before a change window — without exporting CSV or querying uplift endpoints manually.

**Why this priority**: Uplift is a core GARD differentiator; operators need visibility even if wave drafting remains a power-user flow in v1.

**Independent Test**: With at least one draft wave and one exception in lab data, uplift list and detail pages render wave metadata and member devices matching backend state.

**Acceptance Scenarios**:

1. **Given** uplift waves exist, **When** the analyst opens Uplift, **Then** she sees a list with wave name, status, device count, and last updated time.
2. **Given** a wave detail view, **When** opened, **Then** member devices show readiness/compliance posture relevant to uplift gating.
3. **Given** a user with draft permission, **When** she initiates a permitted draft action, **Then** the UI confirms success and refreshes the wave list.

---

### User Story 5 - Audit and evidence for traceability (Priority: P3)

An auditor opens **Audit** to search recent lifecycle actions (imports, evaluations, syncs, uplift changes). She filters by action type and time range, opens an entry, and follows links to related evidence artifacts where available — confirming who did what and when.

**Why this priority**: Trust and compliance require traceability; read-only audit access completes the portal for stakeholders who never mutate state.

**Independent Test**: After performing Story 3 actions, audit screen lists those events with correct actor, timestamp, and action type; evidence links resolve when present.

**Acceptance Scenarios**:

1. **Given** audit entries exist, **When** the auditor searches by action type, **Then** matching entries appear in reverse chronological order.
2. **Given** an audit entry references evidence, **When** selected, **Then** evidence metadata is viewable (read-only download/view as supported by backend).

---

### Edge Cases

- **Session expired or invalid credentials**: User is redirected to sign-in with a message; no cached data is presented as current truth.
- **Partial backend degradation**: If one domain (e.g., uplift) fails to load, other navigation areas remain usable with isolated error banners.
- **Large estates (1,000+ devices)**: List views remain usable via pagination and filters; dashboard aggregates load within acceptable wait time (see success criteria).
- **Stale evaluations**: Device detail clearly shows evaluation age; dashboard may surface " evaluations older than N days" when configured.
- **Unevaluated devices**: Shown as explicit unknown/not-evaluated — never implied compliant.
- **Concurrent operators**: Two users triggering sync or evaluation see independent progress; last completed report timestamp is authoritative on NetBox screen.
- **NetBox sync partial write-back failure**: NetBox screen surfaces write-back failed count and per-device failure reasons from the UI claiming full success.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a web-based operator portal accessible via standard browsers without requiring command-line tools for primary workflows.
- **FR-002**: The portal MUST authenticate operators using the same identity and role model as the existing GARD platform (viewer, lifecycle analyst, platform engineer / admin equivalents).
- **FR-003**: The portal MUST present a **dashboard** with aggregate lifecycle posture metrics: device totals, compliance buckets, readiness buckets, and NetBox linkage coverage.
- **FR-004**: The portal MUST provide a **searchable, filterable device list** with pagination suitable for estates of at least 1,000 devices.
- **FR-005**: The portal MUST provide a **device detail** view consolidating identity, firmware observation, compliance result, readiness result, and NetBox linkage status.
- **FR-006**: The portal MUST provide dedicated **Compliance** and **Readiness** views with fleet-level summaries and drill-down to affected devices.
- **FR-007**: The portal MUST allow permitted operators to **trigger existing GARD mutations** from the UI: device import (CSV), compliance evaluation, readiness evaluation, and NetBox sync — each with structured result feedback.
- **FR-008**: The portal MUST provide a **NetBox integration** view showing the latest sync report including reconciliation and lifecycle write-back outcome counts.
- **FR-009**: The portal MUST provide **Uplift** views listing waves and exceptions with detail drill-down (read); draft/manage actions MUST respect role permissions.
- **FR-010**: The portal MUST provide **read-only Audit and Evidence** views for users with audit read permission.
- **FR-011**: The portal MUST enforce **permission-aware UI**: hide or disable actions the signed-in role cannot perform; unauthorized API responses MUST map to user-friendly messages.
- **FR-012**: The portal MUST show **loading, empty, and error states** for every primary screen — never silent failure or misleading zero counts.
- **FR-013**: The portal MUST NOT implement lifecycle business rules independently of GARD; all displayed data and triggered actions MUST originate from the GARD service.
- **FR-014**: The portal MUST NOT use Streamlit or equivalent Python notebook-style UI frameworks (per kickoff decision).
- **FR-015**: Long-running operations MUST show **in-progress indication** and remain navigable without blocking the entire application shell.

### Key Entities

- **Operator session**: Authenticated context binding a human operator to a role and GARD service endpoint; includes expiry and connection health.
- **Dashboard snapshot**: Aggregated counts and highlights derived from current GARD device, compliance, readiness, and NetBox linkage data for a point-in-time view.
- **Device summary**: List-row projection of a device with identity, firmware, posture labels, and NetBox link flag for browsing and filtering.
- **Device lifecycle profile**: Full detail aggregate for one device: observations, evaluations, evidence references, NetBox metadata.
- **Action result**: Structured outcome of an operator-triggered mutation (import, evaluation, sync) with counts, errors, and navigable follow-ups.
- **Sync report view**: Human-readable presentation of last NetBox sync including pull reconciliation and write-back phases.
- **Audit entry**: Immutable record of a platform action with actor, timestamp, action type, and optional evidence linkage.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new operator can answer "how many devices are drifted?" from the dashboard within **60 seconds** of first sign-in (lab onboarding scenario).
- **SC-002**: **90%** of common operator tasks (view dashboard, find device, read compliance result, trigger compliance run, review last NetBox sync) are completable entirely within the portal without external API clients (validated via structured usability test with ≥5 tasks).
- **SC-003**: Device list and dashboard aggregate views become interactive within **3 seconds** for estates up to **1,000 devices** under normal lab network conditions.
- **SC-004**: **100%** of mutation actions initiated from the UI display a definitive outcome (success, partial success, or failure with reason) — zero silent failures in acceptance testing.
- **SC-005**: Read-only users attempting restricted actions encounter **zero** exposed controls that lead to authorization errors on submit (controls are absent or clearly disabled).
- **SC-006**: After a NetBox sync initiated from the UI, operators can see write-back outcome counts on the NetBox screen **without** opening NetBox or raw API responses.

## Assumptions

- **Existing API surface**: F1–F10 REST endpoints (devices, imports, observations, compliance, readiness, uplift, NetBox integration, audit, evidence) are sufficient for v1 UI; minor read-model additions (if any) are planning concerns, not new business capabilities.
- **Authentication v1**: Operators authenticate with credentials/tokens compatible with existing GARD JWT issuance (e.g., bearer token session established at sign-in); enterprise SSO is out of scope for v1 unless already provided by platform auth.
- **Deployment**: The web portal is deployed as a separate deliverable from the GARD Python service (static/hosted frontend + API backend URL configuration); exact hosting is decided in planning.
- **TypeScript preference**: Implementation will use a TypeScript-based web frontend stack; this spec remains technology-agnostic for requirements and success criteria.
- **No Streamlit**: Python Streamlit and similar rapid-UI tools are excluded by explicit user request.
- **Desktop-first**: Primary target is desktop browsers (latest Chrome/Firefox/Safari/Edge); responsive layout for tablet is desirable; phone layout is not a v1 commitment.
- **Scope boundary — out of v1 UI**: Firmware catalog YAML editing, firmware blob upload management, MCP tool invocation from browser, device execution/provisioning orchestration, NetBox DCIM editing, and Diode/Assurance integrations.
- **Single GARD instance per session**: Operators connect the portal to one configured GARD base URL; multi-tenant switching is out of scope for v1.
- **Localization**: English-only UI copy for v1.

## Dependencies

- GARD service F1–F10 shipped and reachable (health, RBAC, domain endpoints).
- Existing role and permission matrix (viewer, lifecycle analyst, lifecycle admin / platform engineer).
- Lab or production data seed sufficient to validate dashboard aggregates and device drill-down.

## Out of scope (v1)

- Streamlit or embedded Python UI
- New lifecycle evaluation rules or NetBox sync semantics (backend behavior unchanged)
- Replacing NetBox as inventory UI
- MCP client in browser
- Mobile-native applications
- Real-time push/WebSocket live dashboards (polling or refresh-on-action is acceptable for v1)
