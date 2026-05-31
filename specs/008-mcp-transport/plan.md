# F8 — Native MCP Transport: Implementation Plan

**Feature Branch**: `008-mcp-transport`
**Status**: Draft
**Inputs**: `spec.md`, `research.md` (R-1..R-10), `contracts/`
**Constitution version**: 1.0.0
**Predecessors**: F1 (auth + contracts), F2 (firmware tools deferred), F3–F7 (delegates), F6 (MVP #8 proof)
**Supersedes**: ADR-0013 transport deferral (delegates unchanged)

## Summary

F8 replaces the MCP stub with a live Streamable HTTP server registering all 22 tools from F1–F7. Implements 7 missing F1/F2 delegates; wires existing 16 delegates through a central registry with shared JWT/RBAC/audit. Proves MVP criterion #8 via integration test.

Technical shape:

- **Server**: `gard/mcp/server.py` — MCP SDK Streamable HTTP, mounted at `/mcp` on FastAPI
- **Registry**: `gard/mcp/registry.py` — explicit tool → delegate map
- **Handler**: `gard/mcp/handler.py` — auth, RBAC, session, audit wrapper
- **New delegates**: `gard/mcp/tools/list_devices.py`, `get_device_lifecycle_status.py`, + 5 F2 firmware tools
- **Contract**: `specs/008-mcp-transport/contracts/mcp-tools.yaml` — merged manifest + server metadata
- **ADR-0019**: MCP transport binding
- **CLI**: `gard mcp` starts uvicorn with MCP mount (or dedicated port)
- **Tests**: contract (metadata), integration (live transport + MVP #8), deny-list

## Technical Context

| Aspect | Choice |
|---|---|
| MCP SDK | `mcp>=1.0,<2` (already in pyproject.toml) |
| Transport | Streamable HTTP at `/mcp` |
| Auth | Shared bearer JWT with REST (ADR-0008) |
| RBAC | `INVOKE_MCP_TOOL` + per-tool permission |
| DB sessions | `session_scope()` per invocation |
| Audit | `mcp.tool.invoked`, `mcp.disallowed_tool_attempt` |
| Tool count | 22 registered, 6 explicitly disallowed |

## Constitution Check

| Principle | F8 adherence |
|---|---|
| I — Governance Before Execution | Draft tools remain non-mutating; no execution tools |
| II — Desired vs Actual | Tools surface existing controller facts only |
| III — Unknown Is First-Class | Device/firmware unknown paths preserved in envelopes |
| IV — Lifecycle-as-Catalog | No catalog mutation tools |
| V — Evidence/Audit | Every MCP call audited with correlation_id |
| VI — Curated MCP | Registry-only surface; deny-list enforced |
| VII — Integration Over Replacement | MCP parallels REST; no bypass of policy layer |

## Project Structure

**New**

- `adr/ADR-0019-mcp-transport-binding.md`
- `specs/008-mcp-transport/contracts/mcp-tools.yaml`
- `gard/mcp/registry.py`
- `gard/mcp/handler.py`
- `gard/mcp/tools/list_devices.py`
- `gard/mcp/tools/get_device_lifecycle_status.py`
- `gard/mcp/tools/get_target_firmware.py`
- `gard/mcp/tools/get_upgrade_path.py`
- `gard/mcp/tools/list_firmware_targets.py`
- `gard/mcp/tools/list_firmware_packages.py`
- `gard/mcp/tools/list_upgrade_paths.py`
- `tests/contract/test_mcp_registry.py`
- `tests/contract/test_firmware_mcp_tools.py`
- `tests/contract/test_device_mcp_tools.py`
- `tests/integration/test_mcp_transport_isr1121.py`
- `specs/008-mcp-transport/quickstart.md`

**Extended**

- `gard/mcp/server.py` — real implementation
- `gard/api/app.py` — mount MCP sub-app
- `gard/core/settings.py` — `mcp_enabled`, `mcp_path`
- `tests/integration/test_mvp_vertical_slice_isr1121.py` — optional live MCP assertion
- `ROADMAP.md`, `README.md`

## PR slices

| Slice | Scope |
|---|---|
| **8a** | ADR-0019, spec/plan/research/contracts, registry types (no server) |
| **8b** | F1+F2 delegate modules + contract tests |
| **8c** | Server + handler + FastAPI mount + `gard mcp` |
| **8d** | Integration tests, quickstart, docs |

## Risks

| Risk | Mitigation |
|---|---|
| MCP SDK API drift | Pin minor version; wrap in thin adapter |
| Auth context not available in MCP middleware | Pass ASGI scope / custom dependency injection |
| Large tool list startup cost | Lazy delegate import acceptable; explicit registry |
| F6 tests assume no socket | Add separate integration module; keep delegate tests |
