# Research: Device Import & Normalize (F1)

This document resolves the open decisions left in the spec's Assumptions
section and the Technical Context "NEEDS CLARIFICATION" slots. Each
decision becomes an ADR in `adr/` during implementation (ADR numbers
0006–0010 are reserved for the decisions below per `ROADMAP.md`).

---

## D1 — Language & Runtime *(→ ADR-0006)*

**Decision**: **Python 3.12** on Linux. CPython, not PyPy.

**Rationale**:
- Network automation and CSP tooling ecosystems are Python-dominant
  (NetBox, Nornir, Ansible, Netmiko, NETCONF client libs). Operators
  who extend GARD's normalization rules and contribute lifecycle
  catalogues will mostly be Python-fluent.
- Official MCP SDK in Python (`mcp` package) is first-tier supported
  and tracks the spec closely.
- FastAPI + Pydantic v2 give us OpenAPI for free and one schema model
  shared between REST request/response and DB DTOs.
- Async-by-default request handling fits the import-job worker pattern
  without bringing in a thread-pool fork-bomb.
- 3.12 is mainstream LTS-equivalent at the time of writing; we pin to
  3.12.x and document 3.13 readiness as a follow-up.

**Alternatives considered**:
- **Go 1.22**: superior concurrency primitives and single-binary deploy,
  but MCP SDK is less mature, CSV/Pydantic ergonomics are weaker, and
  the operator extension story is worse for this domain.
- **Rust**: overkill for v1; team-velocity hit not justified.
- **Node/TypeScript**: viable (official MCP SDK is excellent), but the
  CSP operator ecosystem skews Python and reusing existing CSP-internal
  Python tooling matters more than runtime perf in v1.

---

## D2 — Database & Migrations *(→ ADR-0007)*

**Decision**: **PostgreSQL 16** for application data, audit, and
`LifecycleEvidence`. **SQLAlchemy 2.x** (ORM + Core) with
**Alembic** migrations. No second datastore in v1.

**Rationale**:
- JSONB columns hold raw CSV payloads and evidence-before/after blobs
  with full indexability — keeps `DeviceObservation.raw_payload` queryable
  without a sidecar document store.
- Row-level constraints (CHECKs, partial uniqueness) express the
  domain's invariants (e.g., serial uniqueness when present,
  hostname+site fallback) cleanly.
- `FOR UPDATE SKIP LOCKED` gives us a simple, durable worker queue
  without bringing in Redis/Celery/RabbitMQ.
- Audit append-only is enforceable at the database role level
  (`REVOKE UPDATE, DELETE`) — see D4.
- Production HA via streaming replication / Patroni is well-trodden.

**Alternatives considered**:
- **SQLite**: rejected — single-writer constraint blocks the worker
  pattern and future multi-process scaling.
- **MySQL/MariaDB**: JSON ergonomics weaker than JSONB; partial indexes
  are restricted.
- **CockroachDB / Yugabyte**: distributed strength irrelevant in v1;
  cost in operational complexity not justified.

---

## D3 — Authentication & RBAC *(→ ADR-0008)*

**Decision**: **OIDC for human users + signed JWT API tokens for
service/MCP clients**, both validated by a single FastAPI dependency.
RBAC implemented as a role→permission catalogue (Python dict / YAML),
enforced by a `require(permission)` middleware that fronts every REST
route and every MCP tool.

**Auth mechanics**:
- Human users authenticate via OIDC (Keycloak / Entra ID / Okta —
  IdP-agnostic, discovery URL configured per deployment). Sessions
  are stateless JWTs issued by the IdP.
- Service / MCP clients authenticate via long-lived signed JWT tokens
  issued by GARD's own admin endpoint and carried as
  `Authorization: Bearer ...`. Token records are stored in the DB and
  can be revoked.
- All tokens carry `sub`, `aud=gard`, `roles=[...]`, `exp`, `correlation_hint`.

**Roles for F1** (subset of the security spec):
- `viewer` — read-only on all F1 surfaces
- `lifecycle_manager` — import, manage normalization rules, manual
  mappings, re-evaluate
- `mcp_client` — call read-only MCP tools only
- `system_admin` — manage tokens, roles, system settings

**Rationale**:
- OIDC is the de-facto enterprise SSO standard; no operator wants a
  local user table on a governance platform.
- Splitting human (OIDC) and service (signed JWT) tokens keeps the
  audit trail clean — every audit row has a clear `actor_type`.
- One middleware for both transports is what makes Constitution VI
  enforceable ("MCP flows through the same RBAC and audit pipeline").

**Alternatives considered**:
- **Built-in user table**: rejected — operators want SSO from day 1.
- **API keys (opaque tokens)**: rejected — signed JWTs let us encode
  audience/roles without a DB round-trip on every call.
