# F2 Operator Quickstart: Firmware Catalog

**Time budget**: < 15 minutes from clone to live compliance read (SC-008).
**Prereqs**: a working F1 stack (i.e. `make up-build && make seed` works against `main`).

This walkthrough exercises every F2 user story end-to-end and shows what each step looks like in the audit + evidence trail. Steps map directly to `spec.md` Acceptance Scenarios (AC) and Success Criteria (SC-00x).

---

## 0. Reset to a clean F2-ready state

```bash
make reset                                # F1 baseline: 5 devices, normalization catalog loaded
cat .gard/token.jwt | pbcopy              # JWT also on clipboard
```

Verify:

```bash
curl -sS http://127.0.0.1:8080/healthz
# {"status":"ok","version":"0.2.0","service":"gard"}
```

After F2 ships, the version bumps to `0.2.0` and `healthz` reports `blob_root_writable: true` when the API process can write to `GARD_BLOB_ROOT`.

---

## 1. (US2 / AC-2.1) Author a firmware target via YAML and load it

Add a new firmware target by writing a YAML file to `gard-catalog/firmware/targets/`:

```bash
mkdir -p gard-catalog/firmware/targets
cat > gard-catalog/firmware/targets/cisco-iosxr-edge.yaml <<'YAML'
catalog_schema_version: 1.0.0
name: cisco-iosxr-edge
platform_family: iosxr
target_version: "7.5.2"
scope_selector:
  vendor_normalized: cisco
  platform_family: iosxr
  region_in: [oslo]
notes: "Edge routers in Oslo run a frozen 7.5.2 baseline."
YAML

git add gard-catalog/firmware/targets/cisco-iosxr-edge.yaml
git commit -m "feat(catalog): add cisco-iosxr-edge target"
```

Trigger a reload (or `docker compose restart api`; the lifespan handler reloads on boot):

```bash
docker compose -f deploy/docker-compose.yml exec api \
  python -m gard catalog reload firmware
# loaded=1 skipped=0 errors=0
```

Verify:

```bash
TOKEN=$(cat .gard/token.jwt)
curl -sS -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8080/api/v1/firmware/targets | jq
```

Expected response includes one target with `loaded_from_git_sha` populated. The audit row:

```bash
curl -sS -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8080/api/v1/audit?action=firmware_catalog.target.loaded&limit=1" | jq
```

`after.git_commit_sha` matches the commit we just made. **SC-002 + SC-003 satisfied** (policy goes from PR-merged to live; mutation traceable to git SHA).

---

## 2. (US1 / AC-1.1, AC-1.2, AC-1.5) Read per-device compliance

The F1 seed brought up `r1.oslo` (cisco/iosxr at firmware `7.5.2`) and `r2.oslo` (juniper). Let's check both:

```bash
R1_ID=$(curl -sS -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8080/api/v1/devices" | jq -r '.items[] | select(.facts.hostname=="r1.oslo") | .facts.id')

curl -sS -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8080/api/v1/devices/$R1_ID/firmware-compliance" | jq
```

Expected:

```json
{
  "state": "compliant",
  "summary": "r1.oslo matches target cisco-iosxr-edge at version 7.5.2",
  "target_ref": "...",
  "target_version": "7.5.2",
  "observed_version": "7.5.2",
  "reasons": [
    {"kind": "target_matched", "ref": "..."},
    {"kind": "version_match"}
  ],
  "recommended_actions": [],
  "confidence": 1.0,
  "as_of": "2026-05-29T...",
  "correlation_id": "..."
}
```

**SC-001 satisfied** (single HTTP call, envelope shape from F1, correct result on first read after import).

Now for the juniper device (`r2.oslo`):

```bash
R2_ID=$(curl -sS -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8080/api/v1/devices" | jq -r '.items[] | select(.facts.hostname=="r2.oslo") | .facts.id')
curl -sS -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8080/api/v1/devices/$R2_ID/firmware-compliance" | jq '.state, .reasons'
```

Expected:

