# ADR-0013: MCP firmware tools deferred to a follow-up feature

- **Status**: Accepted (2026-05-30)
- **Feature**: F2 (002-firmware-catalog)
- **Related**: F2 tasks T060–T067 (US5), ADR-0008 (MCP transport)
- **Supersedes**: nothing
- **Decision drivers**: scope-creep risk, complete-vertical principle, REST parity

## Context

F2's User Story 5 ("AI agents query firmware catalog via MCP tools")
specifies five MCP tools: `get_target_firmware`, `get_upgrade_path`,
`list_firmware_targets`, `list_firmware_packages`,
`list_upgrade_paths`. The contracts in
`specs/002-firmware-catalog/contracts/mcp-tools.yaml` lock the
input/output schemas.

The F1 MCP server is a stub (`gard/mcp/server.py` = 8 lines that raise
`NotImplementedError`). The F1 spec text references MCP tools but the
implementation was deferred there as well — F1's `auth.denied` paths
exist on paper but are not exercised against a running MCP transport.

Standing up a real MCP Streamable HTTP server inside F2 means:

1. Adding the official `mcp` Python SDK (or a stripped server) to
   `pyproject.toml` + the Docker image.
2. Wiring an ASGI sub-application or a second uvicorn worker so MCP
   doesn't share request semantics with REST.
3. Implementing the JSON-RPC framing, tool registration, auth
   dependency, and the per-tool envelope-vs-MCP-result transformers
   for all five F2 tools — plus retrofitting whatever F1 promised.
4. Writing the contract tests (T060) and integration tests (T061)
   against a transport that does not yet exist.

That is roughly the same surface area as everything F2 has already
shipped. Folding it into PR #2 would more than double the diff and
push the merge past the operator-value threshold (the REST endpoints
already deliver every fact the MCP tools would surface).

## Decision

**MCP firmware tools are deferred out of F2.** PR #2 ships:

- Full REST coverage of all catalog read surfaces (targets, packages,
  upgrade-paths, prerequisites, compliance).
- Verified blob upload/download with SHA-256 round-trip.
- The reload + bounded re-eval pipeline.

The MCP layer will be picked up as a dedicated follow-up feature
(working title `003-mcp-firmware-tools`) once F3 design has surfaced
whether the drift-detection surface also wants its own MCP tools —
that affects how the MCP server is structured (single server hosting
all tools vs. per-feature sub-servers).

## Consequences

### Positive

- F2 PR stays reviewable. The blob path + reload + envelope state
  machine are already a meaningful read for a reviewer.
- The MCP follow-up can be tested in isolation against its own
  transport contract, rather than racing the REST integration tests
  through the F1 stub.
- The deferral surfaces an honest gap rather than shipping a half-
  wired MCP server.

### Negative

- F2's spec.md still lists US5 in the SC table; we leave that
  unchecked. ROADMAP.md will mark US5 as **deferred to 003** rather
  than **delivered in 002**.
- Operators or AI agents that wanted to call `get_target_firmware`
  from an MCP client must instead use the REST endpoint
  `GET /api/v1/devices/{id}/firmware-compliance`. The payload is
  byte-identical modulo the correlation_id header.

### Neutral

- All five tools' implementations would have been thin delegates over
  the existing controllers (`compliance_controller.evaluate()`,
  `upgrade_path_graph.shortest_path()`, etc.), so the work is
  preserved — the controllers are stable. F003 will be ~one file per
  tool plus the server scaffold.

## Decision record

| What | Where |
|---|---|
| Tasks deferred | T060–T067 (F2 tasks.md) |
| Tracker | `specs/002-firmware-catalog/tasks.md` will gain a "Deferred to 003" footer |
| Spec impact | F2 SC-007 (MCP tool count) will be checked when 003 lands |
| Compatibility | None — there is no MCP client in the wild to break |
