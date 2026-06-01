# Feature Specification: Native MCP Transport

**Feature Branch**: `008-mcp-transport`
**Created**: 2026-05-31
**Status**: Draft
**Input**: User description: "F8 — Native MCP Transport: wire existing tool delegates to a live Streamable HTTP MCP server with auth, RBAC, and contract registration per ADR-0013"

## Why this feature exists

F1–F7 shipped **22 curated MCP tool contracts** and **16 Python delegates** (F3–F7), but the MCP server remains a stub (`gard/mcp/server.py` raises `NotImplementedError`). ADR-0013 deliberately deferred transport so F2–F7 could land REST-first without doubling every PR.

F8 closes the MVP gap called out in `gard-speckit-start/specs/04-mvp-scope.md` acceptance criterion **#8**: an AI agent must be able to ask GARD lifecycle questions over MCP — not only via REST or in-process delegate tests.

> *MCP exposes curated lifecycle tools, not raw infrastructure (Constitution VI). F8 is the transport layer; it does not invent new lifecycle semantics.*

Without F8, operators and copilots must use REST for every query, and F6's delegate-only MCP validation never exercises auth, audit, or JSON-RPC framing end-to-end.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Live MCP server answers ISR1121 compliance questions (Priority: P1)

A platform engineer starts GARD with MCP enabled. She mints an `mcp_client` token, connects a Streamable HTTP MCP client to `/mcp`, lists tools, and invokes `count_devices_outside_target` with `{vendor_normalized: "Cisco", model_normalized: "ISR1121"}`. The server validates JWT auth, checks RBAC, routes to the existing delegate, returns a bounded JSON result with `correlation_id`, and writes an `mcp.tool.invoked` audit row.

**Why this priority**: This is MVP acceptance criterion #8 — the primary proof that GARD is agent-ready.

**Independent Test**: Integration test against seeded ISR1121 fixture: MCP client calls `count_devices_outside_target`; response count matches REST `GET /api/v1/compliance/summary`; audit row exists with matching `correlation_id`.

**Acceptance Scenarios**:

1. **Given** a valid `mcp_client` token and seeded ISR1121 data, **When** the client invokes `count_devices_outside_target`, **Then** the response conforms to the F3 contract schema and matches the REST summary count.
2. **Given** a `viewer`-only token (no `INVOKE_MCP_TOOL`), **When** any MCP tool is invoked, **Then** the call is denied, zero records are returned, and audit records `result=denied`.
3. **Given** the MCP server is running, **When** a client calls `tools/list`, **Then** all 22 published tools from F1–F7 contracts appear with correct names and input JSON Schemas.

---

### User Story 2 - Single auth and audit pipeline with REST (Priority: P1)

Security review requires MCP and REST to share the same OIDC/JWT validation, RBAC permission checks, correlation-id propagation, and audit pipeline. An operator traces one MCP tool call and finds the same actor, permission, and envelope discipline as an equivalent REST call.

**Why this priority**: Constitution V/VI and ADR-0008 — divergent auth paths would create a shadow API surface.

**Independent Test**: Invoke `get_readiness_summary` via MCP and REST with the same token/filters; compare payloads (modulo transport wrapper); assert identical audit action and permission fields.

**Acceptance Scenarios**:

1. **Given** a bearer JWT accepted by REST, **When** the same token is sent to MCP, **Then** auth succeeds and the subject/roles resolve identically.
2. **Given** any successful MCP tool invocation, **When** audit is queried, **Then** an `mcp.tool.invoked` event exists with tool name, actor, records returned, and `correlation_id`.
3. **Given** an MCP request with a malformed tool input, **When** schema validation fails, **Then** the client receives a structured validation error and no database mutation occurs.

---

### User Story 3 - Complete tool registry from F1–F7 contracts (Priority: P1)

F8 registers every tool published across feature contracts — including F1 device tools and F2 firmware catalog tools whose delegates were never wired because transport was deferred. An agent can traverse the full read/draft surface: devices, firmware compliance, drift, readiness, uplift planning, and NetBox summary.

**Why this priority**: Partial registration would leave agents guessing which facts require REST fallback — defeating the purpose of a native MCP server.

