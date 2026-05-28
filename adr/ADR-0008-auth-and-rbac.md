# ADR-0008 — Auth and RBAC: OIDC for humans, signed JWT for services, single dependency

- **Status**: Accepted
- **Date**: 2026-05-27
- **Feature**: F1 (`001-device-import-normalize`)
- **Source decision**: research.md D3
- **Constitution principle**: VI (MCP Curated Tools), IV (Audit & Explainability)

## Context

GARD has two transports (REST and MCP) and two principal types (human
operators and service/MCP clients). The constitution forbids MCP from
bypassing the same RBAC and audit pipeline humans use. Operators
universally want SSO; "build us a local user table" is a non-starter.

## Decision

- **Human users** authenticate via **OIDC**. GARD trusts the operator's
  IdP (Keycloak / Entra ID / Okta — discovery URL is per-deployment
  config, `GARD_OIDC_ISSUER` + `GARD_OIDC_AUDIENCE`). Sessions are
  stateless ID-tokens bound to the IdP signing keys.
- **Service / MCP clients** authenticate via **GARD-issued signed JWT**
  API tokens (HS256 in v1, with an RS256 path reserved). Tokens are
  minted via `POST /api/v1/admin/tokens`, stored in the `api_tokens`
  table, can be revoked, and have a default TTL of 30 days
  (`GARD_API_TOKEN_TTL_SECONDS`, FR-025).
- **One FastAPI dependency** (`gard.api.middleware.auth`) accepts both
  token types; downstream code only sees a `Principal` with
  `subject`, `actor_type`, and `roles`.
- **RBAC** is a Python role→permission catalogue
  (`gard.core.rbac`). Roles defined in F1: `viewer`,
  `lifecycle_manager`, `mcp_client`, `system_admin`. Every REST route
  and every MCP tool is gated by a `require(permission)` dependency.

## Consequences

- One middleware funnel for both transports — Constitution VI is
  enforceable by inspection.
- Audit rows always carry an unambiguous `actor_type` (`human` |
  `service` | `mcp_client`).
- Operators must run an OIDC IdP. We provide a docker-compose
  Keycloak example for dev; production deployments bring their own.
- Token revocation is a DB lookup, not a JWT-blacklist gymnastics —
  acceptable cost given the verify path.

## Alternatives considered

- **Built-in user table** — operators reject; SSO is mandatory.
- **API keys (opaque tokens)** — no encoded audience/roles; forces a DB
  round-trip on every request.
- **mTLS only** for services — viable but worse UX for MCP developers;
  reserved as an additive option in v2.

## References

- research.md §D3
- spec.md FR-024 (TLS), FR-025 (token TTL)
- contracts/rest-openapi.yaml `Principal`, `IssueTokenRequest`
- ROADMAP.md (ADR-0008 reservation)
