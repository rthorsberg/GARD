# F8 — Native MCP Transport: Implementation Tasks

**Generated**: 2026-05-31 by `/speckit-tasks`
**Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md)
**Research**: [research.md](./research.md) | **Contracts**: [contracts/](./contracts/)

**Conventions**:
- `[P]` — parallelisable (different files, no dependency on an unfinished task)
- `[US1]` … `[US5]` — task belongs to a user-story phase
- `T001..` — sequential IDs in execution order
- Test tasks included (spec FR-011, SC-001–SC-007 require integration + contract coverage)

**PR slices**: **8a** (T001–T012), **8b** (T013–T025), **8c** (T009–T011, T023, T031, T036), **8d** (T026–T042)

Status: `[ ]` pending · `[x]` done

---

## Phase 1 — Setup (slice 8a)

**Purpose**: Design artefacts and binding ADR before transport code.

- [x] **T001** Spec `specs/008-mcp-transport/spec.md`
- [x] **T002** Plan `specs/008-mcp-transport/plan.md` + research R-1..R-10
- [x] **T003** Merged registry manifest `specs/008-mcp-transport/contracts/mcp-tools.yaml` (22 tools + 6 disallowed)
- [x] **T004** Requirements checklist `specs/008-mcp-transport/checklists/requirements.md`
- [x] **T005** [P] Author `adr/ADR-0019-mcp-transport-binding.md` — mount at `/mcp`, shared JWT auth, explicit registry, deny-list; note ADR-0013 transport deferral closed
- [x] **T006** Verify manifest: 22 `tools` entries + 6 `disallowed` names match F1–F7 source contracts

---

## Phase 2 — Foundational (blocking prerequisites)

**Purpose**: Settings, registry scaffold, handler, server, and FastAPI mount. **Blocks all user stories.**

**Checkpoint**: Registry module importable; MCP mount returns 404 when disabled; handler unit-testable in isolation.

- [x] **T007** [P] Add `mcp_enabled: bool = True` and `mcp_path: str = "/mcp"` to `gard/core/settings.py` with env vars `GARD_MCP_ENABLED` / `GARD_MCP_PATH`
- [x] **T008** [P] Create `gard/mcp/registry.py` — `ToolEntry` type + `TOOL_REGISTRY: dict[str, ToolEntry]` with explicit imports for all 22 delegate modules (stub `NotImplementedError` invoke OK until 8b)
- [x] **T009** Create `gard/mcp/handler.py` — `invoke_tool(name, raw_input, *, token, correlation_id)`: JWT via `gard.api.deps.auth`, `INVOKE_MCP_TOOL` + per-tool `REQUIRED_PERMISSION`, Pydantic input validation, `session_scope()` / `append_only_scope()` for audit, emit `mcp.tool.invoked` on success/deny
- [x] **T010** Implement `gard/mcp/server.py` — MCP SDK Streamable HTTP app factory; register tools from `TOOL_REGISTRY`; delegate calls to `handler.invoke_tool`
- [x] **T011** Mount MCP sub-app at `settings.mcp_path` in `gard/api/app.py` when `settings.mcp_enabled`; return 404/disabled response when off
- [x] **T012** [P] `tests/contract/test_mcp_registry.py` — parse `specs/008-mcp-transport/contracts/mcp-tools.yaml`; assert every listed tool exists in `TOOL_REGISTRY` with matching `TOOL_NAME` and `REQUIRED_PERMISSION`

---

## Phase 3 — US3 (P1): Complete tool registry from F1–F7 contracts

**Story goal**: All 22 published tools have working delegates; `tools/list` exposes full surface; F1/F2 gaps closed.

**Independent test criterion**: Contract tests pass for F1+F2 tools; `get_target_firmware` output matches REST firmware-compliance; `list_devices` paginates with `next_page_token`.

### US3 — Tests first

- [x] **T013** [P] [US3] `tests/contract/test_device_mcp_tools.py` — metadata + permissions for `list_devices`, `get_device_lifecycle_status` vs `specs/001-device-import-normalize/contracts/mcp-tools.yaml`
- [x] **T014** [P] [US3] `tests/contract/test_firmware_mcp_tools.py` — metadata + permissions for five F2 tools vs `specs/002-firmware-catalog/contracts/mcp-tools.yaml`
- [x] **T015** [P] [US3] Extend `tests/contract/test_mcp_registry.py` — assert F3–F7 existing delegate modules still register; total registered count = 22

### US3 — F1 delegates

- [x] **T016** [P] [US3] `gard/mcp/tools/list_devices.py` — REST parity with `device_controller.list_devices()`; `DeviceCard` projection; pagination via `page_token`/`next_page_token`; auth `READ_DEVICE_LIFECYCLE`
- [x] **T017** [P] [US3] `gard/mcp/tools/get_device_lifecycle_status.py` — resolve device by id/serial/hostname+site; attach envelope; unknown device → explainable envelope not 500; auth `READ_DEVICE_LIFECYCLE`

### US3 — F2 delegates

