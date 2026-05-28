# Tasks: Device Import & Normalize

**Input**: Design documents from `/specs/001-device-import-normalize/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md
**Tests**: REQUIRED. The constitution mandates contract + integration tests for every controller boundary, REST endpoint, MCP tool, importer, and catalogue schema.

## Format

`- [ ] [TaskID] [P?] [Story?] Description with file path`

- **[P]**: Different files, no dependency on incomplete tasks — runnable in parallel.
- **[USn]**: Required on user-story-phase tasks; omitted on Setup, Foundational, and Polish.

---

## Phase 1: Setup

**Purpose**: Initialize the repo skeleton, language toolchain, dev environment, and the ADRs that capture the binding decisions from `research.md`.

- [X] T001 Create source tree at repo root: `gard/{api,mcp,core,models,db,catalog}`, `gard-catalog/normalization/`, `tests/{contract,integration,unit}`, `deploy/`, `adr/` (with `__init__.py` where Python packages are needed)
- [X] T002 Create `pyproject.toml` at repo root pinning Python 3.12 with deps: `fastapi>=0.115`, `pydantic>=2.7`, `pydantic-settings`, `sqlalchemy>=2.0`, `alembic`, `psycopg[binary]`, `mcp`, `authlib`, `python-jose[cryptography]`, `structlog`, `httpx`, `uvicorn[standard]`; dev deps: `pytest`, `pytest-asyncio`, `pytest-cov`, `ruff`, `mypy`, `freezegun`
- [X] T003 [P] Configure linters in `pyproject.toml`: ruff (line-length 100, target py312, full ruleset), mypy (strict), pytest (markers `contract`, `integration`, `unit`)
- [X] T004 [P] Create `.github/workflows/ci.yml`: matrix on Python 3.12, runs ruff → mypy → pytest with a Postgres 16 service container; uploads coverage
- [X] T005 [P] Create `gard/settings.py` using pydantic-settings, env-driven; documented keys: `GARD_DB_DSN`, `GARD_OIDC_DISCOVERY_URL`, `GARD_OIDC_AUDIENCE`, `GARD_JWT_SIGNING_KEY`, `GARD_CSV_SYNC_THRESHOLD` (default 10000), `GARD_LOG_LEVEL`
- [X] T006 [P] Create `gard/logging.py` configuring `structlog` with JSON output, ISO timestamps, and a `correlation_id` contextvar
- [X] T007 [P] Create `deploy/Dockerfile` (python:3.12-slim, multi-stage), `deploy/docker-compose.yml` (gard-api, gard-worker, gard-postgres), `deploy/.env.example`
- [X] T008 [P] Create initial `gard-catalog/normalization/cisco.yaml` with the rules shown in `contracts/normalization-rule.schema.yaml` example (cisco-isr-1121, cisco-catalyst-9300) plus `version: 1.0.0` header
- [X] T009 [P] Write `adr/ADR-0006-language-and-runtime.md` from research.md D1 (Python 3.12)
- [X] T010 [P] Write `adr/ADR-0007-database-and-migrations.md` from research.md D2 (PostgreSQL 16 + SQLAlchemy 2 + Alembic)
- [X] T011 [P] Write `adr/ADR-0008-auth-and-rbac.md` from research.md D3 (OIDC + signed-JWT API tokens, single FastAPI dependency)
- [X] T012 [P] Write `adr/ADR-0009-audit-and-evidence-storage.md` from research.md D4 (append-only DB roles + daily checksum chain)
- [X] T013 [P] Write `adr/ADR-0010-normalization-rules-format.md` from research.md D5 (YAML + DB override layer + 3-tier resolution)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Database schema, append-only enforcement, auth/RBAC pipeline, audit + evidence emission helpers, REST + MCP app skeletons. **No user-story work may begin until this phase is complete.**

### Database & migrations

- [ ] T014 Initialize Alembic in `gard/db/migrations/`, configure `alembic.ini` to read DSN from settings; create the bootstrap migration that provisions the two PostgreSQL roles `gard_app` (full INSERT/UPDATE/SELECT on regular tables) and `gard_writer_append_only` (INSERT/SELECT only)
- [ ] T015 [P] Alembic migration: `devices` table per data-model.md, with the two partial unique indexes on `lower(serial_number)` and on `(lower(hostname), lower(site))`, owned by `gard_app`, in `gard/db/migrations/versions/0002_devices.py`
- [ ] T016 [P] Alembic migration: `device_observations` table with JSONB `raw_payload`, GIN index, and grants restricted to `gard_writer_append_only` (REVOKE UPDATE, DELETE from `gard_app`), in `gard/db/migrations/versions/0003_device_observations.py`
- [ ] T017 [P] Alembic migration: `normalization_rules` table with `(source, source_path, id)` constraints, in `gard/db/migrations/versions/0004_normalization_rules.py`
- [ ] T018 [P] Alembic migration: `manual_mappings` table with unique `(observation_id)`, in `gard/db/migrations/versions/0005_manual_mappings.py`
- [ ] T019 [P] Alembic migration: `import_jobs` table with partial unique on `file_sha256` where `is_override = false`, in `gard/db/migrations/versions/0006_import_jobs.py`
- [ ] T020 [P] Alembic migration: `audit_events` + `audit_chain_heads` tables, both with append-only grants, in `gard/db/migrations/versions/0007_audit.py`
- [ ] T021 [P] Alembic migration: `lifecycle_evidence` table with append-only grants, in `gard/db/migrations/versions/0008_lifecycle_evidence.py`
- [ ] T022 [P] Alembic migration: `api_tokens` table, in `gard/db/migrations/versions/0009_api_tokens.py`

### SQLAlchemy ORM models

- [ ] T023 [P] `gard/models/__init__.py` with declarative base + UUID v7 server-side default function
- [ ] T024 [P] `gard/models/device.py` matching data-model.md
- [ ] T025 [P] `gard/models/observation.py` (DeviceObservation) — read access via `gard_app`, writes via `gard_writer_append_only`
- [ ] T026 [P] `gard/models/normalization_rule.py`
- [ ] T027 [P] `gard/models/manual_mapping.py`
- [ ] T028 [P] `gard/models/import_job.py`
- [ ] T029 [P] `gard/models/audit_event.py` + `audit_chain_head.py` in same file
- [ ] T030 [P] `gard/models/lifecycle_evidence.py`
- [ ] T031 [P] `gard/models/api_token.py`
- [ ] T032 `gard/db/session.py`: two SQLAlchemy engines (`engine_app`, `engine_append_only`) wired to the two DB roles; FastAPI dependency providers for both

### Auth, RBAC, correlation, errors

- [ ] T033 [P] `gard/api/middleware/correlation_id.py`: ASGI middleware that reads `X-Correlation-Id` header or generates a UUID v7, sets the contextvar, echoes header in response
- [ ] T034 `gard/api/middleware/auth.py`: FastAPI dependency that validates OIDC bearer JWT (via `authlib`) or GARD-signed API-token JWT (via `python-jose`), returns a `Principal` (`subject`, `actor_type`, `roles`)
- [ ] T035 [P] `gard/core/rbac.py`: role→permission catalog as a Python dict (roles `viewer`, `lifecycle_manager`, `mcp_client`, `system_admin`; permissions per the security spec, F1 subset)
- [ ] T036 `gard/api/middleware/rbac.py`: `require(permission)` dependency factory that consults the catalog and the request's `Principal`; emits an `auth.denied` audit event on failure
- [ ] T037 [P] `gard/api/middleware/errors.py`: exception handler that renders the `Error` schema from `contracts/rest-openapi.yaml` with `correlation_id` populated from the contextvar

### Audit + Evidence + Envelope helpers

- [ ] T038 `gard/core/audit.py`: `emit(action, object_type, object_id, before, after, result, principal)` helper that writes to `audit_events` via the append-only role, computes `row_hash` (SHA-256 of canonical JSON of all fields except `row_hash`), and references the `correlation_id` contextvar
- [ ] T039 `gard/core/evidence.py`: `emit(evidence_type, subject_type, subject_id, before_state, after_state, source_checksum, references, principal)` helper writing to `lifecycle_evidence` with the same row-hash construction
- [ ] T040 `gard/worker.py`: scaffolds the worker process; first responsibility is the daily checksum-chain sealing job (computes the chained hash over the previous UTC day's `audit_events` ordered by `(timestamp, id)`, writes to `audit_chain_heads`)
- [ ] T041 [P] `gard/core/envelope.py`: `build_envelope(state, summary, facts, reasons, recommended_actions, confidence)` returning the explainable response envelope used by every classification response

### App skeletons

- [ ] T042 `gard/api/app.py`: FastAPI application factory wiring correlation-id middleware, error handler, auth dependency, and route registration; serves `/health`
- [ ] T043 [P] `gard/api/routers/health.py`: `GET /health` returning `{"status":"ok","version":<gard.__version__>}` (no auth required)
- [ ] T044 `gard/mcp/server.py`: MCP server using the official Python SDK with Streamable HTTP transport, mounted under `/mcp`, sharing the FastAPI auth dependency for bearer JWT validation; calls `audit.emit('mcp.tool.invoked', ...)` on every tool invocation
- [ ] T045 [P] `gard/api/routers/admin_tokens.py`: `POST /api/v1/admin/tokens` (issue) and `POST /api/v1/admin/tokens/{id}/revoke` (revoke), both gated by `manage_mcp_tools` permission
- [ ] T046 [P] `gard/api/routers/audit.py`: `GET /api/v1/audit` per the OpenAPI contract; gated by `read_audit` permission
- [ ] T047 [P] `gard/api/routers/evidence.py`: `GET /api/v1/evidence` per the OpenAPI contract; gated by `read_evidence` permission
- [ ] T048 `gard/__main__.py`: combined entrypoint (`uvicorn` for API + MCP in one process; `worker` subcommand starts `gard.worker`)

### Foundational contract & integration tests

- [ ] T049 [P] Contract test `tests/contract/test_audit_append_only.py`: a transaction using the `gard_app` role attempting `UPDATE audit_events` MUST raise an insufficient-privilege error
- [ ] T050 [P] Contract test `tests/contract/test_evidence_append_only.py`: same pattern for `lifecycle_evidence`
- [ ] T051 [P] Contract test `tests/contract/test_envelope_schema.py`: `build_envelope(...)` output validates against the inline `Envelope` JSON schema extracted from `contracts/rest-openapi.yaml`
- [ ] T052 [P] Contract test `tests/contract/test_correlation_id.py`: every response includes `X-Correlation-Id`; explicit incoming header is preserved
- [ ] T053 [P] Integration test `tests/integration/test_audit_chain.py`: emit 5 audit events, run the chain-sealing job, verify chain head equals the manually-computed expected SHA-256
- [ ] T054 [P] Integration test `tests/integration/test_auth_denied.py`: a request without a token returns 401; a token without the required permission returns 403 and creates an audit row with `result=denied`

**Checkpoint**: Foundation ready — user story implementation can now begin in parallel.

---

## Phase 3: User Story 1 — CSV Import → Canonical Devices (Priority: P1) 🎯 MVP

**Goal**: A lifecycle manager uploads a device-inventory CSV and immediately sees canonical, normalized `Device` records in `GET /api/v1/devices`, with a per-row outcome report for any rejections or manual-review rows.

**Independent Test**: Upload `gard-speckit-start/examples/devices.csv`. Assert: synchronous response carries an `ImportSummary` with `rows_total > 0` and `rows_total = rows_accepted + rows_rejected + rows_manual_review + rows_duplicate`. `GET /api/v1/devices?vendor_normalized=Cisco&model_normalized=ISR1121` returns the matching subset, each entry carries the explainable envelope, and `lifecycle_state = classified` for accepted rows.

### Tests for User Story 1

- [ ] T055 [P] [US1] Contract test `tests/contract/test_imports_post_sync.py`: `POST /imports/devices/csv` with a small CSV → 200 + `ImportSummary` shape; OpenAPI schema validation
- [ ] T056 [P] [US1] Contract test `tests/contract/test_imports_post_async.py`: `POST /imports/devices/csv` with a CSV exceeding `GARD_CSV_SYNC_THRESHOLD` → 202 + `ImportJobAck`
- [ ] T057 [P] [US1] Contract test `tests/contract/test_imports_duplicate.py`: re-upload same file → 409 with `code=DUPLICATE_FILE`; with `?override=true` → 200; both attempts produce audit rows
- [ ] T058 [P] [US1] Contract test `tests/contract/test_imports_jobs_get.py`: `GET /imports/jobs/{id}` returns `ImportJob` shape; 404 for unknown id
- [ ] T059 [P] [US1] Contract test `tests/contract/test_imports_report.py`: `GET /imports/jobs/{id}/report` returns `ImportReport` with `row_errors` list; rows reference original row numbers and raw rows
- [ ] T060 [P] [US1] Contract test `tests/contract/test_devices_list.py`: `GET /devices` filter combinations (`vendor_normalized`, `model_normalized`, `site`, `region`, `lifecycle_state`); pagination via `limit` + `page_token`; every item carries `envelope`
- [ ] T061 [P] [US1] Contract test `tests/contract/test_devices_get.py`: `GET /devices/{id}` returns `DeviceWithEnvelope`; 404 for unknown id
- [ ] T062 [P] [US1] Contract test `tests/contract/test_csv_schema.py`: validate the schema declared in `contracts/csv-schema.yaml` against representative valid and invalid rows; verify every error code is reachable
- [ ] T063 [P] [US1] Integration test `tests/integration/test_us1_clean_import.py` (acceptance scenario US1-AS1): 100-row valid CSV → all accepted; devices listable; `lifecycle_state=classified`
- [ ] T064 [P] [US1] Integration test `tests/integration/test_us1_mixed_import.py` (US1-AS2): 5 missing-column rows + 3 unknown-vendor rows → 5 rejected with reasons, 3 manual-review observations created, downloadable error report
- [ ] T065 [P] [US1] Integration test `tests/integration/test_us1_reimport_update.py` (US1-AS3): second CSV with updated firmware for same hostnames → new observations, no overwrites, devices' lifecycle reflects the latest observation
- [ ] T066 [P] [US1] Integration test `tests/integration/test_us1_duplicate_file.py` (edge case): identical-hash re-upload → 409; `?override=true` → 200, `is_override=true` recorded
- [ ] T067 [P] [US1] Integration test `tests/integration/test_us1_async_import.py`: > threshold CSV → 202, worker drains queue, `GET /imports/jobs/{id}` transitions `pending → processing → completed`
- [ ] T068 [P] [US1] Integration test `tests/integration/test_us1_evidence_emitted.py` (SC-007): every completed import produces exactly one `lifecycle_evidence` row with matching `source_checksum`
- [ ] T069 [P] [US1] Integration test `tests/integration/test_us1_audit_coverage.py` (SC-006): every state-mutating action in the import flow appears in `audit_events`, `correlation_id` matches the response header

### Implementation for User Story 1

- [ ] T070 [P] [US1] CSV row Pydantic models in `gard/api/schemas/csv_row.py` matching `contracts/csv-schema.yaml`
- [ ] T071 [P] [US1] Streaming CSV reader in `gard/core/csv_reader.py` with UTF-8 enforcement, header detection, per-row Pydantic validation, and an iterator yielding `(row_number, row_dict, errors)`
- [ ] T072 [P] [US1] Identity resolution in `gard/core/identity.py`: serial-first, `(hostname, site)` fallback, reject when both absent (per research.md D9)
- [ ] T073 [P] [US1] YAML catalog loader in `gard/catalog/normalization_loader.py`: walks `gard-catalog/normalization/`, validates each file against the JSON Schema in `contracts/normalization-rule.schema.yaml`, upserts file rules into the DB with `source=file`
- [ ] T074 [US1] Normalization rule engine in `gard/core/normalization_engine.py`: tier-aware resolution (manual mapping → DB override → file rule), specificity computation, conflict detection, returns `(rule_id, output, confidence)` or `None` (depends on T073)
- [ ] T075 [US1] Normalization controller in `gard/core/normalization_controller.py`: orchestrates engine for a single observation, materializes the explainable envelope (depends on T074, T041)
- [ ] T076 [US1] Device controller in `gard/core/device_controller.py`: upsert by identity, write `vendor_raw`/`model_raw` from latest observation, transition `imported→classified` when confidence is non-`manual_review_required`, list/get methods (depends on T072, T075)
- [ ] T077 [US1] Pydantic response schemas in `gard/api/schemas/devices.py` (`DeviceWithEnvelope`, `DeviceList`) and `gard/api/schemas/imports.py` (`ImportSummary`, `ImportJobAck`, `ImportJob`, `ImportReport`)
- [ ] T078 [US1] Import controller in `gard/core/import_controller.py`: orchestrates CSV reader → identity → normalization → device upsert → DeviceObservation insert → audit + evidence emission; computes `file_sha256`; produces `ImportSummary` (depends on T071, T076, T038, T039)
- [ ] T079 [US1] Worker import processor in `gard/worker.py`: `SELECT ... FOR UPDATE SKIP LOCKED` over `import_jobs WHERE status='pending'`, calls into `import_controller`; handles failure path (sets `status='failed'` + audit row) (depends on T078)
- [ ] T080 [US1] REST router `gard/api/routers/imports.py`: `POST /imports/devices/csv` (sync ≤ threshold, async > threshold), `GET /imports/jobs/{id}`, `GET /imports/jobs/{id}/report`; gated by `import_devices` permission for POST and `read_device_lifecycle` for GETs (depends on T078)
- [ ] T081 [US1] REST router `gard/api/routers/devices.py`: `GET /devices`, `GET /devices/{id}`; gated by `read_device_lifecycle` (depends on T076, T077)
- [ ] T082 [US1] CLI subcommand `gard catalog reload` in `gard/__main__.py` invoking the catalog loader (developer convenience, used by quickstart.md)

**Checkpoint**: User Story 1 fully functional; quickstart.md steps 1–6 pass; SC-001, SC-002, SC-003, SC-006, SC-007, SC-008 verifiable.

---

## Phase 4: User Story 2 — Normalization Review & Correction (Priority: P2)

**Goal**: A lifecycle manager lists `manual_review_required` observations, adds normalization rules (DB override or YAML) or manual mappings, and re-evaluates affected observations without re-uploading the source CSV.

**Independent Test**: Given a prior import with N manual-review observations, add an override rule via `POST /normalization/rules` that matches the unknown vendor, then call `POST /observations/re-evaluate` with `confidence=["manual_review_required"]`. Assert: response shows `changed=N`, `remaining_manual_review=0`; affected `Device` records moved to `lifecycle_state=classified`; an audit row with `action=observation.re_evaluated` exists.

### Tests for User Story 2

- [ ] T083 [P] [US2] Contract test `tests/contract/test_observations_list.py`: `GET /observations?confidence=manual_review_required` returns `ObservationList` shape
- [ ] T084 [P] [US2] Contract test `tests/contract/test_manual_mapping.py`: `POST /observations/{id}/manual-mapping` happy path → 201; second mapping without disabling first → 409; missing `reason` → 400
- [ ] T085 [P] [US2] Contract test `tests/contract/test_rules_post.py`: `POST /normalization/rules` validates `id` regex, accepts both regex and exact matchers; result has `source=db`
- [ ] T086 [P] [US2] Contract test `tests/contract/test_rules_patch.py`: `PATCH /normalization/rules/{id}` updates priority and match; refuses to mutate a `source=file` rule
- [ ] T087 [P] [US2] Contract test `tests/contract/test_rules_disable.py`: `DELETE /normalization/rules/{id}` sets `enabled=false` for db rules; refuses for file rules
- [ ] T088 [P] [US2] Contract test `tests/contract/test_rules_reload.py`: edits a YAML file under `gard-catalog/normalization/`, calls `POST /normalization/rules/reload`, response reports `loaded` count and `conflicts`
- [ ] T089 [P] [US2] Contract test `tests/contract/test_rules_conflicts.py`: induce a conflict (two equal-priority equal-specificity rules) → conflict surfaced in `/normalization/rules/conflicts`
- [ ] T090 [P] [US2] Contract test `tests/contract/test_re_evaluate.py`: `POST /observations/re-evaluate` accepts `confidence`, `device_id`, `import_job_id` filters; response carries summary + `correlation_id`
- [ ] T091 [P] [US2] Contract test `tests/contract/test_rule_schema.py`: validate the JSON Schema in `contracts/normalization-rule.schema.yaml` against valid + invalid rule documents
- [ ] T092 [P] [US2] Integration test `tests/integration/test_us2_list_review.py` (US2-AS1): observations with `manual_review_required` are listable with raw values and "why review" reason
- [ ] T093 [P] [US2] Integration test `tests/integration/test_us2_rule_reevaluate.py` (US2-AS2): adding a rule + re-evaluate clears manual-review backlog; `Device` records updated; audit row recorded
- [ ] T094 [P] [US2] Integration test `tests/integration/test_us2_manual_mapping.py` (US2-AS3): manual mapping creates audit + evidence, takes precedence over rules on subsequent re-evaluation
- [ ] T095 [P] [US2] Integration test `tests/integration/test_us2_rule_conflict.py`: conflicting equal-priority rules produce a deterministic outcome (later `created_at` wins for db; lexically-first path wins for file) and the conflict appears in `/normalization/rules/conflicts`

### Implementation for User Story 2

- [ ] T096 [US2] Manual-mapping precedence wired into the rule engine in `gard/core/normalization_engine.py` (extend T074): per-observation lookup of `ManualMapping` short-circuits the engine
- [ ] T097 [US2] Re-evaluation orchestration in `gard/core/normalization_controller.py` (extend T075): given a filter, iterate observations in batches, recompute classification, write `audit_events` per batch, return summary
- [ ] T098 [US2] CRUD service for normalization rules in `gard/core/rules_service.py`: list (file + db merged), create (db only), patch (db only), disable (db only); refuses operations on `source=file` rules with a clear error
- [ ] T099 [US2] Catalog reload + conflict report in `gard/catalog/normalization_loader.py` (extend T073): `reload()` returns `(loaded_count, conflicts)`; conflicts persisted to a transient cache surfaced via the conflicts endpoint
- [ ] T100 [US2] REST router `gard/api/routers/observations.py`: `GET /observations`, `POST /observations/{id}/manual-mapping`, `POST /observations/re-evaluate`; permissions `read_device_lifecycle` (GET) and `manage_prerequisites` (POSTs) — using existing F1 permission subset
- [ ] T101 [US2] REST router `gard/api/routers/normalization.py`: full CRUD + `/reload` + `/conflicts`; permission `manage_prerequisites` for writes, `read_catalog` for reads (depends on T098, T099)
- [ ] T102 [US2] Pydantic schemas in `gard/api/schemas/normalization.py` (`NormalizationRule`, `NormalizationRuleInput`) and `gard/api/schemas/observations.py` (`Observation`, `ObservationList`, `ManualMapping`)

**Checkpoint**: User Story 2 fully functional; quickstart.md step 7 passes; SC-004 verifiable.

---

## Phase 5: User Story 3 — AI Agent Queries via MCP (Priority: P2)

**Goal**: An approved MCP client (chatbot, IDE copilot) can call the v1 read-only tools `list_devices` and `get_device_lifecycle_status` over Streamable HTTP, receive bounded paginated responses, and observe that every call is recorded in the same audit pipeline as REST with a matching `correlation_id`.

**Independent Test**: With a populated `Device` table from US1, mint an `mcp_client` token, call MCP `list_devices` with `{vendor_normalized:"Cisco", model_normalized:"ISR1121", limit:5}`. Assert: response items conform to `DeviceCard` schema and each carries an envelope; `next_page_token` present when truncation occurs; `audit_events` row with `actor_type=mcp_client`, `action=mcp.tool.invoked`, `result=success`, matching `correlation_id`. A second call with a `viewer`-only token (no `mcp_client` permission) returns denied + audit row with `result=denied` and zero records leaked.

### Tests for User Story 3

- [ ] T103 [P] [US3] Contract test `tests/contract/test_mcp_discovery.py`: MCP `tools/list` returns exactly `list_devices` and `get_device_lifecycle_status` for an authorized client; tools' input schemas match `contracts/mcp-tools.yaml`
- [ ] T104 [P] [US3] Contract test `tests/contract/test_mcp_list_devices.py`: input schema rejects unknown properties; output bounded by `limit`; `next_page_token` round-trips; `correlation_id` present
- [ ] T105 [P] [US3] Contract test `tests/contract/test_mcp_get_lifecycle.py`: `device_ref` `oneOf` validates each branch (id / serial / hostname+site); 404 case returns a structured error not a raw exception
- [ ] T106 [P] [US3] Contract test `tests/contract/test_mcp_audit_parity.py`: every successful MCP tool call yields one audit row with `actor_type=mcp_client`; the row's `correlation_id` matches the value returned in the tool response
- [ ] T107 [P] [US3] Contract test `tests/contract/test_mcp_rbac.py`: a token without `read_device_lifecycle` calling either tool → MCP error response + `audit_events` row with `result=denied`
- [ ] T108 [P] [US3] Contract test `tests/contract/test_mcp_resources.py`: `resources/list` returns the three URIs declared in `contracts/mcp-tools.yaml`; `resources/read` returns valid JSON for `gard://schema/device` and `gard://schema/envelope`
- [ ] T109 [P] [US3] Integration test `tests/integration/test_us3_list_devices.py` (US3-AS1): 184 Cisco ISR1121 records → `list_devices` filtered call returns matching subset, paginates, audit row recorded
- [ ] T110 [P] [US3] Integration test `tests/integration/test_us3_rbac_denied.py` (US3-AS2): unauthorized client gets denied; record counts and schemas not leaked in error
- [ ] T111 [P] [US3] Integration test `tests/integration/test_us3_pagination_bounded.py` (US3-AS3): request that would exceed `limit=500` cap → response truncated with `next_page_token`; never an unbounded payload
- [ ] T112 [P] [US3] Integration test `tests/integration/test_us3_correlation_id_match.py` (SC-006 for MCP): correlation id returned in tool response matches a single audit row for that call

