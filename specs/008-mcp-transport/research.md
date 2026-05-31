# F8 — Native MCP Transport: Research & Binding Decisions

**Feature**: `008-mcp-transport`
**Date**: 2026-05-31
**Status**: Draft

## R-1. Transport binding: mount vs standalone

**Decision**: Mount MCP Streamable HTTP as a **FastAPI sub-application** at `/mcp` on the existing uvicorn app **and** support standalone `gard mcp` that runs the same ASGI stack on a configurable port.

**Rationale**:
- F1 plan already specified `/mcp` on the FastAPI app sharing auth dependencies.
- Operators running Docker Compose get one port (8080) for REST + MCP — simpler demos.
- `gard mcp` remains useful for local dev splitting processes without duplicating server logic.

**Alternatives rejected**:
- Separate uvicorn worker only — doubles deployment complexity for v1.
- stdio transport — not suitable for remote agents / Netclaw-style clients.

## R-2. Delegate inventory gap

**Decision**: F8 implements **7 missing delegates** (F1: 2, F2: 5). F3–F7 delegates (16 modules) register as-is.

| Feature | Tools | Delegate status |
|---|---|---|
| F1 | `list_devices`, `get_device_lifecycle_status` | **New in F8** |
| F2 | `get_target_firmware`, `get_upgrade_path`, `list_firmware_targets`, `list_firmware_packages`, `list_upgrade_paths` | **New in F8** |
| F3 | 4 tools | Exists |
| F4 | 4 tools | Exists |
| F5 | 6 tools | Exists |
| F7 | `get_netbox_sync_summary` | Exists |

**Total registered**: 22 tools.

## R-3. Auth/RBAC wiring

**Decision**: Reuse `gard.api.deps.auth` (or equivalent) inside MCP tool handler wrapper:
1. Extract bearer token from MCP request context.
2. Resolve `Actor` + roles.
3. Check `Permission.INVOKE_MCP_TOOL` then tool-specific `REQUIRED_PERMISSION`.
4. Propagate `correlation_id` via existing middleware pattern.

Denied calls audit with `result=denied` before returning MCP error to client.

## R-4. Tool registry pattern

**Decision**: Central registry in `gard/mcp/registry.py` built from explicit imports (not runtime filesystem scan) mapping `TOOL_NAME` → module + Pydantic input model.

**Rationale**: Explicit imports catch missing delegates at import time; contract tests already validate metadata per module.

## R-5. Session lifecycle

**Decision**: Each tool invocation opens a short-lived `session_scope()` (read) or `append_only_scope()` when audit writes are needed — mirror REST router pattern.

## R-6. Disallowed tools

**Decision**: Hard-coded deny set from F2 contract (`execute_sql`, `run_shell`, `read_file`, `write_file`, `http_request`, `propose_firmware_target_draft`) plus any unknown name → `tool_not_found` + `mcp.disallowed_tool_attempt`.

## R-7. MVP criterion #8 proof

**Decision**: New integration test `tests/integration/test_mcp_transport_isr1121.py` uses MCP client SDK against test FastAPI app with ISR1121 seed; asserts `count_devices_outside_target` parity with REST.

Updates F6 vertical-slice test comment: transport no longer deferred.

## R-8. ADR

**Decision**: Add **ADR-0019** — MCP transport binding (mount point, auth sharing, registry pattern, deny-list). Supersedes the "transport deferred" consequence in ADR-0013 (tools land; ADR-0013 historical record preserved).

## R-9. Settings

**Decision**: Add `GARD_MCP_ENABLED` (default `true` in dev, configurable) and `GARD_MCP_PATH` (default `/mcp`). When disabled, mount returns 404 or health indicates MCP off.

## R-10. PR slices

| Slice | Scope |
|---|---|
| **8a** | ADR-0019, spec/plan/research, merged contract manifest, registry scaffold |
| **8b** | F1+F2 delegates + unit/contract tests |
| **8c** | Server implementation, auth wrapper, mount on FastAPI, `gard mcp` |
| **8d** | Integration tests (MVP #8), quickstart, ROADMAP/README updates |