- [x] **T018** [P] [US3] `gard/mcp/tools/get_target_firmware.py` — delegate to F2 `compliance_controller.evaluate()`; output matches `GET /api/v1/devices/{id}/firmware-compliance`; auth `READ_FIRMWARE_CATALOG`
- [x] **T019** [P] [US3] `gard/mcp/tools/get_upgrade_path.py` — delegate to `upgrade_path_graph.find_chain()`; cycle-safe; auth `READ_FIRMWARE_CATALOG`
- [x] **T020** [P] [US3] `gard/mcp/tools/list_firmware_targets.py` — bounded list from DB; auth `READ_FIRMWARE_CATALOG`
- [x] **T021** [P] [US3] `gard/mcp/tools/list_firmware_packages.py` — bounded list from DB; auth `READ_FIRMWARE_CATALOG`
- [x] **T022** [P] [US3] `gard/mcp/tools/list_upgrade_paths.py` — bounded list from DB; auth `READ_FIRMWARE_CATALOG`

### US3 — Wire + parity

- [x] **T023** [US3] Finalize `gard/mcp/registry.py` and `gard/mcp/server.py` tool registration for all 22 delegates (depends T016–T022)
- [x] **T024** [P] [US3] `tests/integration/test_us3_mcp_device_pagination.py` — `list_devices` with `limit=5` returns `next_page_token`; follow-up page non-empty
- [x] **T025** [P] [US3] `tests/integration/test_us3_mcp_firmware_parity.py` — `get_target_firmware` byte-parity with REST for seeded ISR1121 device

**Checkpoint**: All 22 tools callable via in-process handler (pre-transport) or delegate tests green.

---

## Phase 4 — US1 (P1): Live MCP answers ISR1121 compliance questions 🎯 MVP

**Story goal**: MVP criterion #8 — live MCP `count_devices_outside_target` for Cisco ISR1121 matches REST; auth deny path; `tools/list` shows 22 tools.

**Independent test criterion**: `tests/integration/test_mcp_transport_isr1121.py` passes against ISR1121 fixture with audit `correlation_id` match.

### US1 — Tests

- [x] **T026** [P] [US1] `tests/integration/test_mcp_transport_isr1121.py` — MCP client against test app: `count_devices_outside_target` `{vendor_normalized:"Cisco", model_normalized:"ISR1121"}` count matches `GET /api/v1/compliance/summary`; audit row `mcp.tool.invoked` with matching `correlation_id`
- [x] **T027** [P] [US1] `tests/integration/test_mcp_tools_list.py` — live `tools/list` returns exactly 22 tools with input JSON Schemas
- [x] **T028** [P] [US1] `tests/integration/test_mcp_auth_denied.py` — `viewer`-only token denied on tool invoke; zero data; audit `result=denied`

**Checkpoint**: MVP criterion #8 proven on live transport.

---

## Phase 5 — US2 (P1): Single auth and audit pipeline with REST

**Story goal**: MCP and REST share JWT resolution, RBAC, correlation-id, and audit fields.

**Independent test criterion**: Same token → `get_readiness_summary` MCP vs REST payloads match (modulo wrapper); malformed input → validation error, no DB writes.

### US2 — Tests + hardening

- [x] **T029** [P] [US2] `tests/integration/test_mcp_auth_audit_parity.py` — `get_readiness_summary` MCP vs REST with identical filters and token; audit action/permission fields match REST read path
- [x] **T030** [P] [US2] `tests/integration/test_mcp_input_validation.py` — invalid tool input → structured validation error; assert no new audit/evaluation rows
- [x] **T031** [US2] Harden `gard/mcp/handler.py` — expired/malformed JWT → 401 before dispatch; missing tool permission → 403 with deny audit even when `INVOKE_MCP_TOOL` present

**Checkpoint**: Security review path — one traced MCP call matches REST audit semantics.

---

## Phase 6 — US4 (P2): Disallowed tools and bounded outputs

**Story goal**: Unknown/disallowed tool names rejected; list tools respect pagination bounds.

**Independent test criterion**: `execute_sql` → `tool_not_found` + `mcp.disallowed_tool_attempt`; list tool at `limit=500` truncates with token.

### US4 — Tests + implementation

- [x] **T032** [P] [US4] `tests/integration/test_mcp_disallowed_tools.py` — invoke `execute_sql` (and one other disallowed name) → `tool_not_found`; audit `mcp.disallowed_tool_attempt` with client identity
- [x] **T033** [US4] Implement deny-list branch in `gard/mcp/handler.py` using `specs/008-mcp-transport/contracts/mcp-tools.yaml` `disallowed` set + unknown names
- [x] **T034** [P] [US4] `tests/integration/test_mcp_pagination_bounds.py` — list tool at max `limit=500` returns pagination token when more rows exist; response within contract byte bounds

**Checkpoint**: Constitution VI deny-list enforced on live transport.

---

## Phase 7 — US5 (P2): Operator runbook — `gard mcp` and Docker

**Story goal**: Operator connects MCP client within 5 minutes of `make seed`; disabled MCP returns clear response.