### Implementation for User Story 3

- [ ] T113 [US3] MCP `list_devices` tool in `gard/mcp/tools/list_devices.py`: input schema validation, calls `device_controller.list_devices(...)` from US1, projects to `DeviceCard`, attaches envelope, attaches `correlation_id`, emits `mcp.tool.invoked` audit (depends on T076, T044, T038)
- [ ] T114 [US3] MCP `get_device_lifecycle_status` tool in `gard/mcp/tools/get_device_lifecycle_status.py`: validates `device_ref` `oneOf`, calls `device_controller.get(...)` and `observation_controller.latest_for_device(...)`, returns combined `DeviceCard` + `ObservationCard` + envelope (depends on T076)
- [ ] T115 [US3] MCP resource provider in `gard/mcp/resources.py`: registers `gard://schema/device`, `gard://schema/envelope`, `gard://reports/manual-review-summary`; the report aggregates counts grouped by `vendor_raw`
- [ ] T116 [US3] MCP rate-limiter in `gard/mcp/middleware/rate_limit.py`: per-token-per-minute counter (in-process for v1; documented as "single-instance" in the file docstring), default 600; returns a structured rate-limit error
- [ ] T117 [US3] Tool registration + discovery wiring in `gard/mcp/server.py` (extend T044): registers the two tools and the resources; ensures `tools/list` returns only what the principal is permitted to call
- [ ] T118 [US3] CSP-realistic seed for the MCP integration tests in `tests/integration/conftest.py`: factory creating ≥ 200 devices spanning multiple vendors, ≥ 50 of which are `Cisco/ISR1121`

