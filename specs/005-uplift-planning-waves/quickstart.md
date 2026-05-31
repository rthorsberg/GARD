# F5 — Quickstart

## For operators

After `make seed`, the dev stack contains 5 devices with F1..F4 verdicts. F5 lets you turn the `ready_for_uplift` devices into reviewable, approvable change packets without leaving the API.

### 1. Create a plan

```bash
TOKEN=$(cat .gard/token.jwt)
curl -sS -X POST -H "Authorization: Bearer $TOKEN" \
  -H "content-type: application/json" \
  http://127.0.0.1:8080/api/v1/uplift/plans \
  -d '{"name": "Q3-2026-edge-refresh", "description": "Bring oslo IOS-XR edge to 7.8.1"}'
```

Returns a `PlanEnvelope` with `id`. Save it as `$PLAN_ID`.

### 2. Draft a wave from `ready_for_uplift` devices

```bash
curl -sS -X POST -H "Authorization: Bearer $TOKEN" \
  -H "content-type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  http://127.0.0.1:8080/api/v1/uplift/plans/$PLAN_ID/waves \
  -d '{
    "name": "oslo-edge-wave-1",
    "target_version": "7.8.1",
    "target_platform_family": "iosxr",
    "scope_selector": {"region_in": ["oslo"], "platform_family": "iosxr"},
    "change_window_start": "2026-07-14T04:00:00Z",
    "change_window_end":   "2026-07-14T06:00:00Z",
    "mode": "skip_ineligible"
  }'
```

Expected output:

- HTTP 201 with the `WaveEnvelope`
- `state: "draft"`
- `devices[]` contains every `ready_for_uplift` IOS-XR device in oslo
- `skipped[]` lists devices in the scope that were not eligible + reason
- one `uplift_wave.drafted` audit row written

### 3. Submit + approve (two principals required — R-2)

```bash
# Drafter submits:
curl -sS -X POST -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8080/api/v1/uplift/waves/$WAVE_ID/submit

# A different principal approves (mint a second JWT with a different subject):
APPROVER_TOKEN=...
curl -sS -X POST -H "Authorization: Bearer $APPROVER_TOKEN" \
  -H "content-type: application/json" \
  http://127.0.0.1:8080/api/v1/uplift/waves/$WAVE_ID/approve \
  -d '{"citation": "Change ticket CHG-2026-1872 — approved in CAB meeting 2026-07-10"}'
```

Self-approval attempts return `403 SELF_APPROVAL_FORBIDDEN`.

### 4. File + approve an exception for a blocked device

```bash
EXCEPTION=$(curl -sS -X POST -H "Authorization: Bearer $TOKEN" \
  -H "content-type: application/json" \
  http://127.0.0.1:8080/api/v1/uplift/exceptions \
  -d '{
    "device_id": "'$BLOCKED_DEVICE_ID'",
    "blocker_rule_id": "'$BLOCKER_RULE_ID'",
    "justification": "Device is end-of-life next quarter, explicit waiver from network ops director (2026-05-30).",
    "expires_at": "2026-08-30T00:00:00Z"
  }')

curl -sS -X POST -H "Authorization: Bearer $APPROVER_TOKEN" \
  http://127.0.0.1:8080/api/v1/uplift/exceptions/$EXCEPTION_ID/approve
```

After approval, F4's `GET /api/v1/devices/$DEVICE_ID/readiness` returns `state=not_applicable, reasons[0].kind=active_exception, reasons[0].ref_id=$EXCEPTION_ID`. After the `expires_at` timestamp passes, the next F4 evaluate flips the device back to `blocked`.

### 5. Verify the audit chain

```bash
curl -sS -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8080/api/v1/audit-events?object_type=UpliftWave&object_id=$WAVE_ID"
```

Should show **4 rows** for a happy-path approved wave: `uplift_wave.drafted`, `uplift_wave.submitted`, `uplift_wave.approved`, plus `uplift_wave.read` for every GET.

## For AI agents (MCP delegates — transport deferred to F008)

Six tools register at `gard/mcp/tools/<name>.py`:

| Tool | Type | Purpose |
|---|---|---|
| `create_uplift_wave_draft` | proposal (no DB write) | Resolve a scope_selector, present the proposed wave for human submission. |
| `create_exception_review_draft` | proposal | Suggest an exception filing for a blocked device. |
| `get_uplift_plan_summary` | read | Estate-wide counters by plan + wave state. |
| `list_open_waves` | read | "What's queued for review right now?" |
| `list_active_exceptions` | read | "What risk are we carrying right now?" |
| `explain_wave` | read | Full per-wave narrative — for change-ticket bodies. |

All six are read-shaped by design (R-9). The agent never mutates F5 state; a human always submits via the REST surface.

## Expected `make seed` output (post-F5)

The seed script gets three new sections after the F4 block:

```
==> F5: drafting a sample uplift wave (oslo-edge-wave-1)
    plan_id=...  wave_id=...
    devices=N (1 ready_for_uplift, M skipped)
    state=draft

==> F5: submit + approve flow (two principals)
    drafter=ops@example.com  approver=cab@example.com
    state=approved  citation=CHG-2026-1872

==> F5: estate-wide plan summary
    total_plans=1  active=1  archived=0
    wave_counts_by_state:
      - draft           0
      - submitted       0
      - approved        1
```
