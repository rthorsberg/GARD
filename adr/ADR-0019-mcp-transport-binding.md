# ADR-0019: MCP transport binding

- **Status**: Accepted (2026-05-31)
- **Feature**: F8 (008-mcp-transport)
- **Related**: ADR-0013 (deferral), ADR-0008 (auth), Constitution VI
- **Supersedes**: the transport-deferral consequence in ADR-0013 (historical record preserved)

## Context

F1–F7 published 22 MCP tool contracts and 16 Python delegates. The MCP
server stub (`gard/mcp/server.py`) raised `NotImplementedError` per
ADR-0013 so feature PRs stayed REST-first.

F8 must close MVP acceptance criterion #8: agents query lifecycle state
over live Streamable HTTP MCP, not only via in-process delegate tests.

## Decision

1. **Transport**: Official `mcp` Python SDK (`FastMCP`) with Streamable
   HTTP mounted at `GARD_MCP_PATH` (default `/mcp`) on the existing
   FastAPI uvicorn app. Standalone `gard mcp` runs the same app factory.

2. **Registry**: Explicit `gard/mcp/registry.py` mapping tool name →
   delegate module + Pydantic input model (22 tools). No filesystem scan.

3. **Auth/RBAC**: ASGI middleware validates bearer JWT via
   `verify_token()` (same as REST). Handler enforces
   `INVOKE_MCP_TOOL` + per-tool `REQUIRED_PERMISSION`.

4. **Audit**: `mcp.tool.invoked` on success/deny; `mcp.disallowed_tool_attempt`
   for deny-list and unknown names (registered as stub tools).

5. **Deny-list**: `execute_sql`, `run_shell`, `read_file`, `write_file`,
   `http_request`, `propose_firmware_target_draft` — never execute.

6. **Settings**: `GARD_MCP_ENABLED` (default `true` in dev/test),
   `GARD_MCP_PATH` (default `/mcp`).

## Consequences

### Positive

- One port (8080) serves REST + MCP in Docker Compose demos.
- F3–F7 delegates unchanged; F8 adds F1/F2 delegates + transport only.
- MVP criterion #8 testable end-to-end.

### Negative

- MCP SDK API surface may drift; wrapped in `gard/mcp/server.py`.

### Neutral

- MCP resources (`gard://schema/...`) remain optional stretch.