**Checkpoint**: User Story 3 fully functional; quickstart.md step 8 passes; SC-005 verifiable end-to-end.

---

## Phase 6: Polish & Cross-Cutting

**Purpose**: Cross-cutting tests, documentation, and final SC verification across all stories.

- [ ] T119 [P] Unit tests `tests/unit/test_normalization_engine.py`: specificity computation, tie-breakers, conflict detection, manual-mapping precedence
- [ ] T120 [P] Unit tests `tests/unit/test_identity.py`: serial trimming/case, fallback to (hostname, site), reject-when-both-absent
- [ ] T121 [P] Unit tests `tests/unit/test_audit_chain.py`: hash-chain construction is stable across event ordering; sealing job is idempotent
- [ ] T122 [P] Unit tests `tests/unit/test_envelope.py`: envelope schema invariants, default-empty fields, confidence enum coverage
- [ ] T123 [P] CI gate test `tests/contract/test_openapi_drift.py`: the FastAPI-generated OpenAPI document is a superset of `contracts/rest-openapi.yaml` (all paths and operations present, all required fields covered)
- [ ] T124 [P] CI gate test `tests/contract/test_mcp_tools_drift.py`: MCP `tools/list` matches the `tools` section of `contracts/mcp-tools.yaml`
- [ ] T125 [P] CI gate test `tests/contract/test_csv_schema_drift.py`: server-side CSV schema validator matches `contracts/csv-schema.yaml`
- [ ] T126 Run the full quickstart end-to-end (steps 1–10) against a freshly-built Docker Compose stack; verify SC-005, SC-007, SC-008
- [ ] T127 [P] Update root `README.md` "Status" section: mark F1 implementation complete and link to `specs/001-device-import-normalize/quickstart.md`
- [ ] T128 [P] Update `ROADMAP.md` status table for F1: spec ✅ plan ✅ tasks ✅ implementation ✅; record any deviations from the plan in the row's notes
- [ ] T129 [P] Capture any new ADRs that emerged during implementation (e.g. UUID v7 generator choice, `resolve_template` policy) in `adr/` with `Status: Accepted` and a back-reference to the originating decision
- [ ] T130 [P] Performance probe `tests/integration/test_perf_sc_001_005.py` (gated by `pytest -m perf`): SC-001 (10k-row import ≤ 30 s) and SC-005 (MCP `list_devices` < 2 s @ 50k devices)
- [ ] T131 [P] Contract test `tests/contract/test_tls_required.py` (FR-024): app refuses to start in production mode without TLS configuration; in dev mode binds plain HTTP only on `localhost`. Implementation lives in `gard/settings.py` startup validation and `deploy/Dockerfile` / `deploy/docker-compose.yml` reverse-proxy section
- [ ] T132 [P] Contract test `tests/contract/test_token_ttl.py` (FR-025): issuance endpoint defaults `expires_at = issued_at + 90 days`; refuses null/indefinite TTL; `manage_mcp_tools` permission required for override; revocation propagates within 60 s across REST + MCP. Implementation in `gard/api/routers/admin_tokens.py` (T045) and `gard/api/middleware/auth.py` (T034)

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1 (Setup)**: no dependencies — start immediately.
- **Phase 2 (Foundational)**: depends on Phase 1; **blocks all user stories**. Within Phase 2: migrations (T014–T022) → models (T023–T032) → app skeletons + middleware (T033–T048) → foundational tests (T049–T054).
- **Phase 3 (US1)**: depends on Phase 2 complete.
- **Phase 4 (US2)**: depends on Phase 2 complete; integrates with US1 controllers but exercises an independent test path.
- **Phase 5 (US3)**: depends on Phase 2 + US1 (needs the device controller); independent test path.
- **Phase 6 (Polish)**: depends on US1 + US2 + US3 done (T126 quickstart needs all three).

