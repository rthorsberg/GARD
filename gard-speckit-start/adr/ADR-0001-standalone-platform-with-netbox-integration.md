# ADR-0001: GARD as Standalone Platform with NetBox Integration

## Status

Proposed

## Context

GARD could be built as:

1. a NetBox plugin only
2. a standalone platform only
3. a standalone platform with first-class NetBox integration/plugin

NetBox is a strong source of infrastructure reference, but GARD requires lifecycle-specific workflows, risk, MCP, file services, adapters, audit and evidence.

## Decision

Build GARD as a standalone lifecycle platform with first-class NetBox integration and optional NetBox plugin.

## Consequences

Positive:

- GARD can evolve independently.
- NetBox remains clean source/reference for infrastructure identity.
- GARD can include MCP, workflows, file services and adapters without overloading NetBox.
- NetBox plugin can provide useful visibility.

Negative:

- Requires synchronization design.
- Requires clear source-of-truth boundaries.
- Adds one more platform to operate.

## Source-of-truth rule

NetBox owns what exists and where it belongs.

GARD owns firmware lifecycle intent, drift, readiness, risk, uplift planning and evidence.
