#!/usr/bin/env bash
# Emit JSON health report for GARD F13 platform lab.
#
# Exit codes: 0 healthy, 1 degraded, 2 unhealthy
#
# Usage:
#   ./deploy/scripts/platform-lab-health.sh | jq .

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
NETBOX_DIR="$REPO_ROOT/deploy/netbox"
COMPOSE_PROJECT="${NETBOX_COMPOSE_PROJECT:-gard-f7-netbox}"
ENV_FILE="${NETBOX_ENV_FILE:-$NETBOX_DIR/.env}"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a
  source "$ENV_FILE"
  set +a
fi

NETBOX_PORT="${GARD_NETBOX_HOST_PORT:-18888}"
DIODE_PORT="${GARD_DIODE_GRPC_HOST_PORT:-58080}"
BRANCHING="${GARD_NETBOX_BRANCHING_ENABLED:-0}"

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


# NetBox UI
try:
    with urllib.request.urlopen(f"http://127.0.0.1:{netbox_port}/login/", timeout=5) as resp:
        add("netbox_ui", resp.status == 200, f"HTTP {resp.status}")
except (urllib.error.URLError, TimeoutError) as exc:
    add("netbox_ui", False, str(exc))

# Diode nginx TCP
try:
    import socket

    with socket.create_connection(("127.0.0.1", int(diode_port)), timeout=3):
        add("diode_grpc", True, f"port {diode_port} open")
except OSError as exc:
    add("diode_grpc", False, str(exc))

# Container running checks
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

# Diode plugin — import check inside NetBox container
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
    add("branching_plugin", True, "enabled via GARD_NETBOX_BRANCHING_ENABLED=1")
else:
    add("branching_plugin", False, "skipped (optional)")

core_names = {"netbox_ui", "diode_grpc", "orb_agent", "netbox_diode_plugin"}
core_ok = all(c["ok"] for c in checks if c["name"] in core_names)

if not core_ok:
    status = "unhealthy"
    code = 2
elif branching_enabled and not any(c["ok"] for c in checks if c["name"] == "branching_plugin"):
    status = "degraded"
    code = 1
elif not branching_enabled:
    status = "degraded"
    code = 1
else:
    status = "healthy"
    code = 0

report = {
    "status": status,
    "branching_enabled": branching_enabled,
    "checks": checks,
}
print(json.dumps(report, indent=2))
raise SystemExit(code)
PY
