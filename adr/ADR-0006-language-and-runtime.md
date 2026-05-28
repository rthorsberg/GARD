# ADR-0006 — Language and runtime: Python 3.12

- **Status**: Accepted
- **Date**: 2026-05-27
- **Feature**: F1 (`001-device-import-normalize`)
- **Source decision**: research.md D1
- **Constitution principle**: VII (Integration Over Replacement)

## Context

GARD must be implementable, extendable, and operable by the same teams
that already run NetBox, Nornir, Ansible, Netmiko, and the official
Model Context Protocol SDK ecosystems. Choosing a language outside that
ecosystem trades short-term performance for long-term operator
unfamiliarity — exactly the wrong trade for a governance platform whose
value is in its rules and audit trail, not its raw throughput.

## Decision

- **Language**: Python 3.12.x (CPython, not PyPy).
- **Pinned floor**: `requires-python = ">=3.12,<3.13"`. 3.13 readiness
  is tracked as a follow-up; we will not block on it.
- **Async-by-default** request handlers, but the worker uses a
  Postgres-backed queue (see ADR D6 / future ADR-0011) — no thread-pool
  fork-bomb.

## Consequences

- We pay a per-request CPython overhead. v1 capacity targets
  (≤50,000 devices, ≤10,000 rows/import sync threshold) are well within
  budget on a 2-vCPU container.
- Operators can extend rules and adapters in the same language they
  already use across the network-automation stack.
- We commit to the FastAPI + Pydantic v2 + SQLAlchemy 2 stack the rest
  of these ADRs assume.

## Alternatives considered

- **Go 1.22** — better concurrency, single-binary deploy, but MCP
  Python SDK is more mature than Go SDK and operator extension story is
  worse for this domain.
- **Rust** — overkill for v1; team velocity hit not justified.
- **Node/TypeScript** — viable (excellent MCP SDK), but the CSP operator
  ecosystem skews Python.

## References

- research.md §D1
- ROADMAP.md (ADR-0006 reservation)
- pyproject.toml `requires-python`
