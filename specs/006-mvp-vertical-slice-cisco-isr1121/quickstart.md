# F6 — MVP Vertical Slice Quickstart (Cisco ISR1121)

Operator runbook for proving the F1–F5 stack against Cisco ISR1121. Assumes Docker Compose on port 8080.

## Prerequisites

```bash
docker compose -f deploy/docker-compose.yml up -d --build
# wait for healthy:
curl -sf http://127.0.0.1:8080/healthz
```

## Automated path (CI parity)

```bash
GARD_DATABASE_URL=postgresql+psycopg://gard:gard@localhost:5432/gard \
GARD_JWT_SECRET=test-secret \
GARD_REQUIRE_TLS=false \
  uv run pytest tests/integration/test_mvp_vertical_slice_isr1121.py -q
```

Expected: all tests pass; runtime under ~60s.

## Manual path (Docker seed script)

After F6 implementation lands, run:

```bash
./deploy/scripts/seed-isr1121.sh
```

### Checkpoint 1 — Import

Expected output includes:

- `rows_accepted >= 1` for ISR1121 rows
- `rows_rejected >= 1` for malformed rows
- `devices_created` matches accepted count

Verify:

```bash
TOKEN=$(cat .gard/token.jwt)
curl -sS -H "Authorization: Bearer $TOKEN" \
  'http://127.0.0.1:8080/api/v1/devices?vendor_normalized=Cisco&model_normalized=ISR1121' | jq '.total_returned'
```

Expected: `>= 1`

### Checkpoint 2 — Compliance + readiness

Seed script prints F3/F4 summaries. Expect:

- `outside_target_count >= 1` for ISR1121 estate
- `ready_for_uplift_count >= 1` before wave drafting

Manual verify:

```bash
curl -sS -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8080/api/v1/compliance/summary | jq
curl -sS -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8080/api/v1/readiness/summary | jq
```

### Checkpoint 3 — Dry-run uplift

Seed script creates a plan and drafts a wave. Expect:

- `wave_id` present
- `state=draft`
- `device_count >= 1`

### Checkpoint 4 — Approval (SoD)

Seed script mints separate drafter + `change_approver` tokens, submits, and approves.

Expected final wave state: `approved`

Verify:

```bash
curl -sS -H "Authorization: Bearer $TOKEN" \
  'http://127.0.0.1:8080/api/v1/uplift/waves?limit=5' | jq '.items[] | {name, state, device_count}'
```

### Checkpoint 5 — Audit trail

Query audit events for the golden hostname (replace as needed):

```bash
curl -sS -H "Authorization: Bearer $TOKEN" \
  'http://127.0.0.1:8080/api/v1/audit/events?limit=50' | jq '.items[] | select(.action | test("import|compliance|readiness|uplift")) | .action'
```

Expected: import, evaluation, and uplift lifecycle actions present.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| All ISR1121 devices `unknown` | ISR1121 catalog not loaded | `docker compose exec api python -m gard catalog reload --only firmware` |
| Zero `ready_for_uplift` | Prereq observation fields missing | Check fixture CSV + `isr1121-minimum-flash.yaml` |
| `SELF_APPROVAL_FORBIDDEN` | Same token for draft + approve | Mint separate `change_approver` token (`gard issue-token --role change_approver`) |
| Wave 422 `UnknownSelectorKey` | Wrong scope key | Use `site_in` not `site` |

## MCP delegate smoke (no live transport)

```bash
uv run pytest tests/integration/test_mvp_vertical_slice_isr1121.py -k mcp -q
```

Validates MVP criterion #8 at delegate level per ADR-0013.
