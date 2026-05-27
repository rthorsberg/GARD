# F1 Quickstart — Device Import & Normalize

This quickstart proves the F1 vertical end-to-end against the
acceptance scenarios in `spec.md`. It is the path a CSP operator
follows after deploying GARD for the first time.

## Prerequisites

- Docker + Docker Compose v2
- An OIDC provider you can hit from the host (Keycloak / Entra / Okta)
  with at least one user assigned the `lifecycle_manager` role
- The seed CSV: `gard-speckit-start/examples/devices.csv` (or your own)

## 1. Bring up GARD

```bash
cd deploy
cp .env.example .env
# edit .env: set GARD_OIDC_DISCOVERY_URL, GARD_OIDC_AUDIENCE,
# GARD_DB_PASSWORD, GARD_ADMIN_BOOTSTRAP_TOKEN
docker compose up -d
```

This launches three containers:

- `gard-api` — FastAPI + MCP server on port 8080
- `gard-worker` — async import worker
- `gard-postgres` — PostgreSQL 16 with the `gard_app` and
  `gard_writer_append_only` roles pre-provisioned

Wait for `docker compose logs gard-api | grep "ready"`.

## 2. Confirm health & auth

```bash
curl -fsS http://localhost:8080/health   # → {"status":"ok","version":"..."}
```

Obtain a user token via your OIDC provider's device-code or
authorization-code flow, then:

```bash
export TOKEN=$(./scripts/dev-oidc-login.sh)   # demo helper
curl -fsS -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/v1/devices
# → {"items": [], "next_page_token": null}
```

The empty list is correct — nothing imported yet.

## 3. Load the seed normalization catalog

```bash
docker compose exec gard-api gard catalog reload
# → {"loaded": 7, "conflicts": []}
```

Or hit the API:

```bash
curl -fsS -X POST -H "Authorization: Bearer $TOKEN" \
  http://localhost:8080/api/v1/normalization/rules/reload
```

## 4. Import a CSV (acceptance scenario US1-1)

```bash
curl -fsS -X POST -H "Authorization: Bearer $TOKEN" \
  -F "file=@../gard-speckit-start/examples/devices.csv" \
  http://localhost:8080/api/v1/imports/devices/csv | jq
```

Expected (shape):

```json
{
  "job_id": "0190fcef-...",
  "status": "completed",
  "totals": {
    "rows_total": 100,
    "rows_accepted": 100,
    "rows_rejected": 0,
    "rows_manual_review": 0,
    "rows_duplicate": 0,
    "devices_created": 100,
    "devices_updated": 0
  },
  "correlation_id": "01J...",
  "warnings": []
}
```

Verify devices are listable:

```bash
curl -fsS -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/api/v1/devices?vendor_normalized=Cisco&model_normalized=ISR1121" \
  | jq '.items | length'
# → some positive integer for the seed file
```

## 5. Re-import the same file (acceptance scenario edge-case)

```bash
curl -i -X POST -H "Authorization: Bearer $TOKEN" \
  -F "file=@../gard-speckit-start/examples/devices.csv" \
  http://localhost:8080/api/v1/imports/devices/csv
# → HTTP/1.1 409 Conflict; body has code DUPLICATE_FILE
```

Use the audited override:

```bash
curl -fsS -X POST -H "Authorization: Bearer $TOKEN" \
  -F "file=@../gard-speckit-start/examples/devices.csv" \
  "http://localhost:8080/api/v1/imports/devices/csv?override=true" | jq
# → completed; new observations created, devices_updated > 0
```

## 6. Import a CSV with a mix of bad and unknown rows (US1-2)

Create `/tmp/messy.csv` with five rows missing `hostname` and three
rows whose vendor has no rule (`vendor_raw: NovaTel-Custom`).

```bash
curl -fsS -X POST -H "Authorization: Bearer $TOKEN" \
  -F "file=@/tmp/messy.csv" \
  http://localhost:8080/api/v1/imports/devices/csv | jq
# rows_rejected: 5, rows_manual_review: 3
```

