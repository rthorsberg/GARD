# F8 — Native MCP Transport quickstart

Live Streamable HTTP MCP at **`/mcp`** on the same uvicorn app as the REST API.
All 22 curated tools from F1–F7 share JWT auth, RBAC, and audit with REST.

## Prerequisites

- GARD stack running (`make up-build` or `docker compose -f deploy/docker-compose.yml up -d`)
- ISR1121 fixture seeded (recommended for smoke examples below):

```bash
./deploy/scripts/seed-isr1121.sh
```

## Mint an MCP client token

```bash
docker compose -f deploy/docker-compose.yml exec api \
  python -m gard issue-token \
  --subject agent:ops-smoke \
  --role mcp_client \
  --ttl-seconds 7200
```

Save the JWT (or use `.gard/token.jwt` from `make seed` with a lifecycle_manager role for REST-only calls).

## Endpoint

| Setting | Default |
|---|---|
| URL | `http://127.0.0.1:8080/mcp/` |
| Auth | `Authorization: Bearer <jwt>` |
| Transport | MCP Streamable HTTP (SDK `2025-03-26`) |

Disable MCP entirely:

```bash
export GARD_MCP_ENABLED=false
```

The mount returns HTTP 404 with `{"detail":"MCP disabled"}`.

## Standalone process (optional)

Same app factory, useful for local dev:

```bash
python -m gard mcp
# or: docker compose exec api python -m gard mcp
```

## Python SDK smoke (ISR1121)

After seeding, this call should return a non-zero `target_drift` count for Cisco IOS ISR1121:

```python
import asyncio
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

TOKEN = open(".gard/token.jwt").read().strip()
BASE = "http://127.0.0.1:8080"

async def main() -> None:
    async with httpx.AsyncClient(
        base_url=BASE,
        headers={"Authorization": f"Bearer {TOKEN}"},
        timeout=30.0,
    ) as http:
        async with streamable_http_client(f"{BASE}/mcp/", http_client=http) as (r, w, _):
            async with ClientSession(r, w) as session:
                await session.initialize()
                tools = await session.list_tools()
                print(f"tools: {len(tools.tools)}")
                result = await session.call_tool(
                    "count_devices_outside_target",
                    {
                        "vendor_normalized": "cisco",
                        "platform_family": "ios",
                    },
                )
                print(result.structuredContent or result.content)

asyncio.run(main())
```

Compare with REST:

```bash
curl -s -H "Authorization: Bearer $(cat .gard/token.jwt)" \
  'http://127.0.0.1:8080/api/v1/compliance/summary?vendor_normalized=cisco&platform_family=ios' \
  | jq '.counts_by_drift_type.target_drift'
```

## Deny-list

These names appear in `tools/list` but **reject** invocation with `tool not found` and audit `mcp.disallowed_tool_attempt`:

- `execute_sql`, `run_shell`, `read_file`, `write_file`, `http_request`, `propose_firmware_target_draft`

## Troubleshooting

| Symptom | Fix |
|---|---|
| `401 invalid token` | Re-mint token; check `GARD_JWT_SECRET` matches across processes |
| `404 MCP disabled` | Set `GARD_MCP_ENABLED=true` (default in dev) |
| `307` on `/mcp` | Use trailing slash: `/mcp/` |
| `missing permission: mcp.tool.invoke` | Token needs `--role mcp_client` plus per-tool permission via role mapping |

## Related

- ADR-0019 — transport binding
- Contract manifest: `specs/008-mcp-transport/contracts/mcp-tools.yaml`
