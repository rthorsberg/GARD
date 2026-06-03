# Diode OAuth and Orb credentials

This stack uses **Ory Hydra** (via `diode-auth`) for client-credentials tokens between NetBox, Diode, and Orb.

## One-time secret setup

Before `./scripts/setup-oauth.sh`, put strong secrets in:

`platform/diode/oauth2/client/client-credentials.json`

Replace both `REPLACE_WITH_STRONG_SECRET` values (one per client). Example:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Keep `client_id` values as shipped (`netbox-to-diode`, `diode-to-netbox`).

## Bootstrap sequence

```bash
./scripts/start.sh          # NetBox + Hydra + Diode up
./scripts/setup-oauth.sh    # Hydra clients + .env + Orb client
```

`setup-oauth.sh` will:

1. Run `diode-auth-bootstrap` (loads `client-credentials.json` into Hydra).
2. Copy NetBox/Diode secrets into `.env` as `NETBOX_TO_DIODE_CLIENT_SECRET` and `DIODE_TO_NETBOX_CLIENT_SECRET`.
3. Create an Orb ingest client via `authmanager` and write `DIODE_CLIENT_ID` / `DIODE_CLIENT_SECRET` to `.env`.
4. Patch `platform/orb/agent.yaml` with **literal** `client_id` / `client_secret` (Orb does not expand `${...}` from Docker env).

Then restart Orb and nginx:

```bash
docker compose -p netbox-platform --env-file .env restart orb-agent diode-nginx
```

## Orb agent.yaml

| Compose mode | `target` in `platform/orb/agent.yaml` |
|--------------|----------------------------------------|
| Default bridge | `grpc://diode-nginx:80/diode` |
| `docker-compose.orb-host.yml` | `grpc://127.0.0.1:58080/diode` |

## Environment reference

| Variable | Role |
|----------|------|
| `OAUTH2_PUBLIC_SERVER_URL` | Must be `http://hydra:4444` inside the compose network (not `127.0.0.1`) |
| `NETBOX_TO_DIODE_CLIENT_SECRET` | NetBox plugin → Diode |
| `DIODE_TO_NETBOX_CLIENT_SECRET` | Diode reconciler → NetBox API |
| `DIODE_CLIENT_ID` / `DIODE_CLIENT_SECRET` | Orb → Diode gRPC ingest |

## NetBox UI alternative

After login: **Plugins → Diode → Client credentials** can show or rotate clients. For automation, prefer `setup-oauth.sh` on first boot.

## NetBox API token

For tools outside this compose file (e.g. GARD):

```bash
eval "$(./scripts/create-api-token.sh)"
```