```json
"classified"
[{"kind": "no_target_matched"}]
```

The juniper device's lifecycle state stays at `classified` because no target's `scope_selector` matched. **AC-1.4 confirmed.**

---

## 3. (US1 / AC-1.3) Unknown observation, unknown compliance

CSV-import a device with no `observed_firmware`:

```bash
cat > /tmp/r6.csv <<'CSV'
hostname,site,serial_number,vendor_raw,model_raw,observed_firmware,os_string,management_ip,observed_at,actor_email
r6.oslo,oslo-1,FOX5555ZZZZZ,Cisco Systems,ASR9006,,,10.0.0.6,2026-05-29T14:00:00Z,ops@example.com
CSV

curl -sS -X POST -H "Authorization: Bearer $TOKEN" \
  -F "file=@/tmp/r6.csv;type=text/csv" \
  -F "actor_email=ops@example.com" \
  "http://127.0.0.1:8080/api/v1/imports/devices/csv?override=true"

R6_ID=$(curl -sS -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8080/api/v1/devices" | jq -r '.items[] | select(.facts.hostname=="r6.oslo") | .facts.id')

curl -sS -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8080/api/v1/devices/$R6_ID/firmware-compliance" | jq '.state, .reasons[0]'
```

Expected:

```json
"unknown"
{"kind": "missing_observation"}
```

No silent coercion to `compliant` or `outside_target`. **Constitution III + AC-1.3 confirmed.**

---

## 4. (US3 / AC-3.1, AC-3.2) Author an upgrade path graph and resolve it

```bash
mkdir -p gard-catalog/firmware/upgrade-paths
cat > gard-catalog/firmware/upgrade-paths/cisco-iosxr.yaml <<'YAML'
catalog_schema_version: 1.0.0
platform_family: iosxr
edges:
  - {from_version: "7.4.1", to_version: "7.5.2", weight: 1}
  - {from_version: "7.5.2", to_version: "7.8.1", weight: 1}
  - {from_version: "7.4.1", to_version: "7.8.1", weight: 5, notes: "skip-version, not preferred"}
YAML

git add gard-catalog/firmware/upgrade-paths/cisco-iosxr.yaml
git commit -m "feat(catalog): add cisco iosxr upgrade graph"
docker compose -f deploy/docker-compose.yml exec api \
  python -m gard catalog reload firmware
```

Resolve the shortest path 7.4.1 → 7.8.1:

```bash
curl -sS -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8080/api/v1/firmware/upgrade-paths?platform_family=iosxr&from_version=7.4.1&to_version=7.8.1" | jq
```

Expected `chain: ["7.4.1", "7.5.2", "7.8.1"]`, `hop_count: 2`, `total_weight: 2` — **not** the direct weight-5 edge. **SC-006 satisfied** (Dijkstra picks the lowest-weight chain).

Now try a non-existent path:

```bash
curl -sS -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8080/api/v1/firmware/upgrade-paths?platform_family=iosxr&from_version=99.0&to_version=7.8.1" | jq
```

Expected `chain: []`, `total_weight: null`, `reasons: [{"kind": "no_path"}]`. HTTP **200**, not 404. **AC-3.2 confirmed.**

---

## 5. (US3 / AC-3.4) Author a prerequisite with a deferred predicate

```bash
mkdir -p gard-catalog/firmware/prerequisites
cat > gard-catalog/firmware/prerequisites/edge-only.yaml <<'YAML'
catalog_schema_version: 1.0.0
name: edge-only-target
applies_to:
  platform_family: iosxr
predicate:
  kind: tagged_with
  tags: [edge]
severity: required
YAML

git add gard-catalog/firmware/prerequisites/edge-only.yaml
git commit -m "feat(catalog): add edge-only prerequisite (deferred to F7)"
docker compose -f deploy/docker-compose.yml exec api \
  python -m gard catalog reload firmware

curl -sS -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8080/api/v1/firmware/prerequisites" | jq '.items[0] | {name, predicate_kind, evaluable}'
```