Download the per-row report:

```bash
JOB=$(curl -fsS -H "Authorization: Bearer $TOKEN" \
  http://localhost:8080/api/v1/imports/jobs?limit=1 | jq -r '.items[0].id')
curl -fsS -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/api/v1/imports/jobs/$JOB/report" | jq
```

## 7. Fix the manual-review backlog (US2)

List manual-review observations:

```bash
curl -fsS -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/api/v1/observations?confidence=manual_review_required" | jq
```

Add an override rule via API:

```bash
curl -fsS -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "novatel-fallback",
    "priority": 50,
    "match": { "vendor_raw_regex": "^(?i)novatel.*" },
    "output": { "vendor_normalized": "NovaTel" },
    "confidence": "medium"
  }' \
  http://localhost:8080/api/v1/normalization/rules
```

Re-evaluate:

```bash
curl -fsS -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"confidence":["manual_review_required"]}' \
  http://localhost:8080/api/v1/observations/re-evaluate | jq
# changed: 3, remaining_manual_review: 0
```

## 8. Query via MCP (US3)

Mint a service token:

```bash
TOKEN_MCP=$(curl -fsS -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"copilot","roles":["mcp_client","viewer"]}' \
  http://localhost:8080/api/v1/admin/tokens | jq -r .token)
```

Call `list_devices` over MCP Streamable HTTP:

```bash
gard-mcp-client --endpoint http://localhost:8080/mcp \
  --token "$TOKEN_MCP" \
  call list_devices '{"vendor_normalized":"Cisco","model_normalized":"ISR1121","limit":5}'
```

(or any MCP client that speaks Streamable HTTP — the
`tools/list` discovery endpoint will expose the two F1 tools.)

The response carries a `correlation_id` matching an audit row:

```bash
CID=...    # from the response
curl -fsS -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/api/v1/audit?correlation_id=$CID" | jq
# → one row with action=mcp.tool.invoked, actor=copilot, result=success
```

## 9. Verify the constitutional guarantees

```bash
# Every import created a LifecycleEvidence record:
curl -fsS -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/api/v1/evidence?evidence_type=import" | jq '.items | length'

# Every state-mutating action is audited:
curl -fsS -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/api/v1/audit?actor=$(whoami)&since=$(date -u -v-1H +%Y-%m-%dT%H:%M:%SZ)" \
  | jq '.items | length'

# RBAC denies unauthorized access:
TOKEN_VIEWER=$(./scripts/dev-mint-token.sh --roles viewer)
curl -i -X POST -H "Authorization: Bearer $TOKEN_VIEWER" \
  -F "file=@../gard-speckit-start/examples/devices.csv" \
  http://localhost:8080/api/v1/imports/devices/csv
# → 403; an audit row exists with result=denied
```

## 10. Success-criteria check

| Criterion | How to verify |
|---|---|
| SC-001 (10k rows ≤ 30s) | `time` the request in step 4 with a 10k-row file |
| SC-002 (≥95% exact/high for reference family) | After step 4, `SELECT confidence, count(*) FROM device_observations GROUP BY 1` ≥ 0.95 in {exact, high} for Cisco ISR1121 rows |
| SC-003 (every row accounted for) | `rows_total == rows_accepted + rows_rejected + rows_manual_review + rows_duplicate` for every job |
| SC-004 (manual review fully resolvable) | Step 7 ends with `remaining_manual_review = 0` without re-uploading |
| SC-005 (MCP < 2s @ 50k devices) | Step 8 with `--latency` flag; load 50k via the seed generator |
| SC-006 (audit coverage) | Step 9 audit query returns one row per mutating call |
| SC-007 (evidence per import) | Step 9 evidence query returns one row per completed import |
| SC-008 (auth enforced) | Step 9 denial returns 403 + audit row with `result=denied` |

## Teardown

```bash
docker compose down -v
```