- **mTLS only**: viable for service clients but worse UX for MCP
  developers; postponed to v2 as an additional option.

---

## D4 — Audit & Evidence Storage *(→ ADR-0009)*

**Decision**: Both `AuditEvent` and `LifecycleEvidence` live in
**PostgreSQL tables** in v1. The tables are **append-only at the DB
role level**: the application role has `INSERT, SELECT` only;
`UPDATE` and `DELETE` are revoked. A **daily checksum-chain job** seals
the previous day's events into a hash chain (SHA-256 of canonical JSON
of the row, chained with previous hash) and stores the head hash in a
separate `audit_chain_heads` table.

**Schema sketch**:
- `audit_events` (append-only): id, timestamp, actor, actor_type,
  action, object_type, object_id, before, after, result,
  correlation_id, source_ip, row_hash
- `lifecycle_evidence` (append-only): id, evidence_type, subject_type,
  subject_id, before_state (JSONB), after_state (JSONB), actor, system,
  timestamp, source_checksum (e.g. CSV file SHA-256), references,
  row_hash
- `audit_chain_heads`: day, last_event_hash, sealed_at

**Rationale**:
- One Postgres database is the simplest deployable v1 stack and matches
  the architecture spec.
- DB-role enforcement is a single, auditable mechanism — no application
  code path can mutate audit data.
- A hash chain gives tamper-evidence without requiring external
  append-only object storage in v1.
- Schema fields match the security spec verbatim, so v2 can migrate
  to a dedicated audit DB / object store with no domain-model change.

**Alternatives considered**:
- **Separate audit Postgres instance**: rejected as premature; can be
  promoted later by moving the two tables to a separate connection
  string.
- **Append-only object store (S3 with Object Lock / WORM)**: stronger
  guarantee, but adds an external dependency in v1; revisit in v2.
- **Event-sourced log (Kafka / Redpanda)**: overkill for v1 volumes;
  introduces a streaming dependency.

---

## D5 — Normalization Rules: Format & Resolution Order *(→ ADR-0010)*

**Decision**: Normalization rules are **YAML files** in
`gard-catalog/normalization/`, loaded at process boot and on demand via
an admin endpoint. A **DB override table** holds hot edits made through
the API; on persist-to-file, overrides are merged back into the
appropriate YAML and the DB row marked `exported_at`.

**Resolution order** (deterministic; first match wins within a tier,
tiers evaluated top-down):

1. **Manual mapping**: an explicit, audited mapping for a specific
   `DeviceObservation.id` — highest precedence by design (operator
   intent).
2. **DB override rule** ordered by `priority DESC, specificity DESC,
   created_at DESC` — hot edits not yet exported.
3. **File rule** ordered by `priority DESC, specificity DESC,
   path-lexical ASC` — committed catalog.

**Rule schema** (illustrative; see
`contracts/normalization-rule.schema.yaml`):

```yaml
id: cisco-isr-1121
priority: 100
match:
  vendor_raw_regex: '^(?i)cisco(\s+systems)?$'
  model_raw_regex:  '^(?i)isr\s*1121.*'
output:
  vendor_normalized: Cisco
  model_normalized: ISR1121
  platform_family: cisco-ios-xe
confidence: exact
notes: 'Matches "Cisco ISR1121", "cisco systems isr-1121"'
```

**Specificity**: number of constrained match fields (regex/exact),
weighted toward exact > regex.

**Conflict policy**: when two rules tie on (tier, priority, specificity),
the loader emits a `RuleConflict` warning surfaced in the
rule-conflict report; resolution falls back to `created_at DESC` (or
path-lexical for files) so the outcome is still deterministic.

**Rationale**:
- YAML-first satisfies Constitution IV (Lifecycle-as-Code) and is
  reviewable in PRs.
- The DB override layer makes the API CRUD path real without losing the
  Git-managed source of truth — operators export overrides back when
  they're stable.
- Three-tier ordering keeps human intent (manual mapping) inviolable
  while still letting catalog rules drive the bulk path.

**Alternatives considered**:
- **DB-only rules**: rejected — violates Constitution IV.
- **YAML-only rules (no DB layer)**: rejected — every API edit would
  require a Git commit; not viable for a running service.
- **Rego / OPA**: powerful but premature; reconsider for F4's
  prerequisite rule engine.

---

## D6 — Async Job Processing

**Decision**: **Postgres-backed worker queue**, no Redis / Celery / arq.
A `gard.worker` process polls the `import_jobs` table with
`SELECT ... FOR UPDATE SKIP LOCKED` and processes one job at a time.
Sync path (≤ 10,000 rows) runs inline via FastAPI; async path enqueues
and returns the job id.

**Rationale**:
- Zero added infrastructure beyond Postgres in v1.
- `FOR UPDATE SKIP LOCKED` is well-supported, durable, and trivial to
  reason about.
