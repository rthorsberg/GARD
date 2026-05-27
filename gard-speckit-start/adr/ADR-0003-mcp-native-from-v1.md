# ADR-0003: Native MCP Server from v1

## Status

Proposed

## Context

GARD contains structured lifecycle state that is highly useful to AI agents and chat-based operational assistants.

Example question:

> How many Cisco ISR1121 devices are outside target version?

## Decision

GARD shall include a native MCP server from v1.

## Scope

v1 MCP supports:

- read-only lifecycle queries
- compliance/readiness reports
- blocker explanations
- target firmware lookup
- upgrade path explanation
- draft uplift wave creation

v1 MCP does not support:

- execution
- approval
- target changes
- package upload
- raw SQL
- shell access

## Consequences

Positive:

- GARD is agent-ready from the start.
- Chat/Netclaw/Cursor-style agents can use safe tools.
- Reduces custom integrations for each agent.

Negative:

- Requires strong security model early.
- Requires tool schemas and audit from v1.