### Within each user story

- Tests for a story (`tests/contract/`, `tests/integration/`) MUST be written and FAIL before implementation tasks begin (TDD-style for the contract surface; constitution mandates contract + integration tests on every controller boundary).
- Models / loaders before controllers; controllers before routers; routers before integration tests pass.
- US3's MCP tools depend on US1's `device_controller` (single source of domain logic per Constitution VI).

### Parallel opportunities

- Setup tasks T002–T013 can all run in parallel after T001.
- Foundational migrations T015–T022 can run in parallel after T014.
- Foundational ORM models T023–T031 can run in parallel after T014.
- All contract tests for a story can run in parallel (different files).
- All integration tests for a story can run in parallel (different files).
- US1, US2, US3 implementation can be staffed in parallel after Phase 2 (US3 should start after T076 is in code review even if not merged).
- All Polish tasks T119–T130 can run in parallel.

---

## Parallel Examples

### Phase 2 — Foundational migrations & models (after T014)

```text
Task: T015 Alembic migration: devices
Task: T016 Alembic migration: device_observations (append-only grants)
Task: T017 Alembic migration: normalization_rules
Task: T018 Alembic migration: manual_mappings
Task: T019 Alembic migration: import_jobs
Task: T020 Alembic migration: audit_events + audit_chain_heads
Task: T021 Alembic migration: lifecycle_evidence
Task: T022 Alembic migration: api_tokens
```