**Independent Test**: Contract test iterates all entries in merged `contracts/mcp-tools.yaml` manifests (F1–F7); each has a registered delegate, `TOOL_NAME`, `REQUIRED_PERMISSION`, and passing schema metadata test.

**Acceptance Scenarios**:

1. **Given** the merged tool manifest, **When** the server starts, **Then** exactly the published read/draft tools are registered (22 tools; disallowed names from F2 contract are rejected with `tool_not_found`).
2. **Given** `get_target_firmware` is invoked for a known device, **When** the delegate runs, **Then** output matches `GET /api/v1/devices/{id}/firmware-compliance`.
3. **Given** `list_devices` with pagination, **When** `limit=5` and more devices exist, **Then** `next_page_token` is present and a follow-up call returns the next page.

---

### User Story 4 - Disallowed tools and bounded outputs (Priority: P2)

An AI agent attempts to invoke a tool not on the published list (e.g. `execute_sql` from the F2 disallowed block). The server rejects the call, emits `mcp.disallowed_tool_attempt`, and never executes infrastructure access.

**Why this priority**: Constitution VI — the deny-list is as important as the allow-list for safe agent deployment.

**Independent Test**: MCP client calls `execute_sql`; receives `tool_not_found`; audit contains `mcp.disallowed_tool_attempt`.

**Acceptance Scenarios**:

1. **Given** a tool name outside the published registry, **When** invoked, **Then** MCP returns `tool_not_found` and audit records the attempt with client identity.
2. **Given** a list tool with `limit=500`, **When** more rows match, **Then** results are truncated with pagination token; response size stays within contract bounds.

---

### User Story 5 - Operator runbook: `gard mcp` and Docker (Priority: P2)

An operator runs MCP either as a standalone process (`gard mcp`) or co-located with the API (mounted at `/mcp` on the existing uvicorn app — binding decision in plan/research). Documentation covers token minting, endpoint URL, and a curl/SDK smoke example against the ISR1121 fixture.

**Why this priority**: MVP demos and local dev must not require reading test code to connect an MCP client.

**Independent Test**: Follow `quickstart.md` on Docker Compose; MCP smoke call succeeds within 5 minutes of `make seed`.

**Acceptance Scenarios**:

1. **Given** Docker Compose is up, **When** the operator follows the quickstart, **Then** MCP responds to `initialize` + one tool call.
2. **Given** MCP is disabled via settings, **When** a client connects, **Then** the endpoint returns a clear not-enabled response (no partial tool surface).

---

### Edge Cases

- **Expired or malformed JWT**: 401 before tool dispatch; no partial results.
- **Missing tool-specific permission**: 403 with audit `result=denied` even if `INVOKE_MCP_TOOL` is present.
- **Database unavailable**: 503 with structured error; no silent empty success.
- **Concurrent tool calls**: Each call gets its own DB session and correlation id; no cross-request state leakage.
- **Draft tools (`create_uplift_wave_draft`)**: Return proposal only; no DB writes (same as REST dry-run semantics from F5).
- **Unknown device ref in `get_device_lifecycle_status`**: Envelope with explainable `unknown` state, not a transport-level 500.

## Functional Requirements

