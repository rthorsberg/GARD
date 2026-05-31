# F7 — Tasks

48 tasks across 9 phases. PR slices: **7a** (T001–T012), **7b** (T013–T030), **7c** (T031–T040), **7d** (T041–T048).

Status: `[ ]` pending · `[x]` done

## Phase 1 — Design + isolated NetBox (slice 7a)

- [x] **T001** Spec `specs/007-netbox-integration-read/spec.md`
- [x] **T002** Plan + research R-1..R-6
- [x] **T003** `deploy/netbox/docker-compose.yml` — project `gard-f7-netbox`, ports 18888/55432
- [x] **T004** `deploy/netbox/README.md` + `.env.example` — docker safety rules
- [x] **T005** `specs/007-netbox-integration-read/quickstart.md`
- [x] **T006** Author `adr/ADR-0017-netbox-integration-boundary.md`
- [x] **T007** Author `adr/ADR-0018-netbox-diode-assurance-ecosystem.md`
- [x] **T008** `contracts/rest-openapi.yaml` — sync + summary paths
- [x] **T009** Validate compose: `docker compose -p gard-f7-netbox -f deploy/netbox/docker-compose.yml config`
- [ ] **T010** Commit + push slice 7a

## Phase 2 — Foundation (slice 7b)

- [x] **T011** Migration `0010_netbox_integration.py` — device columns + `netbox_sync_runs`
- [x] **T012** Extend `gard/models/device.py`, `gard/core/settings.py`
- [x] **T013** `gard/integrations/netbox/client.py` — read-only httpx client + pagination
- [x] **T014** `gard/core/netbox_sync_controller.py` — reconcile logic
- [x] **T015** RBAC permissions `SYNC_NETBOX`, `READ_NETBOX`
- [x] **T016** `gard/api/schemas/netbox_integration.py`
- [x] **T017** `gard/api/routers/netbox_integration.py` — POST sync, GET summary
- [x] **T018** Wire router in `gard/api/app.py`

## Phase 3 — US1 tests (slice 7b)

- [x] **T019** [US1] Integration test: match by serial
- [x] **T020** [US1] Integration test: create from NetBox-only device
- [x] **T021** [US1] Integration test: orphan report, no delete
- [x] **T022** [US1] Integration test: NetBox unreachable → rollback
- [x] **T023** [US1] Audit + evidence on sync

## Phase 4 — US2 tagged_with (slice 7c)

- [x] **T024** [US2] Implement `eval_tagged_with` against `Device.tags`
- [x] **T025** [US2] Integration test: tag sync + readiness eval
- [x] **T026** [US2] Remove `predicate_deferred` for synced tagged devices

## Phase 5 — US4 MCP (slice 7d)

- [x] **T027** [US4] MCP delegate `get_netbox_sync_summary`
- [x] **T028** [US4] Contract test MCP + OpenAPI
- [x] **T029** `deploy/scripts/seed-netbox.sh` — optional fixture loader for dev NetBox
- [x] **T030** Update `README.md`, `ROADMAP.md`, `deploy/README.md`
- [x] **T031** Full pytest + CI green
- [ ] **T032** PR ready

## Docker safety (non-negotiable)

- Never `docker compose down` without `-p gard-f7-netbox`
- Never publish ports 5432, 8080, 18080 on this stack
- Never `docker rm` / `prune` foreign containers
