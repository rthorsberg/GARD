# Diode OAuth bootstrap (lab)

The Diode auth container expects OAuth client definitions under
`oauth2/client/`. On first lab bring-up:

1. Start the stack once (`platform-lab-start.sh`).
2. Inspect `diode-auth-bootstrap` logs for generated client secrets.
3. Copy `netbox-to-diode` secret into `deploy/netbox/.env` as
   `NETBOX_TO_DIODE_CLIENT_SECRET`.
4. Restart NetBox (`docker compose ... restart netbox netbox-worker`).
5. Create an Orb ingest client (or use the lab default):
   ```bash
   docker compose -p gard-f7-netbox ... run --rm --no-deps diode-auth \
     authmanager create-client --client-id orb-platform-lab --allow-ingest \
     --client-secret gard-lab-orb-ingest-dev-only
   ```
6. Set `DIODE_CLIENT_ID` / `DIODE_CLIENT_SECRET` in `.env` (must match `platform/orb/agent.yaml`), restart `orb-agent`.

If bootstrap fails, compare with upstream
[Diode getting started](https://netboxlabs.com/docs/diode/getting-started/).