Expected:

```json
{"name": "edge-only-target", "predicate_kind": "tagged_with", "evaluable": false}
```

The rule loads but `evaluable: false` because tag sourcing waits on F7. **AC-3.4 confirmed.**

---

## 6. (US2 / AC-2.2) Reload rolls back on malformed YAML

Deliberately break a target:

```bash
cat > gard-catalog/firmware/targets/broken.yaml <<'YAML'
catalog_schema_version: 1.0.0
name: broken
platform_family: iosxr
target_version: "x.y.z"
# scope_selector intentionally omitted
YAML

docker compose -f deploy/docker-compose.yml exec api \
  python -m gard catalog reload firmware
# exits non-zero, prints offending file, no partial DB state
```

Verify the previously-loaded targets are untouched:

```bash
curl -sS -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8080/api/v1/firmware/targets" | jq '.total_returned'
# still 1 — the cisco-iosxr-edge target
```

And an audit row recorded the failure:

```bash
curl -sS -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8080/api/v1/audit?action=firmware_catalog.reload_failed&limit=1" | jq '.items[0].after'
# {"failing_file_relpath": "firmware/targets/broken.yaml", "reason": "missing required property: scope_selector", ...}
```

**SC-004 satisfied** (malformed input never produces partial catalog state). Clean up:

```bash
rm gard-catalog/firmware/targets/broken.yaml
```

---

## 7. (US2 / AC-2.3) Retract a target by removing its YAML

```bash
git rm gard-catalog/firmware/targets/cisco-iosxr-edge.yaml
git commit -m "feat(catalog): retract cisco-iosxr-edge (decommissioning)"
docker compose -f deploy/docker-compose.yml exec api \
  python -m gard catalog reload firmware
```

Re-check `r1.oslo`:

```bash
curl -sS -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8080/api/v1/devices/$R1_ID/firmware-compliance" | jq '.state, .reasons[0]'
```

Expected `state: "classified"`, `reasons[0].kind: "no_target_matched"`. The device fell back from `compliant` to `classified`. An audit row captured both transitions:

```bash
curl -sS -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8080/api/v1/audit?action=firmware_target.compliance_evaluated&limit=2" | jq '.items[].after.after_state'
# "classified"
# (the earlier "compliant" transition is also in the log if you scroll)
```

Re-add the YAML and reload — the device transitions back via `target_defined → compliant`. **D3 soft-delete behaviour confirmed**: the same target row is resurrected (`removed_at IS NULL`), not a new row.

---

## 8. (US4 / AC-4.1, AC-4.2) Upload and verify a firmware package blob

Create a tiny fixture so we don't have to download a real Cisco image:

```bash
dd if=/dev/urandom of=/tmp/fake-iosxr.bin bs=1M count=10 2>/dev/null
SHA=$(shasum -a 256 /tmp/fake-iosxr.bin | awk '{print $1}')
BYTES=$(stat -f%z /tmp/fake-iosxr.bin)

mkdir -p gard-catalog/firmware/packages
cat > gard-catalog/firmware/packages/cisco-iosxr-7.5.2.yaml <<YAML
catalog_schema_version: 1.0.0
vendor: cisco
platform_family: iosxr
version: "7.5.2"
sha256: "$SHA"
byte_size: $BYTES
signed_by: cisco
notes: "Fixture for local dev — not the real artefact."
YAML

git add gard-catalog/firmware/packages/cisco-iosxr-7.5.2.yaml
git commit -m "feat(catalog): add cisco iosxr 7.5.2 package metadata"
docker compose -f deploy/docker-compose.yml exec api \
  python -m gard catalog reload firmware

PKG_ID=$(curl -sS -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8080/api/v1/firmware/packages?vendor=cisco" | jq -r '.items[0].id')

# Upload
curl -sS -X POST -H "Authorization: Bearer $TOKEN" \
  --data-binary "@/tmp/fake-iosxr.bin" \
  -H "Content-Type: application/octet-stream" \
  "http://127.0.0.1:8080/api/v1/firmware/packages/$PKG_ID/blob"
```

