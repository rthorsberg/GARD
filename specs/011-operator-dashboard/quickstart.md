# F11 — Operator portal quickstart

Run the GARD operator web UI against a local lab stack.

## Prerequisites

- GARD API running (F1–F10): `uv run python -m gard serve` or docker compose
- Node.js **20+** and **pnpm** (or npm)
- Lab JWT with appropriate role (lifecycle_admin for full UI)

## 1. Issue a lab token

```bash
# If you have an admin JWT already:
ADMIN_JWT=$(cat .gard/admin.jwt)   # or issue via your lab bootstrap

curl -s -X POST http://127.0.0.1:8080/api/v1/admin/tokens \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "ui-lab",
    "subject": "operator@lab",
    "roles": ["lifecycle_admin"],
    "ttl_seconds": 86400
  }' | jq -r '.jwt' > .gard/ui-lab.jwt
```

Viewer-only smoke test: use `"roles": ["viewer"]`.

## 2. Install and run the UI (dev)

```bash
cd web
pnpm install
pnpm dev
```

Open http://127.0.0.1:5173/sign-in

- **API base URL**: leave empty (Vite proxies `/api` → `http://127.0.0.1:8080`)
- **Token**: paste contents of `.gard/ui-lab.jwt`

## 3. Verify dashboard

After sign-in you should see:

- Compliance summary tiles (compliant / drifted / unknown)
- Readiness summary tiles
- NetBox linked count
- Recent audit activity table

Click **Drifted** → devices list filtered to `outside_target`.

## 4. Guided workflow smoke (admin token)

1. **Devices** → Import CSV (lab sample from F6 quickstart)
2. **Compliance** → Run evaluation → wait for completion banner
3. **Readiness** → Run evaluation
4. **NetBox** → Sync (with write-back confirm if prod guard applies)
5. **Audit** → confirm import/eval/sync events appear

## 5. Production-style static build

```bash
cd web
pnpm build
pnpm preview   # serves dist on :4173 — configure proxy or set API URL at sign-in
```

Deploy `web/dist` behind nginx with:

```nginx
location /api/ {
    proxy_pass http://gard-api:8080;
}
location / {
    root /usr/share/nginx/html;
    try_files $uri /index.html;
}
```

## 6. Optional split-origin dev (CORS)

If UI and API run on different origins without a proxy:

```bash
export GARD_CORS_ORIGINS=http://127.0.0.1:5173
uv run python -m gard serve
```

Sign-in with API base URL `http://127.0.0.1:8080`.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| 401 on every screen | Token expired — re-issue; check clock skew |
| Empty dashboard widgets | Role lacks `compliance.read` / `readiness.read` — check JWT roles |
| CORS error in browser | Use Vite proxy (default) or set `GARD_CORS_ORIGINS` |
| NetBox sync 403 confirm | Add `confirm_writeback=true` in UI (prod guard) |
| Drift counts all zero | Run compliance evaluation first (F10 write-back uses stored evals) |

## Related docs

- API map: `contracts/ui-api-map.yaml`
- Routes: `contracts/ui-routes.yaml`
- F10 NetBox write-back: `specs/010-netbox-writeback/quickstart.md`