- **FR-001**: GARD MUST expose a Streamable HTTP MCP server at `/mcp` (or documented alternate path) using the official MCP Python SDK already declared in `pyproject.toml`.
- **FR-002**: The server MUST register all **22** published tools from F1–F7 contracts: F1 (2), F2 (5), F3 (4), F4 (4), F5 (6), F7 (1).
- **FR-003**: F1 and F2 tools MUST ship as new delegate modules matching the existing F3–F7 delegate pattern (`TOOL_NAME`, `REQUIRED_PERMISSION`, Pydantic input/output, `invoke(session, body)`).
- **FR-004**: Every tool invocation MUST validate bearer JWT using the same dependency as REST (ADR-0008).
- **FR-005**: Every tool invocation MUST enforce `INVOKE_MCP_TOOL` plus the tool-specific permission from its contract.
- **FR-006**: Every successful or denied invocation MUST emit an audit event (`mcp.tool.invoked` or equivalent deny path) with `correlation_id`, actor, tool name, and record count.
- **FR-007**: Inputs MUST be validated against each tool's JSON Schema / Pydantic model before controller execution.
- **FR-008**: Outputs MUST match REST-parity shapes documented in per-feature `contracts/mcp-tools.yaml`, including `correlation_id`.
- **FR-009**: Invocations of tools outside the published registry MUST return `tool_not_found` and emit `mcp.disallowed_tool_attempt`.
- **FR-010**: The CLI entry point `gard mcp` MUST start the MCP server (replacing the current `NotImplementedError` stub).
- **FR-011**: Integration tests MUST prove MVP criterion #8: live MCP `count_devices_outside_target` for Cisco ISR1121 matches REST.
- **FR-012**: Documentation MUST cover token minting, endpoint URL, enabled/disabled configuration, and a smoke example.
- **FR-013**: Draft-action tools MUST remain non-mutating at the MCP layer (proposals only; human submits via REST).
- **FR-014**: MCP MUST NOT expose raw SQL, shell, filesystem, unrestricted HTTP, or execution adapters.

## Key Entities

- **McpToolRegistry** — runtime map of tool name → delegate module, input schema, required permission.
- **McpToolInvocation** — ephemeral request context: actor, correlation_id, tool name, validated input, outcome.
- **AuditEvent** (existing) — extended use for `mcp.tool.invoked`, `mcp.disallowed_tool_attempt`.
- **Tool contracts** (existing) — YAML manifests in `specs/001`…`specs/007`; F8 adds merged registry contract.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An MCP client with a valid `mcp_client` token can invoke `count_devices_outside_target` for Cisco ISR1121 and receive a count matching REST within the ISR1121 integration fixture (MVP criterion #8).
- **SC-002**: All 22 published tools appear in `tools/list` and pass existing contract metadata tests plus at least one live-transport integration test per feature family (F1, F2, F3, F4, F5, F7).
- **SC-003**: 100% of MCP tool calls (success and deny paths) produce an audit row queryable by `correlation_id`.
- **SC-004**: Unauthorized tokens (`viewer`-only) are denied on 100% of tool invocations with zero data leakage in integration tests.
- **SC-005**: Disallowed tool names (`execute_sql`, etc.) are rejected on 100% of attempts with `mcp.disallowed_tool_attempt` audit.
- **SC-006**: Operator quickstart: from Docker Compose up to first successful MCP tool call in under 5 minutes.
- **SC-007**: CI remains green — no new infrastructure beyond existing Postgres + pytest; MCP integration tests use in-process or httpx client against test app.
- **SC-008**: No new lifecycle states, controllers, or REST endpoints — F8 is transport + missing F1/F2 delegates only.

## Assumptions

- The official `mcp` Python SDK (already in dependencies) supports Streamable HTTP suitable for co-location with FastAPI.
- F1–F7 delegate implementations for F3–F7 require no semantic changes — F8 only registers them.
- F2 disallowed tool names remain reject-only entries, not registered delegates.
- MCP v1 stays read + draft-only; execution and approval tools remain out of scope (per seed doc §Disallowed).
- Rate limiting follows F1 contract default (600/min per token) or existing middleware if present.
- Single-server deployment (API + MCP) is acceptable for v1; separate `gard mcp` process remains supported for dev.

## Dependencies

- **F1** — auth/RBAC, device controllers, MCP skeleton contracts.
- **F2** — firmware compliance controllers for five catalog tools.
- **F3–F5, F7** — existing delegates and contracts.
- **F6** — ISR1121 fixture for MVP criterion #8 integration test.
- **ADR-0013** — deferral record; F8 supersedes the transport gap (not the delegate pattern).
- **ADR-0008** — shared JWT auth model.

## Out of Scope

- MCP resources (`gard://schema/...`) beyond optional stub URIs — can land as P3 stretch.
- stdio transport, SSE-only legacy transport, or multi-tenant MCP routing.
- New lifecycle tools not already contracted in F1–F7.
- Execution adapters, wave approval, exception approval, NetBox write-back.
- Reporting tools from seed doc not yet contracted (`create_compliance_report`, etc.).