Expected `{"computed_sha256": "<SHA>", "bytes_written": <BYTES>}` — HTTP 200.

Now download and verify:

```bash
curl -sS -D /tmp/headers.txt -o /tmp/roundtrip.bin -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8080/api/v1/firmware/packages/$PKG_ID/blob"
grep X-GARD-SHA256 /tmp/headers.txt
shasum -a 256 /tmp/roundtrip.bin
```

Both hashes match. **SC-005 satisfied** (download verified on every read).

Now try a tampered upload (should reject):

```bash
echo "this is not the firmware" > /tmp/fake.bin
curl -sS -o /dev/null -w "%{http_code}\n" -X POST -H "Authorization: Bearer $TOKEN" \
  --data-binary "@/tmp/fake.bin" -H "Content-Type: application/octet-stream" \
  "http://127.0.0.1:8080/api/v1/firmware/packages/$PKG_ID/blob"
# 422
```

**AC-4.2 confirmed.** Lifecycle evidence:

```bash
curl -sS -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8080/api/v1/evidence?evidence_type=firmware_package_upload&limit=1" | jq '.items[0] | {subject_id, source_checksum}'
```

Subject id matches the package id; source checksum matches the SHA we uploaded.

---

## 9. (US5 / AC-5.1, AC-5.2) Same answers through MCP

Using `curl` against the MCP server (running on the same Compose stack at `/mcp`):

```bash
curl -sS -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' \
  http://127.0.0.1:8080/mcp | jq '.result.tools[].name'
```

Expected tools (F1 + F2):

```
"list_devices"
"get_device_lifecycle_status"
"get_target_firmware"
"get_upgrade_path"
"list_firmware_targets"
"list_firmware_packages"
"list_upgrade_paths"
```

Invoke `get_target_firmware`:

```bash
curl -sS -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"get_target_firmware\",\"arguments\":{\"device_id\":\"$R1_ID\"}}}" \
  http://127.0.0.1:8080/mcp | jq '.result.content[0]'
```

Field-for-field identical to the REST `firmware-compliance` body. **SC-007 satisfied** (MCP and REST agree).

Try a disallowed tool:

```bash
curl -sS -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"execute_sql","arguments":{}}}' \
  http://127.0.0.1:8080/mcp | jq '.error.code'
# "tool_not_found"
```

Audit log:

```bash
curl -sS -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8080/api/v1/audit?action=mcp.disallowed_tool_attempt&limit=1" | jq '.items[0].after'
```

`{"tool_name": "execute_sql", ...}`. **AC-5.3 confirmed.**

---

## 10. Tear-down and `make reset` proof

```bash
make down-volumes
make reset                 # F1 + F2 fixtures auto-loaded
```

Time the full reset:

```bash
time make reset
```

Should complete in under 30 seconds on a developer laptop. The first compliance read against any device returns within 250 ms.

---

## Acceptance / SC mapping summary

| Step | Acceptance scenarios verified | Success criteria touched |
|---|---|---|
| 0 | — | (env baseline) |
| 1 | AC-2.1 | SC-002, SC-003 |
| 2 | AC-1.1, AC-1.2, AC-1.4 | SC-001, SC-008 |
| 3 | AC-1.3 | SC-001 (unknown handling) |
| 4 | AC-3.1, AC-3.2 | SC-006 |
| 5 | AC-3.4 | SC-003 (deferred predicates are still tracked) |
| 6 | AC-2.2 | SC-004 |
| 7 | AC-2.3 | SC-003 |
| 8 | AC-4.1, AC-4.2, AC-4.4 | SC-005 |
| 9 | AC-5.1, AC-5.2, AC-5.3 | SC-007 |
| 10 | end-to-end | SC-008 |

Eight success criteria, ten quickstart steps, every acceptance scenario from the spec exercised at least once. If any step deviates from "Expected", that's a F2 implementation bug; file it before sign-off.
