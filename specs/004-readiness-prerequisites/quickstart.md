# F4 Quickstart — Readiness & Prerequisites

**Generated**: 2026-05-31 by `/speckit-plan`
**Audience**: operators and AI agents using GARD to triage uplift readiness.

## 0. Pre-conditions

```bash
make up-build
make seed
```

After `make seed`, the per-device firmware compliance walk already runs F3 and prints the drift summary. F4 adds two new sections after that block.

## 1. Expected `make seed` output (F4 additions)

```
==> F4: triggering bounded readiness re-eval (scope=all)
    requested=5 evaluated=2 unchanged=3 not_applicable=3
    correlation_id=...

==> F4: estate-wide readiness summary
    total_outside_target=2 ready_for_uplift=0 blocked=2 not_applicable=3
    top_blocker_categories:
      - missing_upgrade_path  2
      - min_ram_mb            1  (if the new fixture lands)

==> F4: per-device readiness verdict
    r1.oslo   state=blocked         primary=missing_upgrade_path  rule=- detail=no chain from 7.5.2 to 7.8.1 on iosxr
    r2.oslo   state=blocked         primary=missing_upgrade_path  rule=- detail=no chain from 22.4R3-S2 to 23.2R1 on junos
    r3.oslo   state=not_applicable  reason=no_target_resolved
    r4.bergen state=not_applicable  reason=already_compliant
    r5.bergen state=not_applicable  reason=already_compliant
```

Note: the first run with the v1 catalogue will show `missing_upgrade_path` for r1 and r2 because the seed fixture does not (yet) include upgrade-path edges for those platforms. The reload-sync hook will pick up any added edges automatically.

## 2. Walk the per-device explainable verdict

```bash
TOKEN="$(cat .gard/token.jwt)"
curl -s -H "Authorization: Bearer $TOKEN" \
  "$API_BASE/api/v1/devices/$DEV_ID/readiness" | jq
```

Expected envelope for a blocked device:

```json
{
  "state": "blocked",
  "summary": "blocked: 1 required + 0 recommended blocker(s)",
  "target_version": "7.8.1",
  "observed_version": "7.5.2",
  "upgrade_path_exists": false,
  "applicable_rules_count": 1,
  "blockers": [
    {
      "rule_id": null,
      "predicate_kind": "missing_upgrade_path",
      "severity": "required",
      "required": {"target_version": "7.8.1", "platform_family": "iosxr"},
      "observed": {"observed_version": "7.5.2"},
      "detail": "no upgrade-path chain from 7.5.2 to 7.8.1 on platform iosxr"
    }
  ],
  "recommended_actions": [
    {
      "kind": "firmware_intermediate_step",
      "target_version": "7.8.1",
      "target_platform_family": "iosxr",
      "requires": ["firmware_catalog.read"],
      "detail": "add an upgrade-path edge or pick an intermediate hop"
    }
  ],
  "confidence": 1.0,
  "evaluation_id": "...",
  "compliance_evaluation_ref": "...",
  "evaluated_at": "...",
  "correlation_id": "..."
}
```

## 3. Estate-wide planning view

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "$API_BASE/api/v1/readiness/summary?region=oslo" | jq
```

Returns the same counters narrowed to Oslo. Use this for quarterly capacity planning.

## 4. Stale F3 input (409 path)

If the device's latest `compliance_evaluations` row is older than `GARD_READINESS_STALE_DAYS` (default 30), the per-device endpoint returns:

```json
{
  "error": {
    "code": "READINESS_INPUT_STALE",
    "message": "compliance_evaluation for this device is older than 30 days; refresh via POST /api/v1/compliance/evaluate",
    "details": {
      "latest_compliance_evaluated_at": "2026-04-30T...",
      "stale_threshold_days": 30
    }
  }
}
```

Recovery is a single call:

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
  -d "{\"device_ids\": [\"$DEV_ID\"]}" \
  "$API_BASE/api/v1/compliance/evaluate"
```

Then re-hit the readiness endpoint.

## 5. Audit verification

After running through this quickstart the operator can verify three new audit families landed:

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "$API_BASE/api/v1/audit?action=readiness.evaluated" | jq '.items | length'
curl -s -H "Authorization: Bearer $TOKEN" \
  "$API_BASE/api/v1/audit?action=readiness.read" | jq '.items | length'
curl -s -H "Authorization: Bearer $TOKEN" \
  "$API_BASE/api/v1/audit?action=readiness.evaluation_triggered" | jq '.items | length'
```

All three counts should be > 0 after a `make seed` run.
