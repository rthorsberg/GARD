# F3 Operator Quickstart

**Generated**: 2026-05-30 by `/speckit-plan`
**Audience**: lifecycle managers, field engineers, AI agents (via
the future MCP transport)
**Prerequisites**: F1 + F2 implementation present on the running
stack; `make seed` produces an F1+F2 demo state today, and after F3
implementation will additionally produce per-device drift
classifications.

This quickstart shows what F3 *delivers*, demoed against the same
5-device fixture set used by F1 and F2. It is the script
integration tests will follow.

---

## 1. Boot + seed

Standard F1+F2 boot. F3 implementation will extend `make seed` to
trigger one estate-wide evaluation pass after the F2 catalog reload,
so the `compliance_evaluations` table is populated for the demo
queries below.

```bash
make up-build      # rebuilds image with F3 router + migration 0007
make seed
```

Expected `make seed` output additions over today's F2 output:

```
==> Evaluating compliance for the estate (F3)
    5 devices evaluated, 5 new evaluation rows persisted

==> Per-device drift classification
    r5.bergen    compliant       drift=none            ←   in compliance
    r4.bergen    compliant       drift=none            ←   in compliance
    r3.oslo      classified      drift=catalog_drift   ←   no target for SR-OS
    r2.oslo      outside_target  drift=target_drift    ←   junos version mismatch
    r1.oslo      outside_target  drift=target_drift    ←   iosxr version mismatch
```

---

## 2. Operator workflow A — Monday morning triage (US1)

```bash
TOKEN=$(cat .gard/token.jwt)

curl -sS -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8080/api/v1/compliance/summary" | jq
```

Expected response shape:

```json
{
  "total_evaluated": 5,
  "compliant_count": 2,
  "unknown_count": 0,
  "counts_by_drift_type": {
    "target_drift":    2,
    "catalog_drift":   1,
    "package_drift":   0,
    "rule_drift":      0,
    "evidence_drift":  0,
    "discovery_drift": 0,
    "exception_drift": 0
  },
  "filters_applied": {},
  "as_of": "2026-05-30T08:55:12Z"
}
```

The triage flow: operator sees `catalog_drift: 1` and clicks
through to see *which* device is missing a target.

```bash
curl -sS -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8080/api/v1/compliance/devices?drift_type=catalog_drift" | jq
```

Expected: exactly the `r3.oslo` device (Nokia SR-OS, no F2 target
matches), with its full envelope including a `define_target`
recommended action.

---

## 3. Operator workflow B — paged about r1.oslo (US2)

```bash
R1_ID=$(curl -sS -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8080/api/v1/devices?limit=200" \
  | jq -r '.items[] | select(.facts.hostname=="r1.oslo") | .facts.id')

curl -sS -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8080/api/v1/devices/$R1_ID/compliance" | jq
```

Expected envelope:

```json
{
  "state": "outside_target",
  "summary": "Device on 7.5.2; target is 7.8.1. Upgrade path exists.",
  "drift_type": "target_drift",
  "secondary_drift_types": [],
  "target_ref": "06a19a40-f305-73f3-8000-d93ee25a761c",
  "target_version": "7.8.1",
  "observed_version": "7.5.2",
  "observation_ref": "…",
  "facts": {
    "hostname": "r1.oslo",
    "platform_family": "iosxr",
    "vendor_normalized": "cisco"
  },
  "reasons": [
    {"kind": "target_matched",    "ref": "06a19a40-f305-…",
     "detail": "cisco-iosxr-edge"},
    {"kind": "version_mismatch", "ref": "06a19a40-f305-…",
     "detail": "observed=7.5.2, target=7.8.1"}
  ],
  "recommended_actions": [
    {"kind": "upgrade_path_query",
     "ref": null,
     "params": {"platform_family": "iosxr",
                "from_version": "7.5.2",
                "to_version": "7.8.1"}}
  ],
  "confidence": 1.0,
  "as_of": "2026-05-30T08:55:12Z",
  "correlation_id": "9a4f…"
}
```

Field engineer's takeaway in one read: "Outside target. Cisco IOS XR
edge target wants 7.8.1, device on 7.5.2. Run the upgrade-path
query F2 already exposes to get the chain." No client-side joins,
no SQL, no SSH.

---

## 4. Operator workflow C — bulk re-eval after a catalog edit

After the operator merges a YAML PR adding a Nokia SR-OS target:

```bash
make seed                                    # idempotent reload
# OR explicit re-evaluation:
curl -sS -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"scope_selector": {"vendor_normalized": "nokia"}}' \
  "http://127.0.0.1:8080/api/v1/compliance/evaluate" | jq
```

Expected: `evaluated_count: 1` (just r3.oslo), and the next call to
`/compliance/summary` shows `catalog_drift: 0`.

The bounded re-eval that F2 already wired automatically triggers F3
resyncing for the same device set — operators rarely need to call
this endpoint explicitly.

---

## 5. Audit trail to confirm everything is captured

```bash
docker compose -f deploy/docker-compose.yml exec -T postgres \
  psql -U gard -d gard -c "
    SELECT action, object_type, result, occurred_at
    FROM audit_events
    WHERE action LIKE 'compliance.%'
    ORDER BY occurred_at DESC
    LIMIT 10;"
```

Expected: one `compliance.evaluated` row per device that received a
new evaluation, one `compliance.read` row per summary/list request,
and one `compliance.evaluation_triggered` row per
`POST /compliance/evaluate`. All share correlation ids with the
HTTP requests' `X-Correlation-Id` headers.