**Independent test criterion**: `quickstart.md` steps reproducible; `GARD_MCP_ENABLED=false` smoke test passes.

- [x] **T035** [US5] Write `specs/008-mcp-transport/quickstart.md` — token mint (`gard issue-token --role mcp_client`), endpoint URL, initialize + tool-call smoke against ISR1121 fixture
- [x] **T036** [US5] Implement `run_mcp()` in `gard/mcp/server.py` for `gard mcp` CLI — standalone uvicorn on configurable port sharing same app factory
- [x] **T037** [P] [US5] `tests/integration/test_mcp_disabled.py` — `GARD_MCP_ENABLED=false` → endpoint not serving tools (404 or documented disabled body)
- [x] **T038** [P] [US5] Update `README.md` MCP section + `deploy/README.md` pointer to F8 quickstart

**Checkpoint**: Demo-ready operator path without reading test code.

---

## Phase 8 — Polish & cross-cutting

- [x] **T039** [P] Update `tests/integration/test_mvp_vertical_slice_isr1121.py` — note transport no longer deferred; optional live MCP assertion for criterion #8
- [x] **T040** [P] Update `ROADMAP.md` — mark F8 shipped when complete; note ADR-0019
- [x] **T041** Full `pytest` + `ruff check` + `ruff format --check` + `mypy` green
- [x] **T042** PR ready — slices 8a→8d reviewed; CI green

---

## Dependencies & Execution Order

### Phase Dependencies

```text
Phase 1 (Setup)
    ↓
Phase 2 (Foundational) ── BLOCKS all user stories
    ↓
Phase 3 (US3) ── F1/F2 delegates + registry complete
    ↓
Phase 4 (US1) ── requires Phase 2 server + Phase 3 compliance tool registered
    ↓
Phase 5 (US2) ── can start after Phase 2; full parity after US3
    ↓
Phase 6 (US4) ── requires Phase 2 handler
    ↓
Phase 7 (US5) ── requires Phase 2 + US1 smoke path
    ↓
Phase 8 (Polish)
```

### User Story Dependencies

| Story | Priority | Depends on | Independent test |
|---|---|---|---|
| US3 | P1 | Phase 2 | Contract + delegate parity tests (T013–T025) |
| US1 | P1 | Phase 2, US3 (compliance tool) | `test_mcp_transport_isr1121.py` (T026) |
| US2 | P1 | Phase 2 | `test_mcp_auth_audit_parity.py` (T029) |
| US4 | P2 | Phase 2 | `test_mcp_disallowed_tools.py` (T032) |
| US5 | P2 | Phase 2, US1 | `quickstart.md` + `test_mcp_disabled.py` (T035, T037) |

### Parallel Opportunities

**Phase 2** (after T007):
```bash
# Parallel: settings + registry scaffold + contract test file
T007  gard/core/settings.py
T008  gard/mcp/registry.py
T012  tests/contract/test_mcp_registry.py
```

**Phase 3 — all seven delegate modules** (after T008):
```bash
T016  gard/mcp/tools/list_devices.py
T017  gard/mcp/tools/get_device_lifecycle_status.py
T018  gard/mcp/tools/get_target_firmware.py
T019  gard/mcp/tools/get_upgrade_path.py
T020  gard/mcp/tools/list_firmware_targets.py
T021  gard/mcp/tools/list_firmware_packages.py
T022  gard/mcp/tools/list_upgrade_paths.py
```

**Phase 4 — US1 integration tests** (after T023):
```bash
T026  tests/integration/test_mcp_transport_isr1121.py
T027  tests/integration/test_mcp_tools_list.py
T028  tests/integration/test_mcp_auth_denied.py
```

---

## Implementation Strategy

### MVP First (US1 path)

1. Complete Phase 1 + Phase 2 (transport scaffold)
2. Complete Phase 3 through T023 (all 22 tools registered; minimum: F3 `count_devices_outside_target` working)
3. Complete Phase 4 (US1) — **STOP and validate MVP criterion #8**
4. Continue US2 → US4 → US5 → Polish

### Incremental PR slices

| Slice | Tasks | Delivers |
|---|---|---|
| **8a** | T001–T012 | ADR-0019, registry/handler/server scaffold, disabled mount |
| **8b** | T013–T025 | F1+F2 delegates, contract tests, registry complete |
| **8c** | T009–T011, T023, T031, T036 | Live transport, auth hardening, `gard mcp` CLI |
| **8d** | T026–T042 | Integration tests, quickstart, docs, CI green |

### Suggested MVP scope

**Minimum shippable increment**: Phase 1 + Phase 2 + Phase 3 (T016–T023 for compliance tool at minimum) + Phase 4 (T026–T028) — proves criterion #8 with auth deny and full `tools/list`.

---

## Notes

- No new DB migrations, lifecycle states, or REST endpoints (SC-008).
- F3–F7 delegate modules must not change semantics — registration + transport only.
- Draft tools (`create_uplift_wave_draft`, etc.) remain non-mutating at MCP layer (FR-013).
- MCP resources (`gard://schema/...`) are out of scope unless added as optional stretch in Polish.
