# NetBox Platform Stack (NetBox + Diode + Orb)

Standalone Docker Compose bundle: **Orb → Diode → NetBox** with optional **Branching**.  
No GARD application code required. Copy or sparse-checkout this folder onto a discovery host.

**Upstream**: Derived from [GARD](https://github.com/rthorsberg/GARD) F13 (`netbox-platform-standalone/`).  
**Scope**: Lab / pilot use — not production HA. See [NetBox Labs Diode docs](https://netboxlabs.com/docs/diode/getting-started/) for hardened deployments.

## Download (this folder only)

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/rthorsberg/GARD.git gard-netbox-bundle
cd gard-netbox-bundle
git sparse-checkout set netbox-platform-standalone
cd netbox-platform-standalone
```

Or download a ZIP of the repo and use only the `netbox-platform-standalone/` directory.

## Requirements

- Docker Compose v2, bash, curl, python3
- ~8 GB RAM
- Host ports **18888** (NetBox), **58080** (Diode gRPC) — override in `.env`
- For **real network discovery**: host must reach device management IPs (see [Real devices](#real-devices-not-lab-simulators))

## Quick start

```bash
cp .env.example .env
# Edit .env — strong passwords for NetBox/DB/Redis/Hydra
# Edit platform/diode/oauth2/client/client-credentials.json — replace REPLACE_WITH_STRONG_SECRET

./scripts/start.sh
./scripts/health.sh | jq .    # expect degraded until OAuth + Orb are configured

./scripts/setup-oauth.sh      # Hydra clients, .env, platform/orb/agent.yaml

./scripts/health.sh | jq .
```

Lab simulators (optional fake routers on the platform subnet):

```bash
COMPOSE_PROFILES=lab ./scripts/start.sh
cp platform/orb/agent.yaml.example-lab platform/orb/agent.yaml
./scripts/setup-oauth.sh
```

- **NetBox UI**: `http://<server-ip>:18888/` (admin / password from `.env`)
- **API token** (for automation): `eval "$(./scripts/create-api-token.sh)"`

## Real devices (not lab simulators)

1. Edit `platform/orb/agent.yaml` — set your management IPs/subnets and Orb credentials.
2. Start with **host networking** for Orb (so scans use the server’s routes):

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.orb-host.yml \
     -p netbox-platform --env-file .env up -d --build
   ```

   In `agent.yaml`, set Diode target to `grpc://127.0.0.1:58080/diode` (not `diode-nginx`).

3. Do **not** enable the `lab` profile unless you want fake simulator containers:

   ```bash
   # Lab simulators only (optional):
   docker compose --profile lab ...
   ```

## Optional Branching

```bash
# In .env:
NETBOX_BRANCHING_ENABLED=1

./scripts/start.sh   # rebuilds NetBox image with branching plugin
```

Stage changes on a NetBox branch, **merge to `main`**, then let any downstream consumer (e.g. GARD) read `main` only.

## Scripts

| Script | Purpose |
|--------|---------|
| `./scripts/start.sh` | Build + up (compose project `netbox-platform`) |
| `./scripts/stop.sh` | Stop (keeps volumes) |
| `./scripts/stop.sh --volumes` | Stop + wipe **this** project’s volumes only |
| `./scripts/health.sh` | JSON health report (exit 0/1/2) |
| `./scripts/create-api-token.sh` | Mint NetBox API token to stdout |
| `./scripts/setup-oauth.sh` | Bootstrap Hydra clients + print next steps |

## Layout

```text
netbox-platform-standalone/
├── docker-compose.yml          # full stack
├── docker-compose.orb-host.yml   # Orb host network overlay
├── Dockerfile.plugins
├── .env.example
├── configuration/plugins.py
├── platform/diode/               # nginx, oauth templates, postgres init
├── platform/orb/agent.yaml       # edit for your network
├── scripts/
└── docs/
```

## Teardown

```bash
./scripts/stop.sh
# Wipe data:
./scripts/stop.sh --volumes
```

Never run `docker system prune` or `compose down -v` without `-p netbox-platform`.

## Integrating with GARD (optional)

If you run [GARD](https://github.com/rthorsberg/GARD) elsewhere, point its API at this NetBox:

- `GARD_NETBOX_URL=http://<this-server-ip>:18888`
- Token from `./scripts/create-api-token.sh`
- Sync only after changes are on NetBox **`main`**

## Docs

- [docs/diode-oauth.md](docs/diode-oauth.md) — Hydra / Diode / Orb credentials
- [docs/troubleshooting.md](docs/troubleshooting.md) — common failures
