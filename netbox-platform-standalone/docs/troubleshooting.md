# Troubleshooting

## Health report

```bash
./scripts/health.sh | jq .
```

| Exit | Status | Meaning |
|------|--------|---------|
| 0 | `healthy` | Core checks OK and Branching enabled |
| 1 | `degraded` | Core OK; Branching off (expected unless `NETBOX_BRANCHING_ENABLED=1`) |
| 2 | `unhealthy` | NetBox, Diode gRPC, Orb, or Diode plugin failed |

## NetBox UI never loads

- Wait up to ~2 minutes on first boot (migrations).
- Check: `docker compose -p netbox-platform logs netbox --tail 50`
- Port conflict: change `NETBOX_HOST_PORT` in `.env`.

## Diode gRPC port closed

- `docker compose -p netbox-platform ps` — `diode-nginx`, `diode-ingester`, `diode-auth` must be up.
- Re-run OAuth: `./scripts/setup-oauth.sh`
- Logs: `docker compose -p netbox-platform logs diode-reconciler diode-ingester --tail 80`

## Orb ingest 401 / unauthorized

Common causes:

1. **Placeholder credentials in `agent.yaml`** — run `./scripts/setup-oauth.sh` and confirm `client_id` / `client_secret` are literals, not `${DIODE_*}`.
2. **Stale nginx upstream** after restarts: `docker compose -p netbox-platform restart diode-nginx orb-agent`
3. **Wrong gRPC target** — host-network Orb must use `grpc://127.0.0.1:58080/diode`, not `diode-nginx`.

## Discovery finds nothing (real devices)

- Default compose only reaches the `platform` bridge (172.30.77.0/24) unless you use host networking.
- Use `docker-compose.orb-host.yml` and set management IPs/CIDRs in `platform/orb/agent.yaml`.
- Orb needs `cap_add: NET_RAW` (already in compose) and routes to device subnets.

## OAuth / Hydra errors on first start

- Edit secrets in `client-credentials.json` before `setup-oauth.sh`.
- Wipe Diode DB only (fresh Hydra): `./scripts/stop.sh --volumes` then start again.

## Safe teardown

Always scope by project name:

```bash
./scripts/stop.sh
./scripts/stop.sh --volumes   # deletes netbox-platform volumes only
```

Do **not** run `docker compose down -v` without `-p netbox-platform` — that can remove unrelated stacks.
