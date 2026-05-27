# ADR-0002: Governance-First, Not Autonomous Upgrade First

## Status

Proposed

## Context

Firmware uplift in CSP networks carries operational risk. Full autonomous execution from v1 may create unacceptable risk and slow adoption.

## Decision

GARD v1 shall be governance-first. It shall support guided and semi-automated workflows, but not uncontrolled autonomous upgrades.

## v1 Allowed

- import
- evaluate
- plan
- dry-run
- create draft wave
- generate command plan
- record manual/semi-automated execution
- validate and evidence result

## v1 Restricted

- autonomous execution across device batches without explicit approval
- MCP-triggered production execution
- blocker overrides without approval

## Consequences

Positive:

- safer adoption
- easier buy-in from network engineers
- stronger focus on lifecycle model and trust

Negative:

- less immediate automation
- execution savings may come later
