# ADR-0005: TR-069/ACS as Southbound Adapter, Not GARD Core

## Status

Proposed

## Context

TR-069 ACS platforms already manage CPE configuration, firmware download and result reporting. Some GARD functionality overlaps with ACS features.

## Decision

GARD shall not replace TR-069 ACS platforms. GARD shall integrate with ACS/TR-069/TR-369 as southbound lifecycle execution adapters.

## Rule

ACS performs device management.

GARD performs lifecycle governance.

## Consequences

Positive:

- leverages existing CPE management investments
- avoids reinventing mature ACS functionality
- keeps GARD cross-domain and protocol-independent

Negative:

- requires adapter design
- data synchronization and state consistency must be handled