### Phase 3 — User Story 1 contract tests

```text
Task: T055 Contract test POST /imports/devices/csv (sync)
Task: T056 Contract test POST /imports/devices/csv (async 202)
Task: T057 Contract test duplicate refusal + override
Task: T060 Contract test GET /devices list
Task: T061 Contract test GET /devices/{id}
Task: T062 Contract test CSV schema
```

### Phase 5 — User Story 3 implementation (after T076 in US1)

```text
Task: T113 MCP list_devices tool
Task: T114 MCP get_device_lifecycle_status tool
Task: T115 MCP resource provider
Task: T116 MCP rate limiter
```

---

## Implementation Strategy

### MVP first (User Story 1 only)

1. Complete Phase 1 (Setup) — all 13 tasks.
2. Complete Phase 2 (Foundational) — all 41 tasks; foundational tests T049–T054 must be green.
3. Complete Phase 3 (US1) — write failing tests T055–T069 first, then implement T070–T082.
4. **STOP and VALIDATE**: run `quickstart.md` steps 1–6; confirm SC-001, SC-002, SC-003, SC-006, SC-007, SC-008 pass.
5. Open the MVP-checkpoint PR for review (everything up to T082 + the constitutional invariants demonstrably enforced).

### Incremental delivery

1. MVP (US1) → demo: operator imports CSV, devices visible.
2. Add US2 → demo: operator clears manual-review backlog without re-uploading.
3. Add US3 → demo: AI agent answers `count_devices_outside_target` precursor (`list_devices` filtered) under full audit.
4. Polish → final SC verification + drift gates.

### Parallel team strategy

After Phase 2:

- Developer A: US1 (T055–T082)
- Developer B: starts US2 contract tests (T083–T091) in parallel; waits on US1's `normalization_engine` (T074) before US2 implementation
- Developer C: starts US3 contract tests (T103–T108) in parallel; waits on US1's `device_controller` (T076) before US3 implementation

---

## Notes

- `[P]` = different files, no dependencies — safe to parallelize.
- Every user-story task carries its `[USn]` label for traceability back to `spec.md`.
- Tests precede implementation within each story (TDD on the contract surface).
- Commit after each task or logical group.
- Stop at any **Checkpoint** to validate the story independently.
- **Constitutional invariants the polish phase must reverify** before this feature merges to `main`:
  1. Audit and evidence tables remain append-only at the DB role level (T049, T050).
  2. Every classification response carries the explainable envelope (T051, T123).
  3. MCP exposes only the two declared tools, sharing the REST auth + audit pipeline (T103, T106, T124).
