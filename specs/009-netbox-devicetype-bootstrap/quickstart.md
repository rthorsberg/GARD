# F9 — NetBox device type bootstrap quickstart

Bootstrap **community-backed device types** for GARD-supported models only, then seed demo devices and run F7 sync.

## Prerequisites

- Optional dev NetBox running (`deploy/netbox/docker-compose.yml`, port **18888**)
- NetBox **write** token (`NETBOX_SEED_TOKEN`) for bootstrap + seed
- Git submodule initialized: `git submodule update --init vendor/netbox-devicetype-library`

## 1. Start dev NetBox (if not running)

```bash
docker compose -p gard-f7-netbox -f deploy/netbox/docker-compose.yml up -d
# wait ~90s for http://127.0.0.1:18888/
```

## 2. Validate manifest (dry run)

```bash
export NETBOX_URL=http://127.0.0.1:18888
export NETBOX_SEED_TOKEN=<write-token-from-netbox-ui>

python -m gard netbox bootstrap-device-types --dry-run
```

Expect: manifest loads, all `library_path` files resolve at pinned SHA, zero NetBox writes.

## 3. Bootstrap device types

```bash
python -m gard netbox bootstrap-device-types
```

Expect summary: 6 entries → manufacturers + device types created (or skipped if re-run). ISR1121 type includes interface templates from community YAML.

## 4. Seed demo devices + GARD sync

```bash
./deploy/scripts/seed-netbox.sh   # calls bootstrap internally after F9 implement
```

Then point GARD at NetBox and sync (F7):

```bash
export GARD_NETBOX_URL=http://127.0.0.1:18888
export GARD_NETBOX_TOKEN=<read-only-token>
export GARD_NETBOX_VERIFY_TLS=false

curl -X POST -H "Authorization: Bearer $(cat .gard/token.jwt)" \
  http://127.0.0.1:8080/api/v1/integrations/netbox/sync
```

## Production provision (optional)

For non-localhost NetBox:

```bash
export NETBOX_URL=https://netbox.example.com
export NETBOX_SEED_TOKEN=<write-token>

python -m gard netbox bootstrap-device-types --confirm
```

`--confirm` is required outside dev. GARD API startup never runs this automatically.

## Pin bump procedure

When adding a new GARD-supported model:

1. Confirm a matching YAML exists in `vendor/netbox-devicetype-library` at the current pin (or bump pin first).
2. Add an entry to `gard-catalog/netbox/device-types-manifest.yaml` with unique `id`, `expected_slug`, and `model_raw_aliases` covering CSV/seed `model_raw` values.
3. Run `python -m gard netbox bootstrap-device-types --dry-run` and contract tests.
4. Bootstrap dev NetBox and update seed fixtures if needed.

When bumping upstream library version:

1. Update `upstream_pin` in `gard-catalog/netbox/device-types-manifest.yaml`
2. `cd vendor/netbox-devicetype-library && git fetch && git checkout <pin>`
3. Run `python -m gard netbox bootstrap-device-types --dry-run`
4. Run contract tests; commit manifest + submodule pointer together

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `library_path not found` | Submodule not at manifest pin — run submodule update |
| `conflict` on re-bootstrap | Type already exists with different layout; use `--force` only if safe |
| F7 sync duplicates | Device type slug mismatch — verify seed uses imported slug |
| Prod refused without confirm | Pass `--confirm` explicitly |

## Related

- F7 quickstart: `specs/007-netbox-integration-read/quickstart.md`
- Manifest schema: `specs/009-netbox-devicetype-bootstrap/contracts/device-types-manifest.schema.yaml`
- ADR-0020: bootstrap boundary (`adr/ADR-0020-netbox-devicetype-bootstrap.md`)
