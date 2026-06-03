#!/usr/bin/env bash
# JSON health report. Exit: 0 healthy, 1 degraded, 2 unhealthy.

set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a
  source "$ENV_FILE"
  set +a
fi

NETBOX_PORT="${NETBOX_HOST_PORT:-18888}"
DIODE_PORT="${DIODE_GRPC_HOST_PORT:-58080}"
BRANCHING="${NETBOX_BRANCHING_ENABLED:-0}"

python3 - <<'PY' "$NETBOX_PORT" "$DIODE_PORT" "$BRANCHING" "$COMPOSE_PROJECT"
import json
import subprocess
import sys
import urllib.error
import urllib.request

netbox_port, diode_port, branching, project = sys.argv[1:5]
branching_enabled = branching == "1"
checks = []


def add(name: str, ok: bool, detail: str = "") -> None:
    item = {"name": name, "ok": ok}
    if detail:
        item["detail"] = detail
    checks.append(item)


try:
    with urllib.request.urlopen(f"http://127.0.0.1:{netbox_port}/login/", timeout=5) as resp:
        add("netbox_ui", resp.status == 200, f"HTTP {resp.status}")
except (urllib.error.URLError, TimeoutError) as exc:
    add("netbox_ui", False, str(exc))

try:
    import socket

    with socket.create_connection(("127.0.0.1", int(diode_port)), timeout=3):
        add("diode_grpc", True, f"port {diode_port} open")
except OSError as exc:
    add("diode_grpc", False, str(exc))

for name in ("orb-agent", "netbox-worker"):
    proc = subprocess.run(
        ["docker", "ps", "--filter", f"name={project}-{name}", "--format", "{{.Status}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    status = proc.stdout.strip()
    key = "orb_agent" if name == "orb-agent" else "netbox_worker"
    add(key, bool(status), status or "not running")

proc = subprocess.run(
    [
        "docker",
        "exec",
        f"{project}-netbox-1",
        "/opt/netbox/venv/bin/python",
        "-c",
        "import netbox_diode_plugin  # noqa: F401",
    ],
    capture_output=True,
    text=True,
    check=False,
)
add(
    "netbox_diode_plugin",
    proc.returncode == 0,
    "netbox_diode_plugin import ok" if proc.returncode == 0 else (proc.stderr or proc.stdout)[:120],
)

if branching_enabled:
    add("branching_plugin", True, "enabled")
else:
    add("branching_plugin", False, "skipped (optional)")

core_names = {"netbox_ui", "diode_grpc", "orb_agent", "netbox_diode_plugin"}
core_ok = all(c["ok"] for c in checks if c["name"] in core_names)

if not core_ok:
    status = "unhealthy"
    code = 2
elif not branching_enabled:
    status = "degraded"
    code = 1
else:
    status = "healthy"
    code = 0

print(json.dumps({"status": status, "branching_enabled": branching_enabled, "checks": checks}, indent=2))
raise SystemExit(code)
PY