- The worker is the only place that flips `import_jobs.status` past
  `processing`, eliminating race conditions.
- The 10,000-row threshold is a setting in `gard.settings`, not a hard
  constant — operators tune it.

**Alternatives considered**:
- **Celery + Redis**: extra moving parts; not needed for v1 volumes.
- **arq + Redis**: same objection.
- **Procrastinate** (Postgres-backed): would also work; rejected only to
  keep the dependency surface minimal. Revisit when concurrent waves
  arrive in F5.

---

## D7 — CSV Parsing & Validation

**Decision**: Python stdlib `csv` (streaming reader) + **Pydantic v2**
row models. UTF-8 only. The CSV schema lives in
`contracts/csv-schema.yaml` and is version-tagged in the
`X-Gard-Csv-Schema-Version` HTTP header echoed in the response.

**Rationale**:
- Stdlib `csv` plus Pydantic gives streaming parsing with strong typing
  and zero extra dependency.
- Pandas is rejected: heavy import, eager-load surprises at large row
  counts, ergonomically wrong shape for per-row error reporting.

**Alternatives considered**:
- **pandas**: rejected for above reasons.
- **polars**: faster than pandas, but per-row Pydantic validation in a
  streaming loop is fast enough at v1 volumes and keeps error reporting
  clean.

---

## D8 — REST Framework & MCP Transport

**Decision**: **FastAPI** for REST. **Official `mcp` Python SDK** with
**Streamable HTTP** transport for MCP. Both run in the same process,
share the same OIDC/JWT dependency, and emit audit through the same
helper.

**Rationale**:
- Streamable HTTP MCP transport sits behind the same ingress as the
  REST API, so RBAC, audit, and structured logging are literally the
  same middleware. stdio transport would force a separate process
  outside the gateway.
- FastAPI auto-generates OpenAPI from Pydantic models; our
  `contracts/rest-openapi.yaml` is the human-curated contract and the
  generated OpenAPI is what's served at runtime — drift is checked in
  CI.

**Alternatives considered**:
- **MCP stdio transport**: rejected — agents are remote; CSP ops teams
  want one HTTPS endpoint behind their IdP, not per-agent SSH tunnels.
- **Starlette + custom routing**: FastAPI is built on Starlette; no
  reason to skip the ergonomics.

---

## D9 — Identity Resolution for Devices

**Decision**: Canonical `Device` identity in F1 is:

1. **`serial_number`** when present and non-empty (case-insensitive,
   trimmed).
2. **`(hostname, site)`** fallback when serial is absent.
3. Reject the row if both are absent.

Two rows in the same import with the same effective identity collapse
to one canonical `Device` but produce two `DeviceObservation` rows.

**Rationale**:
- Serial is the most stable identifier across vendor and management
  systems; using it first means future NetBox integration (F7) joins
  cleanly on serial.
- `(hostname, site)` is the operator-friendly fallback for devices
  whose serial isn't surfaced in the discovery export.
- Refusing serial-less + site-less rows is correct under Constitution
  III: unknown identity isn't classifiable, and we shouldn't invent a
  default.

**Alternatives considered**:
- **Always use hostname**: rejected — collisions across sites are
  common in CSP networks.
- **Synthetic id from all fields hashed**: rejected — opaque,
  un-debuggable.

---

## D10 — Project Layout & ADR Location

**Decision**: Single backend Python project at repo root under `gard/`.
ADRs from F1 onward live in `adr/` at the repo root. Seed ADRs
0001–0005 remain in `gard-speckit-start/adr/` as historical input;
they are referenced (not moved) from new ADRs.

**Rationale**:
- One deployable in v1; layout matches the controller architecture
  from `gard-speckit-start/specs/03-architecture.md`.
- ADRs at the root next to `ROADMAP.md` and `README.md` are easy to
  find and link to from PRs.

**Alternatives considered**:
- **Move seed ADRs to `adr/`**: rejected — keeps the seed package
  immutable as a snapshot input.
- **Polyrepo / packages monorepo**: rejected — premature for v1.

---

## Open follow-ups (deliberately deferred)

| Topic | Why deferred | Lands in |
|---|---|---|
| Vault / secret-manager wiring | F1 ships a `SecretProvider` abstraction with an env-only adapter; Vault adapter is added when production deployment needs it | Later infra feature |
| Multi-tenancy | v1 is single-tenant per `Scale/Scope` | Post-v1 |
| Rule-engine performance at >1M devices | v1 targets ≤50,000 devices; benchmark and revisit as needed | F6 or post-v1 |
| OIDC IdP selection | GARD is IdP-agnostic; deployment chooses Keycloak / Entra / Okta via config | Deployment-time |
| Object-storage promotion for evidence | v1 keeps evidence in Postgres with hash chain; promotion path is documented in ADR-0009 | v2 |
